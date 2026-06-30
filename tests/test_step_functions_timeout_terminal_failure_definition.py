import json
from pathlib import Path



STATE_MACHINE_PATH = Path(
    "step-functions/persistence-task-timeout-terminal-failure.asl.json"
)


def load_state_machine() -> dict:
    return json.loads(STATE_MACHINE_PATH.read_text())


def test_lesson33_state_machine_loads_as_json():
    state_machine = load_state_machine()

    assert state_machine["StartAt"] == "PersistTradeResult"
    assert "States" in state_machine


def test_persistence_task_invokes_lambda_with_timeout_retry_and_catch():
    state_machine = load_state_machine()

    task = state_machine["States"]["PersistTradeResult"]

    assert task["Type"] == "Task"
    assert task["Resource"] == "arn:aws:states:::lambda:invoke"
    assert task["TimeoutSeconds"] == 30
    assert "Retry" in task
    assert "Catch" in task


def test_persistence_task_retry_is_bounded():
    state_machine = load_state_machine()

    retry_block = state_machine["States"]["PersistTradeResult"]["Retry"][0]

    assert retry_block["MaxAttempts"] == 3
    assert retry_block["IntervalSeconds"] == 2
    assert retry_block["BackoffRate"] == 2.0


def test_persistence_task_catch_routes_to_reconciliation():
    state_machine = load_state_machine()

    catch_block = state_machine["States"]["PersistTradeResult"]["Catch"][0]

    assert catch_block["ErrorEquals"] == ["States.ALL"]
    assert catch_block["ResultPath"] == "$.persistence_error"
    assert catch_block["Next"] == "RouteToManualReconciliation"


def test_reconciliation_routes_to_terminal_fail_state():
    state_machine = load_state_machine()
    states = state_machine["States"]

    reconciliation_state = states["RouteToManualReconciliation"]
    failed_state = states["PersistenceFailed"]

    assert reconciliation_state["Type"] == "Pass"
    assert reconciliation_state["Next"] == "PersistenceFailed"
    assert failed_state["Type"] == "Fail"


def test_step_functions_does_not_call_s3_or_dynamodb_directly():
    state_machine = load_state_machine()
    states = state_machine["States"]

    resources = [
        state.get("Resource", "")
        for state in states.values()
        if isinstance(state, dict)
    ]

    assert all("s3:" not in resource for resource in resources)
    assert all("dynamodb:" not in resource for resource in resources)


def test_success_path_routes_to_succeed_state():
    state_machine = load_state_machine()
    states = state_machine["States"]

    persistence_task_state = states["PersistTradeResult"]
    next_state_name = persistence_task_state["Next"]
    next_state = states[next_state_name]

    assert next_state_name == "PersistenceSucceeded"
    assert next_state["Type"] == "Succeed"


def test_persistence_task_passes_input_and_preserves_result():
    state_machine = load_state_machine()
    task = state_machine["States"]["PersistTradeResult"]

    assert task["Parameters"]["Payload.$"] == "$"
    assert task["ResultPath"] == "$.persistence_result"


def test_persistence_task_retries_expected_transient_errors():
    state_machine = load_state_machine()
    task = state_machine["States"]["PersistTradeResult"]

    retry_block = task["Retry"][0]
    assert set(retry_block["ErrorEquals"]) == {
        "Lambda.TooManyRequestsException",
        "Lambda.ServiceException",
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException",
        "States.Timeout",
    }


def test_persistence_task_uses_placeholder_lambda_function_name():
    state_machine = load_state_machine()
    task = state_machine["States"]["PersistTradeResult"]

    function_name = task["Parameters"]["FunctionName"]

    assert "${AWS_REGION}" in function_name
    assert "${AWS_ACCOUNT_ID}" in function_name
    assert "${PERSISTENCE_FUNCTION_NAME}" in function_name
    assert "${PERSISTENCE_FUNCTION_ALIAS}" in function_name
