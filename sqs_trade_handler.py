import json
import logging
from typing import Any

from trade_handler import (
    REQUIRED_FIELDS,
    UNKNOWN_REQUEST_ID,
    find_missing_required_field,
    validate_volume_mwh,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ERROR_MISSING_REQUIRED_FIELD = "Missing required field"
ERROR_INVALID_VOLUME_MWH = "Invalid volume_mwh"

ERROR_INVALID_JSON_BODY = "Invalid or missing JSON body"
ERROR_JSON_BODY_NOT_OBJECT = "JSON body is not an object"

LOG_INVALID_JSON_BODY = f"{ERROR_INVALID_JSON_BODY} message_id=%s"
LOG_JSON_BODY_NOT_OBJECT = f"{ERROR_JSON_BODY_NOT_OBJECT} message_id=%s"

LOG_ACCEPTANCE_MESSAGE = "Processed trade message_id=%s trade_id=%s"


def persist_trade(trade: dict[str, Any]) -> None:
    return None


def batch_item_failure(message_id: str) -> dict[str, str]:
    return {"itemIdentifier": message_id}


def record_rejection(message_id: str, error: str, raw_body: Any) -> None:
    logger.warning(
        "Rejected SQS message message_id=%s error=%s raw_body=%s",
        message_id,
        error,
        raw_body,
    )


def record_accepted(message_id: str, trade: dict[str, Any]) -> None:
    logger.info(
        LOG_ACCEPTANCE_MESSAGE,
        message_id,
        trade.get("trade_id"),
    )

def sqs_trade_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    records = event.get("Records") or []

    batch_item_failures: list[dict[str, str]] = []

    for record in records:
        message_id = record.get("messageId") or UNKNOWN_REQUEST_ID
        body = record.get("body")

        try:
            trade = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            record_rejection(message_id, ERROR_INVALID_JSON_BODY, body)
            continue

        if not isinstance(trade, dict):
            record_rejection(message_id, ERROR_JSON_BODY_NOT_OBJECT, body)
            continue

        missing_field = find_missing_required_field(trade, REQUIRED_FIELDS)
        if missing_field is not None:
            record_rejection(message_id, f"{ERROR_MISSING_REQUIRED_FIELD}: {missing_field}", body)
            continue

        volume_mwh_error = validate_volume_mwh(trade["volume_mwh"])
        if volume_mwh_error is not None:
            record_rejection(message_id, volume_mwh_error, body)
            continue
        
        try:
            persist_trade(trade) 
        except Exception:
            logger.exception("Failed to persist trade message_id=%s", message_id)
            batch_item_failures.append(batch_item_failure(message_id))
            continue
        
        record_accepted(message_id, trade)

    return {"batchItemFailures": batch_item_failures}
