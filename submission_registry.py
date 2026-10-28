from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError


def register_submission(
    table,
    tenant_id: str,
    idempotency_key: str,
    payload_fingerprint: str,
) -> str:
    """
    Register a new submission using a DynamoDB conditional write.

    Returns:
        "CREATED" if the submission was registered successfully.
        "KEY_EXISTS" if the scoped submission key already exists.

    Other DynamoDB errors must propagate.
    """
    # Your implementation
    submission_record = {
        "tenant_id": tenant_id,
        "idempotency_key": idempotency_key,
        "payload_fingerprint": payload_fingerprint,
        "status": "STARTING",
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
    # Your implementation
    response = table.get_item(
        Key={
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
        },
        ConsistentRead=True,
    )
    if "Item" not in response:
        raise LookupError("Submission record not found.")

    submission_record = response["Item"]

    if "payload_fingerprint" not in submission_record:
        raise ValueError("Stored submission is missing payload_fingerprint.")

    if submission_record["payload_fingerprint"] == payload_fingerprint:
        return "MATCH"

    return "CONFLICT"
