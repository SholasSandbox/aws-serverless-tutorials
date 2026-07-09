# Lesson 31: Retry-Safe Persistence and Reconciliation Decision Note

Related note: `docs/iam/persistence-handler-iam-checklist.md`

## Purpose

This note defines how the current persistence workflow should behave when retry
or partial-failure conditions occur.

It is tutorial evidence only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note.
- Do not introduce new services.
- Use the current Python code and tests as the source of truth.
- Keep retry behaviour tied to observed handler behaviour, not broad future
  possibilities.

## Lesson spine

| Lesson | What it established | Why it matters here |
| --- | --- | --- |
| 28 | The persistence pieces were connected into one workflow shape. Accepted/rejected trade result artifacts are written to S3, and status records are written to DynamoDB. | There are now two persistence targets in one workflow boundary. |
| 29 | S3 persistence can succeed, then DynamoDB persistence can fail afterward. | The workflow can enter a partial-persistence state. |
| 30 | Least-privilege IAM was documented. Lambda owns S3/DynamoDB/log permissions; Step Functions owns Lambda invocation. | IAM does not fix retry correctness or partial persistence. |

## Current workflow boundary

```text
Step Functions
  -> persistence Lambda
      -> build accepted/rejected S3 artifact
      -> write artifact to S3
      -> build DynamoDB status record
      -> write status record to DynamoDB
```

Known current responsibilities:

| Responsibility | Current function |
| --- | --- |
| Build S3 object key | `build_s3_key` |
| Build accepted trade artifact | `build_accepted_trade_artifact` |
| Build rejected trade artifact | `build_rejected_trade_artifact` |
| Write DynamoDB status record | `persist_trade_status_record` |
| Combined S3 + DynamoDB workflow | `persist_trade_processing_result` |

## Core problem

The persistence Lambda performs more than one external write:

```text
S3 PutObject
  then
DynamoDB PutItem
```

That means the workflow is not automatically atomic.

If S3 succeeds and DynamoDB fails, AWS will not automatically roll back the S3
object. The workflow must deliberately choose one of these behaviours:

1. retry safely,
2. fail and surface the partial state,
3. route to reconciliation,
4. run explicit compensation logic.

The default should be **retry safely or reconcile**, not broad cleanup.

## Main decision

Retrying the whole persistence Lambda is acceptable only when both of these are
true:

| Requirement | Why it matters |
| --- | --- |
| S3 object key is deterministic for the same workflow input | A retry writes the same object path instead of creating duplicate artifacts. |
| DynamoDB write behaviour is idempotent or explicitly classified | A retry does not silently overwrite or misclassify an existing status record. |

If either condition is false, a whole-Lambda retry can make the failure state
worse.

## Deterministic S3 key rule

A deterministic S3 key means the same logical trade result produces the same
object key across retries.

Example shape:

```text
trade-results/{status}/{trade_id}.json
```

or, if the workflow already has a stable `processed_at` value in the input:

```text
trade-results/{status}/{processed_date}/{trade_id}.json
```

Avoid generating retry-sensitive values inside the persistence Lambda if they
become part of the S3 key.

Bad retry pattern:

```python
# Risky if called again during retry and used in the S3 key.
processed_at = datetime.now(timezone.utc).isoformat()
key = build_s3_key(status=status, trade_id=trade_id, processed_at=processed_at)
```

Better pattern:

```python
# Safer: processed_at is supplied by the upstream workflow input.
processed_at = event["processed_at"]
key = build_s3_key(status=status, trade_id=trade_id, processed_at=processed_at)
```

The issue is not timestamps themselves. The issue is whether the value is stable
for the same workflow execution.

## DynamoDB idempotency rule

A DynamoDB `ConditionExpression` protects against accidental overwrite, but it
does not automatically prove idempotency.

Example write guard:

```python
def persist_trade_status_record(*, dynamodb_table, status_record):
    dynamodb_table.put_item(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",
    )
```

This protects the first write:

```text
No existing trade_id -> PutItem succeeds
Existing trade_id    -> ConditionalCheckFailedException
```

The important interpretation is:

| Duplicate condition | Correct interpretation |
| --- | --- |
| Existing record is identical to the retry attempt | Idempotent success, but only if the code verifies equivalence. |
| Existing record has same `trade_id` but different status, S3 key, or processed timestamp | Business conflict or data integrity issue. Route to reconciliation. |
| Code does not read/compare the existing record | Do not pretend it is idempotent success. Treat as duplicate/conflict or surface for review. |

Pushback: do not simply catch `ConditionalCheckFailedException` and return
success unless the code has proved the existing record matches the attempted
write.

## Failure decision table

| Failure point | State of S3 | State of DynamoDB | Recommended workflow behaviour | Reason |
| --- | --- | --- | --- | --- |
| S3 `PutObject` fails before any DynamoDB write | No artifact written | No status record written | Step Functions may retry the Lambda for transient errors. Catch after retry exhaustion. | No partial persistence has occurred yet. |
| S3 succeeds, DynamoDB transient failure | Artifact written | No status record written | Retry whole Lambda only if S3 key is deterministic. Otherwise route to reconciliation. | Retry may repair the missing status record, but only if repeat S3 write is safe. |
| S3 succeeds, DynamoDB conditional duplicate with identical existing record | Artifact written | Status record already exists | Treat as idempotent success only if equivalence is verified. | The workflow outcome already exists. |
| S3 succeeds, DynamoDB conditional duplicate with different existing record | Artifact written | Conflicting status exists | Catch and route to reconciliation/manual review. | There may be duplicate or inconsistent business state. |
| Lambda times out after S3 write but before returning | Unknown to caller | Unknown or missing | Retry only if deterministic keys and idempotent DynamoDB behaviour are in place. Otherwise reconcile. | Timeout creates ambiguity. The caller may not know which writes completed. |
| DynamoDB succeeds, Lambda fails before response | Artifact written | Status record written | Retry must not corrupt existing record. Duplicate should be classified deterministically. | The workflow may have succeeded even though Step Functions saw failure. |

## Step Functions decision guidance

Step Functions should own orchestration-level failure handling. Lambda should own
its local validation and persistence calls.

Recommended shape:

```json
{
  "PersistResult": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Retry": [
      {
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException"
        ],
        "IntervalSeconds": 2,
        "MaxAttempts": 3,
        "BackoffRate": 2.0
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.persistence_error",
        "Next": "PersistenceReconciliationRequired"
      }
    ],
    "Next": "PersistenceSucceeded"
  }
}
```

This is illustrative only. It is not deployment-ready Amazon States Language
(ASL) for the full workflow.

## When to Retry, Catch, Fail, or Reconcile

| Step Functions action | Use when |
| --- | --- |
| `Retry` | The error is likely transient and repeating the Lambda is safe. |
| `Catch` | Retries are exhausted or the error needs controlled routing. |
| `Fail` | The workflow should stop because the input or state is invalid and no recovery path is useful. |
| Reconciliation/manual review | The workflow cannot prove whether persistence is complete, duplicated, or conflicting. |

Do not use retry as a substitute for idempotency. Retry only amplifies the
existing design. If the write path is unsafe, retry repeats the unsafe action.

## Why `s3:DeleteObject` is not the default fix

Adding `s3:DeleteObject` so the Lambda can clean up after a DynamoDB failure is
not the default design.

Reasons:

- It broadens the Lambda execution role.
- It creates a second failure path: cleanup can also fail.
- It can delete useful audit evidence.
- It hides the partial-failure state instead of making it observable.
- It requires explicit compensation tests.

Use S3 delete compensation only when the workflow has a tested business rule for
undoing the artifact write.

For the current tutorial path, prefer:

```text
stable S3 key
+ idempotent or conditional DynamoDB write
+ Step Functions Retry/Catch
+ reconciliation path when ambiguous
```

## Minimal code direction

The persistence workflow should make failures explicit enough for Step Functions
to route them.

Example direction:

```python
from botocore.exceptions import ClientError


class PersistenceConflictError(Exception):
    """Raised when persistence detects a non-idempotent duplicate."""


def is_conditional_check_failure(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def persist_trade_processing_result(*, s3_client, dynamodb_table, event):
    artifact = build_artifact_from_event(event)
    s3_key = build_s3_key_from_event(event)
    status_record = build_status_record_from_event(event, s3_key=s3_key)

    s3_client.put_object(
        Bucket=event["results_bucket"],
        Key=s3_key,
        Body=json.dumps(artifact),
        ContentType="application/json",
    )

    try:
        persist_trade_status_record(
            dynamodb_table=dynamodb_table,
            status_record=status_record,
        )
    except ClientError as exc:
        if is_conditional_check_failure(exc):
            # Do not blindly treat this as success.
            # Either verify the existing record matches, or raise a conflict.
            raise PersistenceConflictError("status record already exists") from exc
        raise

    return {
        "status": "persisted",
        "s3_key": s3_key,
        "trade_id": status_record["trade_id"],
    }
```

This is not a full replacement implementation. It shows the direction: make the
failure type meaningful instead of swallowing it or hiding it behind a generic
exception.

## Testing direction

A useful future test should prove the retry boundary rather than just the happy
path.

Example test intent:

```python
def test_retry_after_dynamodb_failure_reuses_same_s3_key():
    """If DynamoDB fails after S3 succeeds, retry should target the same S3 key."""
```

Another useful test intent:

```python
def test_duplicate_status_record_is_not_silently_treated_as_success():
    """A conditional DynamoDB duplicate should be classified, not ignored."""
```

Keep these as future directions unless Lesson 31 is deliberately expanded from a
decision note into code/test changes.

## Recommended decision for the current tutorial

For the current workflow, use this design stance:

```text
Retry the whole persistence Lambda only if the S3 key is deterministic for the
same event and DynamoDB duplicate behaviour is explicit.

If the workflow cannot prove retry safety, Step Functions should Catch the error
and route to reconciliation/manual review rather than adding cleanup permissions
or silently ignoring duplicate records.
```

## Review checklist before implementation changes

Before adding code or Terraform, confirm:

- Does `build_s3_key` return the same key for the same workflow input?
- Is `processed_at` generated once upstream or regenerated inside the
  persistence Lambda?
- Does `persist_trade_status_record` use `ConditionExpression`?
- If a conditional duplicate occurs, does the code verify equivalence or raise a
  clear conflict?
- Does the Step Functions definition retry only safe failures?
- Does the Catch path preserve enough context for reconciliation?
- Are we avoiding `s3:DeleteObject` unless compensation is deliberately tested?

## SAP-C02 relevance

| SAP-C02 area | Relevance |
| --- | --- |
| Reliable architectures | Understand retry safety, partial failure, and idempotency. |
| Secure architectures | Avoid broad permissions such as cleanup deletes unless justified. |
| Operational excellence | Surface ambiguous states through Catch/reconciliation instead of hiding them. |
| Cost and performance | Avoid unnecessary extra reads or compensating writes unless the workflow needs them. |
| Migration/improvement thinking | Convert observed failure behaviour into controlled workflow decisions. |

## Acronym legend

| Acronym | Meaning |
| --- | --- |
| ASL | Amazon States Language |
| AWS | Amazon Web Services |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam |
| SDK | Software Development Kit |
