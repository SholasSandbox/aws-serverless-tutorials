import os
import boto3

from typing import Any

from trade_status_persistence import find_missing_required_field

from trade_persistence_workflow import persist_trade_processing_result

TRADE_STATUS_TABLE_ENV_VAR = "TRADE_STATUS_TABLE_NAME"

def trade_persistence_handler(
    event: dict[str, Any],
    context: Any,
    *,
    s3_client: Any,
    dynamodb_table: Any,
) -> dict[str, Any]:
    missing_event_field = find_missing_required_field(
        event,
        [
            "trade",
            "validation",
            "processed_at",
            "bucket_name",
        ],
    )
    if missing_event_field is not None:
        raise ValueError(f"Missing event field: {missing_event_field}")
    
    result = persist_trade_processing_result(
        trade=event["trade"],
        validation=event["validation"],
        processed_at=event["processed_at"],
        bucket_name=event["bucket_name"],
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
    )

    return result

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    table_name = os.environ[TRADE_STATUS_TABLE_ENV_VAR]

    s3_client = boto3.client("s3")
    dynamodb_table = boto3.resource("dynamodb").Table(table_name)

    return trade_persistence_handler(
        event,
        context,
        s3_client=s3_client,
        dynamodb_table=dynamodb_table,
    )