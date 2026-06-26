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
| Test baseline | Verified | 204 tests passed on 2026-06-25 with `.venv/bin/python -m pytest -q` |
| Intentional Git baseline | Implemented | Repository initialised; `.gitignore` covers `.venv`, caches, bytecode, `.DS_Store`, and `archive/` |
| Consolidation review | Implemented | Import order, formatting, trailing whitespace, dead comments, stale README note, and empty archive file resolved in Lesson 27 |
| Persistence handler boundary hardening | Implemented | `trade_persistence_handler.py` rewritten to production shape; boundary and edge-case tests added in Lesson 28 |
| Ruff formatting baseline | Implemented | `ruff` added to `pyproject.toml`; consistent style applied across all 20 tutorial files |

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
- [ ] Add an explicit SQS poison-message and DLQ design exercise.
- [ ] Test mixed-success SQS batches and partial batch failure semantics.
- [x] Add Step Functions timeout, retry, catch, and terminal-failure examples.
- [ ] Compare EventBridge, SQS, and direct Step Functions invocation in a
  decision table.

### 4. Deepen persistence and IAM reasoning

- [x] Add conditional or idempotent DynamoDB write examples. Lesson 26 uses
  `ConditionExpression="attribute_not_exists(trade_id)"` and treats the
  expected duplicate failure as idempotent success.
- [ ] Document S3 key design, partitioning, overwrite behavior, and encryption
  assumptions.
- [ ] Create least-privilege IAM action/resource checklists for each handler.
- [ ] Add failure-ordering tests for partial S3/DynamoDB persistence.
- [ ] Document when orchestration should compensate, retry, or surface manual
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
