# Police Review Feedback V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete V1 police review loop: persistent review records, versioned rule metadata, append-only manual actions, follow-up questions, whole-review completion, history/rules pages, and a printable report.

**Architecture:** Keep the existing React/FastAPI/Qwen pipeline and place a SQLAlchemy repository behind the application services. SQLite is the default local store and Alembic owns schema changes; PostgreSQL remains a connection-string change. Machine results remain immutable while manual actions are append-only and update only a query-friendly current status.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, SQLite/aiosqlite, PostgreSQL/asyncpg, Vitest, pytest, Playwright CLI.

## Global Constraints

- Real uploads continue to require the configured Qwen service; local demos remain explicitly labelled local and never masquerade as model results.
- The current rules are `0.1-working` and must be displayed as project working rules pending customer confirmation.
- Three-present/four-flows are categories, not a permanent seven-result limit; structured parsing must accept the exact IDs of the active rule set without hard-coded Pydantic fields.
- Machine status and evidence are immutable after review; each actionable result is classified as confirmed, supplemented, or ignored without requiring free text.
- V1 persists only normalized desensitized text and review data, not uploaded file bytes.
- Existing strict JSON Schema, one corrective retry, function-calling compatibility fallback, and no-partial-results behavior remain intact.
- Do not log document text, model prompts, API keys, identity numbers, phone numbers, or bank-card numbers.

---

### Task 1: Versioned rule-set contract and dynamic structured output

**Files:**
- Modify: `backend/app/data.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/qwen.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `RULE_SET_META: dict`, `RuleSetSummary`, dynamic `ModelReviewOutput.root: dict[str, ModelRuleResult]`.
- Consumes: existing `RULES` list and `structured_review_schema()`.

- [ ] **Step 1: Write failing rule metadata and dynamic-output tests**

```python
def test_rules_expose_working_rule_set_metadata():
    payload = client.get("/api/v1/rules").json()
    assert payload["ruleSet"] == {
        "id": "telecom-fraud-three-present-four-flows",
        "name": "电诈三现四流笔录审查规则",
        "version": "0.1-working",
        "status": "working",
        "source": "项目工作口径，待客户确认",
    }


def test_model_review_output_accepts_active_rule_ids_without_hard_coded_fields():
    payload = {rule["id"]: _valid_model_rule(rule) for rule in RULES}
    assert ModelReviewOutput.model_validate(payload).as_keyed_payload() == payload
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "rule_set_metadata or active_rule_ids"`

Expected: FAIL because `ruleSet` is absent and `ModelReviewOutput` still declares seven fields.

- [ ] **Step 3: Implement rule metadata and dynamic root model**

```python
RULE_SET_META = {
    "id": "telecom-fraud-three-present-four-flows",
    "name": "电诈三现四流笔录审查规则",
    "version": "0.1-working",
    "status": "working",
    "source": "项目工作口径，待客户确认",
}


class ModelReviewOutput(RootModel[dict[str, ModelRuleResult]]):
    def as_keyed_payload(self) -> dict:
        return self.model_dump(mode="json")
```

Return `ruleSet` beside `rules` and retain deterministic exact-ID validation in `_validation_payload`.

- [ ] **Step 4: Run focused and existing Qwen tests**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "health_and_rules or strict_review or qwen"`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/data.py backend/app/models.py backend/app/main.py backend/app/services/qwen.py backend/tests/test_api.py
git commit -m "feat: version review rules and parse dynamic outputs"
```

### Task 2: SQLAlchemy persistence and repository boundary

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/persistence/__init__.py`
- Create: `backend/app/persistence/entities.py`
- Create: `backend/app/repositories.py`
- Modify: `backend/app/store.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260717_01_review_v1.py`
- Create: `backend/tests/test_repository.py`

**Interfaces:**
- Produces: `ReviewRepository` protocol and `SqlAlchemyReviewRepository` methods `save_task`, `get_task`, `list_tasks`, `append_action`, `complete_review`, `reopen_review`, `report_data`.
- Consumes: Pydantic `ReviewTask`, `ReviewResult`, `ManualAction`.

- [ ] **Step 1: Add dependencies and failing repository contract tests**

Add exact dependencies:

```text
SQLAlchemy==2.0.41
alembic==1.16.1
aiosqlite==0.21.0
asyncpg==0.30.0
pytest-asyncio==0.25.3
```

Write async tests using a temporary SQLite file:

```python
@pytest.mark.asyncio
async def test_repository_persists_task_across_repository_instances(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'review.db'}"
    first = await make_repository(url)
    task = ReviewTask(mode=ReviewMode.LOCAL)
    await first.save_task(task)
    await first.dispose()

    second = await make_repository(url)
    assert (await second.get_task(task.id)).id == task.id
```

- [ ] **Step 2: Run repository tests and verify RED**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_repository.py`

Expected: FAIL because repository modules do not exist.

- [ ] **Step 3: Implement entities and repository**

Use normalized tables:

```python
class ReviewSessionEntity(Base): ...
class DocumentEntity(Base): ...
class ReviewRunEntity(Base): ...
class ReviewResultEntity(Base): ...
class ManualActionEntity(Base): ...
class RuleSetEntity(Base): ...
class RuleEntity(Base): ...
class AuditEventEntity(Base): ...
```

Store `ParsedDocument.pages`, `factCoverage`, `missingFacts`, `advisories`, rule definitions, and action details in JSON columns; store statuses, timestamps, rule/model versions, and searchable summary fields in dedicated columns. Seed `RULE_SET_META` and the current rules idempotently. Implement explicit Pydantic-to-entity and entity-to-Pydantic mapping in `repositories.py`.

- [ ] **Step 4: Implement migration and startup initialization**

Default configuration:

```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'data' / 'bilu.db').as_posix()}",
)
```

Alembic migration creates all eight tables, foreign keys, indexes on `created_at`, `status`, `review_status`, and unique constraints on `(run_id, rule_id)` and `(rule_set_id, version)`.

- [ ] **Step 5: Run migration and repository tests**

Run: `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`

Run: `cd backend && .venv\Scripts\alembic.exe -c alembic.ini upgrade head`

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_repository.py`

Expected: migration succeeds and repository tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/requirements.txt backend/app/config.py backend/app/db.py backend/app/persistence backend/app/repositories.py backend/app/store.py backend/alembic.ini backend/alembic backend/tests/test_repository.py
git commit -m "feat: persist reviews through repository boundary"
```

### Task 3: Manual-action state machine and whole-review lifecycle

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `ManualStatus`, `ManualActionType`, `ManualActionRequest`, `ManualAction`, `ReviewLifecycleStatus`.
- Produces endpoints: `POST .../actions`, `POST .../complete`, `POST .../reopen`.
- Consumes: repository methods from Task 2.

- [ ] **Step 1: Write failing state-transition API tests**

```python
def test_problem_can_be_classified_and_review_completed():
    task = _create_missing_demo()
    problem = _first_problem(task)
    queued = client.post(
        f"/api/v1/reviews/{task['id']}/results/{problem['ruleId']}/actions",
        json={"status": "supplemented", "reason": ""},
    )
    assert queued.json()["result"]["manualDecision"]["status"] == "supplemented"

    completed = client.post(f"/api/v1/reviews/{task['id']}/complete")
    assert completed.json()["reviewStatus"] == "archived"
```

Add tests rejecting completion while actionable items remain and allowing completion after every item is `confirmed`, `supplemented`, or `ignored`. Ignore may carry a preset reason label but does not require free text.

- [ ] **Step 2: Run transition tests and verify RED**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "queued_resolved or dismiss_requires or review_completed or reopen_review"`

Expected: FAIL with 404 for new endpoints.

- [ ] **Step 3: Implement state models and validation**

```python
class ManualStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SUPPLEMENTED = "supplemented"
    IGNORED = "ignored"


class ManualActionType(StrEnum):
    CONFIRM = "confirm"
    QUEUE = "queue"
    RESOLVE = "resolve"
    DISMISS = "dismiss"
    REOPEN = "reopen"
```

Validate the three terminal decisions in the service and persist the updated task. Keep the existing PATCH decision endpoint as the canonical V1 write interface.

- [ ] **Step 4: Replace direct in-memory store calls with awaited repository calls**

Convert `create_task`, `process_upload`, `process_demo`, decision handling, and task detail to use the repository. Keep background processing behavior unchanged.

- [ ] **Step 5: Run backend API tests**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py`

Expected: all prior and new API tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models.py backend/app/services/review.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat: add auditable police review actions"
```

### Task 4: Review history, rule-set, follow-up, and report APIs

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`
- Modify: `docs/openapi.json`

**Interfaces:**
- Produces endpoints: `GET /reviews`, `GET /reviews/{id}/follow-ups`, `GET /reviews/{id}/report-data`, `GET /rule-sets`, `GET /rule-sets/{id}/versions/{version}`.
- Produces models: `ReviewSummary`, `ReviewListResponse`, `FollowUpItem`, `ReportData`, `RuleSetDetail`.

- [ ] **Step 1: Write failing read-model tests**

```python
def test_review_history_lists_persisted_tasks_and_can_reopen_detail():
    task = _create_missing_demo()
    payload = client.get("/api/v1/reviews", params={"search": "样例二"}).json()
    assert any(item["id"] == task["id"] for item in payload["items"])


def test_report_data_separates_machine_result_from_manual_actions():
    task = _create_missing_demo()
    payload = client.get(f"/api/v1/reviews/{task['id']}/report-data").json()
    assert payload["ruleSet"]["version"] == "0.1-working"
    assert "machineStatus" in payload["issues"][0]
    assert "manualActions" in payload["issues"][0]
```

- [ ] **Step 2: Run read-model tests and verify RED**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "review_history or report_data or rule_set_detail or follow_ups"`

Expected: FAIL with 404.

- [ ] **Step 3: Implement list filters and read models**

History accepts `search`, `taskStatus`, `reviewStatus`, `limit`, and `offset`; default order is newest first. Follow-ups include only queued/resolved results and return the edited question plus latest answer.

- [ ] **Step 4: Implement deterministic report DTO**

Return file metadata, rule/model versions, counts, issues, evidence locations, and append-only actions. Do not generate PDF server-side.

- [ ] **Step 5: Export and verify OpenAPI**

Run: `backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py`

Run: `cd backend && .venv\Scripts\python.exe -m pytest -q tests/test_api.py`

Expected: PASS and OpenAPI contains all new endpoints.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models.py backend/app/services/review.py backend/app/main.py backend/tests/test_api.py docs/openapi.json
git commit -m "feat: expose review history and report data"
```

### Task 5: Frontend data layer and navigation

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/reviewState.ts`
- Create: `frontend/src/reviewState.test.ts`

**Interfaces:**
- Produces TypeScript models matching Task 4 and API functions `getReviewHistory`, `getReview`, `submitManualAction`, `completeReview`, `reopenReview`, `getFollowUps`, `getReportData`, `getRuleSets`.
- Produces `isActionable`, `canCompleteReview`, and manual-status labels.

- [ ] **Step 1: Write failing pure state tests**

```typescript
it("allows completion only when every actionable result is resolved or dismissed", () => {
  expect(canCompleteReview([result("missing", "confirmed"), result("incomplete", "ignored")])).toBe(true);
  expect(canCompleteReview([result("missing", "pending")])).toBe(false);
});
```

- [ ] **Step 2: Run state test and verify RED**

Run: `npm --prefix frontend run test -- reviewState.test.ts`

Expected: FAIL because `reviewState.ts` is absent.

- [ ] **Step 3: Add TanStack Query and typed clients**

Run: `npm --prefix frontend install @tanstack/react-query@5.66.8`

Wrap `<App />` in `QueryClientProvider`. Add typed request/response functions; keep upload polling behavior until it is safely migrated.

- [ ] **Step 4: Replace reserved navigation with real views**

Extend view state to `new | result | workflow | history | rules | report`; remove “预留” chips and route history/rules buttons to actual components created in later tasks.

- [ ] **Step 5: Run frontend unit tests and build**

Run: `npm --prefix frontend run test`

Run: `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/main.tsx frontend/src/types.ts frontend/src/api.ts frontend/src/App.tsx frontend/src/reviewState.ts frontend/src/reviewState.test.ts
git commit -m "feat: add review workflow data layer"
```

### Task 6: Police feedback controls and follow-up drawer

**Files:**
- Create: `frontend/src/components/DecisionPanel.tsx`
- Create: `frontend/src/components/FollowUpDrawer.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/decisionForm.ts`
- Create: `frontend/src/decisionForm.test.ts`

**Interfaces:**
- Consumes: `submitManualAction`, current `ReviewResult`, and task-wide results.
- Produces: one-click confirm, add-to-list, and ignore actions; copy-one and copy-all behavior.

- [ ] **Step 1: Write failing form-validation tests**

```typescript
it("treats all three decisions as handled", () => {
  expect(isHandled("confirmed")).toBe(true);
  expect(isHandled("supplemented")).toBe(true);
  expect(isHandled("ignored")).toBe(true);
});
```

- [ ] **Step 2: Run validation tests and verify RED**

Run: `npm --prefix frontend run test -- decisionForm.test.ts`

Expected: FAIL because validation module is absent.

- [ ] **Step 3: Implement action forms**

Use explicit verb buttons: `确认问题`, `加入补问清单`, `忽略`. None requires text entry. Ignore may expose optional preset reason labels. Reopening changes the whole-review status without deleting decisions.

- [ ] **Step 4: Implement follow-up drawer and whole-review controls**

Show supplemented items with copy-one/copy-all behavior, and a disabled “完成本次复核” button with the remaining unclassified count. Completion automatically archives the review.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components frontend/src/App.tsx frontend/src/styles.css frontend/src/decisionForm.ts frontend/src/decisionForm.test.ts
git commit -m "feat: close the police follow-up workflow"
```

### Task 7: History, read-only rules, and printable report pages

**Files:**
- Create: `frontend/src/views/HistoryView.tsx`
- Create: `frontend/src/views/RuleSetsView.tsx`
- Create: `frontend/src/views/ReportView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/reportFormat.ts`
- Create: `frontend/src/reportFormat.test.ts`

**Interfaces:**
- History opens a selected task back into `ResultView`.
- Rules view consumes versioned rule metadata and displays a working-rule warning.
- Report view consumes `ReportData` and calls `window.print()`.

- [ ] **Step 1: Write failing report formatting tests**

```typescript
it("labels machine and manual conclusions separately", () => {
  expect(formatIssue(issue).machineLabel).toBe("明确遗漏");
  expect(formatIssue(issue).manualLabel).toBe("已记录补问结果");
});
```

- [ ] **Step 2: Run test and verify RED**

Run: `npm --prefix frontend run test -- reportFormat.test.ts`

Expected: FAIL because formatter is absent.

- [ ] **Step 3: Implement history and rule-set pages**

History shows file, created time, task/review status, pending count, rule version, model name, and an “查看” action. Rules are read-only and clearly marked `工作规则，待客户确认`.

- [ ] **Step 4: Implement printable report**

Render file metadata, counts, rule/model versions, each machine result, evidence, suggested question, manual actions, and the disclaimer. Add `@media print` rules that remove navigation/buttons and use A4-friendly typography.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/views frontend/src/reportFormat.ts frontend/src/reportFormat.test.ts frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: add review records rules and printable report"
```

### Task 8: End-to-end verification, documentation, and semantic verifier preparation

**Files:**
- Modify: `backend/scripts/verify_qwen.py`
- Create: `backend/tests/golden_reviews.json`
- Modify: `README.md`
- Modify: `docs/product-requirements-v0.1.md`
- Modify: `docs/superpowers/specs/2026-07-16-police-review-feedback-v1-design.md`

**Interfaces:**
- Produces: offline structural verification now and semantic Qwen verification when connected to company intranet.

- [ ] **Step 1: Add golden expectations for three demo documents**

Store expected statuses, required missing facts, and allowed evidence locations per rule. The verifier reports `ruleAccuracy`, `falsePositiveCount`, `missedRuleCount`, and `invalidEvidenceCount` without printing document text.

- [ ] **Step 2: Add API and browser regression coverage**

Backend test path:

```text
create demo -> queue finding -> resolve finding -> dismiss remaining findings
-> complete review -> list history -> reopen detail -> fetch report
```

Browser path:

```text
open demo -> locate evidence -> add follow-up -> record answer
-> complete -> history -> reopen -> print view -> rules view
```

- [ ] **Step 3: Update documentation**

Document database location, Alembic commands, persistence/security boundary, manual states, new API routes, working-rule disclaimer, report behavior, and company-intranet model verification.

- [ ] **Step 4: Run full verification**

Run: `npm run test`

Run: `npm run build`

Run when outside intranet: `npm run verify:model` and confirm the only accepted failure is `model_unreachable` with no leaked secrets.

Run when inside intranet: `npm run verify:model` and require `status=completed`, exact active rule count, and semantic metrics in the configured acceptance range.

- [ ] **Step 5: Perform Playwright CLI browser QA**

Start: `npm run dev`

Verify at `http://127.0.0.1:4173/` using Microsoft Edge: complete the browser path above, check zero console errors, and capture screenshots under `output/playwright/`.

- [ ] **Step 6: Commit**

```powershell
git add backend/scripts/verify_qwen.py backend/tests/golden_reviews.json README.md docs/product-requirements-v0.1.md docs/superpowers/specs/2026-07-16-police-review-feedback-v1-design.md
git commit -m "docs: finalize police review feedback v1"
```

## Completion Audit

- [ ] Every requirement in `docs/superpowers/specs/2026-07-16-police-review-feedback-v1-design.md` maps to a task above.
- [ ] No `TODO`, `TBD`, placeholder endpoint, reserved navigation item, or unimplemented V1 button remains.
- [ ] Machine results are not overwritten by manual actions.
- [ ] SQLite survives process restart and the same repository contract can target PostgreSQL.
- [ ] New migrations apply to an empty database.
- [ ] Existing parser, strict schema, retry, evidence, and no-partial-results tests remain green.
- [ ] Frontend unit tests, backend tests, TypeScript build, Python compile, and browser flow pass.
- [ ] Model unreachability outside the company network is reported as an environment limitation, not a product failure.
