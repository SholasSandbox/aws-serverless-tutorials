Related notes:

- `docs/iam/persistence-handler-iam-checklist.md`
- `docs/lessons/lesson-31-retry-safety-and-reconciliation.md`

# Lesson 32: S3 Key Design, Partitioning, Overwrite Behaviour, and Encryption Assumptions

## Purpose

This note explains the S3 object-key design used by the current persistence
workflow and the operational consequences of that design.

It is tutorial evidence only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note.
- Do not introduce new services.
- Use the current Python code and tests as the source of truth.
- Keep S3 design decisions tied to observed persistence behaviour, not broad
  future possibilities.

## Lesson spine

| Lesson | What it established | Why it matters here |
|---|---|---|
| 28 | The persistence pieces were connected into one workflow shape. Accepted/rejected trade result artifacts are written to S3, and status records are written to DynamoDB. | S3 is now part of the persistence boundary, not just a return value. |
| 29 | S3 can succeed, then DynamoDB can fail afterward. | S3 key design affects whether a retry creates duplicates or safely rewrites the same artifact. |
| 30 | Least-privilege IAM was documented. Lambda owns S3/DynamoDB/log permissions; Step Functions owns Lambda invocation. | S3 key prefixes should drive IAM resource scoping. |
| 31 | Retry-safe persistence and reconciliation behaviour were documented. | Retry safety depends on deterministic keys, acceptable overwrite behaviour, and explicit reconciliation when ambiguity remains. |

## Current workflow boundary

```text
Step Functions
  -> persistence Lambda
      -> build accepted/rejected trade result artifact
      -> build S3 object key
      -> put artifact to S3
      -> build DynamoDB status record
      -> put status record to DynamoDB
```

Known current responsibilities:

| Responsibility | Current function |
|---|---|
| Build S3 object key | `build_s3_key` |
| Build accepted trade artifact | `build_accepted_trade_artifact` |
| Build rejected trade artifact | `build_rejected_trade_artifact` |
| Write DynamoDB status record | `persist_trade_status_record` |
| Combined S3 + DynamoDB workflow | `persist_trade_processing_result` |

## Current S3 key boundary

The confirmed prefix boundary from the current IAM checklist is:

```text
trade-results/accepted/*
trade-results/rejected/*
```

That is the important design boundary for Lesson 32.

The exact suffix under each prefix should remain owned by `build_s3_key`. Do not
hardcode a separate object-key rule in documentation, IAM, tests, or future
Terraform unless it is checked against the actual function.

A concise illustrative key shape is:

```text
trade-results/{status}/{processed_date}/{trade_id}.json
```

Example:

```text
trade-results/accepted/2026-06-27/TRD-12345.json
trade-results/rejected/2026-06-27/TRD-12345.json
```

This is illustrative. The repository's `build_s3_key` implementation remains the
source of truth.

## Why accepted and rejected artifacts are separated by prefix

Accepted and rejected trade results should not be mixed under the same S3 prefix.
Separate prefixes support:

| Benefit | Why it matters |
|---|---|
| Clear retrieval | Operators and later jobs can inspect accepted and rejected artifacts separately. |
| Least-privilege IAM | The Lambda can be scoped to only the prefixes it writes. |
| Safer future lifecycle policy | Accepted and rejected artifacts may later have different retention rules. |
| Cleaner analytics path | A later Glue/Athena-style workflow can treat status as a partition-like path component. |
| Easier reconciliation | Partial-persistence investigation starts from a predictable prefix. |

Do not overstate this as a full data lake partitioning strategy. In this
tutorial, the accepted/rejected split is a practical persistence boundary.

## Deterministic key rule

A deterministic S3 key means the same logical trade result produces the same S3
object key across retries.

For the current workflow, this matters because Lesson 29 proved a partial
failure is possible:

```text
S3 PutObject succeeds
DynamoDB PutItem fails
Step Functions sees failure
Step Functions may retry the persistence Lambda
```

If the retry produces the same key, the second `PutObject` writes to the same
object path. If the retry produces a different key, the workflow may create
multiple S3 artifacts for one logical trade result.

## What makes a key retry-safe

Use stable values from the workflow input or from already-validated trade data.

Good key ingredients:

```text
status
trade_id
processed_at supplied by the upstream workflow
processed_date derived from that stable processed_at
```

Risky key ingredients:

```text
datetime.now() generated inside the persistence Lambda
random UUID generated during each retry
attempt number
Lambda request ID
unvalidated free-text status values
```

The issue is not timestamps or UUIDs by themselves. The issue is whether the
value is stable for the same logical workflow attempt.

## Concise code direction

Good direction: derive the key from stable event fields.

```python
def build_s3_key(*, status: str, trade_id: str, processed_at: str) -> str:
    processed_date = processed_at[:10]
    return f"trade-results/{status}/{processed_date}/{trade_id}.json"
```

Bad direction: generate retry-sensitive key material inside the persistence
handler.

```python
# Risky: a retry can generate a different key for the same trade result.
processed_at = datetime.now(timezone.utc).isoformat()
key = build_s3_key(status=status, trade_id=trade_id, processed_at=processed_at)
```

If `processed_at` is part of the key, it should be supplied by the upstream
workflow event and remain stable during retries.

## Overwrite behaviour

For this tutorial workflow, overwriting the same S3 key during a retry can be
acceptable only when the artifact body is deterministic for the same input.

That means:

```text
same input
+ same validation result
+ same processed_at
= same S3 key and same artifact body
```

If the artifact body changes between retries, overwriting becomes risky because
S3 no longer represents a stable persistence artifact.

## Decision table

| Design choice | Retry consequence | Recommendation |
|---|---|---|
| Deterministic key using stable `trade_id`, `status`, and workflow-supplied `processed_at` | Retry writes the same logical object path. | Preferred for this tutorial. |
| Key includes `datetime.now()` inside the Lambda | Retry can create a new object path. | Avoid. It breaks retry reasoning. |
| Key includes a random UUID generated during each invocation | Retry creates duplicate artifacts for one logical result. | Avoid unless the workflow deliberately tracks every attempt. |
| Accepted/rejected split by prefix | IAM can scope writes to `trade-results/accepted/*` and `trade-results/rejected/*`. | Keep. It supports least privilege and reviewability. |
| Single broad `trade-results/*` prefix for all statuses | Simpler, but less precise for IAM and future operations. | Avoid unless there is a clear reason. |
| Retry overwrites same key with identical artifact body | Usually safe for this tutorial. | Acceptable if tests prove deterministic artifact output. |
| Retry overwrites same key with changed artifact body | Ambiguous audit history. | Treat as a design flaw or route to reconciliation. |
| Add `s3:DeleteObject` for cleanup after DynamoDB failure | Creates broader permissions and a new failure path. | Do not add unless compensation is designed and tested. |

## IAM scoping implication

The S3 key design should drive the Lambda execution role's S3 resource scope.

Good scope:

```json
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": [
    "arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/accepted/*",
    "arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/rejected/*"
  ]
}
```

Avoid:

```json
{
  "Effect": "Allow",
  "Action": "s3:*",
  "Resource": "*"
}
```

Also avoid widening the Lambda role to the full bucket unless the code genuinely
writes outside the accepted/rejected prefixes.

## Encryption assumptions

For this tutorial, assume S3 server-side encryption is handled by the bucket's
default encryption configuration.

Current tutorial assumption:

```text
No encryption parameters are required in the persistence handler's PutObject call.
No KMS permissions are added to the Lambda role by default.
```

This keeps the handler focused on persistence behaviour rather than bucket
configuration.

### When AWS-managed encryption is enough for this tutorial

AWS-managed S3 encryption is enough for the local tutorial design note when:

- the exercise is not deploying live infrastructure,
- the artifact is not crossing accounts,
- there is no explicit customer-managed KMS key requirement,
- the code is only demonstrating S3 `PutObject` behaviour,
- encryption is discussed as an assumption to verify before deployment.

### When customer-managed KMS needs explicit design

Customer-managed KMS keys need explicit design when a later deployment requires:

- a named customer-managed key,
- cross-account access,
- stricter key rotation or key administration controls,
- audit separation between S3 bucket administration and key administration,
- explicit deny/allow rules around which roles may encrypt or decrypt artifacts,
- object reads by separate consumers that need `kms:Decrypt`.

If the persistence Lambda writes objects using SSE-KMS with a customer-managed
key, the Lambda role may need KMS permissions such as `kms:GenerateDataKey` for
object writes. Do not add these permissions until the bucket/key design is
explicit and tested.

## What the handler should not do yet

The persistence handler should not be responsible for:

- creating the S3 bucket,
- changing bucket policies,
- changing default encryption configuration,
- setting object ACLs,
- managing lifecycle rules,
- writing to arbitrary prefixes,
- writing across accounts,
- deleting S3 artifacts as implicit cleanup,
- listing all buckets,
- scanning S3 prefixes to infer workflow state.

Those are infrastructure, operations, or reconciliation concerns. They are not
part of the current persistence Lambda contract.

## Review checklist before later Terraform

Before turning this design into infrastructure code, confirm:

- exact `build_s3_key` output for accepted artifacts,
- exact `build_s3_key` output for rejected artifacts,
- whether `processed_at` is supplied by the workflow input and stable across retries,
- whether repeated `PutObject` produces the same artifact body for the same input,
- whether S3 object versioning is enabled or disabled,
- whether default bucket encryption uses SSE-S3, AWS-managed SSE-KMS, or a customer-managed KMS key,
- whether any downstream reader needs `s3:GetObject` or `kms:Decrypt`,
- whether the Lambda role can remain scoped to accepted/rejected prefixes only,
- whether reconciliation requires read access later, or whether that belongs in a separate role/function.

## SAP-C02 relevance

This lesson maps to SAP-C02 because it connects storage design, retry safety,
security boundaries, and operational consequences.

| SAP-C02 area | Relevance |
|---|---|
| Secure architectures | Prefix-scoped S3 permissions, no bucket-wide `s3:*`, clear KMS boundary. |
| Reliable architectures | Deterministic keys reduce duplicate artifacts during retry. |
| Operational excellence | Predictable prefixes simplify troubleshooting and reconciliation. |
| Cost and complexity control | Avoids premature KMS, lifecycle, cross-account, and Terraform expansion. |
| Migration/improvement thinking | Converts observed handler behaviour into deployable design assumptions later. |

## Bottom line

The current persistence workflow should keep S3 key design simple and stable:

```text
trade-results/accepted/...
trade-results/rejected/...
```

The exact suffix should be determined by `build_s3_key`, but it must be stable
for the same logical trade result.

Do not fix retry uncertainty by granting broad S3 permissions or adding cleanup
deletes. Fix retry uncertainty by using deterministic keys, deterministic artifact
content, explicit DynamoDB idempotency rules, and Step Functions failure routing.

## Acronym legend

| Acronym | Meaning |
|---|---|
| ACL | Access Control List |
| ARN | Amazon Resource Name |
| AWS | Amazon Web Services |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| KMS | Key Management Service |
| Lambda | AWS Lambda |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam |
| SSE-KMS | Server-Side Encryption with AWS Key Management Service keys |
| SSE-S3 | Server-Side Encryption with Amazon S3 managed keys |
