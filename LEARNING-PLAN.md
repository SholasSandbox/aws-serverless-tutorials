# Python and Serverless Learning Plan

Last reviewed: 2026-11-03 (assessment readiness and learning evidence reconciliation)

## Objective

Develop independently demonstrable Python, AWS serverless and,
subsequently, applied AI engineering competence.

The programme builds on the completed SAP-C02 architectural
foundation and supports the longer-term goal of combining
financial-services, energy-trading and regulated-industry
experience with credible cloud and AI architecture capability.

Learning should produce evidence in six areas:

| Focus | Demonstrable capability |
| --- | --- |
| Python engineering | Independently implement, test, debug and explain maintainable Python code |
| Serverless engineering | Build reliable AWS integrations with explicit contracts, persistence and failure handling |
| Security and operations | Reason about IAM, retries, idempotency, observability, cost and recovery |
| Architectural judgement | Translate requirements into defensible designs and explain alternatives, constraints and business outcomes |
| Applied AI engineering (future stage) | Integrate Bedrock and model APIs, evaluate outputs, manage tool boundaries, failures, data exposure and inference costs |
| Employability evidence | Demonstrate solutions, diagnose defects and communicate technical and architectural decisions |

The original Lessons 38–45 remain the controlling serverless
roadmap. Applied AI implementation is deferred until the
serverless foundation is complete.

AWS Skill Builder complements the tutorials. The Energy Data
Lakehouse remains a separate implementation and evidence boundary.

Historical SAP-C02 mappings are retained for reference but
do not govern current progression.

## Programme Priority and Standing Roadmap

Hands-on engineering competence, practical architecture decisions and sustainable
learning time now drive this programme. AWS Skill Builder Serverless Developer is
a complementary foundation, not a replacement for writing and testing code.

The August SAP-C02 two-mock schedule and the gates in
`docs/tutorial-resume-checkpoints.md` are **historical**. They do not govern
the current lesson sequence. The live AWS approval requirement remains.

### Controlling Lessons 38–45

Do not renumber, expand, or replace these lessons without calling out the
original lesson affected, the reason, what is delayed and where work resumes.

| Lesson | Original heading | Status / next action |
| --- | --- | --- |
| 38 | API Lambda → internal workflow contract | **Complete locally** — post-38B input contains normalised trade and idempotency key, not attempt-specific request/correlation IDs |
| 39 | Lambda → Step Functions `StartExecution` with boto3 | **Complete locally** — injected adapter, stable input, correct start/error contracts; no live AWS |
| 40 | Step Functions input/output data flow | **Complete locally** — JSONPath Task input/output contract and focused structural test passed; no live AWS execution |
| 41 | Choice + validation path | **Next** |
| 42 | Retry/Catch + workflow failure semantics | Planned |
| 43 | Idempotent workflow starts / duplicate requests | **Partially advanced early** — DynamoDB registry implemented locally, integration/recovery outstanding |
| 44 | IAM boundary for API Lambda and workflow | Planned |
| 45 | Controlled AWS deployment of this vertical slice | Planned; explicit approval and cost/cleanup plan required |

The October "Lesson 39: DynamoDB Submission Registry" was an **out-of-order
Lesson 43 exercise**, not a replacement for original Lesson 39. The next
active lesson is **41**. Defer durable exact-input retention, API-registry
integration, recovery ownership and workers to Lesson 43 or a separately
approved later exercise.

### Learner working approach

Explain the requirement, then give the learner a small independent coding task.
Review with defects and hints before showing a full correction unless requested.
Prefer pytest, Ruff, injected boto3 clients, local-only tests and small,
explicit service boundaries. Avoid unrelated refactoring, deployment or
frameworks.

### Independence milestones

Use meaningful milestones within the existing lessons to demonstrate that the
learner can:

- Implement and explain a small requirement using documentation and normal
  development tools.
- Diagnose a realistic or injected failure using tests and logs, and explain
  why the fix works.
- Provide reproducible setup instructions and explain the design's security,
  reliability and cost trade-offs.

Assistance is compatible with independence when the learner understands,
can adapt and can troubleshoot the resulting solution. Record the assistance
used and any remaining weaknesses in `learning-summary.md`; these criteria
do not establish that earlier lessons already demonstrate independence.
Use existing lesson artifacts rather than adding a separate course or project.

## Serverless Assessment Readiness

AWS Serverless Demonstrated is a separate practical readiness milestone.
Attempt it when the learner can independently implement and troubleshoot the
serverless capabilities in the current assessment objectives. AI training,
RAG/agent practice and Bedrock competence are not prerequisites in this plan.

AWS's [microcredential overview](https://aws.amazon.com/blogs/training-and-certification/microcredentials-from-aws-are-now-free-heres-why-that-matters/)
distinguishes serverless implementation and troubleshooting from the separate
Bedrock-focused Agentic AI assessment. Check the current assessment guide
before planning an attempt; the overview is not an exhaustive syllabus.

Review readiness against the assessed services using relevant implementation,
console/CLI troubleshooting and operational evidence. Course completion and
local mocked tests alone do not establish practical assessment readiness.
Record demonstrated capabilities and remaining gaps in `learning-summary.md`.

This milestone can be reviewed as serverless skills develop; it does not
reorder Lessons 38–45 or depend on completing the applied AI extension.
Existing approval, cost and cleanup controls continue to apply to AWS labs.

## Post-Lesson 45: Applied AI Extension

Status: Planned — not started.

This stage extends the serverless foundation into applied AI
engineering and architecture. It does not modify, renumber
or add work to Lessons 38–45.

### Entry conditions

- Complete Lessons 38–45 with the appropriate evidence.
- Complete AWS Skill Builder Serverless Developer before
  starting AWS SimuLearn: Generative AI Architect.
- Retain the existing approval, cost and cleanup controls
  for any deployment.

### Learning progression

1. AWS SimuLearn: Generative AI Architect
   Develop customer requirements discovery, architectural
   decision-making and AWS AI solution implementation.

2. RAG/Agent Practice with Bedrock
   Strengthen independent model integration, retrieval,
   evaluation, tool control, security and troubleshooting.

### Engineering outcomes

After the serverless foundation, select bounded AI
integration work that demonstrates:

- Secure and reliable model invocation.
- Controlled interaction between AI and AWS workflows.
- Validation, evaluation and failure handling.
- Observability, latency, cost and data-exposure controls.
- Independent console and CLI troubleshooting.

Reuse relevant serverless patterns rather than creating
unnecessary infrastructure or additional projects.

Each implementation must distinguish conceptual,
locally tested and live AWS evidence.

### Completion criteria for a bounded AI exercise

Before implementation, define the use case, a small evaluation dataset,
expected behaviour and measurable acceptance thresholds. Completion requires:

- Recorded evaluation results against the defined quality criteria.
- Tests or evaluation cases for invalid outputs, dependency failures and any
  retrieval or tool boundaries used by the exercise.
- Evidence against the agreed latency, inference-cost and data-exposure limits.
- Reproducible instructions and an explanation of the design, limitations
  and troubleshooting decisions, using the independence milestones above.

Record the model/configuration, assistance used, evidence level and unresolved
weaknesses in `learning-summary.md`. Mocked results do not establish live model
quality, latency or cost. Course completion alone does not complete an
independent AI exercise. These criteria apply to future selected exercises;
they do not authorise additional work now.

This section defines future direction. It does not
authorise immediate AI development, AWS deployment,
additional learning assignments or workload expansion.

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

## End-of-Lesson Completion Protocol

After **every completed lesson**, update both documentation records:

1. Add an entry in `learning-summary.md` using the original lesson number and
   title, key concepts and trade-offs, files/artifacts, exact test evidence,
   outstanding weaknesses and the next lesson.
2. Update this plan's roadmap status only when supported by evidence.
3. Clearly label **conceptual**, **locally tested**, or **live AWS** evidence;
   mocked calls do not demonstrate live concurrency or idempotency guarantees.
4. Record dates/times, test results and commit IDs only when supported by
   terminal output or an available tool, not inference.
5. Before departing from original Lessons 38–45, record the reason,
   opportunity cost, affected lesson and planned point of resumption.
6. Never make unapproved AWS resource, IAM, or deployment changes.

## Current Baseline

| Capability | Completion status | Evidence level | Evidence |
| --- | --- | --- | --- |
| API-style Lambda request parsing and validation | Completed | Local tested | `trade_handler.py`, `tests/test_trade_handler.py` |
| Correlation IDs and logging context | Partial | Local tested | API, EventBridge, and SQS handlers carry correlation context; repository-wide structured logging consistency remains open |
| EventBridge event handling | Completed | Local tested | `eventbridge_trade_handler.py`, corresponding tests |
| SQS record handling and partial batch responses | Completed | Local tested | `sqs_trade_handler.py`, corresponding tests; live event-source mapping configuration is not proved |
| Step Functions task validation | Completed | Local tested | Handler tests and structurally checked ASL examples; no tutorial workflow has run in AWS |
| Step Functions JSONPath validation handoff (Lesson 40) | Complete locally | Conceptual + local tested | `step-functions/trade-validation-with-task.asl.json` uses `InputPath: $.trade` and `ResultPath: $.validation`; `tests/test_step_functions_validation_contract.py` verifies the direct-ARN Task, selected input, merge location and next-state transition; structural test only |
| Accepted/rejected S3 result artifacts | Completed | Local tested | `trade_result_persistence.py`, corresponding mocked `PutObject` tests |
| DynamoDB status records | Partial | Local tested | Conditional `attribute_not_exists(trade_id)` helper and injected duplicate-exception tests exist, but the real workflow does not yet wire the generated conditional-check exception into duplicate-as-success handling |
| Combined S3 and DynamoDB persistence | Partial | Local tested | Deterministic S3 keys and compact workflow responses are tested; real conditional-duplicate handling and live AWS behavior remain unproved |
| boto3 service boundary | Partial | Local tested | S3 client and DynamoDB resource construction, mocked `PutObject`, conditional `PutItem`, and dependency injection are tested; SDK configuration, realistic `ClientError` classification, and live calls remain open |
| Repository documentation and governance | Completed | Conceptual | `README.md`, `AGENTS.md`, this plan |
| Test baseline | Verified | Local tested | Latest learner-supplied Lesson 40 regression: 249 tests passed in 0.22s; focused contract test: 1 passed in 0.01s; Ruff all checks passed; `git diff --check` reported no errors |
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
| API-to-Step Functions handoff adapter | Completed locally | Local tested | `api_workflow_handoff.py` and `tests/test_api_workflow_handoff.py` verify injected `StartExecution`, retry-stable input/name and honest API responses; not deployed |
| DynamoDB submission registry (partial Lesson 43) | Partial | Local tested | `submission_registry.py` and 11 focused tests cover conditional registration, fingerprint classification and conditional start confirmation; not integrated or deployed |
| Live tutorial AWS integration | Not started | — | No tutorial resources have been deployed or exercised in AWS |

## Historical Backlog (June–August 2026)

This section preserves prior evidence and unresolved quality gaps, but it
does **not** control current lesson order. The Lessons 38–45 table above is
authoritative. Unchecked backlog is not authorization for unrelated work.

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
- `api_workflow_handoff.py` demonstrates a Lambda-mediated handoff locally,
  but the deployed integration choice versus direct API Gateway integration
  still needs an explicit decision before Lesson 45.
- `submission_registry.py` is not yet integrated with that API handoff.
  Canonical fingerprint generation, tenant-safe execution naming, durable
  serialized start input and crash recovery remain open under Lesson 43.
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

### Lesson 38 — API Lambda → internal workflow contract

Status: **Completed locally**. The post-38B internal workflow input contains
normalised trade plus `idempotency_key`, not attempt-specific request or
correlation IDs. Local contract tests support this. No live AWS execution.

### Lesson 39 — Lambda → Step Functions StartExecution with boto3

Status: **Completed locally**. `start_trade_workflow()` and the
`handle_trade_submission()` path in `api_workflow_handoff.py` demonstrate an
injected boto3 `StartExecution` boundary, deterministic name/input,
`202 Accepted`, and client-safe error handling. Local tests only.

### Lesson 40 — Step Functions input/output data flow

Status: **Complete locally (conceptual + local tested)**. The existing direct
Lambda-ARN `ValidateTrade` Task selects `$.trade` as the handler input and
inserts the direct Lambda validation return under `$.validation` using
`ResultPath`. The original workflow input retains `trade` and
`idempotency_key`; `OutputPath` is omitted so its default `$` passes the
combined state to `IsTradeValid`.

Evidence:

- `step-functions/trade-validation-with-task.asl.json` adds
  `"InputPath": "$.trade"` and preserves `"ResultPath": "$.validation"`, the
  existing Lambda ARN, and the transition to `IsTradeValid`;
- `tests/test_step_functions_validation_contract.py` verifies those four
  contract fields and Task type using the parsed ASL definition;
- learner-supplied focused pytest result: **1 passed in 0.01s**;
- learner-supplied full regression: **249 passed in 0.22s**; Ruff
  `All checks passed!`; `git diff --check` returned no errors.

Key learning: `InputPath` selects data sent to a Task, `ResultPath` inserts
or replaces the Task result within the original state input, and `OutputPath`
selects the state output. A direct Lambda ARN returns the handler's value;
the optimised `lambda:invoke` integration instead exposes it under `Payload`.

Limits: The test structurally verifies ASL fields; it neither executes the
state machine nor independently validates AWS runtime JSON transformations.
There is no live AWS execution or deployment. No Lesson 41 Choice-state change
or Lesson 43 registry integration is claimed. **Next:** original Lesson 41 —
Choice + validation path.

### Early Lesson 43 — DynamoDB registry (not complete)

Status: **Partial, locally tested**. `submission_registry.py` implements
conditional `PutItem`, strongly consistent `GetItem` fingerprint classification
and conditional `STARTING` to `START_CONFIRMED` `UpdateItem`.
Learner-supplied terminal evidence: **11 registry tests passed; 249 total
tests passed**. Commits `a79e5f2` and `b430757` were pushed to `origin/main`.
No end-to-end duplicate handling, durable execution identity, recovery worker
or live AWS service guarantees have been demonstrated. Resume this registry
work at original Lesson 43; the next active lesson is 41.

## Parked Topics

- Docker and container packaging
- AI orchestration
- polished UI work
- complex microservices
- production deployment automation beyond a deliberately approved lesson

## Relationship to Employability and AWS/AI Competence

SAP-C02 has been passed. The programme now builds on that architectural
foundation to develop practical Python, AWS and AI engineering competence
that can be demonstrated through working software, troubleshooting,
technical explanations and credible portfolio evidence.

Choose learning tasks for the capabilities they develop and the evidence
they produce. Historical SAP-C02 domain mappings remain useful context;
exam-readiness tracking no longer controls progression.

| Focus | Demonstrable capability |
| --- | --- |
| Python engineering | Independently write, test, debug and explain small, maintainable programs |
| AWS serverless engineering | Build service integrations with explicit contracts, configuration, persistence and failure handling |
| Secure and reliable operation | Explain and test IAM boundaries, retries, idempotency, observability and recovery |
| Applied AI engineering | Integrate model APIs, validate outputs, evaluate quality, handle failures and manage data exposure, latency and cost |
| Employability evidence | Present reproducible projects, explain design trade-offs and diagnose realistic failures |

Lessons 38–45 remain the current serverless foundation. Any change to their
sequence must identify the affected lesson, rationale, delayed work and
planned point of resumption. Applied AI should follow an explicit learning
stage with prerequisites and completion criteria.

Progress is demonstrated by increasing independence: implementing a small
requirement, testing meaningful failure cases, diagnosing defects and
explaining the resulting design. Completing guided exercises alone does
not establish job readiness.

Evidence must distinguish conceptual understanding, locally tested
behaviour and live AWS operation. Controlled deployment exercises require
explicit approval, cost limits and cleanup plans.

This tutorial remains separate from the Energy Data Lakehouse. Patterns
count as lakehouse implementation evidence only after separate adaptation,
testing and verification in that repository.
