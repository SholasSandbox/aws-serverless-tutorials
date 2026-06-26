# Lesson 29: Persistence failure ordering

This note supports the active persistence reasoning objective in
`LEARNING-PLAN.md` by making the S3-then-DynamoDB failure boundary explicit for
local Step Functions and workflow design review.

| Failure point | System state | Retry behaviour | Reconciliation concern |
|---|---|---|---|
| S3 write fails | no artifact, no status | safe retry | low |
| S3 succeeds, DynamoDB fails | artifact exists, status missing | retry writes same S3 key | orphaned artifact possible |
| Retry succeeds | artifact + status exist | complete | no action |
| Repeated DynamoDB failure | artifact may exist, status missing | Step Functions catch/manual review | manual reconciliation needed |

This is Python/serverless tutorial evidence only. It is a candidate pattern for
later adaptation elsewhere, not Energy Data Lakehouse implementation evidence.
