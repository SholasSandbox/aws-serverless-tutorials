import os
import logging

from typing import Any

import boto3

from trade_status_persistence import find_missing_required_field
from trade_persistence_workflow import persist_trade_processing_result

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TRADE_RESULTS_BUCKET_ENV_VAR = "TRADE_RESULTS_BUCKET"
TRADE_STATUS_TABLE_ENV_VAR = "TRADE_STATUS_TABLE_NAME"


def build_persistence_dependencies() -> dict[str, Any]:
    bucket_name = os.environ.get(TRADE_RESULTS_BUCKET_ENV_VAR)
    table_name = os.environ.get(TRADE_STATUS_TABLE_ENV_VAR)

    if bucket_name is None:
        raise ValueError("Missing environment variable: TRADE_RESULTS_BUCKET")

    if table_name is None:
        raise ValueError("Missing environment variable: TRADE_STATUS_TABLE_NAME")

    return {
        "s3_client": boto3.client("s3"),
        "dynamodb_table": boto3.resource("dynamodb").Table(table_name),
        "bucket_name": bucket_name,
    }


def require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")

    return value


def require_number(value: Any, field_name: str) -> int | float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")

    return value


def extract_persistence_event_parts(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("event must be a dict")

    required_event_fields = ["trade", "validation", "processed_at"]

    missing_event_field = find_missing_required_field(event, required_event_fields)

    if missing_event_field is not None:
        raise ValueError(f"Missing event field: {missing_event_field}")

    trade = event["trade"]
    if not isinstance(trade, dict):
        raise ValueError("event field 'trade' must be a dict")

    validation = event["validation"]
    if not isinstance(validation, dict):
        raise ValueError("event field 'validation' must be a dict")

    processed_at = require_non_empty_string(
        event["processed_at"],
        "event processed_at",
    )

    required_trade_fields = ["trade_id", "product", "volume_mwh"]
    missing_trade_field = find_missing_required_field(trade, required_trade_fields)
    if missing_trade_field is not None:
        raise ValueError(f"Missing trade field: {missing_trade_field}")

    require_non_empty_string(
        trade["trade_id"],
        "trade trade_id",
    )

    require_non_empty_string(
        trade["product"],
        "trade product",
    )

    require_number(
        trade["volume_mwh"],
        "trade volume_mwh",
    )

    required_validation_fields = ["is_valid", "errors"]
    missing_validation_field = find_missing_required_field(
        validation,
        required_validation_fields,
    )
    if missing_validation_field is not None:
        raise ValueError(f"Missing validation field: {missing_validation_field}")

    is_valid = validation["is_valid"]
    if not isinstance(is_valid, bool):
        raise ValueError("validation is_valid must be a boolean")

    errors = validation["errors"]
    if not isinstance(errors, list):
        raise ValueError("validation errors must be a list")

    return {
        "trade": trade,
        "validation": validation,
        "processed_at": processed_at,
    }


def trade_persistence_handler(
    event: dict[str, Any],
    context: Any,
    *,
    s3_client: Any,
    dynamodb_table: Any,
    bucket_name: str,
) -> dict[str, Any]:
    validated_event = extract_persistence_event_parts(event)

    try:
        return persist_trade_processing_result(
            trade=validated_event["trade"],
            validation=validated_event["validation"],
            processed_at=validated_event["processed_at"],
            bucket_name=bucket_name,
            s3_client=s3_client,
            dynamodb_table=dynamodb_table,
        )
    except Exception:
        logger.exception(
            "Unexpected persistence handler error trade_id=%s",
            validated_event["trade"]["trade_id"],
        )
        raise


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    dependencies = build_persistence_dependencies()

    return trade_persistence_handler(
        event,
        context,
        s3_client=dependencies["s3_client"],
        dynamodb_table=dependencies["dynamodb_table"],
        bucket_name=dependencies["bucket_name"],
    )
