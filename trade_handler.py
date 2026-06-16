import json
import logging
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REQUIRED_FIELDS = ["trade_id", "product", "volume_mwh"]

ERROR_INVALID_JSON_BODY = "Invalid or missing JSON body"
ERROR_INTERNAL_SERVER = "Internal server error"
ERROR_VOLUME_MWH_NOT_NUMBER = "volume_mwh must be a number"
ERROR_VOLUME_MWH_NOT_POSITIVE = "volume_mwh must be greater than 0"

UNKNOWN_REQUEST_ID = "unknown-request-id"
STATUS_RECEIVED = "received"


def parse_json_body(event: dict[str, Any]) -> dict[str, Any] | None:
    body = event.get("body")

    if body is None:
        return None

    if not isinstance(body, str):
        return None

    try:
        parsed_body = json.loads(body)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed_body, dict):
        return None

    return parsed_body


def find_missing_required_field(body: dict[str, Any], required_fields: list[str]) -> str | None:
    for field in required_fields:
        if field not in body:
            return field

    return None


def validate_volume_mwh(volume_mwh: Any) -> str | None:
    if isinstance(volume_mwh, bool):
        return ERROR_VOLUME_MWH_NOT_NUMBER
    elif not isinstance(volume_mwh, (int, float)):
        return ERROR_VOLUME_MWH_NOT_NUMBER
    elif volume_mwh <= 0:
        return ERROR_VOLUME_MWH_NOT_POSITIVE
    else:
        return None


def internal_error_response(request_id: str | None = None) -> dict[str, Any]:
    response_body = {"error": ERROR_INTERNAL_SERVER}
    if request_id is not None:
        response_body["request_id"] = request_id
    return {
        "statusCode": 500,
        "body": json.dumps(response_body),
    }


def error_response(message: str, request_id: str | None = None) -> dict[str, Any]:
    response_body = {"error": message}
    if request_id is not None:
        response_body["request_id"] = request_id

    return {
        "statusCode": 400,
        "body": json.dumps(response_body),
    }


def success_response(body: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    response_body = body.copy()
    if request_id is not None:
        response_body["request_id"] = request_id
    return {
        "statusCode": 200,
        "body": json.dumps(response_body),
    }


def get_request_id(event: dict[str, Any], context: Any) -> str:
    request_context = event.get("requestContext")

    if isinstance(request_context, dict):
        api_request_id = request_context.get("requestId")

        if isinstance(api_request_id, str) and api_request_id:
            return api_request_id

    lambda_request_id = getattr(context, "aws_request_id", None)

    if isinstance(lambda_request_id, str) and lambda_request_id:
        return lambda_request_id

    return UNKNOWN_REQUEST_ID


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = None

    try:
        request_id = get_request_id(event, context)

        logger.info("Received trade request request_id=%s", request_id)
        request_body = parse_json_body(event)

        if request_body is None:
            logger.warning("Invalid or missing JSON body request_id=%s", request_id)
            return error_response(ERROR_INVALID_JSON_BODY, request_id)

        missing_field = find_missing_required_field(request_body, REQUIRED_FIELDS)

        if missing_field is not None:
            logger.warning("Missing required field: %s request_id=%s", missing_field, request_id)
            return error_response(f"Missing required field: {missing_field}", request_id)

        volume_mwh = request_body["volume_mwh"]

        volume_mwh_error = validate_volume_mwh(volume_mwh)
        if volume_mwh_error is not None:
            logger.warning("Invalid volume_mwh: %s request_id=%s", volume_mwh_error, request_id)
            return error_response(volume_mwh_error, request_id)

        response_body = {
            "trade_id": request_body["trade_id"],
            "product": request_body["product"],
            "volume_mwh": volume_mwh,
            "status": STATUS_RECEIVED,
        }

        logger.info(
            "Trade request accepted request_id=%s trade_id=%s",
            request_id,
            request_body["trade_id"],
        )

        return success_response(response_body, request_id)
    except Exception:
        logger.exception(
            "Unexpected error while processing trade request request_id=%s",
            request_id,
        )

        return internal_error_response(request_id)
