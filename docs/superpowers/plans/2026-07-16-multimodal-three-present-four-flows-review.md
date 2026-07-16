# Multimodal Three-Present Four-Flows Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept text, scanned, and mixed PDF plus DOCX content, normalize it with multimodal assistance, and review it against seven evidence-grounded Three-Present Four-Flows rules.

**Architecture:** Native extraction remains the source of truth when usable; scanned pages and embedded images are transcribed through the configured OpenAI-compatible multimodal Qwen endpoint. Review is a separate model call driven by structured hard rules and optional reference hints, followed by deterministic result and evidence validation.

**Tech Stack:** FastAPI, Pydantic, python-docx, PyMuPDF, httpx, React, TypeScript, Vitest, pytest.

## Global Constraints

- Support `.pdf` and `.docx`, maximum 20 MB; reject legacy `.doc` with a conversion message.
- Never log file bytes, extracted text, model request bodies, or API keys.
- Hard status derives only from Three-Present Four-Flows `requiredFacts`; Baidu Qianfan content is supplementary.
- Model or evidence validation failure produces a failed task with no partial results and no automatic local fallback.
- Tasks remain process-memory-only and all uploaded material must be desensitized.
- The workspace is not a Git repository, so commit steps become local diff/review checkpoints.

---

### Task 1: Structured Document Blocks and Multimodal Transcription

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/models.py`
- Create: `backend/app/services/vision.py`
- Modify: `backend/app/services/parser.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `DocumentParagraph(text: str, sourceType: SourceType, confidence: float | None)`.
- Produces: `async parse_document(filename: str, content: bytes) -> ParsedDocument`.
- Produces: `async transcribe_image(image: bytes, media_type: str, label: str) -> VisionTranscript`.

- [ ] **Step 1: Add failing parser tests**

Add tests proving DOCX tables become `sourceType="table"`, DOCX images call the vision adapter, blank/scanned PDF pages call the adapter, and `.doc` returns `unsupported_legacy_word`.

- [ ] **Step 2: Run parser-focused tests and confirm failure**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py -k "docx or scanned or legacy"`

Expected: failures because paragraphs are strings, scanned PDF is rejected, and `.doc` has no dedicated error.

- [ ] **Step 3: Add document block models and PyMuPDF**

Add `PyMuPDF==1.25.1`. Replace `DocumentPage.paragraphs: list[str]` with `list[DocumentParagraph]` and define:

```python
class SourceType(StrEnum):
    NATIVE_TEXT = "native_text"
    TABLE = "table"
    VISION = "vision"

class DocumentParagraph(BaseModel):
    text: str
    sourceType: SourceType
    confidence: float | None = None
```

- [ ] **Step 4: Implement multimodal transcription**

Send a JSON-only transcription request with an `image_url` data URL and return validated paragraph strings plus an optional confidence value. Convert HTTP, response-shape, and JSON failures to stable `AppError` codes prefixed with `vision_`.

- [ ] **Step 5: Implement async PDF and DOCX normalization**

Use PyMuPDF for real PDF pages, native text extraction, image detection, and PNG rendering. Use python-docx for ordered paragraphs/tables and relationship-backed embedded images. Merge exact duplicate vision/native paragraphs and retain source types.

- [ ] **Step 6: Run parser tests**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py -k "docx or pdf or scanned or legacy"`

Expected: all selected tests pass.

### Task 2: Seven Hard Rules and Supplementary Hints

**Files:**
- Replace: `backend/rules.json`
- Modify: `backend/app/models.py`
- Modify: `backend/app/data.py`
- Modify: `backend/app/services/qwen.py`
- Modify: `backend/app/services/analyzer.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Rules expose `group`, `requiredFacts`, `referenceHints`, `evidencePolicy`, and `source`.
- Review results expose `group` and `advisories` while preserving existing status and manual-decision fields.

- [ ] **Step 1: Add failing rule-contract tests**

Assert the API returns exactly seven hard rules in groups `三现` and `四流`, every rule has a working-rule source, and supplementary hints cannot appear in `missingFacts` unless also listed in `requiredFacts`.

- [ ] **Step 2: Run rule tests and confirm failure**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py -k "rules or qwen"`

Expected: failures against the existing ten base/TEL keyword rules.

- [ ] **Step 3: Replace rules with seven structured rules**

Create one rule each for `案发现场`, `涉案现物`, `电子现痕`, `人员流`, `信息流`, `资金流`, and `行为流`. Keep Qianfan-derived account/chat/APP/delivery/rebate/third-party items in `referenceHints` only.

- [ ] **Step 4: Update the Qwen review contract**

Build prompts from structured rules and `DocumentParagraph.text`. Require `ruleId`, `status`, `missingFacts`, `evidence`, `evidenceLocation`, `reason`, `suggestedQuestion`, and `advisories`. Validate all rule IDs, hard missing facts, locations, evidence text, and conditional applicability.

- [ ] **Step 5: Remove upload fallback dependence on the keyword analyzer**

Make Qwen the upload review path. Retain the local analyzer only for explicit demo-mode fixtures, adapting it to document blocks and the new rule schema so existing demo development remains usable without acting as a model failure fallback.

- [ ] **Step 6: Run rule and API tests**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py`

Expected: all backend API tests pass with seven results.

### Task 3: Task Pipeline and Status Semantics

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/scripts/verify_qwen.py`
- Modify: `docs/openapi.json`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Task statuses include `parsing`, `recognizing`, `checking`, `validating`, `completed`, and `failed`.
- Upload defaults to `qwen`; explicit model failures clear `results`.

- [ ] **Step 1: Add failing status and failure-path tests**

Assert OpenAPI exposes the new statuses, upload invokes async parsing before review, vision/review failures clear results, and successful uploads return seven results.

- [ ] **Step 2: Run status tests and confirm failure**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py -k "status or failure or upload"`

- [ ] **Step 3: Implement status transitions**

Await `parse_document`, save `recognizing` when vision is required, set `checking` for review, and set `validating` immediately before deterministic validation completes. Preserve explicit `AppError` codes and clear results on every failure.

- [ ] **Step 4: Regenerate OpenAPI and update model verification**

Run: `backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py`

Update verification to expect seven results and the working-rule source without printing secrets.

- [ ] **Step 5: Run the backend suite**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests`

Expected: all tests pass.

### Task 4: Frontend Upload and Grouped Review Results

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/workflowData.ts`
- Modify: `frontend/src/workflowData.test.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Frontend consumes structured paragraphs, result groups, advisories, and new task statuses.
- Upload accepts `.pdf,.docx`; the UI explains scanned/mixed PDF and legacy `.doc` conversion.

- [ ] **Step 1: Add failing frontend contract tests**

Extend workflow-data tests to require multimodal normalization, Three-Present Four-Flows review, evidence validation, and the model-failure path.

- [ ] **Step 2: Run frontend tests and confirm failure**

Run: `npm --prefix frontend run test`

- [ ] **Step 3: Update types and upload state**

Represent paragraph objects, `group`, `advisories`, and `recognizing`/`validating`. Remove the user-selectable local upload mode and disable upload with a clear message when Qwen is unavailable.

- [ ] **Step 4: Group results and separate supplementary attention**

Render `三现` and `四流` section labels, keep hard missing facts in the existing fact list, and show advisories under `补充关注` without adding them to problem counts.

- [ ] **Step 5: Update the execution flow and styling**

Replace the old generic-rule nodes with file normalization, multimodal recognition, Three-Present Four-Flows review, evidence validation, and manual action. Keep responsive dimensions stable.

- [ ] **Step 6: Run frontend tests and build**

Run: `npm --prefix frontend run test`

Run: `npm --prefix frontend run build`

Expected: both commands succeed.

### Task 5: End-to-End Verification and Documentation

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- README documents supported formats, multimodal transmission boundary, seven rules, and no legacy `.doc` support.

- [ ] **Step 1: Update operating documentation**

Document text/scanned/mixed PDF, DOCX text/tables/images, `.doc` conversion, model-only upload review, in-memory storage, and desensitization requirements. Keep `.env.example` values as non-secret placeholders.

- [ ] **Step 2: Run all automated verification**

Run: `npm run test`

Run: `npm run build`

Expected: frontend and backend tests pass; TypeScript, Vite, and Python compilation succeed.

- [ ] **Step 3: Verify the configured model adapter**

Run: `npm run verify:model`

Expected: either a successful seven-rule result or a stable, secret-free model/vision error code. A network outage is reported as an external verification limitation, not hidden.

- [ ] **Step 4: Review workspace changes**

Because no Git metadata exists, inspect the touched-file list and verify every changed file traces to this feature; do not modify unrelated generated documents or screenshots.
