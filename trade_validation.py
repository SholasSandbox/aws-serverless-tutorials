from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_FIELDS = ["trade_id", "product", "volume_mwh"]

ERROR_VOLUME_MWH_NOT_NUMBER = "volume_mwh must be a number"
ERROR_VOLUME_MWH_NOT_POSITIVE = "volume_mwh must be greater than 0"


def find_missing_required_field(
    body: Mapping[str, Any], required_fields: Sequence[str]
) -> str | None:
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
    return None


def build_internal_trade(request_body: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_id": request_body["trade_id"],
        "product": request_body["product"],
        "volume_mwh": request_body["volume_mwh"],
    }
