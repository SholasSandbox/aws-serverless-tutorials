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
```

Step Functions still owns orchestration. The persistence Lambda still owns the
S3 and DynamoDB writes.

## Artifact under review

The state-machine example is:

```text
step-functions/persistence-task-timeout-terminal-failure.asl.json
```

Its important states are:

| State | Type | Purpose |
|---|---|---|
| `PersistTradeResult` | `Task` | Invoke the persistence Lambda with timeout, retry, catch, and preserved result data. |
| `PersistenceSucceeded` | `Succeed` | End the workflow when persistence completes. |
| `RouteToManualReconciliation` | `Pass` | Preserve the fact that bounded retry failed and reconciliation is required. |
| `PersistenceFailed` | `Fail` | Stop the workflow explicitly after routing the failure context. |

## Accepted design

The lesson accepts this shape:

```text
Task timeout
+ bounded retry
+ catch all exhausted failures
+ route to reconciliation
+ terminate with explicit Fail state
```

That shape is deliberately conservative. It avoids pretending persistence
succeeded when S3 may have written an artifact before DynamoDB failed.

## Key Step Functions details

| Detail | Current choice | Why it matters |
|---|---|---|
| Lambda integration | `arn:aws:states:::lambda:invoke` | Step Functions invokes Lambda only; it does not directly write to S3 or DynamoDB. |
| Timeout | `TimeoutSeconds: 30` | A hung persistence task has a bounded runtime. |
| Retry errors | Lambda throttling/service/client errors plus `States.Timeout` | Transient failures can be retried before failure handling runs. |
| Retry limits | `MaxAttempts: 3`, `IntervalSeconds: 2`, `BackoffRate: 2.0` | Retry is bounded and does not hide persistent failure. |
| Result preservation | `ResultPath: $.persistence_result` | Success output is kept without replacing the full input. |
| Failure preservation | `ResultPath: $.persistence_error` | Failure context remains available for reconciliation. |
| Terminal state | `PersistenceFailed` | Exhausted failure is explicit and visible. |

## Trade-off

This design favors correctness and observability over automatic cleanup.

| Option | Why not chosen here |
|---|---|
| Retry forever | Can hide a real consistency problem and create runaway executions. |
| Catch and mark success | Misrepresents a possible partial-persistence state. |
| Add S3 delete compensation by default | Broadens IAM, adds a second failure path, and can delete useful evidence. |
| Route to reconciliation then fail | Chosen because it keeps ambiguity visible and teaches the SAP-C02 failure boundary. |

## Local tests

The test file is:

```text
tests/test_step_functions_timeout_terminal_failure_definition.py
```

It verifies that the ASL definition:

- loads as JSON;
- starts at `PersistTradeResult`;
- invokes Lambda through the Step Functions Lambda integration;
- uses `TimeoutSeconds`;
- has bounded retry settings;
- catches exhausted failures into `$.persistence_error`;
- routes caught failures to manual reconciliation;
- terminates through a `Fail` state;
- does not call S3 or DynamoDB directly;
- preserves successful task output under `$.persistence_result`.

Full local validation on 2026-07-01:

```bash
.venv/bin/python -m pytest -q
```

Result: `217 passed`.

## SAP-C02 relevance

| SAP-C02 area | Relevance |
|---|---|
| Domain 2 resilience | Demonstrates bounded retry, explicit timeout, and failure routing for a new workflow design. |
| Domain 3 continuous improvement | Turns earlier persistence failure analysis into a testable workflow contract. |
| Domain 1 security boundary | Keeps S3 and DynamoDB permissions on the Lambda role, not the Step Functions role. |

This is Python/serverless tutorial evidence only. It is a candidate pattern for
later adaptation elsewhere, not Energy Data Lakehouse implementation evidence.
