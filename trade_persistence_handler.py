import os
from typing import Any

import boto3

from trade_status_persistence import find_missing_required_field
from trade_persistence_workflow import persist_trade_processing_result

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


def trade_persistence_handler(
    event: dict[str, Any],
    context: Any,
    *,
    s3_client: Any,
    dynamodb_table: Any,
    bucket_name: str,
) -> dict[str, Any]:
    missing_event_field = find_missing_required_field(
        event,
        [
            "trade",
            "validation",
            "processed_at",
        ],
    )

    if missing_event_field is not None:
        raise ValueError(f"Missing event field: {missing_event_field}")

    return persist_trade_processing_result(
        trade=event["trade"],
        validation=event["validation"],
        processed_at=event["processed_at"],
        bucket_name=bucket_name,
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    dependencies = build_persistence_dependencies()

    return trade_persistence_handler(
        event,
        context,
        s3_client=dependencies["s3_client"],
        dynamodb_table=dependencies["dynamodb_table"],
        bucket_name=dependencies["bucket_name"],
    )