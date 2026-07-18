# Police Review Experience Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build seven realistic fictional inquiry records, run the complete police review workflow, and implement the productivity improvements demonstrated by that testing.

**Architecture:** Keep the existing FastAPI, SQLite, React, and Vite boundaries. Reuse `manualDecision.reason` for optional edited follow-up text, add victim data to the report DTO, and isolate pure frontend behavior in testable helpers. Extend the existing DOCX generator and use LibreOffice/Poppler for PDF conversion and page rendering.

**Tech Stack:** Python 3.12, python-docx, FastAPI, Pydantic, SQLite, React 19, TypeScript, Vitest, Vite, LibreOffice, Poppler, Qwen multimodal API.

## Global Constraints

- Work in the existing shared `main` worktree and preserve all concurrent uncommitted changes.
- Do not create Git commits unless the user explicitly requests them.
- Use only clearly fictional test identities, accounts, addresses, organizations, and case facts.
- Do not infer victim fields that are absent from the source document.
- Routine triage, ignore, completion, and archive must require zero typed text.
- Follow-up editing is optional and lives only in the follow-up list.
- Use TDD for every production behavior change and record the expected RED failure before implementation.

---

### Task 1: Expand the realistic test-record corpus

**Files:**
- Modify: `backend/scripts/generate_test_records.py`
- Modify: `backend/tests/test_generate_test_records.py`
- Generate: `output/doc/01-*.docx` through `output/doc/07-*.docx`
- Generate: matching `output/doc/01-*.pdf` through `output/doc/07-*.pdf`

**Interfaces:**
- Consumes: `InquiryRecord` and `generate_test_records(output_dir: Path) -> list[Path]`.
- Produces: seven deterministic fictional DOCX files and seven matching PDFs.

- [ ] Add a failing test asserting seven records, unique case numbers, explicit eight-field victim identity data, and scenario tokens for safe-account, ATM, cryptocurrency, remote control, courier/gold, destroyed evidence, and contradictory answers.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_generate_test_records.py` and verify it fails because only three records exist.
- [ ] Add four `InquiryRecord` scenarios and make the identity table row count derive from the number of identity fields.
- [ ] Regenerate DOCX files with `backend\.venv\Scripts\python.exe backend\scripts\generate_test_records.py --output-dir output\doc`.
- [ ] Run the focused generator test and verify all assertions pass.
- [ ] Convert all seven DOCX files to PDF with LibreOffice and render every page to PNG under `tmp/docs/rendered/`.
- [ ] Inspect every rendered page and fix layout defects before continuing.

### Task 2: Harden explicit victim-profile extraction

**Files:**
- Modify: `backend/app/services/victim_profile.py`
- Modify: `backend/tests/test_victim_profile.py`

**Interfaces:**
- Consumes: parsed document text containing DOCX table delimiters.
- Produces: `extract_victim_profile(text: str) -> VictimProfile | None` with cleaned explicit values only.

- [ ] Add failing tests for `年龄 | 66岁`, `民族 | 汉族`, `工作单位 | 某单位`, and a `现住址` value prefixed by a table separator.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_victim_profile.py` and verify the table cases fail.
- [ ] Add a narrow value-cleaning helper that removes leading/trailing table separators while preserving source text.
- [ ] Run focused tests and confirm explicit fields pass while the existing partial-profile test still proves no inference.

### Task 3: Add follow-up text helpers and automatic triage progression

**Files:**
- Modify: `frontend/src/reviewState.ts`
- Modify: `frontend/src/reviewState.test.ts`
- Create: `frontend/src/followUpText.ts`
- Create: `frontend/src/followUpText.test.ts`

**Interfaces:**
- Produces: `nextPendingRuleId(results, currentRuleId)`, `effectiveFollowUpQuestion(result)`, and `formatFollowUpList(results)`.
- Consumes: existing `ReviewResult` and `ManualDecision` types.

- [ ] Add failing tests proving the next pending item is selected after a decision and wraps only when an earlier pending item remains.
- [ ] Add failing tests proving edited text overrides model text and copy-all includes only supplemented items with stable numbering.
- [ ] Run `npm --prefix frontend run test -- reviewState.test.ts followUpText.test.ts` and verify RED failures for missing helpers.
- [ ] Implement the three pure helpers with no UI dependencies.
- [ ] Re-run focused tests and verify GREEN.

### Task 4: Implement copy, optional edit, and auto-next UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Consumes: helpers from Task 3 and existing `submitDecision(taskId, ruleId, status, reason)`.
- Produces: single-copy, copy-all, edit/save/cancel controls and automatic selection of the next pending finding.

- [ ] Update `updateManualDecision` to calculate the updated result list once and select `nextPendingRuleId` after a successful save.
- [ ] Render icon buttons for copy and edit in the follow-up drawer; copy text through `navigator.clipboard.writeText` and report success through the existing toast.
- [ ] Show a textarea only after an explicit edit action; save by resubmitting `supplemented` with the edited text in `manualDecision.reason`; cancel without a write.
- [ ] Add stable responsive dimensions so opening edit mode does not resize the result header or overlap the findings panes.
- [ ] Run all frontend unit tests and the production build.

### Task 5: Add victim information and final follow-up text to reports

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/tests/test_api.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: `ReportData.victimProfile: VictimProfile | None`.
- Consumes: persisted task victim profile and `effectiveFollowUpQuestion`.

- [ ] Add a failing backend API test asserting `report-data` returns the task victim profile unchanged.
- [ ] Run the focused backend test and verify the response-model failure.
- [ ] Add `victimProfile` to the Pydantic and TypeScript report types and populate it in `report_data`.
- [ ] Render a compact victim-information section in the printable report and display edited follow-up text when present.
- [ ] Add print CSS that keeps the identity block together and hides all application navigation and controls.
- [ ] Run focused backend tests, all frontend tests, and the production build.

### Task 6: Run all seven materials through the full workflow

**Files:**
- Create: `docs/qa/2026-07-17-police-review-experience.md`
- Produce: browser evidence under `output/playwright/`

**Interfaces:**
- Consumes: generated PDFs/DOCX files, live `4175` frontend, live `8788` backend, and SQLite review history.
- Produces: a per-file result matrix and a concise busy-officer experience report.

- [ ] Upload each of the seven materials through the real Qwen endpoint and record task ID, duration, rule counts, victim extraction, and model errors.
- [ ] For every missing or incomplete item, exercise one of the three manual dispositions and complete the review.
- [ ] Verify copy-one, copy-all, edit-save, report print view, automatic archive, and history reopen behavior.
- [ ] Restart the backend once and verify archived tasks remain readable from `backend/data/reviews.db` with `PRAGMA integrity_check = ok`.
- [ ] Document observed false positives, missed omissions, evidence-location defects, and remaining V1 limitations without presenting model output as legal fact.

### Task 7: Final verification and completion audit

**Files:**
- Verify all files changed by Tasks 1-6.

**Interfaces:**
- Produces: fresh evidence for every completion claim.

- [ ] Run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests`.
- [ ] Run `npm --prefix frontend run test`.
- [ ] Run `npm --prefix frontend run build`.
- [ ] Run `backend\.venv\Scripts\python.exe -m compileall -q backend\app backend\scripts`.
- [ ] Inspect `git diff --check` and search for unresolved conflict markers.
- [ ] Use the browser at desktop and mobile viewports to verify the complete workflow, screenshots, layout, clipboard actions, and zero console errors.
- [ ] Re-read the design spec and QA report and verify every material, interaction, persistence, and reporting requirement has direct evidence.
