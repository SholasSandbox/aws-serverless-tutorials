# Lesson 34B: SQS Retry and Idempotency Implications

## Purpose

This lesson explains why SQS retry is safe only when the Lambda handler's side
effects are idempotent.

It builds on Lesson 34A:

```text
Lesson 34A:
  Who retries the message?
  Who moves it to the DLQ?

Lesson 34B:
  What happens to side effects when the retried message runs again?
```

No AWS resources are deployed from this lesson. No Terraform, queue policy,
`boto3`, S3, or DynamoDB implementation code is added here.

The current local source of truth remains:

- `sqs_trade_handler.py`
- `tests/test_sqs_trade_handler.py`
- earlier persistence lessons covering deterministic S3 keys and DynamoDB
  conditional writes

## Objective

Lesson 34B proves this statement:

```text
A retried SQS message may run the same handler code again.
If the first attempt partially completed side effects before failing,
the retry may repeat those side effects.
Therefore retry safety depends on idempotent side effects.
```

SQS retry only redelivers the message. It does not make S3 writes, DynamoDB
writes, notifications, counters, or audit records safe to repeat.

The handler must be designed so repeated processing converges on the same
intended final state.

## Current handler boundary

The current SQS handler boundary is intentionally small:

```text
SQS queue
  -> Lambda event source mapping
      -> sqs_trade_handler
          -> parse record body
          -> validate trade fields
          -> call persist_trade(trade)
          -> return batchItemFailures for retryable persistence failures
```

The current `persist_trade(...)` function is still a tutorial stub:

```python
def persist_trade(trade: dict[str, Any]) -> None:
    return None
```

The retry signal appears only when `persist_trade(trade)` raises:

```python
try:
    persist_trade(trade)
except Exception:
    logger.exception("Failed to persist trade message_id=%s", message_id)
    batch_item_failures.append(batch_item_failure(message_id))
    continue
```

So, in the current code:

| Case | Handler treatment | Retry? |
|---|---|---:|
| Invalid JSON | `record_rejection(...)`; no batch failure | No |
| Missing field | `record_rejection(...)`; no batch failure | No |
| Invalid `volume_mwh` | `record_rejection(...)`; no batch failure | No |
| `persist_trade(...)` succeeds | `record_accepted(...)`; no batch failure | No |
| `persist_trade(...)` raises | `batch_item_failure(message_id)` | Yes |

The key contract remains:

```text
batchItemFailures is not "business rejection".
batchItemFailures is "retry this SQS message".
```

## What SQS retry means for side effects

When `persist_trade(...)` raises, the handler returns the message ID in
`batchItemFailures`.

Lifecycle:

```text
SQS delivers message
  -> Lambda validates message
  -> handler calls persist_trade(...)
  -> persist_trade(...) performs side effects
  -> persist_trade(...) raises
  -> handler returns messageId in batchItemFailures
  -> message becomes visible again later
  -> SQS delivers same message again
  -> side effects may run again
```

The retry is useful only if the second execution is safe.

Unsafe mental model:

```text
SQS retries the message, so the system is reliable.
```

Correct mental model:

```text
SQS retries the message.
The handler must make repeated side effects safe.
```

## Why at-least-once delivery matters

SQS Standard queues provide at-least-once delivery. That means a message can be
delivered more than once.

Do not treat duplicate delivery as a rare edge case. Treat it as part of the
normal service contract.

The consumer must be designed as if all of these can happen:

```text
This message may run once.
This message may run twice.
This message may run again after a partial previous attempt.
```

This is especially important when the handler performs side effects such as:

- writing an S3 result artifact;
- writing a DynamoDB status record;
- sending a notification;
- updating a counter;
- calling another API;
- writing an audit record.

## Partial success inside `persist_trade(...)`

This function shape looks simple:

```python
def persist_trade(trade):
    write_s3_artifact(trade)
    write_dynamodb_status(trade)
```

But it is not atomic.

Dangerous failure case:

```python
def persist_trade(trade):
    write_s3_artifact(trade)      # succeeds
    write_dynamodb_status(trade)  # raises
```

The SQS handler sees only this:

```text
persist_trade(...) raised an exception.
```

The handler does not automatically know this:

```text
The S3 write already succeeded.
The DynamoDB write failed.
A retry may repeat the S3 write.
```

That is the core Lesson 34B failure mode.

## Duplicate S3 write risk

Non-deterministic S3 keys are dangerous under retry.

Unsafe key shape:

```python
import uuid


def build_s3_key(trade):
    return f"accepted/{uuid.uuid4()}.json"
```

Retry consequence:

```text
First attempt writes: accepted/random-1.json
Retry writes:         accepted/random-2.json
```

Both objects may represent the same logical trade.

That creates several problems:

| Problem | Consequence |
|---|---|
| Duplicate artifacts | The same trade appears more than once. |
| Harder reconciliation | There is no obvious canonical object. |
| Noisy analytics | Downstream consumers may read duplicate records. |
| Weak audit trail | You must infer which object is authoritative. |

Safer deterministic key shape:

```python
def build_s3_key(trade):
    return f"accepted/trade_id={trade['trade_id']}/result.json"
```

Retry consequence:

```text
First attempt writes: accepted/trade_id=TRD-1001/result.json
Retry writes:         accepted/trade_id=TRD-1001/result.json
```

This reduces duplicate object sprawl because repeated attempts target the same
logical artifact.

It does not solve every problem. You still need to decide:

- whether overwrite is allowed;
- whether existing object means "already processed";
- whether to compare content before overwrite;
- whether DynamoDB should be the idempotency gate while S3 stores the artifact.

For this tutorial, the clean mental model is:

```text
S3 deterministic keys reduce duplicate artifact risk.
DynamoDB conditional writes provide the stronger processing-state guard.
```

## Duplicate DynamoDB write risk

Unsafe DynamoDB write shape:

```python
def persist_trade_status_record(*, dynamodb_table, status_record):
    dynamodb_table.put_item(Item=status_record)
```

Retry consequence:

```text
First attempt writes the status record.
Retry writes the status record again.
```

Depending on the item shape, the retry may overwrite:

- `processed_at`;
- `status`;
- `s3_key`;
- error details;
- audit fields.

Safer conditional-write shape already used in the project:

```python
def persist_trade_status_record(*, dynamodb_table, status_record):
    dynamodb_table.put_item(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",
    )
```

Retry consequence:

```text
First attempt creates the status record.
Retry attempts to create it again.
DynamoDB rejects the duplicate write.
The handler can treat duplicate-as-already-processed if that is the intended contract.
```

The conditional write does not stop SQS retry. It protects the state from being
blindly overwritten during retry.

## Why deterministic keys help

Deterministic keys make repeated attempts target the same logical object.

| Key type | Example | Retry behaviour | Risk |
|---|---|---|---|
| Random key | `accepted/{uuid}.json` | Creates another object | Duplicate artifacts |
| Timestamp key | `accepted/{timestamp}.json` | Often creates another object | Duplicate artifacts |
| Trade-ID key | `accepted/trade_id=TRD-1001/result.json` | Targets same logical object | Safer, but overwrite semantics matter |

Judgement call:

```text
Use deterministic keys when the message has a stable business identifier.
Do not use random keys for idempotency-sensitive result artifacts.
```

Random keys are acceptable for append-only logs. They are weak for a system that
needs one canonical result per trade.

## Why conditional writes help

This application-level pattern is weak:

```python
existing = table.get_item(Key={"trade_id": trade_id})
if "Item" not in existing:
    table.put_item(Item=status_record)
```

It has a race condition:

```text
Worker A: get_item -> no item
Worker B: get_item -> no item
Worker A: put_item -> succeeds
Worker B: put_item -> also succeeds or overwrites
```

The safer pattern is an atomic conditional write:

```python
table.put_item(
    Item=status_record,
    ConditionExpression="attribute_not_exists(trade_id)",
)
```

The database evaluates the condition as part of the write request:

```text
Only create this record if trade_id does not already exist.
```

That is stronger than "check then write" because the check and write are not
separate application-level operations.

## Business rejection versus retryable failure

The current handler treats validation and business rejection as handled records.

| Case | Current handler treatment | Retry? |
|---|---|---:|
| Invalid JSON | handled rejection | No |
| Missing field | handled rejection | No |
| Invalid business value | handled rejection | No |
| `persist_trade(...)` raises | retryable failure | Yes |

A business-invalid message is not automatically a poison message.

It becomes a retry candidate only if the handler reports it as failed.

Correct shape for a known business rejection:

```text
Invalid trade
  -> log rejection or persist rejection evidence
  -> do not return messageId in batchItemFailures
```

Correct shape for a retryable processing failure:

```text
Valid trade
  -> persistence dependency fails
  -> return messageId in batchItemFailures
```

Different failure class. Different retry behaviour.

## When to let SQS retry

Let SQS retry when the failure is plausibly temporary or the handler cannot
safely confirm completion.

| Failure | Retry? | Reason |
|---|---:|---|
| S3 unavailable | Yes | Dependency may recover. |
| DynamoDB throttling | Yes | Capacity or throttling may clear. |
| Transient network failure | Yes | Retry may succeed. |
| Temporary dependency error | Yes | Not a message-quality issue. |
| Handler cannot confirm completion | Usually yes | State is ambiguous. Safe retry or reconciliation is needed. |
| Lambda timeout during processing | Yes, if idempotent | The same message may return. |

Retry is only safe if repeated side effects converge on the same final state.

Unsafe retry design:

```text
Retry fixes the dependency failure but creates duplicate state.
```

Safer retry design:

```text
Retry fixes the dependency failure and repeated side effects target the same logical result.
```

## When to treat the message as handled

Retry is usually not useful when repeated processing will not change the
outcome.

| Case | Treat as handled? | Reason |
|---|---:|---|
| Malformed JSON | Yes | Retry will not repair the message body. |
| Missing required field | Yes | Same message will fail again. |
| Invalid business value | Yes | Domain rejection, not system fault. |
| Rejection artifact successfully persisted | Yes | Business outcome was recorded. |
| Duplicate already processed record | Usually yes | Idempotent success if the contract allows it. |
| Unsupported schema version | Usually yes or manual review | Retry alone will not fix schema mismatch. |

For learning code, logging the rejection is enough to teach the handler
contract.

For production-shaped systems, a business rejection normally needs durable
rejection evidence before the message is treated as handled.

## Unsafe retry scenario

Assume this message:

```python
message = {
    "messageId": "msg-1",
    "trade": {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
    },
}
```

Unsafe persistence:

```python
import uuid


def persist_trade(trade):
    s3_key = f"accepted/{uuid.uuid4()}.json"
    write_s3_artifact(s3_key, trade)

    write_dynamodb_status(
        {
            "trade_id": trade["trade_id"],
            "status": "accepted",
            "s3_key": s3_key,
        }
    )
```

Failure timeline:

```text
Attempt 1:
  write_s3_artifact("accepted/random-1.json") succeeds
  write_dynamodb_status(...) fails
  handler returns msg-1 in batchItemFailures

Attempt 2:
  write_s3_artifact("accepted/random-2.json") succeeds
  write_dynamodb_status(...) succeeds
```

Final state:

```text
S3:
  accepted/random-1.json
  accepted/random-2.json

DynamoDB:
  trade_id=TRD-1001 -> accepted/random-2.json
```

That is not clean idempotency. It is duplicate artifact creation with one status
pointer.

## Safer retry scenario

Safer persistence:

```python
def persist_trade(trade):
    s3_key = f"accepted/trade_id={trade['trade_id']}/result.json"
    write_s3_artifact(s3_key, trade)

    write_dynamodb_status_conditionally(
        {
            "trade_id": trade["trade_id"],
            "status": "accepted",
            "s3_key": s3_key,
        }
    )
```

Conditional status write:

```python
def write_dynamodb_status_conditionally(status_record):
    table.put_item(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",
    )
```

Retry timeline:

```text
Attempt 1:
  write_s3_artifact("accepted/trade_id=TRD-1001/result.json") succeeds
  write_dynamodb_status_conditionally(...) fails due to transient issue
  handler returns msg-1 in batchItemFailures

Attempt 2:
  write_s3_artifact("accepted/trade_id=TRD-1001/result.json") repeats same logical write
  write_dynamodb_status_conditionally(...) succeeds
```

Final state:

```text
S3:
  accepted/trade_id=TRD-1001/result.json

DynamoDB:
  trade_id=TRD-1001 -> accepted/trade_id=TRD-1001/result.json
```

This is safer. It is not magic. The overwrite policy for the S3 artifact still
must be intentional.

## Relationship to Lesson 34A

Lesson 34A explained the message lifecycle:

```text
Lambda reports failed records.
SQS/Lambda retries them.
SQS redrive policy moves repeatedly failed messages to the DLQ.
```

Lesson 34B adds the side-effect lifecycle:

```text
The queue can redeliver.
The handler must make repeated processing safe.
```

The important boundary remains:

```text
SQS owns retry and redrive.
The Lambda handler owns side-effect safety.
```

## Relationship to Step Functions reconciliation

SQS retry and Step Functions reconciliation solve related but different failure
problems.

| Area | SQS retry | Step Functions reconciliation |
|---|---|---|
| Unit | Message | Workflow execution |
| Retry owner | SQS/Lambda integration | Step Functions |
| Failure visibility | Message receive count / DLQ | Execution history / terminal state |
| Reconciliation style | Idempotent handler side effects | Explicit `Catch` / `Pass` / `Fail` / `Succeed` path |
| Main risk | Duplicate side effects | Partial workflow completion |

Common lesson:

```text
Partial success is normal.
You must design the recovery path.
```

Step Functions gives visible orchestration states.

SQS gives message redelivery.

That means the SQS handler must be designed around idempotent local side
effects.

## SAP-C02 relevance

This is directly relevant to SAP-C02 architecture judgement.

| SAP-C02 theme | Lesson 34B mapping |
|---|---|
| Decoupled architecture | SQS buffers work and isolates producers from consumers. |
| Resilience | Failed messages can retry without blocking all work. |
| Failure isolation | Partial batch response avoids retrying successful records. |
| Operational recovery | DLQ captures repeatedly failed messages. |
| Idempotent processing | Consumers must tolerate duplicate delivery. |
| Managed-service boundary | SQS retries; handler protects side effects. |
| Reliable persistence | S3 and DynamoDB writes must be safe under retry. |

Exam-level trap:

```text
SQS retry + DLQ = reliable processing.
```

Better answer:

```text
SQS retry + DLQ + idempotent consumer + observable failure path = reliable processing.
```

## Lesson boundary

This lesson does not implement real persistence in `sqs_trade_handler.py`.

That is deliberate.

Do not add this to the handler for Lesson 34B:

```python
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("...")
```

That would broaden the handler, introduce import-time AWS setup, and make local
tests dependent on infrastructure concerns.

The correct implementation boundary for later production-shaped work is:

```text
sqs_trade_handler
  -> owns SQS record parsing, validation, and partial batch response

persistence module
  -> owns S3 artifact write, DynamoDB status write, and idempotency controls
```

## Bottom line

SQS gives redelivery.

It does not give safe persistence.

The safer design is:

```text
SQS retry
  + partial batch response
  + deterministic artifact keys
  + conditional status writes
  + clear business rejection handling
  + DLQ for unresolved retryable failures
```

This is Python/serverless tutorial evidence only. It is a candidate pattern for
later adaptation elsewhere, not Energy Data Lakehouse implementation evidence.

## References

- AWS: Amazon SQS at-least-once delivery
- AWS: Handling errors for an SQS event source in Lambda
- AWS: Amazon SQS visibility timeout
- AWS: Using dead-letter queues in Amazon SQS
- AWS: DynamoDB condition expressions
