# Learning Summary

---

### Lesson 25: Step Functions Retry/Catch for persistence task failure

Completed local-first Step Functions Retry/Catch contract for the persistence Lambda task.

**Evidence:**

- Added `step-functions/persistence-task-state-with-retry-catch.json`
- Added `tests/test_step_functions_persistence_retry_catch_contract.py`
- Verified transient Lambda and timeout errors are retried
- Verified retry behavior uses bounded backoff
- Verified caught failures are stored under `$.persistence_error`
- Verified failures route to `PersistenceFailed`
- Verified `PersistenceFailed` is a terminal `Fail` state
- Full local suite passed: 163 tests passed

No AWS resources deployed.

---

### Lesson 26: Idempotency and duplicate persistence protection

Completed local-first idempotency tests for the persistence workflow.

**Evidence:**

- Added conditional DynamoDB write protection using
  `ConditionExpression="attribute_not_exists(trade_id)"`.
- Added a test proving duplicate conditional-check failure can return
  idempotent success.
- Added a test proving unexpected DynamoDB errors are not swallowed.
- Added an S3 key determinism test using `build_s3_key`.
- Added a workflow retry test proving repeated successful execution returns
  the same compact persistence response.
- Full local suite passed: 168 tests passed.

**Caveat:**

- Duplicate handling is currently tested at `persist_trade_status_record`
  through an injected fake conditional-check exception.
- The full workflow does not yet inject a real DynamoDB conditional-check
  exception type.
- No AWS resources deployed.

This is Python/serverless tutorial evidence mapped to SAP-C02 Domain 2
resilience and Domain 3 continuous improvement. It is not Energy Data
Lakehouse implementation evidence.
