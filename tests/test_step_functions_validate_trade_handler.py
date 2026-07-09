from typing import Any, Mapping

import pytest

from step_functions_validate_trade_handler import (
    ERROR_INVALID_TRADE_INPUT,
    ValidationResult,
    step_functions_validate_trade_handler,
)

from trade_handler import (
    ERROR_VOLUME_MWH_NOT_NUMBER,
    ERROR_VOLUME_MWH_NOT_POSITIVE,
)

from trade_result_persistence import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    build_trade_result_document,
)

TEST_TRADE_ID = "TRD-1001"
TEST_PRODUCT = "UK Power"
TEST_VOLUME_MWH = 250


def apply_result_path(
    original_input: dict,
    result_path: str,
    task_result: Mapping[str, Any] | ValidationResult,
) -> dict:
    if result_path != "$.validation":
        raise ValueError(f"Unsupported ResultPath: {result_path}")

    return {
        **original_input,
        "validation": task_result,
    }


def apply_catch_result_path(
    original_input: dict,
    result_path: str,
    task_error: Mapping[str, Any],
) -> dict:
    if result_path != "$.task_error":
        raise ValueError(f"Unsupported Catch ResultPath: {result_path}")

    return {
        **original_input,
        "task_error": task_error,
    }


def test_step_functions_validate_trade_handler_returns_valid_result_for_valid_trade():
    event = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    response = step_functions_validate_trade_handler(event, None)

    assert response == {
        "is_valid": True,
        "error": None,
    }


@pytest.mark.parametrize(
    "trade, expected_error",
    [
        (
            {
                "product": TEST_PRODUCT,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "Missing required field: trade_id",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "volume_mwh": TEST_VOLUME_MWH,
            },
            "Missing required field: product",
        ),
        (
            {
                "trade_id": TEST_TRADE_ID,
                "product": TEST_PRODUCT,
            },
            "Missing required field: volume_mwh",
        ),
    ],
)
def test_step_functions_validate_trade_handler_returns_invalid_for_missing_required_fields(
    trade: dict[str, Any],
    expected_error: str,
) -> None:
    response = step_functions_validate_trade_handler(trade, None)

    assert response == {
        "is_valid": False,
        "error": expected_error,
    }


@pytest.mark.parametrize(
    "volume_mwh, expected_error",
    [
        (True, ERROR_VOLUME_MWH_NOT_NUMBER),
        ("100", ERROR_VOLUME_MWH_NOT_NUMBER),
        (-10, ERROR_VOLUME_MWH_NOT_POSITIVE),
        (0, ERROR_VOLUME_MWH_NOT_POSITIVE),
    ],
)
def test_step_functions_validate_trade_handler_returns_invalid_for_invalid_volume_mwh(
    volume_mwh: Any,
    expected_error: str,
) -> None:
    event = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": volume_mwh,
    }

    response = step_functions_validate_trade_handler(event, None)

    assert response == {
        "is_valid": False,
        "error": expected_error,
    }


@pytest.mark.parametrize(
    "event",
    [
        None,
        [],
        "not-a-dict",
        123,
    ],
)
def test_step_functions_validate_trade_handler_returns_invalid_for_non_dict_input(
    event: Any,
) -> None:
    response = step_functions_validate_trade_handler(event, None)

    assert response == {
        "is_valid": False,
        "error": ERROR_INVALID_TRADE_INPUT,
    }


def test_step_functions_result_path_adds_valid_validation_result():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    task_result = step_functions_validate_trade_handler(original_input, None)

    workflow_state = apply_result_path(
        original_input,
        "$.validation",
        task_result,
    )

    assert workflow_state == {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
        "validation": {
            "is_valid": True,
            "error": None,
        },
    }


def test_step_functions_result_path_adds_invalid_validation_result():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": 0,
    }

    task_result = step_functions_validate_trade_handler(original_input, None)

    workflow_state = apply_result_path(
        original_input,
        "$.validation",
        task_result,
    )

    assert workflow_state == {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": 0,
        "validation": {
            "is_valid": False,
            "error": ERROR_VOLUME_MWH_NOT_POSITIVE,
        },
    }


def test_apply_result_path_rejects_unsupported_result_path():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    task_result = {
        "is_valid": True,
        "error": None,
    }

    with pytest.raises(ValueError, match="Unsupported ResultPath"):
        apply_result_path(original_input, "$.unexpected", task_result)


def route_validation_result(workflow_state: dict) -> str:
    validation = workflow_state.get("validation")

    if not isinstance(validation, dict):
        return "InvalidWorkflowInput"

    is_valid = validation.get("is_valid")

    if is_valid is True:
        return "AcceptedTrade"

    if is_valid is False:
        return "RejectedTrade"

    return "InvalidWorkflowInput"


def test_merged_valid_validation_result_routes_to_accepted_trade():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    task_result = step_functions_validate_trade_handler(original_input, None)

    workflow_state = apply_result_path(
        original_input,
        "$.validation",
        task_result,
    )

    next_state = route_validation_result(workflow_state)

    assert next_state == "AcceptedTrade"


def test_merged_invalid_validation_result_routes_to_rejected_trade():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": 0,
    }

    task_result = step_functions_validate_trade_handler(original_input, None)

    workflow_state = apply_result_path(
        original_input,
        "$.validation",
        task_result,
    )

    next_state = route_validation_result(workflow_state)

    assert next_state == "RejectedTrade"


@pytest.mark.parametrize(
    "workflow_state",
    [
        {},
        {"validation": None},
        {"validation": []},
        {"validation": {"error": None}},
        {"validation": {"is_valid": "yes", "error": None}},
    ],
)
def test_malformed_validation_result_routes_to_invalid_workflow_input(
    workflow_state: dict[str, Any],
) -> None:
    next_state = route_validation_result(workflow_state)

    assert next_state == "InvalidWorkflowInput"


LAMBDA_ERROR_DESCRIPTIONS = {
    "Lambda.ServiceException": "Lambda service temporarily unavailable",
    "Lambda.AWSLambdaException": "Lambda function invocation failed",
    "Lambda.SdkClientException": "AWS SDK client failed to call Lambda",
}


def build_simulated_lambda_task_error(error_state: dict[str, Any]) -> dict[str, str]:
    lambda_error = error_state.get("lambda_error")

    if not isinstance(lambda_error, str):
        return {
            "Error": "Unknown",
            "Cause": "Unknown Lambda error",
        }

    return {
        "Error": lambda_error,
        "Cause": LAMBDA_ERROR_DESCRIPTIONS.get(
            lambda_error,
            "Unknown Lambda error",
        ),
    }


@pytest.mark.parametrize(
    "lambda_error_state, expected_task_error",
    [
        (
            {"lambda_error": "Lambda.ServiceException"},
            {
                "Error": "Lambda.ServiceException",
                "Cause": "Lambda service temporarily unavailable",
            },
        ),
        (
            {"lambda_error": "Lambda.AWSLambdaException"},
            {
                "Error": "Lambda.AWSLambdaException",
                "Cause": "Lambda function invocation failed",
            },
        ),
        (
            {"lambda_error": "Lambda.SdkClientException"},
            {
                "Error": "Lambda.SdkClientException",
                "Cause": "AWS SDK client failed to call Lambda",
            },
        ),
    ],
)
def test_catch_result_path_adds_task_error_to_workflow_state(
    lambda_error_state: dict[str, Any],
    expected_task_error: dict[str, str],
) -> None:
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    task_error = build_simulated_lambda_task_error(lambda_error_state)

    workflow_state = apply_catch_result_path(
        original_input,
        "$.task_error",
        task_error,
    )

    assert workflow_state == {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
        "task_error": expected_task_error,
    }


@pytest.mark.parametrize(
    "lambda_error_state, expected_error",
    [
        ({}, "Unknown"),
        ({"lambda_error": None}, "Unknown"),
        ({"lambda_error": "Some.UnknownError"}, "Some.UnknownError"),
    ],
)
def test_build_simulated_lambda_task_error_returns_unknown_cause_for_unknown_errors(
    lambda_error_state: dict[str, Any],
    expected_error: str,
) -> None:
    result = build_simulated_lambda_task_error(lambda_error_state)

    assert result == {
        "Error": expected_error,
        "Cause": "Unknown Lambda error",
    }


def test_apply_catch_result_path_rejects_unsupported_result_path():
    original_input = {
        "trade_id": TEST_TRADE_ID,
        "product": TEST_PRODUCT,
        "volume_mwh": TEST_VOLUME_MWH,
    }

    task_error = {
        "Error": "Lambda.ServiceException",
        "Cause": "Lambda service temporarily unavailable",
    }

    with pytest.raises(ValueError, match="Unsupported Catch ResultPath"):
        apply_catch_result_path(
            original_input,
            "$.unexpected",
            task_error,
        )


def test_build_trade_result_document_for_accepted_trade():
    trade = {
        "trade_id": "TRD-001",
        "product": "PPA",
        "volume_mwh": 100,
    }

    result = build_trade_result_document(
        trade=trade,
        status=STATUS_ACCEPTED,
        reason=None,
        processed_at="2026-06-02T10:30:00Z",
    )

    assert result == {
        "trade_id": "TRD-001",
        "status": "ACCEPTED",
        "reason": None,
        "received_trade": trade,
        "processed_at": "2026-06-02T10:30:00Z",
    }


def test_build_trade_result_document_for_rejected_trade():
    trade = {
        "trade_id": "TRD-002",
        "product": "PPA",
        "volume_mwh": 0,
    }

    result = build_trade_result_document(
        trade=trade,
        status=STATUS_REJECTED,
        reason="volume_mwh must be greater than 0",
        processed_at="2026-06-02T10:30:00Z",
    )

    assert result["trade_id"] == "TRD-002"
    assert result["status"] == "REJECTED"
    assert result["reason"] == "volume_mwh must be greater than 0"
    assert result["received_trade"] == trade
