import json
from pathlib import Path


STATE_FILE = (
    Path(__file__).resolve().parents[1]
    / "step-functions"
    / "persistence-task-state-with-retry-catch.json"
)


def load_state_definition():
    return json.loads(STATE_FILE.read_text())


def get_persist_trade_result_task():
    state_definition = load_state_definition()
    return state_definition["PersistTradeResult"]


def test_persistence_task_retry_contract_retries_transient_lambda_errors():
    task = get_persist_trade_result_task()

    retry_block = task["Retry"][0]
    retry_errors = retry_block["ErrorEquals"]

    expected_retry_errors = [
        "Lambda.ServiceException",
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException",
        "Lambda.TooManyRequestsException",
        "States.Timeout",
    ]

    for expected_error in expected_retry_errors:
        assert expected_error in retry_errors, f"Missing retry error: {expected_error}"


def test_persistence_task_retry_contract_uses_bounded_backoff():
    task = get_persist_trade_result_task()

    # Reuse the same Retry block.
    retry_block = task["Retry"][0]

    # Assert exact values here because these are intentional retry policy choices.
    assert retry_block["IntervalSeconds"] == 2
    assert retry_block["MaxAttempts"] == 3
    assert retry_block["BackoffRate"] == 2.0


def test_persistence_task_catch_contract_stores_failure_under_persistence_error():
    task = get_persist_trade_result_task()

    catch_block = task["Catch"][0]

    assert catch_block["ErrorEquals"] == ["States.ALL"]
    assert catch_block["ResultPath"] == "$.persistence_error"


def test_persistence_task_catch_contract_routes_to_persistence_failed_state():
    task = get_persist_trade_result_task()

    catch_block = task["Catch"][0]

    assert catch_block["Next"] == "PersistenceFailed"


def test_persistence_failed_state_is_terminal_fail_state():
    definition = load_state_definition()

    failed_state = definition["PersistenceFailed"]

    assert failed_state["Type"] == "Fail"
    assert failed_state["Error"] == "PersistenceTaskFailed"
    assert failed_state["Cause"] == "Trade persistence task failed after retries"
