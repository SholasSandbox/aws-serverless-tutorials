# Lesson 28: Persistence Handler Boundary Hardening

## Purpose

This note records what Lesson 28 established about hardening the Lambda
handler boundary for the persistence workflow.

It is tutorial evidence only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note.
- Use the current Python code and tests as the source of truth.

## What this lesson established

Lessons 25 and 26 built the S3 and DynamoDB persistence modules. The workflow
module (`trade_persistence_workflow.py`) connected them. But the Lambda
boundary module (`trade_persistence_handler.py`) was a thin shell that passed
events through without strict validation.

Lesson 28 rewrote `trade_persistence_handler.py` to production shape:

- strict input validation at the Lambda boundary before any AWS call is made;
- typed internal helpers for repeated validation patterns;
- structured error logging with `trade_id` context on unexpected failures;
- clean separation between the Lambda boundary and the workflow layer;
- environment variable validation at cold-start via `build_persistence_dependencies`.


## Module: `trade_persistence_handler.py`

### Layer responsibilities

```text
lambda_handler          <- Lambda entrypoint; builds dependencies, delegates
  build_persistence_dependencies  <- validates env vars, creates boto3 clients
  trade_persistence_handler       <- validates event, calls workflow, logs errors
    extract_persistence_event_parts <- validates all event fields before AWS
    persist_trade_processing_result <- S3 + DynamoDB writes (workflow layer)
```

Each layer has a single responsibility. The Lambda entrypoint does not validate
events. The workflow does not read environment variables. The boundary handler
does not construct boto3 clients.

### `extract_persistence_event_parts`

This function is the validation gate. It runs before any AWS call. If it
raises, no S3 or DynamoDB write has occurred.

```python
def extract_persistence_event_parts(event: Any) -> dict[str, Any]:
```

Validation order:

1. `event` must be a `dict`
2. Required top-level fields: `trade`, `validation`, `processed_at`
3. `trade` must be a `dict`
4. `validation` must be a `dict`
5. `processed_at` must be a non-empty string
6. Required trade fields: `trade_id`, `product`, `volume_mwh`
7. `trade_id` must be a non-empty string (not blank/whitespace)
8. `product` must be a non-empty string
9. `volume_mwh` must be a number (not bool, not string)
10. Required validation fields: `is_valid`, `errors`
11. `is_valid` must be a boolean
12. `errors` must be a list

Each failure raises `ValueError` with a descriptive message. No partial
validation passes silently.


### Internal helper functions

Two helpers eliminate repeated validation patterns:

```python
def require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_number(value: Any, field_name: str) -> int | float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    return value
```

`require_number` explicitly excludes `bool` because `isinstance(True, int)`
is `True` in Python. Without the bool guard, `True` and `False` would pass
as numbers, which is a silent type bug.

### Structured error logging

`trade_persistence_handler` wraps the workflow call in a `try/except`:

```python
try:
    return persist_trade_processing_result(...)
except Exception:
    logger.exception(
        "Unexpected persistence handler error trade_id=%s",
        validated_event["trade"]["trade_id"],
    )
    raise
```

The `trade_id` is included in the log context so that any unexpected failure
can be correlated with the specific trade that triggered it. The exception
is re-raised so Step Functions sees the failure and can apply its own retry
or catch logic.

### Environment variable validation

`build_persistence_dependencies` reads two required environment variables and
raises `ValueError` if either is missing:

```python
TRADE_RESULTS_BUCKET_ENV_VAR = "TRADE_RESULTS_BUCKET"
TRADE_STATUS_TABLE_ENV_VAR = "TRADE_STATUS_TABLE_NAME"
```

This fails loudly at cold-start rather than silently at the first S3 or
DynamoDB call with an unhelpful boto3 error.


## Tests established

### Boundary validation tests (parametrized)

| Test | What it proves |
|---|---|
| `test_extract_persistence_event_parts_rejects_non_dict_event` | `None`, int, string, list all raise `ValueError` |
| `test_extract_persistence_event_parts_rejects_trade_that_is_not_dict` | `None`, int, string, list for `trade` all raise |
| `test_extract_persistence_event_parts_rejects_validation_that_is_not_dict` | Same for `validation` |
| `test_extract_persistence_event_parts_rejects_non_boolean_validation_is_valid` | `None`, list, int, string for `is_valid` all raise |
| `test_extract_persistence_event_parts_rejects_validation_errors_is_not_list` | int, string, dict for `errors` all raise |
| `test_extract_persistence_event_parts_rejects_non_numeric_trade_volume_mwh` | `None`, string, list, bool all raise |
| `test_extract_persistence_event_parts_rejects_missing_trade_id` | Missing field raises with field name in message |
| `test_extract_persistence_event_parts_rejects_empty_trade_id` | Blank and whitespace-only strings raise |
| `test_extract_persistence_event_parts_rejects_empty_trade_product` | Same for `product` |
| `test_extract_persistence_event_parts_returns_expected_parts` | Valid event returns clean dict |

### Handler integration tests

| Test | What it proves |
|---|---|
| `test_trade_persistence_handler_persists_accepted_trade_result` | Full accepted trade round trip through handler |
| `test_trade_persistence_handler_persists_rejected_trade_result` | Full rejected trade round trip |
| `test_trade_persistence_handler_rejects_missing_processed_at` | Missing field stops execution before any AWS call |
| `test_build_persistence_dependencies_uses_environment_and_boto3` | Env vars read; boto3 clients created correctly |
| `test_lambda_handler_builds_dependencies_and_delegates` | `lambda_handler` calls `build_persistence_dependencies` then delegates |
| `test_build_persistence_dependencies_requires_results_bucket_env` | Missing bucket env var raises `ValueError` |
| `test_build_persistence_dependencies_requires_status_table_env` | Missing table env var raises `ValueError` |
| `test_trade_persistence_handler_logs_and_reraises_unexpected_s3_put_failure` | S3 error is logged with `trade_id` and re-raised; DynamoDB not called |
| `test_trade_persistence_handler_logs_and_reraises_unexpected_dynamodb_put_failure` | DynamoDB error is logged with `trade_id` and re-raised |

36 new tests were added in this lesson.

## Why validation belongs at the boundary, not inside the workflow

`trade_persistence_workflow.py` validates `is_valid` only. It trusts that the
caller has already checked the event shape. This is deliberate:

- The workflow is called from multiple places in tests and can be called from
  other orchestration layers later.
- Putting exhaustive input validation inside the workflow would couple it to
  the Lambda event shape.
- Putting it at the handler boundary means the workflow only runs when the
  input is already known-good.

The pattern is: **validate at the edge, trust inside**.

## What this module does not own

- It does not construct or test S3 artifact shapes — that is `trade_result_persistence`.
- It does not construct or test DynamoDB record shapes — that is `trade_status_persistence`.
- It does not define retry or catch behaviour — that is the Step Functions definition.

## SAP-C02 relevance

| SAP-C02 area | Relevance |
|---|---|
| Reliable architectures | Boundary validation prevents malformed input from reaching AWS APIs, reducing the surface area for partial-failure states. |
| Operational excellence | Structured logging with `trade_id` context makes failures observable and debuggable. Re-raising instead of swallowing keeps the failure signal visible to Step Functions. |
| Secure architectures | Environment variable validation at cold-start ensures the Lambda never runs without its required configuration, preventing silent permission errors or writes to unintended buckets. |

## Acronym legend

| Acronym | Meaning |
|---|---|
| AWS | Amazon Web Services |
| DynamoDB | Amazon DynamoDB |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam |
| SDK | Software Development Kit |
