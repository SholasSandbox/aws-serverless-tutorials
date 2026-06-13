import json
from pathlib import Path


TASK_STATE_MACHINE_PATH = Path("step-functions/trade-validation-with-task.asl.json")
RETRY_CATCH_STATE_MACHINE_PATH = Path(
    "step-functions/trade-validation-with-retry-catch.asl.json"
)
STATE_MACHINE_PATH = Path("step-functions/trade-validation-basic.asl.json")
VALID_TRADE_PATH = Path("step-functions/sample-valid-trade.json")
REJECTED_TRADE_PATH = Path("step-functions/sample-rejected-trade.json")
INVALID_WORKFLOW_INPUT_PATH = Path("step-functions/sample-invalid-workflow-input.json")


def load_json(path: Path) -> dict:
    with path.open() as file:
        return json.load(file)


def test_trade_validation_state_machine_loads_as_json():
    state_machine = load_json(STATE_MACHINE_PATH)

    assert state_machine["StartAt"] == "ReceiveTrade"
    assert "States" in state_machine


def test_trade_validation_state_machine_start_state_exists():
    state_machine = load_json(STATE_MACHINE_PATH)

    start_state = state_machine["StartAt"]
    states = state_machine["States"]

    assert start_state in states


def test_trade_validation_with_task_state_machine_loads_as_json():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    assert state_machine["StartAt"] == "ReceiveTrade"
    assert "States" in state_machine


def test_trade_validation_choice_targets_exist():
    state_machine = load_json(STATE_MACHINE_PATH)
    states = state_machine["States"]

    choice_state = states["IsTradeValid"]

    for choice in choice_state["Choices"]:
        assert choice["Next"] in states

    assert choice_state["Default"] in states


def route_trade(state_machine: dict, trade: dict) -> str:
    states = state_machine["States"]
    choice_state = states["IsTradeValid"]

    for choice in choice_state["Choices"]:
        variable = choice["Variable"]

        if variable != "$.is_valid":
            continue

        if trade.get("is_valid") is choice["BooleanEquals"]:
            return choice["Next"]

    return choice_state["Default"]


def test_valid_trade_routes_to_accepted_trade():
    state_machine = load_json(STATE_MACHINE_PATH)
    trade = load_json(VALID_TRADE_PATH)

    next_state = route_trade(state_machine, trade)

    assert next_state == "AcceptedTrade"


def test_rejected_trade_routes_to_rejected_trade():
    state_machine = load_json(STATE_MACHINE_PATH)
    trade = load_json(REJECTED_TRADE_PATH)

    next_state = route_trade(state_machine, trade)

    assert next_state == "RejectedTrade"


def test_invalid_workflow_input_routes_to_fail_state():
    state_machine = load_json(STATE_MACHINE_PATH)
    trade = load_json(INVALID_WORKFLOW_INPUT_PATH)

    next_state = route_trade(state_machine, trade)

    assert next_state == "InvalidWorkflowInput"


def test_receive_trade_routes_to_validate_trade_in_task_workflow():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    receive_trade_state = state_machine["States"]["ReceiveTrade"]

    assert receive_trade_state["Next"] == "ValidateTrade"


def test_trade_validation_with_task_has_validate_trade_state():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    states = state_machine["States"]

    assert "ValidateTrade" in states


def test_validate_trade_state_is_task():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]

    assert validate_trade_state["Type"] == "Task"


def test_validate_trade_state_stores_result_under_validation():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]

    assert validate_trade_state["ResultPath"] == "$.validation"


def test_validate_trade_state_routes_to_is_trade_valid():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]

    assert validate_trade_state["Next"] == "IsTradeValid"


def test_is_trade_valid_checks_validation_is_valid():
    state_machine = load_json(TASK_STATE_MACHINE_PATH)

    choice_state = state_machine["States"]["IsTradeValid"]

    variables_checked = [
        choice["Variable"]
        for choice in choice_state["Choices"]
    ]

    assert "$.validation.is_valid" in variables_checked


def test_validate_trade_state_has_retry():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]

    assert "Retry" in validate_trade_state


def test_validate_trade_retry_max_attempts_is_three():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]
    retry_config = validate_trade_state["Retry"][0]

    assert retry_config["MaxAttempts"] == 3


def test_validate_trade_state_has_catch():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]

    assert "Catch" in validate_trade_state


def test_validate_trade_catch_routes_to_validation_task_failed():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]
    catch_config = validate_trade_state["Catch"][0]

    assert catch_config["Next"] == "ValidationTaskFailed"


def test_validate_trade_catch_stores_error_under_task_error():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validate_trade_state = state_machine["States"]["ValidateTrade"]
    catch_config = validate_trade_state["Catch"][0]

    assert catch_config["ResultPath"] == "$.task_error"


def test_validation_task_failed_state_exists():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    states = state_machine["States"]

    assert "ValidationTaskFailed" in states


def test_validation_task_failed_state_is_fail():
    state_machine = load_json(RETRY_CATCH_STATE_MACHINE_PATH)

    validation_task_failed_state = state_machine["States"]["ValidationTaskFailed"]

    assert validation_task_failed_state["Type"] == "Fail"
