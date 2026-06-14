import pytest
from unittest.mock import Mock

import trade_persistence_handler as handler_module


def test_trade_persistence_handler_persists_accepted_trade_result():
    s3_client = Mock()
    dynamodb_table = Mock()

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
    }

    response = handler_module.trade_persistence_handler(
        event,
        None,
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

    event = {
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 0,
        },
        "validation": {
            "is_valid": False,
            "errors": ["volume_mwh must be greater than 0"],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    response = handler_module.trade_persistence_handler(
        event,
        None,
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
    dynamodb_table.put_item.assert_called_once()

    assert response == {
        "trade_id": "TRD-001",
        "status": "REJECTED",
        "result_type": "rejected",
        "s3_bucket": "test-results-bucket",
        "s3_key": expected_s3_key,
    }


def test_trade_persistence_handler_rejects_missing_processed_at():
    s3_client = Mock()
    dynamodb_table = Mock()

    event = {
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": False,
            "errors": [],
        },
    }

    with pytest.raises(
        ValueError,
        match="Missing event field: processed_at",
    ):
        handler_module.trade_persistence_handler(
            event,
            None,
            s3_client=s3_client,
            dynamodb_table=dynamodb_table,
            bucket_name="test-results-bucket",
        )

    s3_client.put_object.assert_not_called()
    dynamodb_table.put_item.assert_not_called()


def test_build_persistence_dependencies_uses_environment_and_boto3(monkeypatch):
    s3_client = Mock()
    dynamodb_resource = Mock()
    dynamodb_table = Mock()

    dynamodb_resource.Table.return_value = dynamodb_table

    fake_boto3 = Mock()
    fake_boto3.client.return_value = s3_client
    fake_boto3.resource.return_value = dynamodb_resource

    monkeypatch.setenv(
        handler_module.TRADE_RESULTS_BUCKET_ENV_VAR,
        "test-results-bucket",
    )
    monkeypatch.setenv(
        handler_module.TRADE_STATUS_TABLE_ENV_VAR,
        "trade-status-table",
    )
    monkeypatch.setattr(handler_module, "boto3", fake_boto3)

    dependencies = handler_module.build_persistence_dependencies()

    fake_boto3.client.assert_called_once_with("s3")
    fake_boto3.resource.assert_called_once_with("dynamodb")
    dynamodb_resource.Table.assert_called_once_with("trade-status-table")

    assert dependencies == {
        "s3_client": s3_client,
        "dynamodb_table": dynamodb_table,
        "bucket_name": "test-results-bucket",
    }


def test_lambda_handler_builds_dependencies_and_delegates(monkeypatch):
    s3_client = Mock()
    dynamodb_table = Mock()
    context = Mock()

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

    fake_dependencies = {
        "s3_client": s3_client,
        "dynamodb_table": dynamodb_table,
        "bucket_name": "test-results-bucket",
    }

    fake_trade_persistence_handler = Mock(return_value=expected_response)

    monkeypatch.setattr(
        handler_module,
        "build_persistence_dependencies",
        Mock(return_value=fake_dependencies),
    )
    monkeypatch.setattr(
        handler_module,
        "trade_persistence_handler",
        fake_trade_persistence_handler,
    )

    response = handler_module.lambda_handler(event, context)

    handler_module.build_persistence_dependencies.assert_called_once_with()
    fake_trade_persistence_handler.assert_called_once_with(
        event,
        context,
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
        bucket_name="test-results-bucket",
    )

    assert response == expected_response


def test_build_persistence_dependencies_requires_results_bucket_env(monkeypatch):
    monkeypatch.delenv(
        handler_module.TRADE_RESULTS_BUCKET_ENV_VAR,
        raising=False,
    )
    monkeypatch.setenv(
        handler_module.TRADE_STATUS_TABLE_ENV_VAR,
        "trade-status-table",
    )

    with pytest.raises(
        ValueError,
        match="Missing environment variable: TRADE_RESULTS_BUCKET",
    ):
        handler_module.build_persistence_dependencies()


def test_build_persistence_dependencies_requires_status_table_env(monkeypatch):
    monkeypatch.delenv(
        handler_module.TRADE_STATUS_TABLE_ENV_VAR,
        raising=False,
    )
    monkeypatch.setenv(
        handler_module.TRADE_RESULTS_BUCKET_ENV_VAR,
        "test-results-bucket",
    )

    with pytest.raises(
        ValueError,
        match="Missing environment variable: TRADE_STATUS_TABLE_NAME",
    ):
        handler_module.build_persistence_dependencies()
