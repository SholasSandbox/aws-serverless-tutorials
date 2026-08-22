<!-- markdownlint-disable MD013 MD024 MD025 -->

# Lesson 38: API-to-Step Functions Workflow Handoff — Design and Minimal Python Implementation

## Objective

Design the boundary between an HTTP API and an AWS Step Functions workflow.

This lesson answers:

```text
Once an API request has reached the system,
how should it start the workflow,
and what may the API truthfully return to the caller?
```

By the end of the lesson, you should be able to:

- choose between an API Gateway direct service integration and a
  Lambda-mediated `StartExecution` call;
- explain why a successful workflow start is not the same as completed business
  processing;
- use `202 Accepted` accurately;
- distinguish `correlation_id`, `idempotency_key`, Step Functions execution
  name, API request ID, and execution ARN;
- explain the relevant differences between Standard and Express Workflows;
- design client-safe error mapping without leaking AWS implementation details;
- identify the IAM roles involved at the API, Lambda, and workflow boundaries;
- defend the handoff selected for the trade-processing tutorial;
- implement a small API-facing boundary adapter that starts Step Functions;
- verify through tests that HTTP-shaped input becomes domain-shaped workflow
  input and that `202 Accepted` is returned only after a successful handoff.

This is a design-and-implementation lesson. It includes a runnable minimal
Python implementation and focused local tests. It does not deploy AWS
resources or claim live AWS validation.

---

## How this connects Lessons 35–37

Lesson 35 classified the producer's intention:

```text
EventBridge:
  publish facts

SQS:
  queue work

Step Functions:
  orchestrate workflows
```

Lesson 36 moved to the system boundary:

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

Lesson 37 then distinguished the responsibility of the first Lambda:

```text
API-facing Lambda:
  translate between HTTP and the internal system

Internal service Lambda:
  perform one bounded domain or workflow task
```

Lesson 38 now makes the handoff concrete:

```text
External client
  → API Gateway
  → direct Step Functions integration
     or API-facing Lambda
  → Step Functions execution
  → internal service Lambdas
  → S3 / DynamoDB
```

The architectural question is no longer merely:

```text
Should Step Functions be used?
```

The question is:

```text
How should the API start the workflow,
what guarantees exist at that point,
and how should those guarantees be expressed to the caller?
```

---

## Short decision rule

```text
Use an API Gateway direct integration
when request mapping, IAM, and response mapping
can express the boundary safely.

Use an API-facing Lambda
when the boundary requires meaningful custom code.

Return 202 Accepted
only after the workflow-start operation succeeds.
```

A second compact rule is:

```text
Configuration before code.
Code when the boundary genuinely needs it.
Workflow completion remains asynchronous.
```

## Lesson 38 implementation checkpoint

The lesson now embeds the architecture in a small executable path:

```text
API Gateway event
  → API-facing Python function
  → normalized workflow input
  → injected Step Functions client
  → StartExecution
  → 202 Accepted
```

The implementation must prove four things:

1. HTTP concerns stop at the API boundary.
2. Step Functions receives domain-shaped JSON rather than the raw API Gateway
   proxy event.
3. `202 Accepted` is returned only after `StartExecution` succeeds.
4. The AWS client is injected into the testable function, so local tests do not
   call AWS.

The code remains deliberately small. It does not implement a DynamoDB-backed
business idempotency store, status endpoint, API Gateway deployment, or live
IAM policy. Those remain later implementation boundaries.

---

## The target trade-processing path

The tutorial's eventual vertical slice is expected to resemble:

```text
Client
  → POST /trade-submissions
  → API Gateway
  → API-facing Lambda
  → Step Functions StartExecution
  → Standard Workflow
       → validate trade
       → Choice: valid or invalid
       → persist accepted or rejected result
       → explicit success or failure path
```

The immediate API operation is:

```text
accept a trade submission and start its processing workflow
```

It is not:

```text
complete all trade processing before returning the HTTP response
```

That distinction controls the API response, timeout boundary, retry behaviour,
idempotency model, and status-tracking design.

---

## What the handoff actually means

The handoff is successful when Step Functions has accepted the execution-start
request.

For an asynchronous `StartExecution` call, success means:

```text
Step Functions accepted the request
and created or recognised the workflow execution.
```

It does not mean:

```text
trade validation succeeded;
trade persistence succeeded;
the workflow reached Succeed;
or the business process completed.
```

The architecture therefore has at least two separate outcomes:

| Outcome | Meaning |
| --- | --- |
| Workflow-start outcome | Did Step Functions accept the execution request? |
| Business-processing outcome | Did the workflow later complete its business process successfully? |

A robust API contract must not merge these outcomes into one vague status such
as `success`.

---

# Pattern 1: API Gateway direct integration

## Mental model

```text
HTTP request
  → API Gateway mapping
  → Step Functions StartExecution
  → mapped HTTP response
```

API Gateway can invoke supported AWS service operations directly. For Step
Functions, this can include `StartExecution`.

The direct integration removes the Lambda hop:

```text
Client
  → API Gateway
  → Step Functions
```

### What API Gateway must do

The integration must provide the parameters required by Step Functions:

```text
stateMachineArn
input
optional execution name
optional trace context
```

Conceptually, the mapped request might become:

```json
{
  "stateMachineArn": "arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing",
  "name": "trade-submit-7f82c81a",
  "input": "{\"trade\":{\"trade_id\":\"TRD-1001\",\"product\":\"POWER\",\"volume_mwh\":25},\"correlation_id\":\"REQ-123\"}"
}
```

Notice that `input` is supplied to the Step Functions API as a JSON **string**.
The workflow receives the decoded JSON object when execution begins.

### IAM boundary

API Gateway requires an IAM role that permits:

```text
states:StartExecution
```

The permission should be scoped to the intended state machine or approved state
machine alias rather than all state machines.

Illustrative policy shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "states:StartExecution",
      "Resource": "arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing"
    }
  ]
}
```

This policy is illustrative. Account IDs, Regions, state machine names, aliases,
and deployment controls must come from the actual environment.

### Direct integration strengths

- removes one Lambda invocation;
- removes one deployment unit;
- reduces code ownership;
- reduces cold-start exposure;
- can reduce latency and cost;
- makes the managed-service relationship explicit;
- keeps the path simple when transformation requirements are modest.

### Direct integration limitations

A direct integration becomes weaker when the boundary needs:

- non-trivial schema validation;
- cross-field validation;
- complex request normalisation;
- business-aware duplicate detection;
- dynamic state-machine selection;
- custom execution-name generation;
- identity translation;
- external-to-internal version conversion;
- detailed client-safe error classification;
- code-level tests for transport and SDK failure paths.

The direct option is not automatically superior. It is superior only when its
configuration remains understandable, testable, secure, and sufficient.

### Architecture risk

Do not replace a small Lambda with an unreadable collection of mapping
templates merely to claim that the design is "more serverless".

A configuration-only integration that is difficult to reason about can become
less maintainable than a small, explicit boundary adapter.

---

# Pattern 2: Lambda-mediated workflow start

## Mental model

```text
HTTP request
  → API Gateway
  → API-facing Lambda
       → parse and validate the request envelope
       → create internal workflow input
       → call Step Functions StartExecution
       → map the immediate result to HTTP
  → Step Functions workflow
```

The Lambda exists because boundary code is required.

It should not become the workflow.

## Correct responsibility split

### API-facing Lambda owns

- HTTP event parsing;
- base64-body handling where required;
- public request validation;
- caller identity extraction;
- correlation-ID handling;
- business idempotency-key handling;
- execution-name derivation where selected;
- the `StartExecution` API call;
- client-safe response mapping;
- immediate handoff logging.

### Step Functions owns

- workflow sequencing;
- branching;
- task retry and catch behaviour;
- timeout paths;
- persistence coordination;
- reconciliation routing;
- terminal success or explicit failure.

### Internal service Lambdas own

- one bounded domain or workflow task;
- task-specific validation;
- task-specific AWS service calls;
- domain-shaped output;
- task failures meaningful to the orchestrator.

Weak design:

```text
API Lambda
  → validate everything
  → write S3
  → write DynamoDB
  → publish events
  → send notifications
  → return HTTP response
```

Better design:

```text
API Lambda
  → validate boundary
  → start workflow
  → return 202

Step Functions
  → coordinate bounded tasks
```

---

## Minimal Python implementation

The following companion module is runnable tutorial code. The proposed module
name is:

```text
api_workflow_handoff.py
```

It is not presented as an existing repository module. When integrated into the
learner's repository, naming should be reconciled with the real modules already
present.

```python
"""Minimal API-to-Step Functions handoff for Lesson 38.

This module is tutorial code. It demonstrates boundary translation,
dependency injection, truthful 202 responses, and a small Step Functions
adapter without deploying AWS resources.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Mapping

import boto3
from botocore.exceptions import BotoCoreError, ClientError

LOGGER = logging.getLogger(__name__)

RETRYABLE_STEP_FUNCTIONS_ERRORS = {
    "ExecutionLimitExceeded",
    "KmsThrottlingException",
    "ServiceUnavailable",
    "ThrottlingException",
}


def normalise_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return lower-case HTTP header names with string values."""
    if not headers:
        return {}

    return {
        str(name).lower(): str(value)
        for name, value in headers.items()
        if value is not None
    }


def parse_json_object_body(event: Mapping[str, Any]) -> dict[str, Any]:
    """Parse the API Gateway body and require a JSON object."""
    raw_body = event.get("body")

    if not isinstance(raw_body, str) or not raw_body.strip():
        raise ValueError("Request body must contain valid JSON.")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must contain valid JSON.") from exc

    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")

    return body


def extract_request_id(event: Mapping[str, Any], context: Any) -> str:
    """Prefer the API Gateway request ID, then use the Lambda request ID."""
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        request_id = request_context.get("requestId")
        if isinstance(request_id, str) and request_id.strip():
            return request_id

    lambda_request_id = getattr(context, "aws_request_id", None)
    if isinstance(lambda_request_id, str) and lambda_request_id.strip():
        return lambda_request_id

    return "unknown-request-id"


def require_idempotency_key(headers: Mapping[str, str]) -> str:
    """Require the public operation idempotency key."""
    idempotency_key = headers.get("idempotency-key", "").strip()
    if not idempotency_key:
        raise ValueError("Idempotency-Key header is required.")
    return idempotency_key


def select_correlation_id(headers: Mapping[str, str], request_id: str) -> str:
    """Use a caller correlation ID when supplied, otherwise the request ID."""
    return headers.get("x-correlation-id", "").strip() or request_id


def build_execution_name(idempotency_key: str) -> str:
    """Create a stable, Step Functions-safe execution name."""
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"trade-submit-{digest}"


def build_workflow_input(
    *,
    trade: Mapping[str, Any],
    correlation_id: str,
    idempotency_key: str,
    request_id: str,
) -> dict[str, Any]:
    """Build domain-shaped workflow input without HTTP envelope fields."""
    return {
        "trade": dict(trade),
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "request_id": request_id,
    }


def start_trade_workflow(
    *,
    step_functions_client: Any,
    state_machine_arn: str,
    execution_name: str,
    workflow_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Start one Step Functions execution and return a small adapter result."""
    response = step_functions_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=execution_name,
        input=json.dumps(dict(workflow_input), separators=(",", ":")),
    )

    return {
        "execution_arn": response["executionArn"],
        "start_date": response["startDate"],
    }


def json_response(
    *,
    status_code: int,
    body: Mapping[str, Any],
    correlation_id: str,
) -> dict[str, Any]:
    """Create an API Gateway-compatible response."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "x-correlation-id": correlation_id,
        },
        "body": json.dumps(dict(body)),
    }


def map_step_functions_error(exc: Exception) -> int:
    """Map AWS start failures to a client-safe HTTP status."""
    if isinstance(exc, ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in RETRYABLE_STEP_FUNCTIONS_ERRORS:
            return 503
    if isinstance(exc, BotoCoreError):
        return 503
    return 500


def handle_trade_submission(
    event: Mapping[str, Any],
    context: Any,
    *,
    step_functions_client: Any,
    state_machine_arn: str,
) -> dict[str, Any]:
    """Translate an HTTP request into an asynchronous workflow start."""
    request_id = extract_request_id(event, context)
    headers = normalise_headers(event.get("headers"))
    correlation_id = select_correlation_id(headers, request_id)

    try:
        trade = parse_json_object_body(event)
        idempotency_key = require_idempotency_key(headers)
    except ValueError as exc:
        return json_response(
            status_code=400,
            correlation_id=correlation_id,
            body={
                "error": str(exc),
                "correlation_id": correlation_id,
            },
        )

    execution_name = build_execution_name(idempotency_key)
    workflow_input = build_workflow_input(
        trade=trade,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_id=request_id,
    )

    try:
        workflow_start = start_trade_workflow(
            step_functions_client=step_functions_client,
            state_machine_arn=state_machine_arn,
            execution_name=execution_name,
            workflow_input=workflow_input,
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception(
            "trade workflow start failed",
            extra={
                "correlation_id": correlation_id,
                "request_id": request_id,
                "execution_name": execution_name,
            },
        )
        status_code = map_step_functions_error(exc)
        return json_response(
            status_code=status_code,
            correlation_id=correlation_id,
            body={
                "error": "Workflow could not be started.",
                "correlation_id": correlation_id,
            },
        )

    LOGGER.info(
        "trade workflow started",
        extra={
            "correlation_id": correlation_id,
            "request_id": request_id,
            "execution_name": execution_name,
            "execution_arn": workflow_start["execution_arn"],
        },
    )

    return json_response(
        status_code=202,
        correlation_id=correlation_id,
        body={
            "status": "accepted_for_processing",
            "operation_id": execution_name,
            "correlation_id": correlation_id,
            "status_path": f"/trade-submissions/{execution_name}",
        },
    )


# Runtime wrapper. Tests call handle_trade_submission with an injected client.
_STEP_FUNCTIONS_CLIENT: Any | None = None


def get_step_functions_client() -> Any:
    """Create the SDK client lazily, then reuse it across warm invocations."""
    global _STEP_FUNCTIONS_CLIENT
    if _STEP_FUNCTIONS_CLIENT is None:
        _STEP_FUNCTIONS_CLIENT = boto3.client("stepfunctions")
    return _STEP_FUNCTIONS_CLIENT


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point."""
    return handle_trade_submission(
        event,
        context,
        step_functions_client=get_step_functions_client(),
        state_machine_arn=os.environ["TRADE_STATE_MACHINE_ARN"],
    )
```

## What the implementation teaches

### Pure boundary helpers

These functions do not call AWS:

```text
normalise_headers
parse_json_object_body
extract_request_id
require_idempotency_key
select_correlation_id
build_execution_name
build_workflow_input
json_response
```

They can be tested with ordinary Python inputs and outputs.

### Impure AWS adapter

```text
start_trade_workflow
```

This function performs the `start_execution` service call. It receives the
Step Functions client as an argument rather than creating the client internally.
That makes the service boundary explicit and testable.

### Testable orchestration function

```text
handle_trade_submission
```

This function coordinates the API boundary:

```text
parse request
  → resolve identifiers
  → construct workflow input
  → call Step Functions adapter
  → return client-safe HTTP response
```

It does not perform the downstream trade workflow itself.

### Thin Lambda runtime wrapper

```text
lambda_handler
```

AWS invokes the two-argument Lambda handler. The handler obtains a cached SDK
client and delegates immediately to the testable function.

The client is created lazily rather than at import time. This matters locally:
the first test run created the client during module import and failed collection
with `NoRegionError` because no AWS Region was configured. Lazy creation removed
that irrelevant test dependency while still allowing client reuse across warm
Lambda invocations.

## Dictionary flow

### API Gateway-shaped input

```json
{
  "body": "{\"trade_id\":\"TRD-1001\",\"product\":\"POWER\",\"volume_mwh\":25}",
  "headers": {
    "Idempotency-Key": "submission-001",
    "X-Correlation-Id": "CORR-123"
  },
  "requestContext": {
    "requestId": "REQ-456"
  }
}
```

This dictionary contains transport concerns: stringified body content, HTTP
headers, and API Gateway request context.

### Normalized Step Functions input

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "correlation_id": "CORR-123",
  "idempotency_key": "submission-001",
  "request_id": "REQ-456"
}
```

This dictionary contains only information needed by the internal workflow. It
does not contain `headers`, `requestContext`, `statusCode`, or a stringified
HTTP body.

## Implementation limitations

The minimal implementation intentionally leaves these concerns incomplete:

- schema validation of individual trade fields;
- bounded length and character validation for public identifiers;
- a durable DynamoDB idempotency record;
- duplicate handling after a Standard Workflow has closed;
- base64-encoded API Gateway request bodies;
- detailed distinction between every Step Functions `ClientError`;
- explicit handling of unknown outcomes after transport timeouts;
- authentication and authorisation context;
- status resource persistence and retrieval;
- Infrastructure as Code and deployed IAM.

Those omissions are explicit lesson boundaries, not production recommendations.

---

# `StartExecution` contract

## Request parameters

The important request parameters are:

| Parameter | Role |
| --- | --- |
| `stateMachineArn` | Selects the state machine, version, or alias to run |
| `input` | JSON text passed into the workflow |
| `name` | Optional execution name with uniqueness rules |
| `traceHeader` | Optional AWS X-Ray trace context |

For production deployment, using a state machine alias can create a more stable
release boundary than always targeting the latest unqualified state machine
revision.

## Successful response

A successful `StartExecution` response contains:

```json
{
  "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:trade-submit-7f82c81a",
  "startDate": "timestamp"
}
```

The AWS API success response confirms that the execution was started or, for a
qualifying Standard Workflow duplicate call, that the same running execution
was recognised.

It does not contain the final workflow result.

To obtain the later state of an asynchronous Standard Workflow, a separate
status mechanism is required, such as:

- `DescribeExecution` for a technical execution view;
- a DynamoDB operation-status record for a domain-facing view;
- an EventBridge completion event;
- a callback or notification;
- a separate status API.

---

# Standard versus Express Workflow

The API handoff cannot be designed correctly without selecting the workflow
semantics.

| Concern | Standard Workflow | Asynchronous Express | Synchronous Express |
| --- | --- | --- | --- |
| Typical use | Durable and auditable business process | High-volume event processing | Short request-response orchestration |
| Maximum duration | Up to one year | Up to five minutes | Up to five minutes |
| Start API | `StartExecution` | `StartExecution` | `StartSyncExecution` |
| Immediate result | Execution reference | Start confirmation | Final execution result |
| Execution guarantee | Exactly-once workflow execution | At-least-once | At-most-once |
| Execution history | Durable Step Functions execution history | Primarily CloudWatch Logs when enabled | Primarily response and CloudWatch Logs when enabled |
| Suitable for this tutorial's auditable trade workflow | Strong fit | Weaker fit | Usually not the intended model |

## Important qualification

```text
Exactly-once workflow execution
is not the same as exactly-once side effects.
```

A Standard Workflow can deliberately retry a Task state. The Lambda or AWS
service operation behind that state can therefore run more than once.

Persistence and external side effects must still be idempotent.

## Recommended tutorial choice

For the planned trade-processing path, Standard Workflow is the stronger
default because the requirements emphasise:

- durable workflow state;
- explicit Retry and Catch behaviour;
- auditable execution history;
- controlled failure paths;
- potential human review or reconciliation;
- asynchronous completion;
- business operations that should not be hidden inside one API request.

This is a judgement based on the tutorial's goals. It is not a universal rule
for all APIs.

## Synchronous Express caution

`StartSyncExecution` is available only for Synchronous Express Workflows.

The AWS API can return HTTP `200 OK` even when the workflow itself failed. The
caller must inspect the response fields such as `status`, `error`, and `cause`.

Therefore this design is wrong:

```text
AWS returned HTTP 200
  → assume business workflow succeeded
```

The correct interpretation is:

```text
AWS accepted and ran the synchronous execution request
  → inspect the workflow status in the response
```

Lesson 38 selects asynchronous Standard Workflow semantics for the trade
submission example, so the public API returns `202 Accepted` after the start
operation succeeds.

---

# Five identifiers that must remain separate

A common design failure is to reuse one identifier for several unrelated jobs.

## 1. `trade_id`

```text
Domain identity of the trade.
```

Example:

```text
TRD-1001
```

A trade may be submitted, amended, retried, or reprocessed. The trade ID alone
may therefore be insufficient as an operation identity.

## 2. `idempotency_key`

```text
Business key representing one logical submission operation.
```

It answers:

```text
Has this logical request already been accepted?
```

The client may supply it through a header such as:

```http
Idempotency-Key: 6dc9019d-5eb0-4f96-a17e-30a97ce5d9db
```

The API must validate its format and scope. The key should be associated with
both the caller and the operation, not assumed globally unique without design.

## 3. `correlation_id`

```text
Observability identifier carried across components and logs.
```

It answers:

```text
Which log records and workflow steps belong to the same end-to-end request?
```

A correlation ID helps trace work. It does not, by itself, prevent duplicates.

## 4. Step Functions execution name

```text
Technical name used by the Step Functions execution-start API.
```

For Standard Workflows, the name participates in Step Functions idempotency and
uniqueness behaviour.

It should normally be generated by the system from controlled input. Do not use
an arbitrary unsanitised client string.

A proposed pattern is:

```text
trade-submit-{short-stable-hash}
```

The hash could be derived from a scoped idempotency key. The exact algorithm
must be stable, collision-aware, testable, and documented.

## 5. API or Lambda request ID

```text
Infrastructure invocation identifier.
```

Examples include:

- API Gateway request ID;
- Lambda invocation request ID.

These are useful for operational diagnosis but are poor business idempotency
keys because retries create new infrastructure requests.

## 6. Execution ARN

```text
AWS identifier for one workflow execution.
```

It is valuable internally for operations and debugging. It need not become the
public API's permanent identifier.

## Comparison

| Identifier | Main purpose | Suitable as business duplicate key? | Suitable for log correlation? |
| --- | --- | --- | --- |
| `trade_id` | Domain resource identity | Sometimes, but often incomplete | Yes |
| `idempotency_key` | Logical operation identity | Yes | Yes |
| `correlation_id` | End-to-end observability | No | Yes |
| Execution name | Step Functions technical uniqueness | Can be derived from it | Yes |
| API request ID | One HTTP infrastructure request | No | Yes |
| Lambda request ID | One Lambda invocation | No | Yes |
| Execution ARN | One Step Functions execution | Not the original business key | Yes |

The design rule is:

```text
Correlate with correlation_id.
Deduplicate with idempotency_key.
Name the workflow with a controlled execution-name rule.
Track AWS execution with executionArn.
```

---

# Standard Workflow execution-name behaviour

For Standard Workflows, `StartExecution` has specific idempotency behaviour.

## Same name and same input while the execution is running

```text
The repeated StartExecution call is treated as idempotent
and returns the same execution response.
```

## Same name but different input

```text
Step Functions returns ExecutionAlreadyExists.
```

## Same name after the earlier execution has closed

```text
The name remains unavailable during the reuse window,
even if the new input matches.
```

A Standard Workflow execution name can be reused 90 days after the previous
execution closes.

## Express Workflow

`StartExecution` is not idempotent for Express Workflows.

## Architectural consequence

Do not rely on Step Functions execution naming as the complete business
idempotency system.

Reasons include:

- business duplicate policy may outlive or be shorter than 90 days;
- a trade may have several legitimate operations;
- public retries may occur after the original workflow has completed;
- business idempotency may need caller and operation scope;
- the API may need to return the original public operation state;
- execution-name constraints are technical rather than domain-driven.

A dedicated idempotency record in DynamoDB may still be appropriate.

---

# Accurate `202 Accepted` semantics

## Correct sequence

```text
1. Receive the HTTP request.
2. Authenticate and authorise the caller.
3. Validate the public request envelope.
4. Resolve business idempotency.
5. Construct normalized workflow input.
6. Call StartExecution.
7. Confirm that StartExecution succeeded.
8. Return 202 Accepted.
```

Do not return `202 Accepted` before step 7.

## Correct response meaning

```text
The system accepted responsibility for processing
and successfully handed the operation to the workflow service.
```

## Example response

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /trade-submissions/trade-submit-7f82c81a
X-Correlation-Id: REQ-123
```

```json
{
  "status": "accepted_for_processing",
  "operation_id": "trade-submit-7f82c81a",
  "correlation_id": "REQ-123",
  "status_path": "/trade-submissions/trade-submit-7f82c81a"
}
```

## What the response must not claim

Avoid:

```json
{
  "status": "success",
  "message": "Trade processed successfully"
}
```

At this point, the system does not yet know whether the workflow will complete
successfully.

## AWS response code versus public response code

The Step Functions `StartExecution` API returns AWS HTTP `200` when the start
request succeeds.

The public API can still correctly return HTTP `202` because the public
operation is asynchronous.

These are different contracts:

```text
AWS service contract:
  StartExecution request succeeded

Public API contract:
  trade processing was accepted and continues asynchronously
```

---

# Status retrieval

An asynchronous API should normally provide a way to determine later progress.

## Option 1: Technical status from Step Functions

```text
GET /trade-submissions/{operation_id}
  → internal mapping
  → DescribeExecution
```

Advantages:

- reuses the workflow service's execution state;
- suitable for operational tooling;
- no separate status write is required for basic state.

Limitations:

- workflow status is technical rather than domain-specific;
- exposing execution ARNs couples the public API to AWS implementation;
- business milestones may not map cleanly to execution status;
- long-term retention and reporting may need another store.

## Option 2: Domain status in DynamoDB

Example record:

```json
{
  "operation_id": "trade-submit-7f82c81a",
  "trade_id": "TRD-1001",
  "status": "PROCESSING",
  "last_completed_stage": "VALIDATED",
  "correlation_id": "REQ-123",
  "execution_arn": "arn:aws:states:...",
  "version": 3
}
```

Advantages:

- stable public operation model;
- business-specific status;
- controlled retention;
- API does not expose AWS internals;
- supports query patterns independent of Step Functions.

Costs and risks:

- additional writes;
- consistency between workflow and status record must be designed;
- idempotent updates are required;
- failure ordering must be understood.

## Recommended model

For the tutorial, treat Step Functions execution history as the workflow audit
source and DynamoDB as the candidate business-status source.

Do not add a status table merely because status tables are common. Add it when
the public API requires a stable domain-facing operation resource.

---

# Error mapping at the handoff

The API-facing layer must classify failures according to the public contract.
It must not return raw Botocore or AWS service errors to the client.

| Condition | Internal meaning | Candidate public response |
| --- | --- | --- |
| Invalid JSON or malformed envelope | Client request is invalid | `400 Bad Request` |
| Missing or invalid idempotency key | Public contract violation | `400 Bad Request` |
| Caller not authenticated | No valid identity | `401 Unauthorized` |
| Caller authenticated but not authorised | Identity lacks operation permission | `403 Forbidden` |
| Previously accepted identical business operation | Idempotent duplicate | Return original operation response, often `200` or `202` according to contract |
| Same execution name with incompatible input | Technical or business conflict | Usually internal classification; possibly `409 Conflict` if it genuinely represents a client conflict |
| Step Functions throttling or capacity failure | Temporary service inability | `503 Service Unavailable` may be suitable |
| Network or connection failure | Handoff outcome uncertain or failed | `503 Service Unavailable`; design carefully for retry and duplicate risk |
| Lambda lacks `states:StartExecution` | Deployment or IAM defect | Generic `500 Internal Server Error` |
| Invalid state machine ARN or invalid configuration | Deployment defect | Generic `500 Internal Server Error` |
| Unexpected programming failure | Internal defect | Generic `500 Internal Server Error` |

## Important ambiguity: connection failure

Suppose the client call to Step Functions times out after the request leaves the
Lambda.

The Lambda may not know whether Step Functions accepted the execution.

This is an **unknown outcome**, not a clean failure.

A retry may create a duplicate unless the execution name and business
idempotency design are stable.

The safe model is:

```text
stable idempotency key
  → stable execution-name derivation
  → retry StartExecution
  → Standard Workflow idempotency assists while execution is running
  → business idempotency record resolves wider cases
```

This is one reason an idempotency strategy must exist before transport retries
are added.

---

# Direct integration versus Lambda-mediated comparison

| Concern | Direct API Gateway integration | Lambda-mediated start |
| --- | --- | --- |
| Custom Python code | None | Required |
| Operational components | Fewer | One additional function |
| Request transformation | API Gateway mapping | Python functions |
| Complex validation | Limited or cumbersome | Strong fit |
| Business idempotency | Possible but awkward | Stronger fit |
| Execution-name calculation | Static/simple mapping | Flexible and testable |
| Client-safe error classification | Mapping configuration | Explicit code |
| Unit testing | Configuration/IaC tests | Python unit tests plus SDK stubs |
| Cost and latency | Lower in simple cases | Additional invocation and latency |
| IAM caller of Step Functions | API Gateway role | Lambda execution role |
| Failure boundary | API Gateway → Step Functions | API Gateway → Lambda → Step Functions |
| Maintainability | Strong when mapping stays simple | Strong when code remains small and bounded |
| Risk | Complex mapping becomes opaque | Lambda becomes unnecessary orchestration code |

---

# Decision for the trade tutorial

## Facts

The planned future slice requires:

- non-trivial public request validation;
- correlation propagation;
- explicit business idempotency handling;
- deterministic execution-name construction;
- client-safe classification of duplicate, service, permission, connection,
  and unexpected failures;
- dependency-injected and `Stubber`-backed SDK tests;
- a deliberate `boto3.start_execution` learning boundary.

## Judgement

For that learning objective, an API-facing Lambda is justified.

The Lambda is not justified merely because Lambda is familiar. It is justified
because the lesson intentionally studies code-level boundary behaviour that a
direct integration would hide or move into mapping configuration.

## Selected conceptual path

```text
API Gateway
  → API-facing Lambda
       → normalize request
       → resolve identifiers
       → start Standard Workflow
       → map start result
  → 202 Accepted
```

## Counterfactual

If the eventual production requirement were only:

```text
accept already-normalized JSON
and start one fixed state machine
```

then a direct API Gateway integration should be reconsidered because the Lambda
could become unnecessary.

A credible architect must be able to defend both the selected design and the
simpler alternative.

---

# IAM responsibility boundaries

Three roles must not be confused.

## 1. API caller permission

Controls whether the external or internal caller may invoke the API route.

Possible mechanisms include:

- JSON Web Token authorisation;
- Amazon Cognito authoriser;
- Lambda authoriser;
- IAM authorisation;
- resource policy;
- private API controls.

This is the caller-to-API boundary.

## 2. API Gateway integration role or Lambda execution role

### Direct integration

API Gateway assumes a role that can call:

```text
states:StartExecution
```

on the intended state machine resource.

### Lambda-mediated integration

The Lambda execution role can call:

```text
states:StartExecution
```

on the intended state machine resource.

It should not automatically receive permission to invoke unrelated workflows.

## 3. Step Functions execution role

The workflow's own execution role permits the workflow to invoke its tasks and
AWS service integrations.

Examples may include:

```text
lambda:InvokeFunction
s3:PutObject
dynamodb:PutItem
events:PutEvents
sns:Publish
```

Each permission should be scoped to the resources used by the state machine.

The API-facing Lambda does not need all permissions required by the workflow.

```text
API Lambda role:
  permission to start the workflow

Workflow role:
  permission to execute workflow tasks
```

This separation reduces blast radius.

---

# Security considerations

## Do not accept the state machine ARN from the client

Weak design:

```json
{
  "state_machine_arn": "client-supplied-value",
  "input": {}
}
```

Risk:

```text
The caller influences which internal workflow is invoked.
```

Better:

```text
The route or server-side configuration selects the workflow.
```

## Do not log the entire request by default

Trade requests may contain sensitive business data.

Prefer structured logs containing deliberate identifiers and state
transitions:

```json
{
  "event": "trade_workflow_start_requested",
  "trade_id": "TRD-1001",
  "correlation_id": "REQ-123",
  "execution_name": "trade-submit-7f82c81a"
}
```

Avoid logging:

- access tokens;
- authorisation headers;
- secrets;
- full identity claims;
- raw exception stacks in client responses;
- sensitive trade payloads without a defined need.

## Validate identifiers

Validate and constrain:

- idempotency-key length and character set;
- correlation-ID length and character set;
- execution-name output;
- request-body type and shape;
- route-specific payload size.

Do not insert untrusted strings directly into ARNs, log messages, or execution
names.

---

# Observability contract

A useful end-to-end trace is:

```text
API Gateway request
  api_request_id = gateway-456
  correlation_id = REQ-123

API-facing Lambda
  lambda_request_id = lambda-789
  idempotency_key = 6dc9...
  execution_name = trade-submit-7f82c81a

Step Functions
  execution_arn = arn:aws:states:...
  correlation_id = REQ-123 in execution input

Validation Lambda
  correlation_id = REQ-123
  trade_id = TRD-1001
  stage = VALIDATION

Persistence Lambda
  correlation_id = REQ-123
  trade_id = TRD-1001
  stage = PERSISTENCE
```

The API-facing Lambda should log the workflow-start result before returning
`202 Accepted`.

Example:

```json
{
  "event": "trade_workflow_started",
  "correlation_id": "REQ-123",
  "operation_id": "trade-submit-7f82c81a",
  "execution_arn": "arn:aws:states:..."
}
```

The external response may omit the ARN while internal logs retain it.

---

# Minimal test implementation

The companion test module is proposed as:

```text
tests/test_api_workflow_handoff.py
```

```python
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from botocore.exceptions import ClientError

from api_workflow_handoff import (
    build_execution_name,
    handle_trade_submission,
)

STATE_MACHINE_ARN = (
    "arn:aws:states:eu-west-2:123456789012:stateMachine:trade-processing"
)


def make_event(
    *,
    body: str = '{"trade_id":"TRD-1001","product":"POWER","volume_mwh":25}',
    headers: dict[str, str] | None = None,
) -> dict:
    return {
        "body": body,
        "headers": headers
        or {
            "Idempotency-Key": "submission-001",
            "X-Correlation-Id": "CORR-123",
        },
        "requestContext": {"requestId": "REQ-456"},
    }


def test_valid_request_starts_workflow_with_normalised_input() -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    assert response["statusCode"] == 202

    call = client.start_execution.call_args.kwargs
    assert call["stateMachineArn"] == STATE_MACHINE_ARN
    assert call["name"] == build_execution_name("submission-001")
    assert json.loads(call["input"]) == {
        "trade": {
            "trade_id": "TRD-1001",
            "product": "POWER",
            "volume_mwh": 25,
        },
        "correlation_id": "CORR-123",
        "idempotency_key": "submission-001",
        "request_id": "REQ-456",
    }
    assert "requestContext" not in json.loads(call["input"])
    assert "headers" not in json.loads(call["input"])


def test_valid_request_returns_truthful_accepted_response() -> None:
    client = Mock()
    client.start_execution.return_value = {
        "executionArn": "arn:aws:states:eu-west-2:123456789012:execution:trade-processing:example",
        "startDate": "2026-01-01T00:00:00Z",
    }

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 202
    assert body["status"] == "accepted_for_processing"
    assert "processed successfully" not in response["body"].lower()


def test_invalid_json_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body="not-json"),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_non_object_json_returns_400_without_starting_workflow() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(body='["TRD-1001"]'),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_missing_idempotency_key_returns_400() -> None:
    client = Mock()

    response = handle_trade_submission(
        make_event(headers={"X-Correlation-Id": "CORR-123"}),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    assert response["statusCode"] == 400
    client.start_execution.assert_not_called()


def test_retryable_step_functions_failure_returns_503_not_202() -> None:
    client = Mock()
    client.start_execution.side_effect = ClientError(
        {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            }
        },
        "StartExecution",
    )

    response = handle_trade_submission(
        make_event(),
        SimpleNamespace(aws_request_id="LAMBDA-789"),
        step_functions_client=client,
        state_machine_arn=STATE_MACHINE_ARN,
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 503
    assert body["error"] == "Workflow could not be started."
    assert "Rate exceeded" not in response["body"]


def test_execution_name_is_stable_for_same_idempotency_key() -> None:
    assert build_execution_name("submission-001") == build_execution_name(
        "submission-001"
    )
    assert build_execution_name("submission-001") != build_execution_name(
        "submission-002"
    )
```

## What the tests prove

| Test behaviour | Learning evidence |
| --- | --- |
| Valid request starts one execution | The API boundary delegates to Step Functions |
| `start_execution` receives normalized JSON | HTTP transport fields do not leak into the workflow |
| Successful start returns `202` | Acceptance is distinguished from completion |
| Invalid JSON returns `400` | External-envelope validation stays at the API boundary |
| Non-object JSON returns `400` | The public contract requires a JSON object |
| Missing idempotency key returns `400` | Logical operation identity is explicit |
| Retryable AWS error returns `503` | A failed start is not falsely reported as accepted |
| Execution name is stable | Retries can reuse deterministic technical naming |

## Local test command

```bash
PYTHONPATH=. python -m pytest -q
```

Observed result for the generated companion implementation:

```text
.......                                                                  [100%]
7 passed in 0.24s
```

No test contacted AWS. The Step Functions client was a `Mock` injected into
`handle_trade_submission`.

## Why these are not yet full production tests

The minimal suite uses `unittest.mock` to expose the core contract clearly. A
later production-shape implementation should add Botocore `Stubber` cases for
realistic service response validation and separate injected transport
exceptions such as endpoint connection and read-timeout failures.

---

# Common wrong designs

## 1. Return `202` before starting the workflow

Weak:

```python
response = accepted_response()
start_workflow()
return response
```

If the workflow start fails, the caller was told that the system accepted work
that it did not accept.

Correct:

```text
start workflow successfully
  → then return 202
```

## 2. Treat `StartExecution` success as workflow completion

Weak:

```json
{
  "message": "Trade processed successfully"
}
```

Correct:

```json
{
  "status": "accepted_for_processing"
}
```

## 3. Use the API Gateway request ID as the idempotency key

A retry receives a new API request ID.

It cannot reliably identify the same logical business operation.

## 4. Pass the raw API Gateway event into Step Functions

Weak:

```text
API Gateway proxy event
  → Step Functions
  → every task understands headers, body strings, and requestContext
```

Better:

```text
API boundary
  → normalized internal command
  → Step Functions
```

## 5. Use one identifier for everything

Weak:

```text
trade_id = correlation_id = idempotency_key = execution_name
```

This creates accidental coupling and breaks when one trade has several valid
operations.

## 6. Expose raw AWS errors

Weak response:

```json
{
  "error": "botocore.errorfactory.ExecutionLimitExceeded ..."
}
```

Better:

```json
{
  "error": "Service temporarily unavailable.",
  "correlation_id": "REQ-123"
}
```

The detailed AWS error belongs in controlled logs.

## 7. Give the API Lambda the workflow's permissions

The API Lambda normally needs permission to start the state machine, not direct
permission to perform every task that the workflow performs.

## 8. Add Lambda when mapping would be sufficient

A Lambda that merely forwards an unchanged body to one fixed state machine may
be unnecessary.

## 9. Force direct integration when mapping becomes opaque

Removing Lambda is not an architectural win if the configuration becomes hard
to understand, test, version, and operate.

## 10. Assume Standard Workflow means exactly-once side effects

Task retries and external-system behaviour still require idempotency.

---

# SAP-C02 relevance

The AWS Certified Solutions Architect – Professional exam commonly tests these
underlying judgements.

## Managed integration versus custom code

Prefer managed service integrations where they satisfy the requirement. Add
Lambda when custom transformation, validation, or control is justified.

## Synchronous versus asynchronous API

Recognise when long-running work should return `202 Accepted` and continue
outside the HTTP request lifecycle.

## Workflow type selection

Choose Standard for durable, auditable, long-running orchestration. Choose
Express for high-volume, short-duration workflows when its execution and
history semantics fit.

## Idempotency

Understand that retries can occur across HTTP clients, Lambda SDK calls, Step
Functions tasks, EventBridge, and SQS. Idempotency must be designed at the
business operation and side-effect boundaries.

## Least privilege

Separate:

- permission to invoke the API;
- permission to start the state machine;
- permission for the state machine to invoke downstream resources.

## Observability

Carry stable identifiers through API Gateway, Lambda, Step Functions, and
persistence without confusing infrastructure IDs with business IDs.

## Failure semantics

Distinguish:

```text
request rejected
workflow start failed
workflow started
workflow business validation rejected input
workflow technical failure
workflow completed successfully
```

---

# Architecture judgement checklist

Before implementing an API-to-Step Functions handoff, answer:

## Boundary

```text
Is request mapping simple enough for a direct integration?
What custom code, if any, justifies Lambda?
```

## Workflow

```text
Is Standard or Express the correct workflow type?
Is the API asynchronous or synchronous?
```

## Contract

```text
What does 202 Accepted guarantee?
How will the caller retrieve later status?
```

## Identity

```text
What are the trade ID, idempotency key, correlation ID,
execution name, and public operation ID?
```

## Failure

```text
What happens when the StartExecution outcome is unknown?
Which failures are retryable?
Which errors are safe to expose?
```

## IAM

```text
Who may invoke the API?
Which role may start which state machine?
What may the workflow role invoke?
```

## Operations

```text
Which identifiers appear in logs?
How is workflow completion observed?
How are failed executions reconciled?
```

---

# Revision questions

You should be able to answer these without reading the lesson:

1. Why can API Gateway start Step Functions without Lambda?
2. When does an API-facing Lambda remain justified?
3. What does a successful `StartExecution` call prove?
4. Why is `202 Accepted` more accurate than `200 OK` for this trade-submission
   path?
5. Why must `202` be returned only after the start call succeeds?
6. What is the difference between `idempotency_key` and `correlation_id`?
7. Why should a Step Functions execution name not automatically equal the
   trade ID?
8. What happens when a Standard Workflow receives the same running execution
   name and the same input?
9. What happens when it receives the same name with different input?
10. Why is Standard Workflow's exactly-once execution model not a guarantee of
    exactly-once side effects?
11. Why is Standard Workflow the stronger default for the tutorial's planned
    path?
12. Why can `StartSyncExecution` return HTTP `200` even when the workflow
    failed?
13. Which IAM role starts the workflow in a direct integration?
14. Which IAM role starts it in a Lambda-mediated integration?
15. Why should the API Lambda not receive all permissions required by the
    workflow?
16. When is a domain status record preferable to exposing Step Functions
    execution status directly?
17. How should an endpoint connection failure affect retry and idempotency
    design?
18. What evidence would be required before claiming the handoff works in AWS?

---

# Lesson boundary

Lesson 38 now establishes both the API-to-workflow design and a minimal
executable Python handoff.

It includes:

- a pure workflow-input builder;
- deterministic execution-name derivation;
- an injected `start_execution` adapter;
- a testable API-facing orchestration function;
- a thin Lambda runtime wrapper;
- client-safe `400`, `500`, `503`, and truthful `202` response paths;
- seven focused local tests.

It still does not:

- create an API Gateway route;
- create IAM roles or policies;
- create or deploy a state machine;
- call a live AWS account;
- add a DynamoDB-backed idempotency or status model;
- write Infrastructure as Code;
- claim deployed integration evidence;

The concrete lesson outcome is:

```text
Use direct API Gateway integration when mapping and IAM are sufficient.

Use an API-facing Lambda when meaningful boundary code is required.

For the planned trade submission, start a Standard Workflow asynchronously
and return 202 Accepted only after StartExecution succeeds.

Prove the boundary locally by testing that HTTP-shaped input becomes
domain-shaped workflow input and that failed starts never return 202.
```

This remains tutorial evidence only. It is not Energy Data Lakehouse
implementation evidence. Repository completion evidence should be recorded only
after the learner intentionally integrates or adopts the companion code and runs
the repository's own test suite.

---

# Acronym legend

| Acronym | Meaning |
| --- | --- |
| API | Application Programming Interface |
| ARN | Amazon Resource Name |
| AWS | Amazon Web Services |
| HTTP | Hypertext Transfer Protocol |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| JWT | JSON Web Token |
| SDK | Software Development Kit |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect – Professional exam code |
| SQS | Amazon Simple Queue Service |
| UUID | Universally Unique Identifier |

---

# Official references

- API Gateway direct integration with Step Functions `StartExecution`:
  <https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-api-gateway.html>
- API Gateway HTTP API AWS service integrations:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-aws-services.html>
- API Gateway HTTP API integration subtype reference:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-aws-services-reference.html>
- Step Functions `StartExecution` API reference:
  <https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html>
- Step Functions `StartSyncExecution` API reference:
  <https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartSyncExecution.html>
- Choosing Standard and Express Workflow types:
  <https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html>
- Step Functions IAM actions and resource types:
  <https://docs.aws.amazon.com/service-authorization/latest/reference/list_stepfunctions.html>
