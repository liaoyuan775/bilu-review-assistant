# Archive Report Handling Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put manually handled review items near the front of archived reports and preserve the downloadable follow-up DOCX.

**Architecture:** Reuse `ReviewResult.manualDecision` as the single source for both the browser report and generated PDF. Keep the existing `follow_up_docx` generator and artifact endpoint unchanged, adding only regression coverage and restoring its visible download path where needed.

**Tech Stack:** FastAPI, ReportLab, python-docx, React, TypeScript, Vitest, pytest.

## Global Constraints

- Keep 34 review rules and existing API result shapes unchanged.
- Do not add a follow-up PDF.
- Do not restore the unrelated follow-up answer re-review sidebar.
- Preserve `review_pdf` and `follow_up_docx` as the two user-facing archive artifacts.

---

### Task 1: Report handling summary

**Files:**
- Modify: `backend/tests/test_reports.py`
- Modify: `backend/app/reporting/reports.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `ReviewResult.manualDecision.status` and `.reason`.
- Produces: “人工处理汇总” in the generated PDF and browser report.

- [ ] **Step 1: Write a failing PDF test**

Assert that generated PDF text contains `人工处理汇总`, `RISK-001`, `已加入补问清单`, and its handling reason before `逐项审查与人工处置`.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m pytest -q tests/test_reports.py::test_generated_documents_contain_review_evidence_and_page_fields`

Expected: failure because `人工处理汇总` is absent.

- [ ] **Step 3: Add the minimal PDF and browser sections**

Filter with:

```python
handled = [item for item in task.results if item.manualDecision.status.value != "pending"]
```

Render rule ID/name, `manual_status_label()`, and `decision.reason or "未填写"` before detailed results. Use the equivalent TypeScript filter in `ReportView`.

- [ ] **Step 4: Run the focused backend test and frontend build**

Run: `python -m pytest -q tests/test_reports.py`

Run: `npm --prefix frontend run build`

Expected: both pass.

### Task 2: Preserve follow-up DOCX download

**Files:**
- Modify: `backend/tests/test_reports.py`
- Verify: `backend/app/reporting/docx_report.py`
- Verify: `backend/app/reporting/reports.py`
- Verify: `frontend/src/TemplateReviewView.tsx`

**Interfaces:**
- Consumes: archive artifact type `follow_up_docx`.
- Produces: downloadable `.docx` containing only `supplemented` items.

- [ ] **Step 1: Strengthen the existing artifact regression test**

Assert the artifact filename ends in `-补问工作清单.docx`, downloaded bytes open with python-docx, and the task includes both `review_pdf` and `follow_up_docx`.

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest -q tests/test_reports.py::test_generate_endpoint_produces_the_two_user_facing_reports`

Expected: pass if the existing Word path is intact; otherwise restore only the missing link or artifact generation line.

- [ ] **Step 3: Run one verification round**

Run: `python -m pytest -q tests/test_reports.py tests/test_api.py`

Run: `npm --prefix frontend test -- --run`

Expected: all related tests pass.
