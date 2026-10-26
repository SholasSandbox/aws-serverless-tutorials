from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

from botocore.exceptions import ClientError, EndpointConnectionError

from api_workflow_handoff import (
    build_execution_name,
    handle_trade_submission,
)

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
    )

    assert response["statusCode"] == 202

    call = client.start_execution.call_args.kwargs
    assert call["stateMachineArn"] == STATE_MACHINE_ARN
    assert call["name"] == build_execution_name("submission-001")
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
    )

    assert response["statusCode"] == 202


def test_missing_trade_field_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='{"product":"POWER","volume_mwh":25}'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
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
    )

    assert response["statusCode"] == 500
    client.start_execution.assert_not_called()


def test_execution_name_is_stable_for_same_idempotency_key() -> None:
    assert build_execution_name("submission-001") == build_execution_name(
        "submission-001"
    )
    assert build_execution_name("submission-001") != build_execution_name(
        "submission-002"
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
    )

    assert client.start_execution.call_count == 2

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs
    second_call = calls[1].kwargs

    expected_execution_name = build_execution_name("SUBMISSION-1001")

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
    )

    assert client.start_execution.call_count == 2

    calls = client.start_execution.call_args_list

    first_call = calls[0].kwargs
    second_call = calls[1].kwargs

    expected_execution_name = build_execution_name("SUBMISSION-1001")

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
