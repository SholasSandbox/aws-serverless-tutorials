from unittest.mock import Mock

import pytest
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from submission_registry import (
    classify_existing_submission,
    confirm_submission_started,
    register_submission,
)


def test_register_submission_created() -> None:
    table = Mock()

    submission_record = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": "<sha256-hex-digest>",
        "status": "STARTING",
    }

    response = register_submission(
        table=table,
        tenant_id=submission_record["tenant_id"],
        idempotency_key=submission_record["idempotency_key"],
        payload_fingerprint=submission_record["payload_fingerprint"],
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

    submission_record = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": "<sha256-hex-digest>",
        "status": "STARTING",
    }
    response = register_submission(
        table=table,
        tenant_id=submission_record["tenant_id"],
        idempotency_key=submission_record["idempotency_key"],
        payload_fingerprint=submission_record["payload_fingerprint"],
    )

    assert response == "KEY_EXISTS"
    table.put_item.assert_called_once()


def test_register_submission_other_client_error() -> None:
    table = Mock()
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
    assert kwargs["ConditionExpression"] == Attr("status").eq("STARTING")
    assert kwargs["ExpressionAttributeValues"][":status"] == "START_CONFIRMED"


def test_confirm_submission_started_invalid_transition()-> None:
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
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"


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
        )

    assert exc_info.value is error
    table.update_item.assert_called_once()
