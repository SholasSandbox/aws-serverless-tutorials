# Lesson 30: Least-Privilege IAM Checklist for the Persistence Workflow

## Purpose

This note maps the current persistence workflow behaviour to the minimum AWS Identity and Access Management (IAM) permissions it should need.

This is a tutorial design note only:

- Do not deploy AWS resources from this note.
- Do not write Terraform from this note yet.
- Do not introduce new services.
- Use the current Python code and tests as the source of truth.
- Keep permissions tied to observed handler behaviour, not broad future possibilities.

## Current workflow boundary

The current persistence path is:

```text
Step Functions
  -> persistence Lambda
      -> write accepted/rejected trade result artifact to S3
      -> write trade status record to DynamoDB
```

Known tutorial functions and responsibilities:

| Responsibility | Current function |
|---|---|
| Build S3 object key | `build_s3_key` |
| Build accepted trade artifact | `build_accepted_trade_artifact` |
| Build rejected trade artifact | `build_rejected_trade_artifact` |
| Write DynamoDB status record | `persist_trade_status_record` |
| Combined S3 + DynamoDB persistence workflow | `persist_trade_processing_result` |

## AWS calls made by the persistence handler

| Code behaviour | Likely AWS SDK call | Required IAM action | Resource scope |
|---|---|---|---|
| Write accepted/rejected JSON artifact to S3 | `s3.put_object(...)` | `s3:PutObject` | Only the configured result bucket and result prefix used by `build_s3_key` |
| Write processing status record to DynamoDB | `dynamodb.put_item(...)` or `table.put_item(...)` | `dynamodb:PutItem` | Only the configured trade status table |
| Emit Lambda logs | Lambda runtime / logging | `logs:CreateLogStream`, `logs:PutLogEvents` | Only the persistence Lambda log group |
| First-time log group creation, if not pre-created | Lambda runtime | `logs:CreateLogGroup` | Only needed if the log group is not created ahead of time |

## Lambda execution role checklist

The persistence Lambda execution role should allow only what the Lambda itself does.

### Required

- `s3:PutObject` for the trade result artifact bucket/prefix.
- `dynamodb:PutItem` for the trade status table.
- CloudWatch Logs write permissions for the Lambda log group.

### Conditional / only if the code or configuration uses it

| Permission | Only needed when |
|---|---|
| `s3:PutObjectTagging` | The code writes S3 object tags |
| `s3:PutObjectAcl` | The code sets an object Access Control List (ACL); avoid this unless there is a strong reason |
| `dynamodb:ConditionCheckItem` | Not normally required for `PutItem` with `ConditionExpression`; `dynamodb:PutItem` is still the action |
| `dynamodb:UpdateItem` | Only if the code changes from full status insert to status update |
| `dynamodb:GetItem` | Only if the code reads before writing; not needed for blind `PutItem` |

### Encryption-related caution

Treat S3 artifact encryption and DynamoDB table encryption as separate IAM
questions.

- S3 with customer-managed KMS keys: only consider extra KMS permissions for the
  Lambda role if the artifact write path is explicitly configured to use
  customer-managed SSE-KMS. Verify the exact required KMS actions against the
  final bucket/key design before adding anything.
- DynamoDB table encryption: do not assume the Lambda role needs extra KMS
  permissions just because the table is encrypted with a customer-managed key.
  For this tutorial's blind `PutItem` path, `dynamodb:PutItem` remains the
  observed application permission boundary unless a later verified design adds
  direct KMS API use.

### Should not have

Do not give the persistence Lambda broad permissions such as:

- `s3:*`
- `s3:ListAllMyBuckets`
- `s3:CreateBucket`
- `s3:DeleteObject`
- `s3:PutBucketPolicy`
- `dynamodb:*`
- `dynamodb:Scan`
- `dynamodb:Query`
- `dynamodb:DeleteItem`
- `dynamodb:UpdateTable`
- `lambda:InvokeFunction`
- `states:StartExecution`
- `iam:PassRole`

The Lambda persists results. It does not orchestrate the state machine, create infrastructure, list buckets, scan tables, or invoke other compute.

## Step Functions execution role checklist

The Step Functions role is separate from the Lambda execution role.

### Required

The Step Functions execution role should allow:

- `lambda:InvokeFunction` on the persistence Lambda function ARN.

### Should not have

The Step Functions role should not have S3 or DynamoDB write permissions unless the Amazon States Language (ASL) definition calls S3 or DynamoDB directly through service integrations.

For the current workflow, Step Functions invokes Lambda. Lambda writes to S3 and DynamoDB. Therefore:

```text
Step Functions role
  -> lambda:InvokeFunction only

Lambda execution role
  -> s3:PutObject
  -> dynamodb:PutItem
  -> logs write permissions
```

Do not fix a Lambda permission issue by adding S3 or DynamoDB permissions to the Step Functions role. That would be the wrong role boundary.

## Resource scoping assumptions

Replace these placeholders with the actual deployed names later:

| Placeholder | Meaning |
|---|---|
| `${AWS_REGION}` | AWS Region, for example `eu-west-2` |
| `${AWS_ACCOUNT_ID}` | Owning AWS account ID |
| `${TRADE_RESULTS_BUCKET}` | S3 bucket used for accepted/rejected trade result artifacts |
| `${RESULTS_PREFIX}` | Base prefix used by `build_s3_key` |
| `${TRADE_STATUS_TABLE}` | DynamoDB table used for trade status records |
| `${PERSISTENCE_FUNCTION_NAME}` | Persistence Lambda function name |
| `${PERSISTENCE_FUNCTION_ALIAS}` | Optional Lambda alias such as `dev`, `test`, or `prod` |

Recommended scoping:

| Resource | Least-privilege scope |
|---|---|
| S3 accepted artifacts | `arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/accepted/*` |
| S3 rejected artifacts | `arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/rejected/*` |
| DynamoDB table | `arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT_ID}:table/${TRADE_STATUS_TABLE}` |
| Lambda invocation | Persistence function ARN, preferably alias-scoped for controlled deployments |
| Logs | `/aws/lambda/${PERSISTENCE_FUNCTION_NAME}` log group only |

These S3 scopes match the current `build_s3_key` behavior, which writes only to
`trade-results/accepted/...` or `trade-results/rejected/...`. If the code later
changes the base prefix, update the IAM resources from the code rather than
widening access to the whole bucket.

## Lesson 29 failure-ordering implication

Lesson 29 proved the important failure boundary: S3 can succeed and DynamoDB can fail afterward.

IAM does not solve that consistency issue. Do not add broad permissions such as `s3:DeleteObject` so the handler can "clean up" unless you deliberately design and test compensation logic.

The better design controls are:

- deterministic S3 object keys,
- idempotent retry behaviour,
- conditional DynamoDB writes where appropriate,
- Step Functions `Retry` and `Catch` paths,
- explicit reconciliation/manual-review path for ambiguous partial persistence.

## Illustrative policy skeleton — not deployment-ready

This example shows role separation. It is intentionally incomplete and uses placeholders.
It also assumes the Lambda log group is pre-created, so the sample policy does
not include `logs:CreateLogGroup`.

```json
{
  "lambdaExecutionRolePolicy": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "WriteTradeResultArtifacts",
        "Effect": "Allow",
        "Action": "s3:PutObject",
        "Resource": [
          "arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/accepted/*",
          "arn:aws:s3:::${TRADE_RESULTS_BUCKET}/trade-results/rejected/*"
        ]
      },
      {
        "Sid": "WriteTradeStatusRecords",
        "Effect": "Allow",
        "Action": "dynamodb:PutItem",
        "Resource": "arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT_ID}:table/${TRADE_STATUS_TABLE}"
      },
      {
        "Sid": "WritePersistenceLambdaLogs",
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/lambda/${PERSISTENCE_FUNCTION_NAME}:*"
      }
    ]
  },
  "stepFunctionsExecutionRolePolicy": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "InvokePersistenceLambdaOnly",
        "Effect": "Allow",
        "Action": "lambda:InvokeFunction",
        "Resource": [
          "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${PERSISTENCE_FUNCTION_NAME}",
          "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${PERSISTENCE_FUNCTION_NAME}:${PERSISTENCE_FUNCTION_ALIAS}"
        ]
      }
    ]
  }
}
```

## Review checklist before later Terraform

Before turning this into infrastructure code, confirm:

- Exact S3 bucket name and prefix shape from `build_s3_key`.
- Exact DynamoDB table name and key schema.
- Whether DynamoDB writes use `ConditionExpression`.
- Whether S3 uses AWS-managed encryption or customer-managed KMS keys.
- Whether the Lambda log group is pre-created.
- Whether Step Functions invokes an unqualified function ARN, version, or alias.
- Whether the ASL definition directly calls only Lambda, not S3 or DynamoDB.
- Whether retry behaviour can safely repeat the S3 write after a DynamoDB failure.

## SAP-C02 relevance

This lesson maps to SAP-C02 because it tests whether you can separate permissions by service responsibility instead of granting broad access.

| SAP-C02 area | Relevance |
|---|---|
| Secure architectures | Least-privilege IAM, scoped resources, service role separation |
| Reliable architectures | Retry/Catch behaviour and partial-failure awareness |
| Cost and operations | Avoid unnecessary service permissions and accidental destructive access |
| Migration/improvement thinking | Convert observed application behaviour into controlled cloud permissions |

## Acronym legend

| Acronym | Meaning |
|---|---|
| ACL | Access Control List |
| ARN | Amazon Resource Name |
| ASL | Amazon States Language |
| AWS | Amazon Web Services |
| IAM | Identity and Access Management |
| JSON | JavaScript Object Notation |
| KMS | Key Management Service |
| Lambda | AWS Lambda |
| S3 | Amazon Simple Storage Service |
| SAP-C02 | AWS Certified Solutions Architect - Professional exam |
