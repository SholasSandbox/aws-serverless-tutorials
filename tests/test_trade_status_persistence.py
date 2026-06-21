import pytest

from unittest.mock import Mock

from trade_result_persistence import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    ARTIFACT_TYPE_ACCEPTED,
    ARTIFACT_TYPE_REJECTED,
    SCHEMA_VERSION,
)

from trade_status_persistence import (
    build_trade_status_record,
    build_trade_status_record_from_artifact,
    persist_trade_status_record,
)


class FakeConditionalCheckFailedException(Exception):
    pass


def test_build_trade_status_record_for_accepted_trade():
    status_record = build_trade_status_record(
        trade_id="TRD-001",
        status=STATUS_ACCEPTED,
        result_type="accepted",
        processed_at="2026-06-02T18:30:00Z",
        s3_bucket="test-results-bucket",
        s3_key="trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        rejection_summary=None,
        schema_version="1.0",
    )

    assert status_record == {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        "rejection_summary": None,
        "schema_version": "1.0",
    }


def test_build_trade_status_record_for_rejected_trade():
    status_record = build_trade_status_record(
        trade_id="TRD-002",
        status=STATUS_REJECTED,
        result_type="rejected",
        processed_at="2026-06-02T18:31:00Z",
        s3_bucket="test-results-bucket",
        s3_key="trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
        rejection_summary="volume_mwh must be greater than 0",
        schema_version="1.0",
    )

    assert status_record == {
        "trade_id": "TRD-002",
        "processed_at": "2026-06-02T18:31:00Z",
        "status": "REJECTED",
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
        "rejection_summary": "volume_mwh must be greater than 0",
        "schema_version": "1.0",
    }

#Revisit this test, after 2 other lesson 26 tests completed
def test_persist_trade_status_record_calls_dynamodb_put_item():
    dynamodb_table = Mock()

    status_record = {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        "rejection_summary": None,
        "schema_version": "1.0",
    }

    persist_trade_status_record(
        dynamodb_table=dynamodb_table,
        status_record=status_record,
    )

    dynamodb_table.put_item.assert_called_once_with(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",      
    )


def test_persist_trade_status_record_returns_stable_response():
    dynamodb_table = Mock()
    dynamodb_table.put_item.return_value = {
        "ResponseMetadata": {
            "HTTPStatusCode": 200,
        }
    }

    status_record = {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        "rejection_summary": None,
        "schema_version": "1.0",
    }

    response = persist_trade_status_record(
        dynamodb_table=dynamodb_table,
        status_record=status_record,
    )

    assert response == {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": "ACCEPTED",
    }



def test_build_trade_status_record_from_accepted_artifact_and_s3_pointer():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
    }

    status_record = build_trade_status_record_from_artifact(
        artifact=artifact,
        s3_pointer=s3_pointer,
    )

    assert status_record == {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
        "rejection_summary": None,
        "schema_version": "1.0",
    }


def test_build_trade_status_record_from_rejected_artifact_and_s3_pointer():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_REJECTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_REJECTED,
        "trade_id": "TRD-002",
        "processed_at": "2026-06-02T18:31:00Z",
        "trade": {
            "trade_id": "TRD-002",
            "product": "POWER",
            "volume_mwh": 0,
        },
        "validation": {
            "is_valid": False,
            "errors": ["volume_mwh must be greater than 0"],
        },
        "rejection_reasons": ["volume_mwh must be greater than 0"],
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
    }

    status_record = build_trade_status_record_from_artifact(
        artifact=artifact,
        s3_pointer=s3_pointer,
    )

    assert status_record == {
        "trade_id": "TRD-002",
        "processed_at": "2026-06-02T18:31:00Z",
        "status": "REJECTED",
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
        "rejection_summary": "volume_mwh must be greater than 0",
        "schema_version": "1.0",
    }


def test_build_trade_status_record_from_artifact_rejects_missing_schema_version():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",      
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
    }

    with pytest.raises(ValueError, match="Missing artifact field: schema_version"):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )


@pytest.mark.parametrize(
    "s3_pointer, expected_missing_s3_field",
    [
        (
            {
                "bucket": "test-results-bucket",
            },
            "key",
        ),
        (
            {
                "key": "trade_id=TRD-002.json",
            },
            "bucket",
        ),
    ],
)
def test_build_trade_status_record_from_artifact_rejects_missing_s3_pointer_field(
    s3_pointer,
    expected_missing_s3_field
):
    artifact = {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "validation": {
            "is_valid": True,
            "errors": [],
        },
    }

    with pytest.raises(
        ValueError,
        match=f"Missing S3 pointer field: {expected_missing_s3_field}",
    ):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )


def test_build_trade_status_record_from_artifact_rejects_accepted_artifact_with_rejected_status():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_REJECTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "validation": {
            "is_valid": True,
            "errors": [],
        },
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
    }

    with pytest.raises(
        ValueError,
        match="accepted artifact must have status ACCEPTED",
    ):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )


def test_build_trade_status_record_from_artifact_rejects_rejected_artifact_with_accepted_status():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_REJECTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "validation": {
            "is_valid": True,
            "errors": [],
        },
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
    }

    with pytest.raises(
        ValueError,
        match="rejected artifact must have status REJECTED",
    ):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )

def test_build_trade_status_record_from_artifact_rejects_accepted_artifact_with_invalid_validation():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "validation": {
            "is_valid": False,
            "errors": ["volume_mwh must be greater than 0"],
        },
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json",
    }

    with pytest.raises(
        ValueError,
        match="accepted artifact must have validation is_valid true",
    ):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )


def test_build_trade_status_record_from_artifact_rejects_rejected_artifact_with_valid_validation():
    artifact = {
        "artifact_type": ARTIFACT_TYPE_REJECTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_REJECTED,
        "trade_id": "TRD-002",
        "processed_at": "2026-06-02T18:31:00Z",
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "rejection_reasons": [],
    }

    s3_pointer = {
        "bucket": "test-results-bucket",
        "key": "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-002.json",
    }

    with pytest.raises(
        ValueError,
        match="rejected artifact must have validation is_valid false",
    ):
        build_trade_status_record_from_artifact(
            artifact=artifact,
            s3_pointer=s3_pointer,
        )


def test_persist_trade_status_uses_conditional_put_for_new_trade_status():
    table = Mock()

    status_record = {
        "trade_id": "TRD-001",
        "result_type": "ACCEPTED",
        "status": "persisted",
        "s3_bucket": "trade-results-bucket",
        "s3_key": "results/accepted/trade_id=TRD-001/result.json",
        "processed_at": "2026-06-16T20:00:00Z",

    }

    persist_trade_status_record(dynamodb_table=table, status_record=status_record)

    table.put_item.assert_called_once()

    put_call = table.put_item.call_args.kwargs

    assert put_call["Item"] == status_record
    assert put_call["ConditionExpression"] == "attribute_not_exists(trade_id)"


def test_persist_trade_status_treats_duplicate_trade_status_as_idempotent_success():
    table = Mock()

    status_record = {
        "trade_id": "TRD-001",
        "result_type": "ACCEPTED",
        "status": "persisted",
        "s3_bucket": "trade-results-bucket",
        "s3_key": "results/accepted/trade_id=TRD-001/result.json",
        "processed_at": "2026-06-16T20:00:00Z",
    }

    table.put_item.side_effect = FakeConditionalCheckFailedException(
        "Conditional check failed"
    )

    result = persist_trade_status_record(
        dynamodb_table=table,
        status_record=status_record,
        conditional_check_failed_exception=FakeConditionalCheckFailedException,        
    )

    assert result == {
        "status": "already_persisted",
        "trade_id": "TRD-001",
        "result_type": "ACCEPTED",
    }

    table.put_item.assert_called_once_with(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",      
    )


def test_save_trade_status_does_not_swallow_unexpected_dynamodb_errors():
    table = Mock()

    status_record = {
        "trade_id": "TRD-001",
        "result_type": "ACCEPTED",
        "status": "persisted",
        "s3_bucket": "trade-results-bucket",
        "s3_key": "results/accepted/trade_id=TRD-001/result.json",
        "processed_at": "2026-06-16T20:00:00Z",
    }

    table.put_item.side_effect = RuntimeError("DynamoDB unavailable")

    with pytest.raises(RuntimeError, match="DynamoDB unavailable"):
        persist_trade_status_record(
            dynamodb_table=table,
            status_record=status_record,

        )

    table.put_item.assert_called_once_with(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",
    )
