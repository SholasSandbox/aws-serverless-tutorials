import json
import logging
import pytest

import sqs_trade_handler as sqs_module
from sqs_trade_handler import (
    sqs_trade_handler,
    ERROR_JSON_BODY_NOT_OBJECT,
    ERROR_INVALID_JSON_BODY,
    ERROR_MISSING_REQUIRED_FIELD,
)

from trade_handler import (
    find_missing_required_field,
    validate_volume_mwh,
    REQUIRED_FIELDS,
    ERROR_VOLUME_MWH_NOT_NUMBER,
    ERROR_VOLUME_MWH_NOT_POSITIVE,
)

TEST_SQS_MESSAGE_ID = "sqs-message-id-456"
MESSAGE_VALID = "msg-valid"
MESSAGE_INVALID = "msg-invalid"
TEST_TRADE_ID = "TRD-1001"
TEST_PRODUCT = "UK Power"
TEST_VOLUME_MWH = 250


def assert_no_batch_failures(response):
    assert response == {"batchItemFailures": []}


def test_sqs_trade_handler_returns_no_batch_failures_for_valid_record():
    event = {
        "Records": [
            {
                "messageId": "msg-001",
                "body": json.dumps({
                    "trade_id": "TRD-1001",
                    "product": "UK Power",
                    "volume_mwh": 250,
                }),
            }
        ]
    }

    response = sqs_trade_handler(event, None)

    assert_no_batch_failures(response)


def test_sqs_trade_handler_records_non_retryable_missing_volume_mwh(caplog):
    test_message_id = "msg-001"
    event = {
        "Records": [
            {
                "messageId": test_message_id,
                "body": json.dumps({
                    "trade_id": "TRD-1001",
                    "product": "UK Power",
                }),
            }
        ]
    }

    response = sqs_trade_handler(event, None)

    assert test_message_id in caplog.text
    assert_no_batch_failures(response)
    assert f"{ERROR_MISSING_REQUIRED_FIELD}: volume_mwh" in caplog.text
    assert_no_batch_failures(response)    


@pytest.mark.parametrize(
    "trade, expected_missing_field",
    [
        (
            {
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "trade_id",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "product",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
            },
            "volume_mwh",
        ),
    ],
)
def test_sqs_find_missing_required_field_returns_missing_field(trade, expected_missing_field):  
    missing_field = find_missing_required_field(trade, REQUIRED_FIELDS)

    assert missing_field == expected_missing_field

def test_sqs_find_missing_required_field_returns_none_when_valid():
    trade = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH
    }
    missing_field = find_missing_required_field(trade, REQUIRED_FIELDS)
    assert missing_field is None

@pytest.mark.parametrize(
    "volume_mwh, expected_error",
    [
        (True, ERROR_VOLUME_MWH_NOT_NUMBER),
        ("100", ERROR_VOLUME_MWH_NOT_NUMBER),
        (-10, ERROR_VOLUME_MWH_NOT_POSITIVE),
        (0, ERROR_VOLUME_MWH_NOT_POSITIVE),
    ]
)
def test_sqs_validate_volume_mwh_rejects_invalid_values(volume_mwh, expected_error):
    volume_mwh_error = validate_volume_mwh(volume_mwh)

    assert volume_mwh_error == expected_error

@pytest.mark.parametrize(
    "volume_mwh",
    [
        10,
        10.01,
    ]
)
def test_sqs_validate_volume_mwh_accepts_valid_values(volume_mwh):
    volume_mwh_error = validate_volume_mwh(volume_mwh)

    assert volume_mwh_error is None

@pytest.mark.parametrize(
    "trade, expected_error",
    [
        (
            {
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "Missing required field: trade_id",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "Missing required field: product",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
            },
            "Missing required field: volume_mwh",
        ),
    ],
)
def test_sqs_trade_handler_records_non_retryable_missing_required_fields(
    trade,
    expected_error,
    caplog,
):
    caplog.set_level(logging.WARNING)

    event = {
        "Records": [
            {
                "messageId": TEST_SQS_MESSAGE_ID,
                "body": json.dumps(trade),
            }
        ]
    }

    response = sqs_trade_handler(event, None)

    assert TEST_SQS_MESSAGE_ID in caplog.text
    assert expected_error in caplog.text
    assert_no_batch_failures(response)


@pytest.mark.parametrize(
    "volume_mwh, expected_error",
    [
        (True, ERROR_VOLUME_MWH_NOT_NUMBER),
        ("100", ERROR_VOLUME_MWH_NOT_NUMBER),
        (-10, ERROR_VOLUME_MWH_NOT_POSITIVE),
        (0, ERROR_VOLUME_MWH_NOT_POSITIVE),
    ],
)
def test_sqs_trade_handler_records_non_retryable_invalid_volume_mwh(volume_mwh, expected_error, caplog):
    caplog.set_level(logging.WARNING)

    event = {
        "Records": [
            {
                "messageId": TEST_SQS_MESSAGE_ID,
                "body": json.dumps({
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": volume_mwh,
                }),
            }
        ]
    }
    response = sqs_trade_handler(event, None)

    assert TEST_SQS_MESSAGE_ID in caplog.text
    assert expected_error in caplog.text
    assert_no_batch_failures(response)



@pytest.mark.parametrize(
    "record, expected_error",
    [
        (
            {"messageId": TEST_SQS_MESSAGE_ID},
            ERROR_INVALID_JSON_BODY,
        ),  # missing body

        (
            {"messageId": TEST_SQS_MESSAGE_ID, "body": 123},
            ERROR_INVALID_JSON_BODY,
        ),  # body is not a string

        (
            {"messageId": TEST_SQS_MESSAGE_ID, "body": "{bad json"},
            ERROR_INVALID_JSON_BODY,
        ),  # invalid JSON

        (
            {"messageId": TEST_SQS_MESSAGE_ID, "body": json.dumps(["bad"])},
            ERROR_JSON_BODY_NOT_OBJECT,
        ),  # valid JSON, but not a dict

        (
            {"messageId": TEST_SQS_MESSAGE_ID, "body": json.dumps(None)},
            ERROR_JSON_BODY_NOT_OBJECT,
        ),  # valid JSON, but not a dict
    ],
)
def test_sqs_trade_handler_records_non_retryable_invalid_json_body(record, expected_error, caplog):
    caplog.set_level(logging.WARNING)

    event = {
        "Records": [record]
    }

    response = sqs_trade_handler(event, None)

    assert expected_error in caplog.text
    assert TEST_SQS_MESSAGE_ID in caplog.text
    assert_no_batch_failures(response)

def test_sqs_trade_handler_handles_mixed_batch_with_non_retryable_invalid_record(caplog):
    caplog.set_level(logging.WARNING)

    event = {
        "Records": [
            {
                "messageId": MESSAGE_VALID,
                "body": json.dumps({
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": TEST_VOLUME_MWH,
                }),
            },
            {
                "messageId": MESSAGE_INVALID,
                "body": json.dumps({
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": 0,
                }),
            },
        ]
    }

    response = sqs_trade_handler(event, None)

    assert ERROR_VOLUME_MWH_NOT_POSITIVE in caplog.text
    assert "msg-invalid" in caplog.text
    assert_no_batch_failures(response)


def test_sqs_trade_handler_handles_trade_with_retryable_record(monkeypatch):
    def failing_persist_trade(trade):
        raise RuntimeError("S3 unavailable")
    
    monkeypatch.setattr(sqs_module, "persist_trade", failing_persist_trade)
       
    event = {
        "Records": [
            {
                "messageId": TEST_SQS_MESSAGE_ID,
                "body": json.dumps({
                    "trade_id": "TRD-1001",
                    "product": "UK Power",
                    "volume_mwh": 250,
                }),
            }
        ]
    }

    response = sqs_module.sqs_trade_handler(event, None)

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": TEST_SQS_MESSAGE_ID}
        ]
    }
  
def test_sqs_trade_handler_persists_valid_trade(monkeypatch):
    persisted_trades = []

    def fake_persist_trade(trade):
        persisted_trades.append(trade)

    monkeypatch.setattr(sqs_module, "persist_trade", fake_persist_trade)

    event = {
        "Records": [
            {
                "messageId": TEST_SQS_MESSAGE_ID,
                "body": json.dumps({
                    "trade_id": TEST_TRADE_ID,
                    "product": "UK Power",
                    "volume_mwh": 250,
                }),
            }
        ]
    }

    response = sqs_module.sqs_trade_handler(event, None)

    assert_no_batch_failures(response)
    assert len(persisted_trades) == 1
    assert persisted_trades[0]["trade_id"] == TEST_TRADE_ID