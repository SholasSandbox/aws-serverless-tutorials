# Lesson 34C: SQS DLQ Operational Handling and Replay Decision Model

## Objective

Lesson 34C explains what to do after an SQS message has reached a dead-letter
queue.

Lessons 34A and 34B covered the mechanics:

```text
Lesson 34A:
  Lambda reports failed SQS records.
  SQS redrive policy moves repeatedly failed messages to the DLQ.

Lesson 34B:
  SQS retry can run the same handler code again.
  Retry is safe only if the handler's side effects are idempotent.
```

Lesson 34C covers the operational decision model:

```text
A message is now in the DLQ.
Should we replay it, discard it, archive it, or fix code/data first?
```

The main rule is:

```text
A DLQ is quarantine, not automatic recovery.
```

Blindly replaying DLQ messages can recreate the same failure, repeat side
effects, increase cost, and hide the real defect.

This is tutorial evidence only. It is not AWS deployment code and not Energy
Data Lakehouse implementation evidence.

---

## Current project context

The current `sqs_trade_handler` has a useful boundary for this lesson:

```text
Validation/business rejection:
  handled
  not returned in batchItemFailures
  no SQS retry

persist_trade(...) exception:
  retryable failure
  returned in batchItemFailures
  may eventually reach the DLQ
```

The important handler shape is:

```python
try:
    persist_trade(trade)
except Exception:
    logger.exception("Failed to persist trade message_id=%s", message_id)
    batch_item_failures.append(batch_item_failure(message_id))
    continue
```

That means the DLQ should mainly contain messages that repeatedly failed the
retryable persistence path, not known-invalid business messages that the handler
already treated as handled.

A message reaching the DLQ is not proof that the message body is wrong. It may
mean:

- the downstream dependency was unavailable;
- the handler had a bug;
- persistence partially succeeded and then failed;
- idempotency logic rejected a duplicate;
- configuration was wrong;
- the message was genuinely unprocessable.

34C is about classifying those possibilities before deciding what to do.

---

## DLQ is quarantine, not automatic recovery

A dead-letter queue is where SQS isolates messages that could not be processed
successfully after repeated receives.

The wrong mental model is:

```text
Message is in DLQ
  -> replay everything
  -> hope it works
```

The correct model is:

```text
Message is in DLQ
  -> inspect evidence
  -> classify failure cause
  -> check whether code/config/data changed
  -> check idempotency safety
  -> decide replay, discard, archive, or fix-first
```

A DLQ preserves failed work for analysis. It does not repair payloads, fix
handler bugs, or make side effects idempotent.

---

## How messages reach the DLQ

The lifecycle is:

```text
Source SQS queue
  -> Lambda receives message
  -> handler reports failure in batchItemFailures
  -> message becomes visible again after visibility timeout
  -> message is received again
  -> receive count increases
  -> repeated failures continue
  -> maxReceiveCount threshold is reached
  -> SQS moves the message to the DLQ
```

The critical ownership boundary is:

```text
Lambda reports failed records.
SQS redrive policy moves repeatedly failed messages to the DLQ.
```

The Lambda handler should not pretend to implement the DLQ itself.

---

## What to inspect before replay

Before replaying messages from a DLQ, inspect enough evidence to classify the
failure.

| Evidence | Why it matters |
|---|---|
| Message body | Confirms whether the payload is malformed, incomplete, stale, or business-invalid |
| Message attributes | May contain correlation IDs, schema version, producer name, or trace metadata |
| Lambda logs | Shows the exception or rejection path that caused failure |
| Message ID | Allows correlation with handler logs and test fixtures |
| Approximate receive count | Shows how many failed attempts occurred before DLQ movement |
| Handler version | Confirms whether the failing code has since been fixed |
| Producer version | Confirms whether the producer is still emitting bad messages |
| S3 artifact state | Shows whether a partial artifact was already written |
| DynamoDB status state | Shows whether the message was already processed or partially recorded |
| Message age | Confirms whether the event is still valid to process |
| Downstream health | Distinguishes temporary dependency outage from bad message data |

Do not rely only on the DLQ message body. The body tells you what was being
processed. Logs and durable state tell you how far processing got.

---

## Failure classification table

Classify messages before choosing an action.

| Failure class | Example | Replay candidate? | Reason |
|---|---|---:|---|
| Temporary dependency outage | S3 or DynamoDB unavailable | Yes | Replay may succeed after recovery |
| Handler bug | Valid message crashes old code | Maybe | Replay only after the code fix is deployed |
| Configuration error | Missing bucket/table name | Maybe | Replay only after configuration is corrected |
| Malformed technical input | Body is not valid JSON | No | Replay will not repair the payload |
| Missing required field | `trade_id` absent | Usually no | Producer/data issue must be fixed first |
| Invalid business value | `volume_mwh` is zero or negative | Usually no | This is a business rejection, not a transient fault |
| Unsupported schema version | Producer sent a newer schema | Maybe | Replay only after consumer supports the schema |
| Duplicate already processed | Conditional write rejects duplicate | Usually no | Treat as idempotent success if contract allows |
| Partial persistence | S3 written, DynamoDB failed | Maybe | Replay only after checking idempotency and state |
| Unknown error pattern | No clear cause | No bulk replay | Investigate before replaying |
| Stale event | Message is too old to act on | Usually no | Processing may be logically unsafe |

The replay test is:

```text
Can replay produce a better result than the original attempts?
```

If the answer is no, replay is noise.

---

## Replay, discard, archive, or fix-first decision table

| Situation | Decision | Required action |
|---|---|---|
| Dependency outage is resolved | Replay | Start with a small sample, monitor errors and DLQ depth |
| Handler bug is fixed | Replay carefully | Replay a small sample before bulk redrive |
| Configuration issue is fixed | Replay carefully | Confirm the correct environment/config is active |
| Message is malformed JSON | Discard or archive | Fix producer; do not replay unchanged message |
| Required field is missing | Discard, archive, or manual review | Fix producer/data contract first |
| Business rule violation is valid | Treat as handled rejection | Do not use DLQ as normal rejection storage |
| Message is duplicate and already processed | Archive evidence | Do not replay if final state is already correct |
| Message partially succeeded | Investigate first | Check S3/DynamoDB state before retrying |
| Failure cause is unknown | Fix-first | No bulk replay until cause is classified |
| Message is stale | Discard/archive | Follow retention and audit policy |

Replay is only one possible action. In many cases, the correct action is to fix
the producer, fix the handler, or archive the evidence.

---

## Replay safety checklist

Before redriving DLQ messages, answer these questions.

| Question | Required answer before replay |
|---|---|
| Has the root cause been identified? | Yes |
| Has the root cause been fixed or cleared? | Yes |
| Are handler side effects idempotent? | Yes |
| Could the message already have partially succeeded? | Known |
| Is the message still valid to process? | Yes |
| Is replay volume controlled? | Yes |
| Is monitoring active during replay? | Yes |
| Is there a stop condition if failures resume? | Yes |
| Is the replay decision auditable? | Yes |

If these answers are unknown, do not bulk replay.

---

## Controlled replay pattern

A safe replay process looks like this:

```text
1. Record current DLQ depth and source queue depth.
2. Inspect a representative sample of DLQ messages.
3. Group messages by failure cause.
4. Check logs and persistence state for each class.
5. Fix code, configuration, producer, or downstream issue.
6. Confirm idempotency safety.
7. Replay a very small sample.
8. Monitor Lambda errors, source queue depth, DLQ depth, and persistence records.
9. Increase replay volume only after sample replay succeeds.
10. Archive or discard messages that should not be replayed.
```

This is controlled recovery.

The weak version is:

```text
Replay everything and hope.
```

That is not architecture. That is gambling with production state.

---

## Why blind replay is dangerous

Blind replay can cause several problems.

| Risk | Consequence |
|---|---|
| Same bug still exists | Messages fail again and return to DLQ |
| Bad payload unchanged | Replay cannot repair malformed data |
| Non-idempotent S3 writes | Duplicate artifacts may be created |
| Non-idempotent DynamoDB writes | Status records may be overwritten or duplicated |
| Downstream dependency still unhealthy | Replay adds more load during an incident |
| Message is stale | System processes data that should no longer be applied |
| Bulk replay too large | Lambda concurrency, downstream throttling, and cost can spike |
| No monitoring | Replay failure is not detected quickly |

The key point:

```text
Replay multiplies the current design.
If the design is still wrong, replay multiplies the damage.
```

---

## Redrive limitations

SQS DLQ redrive is useful, but it is not a transformation step.

Important operational constraints:

```text
Redrive moves messages.
Redrive does not fix messages.
Redrive does not modify message payloads.
Redrive does not add idempotency to the consumer.
```

If a message is malformed, replaying it unchanged usually recreates the same
failure.

If the handler has not changed, replaying may recreate the same exception.

If persistence is not idempotent, replaying may repeat side effects.

---

## Retention-period considerations

DLQ retention is not just housekeeping. It affects whether you still have time
to investigate failed messages.

A practical rule:

```text
Set DLQ retention longer than the source queue retention.
```

Reason:

```text
A message may spend time in the source queue before it moves to the DLQ.
If the DLQ retention period is too short, evidence can expire before operators investigate it.
```

For this tutorial, do not configure queues. Just understand the architecture
implication:

```text
DLQ without retention planning can lose failure evidence.
```

---

## Current-handler examples

### Non-retryable business rejection

A message with an invalid business value should normally be treated as handled:

```text
SQS message body:
  trade_id=TRD-1001
  product=UK Power
  volume_mwh=0

Handler result:
  validation fails
  rejection is logged
  message ID is not returned in batchItemFailures
  no SQS retry
  no DLQ movement from this path
```

This is correct because retrying the same unchanged message will not make
`volume_mwh=0` valid.

### Retryable persistence failure

A valid-looking message may fail during persistence:

```text
SQS message body:
  trade_id=TRD-1001
  product=UK Power
  volume_mwh=250

Handler result:
  validation succeeds
  persist_trade(...) raises
  message ID is returned in batchItemFailures
  SQS/Lambda can retry the message
  repeated failure may eventually move the message to the DLQ
```

This is a DLQ candidate because the message may be valid but the system could
not complete processing.

### DLQ decision after repeated persistence failure

If that message appears in the DLQ, do not assume the body is bad.

Inspect:

```text
Was S3 unavailable?
Was DynamoDB throttled?
Did persist_trade(...) partially complete?
Was there a handler bug?
Was the message already processed on a previous attempt?
```

The replay decision depends on those answers.

---

## Relationship to Lesson 34A

Lesson 34A answered:

```text
Who retries failed SQS messages?
Who moves messages to the DLQ?
```

Answer:

```text
Lambda reports failed records.
SQS/Lambda retry mechanics redeliver them.
SQS redrive policy moves repeatedly failed messages to the DLQ.
```

Lesson 34C builds on that:

```text
Once a message is in the DLQ, what is the safe operational response?
```

The DLQ is not the end of the architecture. It is the start of recovery work.

---

## Relationship to Lesson 34B

Lesson 34B answered:

```text
What happens when SQS retry re-runs side effects?
```

Answer:

```text
The same handler path may run again.
The side effects behind persist_trade(...) must be idempotent.
```

Lesson 34C applies that during replay:

```text
Before replaying DLQ messages, confirm side effects are safe to repeat.
```

This is why deterministic S3 keys and DynamoDB conditional writes matter. They
make replay safer, but they do not remove the need for inspection and judgement.

---

## Relationship to Step Functions reconciliation

SQS DLQ handling and Step Functions reconciliation solve related but different
problems.

| Area | SQS DLQ handling | Step Functions reconciliation |
|---|---|---|
| Failure unit | Individual message | Workflow execution |
| Retry owner | SQS/Lambda event source mapping and SQS redrive policy | Step Functions state machine |
| Failure evidence | DLQ message, receive count, logs, persistence state | Execution history, state input/output, terminal state |
| Recovery action | Inspect, classify, replay/discard/archive/fix-first | Catch, Pass, Fail, Succeed, manual reconciliation path |
| Main risk | Blind replay repeats failure or side effects | Workflow reaches wrong terminal outcome |
| Design requirement | Idempotent consumer and controlled redrive | Explicit failure path and reconciliation state |

Common principle:

```text
Partial success is normal.
Recovery must be designed, observable, and deliberate.
```

---

## What not to implement in this lesson

Do not add:

- AWS deployment code;
- Terraform;
- queue policies;
- boto3 redrive calls;
- SQS queue creation;
- Lambda event source mapping configuration;
- real S3 or DynamoDB code in `sqs_trade_handler.py`;
- bulk replay scripts.

This lesson is a decision model, not an automation lesson.

---

## SAP-C02 relevance

Lesson 34C maps strongly to SAP-C02 architecture judgement.

| SAP-C02 theme | Lesson 34C relevance |
|---|---|
| Decoupling | SQS isolates producers from consumers |
| Resilience | DLQs prevent repeated poison messages from consuming retry capacity indefinitely |
| Operational excellence | Failed messages require alarms, inspection, classification, and controlled replay |
| Reliability | Replay should happen only after root cause and idempotency checks |
| Cost control | Blind replay can create repeated processing cost and downstream load |
| Governance | Replay decisions should be auditable and deliberate |
| Managed-service boundary | SQS moves/redrives messages; Lambda code should not fake DLQ mechanics |

The exam trap is:

```text
Add a DLQ and replay everything.
```

The better answer is:

```text
Add a DLQ, monitor it, classify failures, fix the cause, confirm idempotency, and replay only safe messages under controlled conditions.
```

---

## Lesson boundary

Lesson 34C is complete when you can explain:

- why a DLQ is quarantine, not automatic recovery;
- how messages reach the DLQ;
- what evidence to inspect before replay;
- when to replay;
- when to discard or archive;
- when to fix code/data first;
- why blind replay is dangerous;
- how Lesson 34C builds on Lessons 34A and 34B.

No production code is required.

---

## Reference notes

Official AWS documentation used for this note:

- Amazon SQS dead-letter queues and `maxReceiveCount`:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html>
- Amazon SQS DLQ redrive limitations:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html>
- Amazon SQS DLQ retention behaviour:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/setting-up-dead-letter-queue-retention.html>
- Lambda with SQS and partial batch response:
  <https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html>
- Lambda SQS error handling and `ReportBatchItemFailures`:
  <https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html>

---

## Acronym legend

| Acronym | Meaning |
|---|---|
| AWS | Amazon Web Services |
| DLQ | Dead-letter queue |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda serverless function service |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam code |
| SQS | Amazon Simple Queue Service |
