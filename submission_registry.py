import hashlib
import json
from collections.abc import Mapping
from typing import Any

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError


def fingerprint_normalised_trade(
    trade: Mapping[str, Any],
) -> str:
    """Return a deterministic SHA-256 fingerprint."""
    serialised_trade = json.dumps(
        dict(trade),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialised_trade.encode("utf-8")).hexdigest()


def register_submission(
    table,
    tenant_id: str,
    idempotency_key: str,
    payload_fingerprint: str,
    recovery_token: str,
    lease_expires_at: int,
    now: int,
) -> str:
    """
    Register a new submission using a DynamoDB conditional write.

    Returns:
        "CREATED" if the submission was registered successfully.
        "KEY_EXISTS" if the scoped submission key already exists.

    Other DynamoDB errors must propagate.
    """

    if not isinstance(recovery_token, str) or not recovery_token.strip():
        raise ValueError("recovery_token must be a non-empty string.")

    if (
        type(now) is not int
        or type(lease_expires_at) is not int
        or lease_expires_at <= now
    ):
        raise ValueError("lease_expires_at must be an integer greater than now.")

    submission_record = {
        "tenant_id": tenant_id,
        "idempotency_key": idempotency_key,
        "payload_fingerprint": payload_fingerprint,
        "status": "STARTING",
        "recovery_token": recovery_token,
        "lease_expires_at": lease_expires_at,
    }

    try:
        table.put_item(
            Item=submission_record,
            ConditionExpression=Attr("tenant_id").not_exists(),
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return "KEY_EXISTS"
        raise

    return "CREATED"


def classify_existing_submission(
    table,
    tenant_id: str,
    idempotency_key: str,
    payload_fingerprint: str,
) -> str:
    """
    Retrieve and classify an existing submission.

    Returns:
        "MATCH" if the stored fingerprint matches.
        "CONFLICT" if the fingerprints differ.

    Raises:
        LookupError if the record cannot be found.
        ClientError for DynamoDB service failures.
    """
    submission_record = get_submission_record(
        table,
        tenant_id,
        idempotency_key,
    )

    if "payload_fingerprint" not in submission_record:
        raise ValueError("Stored submission is missing payload_fingerprint.")

    if submission_record["payload_fingerprint"] == payload_fingerprint:
        return "MATCH"

    return "CONFLICT"


def confirm_submission_started(
    table,
    tenant_id: str,
    idempotency_key: str,
    execution_arn: str,
    recovery_token: str,
    now: int,
) -> str:
    """
    Conditionally confirm that a submission's workflow started.

    Returns:
        "START_CONFIRMED" when the registry update succeeds.

    Raises:
        ClientError if the conditional update fails
        or another DynamoDB service error occurs.
    """
    # Your implementation
    table.update_item(
        Key={
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
        },
        UpdateExpression="SET execution_arn = :arn, #s = :status",
        ConditionExpression=(
            "#s = :starting AND "
            "recovery_token = :recovery_token "
            "AND lease_expires_at > :now"
        ),
        ExpressionAttributeValues={
            ":arn": execution_arn,
            ":status": "START_CONFIRMED",
            ":starting": "STARTING",
            ":recovery_token": recovery_token,
            ":now": now,
        },
        ExpressionAttributeNames={
            "#s": "status",  # 'status' is a reserved word in DynamoDB
        },
    )

    return "START_CONFIRMED"


def get_submission_record(
    table,
    tenant_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Read a submission with strong consistency and validate its state."""
    response = table.get_item(
        Key={
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
        },
        ConsistentRead=True,
    )

    if "Item" not in response:
        raise LookupError(
            f"Submission record not found for "
            f"tenant_id={tenant_id!r}, "
            f"idempotency_key={idempotency_key!r}."
        )

    record = response["Item"]
    status = record.get("status")

    match status:
        case None:
            raise ValueError("Submission status is missing or None.")

        case "STARTING":
            return record

        case "START_CONFIRMED":
            execution_arn = record.get("execution_arn")

            if not isinstance(execution_arn, str) or not execution_arn.strip():
                raise ValueError(
                    "START_CONFIRMED submission requires a "
                    "non-empty execution_arn string."
                )

            return record
        case _:
            raise ValueError(f"Expected START_CONFIRMED or STARTING, got {status!r}.")


def acquire_submission_lease(
    table,
    tenant_id: str,
    idempotency_key: str,
    recovery_token: str,
    lease_expires_at: int,
    now: int,
) -> str:
    """Conditionally acquire recovery ownership."""
    if not isinstance(recovery_token, str) or not recovery_token.strip():
        raise ValueError(
            "claim submission recovery requires a non-empty recovery token string."
        )

    if lease_expires_at <= now:
        raise ValueError("lease_expires_at must be later than now.")

    table.update_item(
        Key={
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
        },
        UpdateExpression=("SET recovery_token = :token, lease_expires_at = :expires"),
        ConditionExpression=(
            "#s = :starting AND "
            "(attribute_not_exists(recovery_token) "
            "OR lease_expires_at <= :now)"
        ),
        ExpressionAttributeValues={
            ":token": recovery_token,
            ":expires": lease_expires_at,
            ":starting": "STARTING",
            ":now": now,
        },
        ExpressionAttributeNames={
            "#s": "status",  # 'status' is a reserved word in DynamoDB
        },
    )

    return "RECOVERY_CLAIMED"


def claim_expired_recovery_lease(
    *,
    table: Any,
    tenant_id: str,
    idempotency_key: str,
    expected_recovery_token: str,
    expected_payload_fingerprint: str,
    new_recovery_token: str,
    new_lease_expires_at: int,
    now: int,
) -> str:

    try:
        table.update_item(
            Key={
                "tenant_id": tenant_id,
                "idempotency_key": idempotency_key,
            },
            UpdateExpression=(
                "SET recovery_token = :new_token, lease_expires_at = :new_expiry"
            ),
            ConditionExpression=(
                "#s = :starting "
                "AND recovery_token = :expected_token "
                "AND payload_fingerprint = :expected_fingerprint "
                "AND lease_expires_at <= :now"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":starting": "STARTING",
                ":expected_token": expected_recovery_token,
                ":expected_fingerprint": expected_payload_fingerprint,
                ":now": now,
                ":new_token": new_recovery_token,
                ":new_expiry": new_lease_expires_at,
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return "NOT_CLAIMED"
        raise
    return "CLAIMED"
