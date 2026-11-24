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
import re
import time
import uuid
from collections.abc import (
    Callable,
    Mapping,
)
from functools import lru_cache
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

from submission_registry import (
    claim_expired_recovery_lease,
    classify_existing_submission,
    confirm_submission_started,
    fingerprint_normalised_trade,
    get_submission_record,
    register_submission,
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


def build_execution_name(tenant_id: str, idempotency_key: str) -> str:
    """Create a stable execution name scoped to the tenant."""
    identity = json.dumps(
        [tenant_id, idempotency_key],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"trade-submit-{digest}"


def build_workflow_input(
    *,
    trade: Mapping[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    """Build domain-shaped workflow input without HTTP envelope fields."""
    return {
        "trade": dict(trade),
        "idempotency_key": idempotency_key,
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


def register_trade_for_handoff(
    *,
    table: Any,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
    recovery_token: str,
    lease_expires_at: int,
    now: int,
) -> str:
    """
    Register a normalized trade submission or classify
    an existing submission.

    Returns:
        "CREATED" for a new submission.
        "MATCH" for an existing submission with identical content.
        "CONFLICT" for an existing submission with different content.
    """
    # trade has already been normalised before reaching the workflow
    # handoff logic
    payload_fingerprint = fingerprint_normalised_trade(
        trade=trade,
    )
    submission_status = register_submission(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        payload_fingerprint=payload_fingerprint,
        recovery_token=recovery_token,
        lease_expires_at=lease_expires_at,
        now=now,
    )
    match submission_status:
        case "CREATED":
            return submission_status
        case "KEY_EXISTS":
            return classify_existing_submission(
                table=table,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                payload_fingerprint=payload_fingerprint,
            )
        case _:
            raise ValueError(f"Unexpected submission status: {submission_status!r}.")


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
    tenant_id: str,
    table: Any,
    recovery_token: str,
    lease_expires_at: int,
    now: int,
    confirmation_clock: Callable[[], int],
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

    execution_name = build_execution_name(
        tenant_id=tenant_id, idempotency_key=idempotency_key
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
        coordination_result = coordinate_trade_submission(
            table=table,
            step_functions_client=step_functions_client,
            state_machine_arn=state_machine_arn,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            trade=trade,
            recovery_token=recovery_token,
            lease_expires_at=lease_expires_at,
            now=now,
            confirmation_clock=confirmation_clock,
        )

    except Exception as exc:
        LOGGER.exception(
            "trade submission coordination failed",
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
        "trade submission coordinated",
        extra={
            "correlation_id": correlation_id,
            "request_id": request_id,
            "execution_name": execution_name,
            "coordination_status": coordination_result["status"],
        },
    )
    return map_trade_submission_outcome(
        outcome=coordination_result,
        operation_id=execution_name,
        correlation_id=correlation_id,
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

    try:
        tenant_id = extract_authenticated_tenant_id(event)
    except ValueError:
        request_id = extract_request_id(event, context)

        return json_response(
            status_code=403,
            correlation_id=request_id,
            body={
                "error": "Forbidden.",
                "correlation_id": request_id,
            },
        )

    return handle_trade_submission(
        event,
        context,
        step_functions_client=(
            get_step_functions_client() if state_machine_arn else None
        ),
        state_machine_arn=state_machine_arn,
        tenant_id=tenant_id,
    )


def register_and_claim_initial_submission(
    *,
    table: Any,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
    recovery_token: str,
    lease_expires_at: int,
    now: int,
) -> str:
    """
    Register a submission and acquire initial ownership.

    Returns:
        "READY_TO_START" when registration and
        ownership acquisition both succeed.

        "MATCH" for an existing identical submission.
        "CONFLICT" for an existing conflicting submission.

    Raises:
        ClientError when a DynamoDB operation fails.
    """
    registered_status = register_trade_for_handoff(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        trade=trade,
        recovery_token=recovery_token,
        lease_expires_at=lease_expires_at,
        now=now,
    )

    if registered_status == "CREATED":
        return "READY_TO_START"

    if registered_status in ["MATCH", "CONFLICT"]:
        return registered_status

    raise ValueError(f"Unexpected registration status: {registered_status!r}.")


def extract_authenticated_tenant_id(
    event: Mapping[str, Any],
) -> str:
    """
    Extract tenant identity from an API Gateway
    HTTP API JWT authorizer context.

    Raises ValueError when trusted tenant
    identity is unavailable or invalid.
    """
    # ----------------------------------------------------------------
    # 1. Safely access the JWT authorizer block
    # ----------------------------------------------------------------

    current: Any = event

    for key in ("requestContext", "authorizer", "jwt", "claims"):
        if not isinstance(current, Mapping):
            raise ValueError("JWT authorizer context is missing or invalid.")
        current = current.get(key)

    if not isinstance(current, Mapping):
        raise ValueError("JWT authorizer claims are missing or invalid.")

    tenant_id = current.get("tenant_id")  # Generic / Auth0 namespace claim

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Authenticated tenant ID is missing or invalid.")

    return tenant_id


def coordinate_initial_trade_start(
    *,
    table: Any,
    step_functions_client: Any,
    state_machine_arn: str,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
    recovery_token: str,
    lease_expires_at: int,
    registration_now: int,
    confirmation_clock: Callable[[], int],
) -> dict[str, str]:
    """Coordinate registration, workflow start and confirmation."""

    if not isinstance(state_machine_arn, str) or not state_machine_arn.strip():
        raise ValueError("state_machine_arn must be a non-empty string.")

    registered_status = register_and_claim_initial_submission(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        trade=trade,
        recovery_token=recovery_token,
        lease_expires_at=lease_expires_at,
        now=registration_now,
    )

    if registered_status == "READY_TO_START":
        execution_name = build_execution_name(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        )
        workflow_input = build_workflow_input(
            trade=trade,
            idempotency_key=idempotency_key,
        )
        workflow_start = start_trade_workflow(
            step_functions_client=step_functions_client,
            state_machine_arn=state_machine_arn,
            execution_name=execution_name,
            workflow_input=workflow_input,
        )

        execution_arn = workflow_start["execution_arn"]

        status = confirm_submission_started(
            table=table,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            execution_arn=execution_arn,
            recovery_token=recovery_token,
            now=confirmation_clock(),
        )
        return {
            "status": status,
            "execution_arn": execution_arn,
        }
    if registered_status in ["MATCH", "CONFLICT"]:
        return {"status": registered_status}

    raise ValueError(f"Unexpected registration status: {registered_status!r}.")


def describe_trade_execution(
    *,
    step_functions_client: Any,
    execution_arn: str,
) -> dict[str, str]:
    """
    Look up a Step Functions execution.

    Returns execution metadata when found,
    or NOT_OBSERVED for ExecutionDoesNotExist.

    Propagates other AWS errors.
    """
    client = step_functions_client
    try:
        response = client.describe_execution(
            executionArn=execution_arn,
            includedData="ALL_DATA",
        )

        status = response.get("status")
        input_json = response.get("input")
        if not isinstance(input_json, str) or not input_json.strip():
            raise ValueError("Step Functions execution input is missing or blank.")

        if status in [
            "SUCCEEDED",
            "FAILED",
            "TIMED_OUT",
            "ABORTED",
            "RUNNING",
            "PENDING_REDRIVE",
        ]:
            return {
                "lookup_status": "FOUND",
                "execution_arn": response["executionArn"],
                "execution_status": status,
                "execution_input_json": input_json,
            }

        raise ValueError(f"Unhandled execution status: {status!r}")

    except ClientError as exc_info:
        if exc_info.response["Error"]["Code"] == "ExecutionDoesNotExist":
            return {
                "lookup_status": "NOT_OBSERVED",
                "execution_arn": execution_arn,
            }
        raise


STATE_MACHINE_ARN_PATTERN = re.compile(
    r"^arn:(?P<partition>aws|aws-cn|aws-us-gov):states:"
    r"(?P<region>[a-z]{2}(?:-gov)?-[a-z]+-[0-9]):"
    r"(?P<account_id>[0-9]{12}):stateMachine:"
    r"(?P<name>[a-zA-Z0-9_-]{1,80})(?::(?P<qualifier>[a-zA-Z0-9_-]{1,80}))?$"
)


def derive_execution_arn(
    *,
    state_machine_arn: str,
    execution_name: str,
) -> str:
    """
    Derive a Step Functions execution ARN.

    Accepts only an unqualified state-machine ARN.

    Raises:
        ValueError: If the ARN is malformed, qualified,
                    or otherwise unsupported.

    Returns:
        The corresponding execution ARN.
    """
    arn_error = "Expected an unqualified Step Functions state machine ARN."
    if not isinstance(state_machine_arn, str):
        raise ValueError(arn_error)

    match = STATE_MACHINE_ARN_PATTERN.fullmatch(state_machine_arn)
    if match is None or match.group("qualifier") is not None:
        raise ValueError(arn_error)

    if not isinstance(execution_name, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", execution_name
    ):
        raise ValueError(
            "execution_name must be 1–80 characters using only "
            "ASCII letters, digits, hyphens or underscores."
        )

    partition, region, account_id, machine_name = match.group(
        "partition", "region", "account_id", "name"
    )
    return (
        f"arn:{partition}:states:{region}:{account_id}:"
        f"execution:{machine_name}:{execution_name}"
    )


def execution_input_matches(
    *,
    observed_input_json: str,
    expected_workflow_input: Mapping[str, Any],
) -> bool:
    """Compare the parsed execution input with the expected workflow input.

    Raises ValueError when the observed input cannot be parsed as a JSON object.
    """
    try:
        observed_workflow_input = json.loads(observed_input_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Observed execution input must be a JSON string.") from exc

    if not isinstance(observed_workflow_input, dict):
        raise ValueError("Observed execution input must be a JSON object.")

    return json.dumps(
        observed_workflow_input, sort_keys=True, separators=(",", ":")
    ) == json.dumps(expected_workflow_input, sort_keys=True, separators=(",", ":"))


def inspect_trade_execution_for_recovery(
    *,
    step_functions_client: Any,
    state_machine_arn: str,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
) -> dict[str, str]:
    """
    Inspect an existing workflow execution.

    Return VERIFIED when the execution exists and its
    original input matches the expected workflow input.

    Return INPUT_MISMATCH when an execution exists
    but its input differs.

    Return INCONCLUSIVE when the execution is NOT_OBSERVED.

    Propagate lookup and input-validation errors.
    """

    execution_name = build_execution_name(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    execution_arn = derive_execution_arn(
        state_machine_arn=state_machine_arn,
        execution_name=execution_name,
    )
    execution_lookup = describe_trade_execution(
        step_functions_client=step_functions_client,
        execution_arn=execution_arn,
    )
    if execution_lookup["lookup_status"] == "NOT_OBSERVED":
        return {
            "reconciliation_status": "INCONCLUSIVE",
            "execution_arn": execution_arn,
        }

    workflow_input = build_workflow_input(
        trade=trade,
        idempotency_key=idempotency_key,
    )

    if execution_input_matches(
        observed_input_json=execution_lookup["execution_input_json"],
        expected_workflow_input=workflow_input,
    ):
        return {
            "reconciliation_status": "VERIFIED",
            "execution_arn": execution_arn,
            "execution_status": execution_lookup["execution_status"],
        }

    return {
        "reconciliation_status": "INPUT_MISMATCH",
        "execution_arn": execution_arn,
    }


def confirm_verified_trade_recovery(
    *,
    table: Any,
    tenant_id: str,
    idempotency_key: str,
    recovery_token: str,
    now: int,
    reconciliation_result: Mapping[str, str],
) -> str:
    """
    Confirm a recovered execution only when reconciliation is VERIFIED.

    Returns:
        START_CONFIRMED when conditional confirmation succeeds.
        INPUT_MISMATCH when execution input differs.
        INCONCLUSIVE when execution existence is uncertain.

    Propagates DynamoDB confirmation failures.
    """
    status = reconciliation_result["reconciliation_status"]
    match status:
        case "INPUT_MISMATCH" | "INCONCLUSIVE":
            return status
        case "VERIFIED":
            execution_arn = reconciliation_result["execution_arn"]
            submission_status = confirm_submission_started(
                table=table,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                execution_arn=execution_arn,
                recovery_token=recovery_token,
                now=now,
            )
            return submission_status
        case _:
            raise ValueError(f"Invalid reconciliation status: {status}.")


def coordinate_expired_trade_recovery(
    *,
    table: Any,
    step_functions_client: Any,
    state_machine_arn: str,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
    new_recovery_token: str,
    new_lease_expires_at: int,
    claim_now: int,
    confirmation_clock: Callable[[], int],
) -> str:
    """
    Coordinate recovery of an existing trade submission.

    Returns:
        START_CONFIRMED
        INPUT_MISMATCH
        INCONCLUSIVE
        NOT_CLAIMED
        CONFLICT
        ALREADY_CONFIRMED

    Propagates unexpected AWS and validation errors.

    Never starts a new Step Functions execution.
    """
    record = get_submission_record(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )

    stored_fingerprint = record.get("payload_fingerprint")
    if stored_fingerprint != fingerprint_normalised_trade(trade=trade):
        return "CONFLICT"

    if record.get("status") == "START_CONFIRMED":
        return "ALREADY_CONFIRMED"

    lease_claim = claim_expired_recovery_lease(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        expected_recovery_token=record.get("recovery_token"),
        expected_payload_fingerprint=stored_fingerprint,
        new_recovery_token=new_recovery_token,
        new_lease_expires_at=new_lease_expires_at,
        now=claim_now,
    )
    if lease_claim == "NOT_CLAIMED":
        return lease_claim

    reconciliation_result = inspect_trade_execution_for_recovery(
        step_functions_client=step_functions_client,
        state_machine_arn=state_machine_arn,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        trade=trade,
    )
    confirmation = confirm_verified_trade_recovery(
        table=table,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        recovery_token=new_recovery_token,
        now=confirmation_clock(),
        reconciliation_result=reconciliation_result,
    )
    return confirmation


def coordinate_trade_submission(
    *,
    table: Any,
    step_functions_client: Any,
    state_machine_arn: str,
    tenant_id: str,
    idempotency_key: str,
    trade: Mapping[str, Any],
    recovery_token: str,
    lease_expires_at: int,
    now: int,
    confirmation_clock: Callable[[], int],
) -> dict[str, str]:
    """
    Route a normalised trade through initial submission
    or existing-submission recovery.

    Return a dictionary containing at least a status.

    Never start a workflow directly. Delegate to the
    existing coordinators.

    Propagate unexpected AWS and validation errors.
    """

    initial_result = coordinate_initial_trade_start(
        table=table,
        step_functions_client=step_functions_client,
        state_machine_arn=state_machine_arn,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        trade=trade,
        recovery_token=recovery_token,
        lease_expires_at=lease_expires_at,
        registration_now=now,
        confirmation_clock=confirmation_clock,
    )
    status = initial_result["status"]
    if status == "START_CONFIRMED":
        return initial_result
    if status == "CONFLICT":
        return initial_result
    if status == "MATCH":
        recovery_status = coordinate_expired_trade_recovery(
            table=table,
            step_functions_client=step_functions_client,
            state_machine_arn=state_machine_arn,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            trade=trade,
            new_recovery_token=recovery_token,
            new_lease_expires_at=lease_expires_at,
            claim_now=now,
            confirmation_clock=confirmation_clock,
        )
        return {"status": recovery_status}

    raise ValueError(f"Unexpected initial trade coordination status: {status!r}.")


def map_trade_submission_outcome(
    *,
    outcome: Mapping[str, str],
    operation_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """
    Convert an internal trade coordination outcome
    into an API Gateway-compatible HTTP response.

    Preserve the operation ID and correlation ID.

    Do not perform DynamoDB or Step Functions operations.

    Raise ValueError for an unknown coordination status.
    """

    outcome_status = outcome["status"]
    match outcome_status:
        case "START_CONFIRMED":
            return json_response(
                status_code=202,
                correlation_id=correlation_id,
                body={
                    "status": "accepted_for_processing",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case "ALREADY_CONFIRMED":
            return json_response(
                status_code=200,
                correlation_id=correlation_id,
                body={
                    "status": "already_accepted",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case "CONFLICT":
            return json_response(
                status_code=409,
                correlation_id=correlation_id,
                body={
                    "error": "idempotency_key_conflict",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case "NOT_CLAIMED":
            return json_response(
                status_code=202,
                correlation_id=correlation_id,
                body={
                    "status": "confirmation_pending",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case "INCONCLUSIVE":
            return json_response(
                status_code=503,
                correlation_id=correlation_id,
                body={
                    "error": "start_status_unknown",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case "INPUT_MISMATCH":
            return json_response(
                status_code=500,
                correlation_id=correlation_id,
                body={
                    "error": "submission_verification_failed",
                    "operation_id": operation_id,
                    "correlation_id": correlation_id,
                },
            )
        case _:
            raise ValueError(
                f"Unexpected trade submission outcome: {outcome_status!r}."
            )


@lru_cache(maxsize=1)
def get_submission_table(table_name: str) -> Any:
    """
    Lazily obtain a DynamoDB table resource and reuse it
    across warm Lambda invocations.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    return table


def current_epoch_seconds() -> int:
    """Return the current Unix timestamp in whole seconds."""
    return int(time.time())


def build_submission_attempt(
    *,
    lease_duration_seconds: int,
    clock: Callable[[], int],
) -> dict[str, str | int]:
    """
    Generate a fresh recovery token and initial lease timestamps
    for an individual submission attempt.
    """
    if isinstance(lease_duration_seconds, bool) or not isinstance(
        lease_duration_seconds, int
    ):
        raise ValueError("Lease duration must be an integer")

    if lease_duration_seconds <= 0:
        raise ValueError("Lease duration must be greater than 0")

    now = clock()
    recovery_token = str(uuid.uuid4())

    return {
        "recovery_token": recovery_token,
        "now": now,
        "lease_expires_at": now + lease_duration_seconds,
    }
