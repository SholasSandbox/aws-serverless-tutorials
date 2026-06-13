from typing import Any

from trade_result_persistence import (
    build_accepted_trade_artifact,
    build_rejected_trade_artifact,
    build_s3_key,
    put_json_object_to_s3,
)

from trade_status_persistence import (
    RESULT_TYPE_ACCEPTED,
    RESULT_TYPE_REJECTED,
    build_trade_status_record_from_artifact,
    put_trade_status_record,
)


def persist_trade_processing_result(
    *,
    trade: dict[str, Any],
    validation: dict[str, Any],
    processed_at: str,
    s3_client: Any,
    dynamodb_table: Any,
    bucket_name: str,
) -> dict[str, Any]:
    if "is_valid" not in validation:
        raise ValueError("validation is missing is_valid")

    is_valid = validation["is_valid"]

    if not isinstance(is_valid, bool):
        raise ValueError("validation is_valid must be a boolean")

    if is_valid:
        result_type = RESULT_TYPE_ACCEPTED
        artifact = build_accepted_trade_artifact(
            trade=trade,
            validation=validation,
            processed_at=processed_at,
        )
    else:
        result_type = RESULT_TYPE_REJECTED
        artifact = build_rejected_trade_artifact(
            trade=trade,
            validation=validation,
            processed_at=processed_at,
        )

    s3_key = build_s3_key(
        result_type=result_type,
        trade_id=artifact["trade_id"],
        processed_at=processed_at,
    )

    put_json_object_to_s3(
        s3_client=s3_client,
        bucket_name=bucket_name,
        object_key=s3_key,
        body=artifact,
    )

    s3_pointer = {
        "bucket": bucket_name,
        "key": s3_key,
    }

    status_record = build_trade_status_record_from_artifact(
        artifact=artifact,
        s3_pointer=s3_pointer,
    )

    put_trade_status_record(
        dynamodb_table=dynamodb_table,
        status_record=status_record,
    )

    return {
        "trade_id": status_record["trade_id"],
        "status": status_record["status"],
        "result_type": status_record["result_type"],
        "s3_bucket": status_record["s3_bucket"],
        "s3_key": status_record["s3_key"],
    }