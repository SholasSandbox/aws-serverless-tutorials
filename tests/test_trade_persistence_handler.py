import pytest
from unittest.mock import Mock

from trade_persistence_handler import trade_persistence_handler

import trade_persistence_handler as handler_module


def test_trade_persistence_handler_persists_accepted_trade_result():
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

    event = {
        "trade": trade,
        "validation": validation,
        "processed_at": "2026-06-02T18:30:00Z",
        "bucket_name": "test-results-bucket",
    }

    response = trade_persistence_handler(
        event,
        None,
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
    )

    expected_s3_key = (
        "trade-results/accepted/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001.json"
    )

    s3_client.put_object.assert_called_once()
    dynamodb_table.put_item.assert_called_once()

    assert response == {
        "trade_id": "TRD-001",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
    }


def test_trade_persistence_handler_persists_rejected_trade_result():
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

    event = {
        "trade": trade,
        "validation": validation,
        "processed_at": "2026-06-02T18:30:00Z",
        "bucket_name": "test-results-bucket",
    }

    response = trade_persistence_handler(
        event,
        None,
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
    )

    expected_s3_key = (
        "trade-results/rejected/"
        "year=2026/month=06/day=02/"
        "trade_id=TRD-001.json"
    )

    s3_client.put_object.assert_called_once()
    dynamodb_table.put_item.assert_called_once()

    assert response == {
        "trade_id": "TRD-001",
        "status": "REJECTED",
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
    }


def test_trade_persistence_handler_rejects_missing_bucket_name():
    s3_client = Mock()
    dynamodb_table = Mock()

    trade = {
        "trade_id": "TRD-001",
        "product": "POWER",
        "volume_mwh": 100,
    }

    validation = {
        "is_valid": False,
        "errors": [],
    }

    event = {
        "trade": trade,
        "validation": validation,
        "processed_at": "2026-06-02T18:30:00Z",
    }
    with pytest.raises(
        ValueError,
        match="Missing event field: bucket_name",
    ):
        trade_persistence_handler(
            event,
            None,
            s3_client=s3_client,
            dynamodb_table=dynamodb_table,
        )

    s3_client.put_object.assert_not_called()
    dynamodb_table.put_item.assert_not_called()


def test_lambda_handler_creates_aws_clients_and_delegates(monkeypatch):
    s3_client = Mock()
    dynamodb_resource = Mock()
    dynamodb_table = Mock()
    context = Mock()

    dynamodb_resource.Table.return_value = dynamodb_table

    event = {
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
        "bucket_name": "test-results-bucket",
    }

    expected_response = {
        "trade_id": "TRD-001",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": (
            "trade-results/accepted/"
            "year=2026/month=06/day=02/"
            "trade_id=TRD-001.json"
        ),
    }

    fake_boto3 = Mock()
    fake_boto3.client.return_value = s3_client
    fake_boto3.resource.return_value = dynamodb_resource

    def fake_trade_persistence_handler(
        event,
        context,
        *,
        s3_client,
        dynamodb_table,
    ):
        return expected_response

    monkeypatch.setenv("TRADE_STATUS_TABLE_NAME", "trade-status-table")
    monkeypatch.setattr(handler_module, "boto3", fake_boto3)
    monkeypatch.setattr(
        handler_module,
        "trade_persistence_handler",
        fake_trade_persistence_handler,
    )

    response = handler_module.lambda_handler(event, context)

    fake_boto3.client.assert_called_once_with("s3")
    fake_boto3.resource.assert_called_once_with("dynamodb")
    dynamodb_resource.Table.assert_called_once_with("trade-status-table")

    assert response == expected_response
