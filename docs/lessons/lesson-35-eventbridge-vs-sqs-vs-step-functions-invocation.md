# Lesson 35: EventBridge vs SQS vs Direct Step Functions Invocation

## Objective

This lesson explains when to use:

```text
EventBridge
SQS
Direct Step Functions invocation
```

The goal is not to memorise service definitions. The goal is to choose the
right integration pattern for the workload.

Compact rule:

```text
EventBridge:
  publish facts

SQS:
  queue work

Step Functions:
  orchestrate workflows
```

This is tutorial evidence only. It does not deploy AWS resources, add Terraform,
create queues, create event buses, or modify handler code.

---

## Short decision rule

Use this first-pass rule:

| Pattern | Use when the producer means... | Best phrase |
| --- | --- | --- |
| EventBridge | Something happened | Publish facts |
| SQS | Something needs to be processed | Queue work |
| Direct Step Functions | This known workflow must start | Orchestrate workflows |

The difference is not cosmetic. It changes coupling, failure handling,
observability, and operational ownership.

---

## EventBridge mental model

Use EventBridge when the producer is publishing a **fact**.

```text
TradeReceived happened.
TradeValidated happened.
TradeRejected happened.
PositionLimitBreached happened.
```

The producer should not need to know every consumer that reacts to the event.

Conceptual shape:

```text
Producer
  -> EventBridge event bus
      -> Rule: persist trade
      -> Rule: notify risk
      -> Rule: update audit log
```

EventBridge event buses receive events and route matching events to zero or more
targets using rules. That makes EventBridge a good fit for event-driven fan-out
and loose coupling.

### EventBridge event shape example

This is an event fact:

```python
import json

eventbridge_entry = {
    "Source": "tutorial.trade",
    "DetailType": "TradeReceived",
    "Detail": json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "UK Power",
            "volume_mwh": 250,
        }
    ),
    "EventBusName": "trade-events",
}
```

The important part is the language:

```text
TradeReceived
```

That is a fact. It says what happened. It does not say:

```text
Run this exact worker.
Start this exact workflow.
Persist this exact record now.
```

### EventBridge consumer shape

A Lambda target might receive an event like this:

```python
def eventbridge_trade_handler(event, context):
    trade = event["detail"]

    trade_id = trade["trade_id"]
    product = trade["product"]
    volume_mwh = trade["volume_mwh"]

    return {
        "status": "received",
        "trade_id": trade_id,
        "product": product,
        "volume_mwh": volume_mwh,
    }
```

This works when the handler is reacting to an event. It is less appropriate if
the goal is durable worker-style processing with queue depth, visibility timeout,
and message-level DLQ handling.

### EventBridge is a good fit when

| Requirement | Fit |
| --- | --- |
| Multiple consumers may react to the same event | Strong |
| Producer should not know downstream consumers | Strong |
| Event routing by pattern is important | Strong |
| Business events need fan-out | Strong |
| Backpressure and worker control are primary | Weak |
| Per-message visibility timeout is needed | Weak |

---

## SQS mental model

Use SQS when the producer is queuing **work**.

```text
Process this trade.
Persist this result.
Send this notification.
Transform this file.
```

SQS is a queue. It buffers messages until consumers process them. It is the
right fit when producers and consumers operate at different speeds.

Conceptual shape:

```text
Producer
  -> SQS queue
      -> Lambda consumer
          -> process message
          -> return batchItemFailures for retryable failures
```

SQS Standard queues provide at-least-once delivery. That means a message can be
delivered more than once. The consumer must be idempotent.

### SQS message shape example

This is work to process:

```python
import json

sqs_message_body = json.dumps(
    {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
        "action": "process_trade",
    }
)
```

The important part is the intent:

```text
Process this trade.
```

That is work, not a general domain fact.

### SQS Lambda handler shape

This is the style already used in the tutorial:

```python
def sqs_trade_handler(event, context):
    batch_item_failures = []

    for record in event.get("Records") or []:
        message_id = record.get("messageId")
        body = record.get("body")

        try:
            trade = json.loads(body)
            persist_trade(trade)
        except Exception:
            batch_item_failures.append(
                {"itemIdentifier": message_id}
            )

    return {"batchItemFailures": batch_item_failures}
```

The key contract is:

```text
Do not return messageId:
  message handled

Return messageId in batchItemFailures:
  retry this message
```

SQS is the right tool when failed work should retry independently of successful
work.

### SQS is a good fit when

| Requirement | Fit |
| --- | --- |
| Buffering between producer and consumer | Strong |
| Consumer may be slower than producer | Strong |
| Message-level retry is needed | Strong |
| DLQ after repeated failed processing | Strong |
| Partial batch failure response matters | Strong |
| Fan-out to many unrelated consumers | Weaker than EventBridge |
| Multi-step workflow execution history | Weaker than Step Functions |

---

## Direct Step Functions mental model

Use direct Step Functions invocation when the caller knows the exact workflow
that must start.

```text
Start the trade-processing workflow.
Start the persistence-reconciliation workflow.
Start the AI-enrichment workflow.
```

Step Functions is the right tool when the process has visible steps, branching,
retry/catch logic, and terminal outcomes.

Conceptual shape:

```text
Caller
  -> StartExecution
      -> State machine
          -> Validate
          -> Choice
          -> Persist
          -> Retry/Catch
          -> Succeed/Fail
```

A Step Functions execution receives JSON input and produces JSON output. An
execution can be started by API, SDK, CLI, console, EventBridge, API Gateway, or
another workflow.

### Step Functions execution input example

This is workflow input:

```python
import json

state_machine_input = {
    "trade": {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
    },
    "requested_by": "api",
    "correlation_id": "req-123",
}
```

If calling the Step Functions API directly, the conceptual call shape is:

```python
stepfunctions_client.start_execution(
    stateMachineArn="arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing",
    name="trade-TRD-1001",
    input=json.dumps(state_machine_input),
)
```

Do not add this to the tutorial repo for Lesson 35. This is only to show the
contract difference.

### Step Functions state machine shape

A small workflow shape:

```json
{
  "StartAt": "ValidateTrade",
  "States": {
    "ValidateTrade": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:eu-west-2:123456789012:function:validate-trade",
      "Next": "IsValid"
    },
    "IsValid": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.validation.is_valid",
          "BooleanEquals": true,
          "Next": "PersistTrade"
        }
      ],
      "Default": "Rejected"
    },
    "PersistTrade": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:eu-west-2:123456789012:function:persist-trade",
      "Retry": [
        {
          "ErrorEquals": ["States.ALL"],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "ReconciliationRequired"
        }
      ],
      "Next": "Succeeded"
    },
    "Rejected": {
      "Type": "Succeed"
    },
    "ReconciliationRequired": {
      "Type": "Fail"
    },
    "Succeeded": {
      "Type": "Succeed"
    }
  }
}
```

This is workflow orchestration. SQS does not give this execution history. EventBridge
does not give this step-by-step process model.

### Direct Step Functions is a good fit when

| Requirement | Fit |
| --- | --- |
| Multi-step process | Strong |
| Branching by validation result | Strong |
| Retry/Catch per workflow state | Strong |
| Execution history is required | Strong |
| Human review or reconciliation path exists | Strong |
| Simple one-step message processing | Often too heavy |
| Generic event fan-out | Weaker than EventBridge |

---

## Decision table

| Question | Prefer EventBridge | Prefer SQS | Prefer direct Step Functions |
| --- | --- | --- | --- |
| What is the producer doing? | Publishing a fact | Enqueuing work | Starting a known workflow |
| Does producer know the consumer? | No | Knows queue/work contract | Yes |
| Is fan-out important? | Strong fit | Possible, not primary | Weak fit |
| Is buffering/backpressure important? | Weak fit | Strong fit | Weak fit |
| Is message-level retry needed? | Limited target retry | Strong fit | Not the model |
| Is orchestration needed? | Not directly | Not directly | Strong fit |
| Is execution history needed? | No | No | Strong fit |
| Is DLQ central to failure handling? | Target delivery DLQ possible | Strong fit | Usually workflow failure path |
| Best failure unit | Event delivery | Individual message | Workflow execution |
| Best phrase | Something happened | Do this work | Run this workflow |

---

## Failure model comparison

| Failure area | EventBridge | SQS | Direct Step Functions |
| --- | --- | --- | --- |
| Target unavailable | EventBridge retry/DLQ for event target delivery | Message remains available for retry after visibility timeout | Task-level Retry/Catch |
| Consumer code raises | Target-specific failure handling | Message can retry and eventually DLQ | State can retry/catch/fail |
| Partial batch handling | Not the core model | Core SQS/Lambda concern | Not the model |
| Poison message | Not primary | Core DLQ concept | Bad workflow input or task failure |
| Operational evidence | Event delivery metrics/logs | Queue depth, DLQ depth, receive count, Lambda logs | Execution history and state transitions |
| Recovery style | Re-drive/replay event depending target and archive design | Inspect DLQ, classify, replay safely | Inspect execution history, rerun or compensate |

### Failure example: same trade in each pattern

#### EventBridge failure

```text
trade.received event published
  -> matching rule tries to invoke target
  -> target delivery fails
  -> EventBridge retry policy / target DLQ may apply
```

The failure is event delivery to a target.

#### SQS failure

```text
trade-processing message queued
  -> Lambda receives message
  -> persist_trade(...) raises
  -> handler returns messageId in batchItemFailures
  -> SQS retries message
  -> message may eventually reach DLQ
```

The failure is message processing.

#### Step Functions failure

```text
StartExecution called
  -> ValidateTrade succeeds
  -> PersistTrade times out
  -> Retry exhausted
  -> Catch routes to reconciliation or Fail
```

The failure is workflow execution.

---

## Coupling comparison

| Pattern | Coupling level | Explanation |
| --- | ---: | --- |
| EventBridge | Lowest | Producer emits a fact; consumers can change independently |
| SQS | Medium-low | Producer knows the queue/work contract, not consumer implementation |
| Direct Step Functions | Highest | Caller knows and starts a specific workflow |

High coupling is not automatically wrong.

It is correct when the caller truly owns the business process:

```text
API request received
  -> start this exact trade-processing workflow
```

Low coupling is better when the producer should not own downstream reactions:

```text
TradeAccepted happened
  -> risk, audit, reporting, and notification systems may react independently
```

---

## Applying the decision to the trade tutorial

### Case 1: Trade received as a business fact

Use EventBridge.

```python
eventbridge_entry = {
    "Source": "tutorial.trade",
    "DetailType": "TradeReceived",
    "Detail": json.dumps(
        {
            "trade_id": "TRD-1001",
            "product": "UK Power",
            "volume_mwh": 250,
        }
    ),
    "EventBusName": "trade-events",
}
```

Use this when the important thing is:

```text
TradeReceived happened.
```

Possible consumers:

```text
validate trade
audit event
notify monitoring
start workflow
```

The producer does not need to know all of them.

---

### Case 2: Trade must be processed by a worker

Use SQS.

```python
sqs_message_body = json.dumps(
    {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
        "work_type": "process_trade",
    }
)
```

Use this when the important thing is:

```text
This trade-processing work must be performed eventually.
```

This is strongest when:

```text
traffic may spike
workers may be slower than producers
retry should happen per message
DLQ handling matters
```

---

### Case 3: Trade needs a visible multi-step workflow

Use direct Step Functions invocation.

```python
execution_input = {
    "trade": {
        "trade_id": "TRD-1001",
        "product": "UK Power",
        "volume_mwh": 250,
    },
    "correlation_id": "req-123",
}
```

Use this when the important thing is:

```text
Run the trade-processing workflow.
```

This is strongest when the process has:

```text
validate
branch
persist
retry
catch
reconcile
succeed/fail
```

---

### Case 4: EventBridge starts Step Functions

This is a valid hybrid.

```text
Producer
  -> EventBridge: TradeReceived
      -> Rule starts Step Functions workflow
```

This is useful when the producer should publish a fact, while the platform decides
that one reaction to the fact is starting a workflow.

The producer says:

```text
TradeReceived happened.
```

The EventBridge rule says:

```text
When TradeReceived happens, start trade-processing workflow.
```

This is often cleaner than making the producer call Step Functions directly.

---

### Case 5: Step Functions sends work to SQS

This is also valid.

```text
Step Functions workflow
  -> validate and branch
  -> send message to SQS for asynchronous worker processing
```

Use this when part of the workflow should be buffered or processed by workers.

Example:

```text
Validate trade
  -> if valid, queue enrichment work
  -> continue or wait depending design
```

---

## Common wrong choices

### Wrong choice 1: Using EventBridge as a work queue

Weak design:

```text
Producer
  -> EventBridge event
      -> one Lambda worker expected to process every item like a queue
```

Problem:

```text
You probably wanted queue depth, visibility timeout, per-message retry,
worker backpressure, and DLQ handling.
```

Better:

```text
Producer
  -> SQS
      -> Lambda worker
```

---

### Wrong choice 2: Using SQS for pure business fan-out

Weak design:

```text
Producer
  -> one queue
      -> one consumer
          -> manually call all other interested systems
```

Problem:

```text
The first consumer becomes a hidden orchestrator and fan-out hub.
```

Better:

```text
Producer
  -> EventBridge: TradeAccepted
      -> audit target
      -> reporting target
      -> notification target
```

---

### Wrong choice 3: Starting Step Functions for trivial single-step work

Weak design:

```text
API
  -> StartExecution
      -> one Lambda task
      -> Succeed
```

Problem:

```text
Step Functions may be unnecessary operational overhead if there is no
branching, retry policy, compensation, or execution-history requirement.
```

Better:

```text
API
  -> Lambda
```

or:

```text
API
  -> SQS
      -> Lambda worker
```

depending on whether asynchronous buffering is needed.

---

### Wrong choice 4: Using SQS when workflow state matters

Weak design:

```text
SQS message
  -> Lambda validates
  -> Lambda persists
  -> Lambda branches
  -> Lambda catches errors
  -> Lambda decides reconciliation
```

Problem:

```text
The Lambda function becomes a hidden state machine.
```

Better:

```text
Step Functions
  -> Validate
  -> Choice
  -> Persist
  -> Catch
  -> Reconcile
  -> Succeed/Fail
```

---

## SAP-C02 relevance

SAP-C02 questions usually describe constraints, not service names. Read the
scenario language.

| Scenario phrase | Likely pattern |
| --- | --- |
| Multiple systems need to react to the same business event | EventBridge |
| Producer should not know consumers | EventBridge |
| Route events based on event content | EventBridge |
| Decouple producer and consumer with buffering | SQS |
| Consumers are slower than producers | SQS |
| Retry failed messages and isolate poison messages | SQS |
| Process each unit of work independently | SQS |
| Multi-step workflow with branching | Step Functions |
| Workflow-level retry/catch and terminal state | Step Functions |
| Execution history is required | Step Functions |
| Start known business process from API request | Direct Step Functions invocation |
| Publish fact and let platform decide reactions | EventBridge, possibly targeting Step Functions |

The exam trap is choosing based on the word "event" alone.

Better reasoning:

```text
Is this a fact, work, or a workflow?
```

---

## Lesson boundary

This lesson is a decision note.

It does not:

```text
deploy EventBridge
deploy SQS
deploy Step Functions
write Terraform
add boto3 calls
modify handlers
add new tests
```

It explains how to choose the integration pattern before implementation.

---

## Summary

Use this rule:

```text
EventBridge:
  publish facts

SQS:
  queue work

Step Functions:
  orchestrate workflows
```

In architecture terms:

| Pattern | Main strength |
| --- | --- |
| EventBridge | Loose event routing and fan-out |
| SQS | Durable work buffering and message-level retry |
| Step Functions | Explicit workflow orchestration and execution history |

A good solution architect does not ask:

```text
Which one is newest?
```

A good solution architect asks:

```text
What is the producer trying to express?
What failure model do we need?
How much coupling is acceptable?
What operational evidence will we need when it fails?
```

---

## Acronym legend

| Acronym | Meaning |
| --- | --- |
| API | Application Programming Interface |
| AWS | Amazon Web Services |
| DLQ | Dead-Letter Queue |
| FIFO | First-In, First-Out |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda serverless function service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam code |
| SDK | Software Development Kit |
| SQS | Amazon Simple Queue Service |
