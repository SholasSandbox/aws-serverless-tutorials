import pytest
from unittest.mock import Mock

import trade_persistence_handler as handler_module


@pytest.mark.parametrize(
    "event",
    [
        None,
        123,
        "bad event",
        ["bad"],
    ],
)
def test_extract_persistence_event_parts_rejects_non_dict_event(event):
    with pytest.raises(ValueError, match="event must be a dict"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": None,
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": 123,
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": "not a dict",
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": ["bad"],
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_trade_that_is_not_dict(event):
    with pytest.raises(ValueError, match="event field 'trade' must be a dict"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": None,
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": 123,
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": "bad validation field",
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": ["bad validation field"],
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_validation_that_is_not_dict(event):
    with pytest.raises(ValueError, match="event field 'validation' must be a dict"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": None,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": ["True"],
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": 123,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": "True",
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_non_boolean_validation_is_valid(event):
    with pytest.raises(ValueError, match="validation is_valid must be a boolean"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": True,
                "errors": 123,
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": True,
                "errors": "not a list",
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": True,
                "errors": "[]",
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
            "validation": {
                "is_valid": True,
                "errors": {},
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_validation_errors_is_not_list(event):
    with pytest.raises(ValueError, match="validation errors must be a list"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": None},
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": "False"},
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": [-100]},
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": "100"},
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_non_numeric_trade_volume_mwh(event):
    with pytest.raises(ValueError, match="trade volume_mwh must be a number"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_rejects_missing_trade_id():
    event = {
        "trade": {
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    with pytest.raises(ValueError, match="Missing trade field: trade_id"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {
                "trade_id": "",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {
                "trade_id": "  ",
                "product": "POWER",
                "volume_mwh": 100,
            },
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_empty_trade_id(event):

    with pytest.raises(ValueError, match="trade_id must be a non-empty string"):
        handler_module.extract_persistence_event_parts(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": " ",
                "volume_mwh": 100,
            },
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
        {
            "trade": {
                "trade_id": "TRD-001",
                "product": "",
                "volume_mwh": 100,
            },
            "validation": {
                "is_valid": True,
                "errors": [],
            },
            "processed_at": "2026-06-02T18:30:00Z",
        },
    ],
)
def test_extract_persistence_event_parts_rejects_empty_trade_product(event):

    with pytest.raises(ValueError, match="product must be a non-empty string"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_rejects_missing_trade_product():
    event = {
        "trade": {
            "trade_id": "TRD-001",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    with pytest.raises(ValueError, match="Missing trade field: product"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_rejects_missing_volume_mwh():
    event = {
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    with pytest.raises(ValueError, match="Missing trade field: volume_mwh"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_rejects_missing_validation_is_valid():
    event = {
        "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
        "validation": {
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    with pytest.raises(ValueError, match="Missing validation field: is_valid"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_rejects_missing_validation_errors():
    event = {
        "trade": {"trade_id": "TRD-001", "product": "POWER", "volume_mwh": 100},
        "validation": {
            "is_valid": True,
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }

    with pytest.raises(ValueError, match="Missing validation field: errors"):
        handler_module.extract_persistence_event_parts(event)


def test_extract_persistence_event_parts_returns_expected_parts():
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

    result = handler_module.extract_persistence_event_parts(event)

    assert result == {
        "trade": event["trade"],
        "validation": event["validation"],
        "processed_at": event["processed_at"],
    }


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
        "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json"
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
        "trade-results/rejected/year=2026/month=06/day=02/trade_id=TRD-001.json"
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
            "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json"
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


def test_trade_persistence_handler_logs_and_reraises_unexpected_s3_put_failure(caplog):
    s3_client = Mock()
    dynamodb_table = Mock()

    s3_client.put_object.side_effect = RuntimeError("S3 put failed")

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

    with caplog.at_level("ERROR", logger=handler_module.logger.name):
        with pytest.raises(RuntimeError, match="S3 put failed"):
            handler_module.trade_persistence_handler(
                event,
                None,
                s3_client=s3_client,
                dynamodb_table=dynamodb_table,
                bucket_name="test-results-bucket",
            )

    assert "Unexpected persistence handler error trade_id=TRD-001" in caplog.text

    s3_client.put_object.assert_called_once()
    dynamodb_table.put_item.assert_not_called()


def test_trade_persistence_handler_logs_and_reraises_unexpected_dynamodb_put_failure(
    caplog,
):
    s3_client = Mock()
    dynamodb_table = Mock()

    dynamodb_table.put_item.side_effect = RuntimeError("dynamodb put failed")

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

    with caplog.at_level("ERROR", logger=handler_module.logger.name):
        with pytest.raises(RuntimeError, match="dynamodb put failed"):
            handler_module.trade_persistence_handler(
                event,
                None,
                s3_client=s3_client,
                dynamodb_table=dynamodb_table,
                bucket_name="test-results-bucket",
            )

    assert "Unexpected persistence handler error trade_id=TRD-001" in caplog.text

    s3_client.put_object.assert_called_once()
    dynamodb_table.put_item.assert_called_once()
