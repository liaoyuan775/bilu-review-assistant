# Review Result Action Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ambiguous universal review actions with status-specific actions, require every actionable result to be closed before archive, and provide a user-facing quick-start guide.

**Architecture:** Put all frontend action labels and closure semantics in a pure `reviewActionPolicy` module consumed by the review page and archive gate. Keep automatic `RuleStatus` unchanged and store human outcomes in the existing `ManualStatus`; align the backend archive validator with the same three terminal outcomes.

**Tech Stack:** React 19, TypeScript, Vitest, FastAPI, Pydantic, pytest.

## Global Constraints

- Do not change automatic rule evaluation or overwrite `RuleStatus` with a manual decision.
- Keep backend support for historical `confirmed` decisions, but do not expose a new `confirmed` action in the review UI.
- Terminal decisions are `resolved`, `not_applicable`, and `ignored` with a non-empty reason.
- All `missing`, `incomplete`, `inconsistent`, and `needs_manual_review` results must be terminal before archive.
- Preserve unrelated working-tree changes.

---

### Task 1: Frontend action policy

**Files:**
- Create: `frontend/src/reviewActionPolicy.ts`
- Create: `frontend/src/reviewActionPolicy.test.ts`

**Interfaces:**
- Produces: `reviewActionPolicy(status: RuleStatus): ReviewActionPolicy | null`
- Produces: `isManualDecisionClosed(result: ReviewResult): boolean`
- Produces: `manualDecisionLabel(result: ReviewResult): string`

- [x] **Step 1: Write the failing policy tests**

Cover the status-specific primary labels, absence of actions for `covered` and automatic `not_applicable`, `resolved` secondary actions only for incomplete/inconsistent results, and terminal-state evaluation.

- [x] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --run src/reviewActionPolicy.test.ts`

Expected: FAIL because `reviewActionPolicy.ts` does not exist.

- [x] **Step 3: Implement the minimal pure policy**

Define exact status policies:

```ts
missing: { primaryLabel: "补问并重审", secondary: ["not_applicable", "ignored"] }
incomplete: { primaryLabel: "补问并重审", secondary: ["resolved", "not_applicable", "ignored"] }
inconsistent: { primaryLabel: "核实并重审", secondary: ["resolved", "not_applicable", "ignored"] }
needs_manual_review: { primaryLabel: "确认适用并补问", secondary: ["not_applicable", "ignored"] }
```

Map `resolved` to “接受现有回答” for incomplete and “确认以现有材料为准” for inconsistent. Map `ignored` to “不处理并说明”.

- [x] **Step 4: Run the focused test and verify GREEN**

Run: `npm test -- --run src/reviewActionPolicy.test.ts`

Expected: PASS.

### Task 2: All-actionable archive gate

**Files:**
- Modify: `frontend/src/templateReviewState.ts`
- Modify: `frontend/src/templateReviewState.test.ts`
- Modify: `backend/app/reporting/archive.py`
- Modify: `backend/tests/test_review_lifecycle.py`

**Interfaces:**
- Consumes: `isManualDecisionClosed(result)` from Task 1.
- Changes frontend blocker code from `pending_high_risk` to `unresolved_issues`.
- Changes backend error from `archive_pending_high_risk` to `archive_pending_issues`.

- [x] **Step 1: Write failing frontend and backend tests**

Assert that low-, medium-, and high-risk actionable results in `pending`, `supplemented`, or `confirmed` block archive, while `resolved`, `not_applicable`, and `ignored` with a reason do not.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```powershell
Set-Location frontend
npm test -- --run src/templateReviewState.test.ts
Set-Location ..\backend
.\.venv\Scripts\python.exe -m pytest tests/test_review_lifecycle.py -q
```

Expected: new assertions fail because the existing gate checks only high-risk results.

- [x] **Step 3: Implement aligned closure checks**

Frontend uses the shared policy helper for every actionable result. Backend applies the same rule directly to every actionable result and returns “仍有 N 个问题未闭环，不能归档。”

- [x] **Step 4: Run focused tests and verify GREEN**

Run the same two focused commands. Expected: PASS.

### Task 3: Status-specific review actions

**Files:**
- Modify: `frontend/src/TemplateReviewView.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appCopy.test.ts`

**Interfaces:**
- Consumes: `reviewActionPolicy`, `isManualDecisionClosed`, and `manualDecisionLabel` from Task 1.
- Continues to call existing `onAction(ruleId, status, reason)` and `onFollowUp(...)` props.

- [x] **Step 1: Add failing copy-contract assertions**

Assert the production review page no longer contains the visible action “确认问题” and does contain “推荐处理”, “不处理并说明”, and the status-specific primary labels.

- [x] **Step 2: Run the copy test and verify RED**

Run: `npm test -- --run src/appCopy.test.ts`

Expected: FAIL because the old universal buttons remain.

- [x] **Step 3: Render policy-driven actions**

For each actionable result:

- show a recommendation sentence;
- show the policy primary button, saving `supplemented` and opening the follow-up panel;
- show only allowed secondary actions;
- require an entered reason for `resolved`, `not_applicable`, and `ignored`;
- show the current manual-decision label and whether it is closed;
- show no actions for `covered`, automatic `not_applicable`, or archived tasks.

Keep automatic status counters unchanged and rename the archive gate text to “未闭环问题”. Add focused CSS only for the recommendation and disposition strip.

- [x] **Step 4: Run the copy test and frontend build**

Run:

```powershell
npm test -- --run src/appCopy.test.ts
npm run build
```

Expected: PASS and build exit code 0.

### Task 4: Quick-start documentation

**Files:**
- Create: `docs/review-result-actions-quick-start.md`

**Interfaces:**
- Documents the exact labels and state transitions implemented in Tasks 1-3.

- [x] **Step 1: Write the guide**

Include the five automatic categories, exact available actions, decision examples, resulting manual state, effect on top counters, follow-up list behavior, artifact invalidation, archive prerequisites, and post-archive read-only behavior.

- [x] **Step 2: Verify the guide against source**

Run:

```powershell
rg -n "补问并重审|核实并重审|确认适用并补问|接受现有回答|确认以现有材料为准|确认不适用|不处理并说明|未闭环问题" frontend/src docs/review-result-actions-quick-start.md
```

Expected: every user-facing action appears in both policy/UI evidence and the guide where applicable.

### Task 5: Completion verification

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Confirms the complete objective and the design specification.

- [x] **Step 1: Run frontend tests and build once**

Run:

```powershell
Set-Location frontend
npm test -- --run
npm run build
```

Expected: all tests pass and build exits 0.

- [x] **Step 2: Run targeted backend lifecycle tests once**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_review_lifecycle.py tests/test_api.py -q
```

Expected: all selected tests pass.

- [x] **Step 3: Audit the diff**

Confirm every changed line traces to action policy, archive closure, UI feedback, tests, or quick-start documentation, and that unrelated dirty files were not modified.
