import json
from pathlib import Path


def test_validation_task_input_and_result_paths_match_workflow_contract():
    # Arrange: Load the existing Step Functions state machine
    file_path = Path("step-functions/trade-validation-with-task.asl.json")
    state_machine = json.loads(file_path.read_text())

    # Extract the ValidateTrade Task
    validate_task = state_machine["States"]["ValidateTrade"]

    # Assert: Verify the Task contract
    assert validate_task["Type"] == "Task"

    assert validate_task["InputPath"] == "$.trade"
    assert validate_task["ResultPath"] == "$.validation"
    assert validate_task["Resource"] == (
        "arn:aws:lambda:eu-west-2:123456789012:function:validate-trade"
    )
    assert validate_task["Next"] == "IsTradeValid"


def test_validation_choice_routes_expected_outcomes():
    # Arrange
    file_path = Path("step-functions/trade-validation-with-task.asl.json")
    state_machine = json.loads(file_path.read_text())

    choice_state = state_machine["States"]["IsTradeValid"]
    rules = choice_state["Choices"]

    assert choice_state["Type"] == "Choice"

    assert rules == [
        {
            "Variable": "$.validation.is_valid",
            "BooleanEquals": True,
            "Next": "AcceptedTrade",
        },
        {
            "Variable": "$.validation.is_valid",
            "BooleanEquals": False,
            "Next": "RejectedTrade",
        },
    ]

    assert choice_state["Default"] == "InvalidWorkflowInput"
