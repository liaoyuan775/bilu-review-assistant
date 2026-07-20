# Template-Driven Sanitized Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every local demo/test DOCX derive from the tracked inquiry template and make review-result UI text Chinese while preserving English API contracts.

**Architecture:** A small OpenXML fixture builder rewrites only answer text in the tracked template and skips unreadable nonessential media. The demo catalog reads generated documents from `backend/demo_documents`; the frontend maps internal identifiers to Chinese labels at render time.

**Tech Stack:** Python 3, `lxml`, `zipfile`, existing FastAPI parser, React + TypeScript, Vitest.

## Global Constraints

- Never read or use `D:\AgentLearning\bilu\output`.
- Keep `ruleId`, `group`, fact paths, and entity types English in backend/API contracts.
- Show Chinese-only user-facing review content.
- Treat the template as the source of question order and fields; three-present/four-flow is only a review grouping lens.
- Use fictional names, identifiers, accounts, URLs, and IP placeholders in generated data.

---

### Task 1: Template OpenXML Fixture Builder

**Files:**
- Create: `backend/app/services/template_fixture.py`
- Create: `backend/tests/test_template_fixture.py`

**Interfaces:**
- Consumes: template DOCX bytes and exactly 33 answer strings.
- Produces: `build_template_fixture(template_bytes: bytes, answers: Sequence[str]) -> bytes`.

- [ ] **Step 1: Write the failing test**

Add tests that call `build_template_fixture` with the tracked template and 33 sentinel answers, parse the result through `parse_document`, and assert that there are 33 question-answer blocks, the first question is unchanged, and sentinel answers appear in the corresponding answer slots.

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests\\test_template_fixture.py`

Expected: collection failure because `app.services.template_fixture` does not yet exist.

- [ ] **Step 3: Implement the minimal XML rewrite**

Read `word/document.xml` with `lxml`, replace answer-marker content in order, copy readable ZIP parts, replace `word/document.xml`, and skip only unreadable media parts. Raise `ValueError` when the marker count differs from `len(answers)`.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests\\test_template_fixture.py`

Expected: all focused tests pass and the parsed document still reports 33 Q&A blocks.

### Task 2: Move Demo/Test Documents Off `output`

**Files:**
- Modify: `backend/app/demo_cases.py`
- Modify: `backend/scripts/generate_test_records.py`
- Modify: `backend/scripts/generate_template_gold_cases.py`
- Create: `backend/scripts/generate_template_demos.py`
- Create: `backend/demo_documents/*.docx`
- Modify: `backend/tests/test_demo_cases.py`
- Modify: `backend/tests/test_generate_test_records.py`

**Interfaces:**
- Consumes: `backend/询问笔录模版(1).docx` and existing fictional scenario data.
- Produces: seven template-derived demo files and a demo catalog rooted at `backend/demo_documents`.

- [ ] **Step 1: Add a regression assertion for the demo root**

Assert that every `DemoCase.path` is under `backend/demo_documents` and that no source reference contains `output`.

- [ ] **Step 2: Run the regression and verify it fails**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests\\test_demo_cases.py::test_demo_catalog_uses_only_the_seven_docx_cases`

Expected: failure because the current catalog points at `output/doc`.

- [ ] **Step 3: Generate template-derived documents**

Build seven answer lists from the existing fictional `RECORDS`, fill the template answer slots, and write the generated files under `backend/demo_documents`. Keep scenario namespaces and explicit “不知道” answers in answer text only.

- [ ] **Step 4: Point the catalog and generators at the template output**

Change `DEMO_DOCUMENT_ROOT` and make both generators use the shared fixture builder. Do not add a fallback to `output`.

- [ ] **Step 5: Run the focused backend tests**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests\\test_template_fixture.py backend\\tests\\test_demo_cases.py backend\\tests\\test_generate_test_records.py`

Expected: all selected tests pass and all seven generated files parse as 33-question template documents.

### Task 3: Chinese Review-Result Display

**Files:**
- Modify: `frontend/src/ruleLabels.ts`
- Modify: `frontend/src/TemplateReviewView.tsx`
- Create or modify: `frontend/src/ruleLabels.test.ts`

**Interfaces:**
- Consumes: existing English API identifiers.
- Produces: Chinese-only visible group, domain, entity, scope, and result labels.

- [ ] **Step 1: Write failing label/UI tests**

Add assertions for domain/entity mappings and render a representative result to confirm `CASE`, `transfers`, and a raw rule ID are absent from visible text.

- [ ] **Step 2: Run the focused frontend tests and verify failure**

Run: `npm.cmd --prefix frontend test -- --run src/ruleLabels.test.ts`

Expected: failure because domain/entity mappings and raw-code suppression are not implemented.

- [ ] **Step 3: Add mappings and remove raw-code render nodes**

Map all currently returned domain and entity identifiers, render only Chinese labels, and keep internal IDs in React keys/search/action callbacks.

- [ ] **Step 4: Run focused tests and build**

Run: `npm.cmd --prefix frontend test -- --run src/ruleLabels.test.ts` and `npm.cmd --prefix frontend run build`.

Expected: focused tests pass and the production build exits with code 0.

### Task 4: Handbook, One Baseline Run, and Verification

**Files:**
- Modify: `docs/project-technical-guide.md`
- Modify: `README.md` only if runtime commands or demo location changed.

- [ ] **Step 1: Update the handbook with current evidence**

Record the template path/hash, demo root, Chinese rendering boundary, commands actually run, and the explicit non-use of `output`.

- [ ] **Step 2: Run one proportional verification round**

Run: `npm.cmd test`, `npm.cmd run build`, `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests\\test_template_fixture.py backend\\tests\\test_demo_cases.py backend\\tests\\test_generate_test_records.py`, and one local mock demo request through `/api/v1/demos` plus `/api/v1/reviews/demos/case-01-basic-complete`.

- [ ] **Step 3: Inspect the working tree**

Confirm the pre-existing `frontend/src/styles.css` edit and the Word lock file are untouched, and confirm no command read `output`.
