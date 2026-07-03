# Python and Serverless Learning Plan

## Objective

Build confident Python and AWS serverless engineering skills through small,
tested exercises. This is a parallel SAP-C02 learning track and is not the
Energy Data Lakehouse implementation.

## Evidence Rule

Each lesson should produce at least one concrete artifact:

- a tested handler behavior
- a sample AWS event or state-machine definition
- a short design note or service comparison
- a test that demonstrates a failure or retry boundary
- an IAM action/resource checklist
- a wrong-assumption or weak-area note

Mark a lesson complete only when its local tests pass and the behavior can be
explained without relying on the tutorial prompt.

## Current Baseline

| Capability | Status | Evidence |
|---|---|---|
| API-style Lambda request parsing and validation | Implemented | `trade_handler.py`, `tests/test_trade_handler.py` |
| Correlation IDs and structured logging concepts | Implemented | API, EventBridge, and SQS handlers |
| EventBridge event handling | Implemented | `eventbridge_trade_handler.py`, corresponding tests |
| SQS record handling and partial batch responses | Implemented | `sqs_trade_handler.py`, corresponding tests |
| Step Functions task validation | Implemented | handler, ASL examples, and tests |
| Accepted/rejected S3 result artifacts | Implemented | `trade_result_persistence.py`, corresponding tests |
| DynamoDB status records | Implemented | Conditional `attribute_not_exists(trade_id)` writes and duplicate-as-idempotent-success tests in `trade_status_persistence.py` |
| Combined S3 and DynamoDB persistence | Implemented | Deterministic S3 keys and repeatable compact workflow responses in workflow/handler modules and tests |
| Repository documentation and governance | Implemented | `README.md`, `AGENTS.md`, this plan |
| Test baseline | Verified | 218 tests passed on 2026-07-03 with `python3 -m pytest -q` |
| Intentional Git baseline | Implemented | Repository initialised; `.gitignore` covers `.venv`, caches, bytecode, `.DS_Store`, and `archive/` |
| Consolidation review | Implemented | Import order, formatting, trailing whitespace, dead comments, stale README note, and empty archive file resolved in Lesson 27 |
| Persistence handler boundary hardening | Implemented | `trade_persistence_handler.py` rewritten to production shape; boundary and edge-case tests added in Lesson 28 |
| Ruff formatting baseline | Implemented | `ruff` added to `pyproject.toml`; consistent style applied across all 20 tutorial files |
| Persistence failure-ordering reasoning | Implemented | Lesson 29 note plus workflow tests showing S3 can succeed before DynamoDB fails and retry reuses the same S3 key |
| Persistence IAM boundary | Implemented | Lesson 30 checklist scopes S3, DynamoDB, CloudWatch Logs, and Step Functions role responsibilities for the persistence path |
| Retry-safe persistence and reconciliation | Implemented | Lesson 31 decision note records retry, catch, reconciliation, and no-default-delete compensation guidance |
| S3 key design and encryption assumptions | Implemented | Lesson 32 note documents accepted/rejected prefixes, deterministic keys, overwrite behavior, and bucket-level encryption assumptions |
| Step Functions timeout and terminal failure | Implemented | Lesson 33 ASL definition and tests cover timeout, bounded retry, catch, reconciliation routing, and explicit terminal failure |
| SQS poison-message and DLQ mental model | Implemented | Lesson 34A note explains poison messages, visibility timeout, maxReceiveCount, DLQ ownership, idempotency, and SQS versus Step Functions failure scope |

## Active Sequence

### 1. Consolidate the existing lessons

- [x] Run the complete pytest suite and record the baseline result: 152 tests
  passed on 2026-06-13 with `.venv/bin/python -m pytest -q`.
- [x] Remove or classify scratch files such as `test2.py`, `test3.py`,
  `test_event.py`, `manual_import_check.py`, and `Stepping/`.
- [x] Add a minimal dependency file or `pyproject.toml` for reproducible setup.
- [x] Add `.gitignore` coverage for `.venv`, caches, bytecode, and `.DS_Store`.
- [x] Standardize formatting and import order without obscuring lesson intent.
### 2. Strengthen Python production shape

- [ ] Introduce typed event/result helpers only where they reduce repeated
  validation logic.
- [ ] Standardize error constants and stable response contracts.
- [ ] Replace log-message interpolation patterns with consistent structured
  context.
- [ ] Add tests for unexpected exceptions and malformed nested event shapes.
- [ ] Explain module boundaries, dependency injection, and pure versus impure
  functions in a short note.

### 3. Deepen serverless behavior

- [ ] Demonstrate Lambda retry and idempotency implications for each event
  source.
  Persistence-workflow retry/idempotency evidence is complete in Lesson 26;
  event-source-specific retry implications remain open.
- [x] Add an explicit SQS poison-message and DLQ design exercise.
- [x] Test mixed-success SQS batches and partial batch failure semantics.
- [x] Add Step Functions timeout, retry, catch, and terminal-failure examples.
- [ ] Compare EventBridge, SQS, and direct Step Functions invocation in a
  decision table.

### 4. Deepen persistence and IAM reasoning

- [x] Add conditional or idempotent DynamoDB write examples. Lesson 26 uses
  `ConditionExpression="attribute_not_exists(trade_id)"` and treats the
  expected duplicate failure as idempotent success.
- [x] Document S3 key design, partitioning, overwrite behavior, and encryption
  assumptions.
- [x] Create a least-privilege IAM action/resource checklist for the
  persistence workflow.
- [x] Add failure-ordering tests for partial S3/DynamoDB persistence.
- [x] Document when orchestration should compensate, retry, or surface manual
  reconciliation.

### 5. Optional controlled AWS lab

- [ ] Define cost, IAM, cleanup, and success criteria before deployment.
- [ ] Deploy only after explicit user approval.
- [ ] Capture sanitized evidence and tear down resources after the lesson.
- [ ] Do not connect the lab to the Energy Data Lakehouse automatically.

## Completed Lesson Evidence

### Lesson 26: Idempotency and duplicate persistence protection

Status: **Completed locally on 2026-06-21**.

Evidence:

- conditional DynamoDB write protection using
  `ConditionExpression="attribute_not_exists(trade_id)"`;
- duplicate conditional-check failure returns idempotent success;
- unexpected DynamoDB errors remain visible;
- deterministic S3 keys are verified through `build_s3_key`;
- repeated successful workflow execution returns the same compact persistence
  response;
- full local suite passed: 168 tests.

Caveat:

- duplicate handling is tested at `persist_trade_status_record` through an
  injected fake conditional-check exception;
- the full workflow does not yet inject a real DynamoDB conditional-check
  exception type;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 2 resilience and Domain 3 continuous improvement.
This is tutorial evidence only, not Energy Data Lakehouse implementation.

### Lesson 27: Consolidation review

Status: **Completed locally on 2026-06-21**.

Evidence:

- naming review: all public function names are consistent with their module
  contract; no renames required;
- formatting review: trailing whitespace removed from `trade_status_persistence.py`
  (`ConditionExpression` line and extra blank line after `except` block);
  double trailing blank lines removed from `trade_result_persistence.py` and
  `trade_status_persistence.py`;
- import review: `test_trade_handler.py` import block reordered to stdlib →
  third-party → local; `test_sqs_trade_handler.py` import block consolidated
  and tightened; `test_eventbridge_trade_handler.py` missing blank line between
  tests added;
- scratch file classification: `archive/` contents confirmed as early lesson
  artifacts; empty `archive/json` file deleted; `lesson_1a_lambda_response.py`
  annotated with a clarifying header comment;
- conftest.py dead commented-out code removed;
- `test_trade_status_persistence.py` inline comment spacing fixed;
- `README.md` stale git-status note updated to reflect the initialised
  repository;
- `.gitignore` and `pyproject.toml` confirmed clean; no changes needed;
- full local suite passed: 168 tests.

Weak area noted:

- `lesson_1a_lambda_response.py` remains as an incomplete lesson artifact;
  it calls undefined test functions and would fail if executed directly;
  consider replacing it with a complete early-lesson example in a future
  exercise.

SAP-C02 mapping: Domain 3 operational excellence (code hygiene, reproducible
setup, structured evidence).
This is tutorial evidence only, not Energy Data Lakehouse implementation.

### Lesson 28: Persistence handler boundary hardening

Status: **Completed locally on 2026-06-25**.

Evidence:

- `trade_persistence_handler.py` rewritten to production shape: strict input
  validation, typed internal helpers, structured error responses, and clean
  separation between the Lambda boundary and the workflow layer;
- 36 new tests added covering malformed event shapes, missing required fields,
  unexpected workflow exceptions, and correct pass-through of workflow results;
- full local suite passed: 204 tests.

SAP-C02 mapping: Domain 3 operational excellence (handler contracts) and
Domain 2 resilience (boundary isolation).
This is tutorial evidence only, not Energy Data Lakehouse implementation.

### Ruff formatting baseline

Status: **Completed locally on 2026-06-25**.

Evidence:

- `ruff` added to `pyproject.toml` dev dependencies;
- consistent style applied across all 20 tutorial source and test files;
- full local suite passed: 204 tests; no behaviour changes.

### Lesson 29: Persistence failure ordering

Status: **Completed locally on 2026-06-26**.

Evidence:

- `docs/lessons/lesson-29-persistence-failure-ordering.md` records the
  S3-then-DynamoDB failure boundary;
- workflow tests show that S3 can succeed before DynamoDB fails;
- retry tests show the same deterministic S3 key is reused after the
  DynamoDB failure path;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 2 resilience and Domain 3 continuous improvement.
This is tutorial evidence only, not Energy Data Lakehouse implementation.

### Lesson 30: Least-privilege IAM checklist for persistence

Status: **Completed locally on 2026-06-26**.

Evidence:

- `docs/iam/persistence-handler-iam-checklist.md` scopes the persistence
  Lambda to S3 `PutObject`, DynamoDB `PutItem`, and CloudWatch Logs writes;
- the Step Functions role boundary is kept to `lambda:InvokeFunction`;
- accepted/rejected S3 prefixes drive the recommended S3 resource scope;
- encryption cautions separate S3 SSE-KMS from DynamoDB table encryption;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 1 secure architectures and Domain 3 security
improvement. This is tutorial evidence only, not Energy Data Lakehouse
implementation.

### Lesson 31: Retry-safe persistence and reconciliation

Status: **Completed locally on 2026-06-27**.

Evidence:

- `docs/lessons/lesson-31-retry-safety-and-reconciliation.md` defines when to
  retry, catch, fail, or route to reconciliation;
- the note ties retry safety to deterministic S3 keys and explicit DynamoDB
  idempotency behavior;
- the note rejects default S3 delete compensation unless it is deliberately
  designed and tested;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 2 resilience and Domain 3 operational excellence.
This is tutorial evidence only, not Energy Data Lakehouse implementation.

### Lesson 32: S3 key design and encryption assumptions

Status: **Completed locally on 2026-06-27**.

Evidence:

- `docs/lessons/lesson-32-s3-key-design-and-encryption.md` documents the
  `trade-results/accepted/*` and `trade-results/rejected/*` prefix boundary;
- deterministic S3 keys are connected to retry safety and IAM scoping;
- bucket default encryption is the current tutorial assumption;
- customer-managed KMS is deferred until an explicit deployment design exists;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 2 storage design, Domain 1 security boundaries, and
Domain 3 operational improvement. This is tutorial evidence only, not Energy
Data Lakehouse implementation.

### Lesson 33: Step Functions timeout and terminal failure

Status: **Completed locally on 2026-07-01**.

Evidence:

- `step-functions/persistence-task-timeout-terminal-failure.asl.json` defines
  a persistence task with `TimeoutSeconds`, bounded `Retry`, `Catch`,
  reconciliation routing, and an explicit terminal `Fail` state;
- `tests/test_step_functions_timeout_terminal_failure_definition.py` verifies
  the ASL contract and confirms Step Functions does not call S3 or DynamoDB
  directly;
- `docs/lessons/lesson-33-step-functions-timeout-and-terminal-failure.md`
  explains the trade-off between automatic cleanup and visible failure;
- full local suite passed: 217 tests.

SAP-C02 mapping: Domain 2 resilience, Domain 3 continuous improvement, and
Domain 1 role-boundary reasoning. This is tutorial evidence only, not Energy
Data Lakehouse implementation.

### Lesson 34A: SQS poison-message and DLQ mental model

Status: **Completed locally on 2026-07-03**.

Evidence:

- `docs/lessons/lesson-34a-sqs-poison-message-and-dlq-mental-model.md`
  explains poison messages, transient processing failures, validation
  rejections, partial batch response behaviour, visibility timeout,
  `maxReceiveCount`, DLQ ownership, and idempotency implications;
- the note records the important correction that the current handler treats
  validation and business rejections as non-retryable handled records, while
  `persist_trade(...)` exceptions are returned in `batchItemFailures`;
- `tests/test_sqs_trade_handler.py` includes a mixed-batch retryable persistence
  failure test showing only the failed message ID is returned;
- full local suite passed: 218 tests.

SAP-C02 mapping: Domain 2 resilience and decoupling, Domain 3 operational
excellence, and Domain 1 security boundary reasoning. This is tutorial evidence
only, not Energy Data Lakehouse implementation.

## Parked Topics

- Docker and container packaging
- AI orchestration
- polished UI work
- complex microservices
- production deployment automation beyond a deliberately approved lesson

## Relationship to SAP-C02

Tutorial sessions may be logged in the SAP-C02 readiness tracker when they are
mapped to a domain or weak area. Useful mappings include:

| Tutorial topic | SAP-C02 relevance |
|---|---|
| EventBridge, SQS, Step Functions | Domain 2 integration, decoupling, failure handling, and new-solution design |
| S3 and DynamoDB persistence | Domain 2 storage selection and Domain 3 reliability/performance improvement |
| IAM action/resource reasoning | Domain 1 organizational/security design and Domain 3 security improvement |
| retries, idempotency, DLQs, compensation | Domain 2 resilience and Domain 3 continuous improvement |
| local tests and structured logging | Domain 3 operational excellence and observability |

Tutorial completion does not update a lakehouse implementation checklist row
unless the pattern is separately adapted, tested, and evidenced in that
repository.
