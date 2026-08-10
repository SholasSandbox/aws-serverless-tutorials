# Lesson 29: Persistence Failure Ordering

Last reviewed: 2026-07-26

This note supports the active persistence reasoning objective in
`LEARNING-PLAN.md` by making the S3-then-DynamoDB failure boundary explicit for
local Step Functions and workflow design review.

| Failure point | System state | Retry behaviour | Reconciliation concern |
|---|---|---|---|
| S3 `PutObject` raises or returns no success response | Artifact absent or completion ambiguous; no status | Retry only with a deterministic key and body | Distinguish a definite validation/authorization failure from a timeout or lost response; do not infer absence from every client exception. |
| S3 succeeds, DynamoDB fails | Artifact exists; status missing | Retry writes the same S3 key | Orphaned artifact possible; versioning may create another version on retry. |
| Retry succeeds | Artifact and status exist | Processing can complete | Confirm the final status and account for any noncurrent S3 versions. |
| Repeated DynamoDB failure | Artifact may exist; status missing | Step Functions catches supported failures and marks reconciliation required | Manual or automated reconciliation still needs a separately implemented owner and action. |

This is Python/serverless tutorial evidence only. It is a candidate pattern for
later adaptation elsewhere, not Energy Data Lakehouse implementation evidence.
