import logging
from typing import Any

from trade_handler import (
    UNKNOWN_REQUEST_ID,
    REQUIRED_FIELDS,
    STATUS_RECEIVED,
    find_missing_required_field,
    validate_volume_mwh,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def eventbridge_trade_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    event_id = event.get("id", UNKNOWN_REQUEST_ID)

    trade = event.get("detail")

    if not isinstance(trade, dict):
        logger.warning(
            "Invalid EventBridge event: missing or invalid detail",
            extra={"request_id": event_id}
        )
        return {
            "status": "rejected",
            "request_id": event_id,
            "error": "Missing or invalid event detail"
        }

    missing_field = find_missing_required_field(trade,REQUIRED_FIELDS)
    if missing_field is not None:
        logger.warning(
            "Invalid trade event: missing required field",
            extra={"request_id": event_id, "missing_field": missing_field}
        )
        return {
            "status": "rejected",
            "request_id": event_id,
            "error": f"Missing required field: {missing_field}"
        }

    volume_error = validate_volume_mwh(trade["volume_mwh"])
    if volume_error is not None:
        logger.warning(
            "Invalid trade event: volume_mwh validation failed",
            extra={"request_id": event_id}
        )
        return {
            "status": "rejected",
            "request_id": event_id,
            "error": volume_error
        }

    logger.info(
        "Trade event processed",
        extra={"request_id": event_id, "trade_id": trade.get("trade_id")}
    )

    return {
        "status": STATUS_RECEIVED,
        "request_id": event_id,
        "trade": trade.copy()
    }