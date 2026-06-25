import json
from pathlib import Path


STEP_FUNCTIONS_DIR = Path("step-functions")


def load_json_file(file_name: str) -> dict:
    file_path = STEP_FUNCTIONS_DIR / file_name
    return json.loads(file_path.read_text())


def test_persistence_task_input_contract_contains_trade_validation_and_processed_at():
    task_input = load_json_file("persistence-task-input.json")

    assert task_input == {
        "trade": {
            "trade_id": "TRD-001",
            "product": "POWER",
            "volume_mwh": 100,
        },
        "validation": {
            "is_valid": True,
            "errors": [],
        },
        "processed_at": "2026-06-02T18:30:00Z",
    }


def test_persistence_task_output_contract_contains_stable_status_and_s3_pointer():
    task_output = load_json_file("persistence-task-output.json")

    assert task_output == {
        "trade_id": "TRD-001",
        "status": "ACCEPTED",
        "result_type": "accepted",
        "s3_bucket": "test-results-bucket",
        "s3_key": (
            "trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json"
        ),
    }


def test_persistence_task_state_stores_lambda_payload_under_persistence_result_path():
    task_state = load_json_file("persistence-task-state.json")
    persist_state = task_state["PersistTradeResult"]

    assert persist_state["Type"] == "Task"
    assert persist_state["Resource"] == "arn:aws:states:::lambda:invoke"
    assert persist_state["Parameters"]["Payload.$"] == "$"
    assert persist_state["ResultPath"] == "$.persistence"

    assert persist_state["ResultSelector"] == {
        "trade_id.$": "$.Payload.trade_id",
        "status.$": "$.Payload.status",
        "result_type.$": "$.Payload.result_type",
        "s3_bucket.$": "$.Payload.s3_bucket",
        "s3_key.$": "$.Payload.s3_key",
    }
