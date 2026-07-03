# Lesson 34A: SQS Poison Message and DLQ Mental Model

## Purpose

This lesson explains the SQS poison-message and dead-letter queue mental model
before adding deployment code or queue configuration.

It reconnects the earlier SQS handler lessons with the later persistence and
Step Functions failure-handling lessons.

Current local source of truth:

- `sqs_trade_handler.py`
- `tests/test_sqs_trade_handler.py`
- `docs/lessons/lesson-33-step-functions-timeout-and-terminal-failure.md`

No AWS resources are deployed from this lesson.

## Current handler boundary

The current SQS handler boundary is:

```text
SQS queue
  -> Lambda event source mapping
      -> sqs_trade_handler
          -> parse record body
          -> validate trade fields
          -> call persist_trade(trade)
          -> return batchItemFailures for retryable processing failures
```

The handler returns this Lambda partial batch response shape:

```python
{
    "batchItemFailures": [
        {"itemIdentifier": "message-id-that-failed"}
    ]
}
```

The helper that builds each failed record entry is:

```python
def batch_item_failure(message_id: str) -> dict[str, str]:
    return {"itemIdentifier": message_id}
```

## What a poison message is

A poison message is an SQS message that repeatedly fails processing every time
it is delivered to the consumer.

It is not limited to malformed JSON. A message can become poison because of:

| Cause | Example | Retry likely to help? |
|---|---|---:|
| Malformed technical input | Body is not valid JSON | No |
| Invalid business data | `volume_mwh` is `0` | No, unless upstream data changes |
| Transient processing failure | Temporary S3, DynamoDB, network, or timeout failure | Yes |
| Handler defect | Valid message triggers a code bug | No, until code changes |
| External dependency contract drift | Downstream API shape changes | Usually no, until adapter changes |

The important distinction is whether retry can realistically change the result.

## Invalid business data versus transient processing failure

The current `sqs_trade_handler` deliberately separates these cases.

| Case | Current handler behaviour | Retry classification |
|---|---|---|
| Missing required field | Calls `record_rejection(...)`; does not return a batch failure | Non-retryable in current tutorial code |
| Invalid `volume_mwh` | Calls `record_rejection(...)`; does not return a batch failure | Non-retryable in current tutorial code |
| Invalid JSON body | Calls `record_rejection(...)`; does not return a batch failure | Non-retryable in current tutorial code |
| `persist_trade(trade)` raises | Adds `batch_item_failure(message_id)` | Retryable processing failure |

This matters because the earlier wording "invalid records are returned in
`batchItemFailures`" is not accurate for the current code. The current code
returns `batchItemFailures` only for retryable processing failures raised from
`persist_trade(...)`.

That is a valid tutorial design, but it has an operational consequence: a
business-invalid message is treated as handled after logging the rejection. In a
production design, that rejection would normally need a durable rejection
artifact or audit trail, not only a log line.

## How Lambda partial batch response works for SQS

With an SQS event source mapping, Lambda receives a batch of SQS records.

When partial batch response is enabled with `ReportBatchItemFailures`, the
function can return only the failed message IDs. Lambda then treats the records
not listed in `batchItemFailures` as successfully processed, while the failed
records can become visible again for retry.

For this tutorial, the practical contract is:

| Handler result | Meaning |
|---|---|
| `{"batchItemFailures": []}` | Every record was handled by the function. |
| `{"batchItemFailures": [{"itemIdentifier": "msg-1"}]}` | Only `msg-1` failed and should be retried. |
| Function raises before returning a valid response | The integration cannot use a clean partial-success result. |

The handler should avoid one bad record causing every successful record in the
batch to be retried.

## Why the handler reports failed message IDs

The Lambda handler does not delete SQS messages directly in this pattern.

The Lambda handler also does not move messages to the DLQ.

Its responsibility is narrower:

```text
For each record:
  if handled successfully:
    do not include its messageId in batchItemFailures
  if retryable processing failed:
    include its messageId in batchItemFailures
```

The Lambda/SQS integration handles the service-side acknowledgement behaviour.
The SQS redrive policy handles dead-letter movement after repeated receives.

## Visibility timeout

Visibility timeout is the period after SQS delivers a message during which the
message is hidden from other consumers.

Lifecycle:

```text
SQS delivers message
  -> message becomes invisible
  -> Lambda processes the record
  -> if handled successfully, the message is removed by the integration
  -> if not handled successfully, the message becomes visible again after timeout
```

Operational consequence: the timeout must be long enough for the Lambda
function to finish normal processing. If it is too short, the same message may
become visible and be processed again while the first attempt is still running.

## maxReceiveCount

`maxReceiveCount` is part of the SQS redrive policy.

It controls how many times a message can be received from the source queue
before SQS moves it to the dead-letter queue.

Example mental model:

```text
maxReceiveCount = 3

Receive #1 -> Lambda reports failure -> message becomes visible again
Receive #2 -> Lambda reports failure -> message becomes visible again
Receive #3 -> Lambda reports failure -> redrive threshold reached or exceeded
SQS moves message to the DLQ according to the source queue redrive policy
```

The key boundary is this:

```text
Lambda reports failure.
SQS owns redrive.
```

## What a DLQ is and who moves messages there

A dead-letter queue is a separate SQS queue used to hold messages that could not
be successfully processed from the source queue after the configured receive
limit.

The movement is performed by SQS according to the source queue redrive policy.
The Lambda handler does not implement the DLQ.

Wrong mental model:

```text
Lambda detects bad message
  -> Lambda sends it to the DLQ
```

Correct mental model:

```text
Lambda reports failed messageId
  -> message is retried after visibility timeout
  -> receive count increases across receives
  -> SQS redrive policy moves the message to the DLQ after the threshold
```

## Why Lambda code should not pretend to implement the DLQ

Do not add custom Lambda code that manually sends the original message to a
DLQ-like queue for this lesson.

That would create several problems:

| Problem | Consequence |
|---|---|
| Duplicate DLQ semantics | SQS redrive policy and custom send logic can disagree. |
| Accidental double storage | The same failed message can exist in multiple places. |
| Incorrect ownership | Application code starts implementing queue infrastructure behaviour. |
| Weaker observability | Redrive metrics and source queue behaviour become harder to reason about. |
| Extra IAM scope | Lambda would need `sqs:SendMessage` to a DLQ it should not own here. |

The cleaner architecture is to let SQS own dead-letter movement and let the
handler report record-level processing results accurately.

## Idempotency when SQS retries messages

SQS is an at-least-once delivery service. The handler must assume the same
message can be received more than once.

That means side effects must be safe to repeat.

| Side effect | Duplicate-processing risk | Idempotency control |
|---|---|---|
| S3 artifact write | Duplicate or conflicting result artifacts | Deterministic key and explicit overwrite policy |
| DynamoDB status write | Existing status may be overwritten or conflict | Conditional write and duplicate classification |
| Notification | Duplicate email or alert | Dedupe key or status transition guard |
| Audit event | Repeated audit records | Correlation ID and message ID in the audit record |

This connects directly to the persistence lessons. Retry safety is not just an
SQS topic; it depends on deterministic persistence behaviour downstream.

## Lifecycle diagram

```text
             ┌─────────────────────┐
             │   SQS source queue   │
             └──────────┬──────────┘
                        │
                        │ Lambda polls batch
                        v
             ┌─────────────────────┐
             │  sqs_trade_handler   │
             └──────────┬──────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
          v                           v
┌────────────────────┐      ┌────────────────────────┐
│ Record handled      │      │ Retryable record failed │
│ successfully        │      │ in persist_trade(...)   │
└─────────┬──────────┘      └────────────┬───────────┘
          │                              │
          │ not listed in                │ listed in
          │ batchItemFailures            │ batchItemFailures
          v                              v
┌────────────────────┐      ┌────────────────────────┐
│ Removed from source │      │ Becomes visible again   │
│ queue by integration│      │ after visibility timeout│
└────────────────────┘      └────────────┬───────────┘
                                          │
                                          v
                               ┌─────────────────────┐
                               │ Receive count grows │
                               └──────────┬──────────┘
                                          │
                               maxReceiveCount exceeded
                                          │
                                          v
                               ┌─────────────────────┐
                               │ DLQ                 │
                               │ moved by SQS        │
                               │ redrive policy      │
                               └─────────────────────┘
```

## Decision table

| Situation | Current handler response | Retry? | DLQ path? | Design judgement |
|---|---|---:|---:|---|
| Valid record persists successfully | No batch failure | No | No | Correct success path. |
| Missing required field | Rejection logged; no batch failure | No | No | Current tutorial treats validation rejection as handled. |
| Invalid JSON body | Rejection logged; no batch failure | No | No | Current tutorial treats malformed body as handled. |
| Invalid `volume_mwh` | Rejection logged; no batch failure | No | No | Business-invalid data is not retried in current code. |
| `persist_trade(...)` raises for one record | Failed `messageId` returned | Yes | Eventually, if repeated | Correct use of partial batch failure. |
| Whole function crashes before response | No clean partial response | Likely batch-level retry | Possible | Avoid broad unhandled exceptions. |
| Same failed message keeps retrying | Same `messageId` repeatedly reported | Yes, until threshold | Yes | This is poison-message behaviour. |
| Lambda manually sends to DLQ | Not used | Not applicable | Not the right boundary | SQS redrive policy should own DLQ movement. |

## Difference from Lesson 33 Step Functions terminal failure

Lesson 33 handled workflow-level terminal failure in Step Functions.

SQS poison-message handling is message-level failure.

| Dimension | SQS poison message and DLQ | Step Functions terminal failure |
|---|---|---|
| Failure unit | One SQS message inside a batch | One workflow execution or state path |
| Retry owner | SQS/Lambda event source mapping plus SQS redrive policy | Step Functions state machine |
| Failure shape | `batchItemFailures` with message IDs | `Retry`, `Catch`, `Pass`, `Succeed`, and `Fail` states |
| Terminal destination | DLQ after repeated unsuccessful receives | Explicit workflow terminal state |
| Handler responsibility | Report failed records accurately | Raise or return state-compatible task results |
| Common misconception | Lambda sends messages to the DLQ | Catch always means success or every failure should end immediately |
| Idempotency risk | Same message can be delivered again | Same task can be retried in the workflow |

The distinction is important for architecture design:

```text
SQS owns message delivery and redrive.
Step Functions owns workflow routing and terminal state.
Lambda owns local record processing and clear success/failure reporting.
```

## Optional local test boundary

A useful tiny test is a mixed batch where:

- one valid record persists successfully;
- one structurally valid record fails inside `persist_trade(...)`;
- the response contains only the failed record's `messageId` in
  `batchItemFailures`.

That test clarifies the current handler contract without adding AWS resources,
Terraform, queue policies, or boto3 calls.

## SAP-C02 relevance

| SAP-C02 area | Relevance |
|---|---|
| Domain 2 resilience | SQS retries and DLQs isolate failed messages from healthy processing. |
| Domain 2 decoupling | SQS buffers work between producers and Lambda consumers. |
| Domain 3 continuous improvement | Poison-message handling creates a recovery and inspection path. |
| Domain 3 operational excellence | Partial batch response reduces unnecessary retries. |
| Domain 1 security boundary | Lambda does not need broad SQS permissions just to use a DLQ. |
| Reliability judgement | Idempotency is required because retries can repeat side effects. |

This is tutorial evidence only. It is not Energy Data Lakehouse implementation
evidence.

## References

- AWS Lambda Developer Guide: Handling errors for an SQS event source in Lambda.
- Amazon SQS Developer Guide: Using dead-letter queues in Amazon SQS.
- Amazon SQS Developer Guide: Amazon SQS visibility timeout.
