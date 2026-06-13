import pytest
import json
from unittest.mock import Mock

from trade_result_persistence import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
)

from trade_persistence_workflow import persist_trade_processing_result


def test_persist_trade_processing_result_persists_accepted_trade_artifact_and_status():
    s3_client = Mock()
    dynamodb_table = Mock()

    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 100,
    }

    validation = {
        "is_valid": True,
        "errors": [],
    }

    response = persist_trade_processing_result(
        trade=trade,
        validation=validation,
        processed_at="2026-06-02T18:30:00Z",
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
        bucket_name="test-results-bucket",
    )

    expected_s3_key = (
        "trade-results/accepted/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001.json"
    )

    s3_client.put_object.assert_called_once()

    s3_put_kwargs = s3_client.put_object.call_args.kwargs

    assert s3_put_kwargs["Bucket"] == "test-results-bucket"
    assert s3_put_kwargs["Key"] == expected_s3_key
    assert s3_put_kwargs["ContentType"] == "application/json"

    persisted_artifact = json.loads(s3_put_kwargs["Body"])

    assert persisted_artifact == {
        "artifact_type": "accepted_trade",
        "schema_version": "1.0",
        "status": STATUS_ACCEPTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "trade": trade,
        "validation": validation,
    }

    dynamodb_table.put_item.assert_called_once()

    dynamodb_put_kwargs = dynamodb_table.put_item.call_args.kwargs

    assert dynamodb_put_kwargs["Item"] == {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": STATUS_ACCEPTED,
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
        "rejection_summary": None,
        "schema_version": "1.0",
    }

    assert response == {
        "trade_id": "TRD-001",
        "status": STATUS_ACCEPTED,
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
    }


def test_persist_trade_processing_result_persists_rejected_trade_artifact_and_status():
    s3_client = Mock()
    dynamodb_table = Mock()

    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 0,
    }

    validation = {
        "is_valid": False,
        "errors": ["volume_mwh must be greater than 0"],
    }

    response = persist_trade_processing_result(
        trade=trade,
        validation=validation,
        processed_at="2026-06-02T18:30:00Z",
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
        bucket_name="test-results-bucket",
    )

    expected_s3_key = (
        "trade-results/rejected/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001.json"
    )

    s3_client.put_object.assert_called_once()

    s3_put_kwargs = s3_client.put_object.call_args.kwargs

    assert s3_put_kwargs["Bucket"] == "test-results-bucket"
    assert s3_put_kwargs["Key"] == expected_s3_key
    assert s3_put_kwargs["ContentType"] == "application/json"

    persisted_artifact = json.loads(s3_put_kwargs["Body"])

    assert persisted_artifact == {
        "artifact_type": "rejected_trade",
        "schema_version": "1.0",
        "status": STATUS_REJECTED,
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "trade": trade,
        "validation": validation,
        "rejection_reasons": ["volume_mwh must be greater than 0"],
    }

    dynamodb_table.put_item.assert_called_once()

    dynamodb_put_kwargs = dynamodb_table.put_item.call_args.kwargs

    assert dynamodb_put_kwargs["Item"] == {
        "trade_id": "TRD-001",
        "processed_at": "2026-06-02T18:30:00Z",
        "status": STATUS_REJECTED,
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
        "rejection_summary": "volume_mwh must be greater than 0",
        "schema_version": "1.0",
    }

    assert response == {
        "trade_id": "TRD-001",
        "status": STATUS_REJECTED,
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
    }


def test_persist_trade_processing_result_rejects_validation_without_is_valid():
    s3_client = Mock()
    dynamodb_table = Mock()

    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 100,
    }

    validation = {
        "errors": [],
    }

    with pytest.raises(
        ValueError,
        match="validation is missing is_valid",
    ):
        persist_trade_processing_result(
            trade=trade,
            validation=validation,
            processed_at="2026-06-02T18:30:00Z",
            s3_client=s3_client,
            dynamodb_table=dynamodb_table,
            bucket_name="test-results-bucket",
        )

    s3_client.put_object.assert_not_called()
    dynamodb_table.put_item.assert_not_called()


def test_persist_trade_processing_result_rejects_validation_is_valid_not_boolean():
    s3_client = Mock()
    dynamodb_table = Mock()

    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 100,
    }

    validation = {
        "is_valid": "true",
        "errors": [],
    }

    with pytest.raises(
        ValueError,
        match="validation is_valid must be a boolean",
    ):
        persist_trade_processing_result(
            trade=trade,
            validation=validation,
            processed_at="2026-06-02T18:30:00Z",
            s3_client=s3_client,
            dynamodb_table=dynamodb_table,
            bucket_name="test-results-bucket",
        )

    s3_client.put_object.assert_not_called()
    dynamodb_table.put_item.assert_not_called()