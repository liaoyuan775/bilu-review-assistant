# Review Results Demo and Localized Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Localize user-facing fact paths in PDF/DOCX, show unresolved issues before passed rules with risk cues, and add per-item plus one-click demo pass actions for built-in demo tasks.

**Architecture:** Add a backend presentation helper for Chinese fact labels and deterministic result ordering, then consume it from both artifact generators. Add an optional persisted `demoId` to distinguish built-in demos, a guarded bulk demo-pass endpoint, and frontend presentation sections/actions driven by pure state helpers.

**Tech Stack:** FastAPI, Pydantic, python-docx, ReportLab, React 19, TypeScript, Vitest, pytest.

## Global Constraints

- Do not modify uploaded originals.
- Do not change structured JSON or archive-manifest schemas.
- Keep persisted status values and English fact-path keys unchanged.
- Show demo shortcuts only when `ReviewTask.demoId` is non-null.
- Never bypass failed extraction domains or automatic archive validation.
- Preserve unrelated dirty working-tree and staged changes; do not commit implementation files automatically.

---

### Task 1: Chinese report presentation

**Files:**
- Create: `backend/app/reporting/presentation.py`
- Create: `backend/tests/test_report_presentation.py`
- Modify: `backend/app/reporting/reports.py`
- Modify: `backend/app/reporting/docx_report.py`
- Modify: `backend/tests/test_reports.py`

**Interfaces:**
- Produces: `fact_label(path: str) -> str`
- Produces: `localize_fact_paths(text: str) -> str`
- Produces: `sort_review_results(results: Iterable[ReviewResult]) -> list[ReviewResult]`
- Consumed by both PDF and DOCX generators.

- [ ] **Step 1: Write failing presentation tests**

Add tests equivalent to:

```python
def test_fact_labels_cover_static_and_repeated_fields():
    assert fact_label("money.net_loss") == "净损失"
    assert fact_label("transfer_001.transaction_id") == "第1笔转账交易流水号"
    assert fact_label("withdrawals.count") == "取款记录数量"
    assert fact_label("unknown.path") == "unknown.path"

def test_localize_fact_paths_replaces_paths_inside_reason():
    assert localize_fact_paths("缺少 money.net_loss、transfer_001.transaction_id。") == "缺少 净损失、第1笔转账交易流水号。"

def test_result_order_is_open_closed_not_applicable_covered():
    ordered = sort_review_results([covered, not_applicable, closed_issue, low_open, high_open])
    assert [item.ruleId for item in ordered] == ["HIGH", "LOW", "CLOSED", "NA", "OK"]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_report_presentation.py tests\test_reports.py -q
```

Expected: import or assertion failures because the presentation helper and localized output do not exist.

- [ ] **Step 3: Implement the presentation helper**

Create a pure module containing the complete static fact-label catalog currently used by `frontend/src/ruleLabels.ts`, dynamic labels for entity counts and indexed entity fields, regex replacement for embedded paths, and ordering keys:

```python
_SECTION = {"open": 0, "closed": 1, "not_applicable": 2, "covered": 3}
_SEVERITY = {"high": 0, "medium": 1, "low": 2}
_STATUS = {"missing": 0, "inconsistent": 1, "incomplete": 2, "needs_manual_review": 3}
```

Treat `resolved`, `not_applicable`, and `ignored` with non-empty reasons as closed. Treat `pending`, `supplemented`, and historical `confirmed` as open.

- [ ] **Step 4: Apply localization and ordering to PDF/DOCX**

In both generators iterate over `sort_review_results(task.results)`. Pass `item.reason` through `localize_fact_paths`, and pass every `missingFacts` entry through `fact_label`. Keep rule IDs, task IDs, model names, filenames, JSON and manifests unchanged.

- [ ] **Step 5: Verify GREEN**

Run the focused backend command again. Expected: all selected tests pass and generated PDF/DOCX text contains Chinese field names before passed results.

---

### Task 2: Problem-first frontend sections and risk cues

**Files:**
- Modify: `frontend/src/templateReviewState.ts`
- Modify: `frontend/src/templateReviewState.test.ts`
- Modify: `frontend/src/TemplateReviewView.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appCopy.test.ts`

**Interfaces:**
- Produces: `sectionTemplateResults(results: ReviewResult[]): ReviewResultSection[]`
- Produces section keys: `open`, `closed`, `not_applicable`, `covered`.
- Consumes: existing `isManualDecisionClosed(result)`.

- [ ] **Step 1: Write failing section-order tests**

Add assertions that mixed input produces sections in this exact order and that open items are sorted high, medium, low before status priority:

```ts
expect(sectionTemplateResults(mixed).map((section) => section.key)).toEqual([
  "open", "closed", "not_applicable", "covered",
]);
expect(sections[0].groups.flatMap((group) => group.results.map((item) => item.ruleId))).toEqual([
  "HIGH-MISSING", "MEDIUM-INCONSISTENT", "LOW-INCOMPLETE",
]);
```

Add copy-contract assertions for “待处理问题”, “已闭环问题”, “补问中”, “高风险”, “中风险”, and “低风险”.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run from `frontend`:

```powershell
npm test -- --run src/templateReviewState.test.ts src/appCopy.test.ts
```

Expected: failures because sections and the new labels do not exist.

- [ ] **Step 3: Implement pure sectioning**

Return only non-empty sections. Within each section preserve business groups, but order groups by the first sorted result so no covered item can precede an issue from another group.

- [ ] **Step 4: Render sections and status badges**

Replace the single `groups.map` with section headings and nested business groups. Add article classes derived from section and severity. Show:

```text
pending / confirmed -> 待处理
supplemented        -> 补问中
closed terminal     -> 已闭环
```

Show severity badges for all actionable issues, not only high-risk ones.

- [ ] **Step 5: Add restrained risk styling**

Use left borders plus pale backgrounds: high red, medium orange, low yellow, supplemented blue, closed green, automatic not-applicable gray, and covered green. Keep explicit text labels so color is not the sole signal.

- [ ] **Step 6: Verify GREEN and build**

Run:

```powershell
npm test -- --run src/templateReviewState.test.ts src/appCopy.test.ts
npm run build
```

Expected: focused tests pass and TypeScript/Vite build exits 0.

---

### Task 3: Guarded demo identity and bulk pass API

**Files:**
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/review/review.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_review_lifecycle.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Adds: `ReviewTask.demoId: str | None = None`
- Adds: `pass_demo_review(task_id: str) -> ReviewTask`
- Adds endpoint: `POST /api/v1/reviews/{task_id}/demo-pass -> ReviewTask`

- [ ] **Step 1: Write failing lifecycle and API tests**

Add concrete tests with these arrangements and assertions:

```python
def test_demo_task_records_demo_id(client):
    response = client.post("/api/v1/reviews/demos/case-01-baseline", json={})
    assert response.status_code == 200
    assert response.json()["demoId"] == "case-01-baseline"


def test_bulk_demo_pass_generates_artifacts_and_leaves_archive_ready(client):
    created = client.post("/api/v1/reviews/demos/case-05-five-status", json={}).json()
    response = client.post(f"/api/v1/reviews/{created['id']}/demo-pass")
    assert response.status_code == 200
    task = response.json()
    actionable = {"missing", "incomplete", "inconsistent", "needs_manual_review"}
    handled = [item for item in task["results"] if item["status"] in actionable]
    assert handled
    assert all(item["action"] == "resolved" for item in handled)
    assert all(item["reason"] == "脱敏演示：一键测试通过" for item in handled)
    assert set(task["acknowledgedWarnings"]) == {
        warning["code"] for warning in task["documentWarnings"]
    }
    assert {artifact["type"] for artifact in task["artifacts"]} >= {
        "review_pdf", "follow_up_docx", "structured_json", "archive_manifest"
    }
    archived = client.post(f"/api/v1/reviews/{created['id']}/archive")
    assert archived.status_code == 200


def test_bulk_demo_pass_rejects_normal_upload(client, sample_docx):
    created = upload_review(client, sample_docx)
    response = client.post(f"/api/v1/reviews/{created['id']}/demo-pass")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "demo_action_not_allowed"


def test_bulk_demo_pass_rejects_failed_domains(client):
    created = client.post("/api/v1/reviews/demos/case-05-five-status", json={}).json()
    force_domain_failure(created["id"], "content")
    response = client.post(f"/api/v1/reviews/{created['id']}/demo-pass")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "demo_has_failed_domains"
```

Add a lifecycle-level test for the same mutation to assert it saves once, records one
`demo-operator` audit event per changed issue, acknowledges warning codes, and invalidates
previous generated artifacts. Reuse the repository's existing upload and store helpers in
place of the descriptive `upload_review` and `force_domain_failure` names above.

- [ ] **Step 2: Run focused backend tests and verify RED**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_review_lifecycle.py tests\test_api.py -q
```

Expected: failures because `demoId`, bulk mutation, and route do not exist.

- [ ] **Step 3: Persist demo identity**

Extend `create_task` with an optional `demo_id` argument and set `demoId=demo_id`. `create_demo_review` passes its whitelist ID; `create_upload_review` uses the default `None`. Existing SQLite payloads remain valid through the Pydantic default.

- [ ] **Step 4: Implement guarded bulk mutation**

`pass_demo_review` validates existence, `demoId`, completion, mutability, and no failed domains. In one save operation it resolves every non-terminal actionable result, records one event per changed issue with actor `demo-operator`, acknowledges all document warning codes with an audit event, and invalidates old generated artifacts.

- [ ] **Step 5: Add the one-click route**

The route calls `pass_demo_review(task_id)` and then `generate_review_artifacts(task_id)`. If generation fails, return the generation error while retaining the auditable resolved decisions, allowing manual regeneration.

- [ ] **Step 6: Verify GREEN**

Run the focused backend command again. Expected: all selected lifecycle and API tests pass.

---

### Task 4: Frontend per-item and one-click demo actions

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/TemplateReviewView.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appCopy.test.ts`

**Interfaces:**
- Consumes: `ReviewTask.demoId`.
- Adds API client: `passDemoReview(taskId: string): Promise<ReviewTask>`.
- Adds view callback: `onDemoPassAll(): Promise<void>`.

- [ ] **Step 1: Write failing frontend contracts**

Assert the component contains “测试通过”, “一键测试通过”, `task.demoId`, and `onDemoPassAll`, while production behavior is guarded by `Boolean(task.demoId)`.

- [ ] **Step 2: Run focused test and verify RED**

Run:

```powershell
npm test -- --run src/appCopy.test.ts
```

Expected: copy-contract test fails because demo actions are absent.

- [ ] **Step 3: Add API and task typing**

Add optional `demoId: string | null` to `ReviewTask` and a POST client for `/demo-pass`. Keep old task fixtures valid by making the field optional on the TypeScript side.

- [ ] **Step 4: Add the single-item action**

For demo tasks only, unresolved actionable cards show a secondary “测试通过” button. It calls existing `onAction(ruleId, "resolved", "脱敏演示：测试通过")`. Formal tasks and archived tasks never render it.

- [ ] **Step 5: Add the one-click action**

For demo tasks only, the header shows “一键测试通过”. Disable it while running. `App` calls `passDemoReview`, replaces task state with the returned artifact-complete task, selects the next remaining issue if any, and shows a success or API error toast. The endpoint does not archive automatically.

- [ ] **Step 6: Run complete automated verification**

Run once:

```powershell
Set-Location frontend
npm test -- --run
npm run build
Set-Location ..\backend
.\.venv\Scripts\python.exe -m pytest tests\test_report_presentation.py tests\test_reports.py tests\test_review_lifecycle.py tests\test_api.py -q
```

Expected: all selected tests pass; frontend build exits 0.

- [ ] **Step 7: Browser and artifact QA**

Start the local development environment and use the built-in five-status demo. Verify at 1600×900 and 1366×768:

- open high/medium/low issues appear before closed, not-applicable, and covered sections;
- risk and processing labels are readable with no horizontal overflow;
- per-item “测试通过” closes one issue;
- “一键测试通过” closes the remainder, generates artifacts, and enables archive;
- downloaded PDF and DOCX contain Chinese fact labels and problem-first ordering;
- no browser console errors occur.

Stop the development environment and confirm ports 4178/8790 are no longer listening.
