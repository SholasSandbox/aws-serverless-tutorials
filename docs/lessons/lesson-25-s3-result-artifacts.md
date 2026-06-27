# Lesson 25: S3 Trade Result Artifacts

## Purpose

This note records what Lesson 25 established about building and writing S3
result artifacts for accepted and rejected trades.

It is tutorial evidence only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note.
- Use the current Python code and tests as the source of truth.

## What this lesson established

Before Lesson 25, trade validation results were returned as Lambda response
bodies only. They were not stored anywhere. This lesson introduced the first
persistence layer: a structured JSON artifact written to S3 for every trade
result, accepted or rejected.

## Module: `trade_result_persistence.py`

This module owns all artifact construction and S3 writing logic. It has no
knowledge of DynamoDB. It has no knowledge of the Lambda boundary.

### Key functions

| Function | Responsibility |
|---|---|
| `build_accepted_trade_artifact` | Build a structured dict for an accepted trade, with schema version, status, and full trade/validation payloads |
| `build_rejected_trade_artifact` | Same shape as accepted, with an additional `rejection_reasons` list extracted from `validation.errors` |
| `build_s3_key` | Build a deterministic, partition-friendly S3 object key from `result_type`, `trade_id`, and `processed_at` |
| `put_json_object_to_s3` | Write a dict to S3 as JSON with `ContentType: application/json` |
| `safe_s3_key_part` | Sanitise a string for safe use inside an S3 key path |

### Artifact shape

Both accepted and rejected artifacts share a common envelope:

```python
{
    "artifact_type": "accepted_trade",   # or "rejected_trade"
    "schema_version": "1.0",
    "status": "ACCEPTED",                # or "REJECTED"
    "trade_id": "TRD-001",
    "processed_at": "2026-06-02T18:30:00Z",
    "trade": { ... },
    "validation": { ... },
    # rejected only:
    "rejection_reasons": ["volume_mwh must be greater than 0"],
}
```

The `schema_version` field exists so that downstream consumers can handle
future shape changes without breaking.

### S3 key design

```text
trade-results/{result_type}/year={YYYY}/month={MM}/day={DD}/trade_id={id}.json
```

Example:

```text
trade-results/accepted/year=2026/month=06/day=02/trade_id=TRD-001.json
```

The Hive-style partition segments (`year=`, `month=`, `day=`) make the prefix
compatible with AWS Athena partition projection and S3 inventory analysis
without additional tooling.

### Why the key is deterministic

The key is derived entirely from inputs that must already be stable before
persistence is called:

- `result_type` — derived from `validation.is_valid`
- `trade_id` — from the trade payload
- `processed_at` — passed in as a parameter, not generated inside the function

This is a deliberate design choice. It means retrying the same workflow
execution writes to the same key, not a new one. This property is proved in
`test_s3_result_key_is_deterministic_for_same_trade_result`.

### trade_id sanitisation

`build_s3_key` passes `trade_id` through `safe_s3_key_part` before embedding
it in the key. This function replaces any character that is not alphanumeric,
`.`, `_`, `=`, or `-` with a hyphen, and truncates to 120 characters.

This prevents S3 key injection from unexpected `trade_id` values.

Test:

```python
def test_build_s3_key_sanitises_trade_id():
    key = build_s3_key(
        result_type="accepted",
        trade_id="TRD 001 / bad",
        processed_at="2026-06-02T18:30:00Z",
    )
    assert "trade_id=TRD-001-bad.json" in key
```

### Unsupported result type guard

`build_s3_key` raises `ValueError` for any `result_type` that is not
`"accepted"` or `"rejected"`. This prevents silent key construction for
unknown trade outcomes.

## Dependency injection pattern

`put_json_object_to_s3` takes an `s3_client` argument. The real boto3 client
is never imported or created inside this module. This means every test can
pass a `Mock()` in place of the real client and assert on the exact call made.

```python
def test_put_json_object_to_s3_calls_put_object_with_expected_arguments():
    s3_client = Mock()
    put_json_object_to_s3(
        s3_client=s3_client,
        bucket_name="test-bucket",
        object_key="trade-results/accepted/.../trade_id=TRD-001.json",
        body={ ... },
    )
    s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="trade-results/accepted/.../trade_id=TRD-001.json",
        Body=json.dumps(body),
        ContentType="application/json",
    )
```

This is the standard pattern used across all persistence modules in this
tutorial.

## Tests established

| Test | What it proves |
|---|---|
| `test_build_accepted_trade_artifact_returns_expected_shape` | Full artifact envelope for accepted trade |
| `test_build_rejected_trade_artifact_returns_expected_shape` | Full artifact envelope for rejected trade, including `rejection_reasons` |
| `test_build_s3_key_for_accepted_trade` | Exact key format for accepted result |
| `test_build_s3_key_for_rejected_trade` | Exact key format for rejected result |
| `test_build_s3_key_rejects_unsupported_result_type` | Guard against unknown result types |
| `test_build_s3_key_allows_custom_base_prefix` | `base_prefix` override works |
| `test_build_s3_key_sanitises_trade_id` | Unsafe characters replaced in key |
| `test_put_json_object_to_s3_calls_put_object_with_expected_arguments` | Correct boto3 call shape |
| `test_s3_result_key_is_deterministic_for_same_trade_result` | Same inputs always produce the same key |

## What this module does not own

- It does not create or manage the S3 bucket.
- It does not set bucket policies, encryption, or versioning.
- It does not write to DynamoDB.
- It does not validate the trade or decide whether a trade is accepted or
  rejected. That decision is passed in as `validation.is_valid`.

## SAP-C02 relevance

| SAP-C02 area | Relevance |
|---|---|
| Storage selection | S3 is appropriate for large, schema-versioned result artifacts that need audit retention and potential downstream query via Athena. |
| Reliable architectures | Deterministic keys are the foundation of retry safety. A retry that writes to a different key creates duplicate artifacts. |
| Operational excellence | Hive-style partitions make the data queryable and observable without extra tooling. Schema version enables forward compatibility. |

## Acronym legend

| Acronym | Meaning |
|---|---|
| AWS | Amazon Web Services |
| JSON | JavaScript Object Notation |
| Lambda | AWS Lambda |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam |
