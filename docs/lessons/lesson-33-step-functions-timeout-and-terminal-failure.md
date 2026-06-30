# Lesson 33: Step Functions Timeout and Terminal-Failure Behaviour

## Purpose

This lesson documents how the persistence workflow handles timeout, retry,
catch, reconciliation, success, and terminal-failure behaviour in Step Functions.

It reconnects the previous design notes back to locally testable serverless
artifacts:

- `step-functions/persistence-task-timeout-terminal-failure.asl.json`
- `tests/test_step_functions_timeout_terminal_failure_definition.py`

## Current workflow boundary

The current workflow boundary remains:

```text
Step Functions
  -> persistence Lambda
      -> writes accepted/rejected trade result artifact to S3
      -> writes trade status record to DynamoDB
