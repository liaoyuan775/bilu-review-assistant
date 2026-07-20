# Rule Not Applicable Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the user-facing automatic `not_applicable` status to “规则不适用” without changing persisted values or manual action copy.

**Architecture:** Keep the domain enum and workflow unchanged. Update only presentation mappings in the frontend and report generators, with copy-contract tests preventing accidental changes to the manual “确认不适用” action.

**Tech Stack:** React 19, TypeScript, Vitest, FastAPI reporting modules, pytest.

## Global Constraints

- Keep API and database value `not_applicable` unchanged.
- Keep manual action “确认不适用” and manual state “人工确认不适用” unchanged.
- Preserve unrelated working-tree changes.

---

### Task 1: Automatic status label

**Files:**
- Modify: `frontend/src/appCopy.test.ts`
- Modify: `frontend/src/TemplateReviewView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `backend/tests/test_reports.py`
- Modify: `backend/app/reporting/reports.py`
- Modify: `backend/app/reporting/docx_report.py`
- Modify: `docs/review-result-actions-quick-start.md`

**Interfaces:**
- Consumes: existing `RuleStatus.NOT_APPLICABLE` / `not_applicable` mappings.
- Produces: user-facing automatic label “规则不适用”.

- [x] **Step 1: Write failing copy-contract tests**

Add frontend assertions for `not_applicable: { label: "规则不适用"` and retained “确认不适用”. Add backend assertions that both PDF and DOCX status mappings resolve `not_applicable` to “规则不适用”.

- [x] **Step 2: Run focused tests and verify RED**

Run `npm test -- --run src/appCopy.test.ts` in `frontend`, and `.\.venv\Scripts\python.exe -m pytest tests\test_reports.py -q` in `backend`.

Expected: both suites fail because the automatic status is still labeled “不适用”.

- [x] **Step 3: Update presentation mappings and documentation**

Replace only automatic-state labels with “规则不适用”. Do not replace “确认不适用”, “人工确认不适用”, or explanatory uses of the general phrase “不适用”.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the same focused commands and expect all tests to pass.

- [x] **Step 5: Run final verification**

Run the complete frontend test suite, `npm run build`, and the targeted backend report tests. Audit the diff to confirm only presentation copy, tests, and documentation changed.
