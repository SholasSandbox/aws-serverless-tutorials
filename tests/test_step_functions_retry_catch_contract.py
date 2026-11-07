import json
from pathlib import Path


def test_validation_retry_catch_contract():
    # Arrange
    file_path = Path("step-functions/trade-validation-with-retry-catch.asl.json")
    state_machine = json.loads(file_path.read_text())

    states = state_machine["States"]
    validate_task = states["ValidateTrade"]

    retry_policy = validate_task["Retry"]
    catch_policy = validate_task["Catch"]
    failure_state = states["ValidationTaskFailed"]

    # Assert 1: Verify the input and result paths
    assert validate_task["ResultPath"] == "$.validation"
    assert validate_task["InputPath"] == "$.trade"

    # Assert 2: Verify the bounded retry configuration
    assert retry_policy == [
        {
            "ErrorEquals": [
                "Lambda.ServiceException",
                "Lambda.AWSLambdaException",
                "Lambda.SdkClientException",
                "Lambda.TooManyRequestsException",
                "States.Timeout",
            ],
            "IntervalSeconds": 2,
            "MaxAttempts": 3,
            "BackoffRate": 2,
        }
    ]

    # Assert 3: Verify the Catch error-preservation path
    assert catch_policy == [
        {
            "ErrorEquals": ["States.ALL"],
            "ResultPath": "$.validation_error",
            "Next": "ValidationTaskFailed",
        }
    ]
    # Assert 4: Verify the Catch destination and terminal Fail state
    assert failure_state == {
        "Type": "Fail",
        "Error": "ValidationTaskFailed",
        "Cause": "The ValidateTrade task failed after retry handling",
    }
