# Lesson 34B: SQS Retry and Idempotency Implications

## Objective

Lesson 34B explains why this rule matters:

```text
SQS retry is safe only if the handler's side effects are idempotent.
```

The current `sqs_trade_handler` already has the correct boundary for this lesson:

```text
SQS record handling
  -> parse JSON body
  -> validate required fields and business rules
  -> call persist_trade(trade)
  -> if persist_trade(...) raises, return the message ID in batchItemFailures
```

The lesson is not trying to implement real S3 or DynamoDB persistence inside the SQS handler. The lesson is trying to make the retry risk visible before adding real side effects behind `persist_trade(...)`.

The behaviour to understand is:

```text
A retried SQS message may run the same handler code again.
If the first attempt partially completed side effects before failing,
the retry may repeat those side effects.
Therefore retry safety depends on idempotent side effects.
```

This is tutorial evidence only. It is not AWS deployment code and not Energy Data Lakehouse implementation evidence.

---

## Current project context

Lesson 34A established the SQS poison-message and DLQ mental model:

```text
Lambda reports failed records.
SQS/Lambda retries failed records.
SQS redrive policy moves repeatedly failed messages to the DLQ.
Lambda code does not move messages to the DLQ itself.
```

Lesson 34B builds on that by asking a different question:

```text
What happens if the same SQS message causes the same persistence code to run again?
```

The current handler treats validation and business rejections as handled records:

```text
Invalid JSON                -> handled, no retry
Missing required field      -> handled, no retry
Invalid volume_mwh          -> handled, no retry
persist_trade(...) raises   -> retryable failure
```

That distinction is important. `batchItemFailures` is not a business rejection list. It is a retry signal.

---

## What SQS retry means for side effects

The current handler shape is:

```python
try:
    persist_trade(trade)
except Exception:
    logger.exception("Failed to persist trade message_id=%s", message_id)
    batch_item_failures.append(batch_item_failure(message_id))
    continue
```

That means:

```text
persist_trade(...) succeeds
  -> message is not returned in batchItemFailures
  -> SQS/Lambda treats the record as successfully handled

persist_trade(...) raises
  -> message ID is returned in batchItemFailures
  -> SQS/Lambda treats the record as failed
  -> the message can be retried later
```

The retry lifecycle is:

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

SQS retry does not roll back work that already happened. It only gives the consumer another chance to process the message.

---

## Why at-least-once delivery matters

SQS Standard queues use at-least-once delivery semantics.

That means consumer code must be designed as though this can happen:

```text
The same message may be delivered once.
The same message may be delivered more than once.
The same message may be delivered again after a previous partial failure.
```

Duplicate delivery is not a corner case. It is a normal distributed-systems condition.

The safe consumer assumption is:

```text
Every side effect may be attempted again.
```

The design question is not:

```text
How do I stop SQS from retrying?
```

The better question is:

```text
If SQS retries, can the handler safely repeat its side effects?
```

---

## Partial success inside `persist_trade(...)`

This simple shape looks harmless:

```python
def persist_trade(trade):
    write_s3_artifact(trade)
    write_dynamodb_status(trade)
```

But it is not atomic.

A dangerous failure case is:

```python
def persist_trade(trade):
    write_s3_artifact(trade)      # succeeds
    write_dynamodb_status(trade)  # raises
```

From the SQS handler's point of view, only one thing is visible:

```text
persist_trade(...) raised an exception.
```

The handler does not automatically know that:

```text
S3 write already succeeded.
DynamoDB write failed.
A retry may repeat the S3 write.
```

That is the core Lesson 34B risk.

---

## What idempotency means here

An operation is **idempotent** when repeating it has the same intended final effect as running it once.

For this tutorial, a good idempotency target is:

```text
Processing trade_id=TRD-1001 once
and processing trade_id=TRD-1001 again
should not create duplicate logical results.
```

Idempotency does not mean "the code is never called twice."

It means:

```text
Even if the code is called twice, the durable state remains correct.
```

---

## Duplicate S3 write risk

An unsafe S3 key design uses non-deterministic keys:

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

Both objects may represent the same trade. That creates duplicate artifacts.

A timestamp-based key has a similar problem:

```python
from datetime import UTC, datetime


def build_s3_key(trade):
    timestamp = datetime.now(UTC).isoformat()
    return f"accepted/{timestamp}.json"
```

Retry consequence:

```text
First attempt writes: accepted/2026-07-04T10:00:00Z.json
Retry writes:         accepted/2026-07-04T10:01:00Z.json
```

Again, the retry creates another artifact for the same logical trade.

A safer deterministic shape uses a stable business identifier:

```python
def build_s3_key(trade):
    return f"accepted/trade_id={trade['trade_id']}/result.json"
```

Retry consequence:

```text
First attempt writes: accepted/trade_id=TRD-1001/result.json
Retry writes:         accepted/trade_id=TRD-1001/result.json
```

This is better because repeated attempts target the same logical object.

Deterministic keys reduce duplicate object sprawl, but they do not solve everything by themselves. The overwrite policy still needs to be intentional.

Questions the design must answer:

```text
Can the same S3 object be overwritten?
Should the write be skipped if the object already exists?
Should content be compared before overwrite?
Should DynamoDB be the idempotency gate while S3 stores the artifact?
```

For this tutorial path, the clean mental model is:

```text
Deterministic S3 key: reduces duplicate artifact risk.
DynamoDB conditional write: protects processing status from blind overwrite.
```

---

## Duplicate DynamoDB write risk

An unsafe DynamoDB write shape is:

```python
def persist_trade_status_record(*, dynamodb_table, status_record):
    dynamodb_table.put_item(Item=status_record)
```

If the same message is retried, that write may run again.

Depending on the table key and item shape, retry could overwrite:

```text
status
processed_at
s3_key
error fields
audit fields
```

A safer conditional-write shape is:

```python
def persist_trade_status_record(*, dynamodb_table, status_record):
    dynamodb_table.put_item(
        Item=status_record,
        ConditionExpression="attribute_not_exists(trade_id)",
    )
```

This means:

```text
Create the item only if trade_id does not already exist.
```

Retry consequence:

```text
First attempt creates the status record.
Retry attempts to create it again.
DynamoDB rejects the duplicate write.
Handler can treat duplicate-as-already-processed if that is the intended contract.
```

The condition does not stop SQS from retrying. It protects state when retry happens.

---

## Why deterministic keys help

Deterministic S3 keys are an idempotency support mechanism.

| Key type | Example | Retry behaviour | Risk |
|---|---|---|---|
| Random key | `accepted/{uuid}.json` | Creates another object | Duplicate artifacts |
| Timestamp key | `accepted/{timestamp}.json` | Often creates another object | Duplicate artifacts |
| Trade-ID key | `accepted/trade_id=TRD-1001/result.json` | Targets same logical object | Safer, but overwrite semantics matter |

Use deterministic keys when the message contains a stable business identifier.

Avoid random keys for result artifacts where the intended model is:

```text
one logical result per trade
```

Random keys are more appropriate for append-only logs where every write is intentionally a separate event.

---

## Why conditional writes help

A weak idempotency pattern is "check then write":

```python
existing = table.get_item(Key={"trade_id": trade_id})
if "Item" not in existing:
    table.put_item(Item=status_record)
```

This can race:

```text
Worker A: get_item -> no item
Worker B: get_item -> no item
Worker A: put_item -> succeeds
Worker B: put_item -> also writes or overwrites
```

The safer pattern is an atomic conditional write:

```python
table.put_item(
    Item=status_record,
    ConditionExpression="attribute_not_exists(trade_id)",
)
```

The condition is evaluated by DynamoDB as part of the write operation.

That makes the write itself the idempotency gate.

---

## Unsafe retry scenario

Assume the SQS message represents this trade:

```python
trade = {
    "trade_id": "TRD-1001",
    "product": "UK Power",
    "volume_mwh": 250,
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
  handler returns message ID in batchItemFailures

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

That is not clean idempotency. The system has duplicate S3 artifacts for the same trade.

---

## Safer retry scenario

Safer persistence shape:

```python
def build_s3_key(trade):
    return f"accepted/trade_id={trade['trade_id']}/result.json"


def persist_trade(trade):
    s3_key = build_s3_key(trade)
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
  handler returns message ID in batchItemFailures

Attempt 2:
  write_s3_artifact("accepted/trade_id=TRD-1001/result.json") targets same key
  write_dynamodb_status_conditionally(...) succeeds
```

Final state:

```text
S3:
  accepted/trade_id=TRD-1001/result.json

DynamoDB:
  trade_id=TRD-1001 -> accepted/trade_id=TRD-1001/result.json
```

This is safer because repeated processing converges toward one logical result.

Still, this is not magic. The design must define whether repeated S3 writes are acceptable or whether they should also be guarded.

---

## Business rejection versus retryable failure

The current handler behaviour separates business-invalid messages from retryable persistence failures.

| Case | Current handler treatment | Retry? |
|---|---|---:|
| Invalid JSON | handled rejection | No |
| Missing field | handled rejection | No |
| Invalid business value | handled rejection | No |
| `persist_trade(...)` raises | retryable failure | Yes |

The key point:

```text
A business-invalid message is not automatically a poison message.
It becomes a retry candidate only if the handler reports it as failed.
```

This is correct:

```text
Invalid trade
  -> record rejection
  -> do not return message ID in batchItemFailures
```

This is also correct:

```text
Valid trade
  -> persistence dependency fails
  -> return message ID in batchItemFailures
```

Different failure class. Different retry behaviour.

---

## When to let SQS retry

Let SQS retry when the failure is plausibly temporary or when the handler cannot safely confirm completion.

| Failure | Retry? | Reason |
|---|---:|---|
| S3 unavailable | Yes | Dependency may recover |
| DynamoDB throttling | Yes | Capacity or throttling issue may clear |
| Transient network failure | Yes | Retry may succeed |
| Temporary dependency error | Yes | Not a message-quality issue |
| Handler cannot confirm completion | Usually yes | Ambiguous state requires safe retry or reconciliation |
| Lambda timeout during processing | Yes, if idempotent | Same message may return |

Retry is dangerous when side effects are not idempotent.

Unsafe retry design:

```text
Retry fixes dependency failure
but creates duplicate durable state.
```

Safer retry design:

```text
Retry fixes dependency failure
and repeated side effects converge on the same intended final state.
```

---

## When to treat the message as handled

Retry is usually not useful when repeated processing will not change the outcome.

| Case | Treat as handled? | Reason |
|---|---:|---|
| Malformed JSON | Yes | Retry will not repair the body |
| Missing required field | Yes | Same message will fail again |
| Invalid business value | Yes | Domain rejection, not system fault |
| Rejection artifact successfully persisted | Yes | Business outcome has been recorded |
| Duplicate already processed record | Usually yes | Can be duplicate-as-success if contract allows |
| Unsupported schema version | Usually manual review or handled rejection | Retry alone will not fix schema mismatch |

For learning code:

```text
Log rejection and mark handled.
```

For production-shaped systems:

```text
Persist rejection artifact/status, then mark handled.
```

Do not use the DLQ as a dumping ground for known business rejections.

---

## Where idempotency belongs

Idempotency belongs behind the side-effect boundary:

```text
sqs_trade_handler
  -> decides retry or handled outcome
  -> calls persist_trade(trade)

persist_trade
  -> must make S3/DynamoDB side effects safe under retry
```

Do not add live AWS client construction directly to `sqs_trade_handler.py` for this lesson.

Avoid this shape:

```python
import boto3


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("some-table")
```

That creates import-time AWS coupling and makes local tests brittle.

A better later implementation shape would use dependency injection:

```python
def persist_trade_idempotently(
    *,
    trade,
    s3_client,
    dynamodb_table,
    bucket_name,
):
    s3_key = build_s3_key(trade)
    write_s3_artifact(
        s3_client=s3_client,
        bucket_name=bucket_name,
        s3_key=s3_key,
        trade=trade,
    )
    write_dynamodb_status_conditionally(
        dynamodb_table=dynamodb_table,
        status_record={
            "trade_id": trade["trade_id"],
            "status": "accepted",
            "s3_key": s3_key,
        },
    )
```

That implementation belongs in a later lesson, not in Lesson 34B.

---

## Relationship to Lesson 34A

```text
Lesson 34A:
  Who retries the message?
  Who moves it to the DLQ?

Lesson 34B:
  What happens to side effects when the retried message runs again?
```

Lesson 34A boundary:

```text
Lambda reports failed records.
SQS/Lambda retries them.
SQS redrive policy moves repeatedly failed messages to the DLQ.
```

Lesson 34B boundary:

```text
The queue can redeliver.
The handler must make repeated processing safe.
```

---

## Relationship to Step Functions reconciliation

| Area | SQS retry | Step Functions reconciliation |
|---|---|---|
| Unit | Message | Workflow execution |
| Retry owner | SQS/Lambda integration | Step Functions |
| Failure visibility | Message receive count / DLQ | Execution history / terminal state |
| Reconciliation style | Idempotent handler side effects | Explicit Catch / Pass / Fail / Succeed path |
| Main risk | Duplicate side effects | Partial workflow completion |

The common idea is:

```text
Partial success is normal.
The recovery path must be designed explicitly.
```

Step Functions gives you visible workflow states:

```text
Retry
Catch
Pass
Succeed
Fail
```

SQS gives you message redelivery.

That means the SQS handler and its persistence functions must be safe under repeated invocation.

---

## SAP-C02 relevance

This topic is directly relevant to SAP-C02 architecture judgement.

| SAP-C02 theme | Lesson 34B mapping |
|---|---|
| Decoupled architecture | SQS buffers work and isolates producers from consumers |
| Resilience | Failed messages can retry without blocking all work |
| Failure isolation | Partial batch response avoids retrying successful records |
| Operational recovery | DLQ captures repeatedly failed messages |
| Idempotent processing | Consumers must tolerate duplicate delivery |
| Managed-service boundary | SQS retries; handler protects side effects |
| Reliable persistence | S3/DynamoDB writes must be safe under retry |

Exam-level weak answer:

```text
SQS retry plus DLQ equals reliable processing.
```

Better architecture answer:

```text
SQS retry plus DLQ plus idempotent consumer logic plus observable failure handling equals reliable processing.
```

---

## Lesson boundary

Lesson 34B should not add:

```text
boto3 calls
Terraform
queue policies
real S3 writes
real DynamoDB writes
new AWS deployment code
large handler rewrites
```

The current code already proves the retry signal:

```text
persist_trade(...) succeeds -> no batchItemFailures
persist_trade(...) raises   -> message ID appears in batchItemFailures
```

The note explains the architectural consequence:

```text
If SQS retries the message, the side effects behind persist_trade(...) must be idempotent.
```

---

## Bottom line

SQS gives redelivery.

It does not give safe persistence.

The safe design is:

```text
SQS retry
  + partial batch response
  + deterministic artifact keys
  + conditional status writes
  + clear business rejection handling
  + DLQ for unresolved retryable failures
```

Lesson 34B is complete when the learner can explain:

```text
The handler returns failed message IDs to request retry.
Retry may run the same persistence code again.
Repeated persistence is safe only when the side effects are idempotent.
```

---

## Acronym legend

| Acronym | Meaning |
|---|---|
| AWS | Amazon Web Services |
| DLQ | Dead-Letter Queue |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda serverless function service |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam code |
| SQS | Amazon Simple Queue Service |
