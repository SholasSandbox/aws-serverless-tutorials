from typing import Any

from trade_result_persistence import (
    ARTIFACT_TYPE_ACCEPTED,
    ARTIFACT_TYPE_REJECTED,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
)

RESULT_TYPE_ACCEPTED = "accepted"
RESULT_TYPE_REJECTED = "rejected"


def build_trade_status_record(
    *,
    trade_id: str,
    status: str,
    result_type: str,
    processed_at: str,
    s3_bucket: str,
    s3_key: str,
    rejection_summary: str | None,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "processed_at": processed_at,
        "status": status,
        "result_type": result_type,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "rejection_summary": rejection_summary,
        "schema_version": schema_version,
    }


def persist_trade_status_record(
    *,
    dynamodb_table: Any,
    status_record: dict[str, Any],
    conditional_check_failed_exception: type[Exception]
    | tuple[type[Exception], ...] = (),
) -> dict[str, Any]:
    try:
        dynamodb_table.put_item(
            Item=status_record,
            ConditionExpression="attribute_not_exists(trade_id)",
        )

    except conditional_check_failed_exception:
        return {
            "trade_id": status_record["trade_id"],
            "result_type": status_record["result_type"],
            "status": "already_persisted",
        }

    return {
        "trade_id": status_record["trade_id"],
        "processed_at": status_record["processed_at"],
        "status": status_record["status"],
    }


def find_missing_required_field(
    payload: dict[str, Any],
    required_fields: list[str],
) -> str | None:
    for field in required_fields:
        if field not in payload:
            return field

    return None


def get_result_type_from_artifact_type(artifact_type: str) -> str:
    if artifact_type == ARTIFACT_TYPE_ACCEPTED:
        return RESULT_TYPE_ACCEPTED

    if artifact_type == ARTIFACT_TYPE_REJECTED:
        return RESULT_TYPE_REJECTED

    raise ValueError(f"Unsupported artifact_type: {artifact_type}")


def get_artifact_is_valid(artifact: dict[str, Any]) -> bool:
    validation = artifact.get("validation")

    if not isinstance(validation, dict):
        raise ValueError("artifact validation must be an object")

    if "is_valid" not in validation:
        raise ValueError("artifact validation is missing is_valid")

    is_valid = validation["is_valid"]

    if not isinstance(is_valid, bool):
        raise ValueError("artifact validation is_valid must be a boolean")

    return is_valid


def validate_artifact_consistency(
    *,
    result_type: str,
    status: str,
    is_valid: bool,
) -> None:
    if result_type == RESULT_TYPE_ACCEPTED and status != STATUS_ACCEPTED:
        raise ValueError("accepted artifact must have status ACCEPTED")

    if result_type == RESULT_TYPE_REJECTED and status != STATUS_REJECTED:
        raise ValueError("rejected artifact must have status REJECTED")

    if result_type == RESULT_TYPE_ACCEPTED and not is_valid:
        raise ValueError("accepted artifact must have validation is_valid true")

    if result_type == RESULT_TYPE_REJECTED and is_valid:
        raise ValueError("rejected artifact must have validation is_valid false")


def build_trade_status_record_from_artifact(
    *,
    artifact: dict[str, Any],
    s3_pointer: dict[str, str],
) -> dict[str, Any]:
    missing_artifact_field = find_missing_required_field(
        artifact,
        [
            "artifact_type",
            "schema_version",
            "trade_id",
            "processed_at",
            "status",
            "validation",
        ],
    )

    if missing_artifact_field is not None:
        raise ValueError(f"Missing artifact field: {missing_artifact_field}")

    result_type = get_result_type_from_artifact_type(artifact["artifact_type"])
    is_valid = get_artifact_is_valid(artifact)

    validate_artifact_consistency(
        result_type=result_type,
        status=artifact["status"],
        is_valid=is_valid,
    )

    if result_type == RESULT_TYPE_ACCEPTED:
        rejection_summary = None
    else:
        rejection_reasons = artifact.get("rejection_reasons", [])
        rejection_summary = rejection_reasons[0] if rejection_reasons else None

    missing_s3_field = find_missing_required_field(
        s3_pointer,
        ["bucket", "key"],
    )

    if missing_s3_field is not None:
        raise ValueError(f"Missing S3 pointer field: {missing_s3_field}")

    return build_trade_status_record(
        trade_id=artifact["trade_id"],
        processed_at=artifact["processed_at"],
        result_type=result_type,
        status=artifact["status"],
        s3_bucket=s3_pointer["bucket"],
        s3_key=s3_pointer["key"],
        rejection_summary=rejection_summary,
        schema_version=artifact["schema_version"],
    )
