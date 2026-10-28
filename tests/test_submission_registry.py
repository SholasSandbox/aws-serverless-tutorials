from unittest.mock import Mock

import pytest
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from submission_registry import (
    classify_existing_submission,
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
    assert table.put_item.call_args.kwargs["ConditionExpression"] == Attr("tenant_id").not_exists()



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
