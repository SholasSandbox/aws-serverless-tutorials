# Tutorial Workspace Instructions

## Controlling documents

Read `README.md` and `LEARNING-PLAN.md` before changing this workspace. The
learning plan controls lesson order, completion evidence, and parked topics.

## Purpose and boundary

This directory is a guided Python and AWS serverless tutorial. It is separate
from the Energy Data Lakehouse and must not be described as lakehouse
implementation evidence.

The tutorial may support SAP-C02 readiness through focused exercises in
Lambda, EventBridge, SQS, Step Functions, S3, DynamoDB, configuration,
logging, testing, and IAM-aware design. Do not copy tutorial code into the
lakehouse by default.

## Required task start

Before implementing a change:

1. Identify the active lesson or learning objective in `LEARNING-PLAN.md`.
2. State the Python/serverless skill and SAP-C02 concept it supports.
3. Keep the exercise small enough to explain and test locally.
4. Defer unrelated refactoring, container work, UI work, and AI orchestration.

## Teaching behavior

- Preserve the tutorial nature of the workspace. Explain important choices
  and avoid replacing a learning step with an unexplained large rewrite.
- Prefer standard Python, explicit functions, dependency injection, and small
  testable units.
- Use environment variables for runtime configuration and never hardcode
  credentials or secrets.
- Use mocked or fake AWS clients for local tests.
- Keep AWS event shapes and responses faithful to the service contract being
  studied.
- Add or update tests for each behavior change.
- Correct inaccurate assumptions directly, especially around retries,
  idempotency, partial batch failures, IAM permissions, and persistence.

## AWS safety

Do not deploy or modify AWS resources unless the user explicitly approves the
specific lab. Prefer local tests, sample events, ASL validation, and mocked AWS
clients.

## Completion behavior

Before finishing a lesson:

1. Summarize the behavior learned or changed.
2. List tests or checks run.
3. Update `LEARNING-PLAN.md` only when the lesson's evidence is complete.
4. Record any misconception, weak area, or follow-up exercise.
5. State whether the result is tutorial evidence only or a candidate pattern
   for later adaptation elsewhere.
