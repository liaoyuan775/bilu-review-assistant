# Review Follow-up List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `test-driven-development` to implement each task test-first.

**Goal:** Turn manual review into a three-way triage that produces an offline follow-up list without recording answers or re-running the model.

**Architecture:** Keep existing manual status values for compatibility. `supplemented` means the item belongs to the DOCX list; `resolved` and `ignored` only annotate the review report. Archive will generate the PDF and DOCX itself after all actionable items have a non-pending manual status.

**Tech Stack:** FastAPI, Pydantic, python-docx, ReportLab, React, TypeScript, Vitest, pytest.

## Global Constraints

- Do not append answers to the source document or invoke model review from a manual action.
- Do not make a user download a file before archive.
- Preserve the automatic rule status separately from the manual decision.

### Task 1: Backend review lifecycle

**Files:** `backend/app/review/review.py`, `backend/app/reporting/archive.py`, `backend/tests/test_review_lifecycle.py`

- [ ] Write a failing pytest case asserting all three manual decisions allow archive without a reason and that archiving creates PDF/DOCX without JSON or manifest requirements.
- [ ] Run the targeted test; it must fail because current archive requires generated artifacts and reasons.
- [ ] Remove the answer/re-review path, relax manual-decision validation, and make `complete_review` generate the two user artifacts before setting the task read-only.
- [ ] Run the targeted lifecycle tests.

### Task 2: Report artifacts

**Files:** `backend/app/reporting/docx_report.py`, `backend/app/reporting/reports.py`, `backend/app/storage/artifacts.py`, `backend/tests/test_reports.py`

- [ ] Write a failing pytest case asserting DOCX contains only `supplemented` issues while PDF contains each manual decision.
- [ ] Run the targeted report test and verify its expected failure.
- [ ] Generate only PDF/DOCX, limit DOCX selection to `supplemented`, and keep all decisions in PDF.
- [ ] Run the targeted report tests.

### Task 3: Review interface

**Files:** `frontend/src/reviewActionPolicy.ts`, `frontend/src/templateReviewState.ts`, `frontend/src/TemplateReviewView.tsx`, `frontend/src/reviewActionPolicy.test.ts`, `frontend/src/templateReviewState.test.ts`

- [ ] Write failing Vitest cases for the three labels, their processed status, and no generated-artifact archive blocker.
- [ ] Run the focused Vitest files and verify expected failures.
- [ ] Remove the answer panel flow, make the follow-up action visually primary, and update labels, report links, and archive state.
- [ ] Run focused Vitest files, then `npm run build`.
