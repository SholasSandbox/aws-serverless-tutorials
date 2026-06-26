# Learning Summary

---

### Lessons 1-24: Foundation recap from repository evidence

Status: **Reconstructed from the current repository state on 2026-06-25**.

The early lesson-by-lesson boundaries are not fully preserved in Git history,
so this recap is based on the tutorial source, tests, Step Functions artifacts,
and the pre-Lesson-25 baseline recorded in `LEARNING-PLAN.md`.

**Evidence:**

- Early Lambda response handling is still visible in
  `lesson_1_lambda_response.py`, and its production-shaped successor is
  `trade_handler.py`.
- `tests/test_trade_handler.py` shows the foundation lessons covered JSON body
  parsing, required-field checks, positive numeric `volume_mwh` validation,
  stable success/error responses, request-id fallback, and 500 handling for
  unexpected helper failures.
- `eventbridge_trade_handler.py` and
  `tests/test_eventbridge_trade_handler.py` show the same validation rules
  applied to EventBridge events, with `event.id` reused as the correlation id.
- `sqs_trade_handler.py` and `tests/test_sqs_trade_handler.py` show the SQS
  lessons separated non-retryable bad payloads from retryable persistence
  failures and returned partial batch failure responses only for retryable
  record errors.
- `step_functions_validate_trade_handler.py`,
  `step-functions/trade-validation-basic.asl.json`,
  `step-functions/trade-validation-with-task.asl.json`, and
  `step-functions/trade-validation-with-retry-catch.asl.json` show the Step
  Functions lessons progressed from a basic Choice workflow to Lambda task
  integration, `ResultPath`, retry, catch, and terminal fail-state behavior.
- `trade_result_persistence.py`, `trade_status_persistence.py`,
  `trade_persistence_workflow.py`, and their tests show the persistence lessons
  introduced accepted/rejected artifact schemas, deterministic partition-style
  S3 keys, DynamoDB status records, artifact-to-status consistency checks, and
  a stable workflow output contract.
- The pre-Lesson-25 baseline in `LEARNING-PLAN.md` records that the full local
  suite had already reached 152 passing tests on 2026-06-13 before the later
  retry/idempotency lessons were added.

**Key learnings:**

- Validate inputs at the event boundary first, then return small stable
  contracts that later handlers and workflows can trust.
- Reuse a few focused helpers such as required-field checks and numeric
  validation across API, EventBridge, SQS, and Step Functions handlers instead
  of rewriting the same logic per trigger.
- Treat malformed caller input and transient downstream failure differently:
  reject bad payloads directly, but surface retryable operational failures in a
  way the platform can retry safely.
- Make workflow state explicit. `ResultPath`, choice conditions, retry rules,
  and catch targets should all be visible and testable rather than implied.
- Keep persistence deterministic. Stable artifact shapes, sanitized S3 keys,
  and validated status-record schemas make repeat runs easier to reason about.
- Prefer dependency injection and mocked AWS clients for local-first learning so
  behavior can be tested without deploying cloud resources.

**Cross-trigger similarities:**

- API-style Lambda, EventBridge, SQS, and Step Functions handlers all depend on
  the same core business checks: required fields, valid numeric
  `volume_mwh`, and stable success or rejection contracts.
- All four patterns benefit from small reusable validation helpers instead of
  embedding business rules separately in each trigger path.
- All four need correlation-friendly identifiers in logs or responses so a
  single trade can be traced across distributed components.
- All four become easier to reason about when validation is kept separate from
  persistence and orchestration side effects.

**Cross-trigger differences that matter architecturally:**

| Trigger | Main input shape | Success contract | Failure model | Architectural takeaway |
|---|---|---|---|---|
| API-style Lambda | API Gateway-style event with JSON body and request context | HTTP-style `statusCode` plus JSON body | Bad input returns immediate `400`; unexpected code paths return `500` | Best fit when a caller needs synchronous validation feedback and a stable request-response contract |
| EventBridge handler | Event envelope with `detail` payload and event `id` | Domain result object with `status`, `request_id`, and copied trade | Invalid event detail is rejected in-handler; no batch retry contract is modeled here | Best fit for loosely coupled event distribution where producers and consumers should stay decoupled |
| SQS handler | Batched `Records` with per-message body and `messageId` | `batchItemFailures` list | Bad payloads are treated as non-retryable and logged; persistence failures are surfaced as retryable per-record failures | Best fit when buffering, back-pressure control, and selective redelivery matter |
| Step Functions task handler | Workflow task input plus ASL-managed state transitions | Structured validation result stored under `ResultPath` for later states | Retry, catch, and terminal fail-state behavior are defined explicitly in the workflow contract | Best fit when the system needs visible orchestration, branching, retries, and recovery paths across multiple steps |

**Why this differentiation matters:**

- These are classic SAP-C02 service-selection decisions: when to choose a
  synchronous API path, an event bus, a queue, or an explicit workflow
  orchestrator.
- The same trade validation rules do not imply the same runtime behavior. The
  trigger decides whether the right response is an HTTP error, a rejected event
  record, a selective batch retry, or a workflow branch.
- Service choice changes the failure boundary. SQS pushes you toward
  per-record retry semantics, Step Functions pushes you toward explicit state
  and recovery design, and API-style flows push you toward immediate caller
  feedback.
- This is the real architectural lesson behind the repo: choosing between API,
  EventBridge, SQS, and Step Functions is less about syntax and more about
  coupling, retry ownership, observability, and operational recovery.

**Weak area noted:**

- Lessons 1-24 are recoverable as capabilities and tests, but not all of the
  original lesson boundaries were written down as separate summary entries at
  the time; only the early `lesson_1*` artifacts and Step Functions Lessons
  16-18 still expose explicit lesson numbering in the repo.

SAP-C02 mapping: Domain 2 integration, workflow design, and resilience;
Domain 3 operational excellence, validation, and testable improvement.
This is Python/serverless tutorial evidence only. It is not Energy Data
Lakehouse implementation evidence.

---

### Lesson 25: Step Functions Retry/Catch for persistence task failure

Completed local-first Step Functions Retry/Catch contract for the persistence Lambda task.

**Evidence:**

- Added `step-functions/persistence-task-state-with-retry-catch.json`
- Added `tests/test_step_functions_persistence_retry_catch_contract.py`
- Verified transient Lambda and timeout errors are retried
- Verified retry behavior uses bounded backoff
- Verified caught failures are stored under `$.persistence_error`
- Verified failures route to `PersistenceFailed`
- Verified `PersistenceFailed` is a terminal `Fail` state
- Full local suite passed: 163 tests passed

No AWS resources deployed.

---

### Lesson 26: Idempotency and duplicate persistence protection

Completed local-first idempotency tests for the persistence workflow.

**Evidence:**

- Added conditional DynamoDB write protection using
  `ConditionExpression="attribute_not_exists(trade_id)"`.
- Added a test proving duplicate conditional-check failure can return
  idempotent success.
- Added a test proving unexpected DynamoDB errors are not swallowed.
- Added an S3 key determinism test using `build_s3_key`.
- Added a workflow retry test proving repeated successful execution returns
  the same compact persistence response.
- Full local suite passed: 168 tests passed.

**Caveat:**

- Duplicate handling is currently tested at `persist_trade_status_record`
  through an injected fake conditional-check exception.
- The full workflow does not yet inject a real DynamoDB conditional-check
  exception type.
- No AWS resources deployed.

This is Python/serverless tutorial evidence mapped to SAP-C02 Domain 2
resilience and Domain 3 continuous improvement. It is not Energy Data
Lakehouse implementation evidence.

---

### Lesson 27: Consolidation review

Completed a focused consolidation pass across the tutorial workspace.

**Evidence:**

- Confirmed all public function names remain consistent with their module
  contracts; no renames required.
- Cleaned small formatting and import-order issues across source and test
  files.
- Removed dead commented code from `conftest.py` and deleted the empty
  `archive/json` artifact.
- Updated `README.md` to reflect the repository's intentional Git baseline.
- Full local suite passed: 168 tests passed.

**Weak area noted:**

- `lesson_1a_lambda_response.py` remains an incomplete early-lesson artifact
  and would fail if executed directly.

This is Python/serverless tutorial evidence mapped to SAP-C02 Domain 3
operational excellence. It is not Energy Data Lakehouse implementation
evidence.

---

### Lesson 28: Persistence handler boundary hardening

Completed production-shape hardening for the persistence Lambda boundary.

**Evidence:**

- Rewrote `trade_persistence_handler.py` with strict input validation, typed
  internal helpers, and structured error responses.
- Preserved a clean separation between the Lambda boundary and the workflow
  layer.
- Added 36 tests covering malformed event shapes, missing required fields,
  unexpected workflow exceptions, and workflow result pass-through.
- Full local suite passed: 204 tests passed.

This is Python/serverless tutorial evidence mapped to SAP-C02 Domain 3
operational excellence and Domain 2 resilience. It is not Energy Data
Lakehouse implementation evidence.

---

### Ruff formatting baseline

Completed a consistent formatting baseline across the tutorial workspace.

**Evidence:**

- Added `ruff` to `pyproject.toml` dev dependencies.
- Applied consistent style across all 20 tutorial source and test files.
- Full local suite passed: 204 tests passed with no behavior changes.

This is Python/serverless tutorial evidence mapped to SAP-C02 Domain 3
operational excellence. It is not Energy Data Lakehouse implementation
evidence.
