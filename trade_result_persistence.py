import json
import re

from datetime import UTC, datetime
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_BASE_PREFIX = "trade-results"

STATUS_ACCEPTED = "ACCEPTED"
STATUS_REJECTED = "REJECTED"

ARTIFACT_TYPE_ACCEPTED = "accepted_trade"
ARTIFACT_TYPE_REJECTED = "rejected_trade"

VALID_RESULT_TYPES = {"accepted", "rejected"}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_trade_result_document(
    trade: dict[str, Any],
    status: str,
    reason: str | None,
    processed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "trade_id": trade.get("trade_id", "unknown-trade-id"),
        "status": status,
        "reason": reason,
        "received_trade": trade,
        "processed_at": processed_at or utc_now_iso(),
    }


def put_json_object_to_s3(
    s3_client: Any,
    bucket_name: str,
    object_key: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    json_body = json.dumps(body)

    return s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json_body,
        ContentType="application/json",
    )


def build_accepted_trade_artifact(
    trade: dict[str, Any],
    validation: dict[str, Any],
    processed_at: str,
) -> dict[str, Any]:
    trade_id = trade["trade_id"]

    return {
        "artifact_type": ARTIFACT_TYPE_ACCEPTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_ACCEPTED,
        "trade_id": trade_id,
        "processed_at": processed_at,
        "trade": trade,
        "validation": validation,
    }


def build_rejected_trade_artifact(
    trade: dict[str, Any],
    validation: dict[str, Any],
    processed_at: str,
) -> dict[str, Any]:
    trade_id = trade["trade_id"]
    rejection_reasons = validation.get("errors", [])

    return {
        "artifact_type": ARTIFACT_TYPE_REJECTED,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_REJECTED,
        "trade_id": trade_id,
        "processed_at": processed_at,
        "trade": trade,
        "validation": validation,
        "rejection_reasons": rejection_reasons,
    }


def safe_s3_key_part(value: Any) -> str:
    text = str(value or "unknown").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._=-]+", "-", text)
    return cleaned[:120] or "unknown"


def build_s3_key(
    result_type: str,
    trade_id: str,
    processed_at: str,
    base_prefix: str = DEFAULT_BASE_PREFIX,
) -> str:
    if result_type not in VALID_RESULT_TYPES:
        raise ValueError(f"Unsupported result_type: {result_type}")

    parsed_timestamp = datetime.fromisoformat(processed_at.replace("Z", "+00:00"))

    year = parsed_timestamp.strftime("%Y")
    month = parsed_timestamp.strftime("%m")
    day = parsed_timestamp.strftime("%d")

    safe_trade_id = safe_s3_key_part(trade_id)

    return (
        f"{base_prefix}/{result_type}/"
        f"year={year}/month={month}/day={day}/"
        f"trade_id={safe_trade_id}.json"
    )
