from __future__ import annotations

import base64
import json
import re
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

import api_workflow_handoff
from api_workflow_handoff import (
    build_execution_name,
    build_submission_attempt,
    build_workflow_input,
    confirm_verified_trade_recovery,
    coordinate_expired_trade_recovery,
    coordinate_initial_trade_start,
    coordinate_trade_submission,
    derive_execution_arn,
    describe_trade_execution,
    execution_input_matches,
    extract_authenticated_tenant_id,
    get_submission_table,
    handle_trade_submission,
    inspect_trade_execution_for_recovery,
    lambda_handler,
    map_trade_submission_outcome,
    normalise_trade,
    register_and_claim_initial_submission,
    register_trade_for_handoff,
)
from submission_registry import fingerprint_normalised_trade

STATE_MACHINE_ARN = (
    "arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing"
)


def make_event(
    *,
    body: str = '{"trade_id":"TRD-1001","product":"POWER","volume_mwh":25}',
    headers: dict[str, str] | None = None,
    request_id: str = "REQ-456",
) -> dict:
    return {
        "body": body,
        "headers": (
            headers
            if headers is not None
            else {
                "Idempotency-Key": "submission-001",
                "X-Correlation-Id": "CORR-123",
            }
        ),
        "requestContext": {"requestId": request_id},
    }


def test_valid_request_starts_workflow_with_normalised_input(submission_table) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 202

    call = client.start_execution.call_args.kwargs
    assert call["stateMachineArn"] == STATE_MACHINE_ARN
    assert call["name"] == build_execution_name("TENANT-A", "submission-001")
    assert json.loads(call["input"]) == {
        "trade": {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        },
        "idempotency_key": "submission-001",
    }
    assert "requestContext" not in json.loads(call["input"])
    assert "headers" not in json.loads(call["input"])


def test_valid_request_returns_truthful_accepted_response(submission_table) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 202
    assert body["status"] == "accepted_for_processing"
    assert "processed successfully" not in response["body"].lower()


def test_invalid_json_returns_400_without_starting_workflow(submission_table) -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body="not-json"),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_non_object_json_returns_400_without_starting_workflow(
    submission_table,
) -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='["TRD-1001"]'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_base64_encoded_json_body_is_decoded_before_workflow_start(
    submission_table,
) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }
    event = make_event(
        body=base64.b64encode(
            b'{"trade_id":"TRD-1001","product":"POWER","volume_mwh":25}'
        ).decode("ascii")
    )
    event["isBase64Encoded"] = True

    response = handle_trade_submission(
        event,
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 202


def test_missing_trade_field_returns_400_without_starting_workflow(
    submission_table,
) -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='{"product":"POWER","volume_mwh":25}'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 400
    assert "trade_id" in response["body"]
    client.start_execution.assert_not_called()


def test_external_fields_are_not_passed_to_workflow(submission_table) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = handle_trade_submission(
        make_event(
            body=(
                '{"trade_id":"TRD-1001","product":"POWER","volume_mwh":25,'
                '"unexpected_external_field":"do-not-pass"}'
            )
        ),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 202
    workflow_input = json.loads(client.start_execution.call_args.kwargs["input"])
    assert "unexpected_external_field" not in workflow_input["trade"]


def test_missing_idempotency_key_returns_400(submission_table) -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(headers={"X-Correlation-Id": "CORR-123"}),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_retryable_step_functions_failure_returns_503_not_202(submission_table) -> None:
    client = Mock()
    client.start_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        },
        "StartExecution",
    )

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 503
    assert body["error"] == "Workflow could not be started."
    assert "Rate exceeded" not in response["body"]


def test_duplicate_execution_name_returns_client_safe_409(submission_table) -> None:
    client = Mock()
    client.start_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ExecutionAlreadyExists",
                "Message": "Execution already exists",
            }
        },
        "StartExecution",
    )

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 409
    assert "Execution already exists" not in response["body"]


def test_permission_failure_returns_500_without_leaking_aws_details(
    submission_table,
) -> None:
    client = Mock()
    client.start_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "role arn and account details",
            }
        },
        "StartExecution",
    )

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 500
    assert "role arn and account details" not in response["body"]


def test_connection_failure_returns_503_without_leaking_endpoint(
    submission_table,
) -> None:
    client = Mock()
    client.start_execution.side_effect = EndpointConnectionError(
        endpoint_url="https://states.example.internal"
    )

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 503
    assert "states.example.internal" not in response["body"]


def test_unexpected_start_failure_returns_500_without_leaking_details(
    submission_table,
) -> None:
    client = Mock()
    client.start_execution.side_effect = RuntimeError("sensitive internal detail")

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 500
    assert "sensitive internal detail" not in response["body"]


def test_missing_state_machine_configuration_returns_500_without_sdk_call(
    submission_table,
) -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn="",
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert response["statusCode"] == 500
    client.start_execution.assert_not_called()


def test_execution_name_is_stable_for_same_tenant_and_key() -> None:
    """Same inputs produce the same name"""
    first = build_execution_name("TENANT-A", "submission-001")
    repeated = build_execution_name("TENANT-A", "submission-001")

    assert first == repeated


def test_execution_name_differs_across_tenants() -> None:
    """Same key, different tenants produce different names"""
    first = build_execution_name("TENANT-A", "submission-001")
    different_tenant = build_execution_name("TENANT-B", "submission-001")

    assert first != different_tenant


def test_execution_name_differs_across_keys() -> None:
    """Same tenant, different keys produce different names"""
    first = build_execution_name("TENANT-A", "submission-001")
    different_key = build_execution_name("TENANT-A", "submission-002")

    assert first != different_key


@pytest.mark.parametrize(
    "first_tenant, first_key, second_tenant, second_key",
    [
        pytest.param(
            "AB",
            "C",
            "A",
            "BC",
            id="ambiguous-concatenation",
        ),
        pytest.param(
            "A:B",
            "C",
            "A",
            "B:C",
            id="ambiguous-colon-separator",
        ),
    ],
)
def test_execution_name_avoids_ambiguous_identity_concatenation(
    first_tenant: str,
    first_key: str,
    second_tenant: str,
    second_key: str,
) -> None:
    # ("AB", "C") and ("A", "BC") produce different names
    first = build_execution_name(first_tenant, first_key)
    second = build_execution_name(second_tenant, second_key)

    assert first != second


@pytest.mark.parametrize(
    "tenant_id, idempotency_key",
    [
        ("TENANT-A", "submission-001"),
        ("TENANT A", "submission * ? [001]"),
        ("TENANT-東京", "soumission-énergie"),
        ("TENANT\nA", "submission\x00\x7f"),
        ("T" * 200, "K" * 200),
    ],
)
def test_execution_name_is_step_functions_compatible(
    tenant_id: str,
    idempotency_key: str,
) -> None:
    execution_name = build_execution_name(
        tenant_id,
        idempotency_key,
    )

    # AWS execution names must contain 1–80 characters.
    assert 1 <= len(execution_name) <= 80

    # Restrict names to ASCII for CloudWatch compatibility.
    assert execution_name.isascii()

    # Enforce our application's stricter naming convention.
    assert (
        re.fullmatch(
            r"trade-submit-[0-9a-f]{24}",
            execution_name,
        )
        is not None
    )


def test_retry_with_same_idempotency_key_has_stable_workflow_input(
    submission_table,
) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    request_body = json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    first_response = handle_trade_submission(
        make_event(
            body=request_body,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-788"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    retry_response = handle_trade_submission(
        make_event(
            body=request_body,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-789",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-B",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert client.start_execution.call_count == 1

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs

    expected_execution_name = build_execution_name("TENANT-A", "SUBMISSION-1001")

    assert first_call["name"] == expected_execution_name

    assert first_call["stateMachineArn"] == STATE_MACHINE_ARN
    assert first_response["statusCode"] == 202
    assert retry_response["statusCode"] == 200

    first_body = json.loads(first_response["body"])
    retry_body = json.loads(retry_response["body"])
    assert retry_body["status"] == "already_accepted"
    assert retry_body["operation_id"] == first_body["operation_id"]
    client.start_execution.assert_called_once()

    workflow_input = json.loads(first_call["input"])

    assert workflow_input["trade"]["trade_id"] == "TRD-1001"


def test_changed_volume_same_key_returns_idempotency_conflict(submission_table) -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    request_body_a = json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    first_response = handle_trade_submission(
        make_event(
            body=request_body_a,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-788"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    request_body_b = json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 50,
        }
    )

    conflict_response = handle_trade_submission(
        make_event(
            body=request_body_b,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=submission_table,
        recovery_token="token-B",
        lease_expires_at=150,
        now=100,
        confirmation_clock=lambda: 110,
    )

    assert client.start_execution.call_count == 1

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs

    expected_execution_name = build_execution_name("TENANT-A", "SUBMISSION-1001")

    assert first_call["name"] == expected_execution_name

    workflow_a_input = json.loads(first_call["input"])
    assert workflow_a_input["trade"]["volume_mwh"] == 25

    assert first_response["statusCode"] == 202
    assert conflict_response["statusCode"] == 409
    assert json.loads(conflict_response["body"])["error"] == "idempotency_key_conflict"

    client.start_execution.assert_called_once()
    start_args = client.start_execution.call_args.kwargs
    assert json.loads(start_args["input"])["trade"]["volume_mwh"] == 25


def test_register_trade_for_handoff_creates_submission(submission_table):

    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )
    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        **TEST_LEASE,
        now=100,
    )

    registered_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert response == "CREATED"

    assert registered_submission == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        **TEST_LEASE,
    }


def test_register_trade_for_handoff_matches_duplicate(submission_table) -> None:

    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert response == "CREATED"
    stored_record_before = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    # Second submission with duplicate content should return match
    response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert response == "MATCH"

    stored_record_after = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]
    assert stored_record_before == stored_record_after


def test_register_trade_for_handoff_rejects_payload_conflict(submission_table) -> None:

    table = submission_table
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert response == "CREATED"

    stored_record_before = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 30,
        }
    )

    # Second submission with different content should return CONFLICT
    response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert response == "CONFLICT"
    stored_record_after = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]
    assert stored_record_before == stored_record_after


def test_register_trade_for_handoff_scopes_tenant_identity(submission_table) -> None:

    table = submission_table

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    tenant_a_key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }
    tenant_a_response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert tenant_a_response == "CREATED"

    tenant_a_submission = table.get_item(
        Key=tenant_a_key,
        ConsistentRead=True,
    )["Item"]

    assert tenant_a_submission == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        **TEST_LEASE,
    }

    tenant_b_key = {
        "tenant_id": "TENANT-B",
        "idempotency_key": "SUBMISSION-1001",
    }

    # Two different tenants can each register the same idempotency key
    tenant_b_response = register_trade_for_handoff(
        table=table,
        tenant_id="TENANT-B",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        now=100,
        **TEST_LEASE,
    )
    assert tenant_b_response == "CREATED"

    tenant_b_submission = table.get_item(
        Key=tenant_b_key,
        ConsistentRead=True,
    )["Item"]

    assert tenant_b_submission == {
        "tenant_id": "TENANT-B",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        **TEST_LEASE,
    }


def test_register_trade_for_handoff_propagates_dynamodb_error() -> None:
    table = Mock()
    error = table.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied",
            }
        },
        "put_item",
    )

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    TEST_LEASE = {
        "recovery_token": "test-token-001",
        "lease_expires_at": 200,
    }

    with pytest.raises(
        ClientError,
        match="AccessDeniedException",
    ) as exc_info:
        register_trade_for_handoff(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            trade=trade,
            now=100,
            **TEST_LEASE,
        )

    assert exc_info.value is error
    table.put_item.assert_called_once()


def test_register_and_claim_initial_submission_acquires_lease(submission_table) -> None:

    table = submission_table

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        recovery_token="initial-token",
        lease_expires_at=200,
        now=100,
    )
    assert response == "READY_TO_START"

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    claimed_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert claimed_submission == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "initial-token",
        "lease_expires_at": 200,
    }


def test_register_and_claim_initial_submission_matching_duplicate_preserves_lease(
    submission_table,
) -> None:

    table = submission_table

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    initial_response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        recovery_token="initial-token",
        lease_expires_at=200,
        now=100,
    )
    assert initial_response == "READY_TO_START"

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    pre_dup_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    second_response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        recovery_token="second-token",
        lease_expires_at=300,
        now=150,
    )
    assert second_response == "MATCH"

    post_dup_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert post_dup_submission == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "initial-token",
        "lease_expires_at": 200,
    }

    assert pre_dup_submission == post_dup_submission


def test_register_and_claim_initial_submission_conflict_preserves_record(
    submission_table,
) -> None:

    table = submission_table

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    initial_response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        recovery_token="initial-token",
        lease_expires_at=200,
        now=100,
    )
    assert initial_response == "READY_TO_START"

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    pre_second_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    modified_trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 30,
        }
    )

    # with key with different volume
    second_response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=modified_trade,
        recovery_token="second-token",
        lease_expires_at=300,
        now=150,
    )
    assert second_response == "CONFLICT"

    post_second_submission = table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert pre_second_submission == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "initial-token",
        "lease_expires_at": 200,
    }

    #  item in registry is not modified
    assert pre_second_submission == post_second_submission
    assert post_second_submission[
        "payload_fingerprint"
    ] != fingerprint_normalised_trade(modified_trade)


def test_register_and_claim_initial_submission_uses_single_write() -> None:

    table = Mock()

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    response = register_and_claim_initial_submission(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade=trade,
        recovery_token="initial-token",
        lease_expires_at=200,
        now=100,
    )

    assert response == "READY_TO_START"
    table.put_item.assert_called_once()
    table.update_item.assert_not_called()
    table.get_item.assert_not_called()


def test_register_and_claim_initial_submission_registration_failure_skips_lease() -> (
    None
):
    table = Mock()

    error = table.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied",
            }
        },
        "put_item",
    )

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    with pytest.raises(ClientError) as exc_info:
        register_and_claim_initial_submission(
            table=table,
            tenant_id="TENANT-A",
            idempotency_key="SUBMISSION-1001",
            trade=trade,
            recovery_token="initial-token",
            lease_expires_at=200,
            now=100,
        )

    assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"
    assert exc_info.value is error
    table.put_item.assert_called_once()
    table.get_item.assert_not_called()
    table.update_item.assert_not_called()  # lease acquisition attempt was skipped


def test_extract_authenticated_tenant_id_from_jwt_claims() -> None:

    event = {
        "requestContext": {
            "requestId": "REQ-123",
            "authorizer": {
                "jwt": {
                    "claims": {
                        "tenant_id": "TENANT-A",
                    },
                    "scopes": ["trades:submit"],
                },
            },
        },
    }
    tenant_id = extract_authenticated_tenant_id(event=event)

    assert tenant_id == "TENANT-A"


def test_extract_authenticated_tenant_id_rejects_missing_claims() -> None:

    event = {
        "requestContext": {
            "requestId": "REQ-123",
            "authorizer": {
                "jwt": {
                    "invalid-claims": {
                        "tenant_id": "TENANT-A",
                    },
                    "scopes": ["trades:submit"],
                },
            },
        },
    }

    with pytest.raises(
        ValueError, match="JWT authorizer claims are missing or invalid."
    ):
        extract_authenticated_tenant_id(event=event)


@pytest.mark.parametrize(
    "tenant_id",
    [
        pytest.param(None, id="null"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
        pytest.param(123, id="integer"),
        pytest.param(False, id="boolean"),
        pytest.param([], id="list"),
        pytest.param({}, id="dictionary"),
    ],
)
def test_extract_authenticated_tenant_id_rejects_invalid_tenant(
    tenant_id: object,
) -> None:
    event = {
        "requestContext": {
            "requestId": "REQ-123",
            "authorizer": {
                "jwt": {
                    "claims": {
                        "tenant_id": tenant_id,
                    },
                    "scopes": ["trades:submit"],
                },
            },
        },
    }
    with pytest.raises(
        ValueError,
        match=r"^Authenticated tenant ID is missing or invalid\.$",
    ):
        extract_authenticated_tenant_id(event=event)


def test_extract_authenticated_tenant_id_ignores_untrusted_header() -> None:
    event = {
        "headers": {
            "x-tenant-id": "TENANT-FROM-HEADER",
        },
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"^Authenticated tenant ID is missing or invalid\.$",
    ):
        extract_authenticated_tenant_id(event=event)


def test_extract_authenticated_tenant_id_prefers_jwt_claim_over_header() -> None:
    event = {
        "headers": {
            "x-tenant-id": "TENANT-FROM-HEADER",
        },
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"tenant_id": "TENANT-A"}},
            },
        },
    }

    tenant_id = extract_authenticated_tenant_id(event=event)

    assert tenant_id == "TENANT-A"


def test_extract_authenticated_tenant_id_rejects_malformed_event_structure() -> None:
    event = {
        "requestContext": {
            "authorizer": "not-a-dictionary",
        }
    }

    with pytest.raises(
        ValueError,
        match=r"^JWT authorizer context is missing or invalid\.$",
    ):
        extract_authenticated_tenant_id(event=event)


def test_lambda_handler_forwards_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    event = make_event(request_id="REQ-123")
    authorizer = {
        "jwt": {
            "claims": {
                "tenant_id": "TENANT-A",
            },
            "scopes": ["trades:submit"],
        },
    }
    event["requestContext"]["authorizer"] = authorizer

    context = SimpleNamespace(aws_request_id="LAMBDA-789")

    # Supply the environment configuration expected by lambda_handler.
    monkeypatch.setenv("TRADE_STATE_MACHINE_ARN", STATE_MACHINE_ARN)

    monkeypatch.setenv("TRADE_SUBMISSION_TABLE_NAME", "trade-submissions")

    monkeypatch.setenv("TRADE_SUBMISSION_LEASE_SECONDS", "50")

    # Create fake dependencies
    fake_client = Mock()
    fake_table = Mock()
    mock_get_client = Mock(return_value=fake_client)

    mock_clock = Mock(return_value=100)

    monkeypatch.setattr(
        api_workflow_handoff,
        "current_epoch_seconds",
        mock_clock,
    )

    expected_uuid = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

    mock_uuid = Mock(return_value=expected_uuid)

    monkeypatch.setattr(
        api_workflow_handoff.uuid,
        "uuid4",
        mock_uuid,
    )

    mock_get_table = Mock(return_value=fake_table)

    monkeypatch.setattr(
        api_workflow_handoff,
        "get_submission_table",
        mock_get_table,
    )

    mock_handler = create_autospec(
        api_workflow_handoff.handle_trade_submission,
        return_value={"statusCode": 202, "body": "{}"},
    )

    # Replace production dependencies with mocks for this test.
    monkeypatch.setattr(
        api_workflow_handoff,
        "get_step_functions_client",
        mock_get_client,
    )

    monkeypatch.setattr(
        api_workflow_handoff,
        "handle_trade_submission",
        mock_handler,
    )

    # Act
    response = lambda_handler(event, context)

    # Assert
    assert response["statusCode"] == 202

    mock_get_client.assert_called_once()

    mock_handler.assert_called_once_with(
        event,
        context,
        step_functions_client=fake_client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=fake_table,
        recovery_token=str(expected_uuid),
        lease_expires_at=150,
        now=100,
        confirmation_clock=mock_clock,
    )

    mock_get_client.assert_called_once_with()

    mock_get_table.assert_called_once_with("trade-submissions")
    mock_uuid.assert_called_once_with()
    mock_clock.assert_called_once_with()


def test_lambda_handler_ignores_untrusted_tenant_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    event = make_event(request_id="REQ-123")

    event["headers"]["x-tenant-id"] = "TENANT-B"

    event["requestContext"]["authorizer"] = {
        "jwt": {
            "claims": {
                "tenant_id": "TENANT-A",
            }
        }
    }

    # Supply the environment configuration expected by lambda_handler.
    monkeypatch.setenv("TRADE_STATE_MACHINE_ARN", STATE_MACHINE_ARN)

    monkeypatch.setenv("TRADE_SUBMISSION_TABLE_NAME", "trade-submissions")

    monkeypatch.setenv("TRADE_SUBMISSION_LEASE_SECONDS", "50")

    # Create fake dependencies
    fake_client = Mock()
    fake_table = Mock()
    mock_get_client = Mock(return_value=fake_client)
    mock_handler = create_autospec(
        api_workflow_handoff.handle_trade_submission,
        return_value={"statusCode": 202, "body": "{}"},
    )

    mock_get_table = Mock(return_value=fake_table)

    monkeypatch.setattr(
        api_workflow_handoff,
        "get_submission_table",
        mock_get_table,
    )

    # Replace production dependencies with mocks for this test.
    monkeypatch.setattr(
        api_workflow_handoff,
        "get_step_functions_client",
        mock_get_client,
    )

    monkeypatch.setattr(
        api_workflow_handoff,
        "handle_trade_submission",
        mock_handler,
    )

    monkeypatch.setattr(
        api_workflow_handoff,
        "build_submission_attempt",
        Mock(
            return_value={
                "recovery_token": "token-A",
                "now": 100,
                "lease_expires_at": 150,
            }
        ),
    )

    mock_clock = Mock(return_value=110)

    monkeypatch.setattr(
        api_workflow_handoff,
        "current_epoch_seconds",
        mock_clock,
    )

    context = SimpleNamespace(aws_request_id="LAMBDA-789")
    # Act
    response = lambda_handler(
        event,
        context,
    )

    # Assert
    assert response["statusCode"] == 202

    mock_get_client.assert_called_once()
    mock_handler.assert_called_once_with(
        event,
        context,
        step_functions_client=fake_client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        table=fake_table,
        recovery_token="token-A",
        lease_expires_at=150,
        now=100,
        confirmation_clock=mock_clock,
    )
    mock_clock.assert_not_called()


@pytest.mark.parametrize(
    "authorizer, extra_headers",
    [
        pytest.param(
            {"jwt": {"claims": {}}},
            {},
            id="missing-tenant",
        ),
        pytest.param(
            "not-a-dictionary",
            {},
            id="invalid-authorizer",
        ),
        pytest.param(
            {"jwt": {"claims": {}}},
            {"x-tenant-id": "TENANT-FROM-HEADER"},
            id="header-cannot-supply-tenant",
        ),
    ],
)
def test_lambda_handler_rejects_untrusted_tenant_identity(
    monkeypatch: pytest.MonkeyPatch,
    authorizer: object,
    extra_headers: dict[str, str],
) -> None:
    event = make_event(request_id="REQ-123")
    event["requestContext"]["authorizer"] = authorizer
    event["headers"].update(extra_headers)

    monkeypatch.setenv("TRADE_STATE_MACHINE_ARN", STATE_MACHINE_ARN)

    monkeypatch.setenv("TRADE_SUBMISSION_TABLE_NAME", "trade-submissions")

    monkeypatch.setenv("TRADE_SUBMISSION_LEASE_SECONDS", "50")

    mock_get_client = Mock()
    mock_handler = Mock()
    mock_get_table = Mock()
    mock_build_attempt = Mock()

    monkeypatch.setattr(
        api_workflow_handoff,
        "get_step_functions_client",
        mock_get_client,
    )
    monkeypatch.setattr(
        api_workflow_handoff,
        "handle_trade_submission",
        mock_handler,
    )

    monkeypatch.setattr(
        api_workflow_handoff,
        "get_submission_table",
        mock_get_table,
    )

    monkeypatch.setattr(
        api_workflow_handoff,
        "build_submission_attempt",
        mock_build_attempt,
    )

    mock_clock = Mock(return_value=110)

    monkeypatch.setattr(
        api_workflow_handoff,
        "current_epoch_seconds",
        mock_clock,
    )

    response = lambda_handler(
        event,
        SimpleNamespace(aws_request_id="LAMBDA-789"),
    )

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {
        "error": "Forbidden.",
        "correlation_id": "REQ-123",
    }
    assert response["headers"]["x-correlation-id"] == "REQ-123"

    mock_get_client.assert_not_called()
    mock_get_table.assert_not_called()
    mock_build_attempt.assert_not_called()
    mock_clock.assert_not_called()
    mock_handler.assert_not_called()


def test_coordinate_initial_trade_start_confirms_success(
    submission_table,
) -> None:

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    expected_record = {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "START_CONFIRMED",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
        "execution_arn": expected_execution_arn,
    }

    client = Mock()
    client.start_execution.return_value = {
        "executionArn": expected_record["execution_arn"],
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = coordinate_initial_trade_start(
        table=submission_table,
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        recovery_token=expected_record["recovery_token"],
        lease_expires_at=expected_record["lease_expires_at"],
        registration_now=100,
        confirmation_clock=lambda: 150,
    )

    stored_record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]

    assert stored_record == expected_record

    assert response == {
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
    }

    client.start_execution.assert_called_once()
    start_args = client.start_execution.call_args.kwargs

    assert start_args["stateMachineArn"] == STATE_MACHINE_ARN
    assert start_args["name"] == build_execution_name("TENANT-A", "SUBMISSION-1001")
    assert json.loads(start_args["input"]) == {
        "trade": trade,
        "idempotency_key": "SUBMISSION-1001",
    }


def test_coordinate_initial_trade_start_confirmed_matching_duplicate_skips_workflow(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    expected_record = {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "START_CONFIRMED",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
        "execution_arn": expected_execution_arn,
    }

    client = Mock()
    client.start_execution.return_value = {
        "executionArn": expected_record["execution_arn"],
        "startDate": "2026-01-01T00:00:00Z",
    }

    mock_clock = Mock(return_value=170)

    coordinate_initial_trade_start(
        table=submission_table,
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        recovery_token=expected_record["recovery_token"],
        lease_expires_at=expected_record["lease_expires_at"],
        registration_now=100,
        confirmation_clock=lambda: 150,
    )

    stored_record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]
    assert stored_record == expected_record
    client.start_execution.assert_called_once()

    client.start_execution.reset_mock()  # clear call history before the duplicate

    duplicate_record = {
        **expected_record,
        "recovery_token": "TOKEN-B",
        "lease_expires_at": 300,
        "registration_now": 160,
        "confirmation_clock": lambda: 170,
    }
    duplicate_response = coordinate_initial_trade_start(
        table=submission_table,
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        recovery_token=duplicate_record["recovery_token"],
        lease_expires_at=duplicate_record["lease_expires_at"],
        registration_now=duplicate_record["registration_now"],
        confirmation_clock=mock_clock,
    )
    post_duplicate_record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]

    assert duplicate_response == {
        "status": "MATCH",
    }
    assert post_duplicate_record == stored_record
    client.start_execution.assert_not_called()
    mock_clock.assert_not_called()


def test_coordinate_initial_trade_start_conflicting_payload_skips_workflow(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    expected_record = {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "START_CONFIRMED",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
        "execution_arn": expected_execution_arn,
    }

    client = Mock()
    client.start_execution.return_value = {
        "executionArn": expected_record["execution_arn"],
        "startDate": "2026-01-01T00:00:00Z",
    }

    mock_clock = Mock(return_value=170)

    coordinate_initial_trade_start(
        table=submission_table,
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        recovery_token=expected_record["recovery_token"],
        lease_expires_at=expected_record["lease_expires_at"],
        registration_now=100,
        confirmation_clock=lambda: 150,
    )

    stored_record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]
    assert stored_record == expected_record
    client.start_execution.assert_called_once()

    client.start_execution.reset_mock()  # clear call history before the duplicate

    conflicting_attempt = {
        **expected_record,
        "trade": normalise_trade(
            {
                "trade_id": "TRD-1001",
                "product": "POWER",
                "volume_mwh": 50,
            }
        ),
        "recovery_token": "TOKEN-B",
        "lease_expires_at": 300,
        "registration_now": 160,
        "confirmation_clock": lambda: 170,
    }
    conflict_response = coordinate_initial_trade_start(
        table=submission_table,
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=conflicting_attempt["trade"],
        recovery_token=conflicting_attempt["recovery_token"],
        lease_expires_at=conflicting_attempt["lease_expires_at"],
        registration_now=conflicting_attempt["registration_now"],
        confirmation_clock=mock_clock,
    )
    post_conflicting_attempt = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]

    assert conflict_response == {
        "status": "CONFLICT",
    }
    assert post_conflicting_attempt == stored_record
    client.start_execution.assert_not_called()
    mock_clock.assert_not_called()


def test_coordinate_initial_trade_start_start_error_leaves_unconfirmed(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    expected_record = {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
    }

    client = Mock()
    error = client.start_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        },
        "StartExecution",
    )

    with pytest.raises(ClientError) as exc_info:
        coordinate_initial_trade_start(
            table=submission_table,
            step_functions_client=client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token=expected_record["recovery_token"],
            lease_expires_at=expected_record["lease_expires_at"],
            registration_now=100,
            confirmation_clock=lambda: 150,
        )

    assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"
    assert exc_info.value is error
    starting_record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]

    assert starting_record == expected_record
    client.start_execution.assert_called_once()


def test_coordinate_initial_trade_start_confirmation_failure(
    submission_table,
) -> None:

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    expected_record = {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "TOKEN-A",
        "lease_expires_at": 200,
    }

    client = Mock()
    client.start_execution.return_value = {
        "executionArn": expected_execution_arn,
        "startDate": "2026-01-01T00:00:00Z",
    }

    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
        "UpdateItem",
    )

    with patch.object(submission_table, "update_item", side_effect=error):
        with pytest.raises(ClientError) as exc_info:
            coordinate_initial_trade_start(
                table=submission_table,
                step_functions_client=client,
                state_machine_arn=STATE_MACHINE_ARN,
                **key,
                trade=trade,
                recovery_token="TOKEN-A",
                lease_expires_at=200,
                registration_now=100,
                confirmation_clock=lambda: 150,
            )

    assert exc_info.value is error
    assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"

    # execution started but DynamoDB not updated — no execution_arn, status still STARTING
    record = submission_table.get_item(
        Key={
            "tenant_id": "TENANT-A",
            "idempotency_key": "SUBMISSION-1001",
        },
        ConsistentRead=True,
    )["Item"]
    assert record == expected_record
    assert "execution_arn" not in record
    client.start_execution.assert_called_once()


def test_describe_trade_execution_running():
    """Returns FOUND and RUNNING"""
    client = Mock()

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    execution_input_json = (
        '{"trade": {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25}, '
        '"idempotency_key": "SUBMISSION-1001"}'
    )

    client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "RUNNING",
        "input": execution_input_json,
    }

    response = describe_trade_execution(
        step_functions_client=client, execution_arn=expected_execution_arn
    )

    assert response == {
        "lookup_status": "FOUND",
        "execution_arn": expected_execution_arn,
        "execution_status": "RUNNING",
        "execution_input_json": execution_input_json,
    }

    client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )


def test_describe_trade_execution_succeeded():
    """Returns FOUND and SUCCEEDED"""
    client = Mock()

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    execution_input_json = (
        '{"trade": {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25}, '
        '"idempotency_key": "SUBMISSION-1001"}'
    )

    client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "SUCCEEDED",
        "input": execution_input_json,
    }

    response = describe_trade_execution(
        step_functions_client=client, execution_arn=expected_execution_arn
    )

    assert response == {
        "lookup_status": "FOUND",
        "execution_arn": expected_execution_arn,
        "execution_status": "SUCCEEDED",
        "execution_input_json": execution_input_json,
    }

    client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )


def test_describe_trade_execution_not_observed():
    """Converts ExecutionDoesNotExist to NOT_OBSERVED"""
    client = Mock()
    client.describe_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ExecutionDoesNotExist",
                "Message": "Execution Does Not Exist",
            }
        },
        "describe_execution",
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    response = describe_trade_execution(
        step_functions_client=client, execution_arn=expected_execution_arn
    )

    assert response == {
        "lookup_status": "NOT_OBSERVED",
        "execution_arn": expected_execution_arn,
    }

    client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )


def test_describe_trade_execution_propagates_access_denied():
    """Original ClientError propagates"""
    client = Mock()
    error = client.describe_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access Denied",
            }
        },
        "describe_execution",
    )

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    with pytest.raises(ClientError) as exc_info:
        describe_trade_execution(
            step_functions_client=client, execution_arn=expected_execution_arn
        )
    assert exc_info.value is error
    client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )


def test_describe_trade_execution_rejects_unknown_status() -> None:
    client = Mock()
    execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
    )
    client.describe_execution.return_value = {
        "executionArn": execution_arn,
        "status": "UNKNOWN",
        "input": "{}",
    }

    with pytest.raises(
        ValueError,
        match=r"^Unhandled execution status: 'UNKNOWN'$",
    ):
        describe_trade_execution(
            step_functions_client=client,
            execution_arn=execution_arn,
        )
    client.describe_execution.assert_called_once_with(
        executionArn=execution_arn,
        includedData="ALL_DATA",
    )


def test_derive_execution_arn_standard_partition() -> None:
    """Derive the correct execution ARN from a valid state-machine ARN."""

    # Arrange
    state_machine_arn = (
        "arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing"
    )

    execution_name = "trade-submit-123"

    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        "execution:trade-processing:trade-submit-123"
    )

    # Act
    actual_execution_arn = derive_execution_arn(
        state_machine_arn=state_machine_arn,
        execution_name=execution_name,
    )

    # Assert
    assert actual_execution_arn == expected_execution_arn


def test_derive_execution_arn_govcloud_partition():
    """Correct GovCloud execution ARN"""

    GOVCLOUD_STATE_MACHINE_ARN = (
        "arn:aws-us-gov:states:us-gov-west-1:123456789012:stateMachine:trade-processing"
    )

    execution_name = "trade-submit-123"

    expected_execution_arn = (
        "arn:aws-us-gov:states:us-gov-west-1:123456789012:"
        "execution:trade-processing:trade-submit-123"
    )

    actual_execution_arn = derive_execution_arn(
        state_machine_arn=GOVCLOUD_STATE_MACHINE_ARN,
        execution_name=execution_name,
    )

    assert actual_execution_arn == expected_execution_arn


@pytest.mark.parametrize(
    "state_machine_arn",
    [
        pytest.param(f"{STATE_MACHINE_ARN}:PROD", id="alias"),
        pytest.param(f"{STATE_MACHINE_ARN}:8", id="version"),
    ],
)
def test_derive_execution_arn_rejects_version_or_alias_arn(
    state_machine_arn: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^Expected an unqualified Step Functions state machine ARN\.$",
    ):
        derive_execution_arn(
            state_machine_arn=state_machine_arn, execution_name="trade-submit-123"
        )


@pytest.mark.parametrize(
    "state_machine_arn",
    [
        pytest.param(
            "arn:aws:states::123456789012:stateMachine:trade-processing",
            id="missing-region",
        ),
        pytest.param(
            "arn:aws:states:eu-west-2:12345678901:stateMachine:trade-processing",
            id="eleven-digit-account",
        ),
        pytest.param(
            "arn:aws:states:eu-west-2:123456789012:"
            "execution:trade-processing:trade-submit-123",
            id="execution-arn",
        ),
        pytest.param(f"{STATE_MACHINE_ARN}/ProcessTrades", id="distributed-map"),
    ],
)
def test_derive_execution_arn_rejects_malformed_or_unsupported_arn(
    state_machine_arn: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^Expected an unqualified Step Functions state machine ARN\.$",
    ):
        derive_execution_arn(
            state_machine_arn=state_machine_arn,
            execution_name="trade-submit-123",
        )


@pytest.mark.parametrize(
    "state_machine_arn",
    [
        pytest.param(
            "arn:aws:states:eu-west-\u0662:123456789012:stateMachine:trade-processing",
            id="unicode-region-digit",
        ),
        pytest.param(
            "arn:aws:states:eu-west-2:\u066123456789012:stateMachine:trade-processing",
            id="unicode-account-digit",
        ),
    ],
)
def test_derive_execution_arn_rejects_unicode_digits_in_arn(
    state_machine_arn: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^Expected an unqualified Step Functions state machine ARN\.$",
    ):
        derive_execution_arn(
            state_machine_arn=state_machine_arn,
            execution_name="trade-submit-123",
        )


@pytest.mark.parametrize(
    "execution_name",
    [
        pytest.param("", id="empty-name"),
        pytest.param("trade-submit:123", id="colon-in-name"),
        pytest.param("x" * 81, id="eighty-one-characters"),
    ],
)
def test_derive_execution_arn_rejects_invalid_execution_name(
    execution_name: str,
) -> None:
    with pytest.raises(ValueError, match=r"^execution_name must be 1–80 characters"):
        derive_execution_arn(
            state_machine_arn=STATE_MACHINE_ARN,
            execution_name=execution_name,
        )


@pytest.mark.parametrize(
    "execution_name",
    [
        pytest.param("trade-submit-\u0661", id="arabic-indic-digit"),
        pytest.param("trade-submit-\u0967", id="devanagari-digit"),
        pytest.param("trade-submit-\uff11", id="fullwidth-digit"),
    ],
)
def test_derive_execution_arn_rejects_unicode_digits(execution_name: str) -> None:
    with pytest.raises(ValueError, match=r"^execution_name must be 1–80 characters"):
        derive_execution_arn(
            state_machine_arn=STATE_MACHINE_ARN,
            execution_name=execution_name,
        )


@pytest.mark.parametrize(
    ("trade_changes", "idempotency_key", "matches"),
    [
        pytest.param({}, "SUBMISSION-1", True, id="same-input"),
        pytest.param(
            {"trade_id": "TRD-1002"}, "SUBMISSION-1", False, id="different-trade-id"
        ),
        pytest.param({"product": "GAS"}, "SUBMISSION-1", False, id="different-product"),
        pytest.param({"volume_mwh": 2}, "SUBMISSION-1", False, id="different-volume"),
        pytest.param(
            {"volume_mwh": True}, "SUBMISSION-1", False, id="python-bool-equals-one"
        ),
        pytest.param({}, "SUBMISSION-2", False, id="different-idempotency-key"),
    ],
)
def test_execution_input_matches_compares_trade_fields(
    trade_changes: dict,
    idempotency_key: str,
    matches: bool,
) -> None:
    expected_trade = {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 1}
    expected_workflow_input = {
        "trade": expected_trade,
        "idempotency_key": "SUBMISSION-1",
    }
    observed_input_json = json.dumps(
        {
            "trade": {**expected_trade, **trade_changes},
            "idempotency_key": idempotency_key,
        }
    )

    assert (
        execution_input_matches(
            observed_input_json=observed_input_json,
            expected_workflow_input=expected_workflow_input,
        )
        is matches
    )


def test_execution_input_matches_rejects_null_trade() -> None:
    assert (
        execution_input_matches(
            observed_input_json='{"trade": null, "idempotency_key": "SUBMISSION-1"}',
            expected_workflow_input={
                "trade": {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 1},
                "idempotency_key": "SUBMISSION-1",
            },
        )
        is False
    )


def test_execution_input_matches_chains_malformed_json_error() -> None:
    with pytest.raises(
        ValueError,
        match=r"^Observed execution input must be a JSON string\.$",
    ) as exc_info:
        execution_input_matches(
            observed_input_json="{",
            expected_workflow_input={},
        )

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_execution_input_matches_requires_json_object() -> None:
    with pytest.raises(
        ValueError,
        match=r"^Observed execution input must be a JSON object\.$",
    ):
        execution_input_matches(
            observed_input_json="[]",
            expected_workflow_input={},
        )


def test_execution_input_matches_identical() -> None:
    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    observed_input = json.dumps(
        build_workflow_input(trade=trade, idempotency_key="SUBMISSION-1001")
    )
    expected_input = {
        "trade": trade,
        "idempotency_key": "SUBMISSION-1001",
    }

    assert (
        execution_input_matches(
            observed_input_json=observed_input, expected_workflow_input=expected_input
        )
        is True
    )


@pytest.mark.parametrize(
    ("observed_input_json", "matches"),
    [
        pytest.param(
            '{"idempotency_key": "SUBMISSION-1001", '
            '"trade": {"volume_mwh": 25, "product": "POWER", "trade_id": "TRD-1001"}}',
            True,
            id="reordered-keys",
        ),
        pytest.param(
            '{"trade": {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25}, '
            '"idempotency_key": "SUBMISSION-1001", "request_id": "REQ-456"}',
            False,
            id="extra-observed-field",
        ),
    ],
)
def test_execution_input_matches_compares_object_keys(
    observed_input_json: str,
    matches: bool,
) -> None:
    expected_workflow_input = {
        "trade": {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25},
        "idempotency_key": "SUBMISSION-1001",
    }

    result = execution_input_matches(
        observed_input_json=observed_input_json,
        expected_workflow_input=expected_workflow_input,
    )

    assert result is matches


def test_execution_input_matches_changed_volume() -> None:
    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    observed_input = json.dumps(
        build_workflow_input(trade=trade, idempotency_key="SUBMISSION-1001")
    )

    changed_volume_mwh = {
        "trade": {**trade, "volume_mwh": 50},
        "idempotency_key": "SUBMISSION-1001",
    }

    assert (
        execution_input_matches(
            observed_input_json=observed_input,
            expected_workflow_input=changed_volume_mwh,
        )
        is False
    )


def test_execution_input_matches_changed_key() -> None:
    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    observed_input = json.dumps(
        build_workflow_input(trade=trade, idempotency_key="SUBMISSION-1001")
    )

    different_idempotency_key = {
        "trade": trade,
        "idempotency_key": "SUBMISSION-2002",
    }

    assert (
        execution_input_matches(
            observed_input_json=observed_input,
            expected_workflow_input=different_idempotency_key,
        )
        is False
    )


@pytest.mark.parametrize(
    "observed_input",
    [
        pytest.param("{trade: {}}", id="unquoted-key"),
        pytest.param('{"trade": {},}', id="trailing-comma"),
        pytest.param(
            '{"trade": {} "idempotency_key": "SUBMISSION-1001"}',
            id="missing-comma",
        ),
        pytest.param(
            '{"idempotency_key": "SUBMISSION-1001}',
            id="unterminated-string",
        ),
    ],
)
def test_execution_input_matches_invalid_json(observed_input: str) -> None:
    with pytest.raises(
        ValueError,
        match=r"^Observed execution input must be a JSON string\.$",
    ) as exc_info:
        execution_input_matches(
            observed_input_json=observed_input,
            expected_workflow_input={},
        )

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize(
    "input_fields",
    [
        pytest.param({}, id="missing-input"),
        pytest.param({"input": None}, id="null-input"),
        pytest.param({"input": ""}, id="empty-input"),
        pytest.param({"input": " \t\n"}, id="whitespace-only-input"),
        pytest.param({"input": 123}, id="non-string-input"),
    ],
)
def test_describe_trade_execution_rejects_missing_or_blank_input(
    input_fields: dict[str, str | None],
) -> None:
    execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
    )
    client = Mock()
    client.describe_execution.return_value = {
        "executionArn": execution_arn,
        "status": "RUNNING",
        **input_fields,
    }

    with pytest.raises(
        ValueError,
        match=r"^Step Functions execution input is missing or blank\.$",
    ):
        describe_trade_execution(
            step_functions_client=client,
            execution_arn=execution_arn,
        )


def test_inspect_trade_execution_for_recovery_verifies_matching_input() -> None:

    tenant_id = "TENANT-A"
    idempotency_key = "SUBMISSION-1001"
    trade = {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25}
    execution_arn = derive_execution_arn(
        state_machine_arn=STATE_MACHINE_ARN,
        execution_name=build_execution_name(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        ),
    )

    client = Mock()
    client.describe_execution.return_value = {
        "executionArn": execution_arn,
        "status": "RUNNING",
        "input": json.dumps({"trade": trade, "idempotency_key": idempotency_key}),
    }

    response = inspect_trade_execution_for_recovery(
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade={
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        },
    )
    assert response == {
        "reconciliation_status": "VERIFIED",
        "execution_arn": execution_arn,
        "execution_status": "RUNNING",
    }


def test_inspect_trade_execution_for_recovery_reports__mismatch() -> None:

    tenant_id = "TENANT-A"
    idempotency_key = "SUBMISSION-1001"
    trade = {"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25}
    execution_arn = derive_execution_arn(
        state_machine_arn=STATE_MACHINE_ARN,
        execution_name=build_execution_name(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        ),
    )

    client = Mock()
    client.describe_execution.return_value = {
        "executionArn": execution_arn,
        "status": "RUNNING",
        "input": json.dumps(
            {
                "trade": {**trade, "volume_mwh": 50},
                "idempotency_key": idempotency_key,
            }
        ),
    }

    response = inspect_trade_execution_for_recovery(
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        trade={
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        },
    )
    assert response == {
        "reconciliation_status": "INPUT_MISMATCH",
        "execution_arn": execution_arn,
    }


def test_inspect_trade_execution_for_recovery_is_inconclusive_if_not_observed() -> None:
    tenant_id = "TENANT-A"
    idempotency_key = "SUBMISSION-1001"
    execution_arn = derive_execution_arn(
        state_machine_arn=STATE_MACHINE_ARN,
        execution_name=build_execution_name(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        ),
    )

    client = Mock()
    client.describe_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ExecutionDoesNotExist",
                "Message": "Execution does not exist",
            }
        },
        "DescribeExecution",
    )

    response = inspect_trade_execution_for_recovery(
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        trade={"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25},
    )

    assert response == {
        "reconciliation_status": "INCONCLUSIVE",
        "execution_arn": execution_arn,
    }
    client.describe_execution.assert_called_once_with(
        executionArn=execution_arn,
        includedData="ALL_DATA",
    )


def test_confirm_verified_trade_recovery_is_verified():
    table = Mock()

    execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
    )
    response = confirm_verified_trade_recovery(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="token-A",
        now=100,
        reconciliation_result={
            "reconciliation_status": "VERIFIED",
            "execution_arn": execution_arn,
            "execution_status": "RUNNING",
        },
    )

    assert response == "START_CONFIRMED"
    table.update_item.assert_called_once()
    update_request = table.update_item.call_args.kwargs
    assert update_request["Key"] == {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }
    values = update_request["ExpressionAttributeValues"]
    assert values[":arn"] == execution_arn
    assert values[":status"] == "START_CONFIRMED"
    assert values[":recovery_token"] == "token-A"
    assert values[":now"] == 100


def test_confirm_verified_trade_recovery_input_mismatched():
    table = Mock()

    execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
    )
    response = confirm_verified_trade_recovery(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="token-A",
        now=100,
        reconciliation_result={
            "reconciliation_status": "INPUT_MISMATCH",
            "execution_arn": execution_arn,
        },
    )

    assert response == "INPUT_MISMATCH"
    assert table.mock_calls == []


def test_confirm_verified_trade_recovery_inconclusive():
    table = Mock()

    execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
    )
    response = confirm_verified_trade_recovery(
        table=table,
        tenant_id="TENANT-A",
        idempotency_key="SUBMISSION-1001",
        recovery_token="token-A",
        now=100,
        reconciliation_result={
            "reconciliation_status": "INCONCLUSIVE",
            "execution_arn": execution_arn,
        },
    )

    assert response == "INCONCLUSIVE"
    assert table.mock_calls == []


def test_coordinate_expired_trade_recovery_success(submission_table) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    starting_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    step_functions_client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "RUNNING",
        "input": json.dumps(
            {"trade": trade, "idempotency_key": key["idempotency_key"]}
        ),
    }

    response = coordinate_expired_trade_recovery(
        table=submission_table,
        step_functions_client=step_functions_client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        new_recovery_token="token-B",
        new_lease_expires_at=150,
        claim_now=100,
        confirmation_clock=lambda: 110,
    )

    assert response == "START_CONFIRMED"
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert stored_record == {
        **starting_record,
        "status": "START_CONFIRMED",
        "recovery_token": "token-B",
        "lease_expires_at": 150,
        "execution_arn": expected_execution_arn,
    }
    assert starting_record != stored_record
    step_functions_client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_already_confirmed(submission_table) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    starting_record = {
        **key,
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)
    step_functions_client = Mock()

    response = coordinate_expired_trade_recovery(
        table=submission_table,
        step_functions_client=step_functions_client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade=trade,
        new_recovery_token="token-B",
        new_lease_expires_at=150,
        claim_now=100,
        confirmation_clock=lambda: 110,
    )

    assert response == "ALREADY_CONFIRMED"
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert stored_record == {
        **starting_record,
        "status": "START_CONFIRMED",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "execution_arn": expected_execution_arn,
    }
    assert starting_record == stored_record
    step_functions_client.describe_execution.assert_not_called()
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_payload_fingerprint_conflict(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    starting_record = {
        **key,
        "status": "STARTING",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)
    step_functions_client = Mock()

    response = coordinate_expired_trade_recovery(
        table=submission_table,
        step_functions_client=step_functions_client,
        state_machine_arn=STATE_MACHINE_ARN,
        **key,
        trade={**trade, "volume_mwh": 50},
        new_recovery_token="token-B",
        new_lease_expires_at=150,
        claim_now=100,
        confirmation_clock=lambda: 110,
    )

    assert response == "CONFLICT"
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert starting_record == stored_record
    step_functions_client.describe_execution.assert_not_called()
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_not_claimed(submission_table) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    starting_record = {
        **key,
        "status": "STARTING",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-A",
        "lease_expires_at": 110,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)
    step_functions_client = Mock()
    step_functions_client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "RUNNING",
        "input": json.dumps(
            {"trade": trade, "idempotency_key": key["idempotency_key"]}
        ),
    }
    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_expired_trade_recovery(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            new_recovery_token="token-B",
            new_lease_expires_at=150,
            claim_now=100,
            confirmation_clock=lambda: 110,
        )

    update_item.assert_called_once()
    assert response == "NOT_CLAIMED"
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert starting_record == stored_record
    step_functions_client.describe_execution.assert_not_called()
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_inconclusive(submission_table) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    starting_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    step_functions_client.describe_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ExecutionDoesNotExist",
                "Message": "Execution Does Not Exist",
            }
        },
        "describe_execution",
    )
    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_expired_trade_recovery(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            new_recovery_token="token-B",
            new_lease_expires_at=150,
            claim_now=100,
            confirmation_clock=lambda: 110,
        )

    assert response == "INCONCLUSIVE"
    update_item.assert_called_once()
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert stored_record == {
        **starting_record,
        "status": "STARTING",
        "recovery_token": "token-B",
        "lease_expires_at": 150,
        #        "execution_arn": expected_execution_arn,
    }
    assert starting_record != stored_record
    step_functions_client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_execution_mismatch(submission_table) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    starting_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    step_functions_client = Mock()
    step_functions_client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "RUNNING",
        "input": json.dumps(
            {
                "trade": {**trade, "volume_mwh": 50},
                "idempotency_key": key["idempotency_key"],
            }
        ),
    }
    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_expired_trade_recovery(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            new_recovery_token="token-B",
            new_lease_expires_at=150,
            claim_now=100,
            confirmation_clock=lambda: 110,
        )

    assert response == "INPUT_MISMATCH"
    update_item.assert_called_once()
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert stored_record == {
        **starting_record,
        "status": "STARTING",
        "recovery_token": "token-B",
        "lease_expires_at": 150,
        #        "execution_arn": expected_execution_arn,
    }
    assert starting_record != stored_record
    step_functions_client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_expired_trade_recovery_confirmed_payload_conflict(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }

    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    starting_record = {
        **key,
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)
    step_functions_client = Mock()

    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_expired_trade_recovery(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade={**trade, "volume_mwh": 50},
            new_recovery_token="token-B",
            new_lease_expires_at=150,
            claim_now=100,
            confirmation_clock=lambda: 110,
        )
    assert response == "CONFLICT"
    update_item.assert_not_called()
    stored_record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert starting_record == stored_record
    step_functions_client.describe_execution.assert_not_called()
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_trade_submission_returned_starts_new_trade(
    submission_table,
) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    step_functions_client.start_execution.return_value = {
        "executionArn": expected_execution_arn,
        "startDate": "2026-01-01T00:00:00Z",
    }

    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_trade_submission(
            table=table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token="token-A",
            lease_expires_at=150,
            confirmation_clock=lambda: 120,
            now=80,
        )

    assert response == {
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
    }

    update_item.assert_called_once()
    record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record["status"] == "START_CONFIRMED"
    assert record["execution_arn"] == expected_execution_arn
    step_functions_client.start_execution.assert_called_once()
    step_functions_client.describe_execution.assert_not_called()


def test_coordinate_trade_submission_already_confirmed(
    submission_table,
) -> None:
    table = submission_table

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    starting_record = {
        **key,
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_trade_submission(
            table=table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token="token-B",
            lease_expires_at=150,
            confirmation_clock=lambda: 120,
            now=100,
        )

    assert response == {"status": "ALREADY_CONFIRMED"}

    update_item.assert_not_called()
    record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record == starting_record
    step_functions_client.start_execution.assert_not_called()
    step_functions_client.describe_execution.assert_not_called()


def test_coordinate_trade_submission_returned_recover_claim(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    step_functions_client.describe_execution.return_value = {
        "executionArn": expected_execution_arn,
        "status": "RUNNING",
        "input": json.dumps(
            {
                "trade": trade,
                "idempotency_key": key["idempotency_key"],
            }
        ),
    }
    starting_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_trade_submission(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token="token-B",
            lease_expires_at=150,
            confirmation_clock=lambda: 120,
            now=100,
        )

    assert response == {"status": "START_CONFIRMED"}

    assert update_item.call_count == 2
    record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record == {
        **starting_record,
        "status": "START_CONFIRMED",
        "execution_arn": expected_execution_arn,
        "recovery_token": "token-B",
        "lease_expires_at": 150,
    }
    step_functions_client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )
    step_functions_client.start_execution.assert_not_called()


def test_coordinate_trade_submission_execution_not_observed(
    submission_table,
) -> None:
    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    }
    execution_name = build_execution_name(**key)
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )
    step_functions_client = Mock()
    step_functions_client.describe_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ExecutionDoesNotExist",
                "Message": "Execution Does Not Exist",
            }
        },
        "describe_execution",
    )
    starting_record = {
        **key,
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 90,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
    }
    submission_table.put_item(Item=starting_record)

    with patch.object(
        submission_table, "update_item", wraps=submission_table.update_item
    ) as update_item:
        response = coordinate_trade_submission(
            table=submission_table,
            step_functions_client=step_functions_client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token="token-B",
            lease_expires_at=150,
            confirmation_clock=lambda: 120,
            now=100,
        )

    assert response == {"status": "INCONCLUSIVE"}

    assert update_item.call_count == 1
    record = submission_table.get_item(Key=key, ConsistentRead=True)["Item"]
    assert record == {
        **starting_record,
        "status": "STARTING",
        "recovery_token": "token-B",
        "lease_expires_at": 150,
    }
    step_functions_client.describe_execution.assert_called_once_with(
        executionArn=expected_execution_arn,
        includedData="ALL_DATA",
    )
    step_functions_client.start_execution.assert_not_called()


def test_map_trade_submission_outcome_start_confirmed() -> None:
    outcome = {
        "status": "START_CONFIRMED",
        "execution_arn": (
            "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
        ),
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 202
    body = json.loads(response["body"])
    assert body["status"] == "accepted_for_processing"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_map_trade_submission_outcome_conflict() -> None:
    outcome = {
        "status": "CONFLICT",
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 409
    body = json.loads(response["body"])
    assert body["error"] == "idempotency_key_conflict"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_map_trade_submission_outcome_already_confirmed() -> None:
    outcome = {
        "status": "ALREADY_CONFIRMED",
        "execution_arn": (
            "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:test-run"
        ),
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "already_accepted"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_map_trade_submission_outcome_not_claimed() -> None:
    outcome = {
        "status": "NOT_CLAIMED",
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 202
    body = json.loads(response["body"])
    assert body["status"] == "confirmation_pending"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_map_trade_submission_outcome_inconclusive() -> None:
    outcome = {
        "status": "INCONCLUSIVE",
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"] == "start_status_unknown"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_map_trade_submission_outcome_input_mismatch() -> None:
    outcome = {
        "status": "INPUT_MISMATCH",
    }
    response = map_trade_submission_outcome(
        outcome=outcome, operation_id="trade-submit-abc123", correlation_id="CORR-123"
    )

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert body["error"] == "submission_verification_failed"
    assert body["operation_id"] == "trade-submit-abc123"
    assert body["correlation_id"] == "CORR-123"
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(None, id="null-input"),
        pytest.param("", id="empty-input"),
        pytest.param("INVALID", id="whitespace-only-input"),
        pytest.param(123, id="non-string-input"),
    ],
)
def test_map_trade_submission_outcome_unknown_status(status: str) -> None:
    outcome = {
        "status": status,
    }

    with pytest.raises(
        ValueError, match=f"Unexpected trade submission outcome: {outcome['status']!r}."
    ):
        map_trade_submission_outcome(
            outcome=outcome,
            operation_id="trade-submit-abc123",
            correlation_id="CORR-123",
        )


def test_coordinate_trade_submission_routes_match_to_recovery(submission_table) -> None:
    clock = Mock(return_value=110)

    common = {
        "table": submission_table,
        "step_functions_client": Mock(),
        "state_machine_arn": STATE_MACHINE_ARN,
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
        "trade": {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        },
    }

    with (
        patch(
            "api_workflow_handoff.coordinate_initial_trade_start",
            autospec=True,
            return_value={"status": "MATCH"},
        ) as initial_start,
        patch(
            "api_workflow_handoff.coordinate_expired_trade_recovery",
            autospec=True,
            return_value="START_CONFIRMED",
        ) as recover,
    ):
        response = coordinate_trade_submission(
            **common,
            recovery_token="token-B",
            lease_expires_at=130,
            now=100,
            confirmation_clock=clock,
        )

    initial_start.assert_called_once()
    recover.assert_called_once_with(
        **common,
        new_recovery_token="token-B",
        new_lease_expires_at=130,
        claim_now=100,
        confirmation_clock=clock,
    )
    assert response == {"status": "START_CONFIRMED"}


@pytest.mark.parametrize(
    ("outcome", "expected_status_code", "body_field", "expected_value"),
    [
        pytest.param(
            {
                "status": "START_CONFIRMED",
                "execution_arn": (
                    "arn:aws:states:eu-west-2:123456789012:"
                    "execution:trade-processing:test-run"
                ),
            },
            202,
            "status",
            "accepted_for_processing",
            id="start-confirmed",
        ),
        pytest.param(
            {"status": "INPUT_MISMATCH"},
            500,
            "error",
            "submission_verification_failed",
            id="input-mismatch",
        ),
    ],
)
def test_handle_trade_submission_maps_coordinator_outcome(
    outcome: dict[str, str],
    expected_status_code: int,
    body_field: str,
    expected_value: str,
) -> None:
    handler_kwargs = {
        "table": Mock(),
        "step_functions_client": Mock(),
        "state_machine_arn": STATE_MACHINE_ARN,
        "tenant_id": "TENANT-A",
        "recovery_token": "token-A",
        "lease_expires_at": 150,
        "now": 100,
        "confirmation_clock": lambda: 110,
    }

    with patch(
        "api_workflow_handoff.coordinate_trade_submission",
        autospec=True,
        return_value=outcome,
    ) as coordinate:
        response = handle_trade_submission(make_event(), None, **handler_kwargs)

    coordinate.assert_called_once_with(
        **handler_kwargs,
        idempotency_key="submission-001",
        trade={"trade_id": "TRD-1001", "product": "POWER", "volume_mwh": 25},
    )
    handler_kwargs["step_functions_client"].start_execution.assert_not_called()
    assert handler_kwargs["step_functions_client"].mock_calls == []
    assert handler_kwargs["table"].mock_calls == []
    assert response["statusCode"] == expected_status_code
    assert json.loads(response["body"])[body_field] == expected_value
    headers = response["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-correlation-id"] == "CORR-123"


def test_get_submission_table_reuses_cached_resource() -> None:
    table_name = "trade-submissions"
    fake_dynamodb = Mock()
    fake_table = Mock()
    fake_dynamodb.Table.return_value = fake_table

    get_submission_table.cache_clear()
    try:
        with patch(
            "api_workflow_handoff.boto3.resource",
            return_value=fake_dynamodb,
            autospec=True,
        ) as mock_resource:
            first_table = get_submission_table(table_name)
            second_table = get_submission_table(table_name)

            fake_dynamodb.Table.assert_called_once_with(table_name)
            mock_resource.assert_called_once_with("dynamodb")
            assert first_table is fake_table
            assert second_table is first_table
    finally:
        get_submission_table.cache_clear()


def test_initial_trade_start_rejects_confirmation_after_lease_expiry(
    submission_table,
) -> None:
    client = Mock()
    clock = Mock(return_value=110)

    execution_name = build_execution_name(
        "TENANT-A",
        "SUBMISSION-1001",
    )
    expected_execution_arn = (
        "arn:aws:states:eu-west-2:123456789012:"
        f"execution:trade-processing:{execution_name}"
    )

    def simulated_workflow_start(**kwargs):
        clock.assert_not_called()
        clock.return_value = 165

        return {
            "executionArn": expected_execution_arn,
            "startDate": "2026-01-01T00:00:00Z",
        }

    client.start_execution.side_effect = simulated_workflow_start

    key = {
        "tenant_id": "TENANT-A",
        "idempotency_key": "SUBMISSION-1001",
    }

    trade = normalise_trade(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        }
    )

    with pytest.raises(
        ClientError,
        match="ConditionalCheckFailedException",
    ) as exc_info:
        coordinate_initial_trade_start(
            table=submission_table,
            step_functions_client=client,
            state_machine_arn=STATE_MACHINE_ARN,
            **key,
            trade=trade,
            recovery_token="token-A",
            lease_expires_at=150,
            registration_now=100,
            confirmation_clock=clock,
        )

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    stored_record = submission_table.get_item(
        Key=key,
        ConsistentRead=True,
    )["Item"]

    assert stored_record == {
        **key,
        "payload_fingerprint": fingerprint_normalised_trade(trade),
        "status": "STARTING",
        "recovery_token": "token-A",
        "lease_expires_at": 150,
    }

    client.start_execution.assert_called_once()
    clock.assert_called_once_with()
    start_args = client.start_execution.call_args.kwargs

    assert start_args["stateMachineArn"] == STATE_MACHINE_ARN
    assert start_args["name"] == build_execution_name("TENANT-A", "SUBMISSION-1001")
    assert json.loads(start_args["input"]) == {
        "trade": trade,
        "idempotency_key": "SUBMISSION-1001",
    }


def test_build_submission_attempt_generates_fresh_tokens_and_lease() -> None:
    clock = Mock(side_effect=[100, 120])

    first_uuid = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

    second_uuid = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")
    with patch(
        "api_workflow_handoff.uuid.uuid4",
        side_effect=[first_uuid, second_uuid],
        autospec=True,
    ) as mock_uuid:
        first_attempt = build_submission_attempt(
            lease_duration_seconds=50,
            clock=clock,
        )

        second_attempt = build_submission_attempt(
            lease_duration_seconds=50,
            clock=clock,
        )

        assert mock_uuid.call_count == 2
        assert clock.call_count == 2

        assert first_attempt == {
            "recovery_token": str(first_uuid),
            "now": 100,
            "lease_expires_at": 150,
        }

        assert second_attempt == {
            "recovery_token": str(second_uuid),
            "now": 120,
            "lease_expires_at": 170,
        }


@pytest.mark.parametrize(
    ("lease_duration_seconds", "expected_message"),
    [
        (0, "Lease duration must be greater than 0"),
        (-1, "Lease duration must be greater than 0"),
        (True, "Lease duration must be an integer"),
        (1.5, "Lease duration must be an integer"),
    ],
)
def test_build_submission_attempt_rejects_invalid_lease_duration(
    lease_duration_seconds,
    expected_message: str,
) -> None:
    clock = Mock(return_value=100)

    with patch(
        "api_workflow_handoff.uuid.uuid4",
        autospec=True,
    ) as mock_uuid:
        with pytest.raises(ValueError, match=rf"^{re.escape(expected_message)}$"):
            build_submission_attempt(
                lease_duration_seconds=lease_duration_seconds,
                clock=clock,
            )

    assert mock_uuid.call_count == 0
    clock.assert_not_called()
