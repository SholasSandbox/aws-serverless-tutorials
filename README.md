# Python and AWS Serverless Handlers Tutorial

This workspace contains guided Python and AWS serverless exercises. It is a
learning project, not part of the Energy Data Lakehouse repository and not
production deployment code.

## Purpose

The exercises build practical understanding of production-shaped serverless
patterns that support SAP-C02 study, including:

- Lambda handler contracts and stable responses
- request and event validation
- environment-based configuration
- structured logging and correlation identifiers
- EventBridge and SQS event handling
- Step Functions task boundaries, retry, and catch behavior
- S3 result-artifact persistence
- DynamoDB status persistence
- dependency injection and mocked AWS clients
- focused pytest coverage

## Current Exercises

| Area | Main files | Current evidence |
|---|---|---|
| API-style Lambda validation | `trade_handler.py` | request parsing, validation, logging, stable success/error responses |
| EventBridge handling | `eventbridge_trade_handler.py` | detail validation and correlation using event IDs |
| SQS handling | `sqs_trade_handler.py` | record parsing, validation, and partial batch response behavior |
| Step Functions validation | `step_functions_validate_trade_handler.py`, `step-functions/` | task handler plus basic, task, retry/catch, timeout, reconciliation, and terminal-failure ASL examples |
| S3 result persistence | `trade_result_persistence.py` | accepted/rejected artifacts and partitioned object keys |
| DynamoDB status persistence | `trade_status_persistence.py` | stable status records and S3 pointers |
| Combined persistence workflow | `trade_persistence_workflow.py`, `trade_persistence_handler.py` | S3 and DynamoDB orchestration with injected clients |
| Tests | `tests/` | unit tests using mocks rather than live AWS resources |

## Workspace Boundary

- The source of truth for tutorial progression is `LEARNING-PLAN.md`.
- Local working rules are in `AGENTS.md`.
- The Energy Data Lakehouse remains a separate applied case study under
  `/Users/shola/Workspace/cloud-projects/energy-market-data-lake`.
- Tutorial work may count as SAP-C02 study time or weak-area remediation when
  the lesson is mapped explicitly in the lakehouse readiness tracker.
- Tutorial code must not be presented as lakehouse implementation evidence.
- Any later promotion into the lakehouse requires a named tracker gap,
  adaptation to lakehouse contracts, IAM review, and repository-specific tests.

## Local Validation

Run the tests from this directory:

```bash
.venv/bin/python -m pytest -q
```

These exercises should use mocks or fakes by default. Do not deploy or modify
AWS resources unless a lesson explicitly calls for a controlled lab and the
user approves it for that task.

## Current Status

The workspace is under version control. The Git repository was initialised
after the test suite reached a stable baseline. `.gitignore` covers `.venv`,
caches, bytecode, `.DS_Store`, and `archive/`.
