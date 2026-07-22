# Lesson 37: API-Facing Lambda vs Internal Service Lambda

## Objective

This lesson answers:

```text
Once the entry point has been chosen,
what responsibility belongs in the first Lambda?
```

Lesson 36 selected the system entry point:

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

Lesson 37 moves one boundary inward:

```text
What contract should the Lambda receive,
and what contract should it return?
```

The key distinction is:

```text
API-facing Lambda:
  translate between HTTP and the internal system

Internal service Lambda:
  perform one bounded domain or workflow task
```

Both are AWS Lambda functions. The difference is not the runtime. The difference is the **contract and responsibility**.

---

## How this connects to Lesson 36

Lesson 36 established that these services can occupy different positions within one architecture:

```text
External client
  → API Gateway
  → API-facing Lambda
  → Step Functions
  → internal service Lambdas
  → S3 / DynamoDB
```

Each component solves a different problem:

| Component | Primary responsibility |
|---|---|
| API Gateway | Expose and govern an HTTP endpoint |
| API-facing Lambda | Translate the external HTTP request |
| Step Functions | Coordinate the workflow |
| Internal service Lambda | Execute one workflow or domain task |
| S3 / DynamoDB | Persist artifacts and state |

The important architectural boundary is here:

```text
external transport contract
          ↓
API-facing Lambda
          ↓
internal domain contract
```

The API-facing Lambda prevents HTTP-specific details from spreading through the rest of the system.

---

## Short decision rule

```text
API Lambda:
  adapt the boundary

Service Lambda:
  execute the capability
```

A second useful version is:

```text
Does the Lambda primarily understand HTTP?

Yes:
  API-facing Lambda

No:
  internal service, event-consumer, or worker Lambda
```

This distinction determines:

- input structure;
- output structure;
- error semantics;
- retry behaviour;
- logging context;
- authentication assumptions;
- coupling;
- test design.

---

## API-facing Lambda mental model

An API-facing Lambda is a **boundary adapter**.

Its primary job is not to execute the entire business process. Its job is to convert an external HTTP request into a controlled internal representation.

```text
HTTP request
  → parse
  → validate transport structure
  → extract identity and correlation data
  → normalize
  → invoke internal capability
  → map result to HTTP response
```

### Typical responsibilities

An API-facing Lambda may:

1. Read the HTTP method and path.
2. Read headers and query parameters.
3. Parse the request body.
4. Verify that the body contains valid JSON.
5. Verify that the JSON has the expected external structure.
6. Extract caller identity from the API Gateway authorizer context.
7. Extract or generate a correlation identifier.
8. Construct an internal command.
9. Start a Step Functions execution or send an SQS message.
10. Map the immediate outcome to an HTTP response.

It should normally avoid:

- performing several unrelated business operations;
- passing raw API Gateway events into downstream services;
- making downstream Lambdas understand HTTP status codes;
- mixing request parsing, orchestration, persistence, and notification in one function.

---

## What an API Gateway event contains

An API-facing Lambda commonly receives an API Gateway proxy event.

A simplified event could look like this:

```json
{
  "version": "2.0",
  "routeKey": "POST /trades",
  "rawPath": "/trades",
  "headers": {
    "content-type": "application/json",
    "x-correlation-id": "REQ-123"
  },
  "requestContext": {
    "requestId": "gateway-request-456",
    "http": {
      "method": "POST",
      "path": "/trades"
    },
    "authorizer": {
      "jwt": {
        "claims": {
          "sub": "user-789"
        }
      }
    }
  },
  "body": "{\"trade_id\":\"TRD-1001\",\"product\":\"POWER\",\"volume_mwh\":25}",
  "isBase64Encoded": false
}
```

### `headers`

```python
event["headers"]
```

Contains HTTP metadata supplied by the client or infrastructure.

Examples:

```text
content-type
authorization
x-correlation-id
user-agent
```

Headers should not be treated as trusted business data without validation.

### `requestContext`

```python
event["requestContext"]
```

Contains metadata created by API Gateway.

It may include:

- API request identifier;
- HTTP method;
- route;
- source IP address;
- authentication or authorizer information;
- stage information.

This is infrastructure context, not the trade itself.

### `body`

```python
event["body"]
```

Usually contains a **string**, not a Python dictionary.

For example:

```python
'{"trade_id":"TRD-1001","product":"POWER","volume_mwh":25}'
```

The Lambda must parse it:

```python
trade_request = json.loads(event["body"])
```

After parsing, `trade_request` becomes a Python dictionary:

```python
{
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25,
}
```

This distinction matters:

```text
API Gateway body:
  JSON text stored in a string

Internal Lambda input:
  already-decoded JSON represented as Python dictionaries and lists
```

---

## Proposed API-facing handler shape

The following is a **proposed example**, not a claim about an existing repository function.

```python
import json
from typing import Any


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    request_id = (
        event.get("requestContext", {}).get("requestId")
        or "unknown-request-id"
    )

    try:
        request_body = json.loads(event.get("body") or "")
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {
                "content-type": "application/json",
            },
            "body": json.dumps(
                {
                    "error": "Request body must contain valid JSON.",
                    "request_id": request_id,
                }
            ),
        }

    if not isinstance(request_body, dict):
        return {
            "statusCode": 400,
            "headers": {
                "content-type": "application/json",
            },
            "body": json.dumps(
                {
                    "error": "Request body must be a JSON object.",
                    "request_id": request_id,
                }
            ),
        }

    internal_command = {
        "trade": request_body,
        "correlation_id": request_id,
        "submitted_by": extract_caller_identity(event),
    }

    execution_reference = start_trade_workflow(internal_command)

    return {
        "statusCode": 202,
        "headers": {
            "content-type": "application/json",
        },
        "body": json.dumps(
            {
                "status": "accepted",
                "request_id": request_id,
                "execution_reference": execution_reference,
            }
        ),
    }
```

### What this function receives

`event`

A dictionary representing the API Gateway event.

`context`

A Lambda runtime object containing execution metadata such as:

- function name;
- invocation request ID;
- remaining execution time.

The example does not require the context object, but it remains part of the Lambda handler contract.

### What this function returns

A dictionary shaped for API Gateway:

```python
{
    "statusCode": 202,
    "headers": {...},
    "body": "...JSON string...",
}
```

The body is again encoded as a string because API Gateway expects an HTTP response payload.

---

## External validation versus domain validation

An important distinction is often missed.

### Boundary validation

The API-facing Lambda validates whether the request can safely enter the internal system.

Examples:

```text
Is the body valid JSON?
Is the body a JSON object?
Is the HTTP method allowed?
Is the caller authenticated?
Are mandatory request-envelope fields present?
Is the payload within the configured size limit?
```

### Domain validation

An internal validation Lambda checks whether the trade is valid according to business rules.

Examples:

```text
Is trade_id present?
Is volume_mwh numeric and positive?
Is the product supported?
Is the trade date valid?
Does the trade violate a business rule?
```

There can be some overlap, especially for cheap and obvious validation.

For example, an API-facing Lambda may reject a request immediately if `trade_id` is missing. But deeper business validation should not become inseparably coupled to HTTP.

A useful rule is:

```text
Reject malformed requests at the boundary.

Evaluate business validity inside the domain workflow.
```

---

## Internal service Lambda mental model

An internal service Lambda performs one bounded task.

It should understand:

- the task it has been assigned;
- the internal input contract;
- relevant domain rules;
- its direct dependencies;
- how to return success or signal failure.

It should normally not understand:

- HTTP methods;
- HTTP headers;
- API Gateway proxy envelopes;
- HTTP status codes;
- browser or client concerns.

Mental model:

```text
normalized internal input
  → execute one capability
  → return structured internal result
```

Examples from the tutorial workspace include categories such as:

- Step Functions validation handlers;
- persistence handlers;
- EventBridge consumers;
- SQS workers.

---

## Internal trade-validation example

A Step Functions task might invoke a validation Lambda with this input:

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "correlation_id": "REQ-123"
}
```

The Lambda receives decoded JSON.

In Python, the input is already a dictionary:

```python
{
    "trade": {
        "trade_id": "TRD-1001",
        "product": "POWER",
        "volume_mwh": 25,
    },
    "correlation_id": "REQ-123",
}
```

There is no API Gateway `body` string to parse.

A proposed internal handler could look like this:

```python
from typing import Any


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    trade = event["trade"]
    correlation_id = event["correlation_id"]

    validation_errors = validate_trade(trade)

    return {
        "is_valid": not validation_errors,
        "trade": trade,
        "validation_errors": validation_errors,
        "correlation_id": correlation_id,
    }
```

### What this function receives

`event`

A normalized internal command created by an upstream component.

It contains only data relevant to the workflow task:

```text
trade
correlation_id
```

It does not contain:

```text
HTTP headers
HTTP path
requestContext
API Gateway body string
HTTP method
```

### What it returns

```python
{
    "is_valid": True,
    "trade": {...},
    "validation_errors": [],
    "correlation_id": "REQ-123",
}
```

This is domain-shaped JSON.

It can be consumed directly by Step Functions:

```text
Validation Lambda
  → Choice state checks $.is_valid
```

No HTTP status code is needed.

---

## Why internal Lambdas should not return HTTP responses

Consider this internal response:

```python
return {
    "statusCode": 200,
    "body": json.dumps(
        {
            "is_valid": True,
            "trade": trade,
        }
    ),
}
```

This is technically possible, but architecturally weak.

Step Functions must now:

1. inspect `statusCode`;
2. parse the JSON string in `body`;
3. understand API Gateway conventions;
4. distinguish transport success from business success.

The workflow becomes coupled to HTTP even though there is no HTTP interaction.

A better internal result is:

```python
return {
    "is_valid": True,
    "trade": trade,
    "validation_errors": [],
}
```

Then the workflow can evaluate:

```json
{
  "Variable": "$.is_valid",
  "BooleanEquals": true,
  "Next": "PersistAcceptedTrade"
}
```

This is simpler, clearer, and easier to test.

---

## Contract comparison

| Concern | API-facing Lambda | Internal service Lambda |
|---|---|---|
| Primary contract | HTTP through API Gateway | Domain command, event, queue record, or workflow input |
| Typical caller | External client | Step Functions, SQS, EventBridge, or another AWS component |
| Input | Method, path, headers, body, identity context | Normalized JSON relevant to one task |
| Output | API Gateway-compatible response | Domain or workflow result |
| Body encoding | Often parses and serializes JSON strings | Usually receives and returns decoded JSON |
| Error model | HTTP status codes | Exceptions, task failures, batch failures, or domain results |
| Authentication | Often consumes caller identity | Usually relies on IAM and trusted service integration |
| Retry behaviour | Client or API integration dependent | Event source or orchestrator dependent |
| Main responsibility | Boundary translation | Execute a bounded capability |
| Coupling | External API contract | Internal domain or workflow contract |
| Reuse | Usually tied to an API route | Potentially reusable across workflows |
| Idempotency basis | Request or operation identifier | Event ID, message ID, execution ID, or domain key |

---

## HTTP response semantics

An API-facing Lambda must map system outcomes to accurate HTTP semantics.

### `200 OK`

Use when the request completed successfully and the response represents the completed operation.

Example:

```text
GET /trades/TRD-1001
```

The trade was retrieved and returned.

### `201 Created`

Use when a new resource has been created synchronously.

Example:

```text
POST /trade-drafts
```

A trade draft was persisted before the response was returned.

### `202 Accepted`

Use when the request has been accepted but processing continues asynchronously.

Example:

```text
POST /trades
  → API-facing Lambda
  → starts Step Functions execution
  → returns immediately
```

Response:

```json
{
  "status": "accepted",
  "request_id": "REQ-123"
}
```

The response means:

```text
The system accepted responsibility for processing.
```

It does not mean:

```text
The trade completed all validation and persistence steps.
```

This distinction is operationally important.

Returning `200 OK` with a message such as `"trade processed"` when the system merely queued the request is misleading.

### `400 Bad Request`

Use when the external request is malformed or violates the public request contract.

Examples:

- invalid JSON;
- body is not an object;
- required request field missing;
- invalid query parameter.

### `401 Unauthorized`

Use when valid authentication credentials are missing or invalid.

Authentication is often handled by API Gateway or an authorizer before the Lambda runs.

### `403 Forbidden`

Use when the caller is authenticated but not permitted to perform the operation.

### `404 Not Found`

Use when the requested public resource does not exist.

### `409 Conflict`

Can be appropriate when the request conflicts with existing state.

Examples:

- duplicate trade identifier;
- invalid state transition;
- resource already exists.

### `500 Internal Server Error`

Use for unexpected server-side failures.

Do not expose:

- stack traces;
- AWS credentials;
- internal resource names unnecessarily;
- sensitive payload fields;
- raw downstream exceptions.

### `503 Service Unavailable`

May be appropriate when a required downstream dependency is temporarily unavailable and the client may retry.

The exact mapping depends on the public API contract.

---

## Domain invalidity is not always a Lambda failure

An internal validation Lambda must distinguish two different conditions.

### Expected domain rejection

Example:

```text
volume_mwh is negative
```

The Lambda executed successfully and determined that the trade is invalid.

A structured result is appropriate:

```python
{
    "is_valid": False,
    "trade": trade,
    "validation_errors": [
        {
            "field": "volume_mwh",
            "code": "MUST_BE_POSITIVE",
        }
    ],
}
```

The Step Functions workflow can route this through a `Choice` state.

```text
ValidateTrade
  → Choice
      valid   → persist accepted
      invalid → persist rejected
```

This is not necessarily a system failure.

### Unexpected technical failure

Example:

```text
required configuration missing
dependency unavailable
internal programming defect
unexpected data structure
```

The Lambda should normally raise an exception.

```python
raise RuntimeError("Trade reference data service unavailable")
```

Step Functions can then apply:

```text
Retry
Catch
terminal failure handling
```

This distinction prevents expected business outcomes from being treated like infrastructure faults.

---

## Error handling comparison

### API-facing Lambda

The function often catches known boundary errors and maps them to HTTP.

```python
try:
    body = json.loads(event["body"])
except json.JSONDecodeError:
    return error_response(
        status_code=400,
        message="Request body must contain valid JSON.",
    )
```

Unexpected failures may be logged and mapped to a generic response:

```python
except Exception:
    logger.exception(
        "Unexpected API request failure",
        extra={"request_id": request_id},
    )

    return error_response(
        status_code=500,
        message="Internal server error.",
    )
```

The client should not receive internal exception details.

### Internal Step Functions Lambda

Known business outcomes are returned as data.

Unexpected technical failures are raised:

```python
def lambda_handler(event, context):
    trade = event["trade"]

    validation_errors = validate_trade(trade)

    return {
        "is_valid": not validation_errors,
        "validation_errors": validation_errors,
        "trade": trade,
    }
```

For a genuine dependency failure:

```python
def persist_trade(event, context):
    try:
        persistence_result = write_trade(event["trade"])
    except TemporaryPersistenceError as exc:
        raise RuntimeError("Persistence temporarily unavailable") from exc

    return {
        "persistence_status": "completed",
        "result": persistence_result,
    }
```

Step Functions controls the retry policy.

### SQS Lambda

An SQS-triggered Lambda has different semantics.

It may receive several records in one invocation:

```json
{
  "Records": [
    {
      "messageId": "msg-001",
      "body": "{\"trade_id\":\"TRD-1001\"}"
    },
    {
      "messageId": "msg-002",
      "body": "{\"trade_id\":\"TRD-1002\"}"
    }
  ]
}
```

The Lambda may return a partial batch response:

```json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "msg-002"
    }
  ]
}
```

It must not return:

```python
{
    "statusCode": 500,
    "body": "...",
}
```

SQS does not interpret API Gateway responses.

The correct output contract is determined by the event source.

### EventBridge Lambda

An EventBridge consumer usually either:

- completes successfully; or
- raises an exception.

Its return value is normally not used as an HTTP response.

The event might look like:

```json
{
  "id": "event-123",
  "source": "com.example.trade",
  "detail-type": "TradeCaptured",
  "time": "2026-07-23T12:00:00Z",
  "detail": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  }
}
```

The consumer should understand:

```text
source
detail-type
detail
event ID
event time
```

It should not return an API Gateway envelope.

---

## One Lambda runtime, several contracts

A Lambda function is not inherently:

```text
an API function
an SQS worker
a workflow task
an EventBridge consumer
```

Lambda is only the compute runtime.

The invocation source defines the contract.

| Invocation source | Expected Lambda concern |
|---|---|
| API Gateway | HTTP request and response |
| SQS | Batch records and partial batch failure |
| EventBridge | Event envelope and event processing |
| Step Functions | Task input, task result, exceptions |
| S3 event | Object-created or object-removed event |
| Direct invocation | Caller-defined JSON contract |

Therefore, this statement is incorrect:

```text
All Lambda handlers should return statusCode and body.
```

A more accurate statement is:

```text
A Lambda should return the response shape expected by its caller.
```

---

## Boundary normalization

The API-facing Lambda should reduce the external event into an internal command.

### Raw API Gateway input

```json
{
  "version": "2.0",
  "routeKey": "POST /trades",
  "headers": {
    "authorization": "Bearer ...",
    "x-correlation-id": "REQ-123"
  },
  "requestContext": {
    "requestId": "gateway-456",
    "authorizer": {
      "jwt": {
        "claims": {
          "sub": "user-789"
        }
      }
    }
  },
  "body": "{\"trade_id\":\"TRD-1001\",\"product\":\"POWER\",\"volume_mwh\":25}"
}
```

### Normalized internal command

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "submission": {
    "correlation_id": "REQ-123",
    "submitted_by": "user-789",
    "channel": "trade-api"
  }
}
```

The internal workflow does not need:

```text
routeKey
rawPath
HTTP headers
API Gateway version
JWT envelope structure
```

It receives only relevant business and operational context.

This is an **anti-corruption boundary**: external transport details are prevented from contaminating the internal model.

---

## Do not pass raw API Gateway events through Step Functions

### Weak design

```text
API Gateway
  → Lambda
  → Step Functions receives entire API Gateway event
  → validation Lambda reads event.body
  → persistence Lambda reads requestContext
```

Problems:

1. Every workflow task becomes coupled to API Gateway.
2. The workflow cannot easily be started by another source.
3. Tests require large synthetic API events.
4. Changes to the API contract may affect internal tasks.
5. Sensitive headers may be persisted or logged accidentally.
6. The workflow payload is larger than necessary.
7. Internal services cannot be reused cleanly.

### Better design

```text
API Gateway
  → API-facing Lambda
      parse body
      extract identity
      normalize command
  → Step Functions
      receives internal command
  → internal Lambdas
```

This allows the same workflow to be started later by another trusted source:

```text
EventBridge
  → event adapter Lambda
  → same internal command
  → same Step Functions workflow
```

The external adapters differ. The workflow contract remains stable.

---

## API Gateway over asynchronous processing

Consider this architecture:

```text
Client
  → API Gateway
  → API-facing Lambda
  → SQS
  → worker Lambda
  → S3 / DynamoDB
```

### API-facing Lambda responsibility

The API-facing Lambda:

1. validates the HTTP request;
2. creates an internal message;
3. sends the message to SQS;
4. returns `202 Accepted`.

Example public response:

```json
{
  "status": "accepted",
  "request_id": "REQ-123",
  "trade_id": "TRD-1001"
}
```

### Worker Lambda responsibility

The worker Lambda:

1. reads SQS records;
2. parses each message body;
3. processes the trade;
4. handles duplicate delivery;
5. records partial batch failures;
6. persists results.

The worker does not return an HTTP response.

This architecture separates:

```text
HTTP availability
```

from:

```text
trade-processing throughput
```

SQS provides buffering and retry behaviour between the two components.

---

## API Gateway over Step Functions

Another architecture is:

```text
Client
  → API Gateway
  → API-facing Lambda
  → Step Functions
  → validation Lambda
  → persistence Lambda
```

The API-facing Lambda may call `StartExecution`.

Conceptually:

```python
internal_input = {
    "trade": request_body,
    "correlation_id": request_id,
}

execution = start_workflow(internal_input)
```

The API-facing Lambda returns:

```python
{
    "statusCode": 202,
    "body": json.dumps(
        {
            "status": "accepted",
            "request_id": request_id,
            "execution_reference": execution.reference,
        }
    ),
}
```

Step Functions then controls:

- validation;
- branching;
- retries;
- catches;
- persistence;
- terminal success;
- terminal failure.

The API Lambda should not reimplement the workflow in Python.

---

## When API Gateway can start Step Functions directly

An important architecture challenge is:

```text
Do we need the API-facing Lambda at all?
```

API Gateway can integrate directly with some AWS services, including Step Functions.

A direct integration may be appropriate when:

- request transformation is simple;
- authentication is handled by API Gateway;
- no substantial Python validation is required;
- no custom business translation is needed;
- the integration can produce the required response contract;
- operational complexity is lower without Lambda.

Possible design:

```text
Client
  → API Gateway
  → Step Functions StartExecution
```

This removes:

- a Lambda deployment;
- a Lambda invocation;
- one codebase;
- one failure boundary.

However, an API-facing Lambda remains justified when it provides meaningful capability:

- non-trivial JSON validation;
- identity translation;
- complex request normalization;
- custom idempotency logic;
- dynamic routing;
- compatibility with an existing public API;
- controlled response mapping.

The architecture rule is:

```text
Do not add Lambda merely because Lambda is familiar.

Add it when code is required at that boundary.
```

---

## Internal service Lambda does not automatically mean microservice

A Lambda function may be:

- a Step Functions task;
- an SQS batch worker;
- an EventBridge adapter;
- a persistence adapter;
- a validation function;
- a notification function.

That does not automatically make it a microservice.

A genuine microservice normally has a stronger boundary:

- independently owned business capability;
- explicit interface;
- independent deployment lifecycle;
- autonomous data ownership;
- operational ownership;
- security boundary;
- versioning strategy.

A small Lambda used by one state machine is better described as:

```text
workflow task Lambda
```

rather than:

```text
trade-validation microservice
```

Overusing the term microservice obscures the actual architecture.

---

## Logging and correlation identifiers

API-facing and internal Lambdas should carry the same correlation identifier through the workflow.

Example flow:

```text
Client request
  correlation_id = REQ-123

API Gateway
  → API-facing Lambda logs REQ-123

Step Functions input
  → carries REQ-123

Validation Lambda
  → logs REQ-123

Persistence Lambda
  → logs REQ-123

DynamoDB status record
  → stores REQ-123
```

### API-facing log context

```python
logger.info(
    "Trade submission accepted",
    extra={
        "correlation_id": correlation_id,
        "trade_id": trade_id,
        "route": "POST /trades",
    },
)
```

### Internal service log context

```python
logger.info(
    "Trade validation completed",
    extra={
        "correlation_id": correlation_id,
        "trade_id": trade_id,
        "is_valid": is_valid,
    },
)
```

The internal function should not need to reconstruct the correlation ID from an API Gateway-specific location.

It should receive it explicitly:

```python
event["correlation_id"]
```

---

## Request ID versus correlation ID

These identifiers are related but not identical.

### API Gateway request ID

Generated for one API request.

```text
gateway-request-456
```

Useful for tracing API Gateway and Lambda invocation logs.

### Lambda request ID

Generated for one Lambda invocation.

```text
lambda-invocation-789
```

A retry creates a new Lambda invocation ID.

### Step Functions execution ID

Identifies one workflow execution.

### SQS message ID

Identifies one queue message.

### Domain identifier

Example:

```text
trade_id = TRD-1001
```

### Correlation ID

Chosen to connect activity across the full operation.

```text
correlation_id = REQ-123
```

A robust system records several identifiers rather than pretending they are interchangeable.

Example structured context:

```json
{
  "correlation_id": "REQ-123",
  "trade_id": "TRD-1001",
  "api_request_id": "gateway-request-456",
  "workflow_execution_id": "execution-789"
}
```

---

## Authentication and authorization boundaries

### API-facing Lambda

The API-facing Lambda may consume identity claims supplied by API Gateway.

Example:

```python
claims = (
    event.get("requestContext", {})
    .get("authorizer", {})
    .get("jwt", {})
    .get("claims", {})
)

caller_id = claims.get("sub")
```

The Lambda may use these claims to construct an internal identity context:

```python
{
    "principal_id": caller_id,
    "permissions": ["trade:submit"],
}
```

It should not pass the full raw token through the workflow unless there is a justified requirement.

Reasons:

- tokens may contain sensitive claims;
- tokens may expire during a long-running workflow;
- downstream Lambdas should not all become token-validation services;
- logging risk increases.

### Internal service Lambda

Internal callers usually authenticate using AWS Identity and Access Management roles and service permissions.

Examples:

```text
Step Functions execution role may invoke ValidateTrade Lambda.

API-facing Lambda role may start one named state machine.

Worker Lambda role may read from one queue and write to one table.
```

The internal service Lambda should still enforce relevant authorization boundaries where necessary, but it does not normally process an external bearer token.

---

## Least-privilege permissions

Different Lambda responsibilities require different Identity and Access Management permissions.

### API-facing Lambda

Possible permissions:

```text
states:StartExecution
```

on one state machine.

Or:

```text
sqs:SendMessage
```

on one queue.

It may not need permission to:

```text
write S3
write DynamoDB
publish every EventBridge event
invoke every Lambda
```

### Validation Lambda

May require no AWS service permissions at all if validation is pure Python.

### Persistence Lambda

May require:

```text
s3:PutObject
dynamodb:PutItem
```

restricted to specific resources and key patterns.

### SQS worker

May require:

- queue-consumption permissions provided by the event source mapping;
- persistence permissions;
- possibly dead-letter or notification permissions, depending on the design.

Separating responsibilities supports least privilege.

One all-purpose Lambda often leads to one overpowered execution role.

---

## Dependency ownership

A useful design question is:

```text
Which component should own each AWS service call?
```

Example architecture:

```text
API-facing Lambda
  → starts workflow

Validation Lambda
  → pure validation, no AWS calls

Persistence Lambda
  → writes S3 and DynamoDB

Event-publishing step
  → publishes TradeAccepted
```

This produces clearer dependency ownership.

| Component | Dependency |
|---|---|
| API-facing Lambda | Step Functions client |
| Validation Lambda | None, ideally |
| Persistence Lambda | S3 and DynamoDB clients |
| Notification component | SNS or EventBridge client |

This improves:

- unit testing;
- IAM scoping;
- failure diagnosis;
- maintainability;
- observability.

---

## `boto3` positioning

`boto3` is the AWS Software Development Kit for Python.

A Lambda does not need `boto3` merely because it runs on AWS.

### No `boto3` needed to receive

- an API Gateway event;
- an EventBridge event;
- an SQS batch;
- a Step Functions task input.

AWS invokes the Lambda and supplies the event.

### `boto3` may be needed when the Lambda actively calls AWS

Examples:

- start a Step Functions execution;
- send an SQS message;
- write an S3 object;
- write a DynamoDB item;
- publish an EventBridge event;
- send an SNS notification.

The important distinction is:

```text
Receiving an event:
  Lambda runtime responsibility

Calling another AWS service:
  AWS SDK or managed integration responsibility
```

Lesson 37 is not yet the dedicated `boto3` implementation lesson.

---

## Retry models differ by boundary

### API-facing Lambda

A client may retry an HTTP request because:

- it timed out;
- it received a `5xx` response;
- the network connection failed;
- it did not receive the response.

The system may therefore receive the same logical submission more than once.

The API layer may need:

- an idempotency key;
- a client-supplied request identifier;
- duplicate-submission protection;
- stable operation status retrieval.

### Step Functions task Lambda

Step Functions may retry according to the state-machine definition.

```json
{
  "Retry": [
    {
      "ErrorEquals": ["Lambda.ServiceException"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2
    }
  ]
}
```

The task may therefore run more than once.

### SQS worker Lambda

SQS delivery is at least once.

The same message may be delivered more than once.

The worker must assume duplicates are possible.

### EventBridge consumer Lambda

EventBridge also provides retry behaviour and can deliver an event more than once.

Therefore:

```text
Internal does not mean exactly once.
```

Idempotency remains necessary.

The idempotency key depends on the contract:

| Source | Candidate key |
|---|---|
| Public API | Client idempotency key |
| Step Functions | Execution ID plus task or business key |
| SQS | Domain operation ID, not only message ID |
| EventBridge | Event ID or domain event ID |
| Trade persistence | Trade ID plus version or processing stage |

---

## Timeout boundaries

An API-facing Lambda is constrained by the client-facing request lifecycle.

Even where infrastructure allows a relatively long timeout, making a client wait for an entire trade workflow is often a poor design.

Weak design:

```text
Client waits
  → API Lambda validates
  → writes S3
  → writes DynamoDB
  → calls external service
  → publishes event
  → sends notification
  → returns response
```

Risks:

- client timeout;
- duplicate retry;
- long-held connection;
- difficult partial-failure handling;
- poor user experience;
- tightly coupled availability.

Better design:

```text
Client
  → submit request
  → receive 202 Accepted

Internal workflow
  → complete independently
```

The client can query status:

```text
GET /trade-submissions/REQ-123
```

or receive a later notification.

---

## Common wrong designs

### 1. HTTP responses everywhere

Weak internal function:

```python
def lambda_handler(event, context):
    result = validate_trade(event)

    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }
```

Problem:

```text
The internal caller receives a transport envelope
instead of a domain result.
```

Correction:

```python
def lambda_handler(event, context):
    result = validate_trade(event["trade"])

    return {
        "is_valid": result.is_valid,
        "validation_errors": result.errors,
        "trade": event["trade"],
    }
```

### 2. Raw API event passed downstream

Weak:

```python
workflow_input = event
```

This passes:

- headers;
- request context;
- HTTP route;
- raw body string;
- authorizer details;
- infrastructure metadata.

Better:

```python
workflow_input = {
    "trade": parsed_body,
    "correlation_id": correlation_id,
    "submitted_by": caller_id,
}
```

### 3. One Lambda does everything

Weak architecture:

```text
API Gateway
  → one Lambda:
      parse HTTP
      authenticate caller
      validate trade
      check reference data
      write S3
      write DynamoDB
      publish EventBridge event
      send notification
      map HTTP response
```

This produces:

- broad IAM permissions;
- complex test setup;
- long runtime;
- ambiguous failure handling;
- poor retry safety;
- high coupling;
- difficult deployment changes;
- weak observability.

A better decomposition is:

```text
API-facing Lambda
  → normalize and start workflow

Validation Lambda
  → validate trade

Persistence component
  → persist result

Event publisher
  → publish outcome
```

However, decomposition also has a cost:

- more resources;
- more deployment units;
- more logs;
- more orchestration;
- more contracts;
- more operational complexity.

Therefore, do not split every ten-line function into a separate Lambda.

Use a separate Lambda when there is a meaningful boundary:

- different retry policy;
- different IAM permissions;
- different timeout;
- different scaling profile;
- different dependency set;
- independent failure handling;
- meaningful reuse;
- clear workflow stage.

### 4. Lambda-to-Lambda invocation chains

Weak pattern:

```text
API Lambda
  → invokes validation Lambda
      → invokes persistence Lambda
          → invokes notification Lambda
```

This creates hidden orchestration in application code.

Problems:

- difficult failure tracing;
- unclear retry ownership;
- nested timeouts;
- synchronous coupling;
- hard-to-observe execution path;
- duplicated orchestration logic.

Better:

```text
API Lambda
  → Step Functions
      → validation Lambda
      → persistence Lambda
      → notification step
```

Step Functions makes the orchestration explicit.

### 5. Misleading synchronous success

Weak response:

```json
{
  "status": "completed"
}
```

when the Lambda only sent a message to SQS.

Correct response:

```json
{
  "status": "accepted",
  "request_id": "REQ-123"
}
```

with:

```text
HTTP 202 Accepted
```

The response must accurately describe the boundary the system has crossed.

### 6. Trusting internal input blindly

An internal Lambda may be invoked by a trusted AWS service, but this does not mean the payload is guaranteed to be valid.

Possible causes:

- upstream application defect;
- state-machine mapping error;
- event schema version mismatch;
- malformed queue message;
- manual replay error;
- old event format;
- partial deployment.

Internal functions still need appropriate validation.

The distinction is not:

```text
external input:
  validate

internal input:
  trust completely
```

The better rule is:

```text
Validate according to the boundary.

External boundary:
  validate transport, identity, and public contract

Internal boundary:
  validate required task and domain assumptions
```

---

## Applying the distinction to the trade tutorial

Based on the visible workspace structure, the current handlers represent different boundary types.

### `trade_handler.py`

This is described as API-style Lambda validation.

Its responsibilities are likely closest to:

```text
API-facing boundary
```

Relevant concerns include:

- request parsing;
- validation;
- logging;
- stable HTTP responses.

### `eventbridge_trade_handler.py`

This represents:

```text
EventBridge consumer boundary
```

It should understand EventBridge fields such as:

```text
detail
event ID
detail-type
source
```

It should not return an HTTP proxy response.

### `sqs_trade_handler.py`

This represents:

```text
queue worker boundary
```

It should understand:

```text
Records
message body
messageId
partial batch failure
duplicate delivery
```

### `step_functions_validate_trade_handler.py`

This represents:

```text
internal workflow task
```

It should receive normalized workflow JSON and return a domain validation result.

### Persistence modules

The workspace identifies persistence modules for S3, DynamoDB, and combined persistence. These represent internal capabilities rather than HTTP endpoints.

The separation already visible in the tutorial is therefore useful evidence for Lesson 37:

```text
Same Lambda runtime
Different invocation contracts
Different response contracts
Different failure semantics
```

---

## Recommended trade-processing boundary

A clean architecture could look like this:

```text
POST /trades
      |
      v
API Gateway
      |
      v
API-facing Lambda
  - parse HTTP body
  - consume caller identity
  - validate request envelope
  - assign correlation ID
  - create internal command
  - start workflow
      |
      v
Step Functions
      |
      +--> ValidateTrade Lambda
      |      - validate domain rules
      |      - return domain result
      |
      +--> Choice
      |      - valid
      |      - invalid
      |
      +--> Persistence task
      |      - store artifact
      |      - store status
      |
      +--> Publish outcome
             - TradeAccepted
             - TradeRejected
```

The external client sees an API contract.

The internal system sees a domain contract.

---

## Example contract progression

### Stage 1: External request

```http
POST /trades
Content-Type: application/json
X-Correlation-Id: REQ-123
```

```json
{
  "trade_id": "TRD-1001",
  "product": "POWER",
  "volume_mwh": 25
}
```

### Stage 2: API Gateway event

```json
{
  "headers": {
    "x-correlation-id": "REQ-123"
  },
  "requestContext": {
    "requestId": "gateway-456"
  },
  "body": "{\"trade_id\":\"TRD-1001\",\"product\":\"POWER\",\"volume_mwh\":25}"
}
```

### Stage 3: Internal command

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "submission": {
    "correlation_id": "REQ-123",
    "api_request_id": "gateway-456",
    "channel": "trade-api"
  }
}
```

### Stage 4: Validation result

```json
{
  "trade": {
    "trade_id": "TRD-1001",
    "product": "POWER",
    "volume_mwh": 25
  },
  "validation": {
    "is_valid": true,
    "errors": []
  },
  "submission": {
    "correlation_id": "REQ-123"
  }
}
```

### Stage 5: Persistence result

```json
{
  "trade_id": "TRD-1001",
  "processing_status": "ACCEPTED",
  "artifact": {
    "bucket": "trade-results",
    "key": "accepted/POWER/TRD-1001.json"
  },
  "correlation_id": "REQ-123"
}
```

### Stage 6: API response

For asynchronous processing:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
```

```json
{
  "status": "accepted",
  "request_id": "REQ-123",
  "trade_id": "TRD-1001"
}
```

The internal validation and persistence results are not automatically returned to the original client.

The API contract must define how the client retrieves later status.

---

## Security consequences

Separating the API boundary from internal capability reduces the attack surface.

### API-facing concerns

- validate untrusted input;
- limit payload size;
- reject unsupported content types;
- consume authenticated identity;
- avoid logging tokens;
- apply rate limits through API Gateway;
- support Web Application Firewall controls if required;
- prevent injection into downstream commands.

### Internal service concerns

- least-privilege execution role;
- validate internal contract;
- encrypt sensitive data;
- avoid logging full trade payloads unnecessarily;
- restrict invocation permissions;
- protect S3 and DynamoDB resources;
- use explicit event schemas;
- control replay and idempotency.

The boundary does not remove security obligations. It makes them clearer.

---

## Scalability consequences

The two Lambda categories may scale differently.

### API-facing Lambda

Scales with HTTP request volume.

Potential controls:

- API Gateway throttling;
- reserved concurrency;
- request quotas;
- authentication limits;
- payload limits.

### SQS worker Lambda

Scales according to:

- queue depth;
- batch size;
- event source mapping concurrency;
- downstream capacity;
- visibility timeout;
- failure rate.

### Step Functions task Lambda

Scales according to:

- workflow execution volume;
- parallel states;
- retry behaviour;
- state transition design.

A single Lambda handling all concerns loses these independent scaling controls.

---

## Reliability consequences

Separating the boundary allows the system to acknowledge requests independently of downstream processing.

```text
HTTP request accepted
        ≠
trade processing completed
```

This enables:

- queue buffering;
- workflow retries;
- dead-letter handling;
- manual review;
- asynchronous status tracking;
- controlled failure recovery.

The API-facing Lambda remains small and responsive while internal processing follows its own reliability model.

---

## Cost consequences

More functions and Step Functions states can increase:

- request charges;
- state transition charges;
- logging volume;
- deployment overhead.

However, a single oversized Lambda can increase:

- execution duration;
- memory cost;
- retry cost;
- duplicate side effects;
- engineering effort;
- incident-recovery cost.

The goal is not maximum decomposition.

The goal is:

```text
the smallest number of components
that preserve clear contracts,
retry safety,
security boundaries,
and operational visibility
```

---

## Maintainability consequences

A clear boundary improves test design.

### API-facing tests

Test:

- missing body;
- invalid JSON;
- body not an object;
- missing request ID;
- authentication context;
- correct internal command;
- correct HTTP status code;
- correct response encoding.

### Internal validation tests

Test:

- valid trade;
- missing field;
- invalid volume;
- unsupported product;
- domain rejection structure;
- unexpected exception behaviour.

### SQS worker tests

Test:

- one valid record;
- one malformed record;
- mixed-success batch;
- duplicate delivery;
- partial batch response.

Each test suite remains focused on one contract.

---

## Observability consequences

A well-designed boundary should make it possible to answer:

```text
Which client request started this workflow?

Which workflow processed this trade?

Which Lambda invocation failed?

Which SQS message was retried?

Which persistence record represents the final state?
```

Useful fields include:

```text
correlation_id
trade_id
api_request_id
lambda_request_id
workflow_execution_id
event_id
message_id
processing_stage
attempt_number
```

Do not log all available data merely because it exists.

Log identifiers and state transitions deliberately.

---

## SAP-C02 relevance

The AWS Certified Solutions Architect – Professional exam commonly tests the underlying design principles represented here.

### Decoupling

Recognize when an API should accept work asynchronously rather than hold the connection open.

```text
API Gateway
  → Lambda
  → SQS
  → worker
```

### Orchestration

Recognize when Step Functions should coordinate tasks instead of embedding Lambda-to-Lambda orchestration.

### Managed integrations

Recognize when API Gateway or Step Functions can call an AWS service directly and remove unnecessary Lambda code.

### Failure handling

Understand that:

- API clients retry differently from SQS;
- SQS uses at-least-once delivery;
- Step Functions can apply explicit Retry and Catch rules;
- EventBridge has its own retry and dead-letter handling.

### Least privilege

Different functions should receive only the permissions required for their role.

### Asynchronous response semantics

Understand the architectural meaning of:

```text
202 Accepted
```

### Loose coupling

Internal workflows should not depend on HTTP-specific response envelopes unless HTTP is genuinely their interface.

---

## Architecture judgement test

For each function, ask these questions.

### Contract

```text
Who invokes this function?
What exact input shape does the caller provide?
What output shape does the caller expect?
```

### Responsibility

```text
Is it translating a boundary,
or executing a business capability?
```

### Error handling

```text
Should this failure become:
- an HTTP response;
- a domain result;
- a raised exception;
- an SQS batch failure?
```

### Retry ownership

```text
Who retries:
- the client;
- API Gateway;
- Step Functions;
- SQS;
- EventBridge?
```

### Coupling

```text
Could this function be reused without carrying transport-specific details?
```

### IAM

```text
What is the minimum set of AWS permissions this function needs?
```

### Observability

```text
Which identifiers must survive across this boundary?
```

---

## Final mental model

```text
API-facing Lambda
  knows HTTP
  protects the boundary
  normalizes external input
  returns HTTP-shaped output
```

```text
Internal service Lambda
  knows one task
  consumes normalized input
  returns domain-shaped output
  fails according to its orchestrator or event-source contract
```

The architecture boundary is:

```text
API Gateway event
      |
      v
API-facing Lambda
      |
      |  removes HTTP-specific structure
      v
internal command
      |
      v
Step Functions
      |
      v
internal service Lambdas
```

---

## Lesson boundary

Lesson 37 establishes the design distinction only.

It does not yet:

- add production code;
- add `boto3` calls;
- deploy AWS resources;
- write Terraform;
- add new tests;
- update `LEARNING-PLAN.md`;
- claim any tests were run.

The lesson outcome is:

```text
An API-facing Lambda returns HTTP-shaped responses
because HTTP is its contract.

An internal service Lambda returns domain-shaped data
because a workflow, event source, or internal caller is its contract.
```

---

## Acronym legend

| Acronym | Meaning |
|---|---|
| API | Application Programming Interface |
| AWS | Amazon Web Services |
| HTTP | Hypertext Transfer Protocol |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| JWT | JSON Web Token |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect – Professional exam code |
| SDK | Software Development Kit |
| SNS | Amazon Simple Notification Service |
| SQS | Amazon Simple Queue Service |
