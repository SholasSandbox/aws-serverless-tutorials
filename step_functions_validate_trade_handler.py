import logging
from typing import Any, TypedDict

from trade_handler import (
    REQUIRED_FIELDS,
    find_missing_required_field,
    validate_volume_mwh,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ERROR_INVALID_TRADE_INPUT = "Invalid trade input"
ERROR_MISSING_REQUIRED_FIELD = "Missing required field"

LOG_TRADE_VALIDATED = "Trade validated successfully trade_id=%s"
LOG_TRADE_REJECTED = "Trade validation failed error=%s"


class ValidationResult(TypedDict):
    is_valid: bool
    error: str | None


def validation_success() -> ValidationResult:
    return {
        "is_valid": True,
        "error": None,
    }


def validation_failure(error: str) -> ValidationResult:
    return {
        "is_valid": False,
        "error": error,
    }


def step_functions_validate_trade_handler(
    event: Any,
    context: Any,
) -> ValidationResult:
    """
    Lambda-style validation handler for Step Functions.

    Expected Step Functions task input:
    {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250
    }

    Expected Step Functions task output:
    {
        "is_valid": true,
        "error": null
    }

    or:

    {
        "is_valid": false,
        "error": "Missing required field: trade_id"
    }

    This output is intended to be inserted into the workflow state using:

    "ResultPath": "$.validation"
    """
    if not isinstance(event, dict):
        logger.warning(LOG_TRADE_REJECTED, ERROR_INVALID_TRADE_INPUT)
        return validation_failure(ERROR_INVALID_TRADE_INPUT)

    missing_field = find_missing_required_field(event, REQUIRED_FIELDS)
    if missing_field:
        error = f"{ERROR_MISSING_REQUIRED_FIELD}: {missing_field}"
        logger.warning(LOG_TRADE_REJECTED, error)
        return validation_failure(error)

    volume_mwh_error = validate_volume_mwh(event["volume_mwh"])
    if volume_mwh_error:
        logger.warning(LOG_TRADE_REJECTED, volume_mwh_error)
        return validation_failure(volume_mwh_error)

    logger.info(
        LOG_TRADE_VALIDATED,
        event["trade_id"],
    )

    return validation_success()
