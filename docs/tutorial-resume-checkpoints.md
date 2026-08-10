# Tutorial Resume and Implementation Checkpoints

Last reviewed: 2026-08-10

## Purpose

Preserve the justified Python/serverless implementation backlog without
allowing it to displace the active SAP-C02 validation programme. This is a
tutorial planning artifact, not Energy Data Lakehouse implementation evidence
and not authorization to deploy AWS resources.

`LEARNING-PLAN.md` controls lesson order in this workspace. During the current
certification programme, the separate Energy Data Lakehouse SAP-C02 readiness
tracker controls the active study cadence.

## Current Decision

- Maintain two independent, timed 75-question mocks per week through the
  four-week validation series.
- Complete review, wrong-answer reconstruction, and spaced remediation for each
  mock before treating its score as readiness evidence.
- Do not reduce the mock cadence to create implementation time.
- Tutorial implementation may use only genuine spare capacity after the mocks,
  their reviews, and the current DR, migration, and cost priorities are met.
- Containers and new AI orchestration remain parked until after the SAP-C02
  attempt.

## Evidence Baseline

| Area | Current evidence | Boundary |
| --- | --- | --- |
| boto3 construction | S3 client and DynamoDB resource construction are locally tested | Current construction occurs on every handler invocation |
| S3 SDK call | Mocked `PutObject` parameters are tested | No live object write in this tutorial |
| DynamoDB SDK call | Conditional `PutItem` parameters are tested | The real workflow does not wire the conditional-check exception into duplicate-as-success handling |
| Step Functions | ASL contracts plus a local, injected `start_execution` adapter are tested | No architecture selection, deployed integration, or live execution |
| IAM | Least-privilege checklist and illustrative policies exist | No tutorial role has been deployed or denial-tested |
| Observability | Logging and correlation concepts are locally represented | No tutorial CloudWatch logs, execution history, metric, or alarm evidence |

## Checkpoint A: After Full Mock 005

Trigger: the baseline mock plus four additional independent full mocks have been
completed and reviewed.

Review:

- at least three of Mocks 002-005 score 80% or higher overall;
- no individual domain score is below 75% in any of Mocks 002-005;
- multiple-response performance is at least 80% in each of at least three of
  Mocks 002-005;
- no unresolved misconception repeats across the mocks; and
- the next two mocks, their reviews, and required remediation remain fully
  scheduled within the weekly capacity.

If a mock source does not provide a credible domain or response-type breakdown,
record that evidence as unavailable rather than inferring a passing threshold.
The affected checkpoint condition remains unmet until equivalent independent
evidence is available.

If all conditions hold, one bounded local correctness repair may be scheduled
only from genuine spare capacity. It must not replace either weekly mock. The
first eligible repair is the existing DynamoDB conditional-check exception
wiring and its realistic tests. If any condition fails, continue targeted
remediation and leave implementation parked.

## Checkpoint B: After Full Mock 009

Trigger: the planned eight additional mocks are complete and their evidence has
been reconciled.

If score stability and domain floors meet the readiness thresholds, complete
the following remaining items in order, skipping any item already completed and
evidenced under Checkpoint A:

1. wire and test realistic DynamoDB conditional-check classification through
   the actual workflow;
2. introduce reusable or lazily cached SDK-client construction while retaining
   dependency injection;
3. add deliberate Botocore retry and timeout configuration where justified;
4. add `Stubber`-backed request-parameter, success, and modeled service-error
   tests, then add separately injected Botocore transport-exception and
   unexpected-exception tests; and
5. rerun the full local test suite and update tutorial evidence.

This remains local-only. It does not authorize deployment and should not delay
the formal 2026-09-07 readiness and booking review.

## Checkpoint C: After the SAP-C02 Attempt

The local `api_workflow_handoff.py` teaching adapter does not satisfy this
checkpoint or preselect the deployed architecture. It provides mocked Python
boundary evidence only; the direct-integration versus Lambda-mediated decision
still requires the analysis below.

First produce a bounded architecture decision between these two paths:

```text
API Gateway
    -> direct Step Functions StartExecution integration

or

API Gateway
    -> API-facing Lambda
        -> boto3 start_execution

selected path
    -> Standard Step Functions workflow
        -> controlled success or explicit Fail path
```

Required design points:

- select one path from its validation, transformation, identity propagation,
  idempotency, response-mapping, operational, and cost requirements;
- introduce an API-facing Lambda only when those requirements justify it over
  the direct service integration;
- keep `correlation_id`, business `idempotency_key`, and Step Functions
  execution name separate;
- document Standard versus Express workflow semantics and the Standard
  execution-name reuse window;
- return `202 Accepted` only after the selected asynchronous handoff succeeds;
- if the Lambda path wins, keep HTTP translation out of the internal workflow
  adapter; and
- test duplicate, throttling or service, permission, connection, and unexpected
  failures without leaking AWS error details to an external caller.

## Checkpoint D: Separately Approved Live Lab

Only after an explicit user-approved plan defines cost, IAM, rollback, cleanup,
and success criteria:

1. choose one Infrastructure-as-Code tool;
2. deploy one minimal API-to-Standard-Workflow path;
3. scope permissions for the selected path: use an API Gateway integration role
   for direct `StartExecution`, or use a scoped API Gateway-to-Lambda invoke
   permission plus a Lambda execution role for the Lambda path; in both cases,
   scope the Step Functions execution role to its intended task resources;
4. verify correlation in logs and workflow execution history;
5. route a controlled input to an explicit `Fail` state;
6. verify one useful failure metric or alarm;
7. capture sanitized evidence; and
8. destroy the stack and verify cleanup.

The evidence label for that result is `Controlled live vertical slice
verified`, not general production readiness.

## Parked Beyond the Live Slice

- Lambda versus ECS Fargate implementation lab
- container packaging and ECR
- Step Functions integration with an ECS task
- controlled Bedrock or OpenAI orchestration
- AI output validation and human-review routing
- Glue-style analytics extensions not already covered by the separate Energy
  Data Lakehouse case study

These items require a post-exam priority decision. Their presence here does not
make them active.

## Official References for the Future Slice

- AWS Lambda execution-environment and SDK-client reuse guidance:
  <https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html>
- Boto3 retry modes and attempt-count semantics:
  <https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html>
- Botocore Stubber request, response, and service-error validation:
  <https://botocore.amazonaws.com/v1/documentation/api/latest/reference/stubber.html>
- API Gateway direct integration with Step Functions:
  <https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-api-gateway.html>
- Step Functions `StartExecution` idempotency and execution-name rules:
  <https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html>
