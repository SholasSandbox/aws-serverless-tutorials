# Lesson 36: Choosing the Right Serverless Entry Point

## Objective

Choose the correct entry point for a serverless workload by identifying what the
caller is trying to do before selecting an AWS service.

Use this compact rule:

```text
API Gateway:
  expose an HTTP API

EventBridge:
  publish an internal business event

SQS:
  accept durable asynchronous work

Step Functions:
  start a known workflow
```

By the end of this lesson, you should be able to explain:

- what contract each entry point exposes;
- what the caller expects after submitting input;
- how request-response differs from asynchronous acceptance;
- how an external boundary differs from an internal service boundary;
- why these services may be combined rather than treated as four mutually
  exclusive choices;
- which entry point fits each trade-processing scenario in the tutorial.

This is a design-decision lesson. It does not add production code, AWS
resources, Terraform, `boto3` calls, or new tests.

---

## How This Connects Lessons 34 and 35

Lessons 34A-34C examined what happens after work has already entered an SQS
queue.

```text
message submitted
    ↓
consumer receives message
    ↓
processing fails
    ↓
message becomes visible again
    ↓
retry
    ↓
possible poison message
    ↓
DLQ
    ↓
operator decides whether and how to replay
```

Those lessons established that choosing SQS carries an operational model:

- at-least-once delivery;
- possible duplicate processing;
- visibility timeout management;
- retry behaviour;
- poison-message isolation;
- dead-letter queue handling;
- replay decisions;
- idempotent consumer design.

Lesson 35 then asked:

```text
Should this integration:

publish a fact,
queue work,
or orchestrate a workflow?
```

Its compact decision rule was:

```text
EventBridge:
  publish facts

SQS:
  queue work

Step Functions:
  orchestrate workflows
```

Lesson 36 moves one architectural boundary earlier.

```text
caller
  ↓
entry point
  ↓
integration pattern
  ↓
processing components
```

It asks:

```text
How should input enter the system in the first place?
```

That distinction matters because the entry point defines the first contract the
system presents to its caller:

| Entry point | First contract presented to the caller |
| --- | --- |
| API Gateway | HTTP request and HTTP response contract |
| EventBridge | Business-event envelope |
| SQS | Queue-message contract |
| Step Functions | State-machine execution input |

The entry point then influences:

- caller coupling;
- authentication and authorisation boundaries;
- latency expectations;
- durability expectations;
- retry ownership;
- failure reporting;
- message or request shape;
- the responsibility of the first Lambda function.

This lesson also prepares the next implementation boundary:

```text
Lesson 37:
  API-facing Lambda
  versus
  internal service Lambda
```

Lesson 36 chooses the doorway. Lesson 37 will decide what the first Lambda
behind that doorway should understand and own.

---

## Short Decision Rule

Ask what the caller believes it is doing.

| Caller intention | Preferred entry point |
| --- | --- |
| "Perform an operation through HTTP and return an HTTP response." | API Gateway |
| "This internal business fact occurred." | EventBridge |
| "Process this work when capacity is available." | SQS |
| "Run this specific multi-step process." | Direct Step Functions invocation |

A useful decision sequence is:

```text
Does the caller require an HTTP contract?
  ├── Yes → API Gateway
  └── No
       ↓
Is the caller announcing a reusable business fact?
  ├── Yes → EventBridge
  └── No
       ↓
Is durable buffering and consumer-paced processing the main requirement?
  ├── Yes → SQS
  └── No
       ↓
Is the caller intentionally starting a known workflow?
  ├── Yes → Step Functions
  └── Re-examine the requirement
```

This is a design aid, not an absolute algorithm. Real architectures often
combine the services because each service can occupy a different boundary.

For example:

```text
External caller
  → API Gateway
  → API-facing Lambda
  → SQS
  → worker Lambda
```

Here:

- API Gateway is the external entry point;
- SQS is the durable asynchronous handoff;
- Lambda performs bounded processing.

Another example:

```text
Internal trade-capture service
  → EventBridge
  → Step Functions
  → task Lambdas
```

Here:

- EventBridge accepts and routes the business fact;
- Step Functions orchestrates the resulting workflow;
- Lambdas implement individual workflow tasks.

---

## API Gateway Mental Model

Use API Gateway when the system must expose an HTTP API.

The caller thinks in terms of:

```text
HTTP method
path
headers
query parameters
authentication
request body
HTTP status code
response body
```

A client may submit a trade using a request such as:

```http
POST /trades HTTP/1.1
Content-Type: application/json
Authorization: Bearer <token>

{
  "trade_id": "TRD-1001",
  "product": "POWER",
  "volume_mwh": 25
}
```

The caller expects an HTTP response.

A synchronous success response might be:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "trade_id": "TRD-1001",
  "status": "valid"
}
```

A validation failure might be:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "volume_mwh must be greater than zero",
  "request_id": "req-123"
}
```

An asynchronously accepted request might return:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "trade_id": "TRD-1001",
  "status": "accepted_for_processing",
  "request_id": "req-123"
}
```

### What choosing API Gateway means

Choosing API Gateway means that HTTP is part of the system boundary.

The design must consider:

- methods and resource paths;
- authentication and authorisation;
- throttling and quotas;
- request validation;
- content types;
- client-visible error responses;
- API versioning;
- synchronous latency;
- protection from malformed or hostile traffic;
- mapping the external request into an internal domain shape.

A simplified flow is:

```text
External client
    ↓ HTTP
API Gateway
    ↓ Lambda event
API-facing Lambda
    ↓ normalized internal input
Internal processing
```

The API-facing Lambda usually understands HTTP-specific information such as:

```python
http_method = event["requestContext"]["http"]["method"]
raw_body = event.get("body")
request_id = event["requestContext"]["requestId"]
```

This is only a code-shaped illustration of the event boundary. Lesson 36 does
not add or change handler code.

### API Gateway is not the processing engine

API Gateway exposes the HTTP boundary. It does not mean that the entire
business process should complete synchronously behind one request.

After validating and normalising an HTTP request, the system may hand off work
to another service.

```text
API Gateway
  → API-facing Lambda
  → SQS
```

This is suitable when durable asynchronous processing is required.

```text
API Gateway
  → API-facing Lambda
  → Step Functions
```

This is suitable when the request intentionally starts a known workflow.

```text
API Gateway
  → API-facing Lambda
  → EventBridge
```

This can be suitable when the request results in a business fact that multiple
internal consumers may react to.

### Trade example: synchronous validation

Requirement:

```text
A trade-entry screen needs immediate validation feedback before the user can
continue.
```

Design:

```text
Trading UI
    ↓ POST /trades/validate
API Gateway
    ↓
API-facing Lambda
    ↓
validate trade
    ↓
200 valid or 400 invalid
```

The work is short and the result is immediately useful to the caller.

### Trade example: asynchronous submission

Requirement:

```text
A submitted trade must pass through several internal processing steps, but the
user interface should not wait for the full workflow.
```

Design:

```text
Trading UI
    ↓ POST /trades
API Gateway
    ↓
API-facing Lambda
    ↓
validate request envelope
    ↓
SQS or Step Functions
    ↓
202 Accepted
```

The HTTP response confirms acceptance, not completion.

That distinction must be explicit:

```text
accepted for processing
≠
processing completed successfully
```

---

## EventBridge Entry-Point Mental Model

Use EventBridge when an internal producer publishes that a business fact has
occurred.

The producer is not primarily asking a named consumer to perform an operation.
It is announcing a fact that may be useful to one or more consumers.

A business-event envelope may look like:

```json
{
  "source": "trade.capture",
  "detail-type": "TradeCaptured",
  "detail": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  }
}
```

The important wording is:

```text
TradeCaptured occurred.
```

not:

```text
Call the trade validation Lambda.
```

The first statement describes a business fact. The second describes a specific
technical target and creates tighter coupling.

### Business events are usually named as facts

Useful event names often use past tense:

```text
TradeCaptured
TradeValidated
TradeRejected
TradePersisted
TradeCancelled
TradeAmended
```

These names describe completed state transitions or observations.

Command-shaped names indicate a different intention:

```text
ValidateTrade
PersistTrade
GenerateReport
ReplayTrade
```

These represent work to perform and may be better expressed as queue messages,
workflow starts, or task inputs.

### EventBridge supports loose coupling

A producer can publish one event without knowing every downstream consumer.

```text
Trade Capture
    ↓ TradeCaptured
EventBridge
    ├── Risk position update
    ├── Compliance screening
    ├── Audit archive
    └── Trade-processing workflow
```

The consumers may evolve independently.

This is a different kind of decoupling from SQS:

```text
EventBridge:
  decouples the publisher from interested consumers

SQS:
  decouples the producer's rate from the consumer's processing rate
```

### EventBridge as an entry point

EventBridge may be the first managed boundary for an internal AWS producer.

```text
Internal trade-capture service
    ↓ business event
EventBridge
    ↓ matching rule
Step Functions trade-processing workflow
```

The event enters the architecture as a fact. A rule then routes that fact to
one or more targets.

### What EventBridge does not inherently provide

EventBridge is not a direct replacement for an SQS work queue.

It does not inherently mean:

- one worker must eventually process every item from a durable backlog;
- consumers should process at their own controlled rate;
- queue depth should represent outstanding work;
- operators should manage redrive from a work queue;
- a single consumer group should compete for messages;
- the publisher expects a processing response.

EventBridge has delivery and failure-handling features, but the architectural
model remains event routing rather than worker backlog management.

### Trade example: several consumers react to trade capture

Requirement:

```text
When a trade is captured, risk, compliance, audit, and reporting components may
need to react independently.
```

Design:

```text
Trade Capture
    ↓
EventBridge: TradeCaptured
    ├── Risk target
    ├── Compliance target
    ├── Audit target
    └── Reporting target
```

The producer publishes one fact rather than calling four consumers.

### Combining EventBridge and SQS

A common design is:

```text
Trade Capture
    ↓ TradeCaptured
EventBridge
    ├── SQS queue: risk work
    ├── SQS queue: compliance work
    └── audit archive target
```

EventBridge performs event routing and fan-out. Each SQS queue gives a consumer
its own durable backlog, retry behaviour, and operational isolation.

This combination is often stronger than forcing either service to solve both
problems.

---

## SQS Entry-Point Mental Model

Use SQS when a producer submits durable asynchronous work.

The producer is effectively saying:

```text
This work must be processed, but it does not need to complete during this
interaction.
```

A queue message might contain:

```json
{
  "trade_id": "TRD-1001",
  "operation": "validate_and_persist",
  "product": "POWER",
  "volume_mwh": 25
}
```

This is work-shaped input.

This tutorial primarily uses SQS Standard queue semantics. FIFO queues add
ordering and deduplication features, but application-level idempotency remains
important because a failure can occur after a business side effect and before
the consumer reports successful completion.

The message requests an operation:

```text
Validate and persist this trade.
```

### What choosing SQS means

Choosing SQS means accepting the queue-processing model studied in Lessons
34A-34C:

- producer and consumer run independently;
- messages remain available while consumers are unavailable;
- the queue can absorb temporary traffic spikes;
- consumers process at their own rate;
- processing failures can cause redelivery;
- duplicate processing is possible;
- consumers must be idempotent;
- poison messages may require DLQ handling;
- replay requires an operational decision.

```text
SQS entry point
    ↓
at-least-once delivery
    ↓
retry
    ↓
possible duplicate
    ↓
idempotent processing
    ↓
DLQ and replay operations
```

### Queue work, do not merely rename events

A strong SQS message usually describes work:

```text
ValidateTrade
PersistTrade
EnrichTrade
GenerateSettlementReport
ReplayRejectedTrade
```

A strong EventBridge event usually describes a fact:

```text
TradeCaptured
TradeValidated
TradePersisted
SettlementReportGenerated
TradeReplayRequested
```

The distinction is not mechanically enforced by AWS, but it helps preserve
clear contracts.

### What the sender should expect

The sender should not expect the processing result in the same interaction.

Successful submission to SQS means the message was accepted by the queue. It
does not mean the consumer completed the work.

```text
message accepted
≠
message processed
≠
result persisted
≠
business process completed
```

The eventual outcome must be exposed through another mechanism, such as:

- a DynamoDB status record;
- an S3 result artifact;
- a completion event on EventBridge;
- an SNS notification;
- a callback endpoint;
- a status API.

### Trade example: overnight bulk enrichment

Requirement:

```text
An overnight process exports 50,000 trades for enrichment. Downstream services
may throttle, and processing must survive temporary outages.
```

Design:

```text
Trade export process
    ↓
SQS
    ↓
Lambda consumers
    ↓
enrich trades
    ↓
S3 result artifacts
    ↓
DynamoDB processing status
```

SQS provides:

- buffering;
- consumer scaling;
- protection from downstream throttling;
- durable retention during consumer outages;
- failure isolation through a DLQ.

### Trade example: explicit work command

A queue message can make the requested operation clear:

```json
{
  "message_type": "ValidateTrade",
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "correlation_id": "corr-456"
}
```

A consumer receives the message and performs the bounded unit of work.

The consumer should not assume that receiving the message exactly once is
guaranteed. The correlation or idempotency key must support safe retries.

---

## Direct Step Functions Entry-Point Mental Model

Use direct Step Functions invocation when a trusted caller intentionally starts
a known workflow.

The caller knows:

- which workflow should run;
- the workflow's input contract;
- that several controlled steps may follow;
- that execution state and outcome matter.

Example workflow input:

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "requested_operation": "validate_and_persist",
  "correlation_id": "corr-456"
}
```

The caller is saying:

```text
Start the trade validation and persistence workflow.
```

### What choosing direct Step Functions invocation means

The caller is coupled to a named workflow contract.

```text
Trusted internal service
    ↓ StartExecution
Trade Processing State Machine
    ↓
Validate
    ↓
Choice
    ├── Persist accepted trade
    └── Persist rejected trade
    ↓
Record processing status
```

This coupling is acceptable when the workflow itself is the intended internal
service boundary.

### Direct invocation is suitable when

- the caller is trusted and internal;
- the caller intentionally selects the workflow;
- orchestration is the primary requirement;
- multiple ordered or conditional steps are expected;
- workflow execution identity is useful;
- retry, catch, timeout, and failure paths belong in the orchestration layer;
- queue-style buffering is not the main requirement.

### Direct invocation is weaker when

- many unknown consumers may need the same business fact;
- the producer should not know the workflow name;
- a large durable backlog must absorb bursts;
- consumer-paced queue processing is required;
- an external public HTTP contract is required;
- the operation is so small that orchestration adds no real value.

### Trade example: known validate-and-persist process

Requirement:

```text
Every submitted trade must follow a defined sequence:

validate
  → branch on valid or invalid
  → persist the appropriate artifact
  → update processing status
```

Design:

```text
Trusted internal trade service
    ↓
Step Functions
    ↓
ValidateTrade task
    ↓
Choice
    ├── valid → PersistAcceptedTrade
    └── invalid → PersistRejectedTrade
    ↓
UpdateTradeStatus
```

The workflow is explicit, ordered, observable, and designed around known
business steps.

### Step Functions does not replace every integration service

Step Functions coordinates work. It is not automatically the correct external
entry point, event bus, or work queue.

A combined design may be:

```text
External client
    ↓
API Gateway
    ↓
API-facing Lambda
    ↓
Step Functions
    ↓
workflow task Lambdas
```

Or:

```text
TradeCaptured
    ↓
EventBridge
    ↓
Step Functions
    ↓
workflow task Lambdas
```

Or:

```text
SQS backlog
    ↓
Lambda consumer
    ↓
Step Functions for qualifying complex cases
```

The service selected at each boundary should match the responsibility at that
boundary.

---

## Decision Table

| Decision factor | API Gateway | EventBridge | SQS | Direct Step Functions |
| --- | --- | --- | --- | --- |
| Primary purpose | Expose an HTTP API | Publish and route business facts | Accept durable asynchronous work | Start a known workflow |
| Typical caller | External or HTTP client | Internal event producer | Internal producer submitting work | Trusted internal service |
| Caller intention | Request an HTTP operation | Announce that something happened | Request eventual processing | Invoke a specific process |
| Contract shape | Method, path, headers, body, HTTP response | Source, event type, detail | Message body and attributes | Workflow input JSON |
| Immediate response expected | Usually an HTTP response | No business response | No processing response | Execution acknowledgement; result depends on invocation pattern |
| Main coupling reduced | Client from backend implementation | Publisher from consumers | Producer rate from consumer rate | Workflow definition from individual task implementation |
| Fan-out | Requires downstream design | Strong core pattern | One queue normally represents one consumer backlog | Controlled branching inside workflow |
| Durable backlog | Not inherent | Not its primary model | Core capability | Not a queue-style backlog |
| Back-pressure handling | Must be added downstream | Not the primary model | Strong | Concurrency can be controlled, but it is not queue buffering |
| Retry model | Client and integration dependent | Target delivery retry | Message redelivery | State-level `Retry` and `Catch` |
| Duplicate risk | Client retries may duplicate requests | Delivery may be repeated | Expected design concern | Start retries and task retries must be considered |
| DLQ relevance | Usually downstream | Possible for failed target delivery | Central operational pattern | Workflow failures use orchestration paths rather than normal queue DLQ semantics |
| Typical status tracking | HTTP response or status resource | Separate consumer outcomes | Separate status store or completion event | Execution history and domain status store |
| Best tutorial example | Submit trade through HTTP | Publish `TradeCaptured` | Queue trade enrichment | Start validate-and-persist workflow |

---

## Request-Response Versus Asynchronous Processing

The entry-point decision is strongly influenced by whether the caller expects a
result immediately.

### Request-response

```text
caller sends request
    ↓
system performs enough work to determine the response
    ↓
caller receives result
```

Typical entry point:

```text
API Gateway
```

Trade example:

```text
POST /trades/validate
    ↓
validate immediately
    ↓
200 valid or 400 invalid
```

The caller remains connected and expects a timely answer.

Request-response is suitable when:

- the work is short;
- the caller needs the result immediately;
- failure can be expressed clearly through the response;
- holding the connection open is reasonable;
- downstream dependencies are not likely to create unpredictable delays.

### Asynchronous acceptance

```text
caller submits input
    ↓
system confirms acceptance
    ↓
processing continues independently
```

Possible entry points or handoffs:

```text
SQS
EventBridge
Step Functions
```

A common external pattern is:

```text
caller
    ↓ HTTP request
API Gateway
    ↓
validate request
    ↓
SQS or Step Functions
    ↓
202 Accepted
```

The response means:

```text
the system accepted responsibility for processing
```

It does not mean:

```text
the business process completed successfully
```

### Why long work should not be hidden behind a synchronous request

A weak design is:

```text
Client
    ↓ waits
API Gateway
    ↓
Lambda
    ↓
several slow dependencies
    ↓
timeout or uncertain completion
```

Operational consequences include:

- client timeouts;
- repeated submissions;
- duplicate processing;
- ambiguous completion state;
- poor user experience;
- dependency on the slowest downstream component;
- difficult recovery after partial completion.

A stronger design is:

```text
Client
    ↓ POST /trades
API Gateway
    ↓
validate request envelope
    ↓
SQS or Step Functions
    ↓
202 Accepted + tracking identifier
```

The client can later query:

```http
GET /trades/TRD-1001/status
```

A possible response is:

```json
{
  "trade_id": "TRD-1001",
  "status": "PROCESSING",
  "last_completed_step": "VALIDATED"
}
```

The API boundary and the processing mechanism now have distinct
responsibilities.

### Precise response semantics

Avoid vague responses such as:

```json
{
  "status": "success"
}
```

That does not say what succeeded.

Prefer explicit language:

```json
{
  "status": "accepted_for_processing"
}
```

or:

```json
{
  "status": "validation_completed",
  "validation_result": "VALID"
}
```

The contract should distinguish:

```text
request accepted
request validated
workflow started
trade persisted
processing completed
```

---

## External Caller Versus Internal Service

The caller's trust boundary influences the entry-point design.

### External caller

Examples include:

- a browser-based trading application;
- a vendor platform;
- an external trading partner;
- a command-line client outside the AWS account;
- a mobile or web application.

Typical concerns include:

- authentication;
- authorisation;
- throttling;
- quotas;
- malformed input;
- hostile traffic;
- HTTP compatibility;
- API versioning;
- client-safe error messages;
- hiding internal service contracts.

The usual entry point is:

```text
API Gateway
```

An external caller should normally interact with a deliberate public or partner
contract, not with an internal queue message or state-machine definition.

### Internal service

Examples include:

- a Lambda function;
- an ECS service;
- a scheduled ingestion process;
- a trade-capture component;
- a service in another trusted AWS account;
- an internal batch process.

An internal service may use any of the four entry points depending on intent.

| Internal service intention | Suitable entry point |
| --- | --- |
| Announce a business fact | EventBridge |
| Submit work for eventual processing | SQS |
| Start a specific process | Step Functions |
| Call a governed internal HTTP contract | API Gateway or another HTTP service boundary |

### Internal does not automatically mean EventBridge

This is a common weak assumption.

An internal service may require:

- SQS because downstream processing is slower than production;
- Step Functions because several explicit steps must be coordinated;
- API Gateway because teams require a stable HTTP contract;
- EventBridge because multiple consumers should react to a fact.

The correct decision follows the contract and workload semantics, not merely
the network location of the caller.

### External does not automatically mean synchronous

An external caller may enter through API Gateway while the business process
continues asynchronously.

```text
External caller
    ↓ HTTP
API Gateway
    ↓
API-facing Lambda
    ↓
SQS
    ↓
worker Lambda
```

API Gateway protects and translates the external boundary. SQS provides durable
asynchronous processing behind it.

### Why direct external submission needs scrutiny

It is technically possible to grant external identities permission to submit
directly to AWS services in some architectures. That does not make it the
default choice.

Risks include:

- exposing internal message formats;
- coupling external clients to AWS service semantics;
- difficult contract evolution;
- complex IAM policies;
- weaker validation boundaries;
- reduced control over abuse and throttling;
- making internal workflow names part of the external contract.

A direct integration should be chosen deliberately, not merely because it
removes a Lambda function.

---

## Applying the Decision to the Trade Tutorial

The tutorial already contains several processing shapes:

- API-style Lambda request parsing and validation;
- EventBridge event handling;
- SQS batch processing and partial batch failures;
- Step Functions validation tasks;
- S3 accepted and rejected result artifacts;
- DynamoDB processing status records;
- combined persistence workflow logic.

Lesson 36 connects those exercises into a single entry-point model.

### Scenario 1: A trader submits a trade through a web application

Requirement:

```text
A user-facing application submits a trade. The user needs immediate feedback if
the request is malformed, but the full processing workflow may continue after
the response.
```

Entry point:

```text
API Gateway
```

Possible design:

```text
Trading UI
    ↓ POST /trades
API Gateway
    ↓
API-facing Lambda
    ↓
validate HTTP request and basic trade structure
    ├── invalid → 400 Bad Request
    └── valid
         ↓
         start internal processing
         ↓
         202 Accepted
```

The internal handoff could be:

```text
SQS
```

when durable buffering is the main requirement.

It could be:

```text
Step Functions
```

when the request starts a known multi-step workflow.

The external client should not need to understand the internal queue-message or
workflow-input contract.

### Scenario 2: A trade-capture platform announces a booked trade

Requirement:

```text
Risk, compliance, audit, and reporting may react independently when a trade is
captured.
```

Entry point:

```text
EventBridge
```

Design:

```text
Trade Capture Platform
    ↓ TradeCaptured
EventBridge
    ├── Risk consumer
    ├── Compliance consumer
    ├── Audit consumer
    └── Reporting consumer
```

The producer publishes one business fact. It does not call each target
explicitly.

A code-shaped event example is:

```json
{
  "source": "trade.capture",
  "detail-type": "TradeCaptured",
  "detail": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  }
}
```

### Scenario 3: Bulk trade enrichment must survive downstream outages

Requirement:

```text
A large batch of trades must eventually be enriched. Consumers may be throttled
or temporarily unavailable.
```

Entry point:

```text
SQS
```

Design:

```text
Trade ingestion process
    ↓
SQS
    ↓
Lambda batch consumer
    ↓
enrich and persist
    ↓
partial batch failure when necessary
    ↓
DLQ for poison messages
```

The Lessons 34A-34C model now applies directly:

```text
retry
idempotency
visibility timeout
partial batch failure
DLQ isolation
replay decision
```

### Scenario 4: A trusted service starts validation and persistence

Requirement:

```text
Every trade must pass through a known sequence:

validate
  → branch
  → persist accepted or rejected artifact
  → update status
```

Entry point:

```text
Direct Step Functions invocation
```

Design:

```text
Trusted internal trade service
    ↓
Start trade-processing state machine
    ↓
ValidateTrade
    ↓
Choice
    ├── valid → PersistAcceptedTrade
    └── invalid → PersistRejectedTrade
    ↓
UpdateTradeStatus
```

The caller intentionally starts this workflow and supplies its defined JSON
input.

### Scenario 5: External request starts a workflow

This scenario demonstrates that the services are not always competing choices.

```text
External client
    ↓ HTTP
API Gateway
    ↓
API-facing Lambda
    ↓ workflow input
Step Functions
    ↓
internal task Lambdas
```

From the external caller's perspective, API Gateway is the system entry point.

From the API-facing Lambda's perspective, Step Functions is the orchestration
entry point.

Each service owns a different boundary.

### Scenario 6: Business event creates durable consumer work

```text
Trade Capture
    ↓ TradeCaptured
EventBridge
    ├── SQS risk queue
    ├── SQS compliance queue
    └── audit target
```

EventBridge publishes and routes the fact.

Each SQS queue provides a durable work backlog for one consumer domain.

This architecture preserves both:

- loose publisher-to-consumer coupling;
- consumer-specific buffering and retry isolation.

### Scenario summary

| Trade scenario | Entry point | Reason |
| --- | --- | --- |
| User submits HTTP request | API Gateway | Exposes a controlled HTTP contract |
| Trade capture announces a fact | EventBridge | Supports loose event publication and fan-out |
| Bulk items await processing | SQS | Provides durable buffering and consumer-paced work |
| Trusted service starts defined process | Step Functions | Runs a known multi-step workflow |
| HTTP request triggers workflow | API Gateway, then Step Functions | External API boundary followed by orchestration |
| One event feeds isolated consumer backlogs | EventBridge, then SQS | Event fan-out followed by durable work queues |

---

## Common Wrong Choices

### 1. Using API Gateway because "everything needs an API"

Weak design:

```text
Internal Lambda
    ↓ HTTP
API Gateway
    ↓
another Lambda
```

This may add unnecessary:

- HTTP translation;
- latency;
- cost;
- authentication configuration;
- throttling behaviour;
- failure modes;
- client and server error mapping.

Use HTTP when an HTTP contract is genuinely required.

For internal integration:

```text
business fact → EventBridge
work backlog → SQS
known workflow → Step Functions
```

may be cleaner.

### 2. Using EventBridge as a work queue

Weak assumption:

```text
EventBridge delivers events, therefore it replaces SQS.
```

The missing requirements are often:

- durable backlog management;
- consumer-paced processing;
- queue depth monitoring;
- worker concurrency control;
- poison-message handling;
- explicit DLQ replay operations.

When every item represents work that must eventually be processed, SQS is
usually the stronger starting point.

### 3. Using SQS when the producer is publishing a reusable business fact

Weak design:

```text
Trade Capture
    ↓
one queue called trade-events
```

This becomes awkward when several independent consumers need the same event.

A stronger design may be:

```text
TradeCaptured
    ↓
EventBridge
    ├── SQS queue for risk work
    ├── SQS queue for compliance work
    └── audit target
```

EventBridge publishes the fact. Each queue buffers work for a specific consumer
context.

### 4. Starting Step Functions for every trivial operation

Weak design:

```text
Start workflow
    ↓
one Lambda task
    ↓
Succeed
```

If there is no meaningful orchestration, Step Functions may add unnecessary
operational and conceptual overhead.

A workflow becomes justified when it coordinates meaningful concerns such as:

- several tasks;
- branching;
- retries;
- catches;
- timeouts;
- waits;
- audit-visible execution state;
- compensation;
- human review.

### 5. Returning `200 OK` without defining what completed

A response such as:

```json
{
  "status": "success"
}
```

is ambiguous.

Did the system:

- parse the request?
- validate the trade?
- place work on SQS?
- start the workflow?
- persist the trade?
- complete every downstream operation?

Use precise response semantics.

| HTTP status | Typical meaning in this lesson |
| --- | --- |
| `200 OK` | Synchronous operation completed successfully |
| `201 Created` | A new resource was created |
| `202 Accepted` | Work was accepted for asynchronous processing |
| `400 Bad Request` | The caller supplied invalid input |
| `409 Conflict` | The request conflicts with existing state |

### 6. Exposing internal workflow or queue contracts directly by accident

A public client should not normally need to know:

- the SQS message schema;
- the state-machine name;
- internal task names;
- retry attributes;
- internal correlation conventions;
- AWS-specific error shapes.

API Gateway and an API-facing Lambda can shield and translate the external
contract.

### 7. Assuming asynchronous means reliable

Asynchronous processing changes the failure model. It does not remove failure.

For SQS:

```text
message accepted
≠
message processed successfully
```

For EventBridge:

```text
event published
≠
every downstream business process succeeded
```

For Step Functions:

```text
execution started
≠
execution completed successfully
```

Reliability still requires:

- idempotency;
- retry policy;
- failure destinations or catch paths;
- status persistence;
- observability;
- ownership of manual recovery.

### 8. Treating service selection as a one-service contest

Weak framing:

```text
Which single service should the whole architecture use?
```

Better framing:

```text
Which service should own each boundary?
```

Example:

```text
API Gateway
  → external HTTP boundary

SQS
  → durable work buffering

Step Functions
  → workflow orchestration

EventBridge
  → completion-event publication
```

A strong serverless design composes services deliberately rather than forcing
one service to solve every concern.

---

## SAP-C02 Relevance

This lesson supports AWS Certified Solutions Architect - Professional
(SAP-C02) questions involving integration, decoupling, event-driven design,
resilience, and new-solution design.

### 1. Service selection from requirement signals

| Requirement wording | Likely entry point or service |
| --- | --- |
| REST, HTTP method, authentication, throttling, client response | API Gateway |
| Business event, routing, fan-out, loosely coupled consumers | EventBridge |
| Traffic burst, durable backlog, consumer throttling, worker decoupling | SQS |
| Ordered tasks, branching, retry/catch, workflow state | Step Functions |

The exam often includes several technically possible services. The correct
answer is usually the service whose operating model matches the requirement.

### 2. Different forms of decoupling

| Service | Decoupling provided |
| --- | --- |
| API Gateway | Separates HTTP clients from backend implementation |
| EventBridge | Separates publishers from interested consumers |
| SQS | Separates producer throughput from consumer throughput |
| Step Functions | Separates workflow control from individual task implementation |

The word `decouple` is not enough by itself. Identify which dependency must be
reduced.

### 3. Synchronous timeout versus asynchronous acceptance

A common exam scenario includes:

- slow backend processing;
- API timeouts;
- traffic spikes;
- retries creating duplicate submissions.

A strong architecture is often:

```text
API Gateway
    ↓
request validation
    ↓
SQS or Step Functions
    ↓
202 Accepted
```

rather than holding the HTTP request open for the full process.

### 4. Event fan-out versus queue buffering

Typical trap:

```text
Use EventBridge because the architecture is event-driven.
```

But if the scenario emphasises:

- durable backlog;
- worker-controlled processing rate;
- queue depth;
- poison messages;
- replay;

then SQS is likely required, possibly behind EventBridge.

### 5. Orchestration versus choreography

```text
Step Functions:
  a central workflow defines the sequence and decisions

EventBridge:
  publishers emit facts and independent consumers react
```

Choose Step Functions when the process requires explicit state, ordering,
branching, or error paths.

Choose EventBridge when the main requirement is loose event-driven reaction
without one central component owning the whole sequence.

### 6. Combined architectures are often the strongest answer

SAP-C02 scenarios frequently require several services with distinct
responsibilities.

Example:

```text
API Gateway
    ↓
Lambda request validation
    ↓
SQS
    ↓
Step Functions
    ↓
Lambda tasks
    ↓
EventBridge completion event
```

This design can provide:

- an external HTTP contract;
- durable burst absorption;
- explicit workflow control;
- reusable completion events.

Do not select every service merely because it appears in the answer. Each
service must solve a stated requirement.

### 7. Exam trap summary

| Trap | Correction |
| --- | --- |
| "Event-driven" automatically means EventBridge | Determine whether the requirement is event routing, queue buffering, or orchestration |
| API Gateway means processing must be synchronous | API Gateway can return `202 Accepted` after asynchronous handoff |
| SQS provides exactly-once business processing | Consumers must still design for retries and idempotency |
| Step Functions replaces queues | Orchestration and durable work buffering solve different problems |
| Internal caller always uses EventBridge | Internal intent may require SQS, Step Functions, or HTTP |
| One service must be chosen | Services can be composed at different architectural boundaries |

---

## Lesson Boundary

Lesson 36 stops at the entry-point design decision.

It establishes:

```text
API Gateway:
  HTTP boundary

EventBridge:
  business-event boundary

SQS:
  durable asynchronous-work boundary

Step Functions:
  explicit workflow boundary
```

This lesson does not implement:

- API Gateway event parsing;
- HTTP response helpers;
- EventBridge publishing;
- SQS message submission;
- Step Functions execution calls;
- AWS SDK clients;
- IAM policies;
- infrastructure definitions;
- Terraform;
- live AWS deployment;
- new tests.

The concrete evidence is this design note and the ability to defend an entry
point for a trade-processing scenario.

The lesson remains tutorial evidence only. It is not Energy Data Lakehouse
implementation evidence and must not be promoted into another repository
without adaptation, IAM review, and repository-specific tests.

The next likely lesson is:

```text
Lesson 37:
  API-facing Lambda
  versus
  internal service Lambda
```

Lesson 37 should answer:

```text
Once the entry point has been chosen, what responsibility belongs in the first
Lambda?
```

The expected distinction is:

```text
API-facing Lambda
  understands HTTP
  reads request and identity context
  validates the external envelope
  maps failures to HTTP responses
  shields internal contracts

Internal service Lambda
  understands domain events, commands, or workflow inputs
  performs one bounded business task
  returns structured internal data
  should not contain HTTP behaviour unless HTTP is its actual contract
```

The lesson sequence is therefore:

```text
Lesson 34:
  understand SQS failure, DLQ, idempotency, and replay

Lesson 35:
  choose publish-fact vs queue-work vs orchestrate-workflow

Lesson 36:
  choose how input enters the system

Lesson 37:
  design the Lambda responsibility behind that entry point
```

---

## Revision Checklist

Before treating Lesson 36 as understood, you should be able to answer these
questions without reading the lesson:

1. Why is API Gateway an HTTP boundary rather than a complete processing
   architecture?
2. What is the difference between `TradeCaptured` and `ValidateTrade`?
3. Why does SQS imply idempotency and DLQ operations?
4. When is direct Step Functions invocation a reasonable form of coupling?
5. Why can API Gateway and SQS both appear in the same request path?
6. Why can EventBridge fan out to several SQS queues?
7. What does `202 Accepted` guarantee, and what does it not guarantee?
8. How does an external caller's contract differ from an internal service
   contract?
9. Which form of decoupling does each of the four services provide?
10. Where should Lesson 36 stop before Lesson 37 begins?

---

## Acronym Legend

| Acronym | Meaning |
| --- | --- |
| API | Application Programming Interface |
| AWS | Amazon Web Services |
| DLQ | Dead-Letter Queue |
| HTTP | Hypertext Transfer Protocol |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| Lambda | AWS serverless function service |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam code |
| SNS | Amazon Simple Notification Service |
| SQS | Amazon Simple Queue Service |
