# Internal Inquiry Template Complete Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed seven-rule review with a template-derived, evidence-linked workflow covering upload, extraction, deterministic validation, police follow-up handling, document output, archive, quality gates, performance measurement, branch push, and final merge.

**Architecture:** Preserve the existing FastAPI/React/Qwen stack, but separate tolerant document normalization, strict-schema fact extraction, deterministic template rules, append-only manual events, and artifact generation. Keep current endpoints compatible where practical while adding versioned facts, precise anchors, template groups, and archive gates.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, PyMuPDF, python-docx, sqlite3, React 18, TypeScript, Vite, Vitest, pytest, Playwright, Qwen3.6-35B-A3B.

## Global Constraints

- The internal template is the sole business-rule source; “三现四流” is not a final rule authority.
- Use only the project-configured `Qwen3.6-35B-A3B` endpoint; do not add a second model provider.
- Common rules are mandatory; conditional rules require evidence-backed applicability; repeated rules verify declared and actual entity counts.
- Model output never overrides deterministic missing, incomplete, inconsistent, or applicability decisions.
- All facts and review issues require valid source anchors; failed required stages block archive.
- Test data must use explicit synthetic namespaces and pass sensitive-pattern scanning.
- Quality gates run before performance work; performance changes require zero semantic regression and at least 10% repeatable P50 or P95 improvement.
- Work only on `codex/template-complete-review`, push each completed phase, and merge to `main` only after all gates pass.

---

### Task 1: Establish Isolated Baseline And Template Regression

**Files:**
- Create: `backend/tests/fixtures/template/README.md`
- Create: `backend/tests/test_template_document_parser.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: user-provided source template copied to ignored local fixture location via `BILU_TEMPLATE_PATH`.
- Produces: regression tests that call `parse_document(filename: str, content: bytes) -> ParsedDocument` and prove the current failure mode.

- [ ] **Step 1: Verify the worktree branch and clean baseline**

Run: `git status --short --branch && npm install && npm --prefix frontend install && backend\.venv\Scripts\python.exe -m pytest -q backend\tests && npm --prefix frontend run test && npm --prefix frontend run build`

Expected: branch is `codex/template-complete-review`; 49 backend tests and 36 frontend tests pass; build exits 0.

- [ ] **Step 2: Write the failing damaged-media template test**

```python
def test_docx_with_corrupt_nonessential_media_keeps_document_text(corrupt_media_docx: bytes):
    parsed = asyncio.run(parse_document("template.docx", corrupt_media_docx))
    assert "电信网络诈骗案件询问笔录" in parsed.text
    assert any(warning.code == "media_corrupt" for warning in parsed.warnings)
```

- [ ] **Step 3: Run the regression test and verify RED**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_document_parser.py::test_docx_with_corrupt_nonessential_media_keeps_document_text`

Expected: FAIL with current `parse_failed` behavior or missing `warnings` contract.

- [ ] **Step 4: Commit the approved design, plan, and failing regression**

Run: `git add docs/superpowers/specs/2026-07-18-template-complete-review-design.md docs/superpowers/plans/2026-07-18-template-complete-review.md backend/tests/test_template_document_parser.py backend/tests/fixtures/template/README.md .gitignore && git commit -m "docs: define template review implementation" && git push`

Expected: commit succeeds and remote branch advances.

### Task 2: Tolerant DOCX/PDF Normalization And Precise Anchors

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/parser.py`
- Create: `backend/app/services/openxml.py`
- Test: `backend/tests/test_template_document_parser.py`
- Modify: `backend/tests/test_parser.py`

**Interfaces:**
- Produces: `DocumentWarning(code, message, partName)`, `SourceAnchor(blockId, page, paragraph, charStart, charEnd, bbox)`, and extended `DocumentParagraph(id, text, sourceType, confidence, anchors)`.
- Produces: `read_docx_parts(content: bytes) -> OpenXmlDocument` that returns recoverable text even when an unrelated media member has a bad CRC.

- [ ] **Step 1: Add failing tests for media isolation, header/footer extraction, stable block IDs, offsets, and PDF coordinates**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_document_parser.py backend\tests\test_parser.py`

Expected: new assertions fail because the contracts do not exist.

- [ ] **Step 2: Implement selective Open XML loading**

```python
def read_docx_parts(content: bytes) -> OpenXmlDocument:
    """Read document/header/footer XML first and isolate per-media CRC failures."""
```

Use `zipfile.ZipFile.read()` only for required XML parts, parse with `lxml`, and catch `BadZipFile` per optional media part. Preserve reading order and create a warning for each skipped media member.

- [ ] **Step 3: Add stable anchors to DOCX and PDF paragraphs**

Create deterministic block IDs from document version, page/logical page, source order, and text hash. Populate character offsets; populate PDF block bounding boxes from `page.get_text("dict")`.

- [ ] **Step 4: Verify parser GREEN and full backend regression**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_document_parser.py backend\tests\test_parser.py backend\tests\test_api.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit and push**

Run: `git add backend/app/models.py backend/app/services/parser.py backend/app/services/openxml.py backend/tests && git commit -m "feat: add tolerant template document parsing" && git push`

### Task 3: Reconstruct Question/Answer Blocks Without Mixing Template Guidance

**Files:**
- Create: `backend/app/services/question_answer.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/parser.py`
- Create: `backend/tests/test_question_answer.py`

**Interfaces:**
- Produces: `QuestionAnswerBlock(id, question, answer, guidance, anchorIds, answerClarity)`.
- Produces: `reconstruct_question_answers(pages: list[DocumentPage]) -> list[QuestionAnswerBlock]`.

- [ ] **Step 1: Write failing tests for cross-paragraph, cross-page, same-paragraph, blank-answer, and guidance isolation cases**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_question_answer.py`

Expected: FAIL because `reconstruct_question_answers` is absent.

- [ ] **Step 2: Implement the minimal finite-state parser**

Recognize both Chinese and ASCII colons after 问/答, carry an open answer across pages until the next question, split multiple markers in one paragraph, and move parenthetical template instructions into `guidance` rather than `answer`.

- [ ] **Step 3: Attach Q/A blocks to `ParsedDocument` and preserve legacy pages/text**

The API remains backward compatible while exposing `questionAnswers` and warnings.

- [ ] **Step 4: Verify RED-GREEN and parser regression**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_question_answer.py backend\tests\test_template_document_parser.py backend\tests\test_api.py`

- [ ] **Step 5: Commit and push**

Run: `git add backend/app/models.py backend/app/services/parser.py backend/app/services/question_answer.py backend/tests && git commit -m "feat: reconstruct template question answers" && git push`

### Task 4: Add Versioned Template Rule Catalog And Deterministic Engine

**Files:**
- Create: `backend/template_rules.json`
- Create: `backend/app/template_models.py`
- Create: `backend/app/services/template_rule_engine.py`
- Modify: `backend/app/data.py`
- Modify: `backend/app/models.py`
- Create: `backend/tests/test_template_rule_catalog.py`
- Create: `backend/tests/test_template_rule_engine.py`

**Interfaces:**
- Produces: `TemplateRule`, `ExtractedFact`, `ExtractedEntity`, `CaseExtraction`, `TemplateReviewIssue`.
- Produces: `evaluate_template_rules(extraction: CaseExtraction, rules: list[TemplateRule]) -> list[TemplateReviewIssue]`.

- [ ] **Step 1: Write catalog tests proving every template question/structural item maps to a source-backed rule**

Assert unique IDs, version/source metadata, valid fields, valid conditions, and coverage of META/PROC/CASE/PREV/RISK/CASH/TIME/PRIV/LEAD/MOTIVE/CONTACT/MONEY/OFFLINE/EXTRA/EVID groups.

- [ ] **Step 2: Write failing rule-engine tests**

Cover common missing fields, conditional not-applicable, unknown answers, repeated count mismatch, sum mismatch, rebate/net-loss mismatch, and chronological contradiction.

- [ ] **Step 3: Implement the minimal typed rule loader and deterministic evaluator**

The evaluator derives statuses and explanations from facts; no LLM call is allowed in this module.

- [ ] **Step 4: Verify catalog and engine tests**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_rule_catalog.py backend\tests\test_template_rule_engine.py`

- [ ] **Step 5: Commit and push**

Run: `git add backend/template_rules.json backend/app/data.py backend/app/models.py backend/app/template_models.py backend/app/services/template_rule_engine.py backend/tests && git commit -m "feat: add template-derived review rules" && git push`

### Task 5: Extract Evidence-Linked Facts With The Configured Qwen Model

**Files:**
- Create: `backend/app/services/template_extraction.py`
- Modify: `backend/app/services/qwen.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/models.py`
- Create: `backend/tests/test_template_extraction.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `extract_template_facts(document: ParsedDocument, timings: dict[str, int]) -> CaseExtraction`.
- Consumes: domain-specific strict JSON Schemas and stable source anchors.
- Produces: evidence-validated facts only; values with invalid anchors are rejected and retried once.

- [ ] **Step 1: Write failing schema, prompt-boundary, anchor-validation, retry, and domain-merge tests**

Verify that guidance text cannot become a fact, repeated arrays preserve all entities, and one failed domain prevents a complete review.

- [ ] **Step 2: Implement domain schemas and prompt construction**

Reuse the current OpenAI-compatible client, authentication, timeout, strict schema/tool fallback, logging redaction, and one-retry policy.

- [ ] **Step 3: Implement anchor validation and deterministic issue generation**

Pass `CaseExtraction` to `evaluate_template_rules`; only unresolved ambiguity receives a targeted semantic-review request.

- [ ] **Step 4: Verify extraction and API tests without live model dependency**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_extraction.py backend\tests\test_template_rule_engine.py backend\tests\test_api.py`

- [ ] **Step 5: Commit and push**

Run: `git add backend/app backend/tests && git commit -m "feat: extract template facts with evidence" && git push`

### Task 6: Persist Documents, Runs, Issues, Events, And Artifacts

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/store.py`
- Create: `backend/app/services/artifacts.py`
- Create: `backend/tests/test_template_store.py`
- Modify: `backend/tests/test_store.py`

**Interfaces:**
- Produces: storage methods for document/version/run/issue/event/artifact records while retaining legacy task reads.
- Produces: `save_original(task_id, filename, content) -> DocumentArtifact` and content-addressed SHA-256 metadata.

- [ ] **Step 1: Write failing migration, persistence, append-only event, artifact hash, and legacy-read tests**

- [ ] **Step 2: Implement idempotent SQLite schema migrations**

Use explicit schema versioning and transactions; do not introduce an ORM dependency.

- [ ] **Step 3: Implement controlled artifact storage**

Normalize filenames, prevent path traversal, store under configured task/version directories, and verify hash on read.

- [ ] **Step 4: Verify persistence tests**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_store.py backend\tests\test_store.py`

- [ ] **Step 5: Commit and push**

Run: `git add backend/app backend/tests && git commit -m "feat: persist review audit records and artifacts" && git push`

### Task 7: Complete API Workflow And Archive Gates

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/review.py`
- Create: `backend/app/services/archive.py`
- Modify: `backend/tests/test_api.py`
- Create: `backend/tests/test_review_lifecycle.py`
- Modify: `docs/openapi.json`

**Interfaces:**
- Adds version, issue-action, follow-up-answer, retry-domain, artifact-download, and archive endpoints.
- Produces append-only manual events and affected-domain re-review.

- [ ] **Step 1: Write failing lifecycle tests from upload through follow-up, re-review, report, and archive**

Assert that pending high-risk issues, failed domains, unresolved warnings, or missing artifacts block archive.

- [ ] **Step 2: Implement endpoints and state transitions**

Keep existing review detail/history endpoints compatible and add precise error codes for every archive gate.

- [ ] **Step 3: Export and validate OpenAPI**

Run: `backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py`

- [ ] **Step 4: Verify lifecycle and full backend tests**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests`

- [ ] **Step 5: Commit and push**

Run: `git add backend docs/openapi.json && git commit -m "feat: complete review lifecycle and archive gates" && git push`

### Task 8: Build The Police-Facing Template Review Workspace

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/TemplateReviewView.tsx`
- Create: `frontend/src/DocumentEvidencePane.tsx`
- Create: `frontend/src/FollowUpPanel.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/templateReviewState.test.ts`
- Modify: `frontend/src/evidenceSelection.test.ts`

**Interfaces:**
- Consumes template groups, precise anchors, repeated entities, issues, manual events, artifacts, and archive gates.
- Produces dynamic group rendering; exact evidence highlight; follow-up question/answer/resolution flow; immutable archived view.

- [ ] **Step 1: Write failing frontend state tests for dynamic groups, status counts, anchor ranges, next issue, and archive readiness**

Run: `npm --prefix frontend run test -- templateReviewState.test.ts evidenceSelection.test.ts`

- [ ] **Step 2: Extend types and API client**

Remove the hard-coded `"三现" | "四流"` union and use server-provided template group metadata.

- [ ] **Step 3: Implement the focused workbench components**

Retain the existing quiet office UI; display actionable items first, repeated entities as compact rows, exact source highlighting, and explicit warnings/gates.

- [ ] **Step 4: Verify frontend tests and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

- [ ] **Step 5: Commit and push**

Run: `git add frontend && git commit -m "feat: add template review police workflow" && git push`

### Task 9: Generate Review PDF, Follow-Up DOCX, JSON, And Archive Manifest

**Files:**
- Create: `backend/app/services/reports.py`
- Create: `backend/app/services/docx_report.py`
- Modify: `backend/app/services/archive.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_reports.py`
- Create: `backend/tests/test_archive_manifest.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces: `generate_review_artifacts(task_id) -> list[ArtifactRecord]`.
- Produces PDF, DOCX, JSON, and a SHA-256 manifest with rule/model/parser versions.

- [ ] **Step 1: Write failing content, pagination, manifest-hash, and archive-readonly tests**

- [ ] **Step 2: Implement deterministic JSON and DOCX generation**

Use `python-docx`; include unresolved issues, exact evidence, and manual history; calculate page/footer fields dynamically.

- [ ] **Step 3: Implement printable HTML/PDF path and artifact endpoints**

Use the existing print-oriented report UI for HTML and a verified server-side PDF renderer available in the workspace; if Word/renderer is unavailable, fail the artifact stage explicitly rather than archiving without PDF.

- [ ] **Step 4: Render and visually inspect every generated DOCX/PDF page**

Use `tmp/docs/` for intermediate pages and record page count/visual findings in `progress.md`.

- [ ] **Step 5: Verify report/archive tests, commit, and push**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_reports.py backend\tests\test_archive_manifest.py`

Run: `git add backend frontend && git commit -m "feat: generate review and archive artifacts" && git push`

### Task 10: Build The Sanitized Golden Corpus And Quality Gate

**Files:**
- Create: `backend/scripts/generate_template_gold_cases.py`
- Create: `backend/scripts/verify_template_quality.py`
- Create: `backend/tests/gold/template_cases.json`
- Create: `backend/tests/test_template_gold_corpus.py`
- Modify: `backend/scripts/generate_test_records.py`
- Modify: `backend/app/demo_cases.py`

**Interfaces:**
- Produces at least 12 base DOCX/PDF pairs plus rule mutations and oracle JSON.
- Produces a verifier reporting parse, Q/A, field, entity, anchor, applicability, issue, false-positive, stability, and sensitive-pattern metrics.

- [ ] **Step 1: Write failing corpus coverage and sensitive-pattern tests**

Require every template rule to have covered, missing, and incomplete/inconsistent evidence across the corpus.

- [ ] **Step 2: Implement deterministic synthetic records and mutation generation**

Use explicit test namespaces and no complete real-looking identity, phone, card, URL, public IP, or account values.

- [ ] **Step 3: Implement offline quality verifier and run it against mocked extraction contracts**

Run: `backend\.venv\Scripts\python.exe backend\scripts\verify_template_quality.py --offline`

Expected: all deterministic metrics are 100% and sensitive scan finds zero prohibited values.

- [ ] **Step 4: Run live Qwen gold verification three consecutive times**

Run: `backend\.venv\Scripts\python.exe backend\scripts\verify_template_quality.py --live --runs 3 --output .runtime\template-quality.json`

Expected: required recall/anchors/applicability/issues are 100%; semantic stability is 100%; no raw sensitive payload appears in logs.

- [ ] **Step 5: Commit corpus sources/oracles, not transient rendered output, and push**

Run: `git add backend/scripts backend/tests/gold backend/tests/test_template_gold_corpus.py backend/app/demo_cases.py && git commit -m "test: add template review quality gate" && git push`

### Task 11: Measure And Apply Only Quality-Neutral Performance Improvements

**Files:**
- Create: `backend/scripts/benchmark_template_review.py`
- Modify: `backend/app/services/template_extraction.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/models.py`
- Create: `backend/tests/test_template_performance_contract.py`
- Create: `docs/template-review-performance.md`

**Interfaces:**
- Produces benchmark JSON with per-stage, request, token, P50, and P95 metrics.
- Consumes quality fingerprints and rejects any semantic difference.

- [ ] **Step 1: Write the semantic-fingerprint regression test before optimizing**

The fingerprint includes paths, fact values, entity counts, rule statuses, missing fields, and anchors; explanation wording is excluded.

- [ ] **Step 2: Capture the unoptimized baseline**

Run: `backend\.venv\Scripts\python.exe backend\scripts\benchmark_template_review.py --runs 5 --output .runtime\benchmark-before.json`

- [ ] **Step 3: Implement one measured candidate at a time**

Evaluate bounded domain concurrency, HTTP connection reuse, affected-domain rechecks, and domain context selection independently. Revert candidates that fail quality or do not improve P50/P95 by at least 10%.

- [ ] **Step 4: Capture the optimized benchmark and compare**

Run: `backend\.venv\Scripts\python.exe backend\scripts\benchmark_template_review.py --runs 5 --baseline .runtime\benchmark-before.json --output .runtime\benchmark-after.json`

Expected: quality fingerprint identical; P50 or P95 improves by at least 10%, otherwise the final document records that no optimization was accepted.

- [ ] **Step 5: Commit accepted code and performance report, then push**

Run: `git add backend docs/template-review-performance.md && git commit -m "perf: optimize template review without quality loss" && git push`

### Task 12: End-To-End Verification, Review, And Main Merge

**Files:**
- Modify: `README.md`
- Modify: `docs/project-technical-guide.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

**Interfaces:**
- Produces final requirements audit and reproducible verification commands.

- [ ] **Step 1: Run the full automated suite and build**

Run: `npm run test && npm run build`

Expected: all backend/frontend tests pass and build exits 0.

- [ ] **Step 2: Run live quality, report rendering, sensitive scan, and benchmark comparison**

Run the Task 10 and Task 11 commands fresh; inspect generated JSON and every report page.

- [ ] **Step 3: Start the app and execute Playwright end-to-end checks**

Verify upload, progress, dynamic rule groups, exact location, follow-up answer, re-review, artifact download, archive gate, history replay, desktop 1440x900/1920x1080, and 390px overflow sanity; require zero console errors.

- [ ] **Step 4: Review the complete diff and requirements matrix**

Run: `git diff origin/main...HEAD --stat && git diff --check && git status --short --branch`

- [ ] **Step 5: Commit final docs and push feature branch**

Run: `git add README.md docs progress.md task_plan.md && git commit -m "docs: finalize template review delivery" && git push`

- [ ] **Step 6: Merge current `origin/main` into the feature branch and rerun smoke tests**

Run: `git fetch origin && git merge --no-edit origin/main && npm run test && npm run build && git push`

- [ ] **Step 7: Merge the verified feature branch to remote `main` and refresh local main safely**

Use a GitHub merge or an isolated integration checkout so the dirty root worktree is not overwritten. Push the merge to `origin/main`, fetch it locally, and update the root `main` only when its existing uncommitted files can be preserved without conflict.

- [ ] **Step 8: Verify remote state**

Run: `git ls-remote --heads origin main codex/template-complete-review`

Expected: `main` contains the verified feature commit; feature branch remains available for audit.

