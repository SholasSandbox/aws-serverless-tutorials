from unittest.mock import Mock, patch

import pytest
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from api_workflow_handoff import normalise_trade
from submission_registry import (
    acquire_submission_lease,
    claim_expired_recovery_lease,
    classify_existing_submission,
    confirm_submission_started,
    fingerprint_normalised_trade,
    get_submission_record,
    register_submission,
)


def test_register_submission_created() -> None:

    table = Mock()

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    submission_record = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": "<sha256-hex-digest>",
        "status": "STARTING",
        **TEST_LEASE,
    }

    response = register_submission(
        table=table,
        tenant_id=submission_record["tenant_id"],
        idempotency_key=submission_record["idempotency_key"],
        payload_fingerprint=submission_record["payload_fingerprint"],
        **TEST_LEASE,
        now=100,
    )

    assert response == "CREATED"

    table.put_item.assert_called_once()
    actual_item = table.put_item.call_args.kwargs["Item"]
    assert actual_item == submission_record
    assert (
        table.put_item.call_args.kwargs["ConditionExpression"]
        == Attr("tenant_id").not_exists()
    )


def test_register_submission_key_exists() -> None:
    table = Mock()
    table.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "Key Exists",
            }
        },
        "put_item",
    )

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    submission_record = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": "<sha256-hex-digest>",
        "status": "STARTING",
        **TEST_LEASE,
    }
    response = register_submission(
        table=table,
        tenant_id=submission_record["tenant_id"],
        idempotency_key=submission_record["idempotency_key"],
        payload_fingerprint=submission_record["payload_fingerprint"],
        now=100,
        **TEST_LEASE,
    )

    assert response == "KEY_EXISTS"
    table.put_item.assert_called_once()


def test_register_submission_other_client_error() -> None:

    table = Mock()

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    error = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied",
            }
        },
        "put_item",
    )
    table.put_item.side_effect = error

    with pytest.raises(ClientError) as exc_info:
        register_submission(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            payload_fingerprint="<sha256-hex-digest>",
            now=100,
            **TEST_LEASE,
        )

    assert exc_info.value is error
    table.put_item.assert_called_once()


def test_classify_existing_submission_match() -> None:
    table = Mock()
    # Simulate DynamoDB returning an item whose fingerprint matches the caller's
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "payload_fingerprint": "<sha256-hex-digest>",
            "status": "STARTING",
        }
    }

    response = classify_existing_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        payload_fingerprint="<sha256-hex-digest>",
    )
    assert response == "MATCH"
    table.get_item.assert_called_once_with(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )


def test_classify_existing_submission_conflict() -> None:
    table = Mock()
    # Simulate DynamoDB returning an item whose fingerprint differs from the caller's
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "payload_fingerprint": "<sha256-hex-digest-stored>",
            "status": "STARTING",
        }
    }

    response = classify_existing_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        payload_fingerprint="<sha256-hex-digest-conflict>",
    )
    assert response == "CONFLICT"
    table.get_item.assert_called_once()


def test_classify_existing_submission_not_found() -> None:
    table = Mock()
    # Simulate DynamoDB returning no results
    table.get_item.return_value = {}

    with pytest.raises(
        LookupError,
        match="Submission record not found.",
    ):
        classify_existing_submission(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            payload_fingerprint="<sha256-hex-digest-conflict>",
        )

    table.get_item.assert_called()


def test_acquire_submission_lease_uses_atomic_lease_condition() -> None:
    """Check the claim request; the mock does not evaluate DynamoDB conditions."""
    table = Mock()

    acquire_submission_lease(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="recovery-attempt-2",
        lease_expires_at=160,
        now=100,
    )

    table.get_item.assert_not_called()
    table.update_item.assert_called_once_with(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        UpdateExpression=("SET recovery_token = :token, lease_expires_at = :expires"),
        ConditionExpression=(
            "#s = :starting AND "
            "(attribute_not_exists(recovery_token) "
            "OR lease_expires_at <= :now)"
        ),
        ExpressionAttributeValues={
            ":token": "recovery-attempt-2",
            ":expires": 160,
            ":starting": "STARTING",
            ":now": 100,
        },
        ExpressionAttributeNames={"#s": "status"},
    )


def test_classify_existing_submission_missing_fingerprint() -> None:
    table = Mock()
    # Simulate DynamoDB returning an item missing a fingerprint
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "status": "STARTING",
        }
    }

    with pytest.raises(
        ValueError,
        match="Stored submission is missing payload_fingerprint.",
    ):
        classify_existing_submission(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            payload_fingerprint="<sha256-hex-digest>",
        )

    table.get_item.assert_called()


def test_classify_existing_submission_client_error() -> None:
    table = Mock()
    # Simulate AWS Service error
    error = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied",
            }
        },
        "GetItem",
    )
    table.get_item.side_effect = error

    with pytest.raises(
        ClientError,
        match="AccessDeniedException",
    ) as exc_info:
        classify_existing_submission(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            payload_fingerprint="<sha256-hex-digest>",
        )
    assert exc_info.value is error
    table.get_item.assert_called()


def test_confirm_submission_started_success() -> None:
    # Return START_CONFIRMED; verify the composite key, update expression, new status and execution ARN
    table = Mock()
    response = confirm_submission_started(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
        recovery_token="token-A",
        now=100,
    )

    assert response == "START_CONFIRMED"

    table.update_item.assert_called_once()
    kwargs = table.update_item.call_args.kwargs

    # Composite key
    assert kwargs["Key"] == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Update expression sets both new attributes
    assert "execution_arn" in kwargs["UpdateExpression"]
    assert kwargs["UpdateExpression"] == "SET execution_arn = :arn, #s = :status"
    assert kwargs["ExpressionAttributeNames"]["#s"] == "status"

    # New status and execution ARN are in the expression attribute values
    assert kwargs["ExpressionAttributeValues"][":arn"] == (
        "arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution"
    )
    assert kwargs["ConditionExpression"] == (
        "#s = :starting AND "
        "recovery_token = :recovery_token "
        "AND lease_expires_at > :now"
    )
    assert kwargs["ExpressionAttributeValues"][":status"] == "START_CONFIRMED"
    assert kwargs["ExpressionAttributeValues"][":starting"] == "STARTING"

    values = kwargs["ExpressionAttributeValues"]
    assert values[":recovery_token"] == "token-A"
    assert values[":now"] == 100


def test_confirm_submission_started_invalid_transition() -> None:
    # Simulate ConditionalCheckFailedException and verify that it propagates

    table = Mock()
    table.update_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            }
        },
        "update_item",
    )
    with pytest.raises(ClientError) as exc_info:
        confirm_submission_started(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
            recovery_token="token-A",
            now=100,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
    table.update_item.assert_called_once()
    kwargs = table.update_item.call_args.kwargs
    values = kwargs["ExpressionAttributeValues"]

    assert values[":recovery_token"] == "token-A"
    assert values[":now"] == 100


def test_confirm_submission_started_client_error() -> None:
    table = Mock()
    error = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied",
            }
        },
        "update_item",
    )
    table.update_item.side_effect = error

    with pytest.raises(ClientError) as exc_info:
        confirm_submission_started(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
            recovery_token="token-A",
            now=100,
        )

    assert exc_info.value is error
    table.update_item.assert_called_once()
    kwargs = table.update_item.call_args.kwargs
    values = kwargs["ExpressionAttributeValues"]

    assert values[":recovery_token"] == "token-A"
    assert values[":now"] == 100


def test_fingerprint_independent_of_dictionary_order() -> None:

    trade_order = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    hashed_trade = fingerprint_normalised_trade(trade_order)

    trade_reordered = {
        "product": "POWER",
        "volume_mwh": 25,
        "trade_id": "TRD-1001",
    }

    hashed_trade_reordered = fingerprint_normalised_trade(trade_reordered)

    assert hashed_trade == hashed_trade_reordered


def test_fingerprint_changes_when_trade_changes() -> None:

    trade_order = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    hashed_trade = fingerprint_normalised_trade(trade_order)

    trade_vol_changed = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 10,
    }

    hashed_trade_reordered = fingerprint_normalised_trade(trade_vol_changed)

    assert hashed_trade != hashed_trade_reordered


def test_fingerprint_ignores_transport_metadata() -> None:

    response = fingerprint_normalised_trade(
        normalise_trade(
            {
                "trade_id": "TRD-1001",
                "product": "POWER",
                "volume_mwh": 25,
                "non_trade_key": "not a trade attribute",
            }
        )
    )

    assert response == fingerprint_normalised_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )


def test_get_submission_record_starting_returns_record() -> None:
    table = Mock()
    # Simulate DynamoDB returning an item whose fingerprint matches the caller's
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "status": "STARTING",
        }
    }

    response = get_submission_record(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
    )
    assert response == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "status": "STARTING",
    }

    table.get_item.assert_called_once_with(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )


def test_get_submission_record_confirmed_returns_record() -> None:
    table = Mock()
    # Simulate DynamoDB returning an item whose fingerprint matches the caller's
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "status": "START_CONFIRMED",
            "execution_arn": "arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
        }
    }

    response = get_submission_record(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
    )
    assert response == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "status": "START_CONFIRMED",
        "execution_arn": "arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
    }

    table.get_item.assert_called_once_with(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )


def test_get_submission_record_missing_raises_lookup_error() -> None:
    table = Mock()
    # Simulate DynamoDB returning no results for submission record lookup
    table.get_item.return_value = {}

    with pytest.raises(
        LookupError,
        match="Submission record not found.",
    ):
        get_submission_record(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
        )

    table.get_item.assert_called()


def test_get_submission_record_confirmed_without_arn_raises_value_error() -> None:
    table = Mock()
    # Confirmed submission with an empty execution ARN.
    table.get_item.return_value = {
        "Item": {
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
            "status": "START_CONFIRMED",
            "execution_arn": "",
        }
    }
    with pytest.raises(
        ValueError,
        match=r"^START_CONFIRMED submission requires a "
        r"non-empty execution_arn string\.",
    ):
        get_submission_record(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
        )

    table.get_item.assert_called()


def test_acquire_submission_lease_success_returns_claimed() -> None:
    table = Mock()

    response = acquire_submission_lease(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="token-1",
        lease_expires_at=1000,
        now=100,
    )

    assert response == "RECOVERY_CLAIMED"

    kwargs = table.update_item.call_args.kwargs
    table.update_item.assert_called_once()

    assert kwargs["Key"] == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    assert (
        kwargs["UpdateExpression"]
        == "SET recovery_token = :token, lease_expires_at = :expires"
    )
    assert kwargs["ExpressionAttributeNames"]["#s"] == "status"

    assert kwargs["ConditionExpression"] == (
        "#s = :starting AND "
        "(attribute_not_exists(recovery_token) "
        "OR lease_expires_at <= :now)"
    )

    assert kwargs["ExpressionAttributeValues"] == {
        ":token": "token-1",
        ":expires": 1000,
        ":starting": "STARTING",
        ":now": 100,
    }


def test_acquire_submission_lease_expired_lease_allows_new_owner(
    submission_table,
) -> None:

    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: an existing owner's lease has expired.
    table.put_item(
        Item={
            **key,
            "status": "STARTING",
            "recovery_token": "old-owner-token",
            "lease_expires_at": 90,
        }
    )

    # Act: acquire ownership at time 100 with a new lease.
    response = acquire_submission_lease(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="new-owner-token",
        lease_expires_at=120,
        now=100,
    )

    # Assert: the stored owner and expiry were replaced.
    record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert response == "RECOVERY_CLAIMED"
    assert record == {
        **key,
        "status": "STARTING",
        "recovery_token": "new-owner-token",
        "lease_expires_at": 120,
    }


def test_acquire_submission_lease_propagates_conditional_failure() -> None:
    table = Mock()
    table.update_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            }
        },
        "update_item",
    )
    with pytest.raises(ClientError) as exc_info:
        acquire_submission_lease(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            recovery_token="token-1",
            lease_expires_at=1000,
            now=100,
        )

    table.update_item.assert_called_once()

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"


@pytest.mark.parametrize("lease_expires_at", [99, 100, 999, 1000])
def test_acquire_submission_lease_invalid_lease(lease_expires_at) -> None:
    table = Mock()

    with pytest.raises(
        ValueError,
        match=r"^lease_expires_at must be later than now\.$",
    ):
        acquire_submission_lease(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            recovery_token="token-1",
            lease_expires_at=lease_expires_at,
            now=1000,
        )

    table.update_item.assert_not_called()


@pytest.mark.parametrize("recovery_token", ["", None, "   ", 123])
def test_acquire_submission_lease_invalid_token(recovery_token) -> None:
    table = Mock()

    with pytest.raises(
        ValueError,
        match=(
            r"^claim submission recovery requires a "
            r"non-empty recovery token string\.$"
        ),
    ):
        acquire_submission_lease(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            recovery_token=recovery_token,
            lease_expires_at=1000,
            now=100,
        )

    table.update_item.assert_not_called()


def test_acquire_submission_lease_active_lease_preserves_owner(
    submission_table,
) -> None:

    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: the existing owner's lease is still active.
    original_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "old-owner-token",
        "lease_expires_at": 150,
    }
    table.put_item(Item=original_record)

    with pytest.raises(ClientError) as exc_info:
        acquire_submission_lease(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            recovery_token="new-owner-token",
            lease_expires_at=200,
            now=100,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    stored_record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert stored_record == original_record


def test_confirm_submission_started_rejects_stale_owner(submission_table) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: TOKEN-B is the current owner; TOKEN-A is stale.

    original_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "TOKEN-B",
        "lease_expires_at": 200,
    }
    table.put_item(Item=original_record)

    with pytest.raises(ClientError) as exc_info:
        confirm_submission_started(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
            recovery_token="TOKEN-A",
            now=150,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    stored_record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert stored_record == original_record


def test_confirm_submission_started_accepts_current_owner(submission_table) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: the caller holds the current, unexpired lease.

    original_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
    }
    table.put_item(Item=original_record)

    execution_arn = (
        "arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution"
    )

    response = confirm_submission_started(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        execution_arn=execution_arn,
        recovery_token="TOKEN-A",
        now=150,
    )

    stored_record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert response == "START_CONFIRMED"
    assert stored_record == {
        **original_record,
        "status": "START_CONFIRMED",
        "execution_arn": execution_arn,
    }


def test_confirm_submission_started_rejects_expired_owner(submission_table) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: the existing owner's lease has expired.
    original_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 150,
    }
    table.put_item(Item=original_record)

    with pytest.raises(ClientError) as exc_info:
        confirm_submission_started(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
            recovery_token="TOKEN-A",
            now=200,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    stored_record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert stored_record == original_record


def test_confirm_submission_started_rejects_unowned_record(submission_table) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Arrange: submission record has no recovery owner
    original_record = {
        **key,
        "status": "STARTING",
        "lease_expires_at": 150,
    }
    table.put_item(Item=original_record)

    with pytest.raises(ClientError) as exc_info:
        confirm_submission_started(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:myStateMachine:myExecution",
            recovery_token="TOKEN-A",
            now=100,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    stored_record = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert stored_record == original_record


TOKEN_ERROR = "recovery_token must be a non-empty string."
LEASE_ERROR = "lease_expires_at must be an integer greater than now."


@pytest.mark.parametrize(
    "recovery_token, lease_expires_at, now, expected_message",
    [
        ("", 200, 100, TOKEN_ERROR),
        ("   ", 200, 100, TOKEN_ERROR),
        (None, 200, 100, TOKEN_ERROR),
        ("valid-token", 100, 100, LEASE_ERROR),
        ("valid-token", 99, 100, LEASE_ERROR),
    ],
)
def test_register_submission_rejects_invalid_initial_lease(
    recovery_token,
    lease_expires_at,
    now,
    expected_message,
) -> None:
    table = Mock()

    submission_record = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": "<sha256-hex-digest>",
        "status": "STARTING",
    }

    with pytest.raises(
        ValueError,
    ) as exc_info:
        register_submission(
            table=table,
            tenant_id=submission_record["tenant_id"],
            idempotency_key=submission_record["idempotency_key"],
            payload_fingerprint=submission_record["payload_fingerprint"],
            recovery_token=recovery_token,
            lease_expires_at=lease_expires_at,
            now=now,
        )

    assert str(exc_info.value) == expected_message
    table.put_item.assert_not_called()


def test_claim_expired_recovery_lease_succeeded(submission_table) -> None:
    table = submission_table
    key = {"tenant_id": "TENANT-A", "idempotency_key": "SUBMISSION-1001"}

    # Arrange: current lease has expired.
    expected_values = {
        "expected_recovery_token": "token-A",
        "expected_payload_fingerprint": "<sha256-hex-digest>",
    }

    table.put_item(
        Item={
            **key,
            "status": "STARTING",
            "recovery_token": "token-A",
            "payload_fingerprint": "<sha256-hex-digest>",
            "lease_expires_at": 90,
        }
    )

    response = claim_expired_recovery_lease(
        table=table,
        **key,
        **expected_values,
        new_recovery_token="token-B",
        new_lease_expires_at=150,
        now=100,
    )
    assert response == "CLAIMED"

    record = table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record["status"] == "STARTING"
    assert record["recovery_token"] == "token-B"
    assert record["lease_expires_at"] == 150


def test_claim_expired_recovery_lease_failed_different_fingerprint(
    submission_table,
) -> None:
    table = submission_table
    key = {"tenant_id": "TENANT-A", "idempotency_key": "SUBMISSION-1001"}

    # Arrange: current lease has expired.
    expected_values = {
        "expected_recovery_token": "token-A",
        "expected_payload_fingerprint": "<sha256-hex-digest>",
    }

    table.put_item(
        Item={
            **key,
            "status": "STARTING",
            "recovery_token": "token-A",
            "payload_fingerprint": "<sha256-hex-digest_changed>",
            "lease_expires_at": 90,
        }
    )

    response = claim_expired_recovery_lease(
        table=table,
        **key,
        **expected_values,
        new_recovery_token="token-B",
        new_lease_expires_at=150,
        now=100,
    )
    assert response == "NOT_CLAIMED"

    record = table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record["recovery_token"] == "token-A"
    assert record["lease_expires_at"] == 90


@pytest.mark.parametrize(
    "current_lease_expires_at,new_lease_expires_at, now",
    [
        pytest.param(121, 150, 120, id="lease_expires_now"),
        pytest.param(110, 110, 100, id="lease_expires_after_now"),
    ],
)
def test_claim_expired_recovery_lease_failed_different_lease_not_expired(
    submission_table,
    current_lease_expires_at: int,
    new_lease_expires_at: int,
    now: int,
) -> None:
    table = submission_table
    key = {"tenant_id": "TENANT-A", "idempotency_key": "SUBMISSION-1001"}

    # Arrange: current lease has expired.
    expected_values = {
        "expected_recovery_token": "token-A",
        "expected_payload_fingerprint": "<sha256-hex-digest>",
    }

    table.put_item(
        Item={
            **key,
            "status": "STARTING",
            "recovery_token": "token-A",
            "payload_fingerprint": "<sha256-hex-digest>",
            "lease_expires_at": current_lease_expires_at,
        }
    )

    response = claim_expired_recovery_lease(
        table=table,
        **key,
        **expected_values,
        new_recovery_token="token-B",
        new_lease_expires_at=new_lease_expires_at,
        now=now,
    )
    assert response == "NOT_CLAIMED"

    record = table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record["status"] == "STARTING"
    assert record["recovery_token"] == "token-A"
    assert record["lease_expires_at"] == current_lease_expires_at


def test_claim_expired_recovery_lease_failed_dynamodb_error(submission_table) -> None:
    table = submission_table
    key = {"tenant_id": "TENANT-A", "idempotency_key": "SUBMISSION-1001"}

    # Arrange: current lease has expired.
    expected_values = {
        "expected_recovery_token": "token-A",
        "expected_payload_fingerprint": "<sha256-hex-digest>",
    }

    table.put_item(
        Item={
            **key,
            "status": "STARTING",
            "recovery_token": "token-A",
            "payload_fingerprint": "<sha256-hex-digest>",
            "lease_expires_at": 90,
        }
    )

    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
        "UpdateItem",
    )

    with patch.object(submission_table, "update_item", side_effect=error):
        with pytest.raises(ClientError) as exc_info:
            claim_expired_recovery_lease(
                table=table,
                **key,
                **expected_values,
                new_recovery_token="token-B",
                new_lease_expires_at=150,
                now=100,
            )
    assert exc_info.value is error
    record = table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record["status"] == "STARTING"
    assert record["recovery_token"] == "token-A"
    assert record["lease_expires_at"] == 90
