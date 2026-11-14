from __future__ import annotations

import base64
import json
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from api_workflow_handoff import (
    build_execution_name,
    handle_trade_submission,
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


def test_valid_request_starts_workflow_with_normalised_input() -> None:
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


def test_valid_request_returns_truthful_accepted_response() -> None:
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
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 202
    assert body["status"] == "accepted_for_processing"
    assert "processed successfully" not in response["body"].lower()


def test_invalid_json_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body="not-json"),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_non_object_json_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='["TRD-1001"]'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_base64_encoded_json_body_is_decoded_before_workflow_start() -> None:
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
    )

    assert response["statusCode"] == 202


def test_missing_trade_field_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='{"product":"POWER","volume_mwh":25}'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert response["statusCode"] == 400
    assert "trade_id" in response["body"]
    client.start_execution.assert_not_called()


def test_external_fields_are_not_passed_to_workflow() -> None:
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
    )

    assert response["statusCode"] == 202
    workflow_input = json.loads(client.start_execution.call_args.kwargs["input"])
    assert "unexpected_external_field" not in workflow_input["trade"]


def test_missing_idempotency_key_returns_400() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(headers={"X-Correlation-Id": "CORR-123"}),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_retryable_step_functions_failure_returns_503_not_202() -> None:
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
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 503
    assert body["error"] == "Workflow could not be started."
    assert "Rate exceeded" not in response["body"]


def test_duplicate_execution_name_returns_client_safe_409() -> None:
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
    )

    assert response["statusCode"] == 409
    assert "Execution already exists" not in response["body"]


def test_permission_failure_returns_500_without_leaking_aws_details() -> None:
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
    )

    assert response["statusCode"] == 500
    assert "role arn and account details" not in response["body"]


def test_connection_failure_returns_503_without_leaking_endpoint() -> None:
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
    )

    assert response["statusCode"] == 503
    assert "states.example.internal" not in response["body"]


def test_unexpected_start_failure_returns_500_without_leaking_details() -> None:
    client = Mock()
    client.start_execution.side_effect = RuntimeError("sensitive internal detail")

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert response["statusCode"] == 500
    assert "sensitive internal detail" not in response["body"]


def test_missing_state_machine_configuration_returns_500_without_sdk_call() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn="",
        tenant_id="TENANT-A",
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


def test_retry_with_same_idempotency_key_has_stable_workflow_input() -> None:
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

    handle_trade_submission(
        make_event(
            body=request_body,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-788"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    handle_trade_submission(
        make_event(
            body=request_body,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-789",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert client.start_execution.call_count == 2

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs
    second_call = calls[1].kwargs

    expected_execution_name = build_execution_name("TENANT-A", "SUBMISSION-1001")

    assert first_call["name"] == expected_execution_name
    assert first_call["name"] == second_call["name"]
    assert first_call["input"] == second_call["input"]

    assert first_call["stateMachineArn"] == STATE_MACHINE_ARN
    assert second_call["stateMachineArn"] == STATE_MACHINE_ARN

    workflow_input = json.loads(first_call["input"])

    assert workflow_input["trade"]["trade_id"] == "TRD-1001"


def test_changed_volume_same_key_changes_workflow_input() -> None:
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

    handle_trade_submission(
        make_event(
            body=request_body_a,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-788"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    request_body_b = json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 50,
        }
    )

    handle_trade_submission(
        make_event(
            body=request_body_b,
            headers={"Idempotency-Key": "SUBMISSION-1001"},
            request_id="API-788",
        ),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
        tenant_id="TENANT-A",
    )

    assert client.start_execution.call_count == 2

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs
    second_call = calls[1].kwargs

    expected_execution_name = build_execution_name("TENANT-A", "SUBMISSION-1001")

    assert first_call["name"] == expected_execution_name
    assert first_call["name"] == second_call["name"]
    assert first_call["input"] != second_call["input"]

    workflow_a_input = json.loads(first_call["input"])
    assert workflow_a_input["trade"]["volume_mwh"] == 25

    workflow_b_input = json.loads(second_call["input"])
    assert workflow_b_input["trade"]["volume_mwh"] == 50

    assert (
        workflow_a_input["trade"]["trade_id"] == workflow_b_input["trade"]["trade_id"]
    )
    assert workflow_a_input["trade"]["product"] == workflow_b_input["trade"]["product"]


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
