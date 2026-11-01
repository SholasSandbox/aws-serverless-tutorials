# Tutorial Workspace Instructions

## Controlling documents

Read `README.md`, `LEARNING-PLAN.md`, and `learning-summary.md` before
changing this workspace. `LEARNING-PLAN.md` controls the original Lessons
38–45 roadmap; `learning-summary.md` records completed learning evidence.
Flag any departure from that roadmap before starting it, including the
original lesson, rationale, delayed work and planned point of resumption.

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
- When the user suggests an action that conflicts with good practice, explain
  the concern and recommend the better approach before proceeding. Because the
  workspace is used for learning, do not implement a poor practice silently.
  Proceed with the user's requested deviation only after they explicitly state
  that they want to make that exception for the current task.

## AWS safety

Do not deploy or modify AWS resources unless the user explicitly approves the
specific lab. Prefer local tests, sample events, ASL validation, and mocked AWS
clients.

## Completion behavior

Before finishing a lesson:

1. Summarize the behavior learned or changed.
2. List tests or checks run.
3. Update `learning-summary.md` at the end of each completed lesson with
   the original lesson number/title, key learning, concrete file/test evidence,
   limitations, and next lesson or follow-up.
4. Update `LEARNING-PLAN.md` only when that lesson's evidence is complete.
5. Record misconceptions, weak areas and follow-up work.
6. Distinguish conceptual, locally tested and live AWS evidence. Record test
   counts and timestamps only when supported by supplied or tool evidence.
7. Do not silently renumber or expand the standing Lessons 38–45.
