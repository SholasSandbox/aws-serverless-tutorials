import json
import pytest

import trade_handler
from trade_handler import (
    lambda_handler,
    find_missing_required_field,
    validate_volume_mwh,
    parse_json_body,
    internal_error_response,
    get_request_id,
)

from eventbridge_trade_handler import eventbridge_trade_handler

REQUIRED_FIELDS = ["trade_id", "product", "volume_mwh"]

ERROR_INVALID_JSON_BODY = "Invalid or missing JSON body"
ERROR_INTERNAL_SERVER = "Internal server error"
ERROR_VOLUME_MWH_NOT_NUMBER = "volume_mwh must be a number"
ERROR_VOLUME_MWH_NOT_POSITIVE = "volume_mwh must be greater than 0"
UNKNOWN_REQUEST_ID = "unknown-request-id"
STATUS_RECEIVED = "received"

TEST_API_REQUEST_ID = "api-request-123"
TEST_LAMBDA_REQUEST_ID = "lambda-request-456"
TEST_TRADE_ID = "TRD-1001"
TEST_PRODUCT = "UK Power"
TEST_VOLUME_MWH = 250


class FakeContext:
    aws_request_id = TEST_LAMBDA_REQUEST_ID


def test_success_response_does_not_mutate_input_body():
    body = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
        "status": STATUS_RECEIVED,
    }

    response = trade_handler.success_response(body, TEST_API_REQUEST_ID)
    response_body = json.loads(response["body"])
    assert response_body["request_id"] == TEST_API_REQUEST_ID
    assert "request_id" not in body


def test_get_request_id_returns_api_gateway_request_id():
    event = {"requestContext": {"requestId": TEST_API_REQUEST_ID}}

    request_id = get_request_id(event, None)
    assert request_id == TEST_API_REQUEST_ID


def test_get_request_id_returns_lambda_context_request_id_when_api_id_missing():
    event = {}
    context = FakeContext()
    request_id = get_request_id(event, context)

    assert request_id == TEST_LAMBDA_REQUEST_ID


def test_get_request_id_returns_unknown_when_no_request_id_available():
    event = {}
    request_id = get_request_id(event, None)

    assert request_id == UNKNOWN_REQUEST_ID


@pytest.mark.parametrize(
    "event",
    [
        {},  # missing body
        {"body": 123},  # body is not a string
        {"body": "{bad json"},  # invalid JSON
        {"body": json.dumps(["bad"])},  # valid JSON, but not a dict
        {"body": json.dumps(None)},  # valid JSON, but not a dict
    ],
)
def test_parse_json_body_returns_none_for_invalid_body(event):
    parsed_body = parse_json_body(event)

    assert parsed_body is None


def test_parse_json_body_returns_dict_for_valid_json_body():
    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            }
        )
    }

    parsed_body = parse_json_body(event)

    assert parsed_body == {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }


@pytest.mark.parametrize(
    "volume_mwh, expected_error",
    [
        (True, ERROR_VOLUME_MWH_NOT_NUMBER),
        ("100", ERROR_VOLUME_MWH_NOT_NUMBER),
        (-10, ERROR_VOLUME_MWH_NOT_POSITIVE),
        (0, ERROR_VOLUME_MWH_NOT_POSITIVE),
    ],
)
def test_validate_volume_mwh_rejects_invalid_values(volume_mwh, expected_error):
    volume_mwh_error = validate_volume_mwh(volume_mwh)

    assert volume_mwh_error == expected_error


@pytest.mark.parametrize(
    "volume_mwh",
    [
        10,
        10.01,
    ],
)
def test_validate_volume_mwh_accepts_valid_values(volume_mwh):
    volume_mwh_error = validate_volume_mwh(volume_mwh)

    assert volume_mwh_error is None


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
def test_find_missing_required_field_returns_missing_field(
    trade, expected_missing_field
):
    missing_field = find_missing_required_field(trade, REQUIRED_FIELDS)

    assert missing_field == expected_missing_field


def test_find_missing_required_field_returns_none_when_valid():
    trade = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }
    missing_field = find_missing_required_field(trade, REQUIRED_FIELDS)
    assert missing_field is None


@pytest.mark.parametrize(
    "event",
    [
        {},  # missing body
        {"body": 123},  # body is not a string
        {"body": "{bad json"},  # invalid JSON
        {"body": json.dumps(["bad"])},  # valid JSON, but not a dict
        {"body": json.dumps(None)},  # valid JSON, but not a dict
    ],
)
def test_lambda_handler_returns_400_for_invalid_json_body(event):
    response = lambda_handler(event, None)

    response_body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert response_body["error"] == ERROR_INVALID_JSON_BODY


@pytest.mark.parametrize(
    "event",
    [
        {
            "body": json.dumps(
                {
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": TEST_VOLUME_MWH,
                }
            ),
            "requestContext": {"requestId": ""},
        },
        {
            "body": json.dumps(
                {
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": TEST_VOLUME_MWH,
                }
            )
        },
        {
            "body": json.dumps(
                {
                    "trade_id": TEST_TRADE_ID,
                    "product": TEST_PRODUCT,
                    "volume_mwh": TEST_VOLUME_MWH,
                }
            ),
            "requestContext": {"requestId": None},
        },
    ],
)
def test_lambda_handler_uses_unknown_request_id_when_request_id_missing_or_invalid(
    event,
):
    response = lambda_handler(event, None)

    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["trade_id"] == TEST_TRADE_ID
    assert body["product"] == TEST_PRODUCT
    assert body["volume_mwh"] == TEST_VOLUME_MWH
    assert body["status"] == STATUS_RECEIVED
    assert body["request_id"] == UNKNOWN_REQUEST_ID


class FakeLambdaContext:
    aws_request_id = "lambda-req-123"


def test_lambda_handler_uses_lambda_context_request_id_when_api_gateway_request_id_missing():
    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            }
        )
    }

    response = lambda_handler(event, FakeLambdaContext())
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["request_id"] == "lambda-req-123"


def test_lambda_handler_uses_api_gateway_request_id_when_available():
    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            }
        ),
        "requestContext": {"requestId": "api-req-123"},
    }

    response = lambda_handler(event, None)
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["request_id"] == "api-req-123"


def test_valid_event():
    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            }
        ),
        "requestContext": {"requestId": TEST_API_REQUEST_ID},
    }
    response = lambda_handler(event, None)
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["request_id"] == TEST_API_REQUEST_ID
    assert body["trade_id"] == TEST_TRADE_ID
    assert body["product"] == TEST_PRODUCT
    assert body["volume_mwh"] == TEST_VOLUME_MWH
    assert body["status"] == STATUS_RECEIVED


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
def test_lambda_handler_returns_400_for_missing_required_fields(trade, expected_error):
    event = {
        "body": json.dumps(trade),
        "requestContext": {"requestId": TEST_API_REQUEST_ID},
    }

    response = lambda_handler(event, None)
    response_body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert response_body["request_id"] == TEST_API_REQUEST_ID
    assert response_body["error"] == expected_error


@pytest.mark.parametrize(
    "volume_mwh, expected_error",
    [
        (0, ERROR_VOLUME_MWH_NOT_POSITIVE),
        (-10, ERROR_VOLUME_MWH_NOT_POSITIVE),
        ("250", ERROR_VOLUME_MWH_NOT_NUMBER),
        (True, ERROR_VOLUME_MWH_NOT_NUMBER),
    ],
)
def test_lambda_handler_returns_400_for_invalid_volume_mwh(volume_mwh, expected_error):
    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": volume_mwh,
            }
        ),
        "requestContext": {"requestId": TEST_API_REQUEST_ID},
    }

    response = lambda_handler(event, None)
    response_body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert response_body["request_id"] == TEST_API_REQUEST_ID
    assert response_body["error"] == expected_error


def test_internal_error_response_returns_500():
    request_id = TEST_API_REQUEST_ID
    response = internal_error_response(request_id)
    response_body = json.loads(response["body"])

    assert response["statusCode"] == 500
    assert response_body["request_id"] == TEST_API_REQUEST_ID
    assert response_body["error"] == ERROR_INTERNAL_SERVER


def test_lambda_handler_returns_500_when_internal_helper_fails(monkeypatch):
    def broken_parse_json_body(event):
        raise RuntimeError("simulated parser failure")

    monkeypatch.setattr(trade_handler, "parse_json_body", broken_parse_json_body)

    event = {
        "body": json.dumps(
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            }
        ),
        "requestContext": {"requestId": TEST_API_REQUEST_ID},
    }

    response = lambda_handler(event, None)
    response_body = json.loads(response["body"])

    assert response["statusCode"] == 500
    assert response_body["request_id"] == TEST_API_REQUEST_ID
    assert response_body["error"] == ERROR_INTERNAL_SERVER


def test_eventbridge_trade_handler_valid_trade_returns_received():
    event = {
        "id": "evt-12345",
        "detail": {"trade_id": "TRD-1001", "product": "UK Power", "volume_mwh": 250},
    }

    response = eventbridge_trade_handler(event, None)

    assert response["status"] == STATUS_RECEIVED
    assert response["request_id"] == "evt-12345"
    assert response["trade"]["trade_id"] == "TRD-1001"


def test_eventbridge_trade_handler_missing_detail_returns_rejected():
    event = {"id": "evt-12345"}

    response = eventbridge_trade_handler(event, None)

    assert response["status"] == "rejected"
    assert response["request_id"] == "evt-12345"
    assert response["error"] == "Missing or invalid event detail"


def test_eventbridge_trade_handler_missing_required_field_returns_rejected():
    event = {"id": "evt-12345", "detail": {"product": "UK Power", "volume_mwh": 250}}

    response = eventbridge_trade_handler(event, None)

    assert response["status"] == "rejected"
    assert "trade_id" in response["error"]
