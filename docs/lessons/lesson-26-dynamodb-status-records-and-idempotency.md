# Lesson 26: DynamoDB Status Records and Idempotency

## Purpose

This note records what Lesson 26 established about writing trade status records
to DynamoDB and protecting against duplicate writes with a conditional
expression.

It is tutorial evidence only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note.
- Use the current Python code and tests as the source of truth.

## What this lesson established

Lesson 25 wrote trade result artifacts to S3 only. This lesson added the
second persistence target: a DynamoDB item that records the trade status,
the S3 pointer, and enough metadata to reconstruct the persistence outcome
without re-reading the S3 object.

It also introduced the first idempotency protection in the workflow: a
DynamoDB `ConditionExpression` that prevents overwriting an existing record.

## Module: `trade_status_persistence.py`

This module owns DynamoDB status record construction and writing. It imports
constants from `trade_result_persistence` but does not import or call any
S3 functions.

### Key functions

| Function | Responsibility |
|---|---|
| `build_trade_status_record` | Build a flat DynamoDB item dict from explicit fields |
| `build_trade_status_record_from_artifact` | Derive a status record from an S3 artifact dict and an S3 pointer |
| `persist_trade_status_record` | Write a status record to DynamoDB with a conditional expression |
| `find_missing_required_field` | Return the first missing field name from a dict, or `None` |
| `get_result_type_from_artifact_type` | Map `artifact_type` constant to `result_type` string |
| `get_artifact_is_valid` | Extract and type-check `validation.is_valid` from an artifact |
| `validate_artifact_consistency` | Assert that `result_type`, `status`, and `is_valid` are internally consistent |

### Status record shape

```python
{
    "trade_id": "TRD-001",
    "processed_at": "2026-06-02T18:30:00Z",
    "status": "ACCEPTED",           # or "REJECTED"
    "result_type": "accepted",      # or "rejected"
    "s3_bucket": "test-results-bucket",
    "s3_key": "trade-results/accepted/year=2026/.../trade_id=TRD-001.json",
    "rejection_summary": None,      # first rejection reason, or None for accepted
    "schema_version": "1.0",
}
```

`trade_id` is the DynamoDB partition key. All other fields are attributes.

### Conditional write pattern

```python
dynamodb_table.put_item(
    Item=status_record,
    ConditionExpression="attribute_not_exists(trade_id)",
)
```

This succeeds only when no item with the same `trade_id` exists. If a record
already exists, DynamoDB raises `ConditionalCheckFailedException`.

### Idempotency classification

`persist_trade_status_record` accepts an optional
`conditional_check_failed_exception` parameter. When the write raises that
exception type, the function returns an `already_persisted` response instead
of re-raising.

```python
def persist_trade_status_record(
    *,
    dynamodb_table: Any,
    status_record: dict[str, Any],
    conditional_check_failed_exception: type[Exception]
    | tuple[type[Exception], ...] = (),
) -> dict[str, Any]:
```

The default is an empty tuple, meaning no exception is caught by default in
tests that do not inject the exception type. This keeps the interface explicit
and avoids hiding unexpected errors.

Response when a new record is written:

```python
{
    "trade_id": "TRD-001",
    "processed_at": "2026-06-02T18:30:00Z",
    "status": "ACCEPTED",
}
```

Response when the conditional check fails (duplicate treated as idempotent):

```python
{
    "trade_id": "TRD-001",
    "result_type": "ACCEPTED",
    "status": "already_persisted",
}
```

### Important caveat on idempotency

Returning `already_persisted` does not prove that the existing DynamoDB record
matches the attempted write. The function does not read back and compare the
existing item.

This is acceptable for the current tutorial scope, where retries are assumed
to carry the same input. In a production system with stronger guarantees, the
duplicate handler should either verify equivalence or raise a conflict error.
Lesson 31 addresses this in detail.

### Artifact consistency validation

`build_trade_status_record_from_artifact` validates that the artifact's
internal fields are consistent before building a status record.

Rules enforced:

| Rule | Error raised |
|---|---|
| `accepted_trade` artifact must have `status == ACCEPTED` | `ValueError` |
| `rejected_trade` artifact must have `status == REJECTED` | `ValueError` |
| `accepted_trade` artifact must have `validation.is_valid == True` | `ValueError` |
| `rejected_trade` artifact must have `validation.is_valid == False` | `ValueError` |

These checks prevent a corrupted or mismatched artifact from producing a
contradictory status record.

## Tests established

| Test | What it proves |
|---|---|
| `test_build_trade_status_record_for_accepted_trade` | Full status record shape for accepted trade |
| `test_build_trade_status_record_for_rejected_trade` | Full status record shape with `rejection_summary` |
| `test_persist_trade_status_record_calls_dynamodb_put_item` | Correct boto3 call shape with `ConditionExpression` |
| `test_persist_trade_status_record_returns_stable_response` | Response shape after successful write |
| `test_persist_trade_status_uses_conditional_put_for_new_trade_status` | `ConditionExpression` is always passed |
| `test_persist_trade_status_treats_duplicate_trade_status_as_idempotent_success` | Injected `ConditionalCheckFailedException` returns `already_persisted` |
| `test_save_trade_status_does_not_swallow_unexpected_dynamodb_errors` | Unexpected `RuntimeError` is not caught |
| `test_build_trade_status_record_from_accepted_artifact_and_s3_pointer` | Artifact-to-status-record derivation for accepted trade |
| `test_build_trade_status_record_from_rejected_artifact_and_s3_pointer` | Same for rejected trade, including `rejection_summary` |
| `test_build_trade_status_record_from_artifact_rejects_missing_schema_version` | Missing artifact field raises `ValueError` |
| `test_build_trade_status_record_from_artifact_rejects_missing_s3_pointer_field` | Missing `bucket` or `key` raises `ValueError` |
| `test_build_trade_status_record_from_artifact_rejects_accepted_artifact_with_rejected_status` | Status/artifact-type mismatch raises `ValueError` |
| `test_build_trade_status_record_from_artifact_rejects_rejected_artifact_with_valid_validation` | Validation/artifact-type mismatch raises `ValueError` |

## What this module does not own

- It does not create or manage the DynamoDB table.
- It does not set table throughput, TTL, or stream settings.
- It does not write to S3.
- It does not validate the original trade input. It trusts the artifact it
  receives as already constructed correctly.

## Weak area noted

The `conditional_check_failed_exception` parameter requires the caller to
inject the real `botocore.exceptions.ClientError` type in production. If the
caller forgets, duplicate writes will silently raise instead of returning
`already_persisted`. A future exercise could add a production integration test
that injects the real boto3 exception type.

## SAP-C02 relevance

| SAP-C02 area | Relevance |
|---|---|
| Reliable architectures | `ConditionExpression` prevents silent overwrite on retry. The choice between idempotent-success and conflict-error is a deliberate design decision. |
| Storage selection | DynamoDB is appropriate for keyed status lookups with conditional write semantics. S3 is appropriate for the full artifact body. Using both together follows the separation of concerns pattern. |
| Operational excellence | Unexpected errors are not swallowed. The conditional exception is injected, not hardcoded, which keeps the module testable without real AWS. |

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
