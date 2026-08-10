# Python and Serverless Learning Plan

Last reviewed: 2026-08-10

## Objective

Build confident Python and AWS serverless engineering skills through small,
tested exercises. This is a parallel SAP-C02 learning track and is not the
Energy Data Lakehouse implementation.

## Programme Priority Gate

During the current SAP-C02 validation period, the separate Energy Data
Lakehouse SAP-C02 readiness tracker controls programme priority. The learner
will maintain two full timed mocks per week. Tutorial work must not displace a
mock, its review, spaced remediation, or the current DR, migration, and cost
decision work.

An unchecked tutorial item is backlog, not authorization to start it. Local
implementation may resume only at one of the evidence checkpoints recorded in
`docs/tutorial-resume-checkpoints.md`, and only when it fits without weakening
the two-mock cadence. Live AWS work still requires explicit approval for the
specific lab.

## Evidence Rule

Each lesson should produce at least one concrete artifact:

- a tested handler behavior
- a sample AWS event or state-machine definition
- a short design note or service comparison
- a test that demonstrates a failure or retry boundary
- an IAM action/resource checklist
- a wrong-assumption or weak-area note

Completion evidence depends on the lesson type:

- Implementation lesson: the relevant behavior tests must pass.
- ASL lesson: the state-machine definition and intended transitions must be
  structurally validated.
- Conceptual or service-selection lesson: an accuracy-reviewed artifact must
  state its assumptions, boundaries, trade-offs, and evidence sources.

The full repository test suite is regression evidence. Passing unrelated tests
does not prove that a conceptual note is correct.

### Evidence levels

| Evidence level | Meaning |
| --- | --- |
| Conceptual | Accuracy-reviewed explanation, comparison, checklist, or decision artifact; no executable behavior is implied |
| Local tested | Executable Python behavior or an ASL contract has relevant passing local tests; AWS responses may still be mocked or structurally checked |
| Live AWS | The behavior has been deployed, exercised against AWS, and supported by sanitized operational evidence |

A capability may cite more than one level when separate conceptual and local
artifacts exist. A dash means that the target evidence level has not been
attained.

## Current Baseline

| Capability | Completion status | Evidence level | Evidence |
| --- | --- | --- | --- |
| API-style Lambda request parsing and validation | Completed | Local tested | `trade_handler.py`, `tests/test_trade_handler.py` |
| Correlation IDs and logging context | Partial | Local tested | API, EventBridge, and SQS handlers carry correlation context; repository-wide structured logging consistency remains open |
| EventBridge event handling | Completed | Local tested | `eventbridge_trade_handler.py`, corresponding tests |
| SQS record handling and partial batch responses | Completed | Local tested | `sqs_trade_handler.py`, corresponding tests; live event-source mapping configuration is not proved |
| Step Functions task validation | Completed | Local tested | Handler tests and structurally checked ASL examples; no tutorial workflow has run in AWS |
| Accepted/rejected S3 result artifacts | Completed | Local tested | `trade_result_persistence.py`, corresponding mocked `PutObject` tests |
| DynamoDB status records | Partial | Local tested | Conditional `attribute_not_exists(trade_id)` helper and injected duplicate-exception tests exist, but the real workflow does not yet wire the generated conditional-check exception into duplicate-as-success handling |
| Combined S3 and DynamoDB persistence | Partial | Local tested | Deterministic S3 keys and compact workflow responses are tested; real conditional-duplicate handling and live AWS behavior remain unproved |
| boto3 service boundary | Partial | Local tested | S3 client and DynamoDB resource construction, mocked `PutObject`, conditional `PutItem`, and dependency injection are tested; SDK configuration, realistic `ClientError` classification, and live calls remain open |
| Repository documentation and governance | Completed | Conceptual | `README.md`, `AGENTS.md`, this plan |
| Test baseline | Verified | Local tested | 234 tests passed on 2026-08-10 with `.venv/bin/python -m pytest -q` |
| Intentional Git baseline | Completed | Local tested | Repository initialised; `.gitignore` covers `.venv`, caches, bytecode, `.DS_Store`, and `archive/` |
| Consolidation review | Completed | Local tested | Import order, formatting, trailing whitespace, dead comments, stale README note, and empty archive file resolved in Lesson 27 |
| Persistence handler boundary hardening | Completed | Local tested | `trade_persistence_handler.py` boundary validation and edge-case tests added in Lesson 28 |
| Ruff formatting baseline | Completed | Local tested | `ruff` added to `pyproject.toml`; consistent style applied across all 20 tutorial files |
| Persistence failure-ordering reasoning | Completed | Conceptual + Local tested | Lesson 29 note plus workflow tests show S3 can succeed before DynamoDB fails and a retry reuses the same S3 key |
| Persistence IAM boundary | Completed | Conceptual | Lesson 30 checklist scopes S3, DynamoDB, CloudWatch Logs, and Step Functions roles; no tutorial IAM role has been deployed |
| Retry-safe persistence and reconciliation | Completed | Conceptual | Lesson 31 records retry, catch, reconciliation, and no-default-delete guidance |
| S3 key design and encryption assumptions | Completed | Conceptual | Lesson 32 documents prefixes, deterministic keys, versioning implications, and encryption assumptions |
| Step Functions timeout and terminal failure | Completed | Local tested | Lesson 33 ASL definition is structurally tested; no live execution is claimed |
| SQS poison-message and DLQ mental model | Completed | Conceptual + Local tested | Lesson 34A explains the model and connects it to existing mixed-batch handler tests |
| SQS retry and replay decision reasoning | Completed | Conceptual | Lessons 34B and 34C document idempotent side effects, partial-success risk, DLQ triage, and replay boundaries |
| EventBridge vs SQS vs direct Step Functions selection | Completed | Conceptual | Lesson 35 decision note compares fact publication, queued work, and orchestration |
| Serverless entry-point selection | Completed | Conceptual | Lesson 36 compares API Gateway, EventBridge, SQS, and direct Step Functions invocation |
| API-facing vs internal Lambda boundaries | Completed | Conceptual | Lesson 37 separates HTTP translation, internal contracts, retry ownership, identity context, and least privilege |
| API-to-Step Functions handoff adapter | Partial | Local tested | `api_workflow_handoff.py` and focused mocked tests validate the local Lambda-mediated pattern; the post-attempt architecture decision and all live evidence remain open |
| Live tutorial AWS integration | Not started | — | No tutorial resources have been deployed or exercised in AWS |

## Tutorial Backlog and Resume Sequence

Nothing in this section is active merely because it is unchecked. Resume order
and evidence gates are controlled by `docs/tutorial-resume-checkpoints.md`.

### 1. Consolidate the existing lessons

- [x] Run the complete pytest suite and record the baseline result: 152 tests
  passed on 2026-06-13 with `.venv/bin/python -m pytest -q`.
- [x] Remove or classify scratch files such as `test2.py`, `test3.py`,
  `test_event.py`, `manual_import_check.py`, and `Stepping/`.
- [x] Add a minimal dependency file or `pyproject.toml` for reproducible setup.
- [x] Add `.gitignore` coverage for `.venv`, caches, bytecode, and `.DS_Store`.
- [x] Standardize formatting and import order without obscuring lesson intent.

### 2. Strengthen Python production shape

- [x] Introduce typed validation helpers where they reduce repetition in the
  persistence boundary; do not generalize them without a demonstrated need.
- [ ] Standardize error constants and stable response contracts.
- [ ] Standardize machine-queryable structured log fields where a demonstrated
  operational need justifies them; parameterized `%s` logging is not itself an
  error.
- [x] Add unexpected dependency-failure and malformed nested-event tests for
  the persistence path; reopen repository-wide work only for a demonstrated
  gap.
- [x] Explain module boundaries, dependency injection, and pure validation
  boundaries in Lessons 28 and 37; a separate generic note is not required.

### 3. Deepen serverless behavior

- [ ] Compare retry and idempotency implications across EventBridge and direct
  Step Functions invocation.
  Persistence-workflow retry/idempotency evidence is complete in Lesson 26,
  and SQS retry/idempotency/DLQ evidence is complete in Lessons 34A-34C.
- [x] Add an explicit SQS poison-message and DLQ design exercise.
- [x] Test mixed-success SQS batches and partial batch failure semantics.
- [x] Add Step Functions timeout, retry, catch, and terminal-failure examples.
- [x] Compare EventBridge, SQS, and direct Step Functions invocation in a
  decision table.

### 4. Deepen persistence and IAM reasoning

- [x] Add conditional or idempotent DynamoDB write examples. Lesson 26 uses
  `ConditionExpression="attribute_not_exists(trade_id)"`; the helper can treat
  an injected expected duplicate failure as idempotent success, while the real
  workflow wiring remains a recorded limitation.
- [x] Document S3 key design, partitioning, overwrite behavior, and encryption
  assumptions.
- [x] Create a least-privilege IAM action/resource checklist for the
  persistence workflow.
- [x] Add failure-ordering tests for partial S3/DynamoDB persistence.
- [x] Document when orchestration should compensate, retry, or surface manual
  reconciliation.

### 5. Resume checkpoints and optional controlled AWS lab

- [x] Record the local implementation and post-exam checkpoints in
  `docs/tutorial-resume-checkpoints.md`.
- [ ] Define cost, IAM, cleanup, and success criteria before deployment.
- [ ] Deploy only after explicit user approval.
- [ ] Capture sanitized evidence and tear down resources after the lesson.
- [ ] Do not connect the lab to the Energy Data Lakehouse automatically.

## Known Current Implementation Limitations

- `persist_trade_status_record` can treat a supplied conditional-check
  exception as duplicate success, but `persist_trade_processing_result` does
  not currently supply DynamoDB's generated exception class. The real workflow
  therefore propagates that conditional failure instead of proving end-to-end
  duplicate-as-success behavior.
- `build_persistence_dependencies` creates the S3 client and DynamoDB resource
  on every current handler invocation. A later local slice should evaluate a
  reusable or lazily cached client factory while preserving dependency
  injection and import-safe tests.
- No tutorial IAM role, API route, Lambda, state machine, log group, metric, or
  alarm has been deployed or verified in AWS.
- `api_workflow_handoff.py` is a local teaching adapter, not the selected
  architecture for a deployed vertical slice. The direct-integration versus
  Lambda-mediated decision remains at Checkpoint C.
- These limitations are recorded backlog. This planning update does not
  authorize code changes or AWS deployment.

## Completed Lesson Evidence

### Lesson 25: Persistence task contract and S3 result artifacts

Status: **Completed locally in June 2026**.

Evidence:

- `step-functions/persistence-task-state.json` and
  `persistence-task-state-with-retry-catch.json` define the Step Functions
  persistence-task contract and bounded Retry/Catch path;
- `docs/lessons/lesson-25-s3-result-artifacts.md` documents the S3 artifact
  envelope, deterministic key, and dependency-injected write boundary;
- the two artifacts are complementary parts of the same persistence lesson,
  not two different Lesson 25 identities;
- no AWS resources were deployed.

SAP-C02 mapping: Domain 2 persistence and resilience and Domain 3 operational
improvement. This is tutorial evidence only, not Energy Data Lakehouse
implementation.

### Lesson 26: Idempotency and duplicate persistence protection

Status: **Completed locally on 2026-06-21**.

Evidence:

- conditional DynamoDB write protection using
  `ConditionExpression="attribute_not_exists(trade_id)"`;
- the helper returns idempotent success when its test injects the expected
  duplicate conditional-check exception;
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

- `lesson_1a_lambda_response.py` remains an archived early-lesson artifact;
  it now re-exports the completed Lesson 1 handler so scratch imports do not
  leave the workspace in a broken state;
  consider replacing it with a clearer historical note or removing it in a
  future consolidation exercise.

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

### Lesson 34B: SQS retry and idempotency implications

Status: **Completed locally on 2026-07-10**.

Evidence:

- `docs/lessons/lesson-34b-sqs-retry-and-idempotency-implications.md`
  explains that SQS retry safety depends on idempotent side effects rather than
  on suppressing retries;
- the note connects `batchItemFailures` to retry signalling, not business
  rejection storage;
- the lesson makes the partial-success risk explicit when persistence side
  effects can succeed before a later exception causes the message to retry;
- deterministic S3 keys and duplicate-safe DynamoDB behavior are described as
  the conditions that make repeated processing safer;
- full local suite passed: 218 tests.

SAP-C02 mapping: Domain 2 resilience and decoupling, Domain 3 operational
excellence, and Domain 1 boundary reasoning. This is tutorial evidence only,
not Energy Data Lakehouse implementation.

### Lesson 34C: SQS DLQ operational handling and replay decision model

Status: **Completed locally on 2026-07-10**.

Evidence:

- `docs/lessons/lesson-34c-sqs-dlq-operational-handling-and-replay-decision-model.md`
  defines the rule that a DLQ is quarantine, not automatic recovery;
- the note adds failure-classification, replay-decision, and replay-safety
  tables tied to the existing `sqs_trade_handler` retry boundary;
- the lesson makes the operational distinction between replayable transient
  failures and messages that should be archived, discarded, or fixed-first;
- full local suite passed: 218 tests.

SAP-C02 mapping: Domain 2 resilience and decoupling, Domain 3 operational
excellence, and Domain 1 control-boundary reasoning. This is tutorial evidence
only, not Energy Data Lakehouse implementation.

### Lesson 35: EventBridge vs SQS vs direct Step Functions invocation

Status: **Completed locally on 2026-07-10**.

Evidence:

- `docs/lessons/lesson-35-eventbridge-vs-sqs-vs-step-functions-invocation.md`
  compares event publication, queued work, and direct workflow orchestration;
- the note includes decision and failure-model tables showing when EventBridge,
  SQS, or direct Step Functions invocation is the better fit;
- the lesson connects the comparison back to the existing tutorial handlers and
  Step Functions examples rather than introducing new deployment code;
- full local suite passed: 218 tests.

SAP-C02 mapping: Domain 2 integration and new-solution design, Domain 3
operational reasoning, and Domain 1 boundary clarity. This is tutorial evidence
only, not Energy Data Lakehouse implementation.

### Lesson 36: Choosing the right serverless entry point

Status: **Completed locally on 2026-07-23**.

Evidence:

- `docs/lessons/lesson-36-choosing-the-right-serverless-entry-point.md`
  compares API Gateway, EventBridge, SQS, and direct Step Functions invocation;
- the decision model distinguishes HTTP requests, business facts, durable work,
  and known workflows;
- asynchronous response semantics now state that `202 Accepted` is valid only
  after the internal handoff itself succeeds;
- no AWS resources were deployed and no code behaviour changed.

SAP-C02 mapping: Domain 2 integration and new-solution design, Domain 3
operational reasoning, and Domain 1 external/internal boundary design. This is
tutorial evidence only, not Energy Data Lakehouse implementation.

### Lesson 37: API-facing Lambda versus internal service Lambda

Status: **Completed locally on 2026-07-23; accuracy-reviewed 2026-07-26**.

Evidence:

- `docs/lessons/lesson-37-api-facing-lambda-vs-internal-service-lambda.md`
  separates HTTP proxy contracts from normalized internal task contracts;
- the note distinguishes boundary validation, domain validation, retry owners,
  identity context, correlation identifiers, and dependency ownership;
- the accuracy review records API Gateway base64-body handling and the Lambda
  execution-role permissions required for an SQS event source mapping;
- no AWS resources were deployed and no code behaviour changed;
- the full local suite still passes: 218 tests on 2026-07-26.

SAP-C02 mapping: Domain 1 security and responsibility boundaries, Domain 2
serverless design, and Domain 3 operational improvement. This is tutorial
evidence only, not Energy Data Lakehouse implementation.

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
| --- | --- |
| EventBridge, SQS, Step Functions | Domain 2 integration, decoupling, failure handling, and new-solution design |
| S3 and DynamoDB persistence | Domain 2 storage selection and Domain 3 reliability/performance improvement |
| IAM action/resource reasoning | Domain 1 organizational/security design and Domain 3 security improvement |
| retries, idempotency, DLQs, compensation | Domain 2 resilience and Domain 3 continuous improvement |
| local tests and structured logging | Domain 3 operational excellence and observability |

Tutorial completion does not update a lakehouse implementation checklist row
unless the pattern is separately adapted, tested, and evidenced in that
repository.
