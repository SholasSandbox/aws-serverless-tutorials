"""Minimal API-to-Step Functions handoff for Lesson 38.

This module is tutorial code. It demonstrates boundary translation,
dependency injection, truthful 202 responses, and a small Step Functions
adapter without deploying AWS resources.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
from collections.abc import Mapping
from typing import Any

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    ReadTimeoutError,
)

from trade_validation import (
    REQUIRED_FIELDS,
    find_missing_required_field,
    validate_volume_mwh,
)

LOGGER = logging.getLogger(__name__)

RETRYABLE_STEP_FUNCTIONS_ERRORS = {
    "ExecutionLimitExceeded",
    "KmsThrottlingException",
    "ServiceUnavailable",
    "ThrottlingException",
}
CONFLICT_STEP_FUNCTIONS_ERRORS = {"ExecutionAlreadyExists"}
RETRYABLE_TRANSPORT_ERRORS = (
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    ReadTimeoutError,
)


def normalise_headers(headers: Any) -> dict[str, str]:
    """Return lower-case HTTP header names with string values."""
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise ValueError("Request headers must be an object.")

    return {
        str(name).lower(): str(value)
        for name, value in headers.items()
        if value is not None
    }


def parse_json_object_body(event: Mapping[str, Any]) -> dict[str, Any]:
    """Parse the API Gateway body and require a JSON object."""
    raw_body = event.get("body")

    if not isinstance(raw_body, str) or not raw_body.strip():
        raise ValueError("Request body must contain valid JSON.")

    if event.get("isBase64Encoded") is True:
        try:
            raw_body = base64.b64decode(raw_body, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("Request body must contain valid JSON.") from exc

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must contain valid JSON.") from exc

    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")

    return body


def normalise_trade(body: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the shared trade fields and discard transport-only extras."""
    missing_field = find_missing_required_field(body, REQUIRED_FIELDS)
    if missing_field is not None:
        raise ValueError(f"Missing required field: {missing_field}.")

    volume_error = validate_volume_mwh(body["volume_mwh"])
    if volume_error is not None:
        raise ValueError(f"{volume_error}.")

    return {
        "trade_id": body["trade_id"],
        "product": body["product"],
        "volume_mwh": body["volume_mwh"],
    }


def extract_request_id(event: Mapping[str, Any], context: Any) -> str:
    """Prefer the API Gateway request ID, then use the Lambda request ID."""
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        request_id = request_context.get("requestId")
        if isinstance(request_id, str) and request_id.strip():
            return request_id

    lambda_request_id = getattr(context, "aws_request_id", None)
    if isinstance(lambda_request_id, str) and lambda_request_id.strip():
        return lambda_request_id

    return "unknown-request-id"


def require_idempotency_key(headers: Mapping[str, str]) -> str:
    """Require the public operation idempotency key."""
    idempotency_key = headers.get("idempotency-key", "").strip()
    if not idempotency_key:
        raise ValueError("Idempotency-Key header is required.")
    return idempotency_key


def select_correlation_id(headers: Mapping[str, str], request_id: str) -> str:
    """Use a caller correlation ID when supplied, otherwise the request ID."""
    return headers.get("x-correlation-id", "").strip() or request_id


def build_execution_name(idempotency_key: str) -> str:
    """Create a stable, Step Functions-safe execution name."""
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"trade-submit-{digest}"


def build_workflow_input(
    *,
    trade: Mapping[str, Any],
    correlation_id: str,
    idempotency_key: str,
    request_id: str,
) -> dict[str, Any]:
    """Build domain-shaped workflow input without HTTP envelope fields."""
    return {
        "trade": dict(trade),
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "request_id": request_id,
    }


def start_trade_workflow(
    *,
    step_functions_client: Any,
    state_machine_arn: str,
    execution_name: str,
    workflow_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Start one Step Functions execution and return a small adapter result."""
    response = step_functions_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=execution_name,
        input=json.dumps(dict(workflow_input), separators=(",", ":")),
    )

    return {
        "execution_arn": response["executionArn"],
        "start_date": response["startDate"],
    }


def json_response(
    *,
    status_code: int,
    body: Mapping[str, Any],
    correlation_id: str,
) -> dict[str, Any]:
    """Create an API Gateway-compatible response."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "x-correlation-id": correlation_id,
        },
        "body": json.dumps(dict(body)),
    }


def map_step_functions_error(exc: Exception) -> int:
    """Map AWS start failures to a client-safe HTTP status."""
    if isinstance(exc, ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in CONFLICT_STEP_FUNCTIONS_ERRORS:
            return 409
        if error_code in RETRYABLE_STEP_FUNCTIONS_ERRORS:
            return 503
        return 500
    if isinstance(exc, RETRYABLE_TRANSPORT_ERRORS):
        return 503
    if isinstance(exc, BotoCoreError):
        return 500
    return 500


def handle_trade_submission(
    event: Mapping[str, Any],
    context: Any,
    *,
    step_functions_client: Any,
    state_machine_arn: str,
) -> dict[str, Any]:
    """Translate an HTTP request into an asynchronous workflow start."""
    request_id = extract_request_id(event, context)
    try:
        headers = normalise_headers(event.get("headers"))
    except ValueError as exc:
        return json_response(
            status_code=400,
            correlation_id=request_id,
            body={"error": str(exc), "correlation_id": request_id},
        )

    correlation_id = select_correlation_id(headers, request_id)

    try:
        trade = normalise_trade(parse_json_object_body(event))
        idempotency_key = require_idempotency_key(headers)
    except ValueError as exc:
        return json_response(
            status_code=400,
            correlation_id=correlation_id,
            body={
                "error": str(exc),
                "correlation_id": correlation_id,
            },
        )

    execution_name = build_execution_name(idempotency_key)
    workflow_input = build_workflow_input(
        trade=trade,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_id=request_id,
    )

    if not state_machine_arn.strip():
        LOGGER.error(
            "trade workflow state machine is not configured",
            extra={"correlation_id": correlation_id, "request_id": request_id},
        )
        return json_response(
            status_code=500,
            correlation_id=correlation_id,
            body={
                "error": "Workflow could not be started.",
                "correlation_id": correlation_id,
            },
        )

    try:
        workflow_start = start_trade_workflow(
            step_functions_client=step_functions_client,
            state_machine_arn=state_machine_arn,
            execution_name=execution_name,
            workflow_input=workflow_input,
        )
    except Exception as exc:
        LOGGER.exception(
            "trade workflow start failed",
            extra={
                "correlation_id": correlation_id,
                "request_id": request_id,
                "execution_name": execution_name,
            },
        )
        status_code = map_step_functions_error(exc)
        return json_response(
            status_code=status_code,
            correlation_id=correlation_id,
            body={
                "error": "Workflow could not be started.",
                "correlation_id": correlation_id,
            },
        )

    LOGGER.info(
        "trade workflow started",
        extra={
            "correlation_id": correlation_id,
            "request_id": request_id,
            "execution_name": execution_name,
            "execution_arn": workflow_start["execution_arn"],
        },
    )

    return json_response(
        status_code=202,
        correlation_id=correlation_id,
        body={
            "status": "accepted_for_processing",
            "operation_id": execution_name,
            "correlation_id": correlation_id,
        },
    )


# Runtime wrapper. Tests call handle_trade_submission with an injected client.
_STEP_FUNCTIONS_CLIENT: Any | None = None


def get_step_functions_client() -> Any:
    """Create the SDK client lazily, then reuse it across warm invocations."""
    global _STEP_FUNCTIONS_CLIENT
    if _STEP_FUNCTIONS_CLIENT is None:
        _STEP_FUNCTIONS_CLIENT = boto3.client("stepfunctions")
    return _STEP_FUNCTIONS_CLIENT


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point."""
    state_machine_arn = os.environ.get("TRADE_STATE_MACHINE_ARN", "")
    return handle_trade_submission(
        event,
        context,
        step_functions_client=(
            get_step_functions_client() if state_machine_arn else None
        ),
        state_machine_arn=state_machine_arn,
    )
