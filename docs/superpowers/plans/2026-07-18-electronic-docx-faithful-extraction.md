# Electronic DOCX Faithful Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faithfully transcribe electronic DOCX checkbox states into question-answer text, extract a source-bounded complete victim profile, and expose the result consistently to the seven review domains, API, and frontend.

**Architecture:** `app/parsing/openxml.py` converts supported OOXML checkbox representations into inline text markers before the existing question-answer state machine runs. `app/review/victim.py` receives the structured `ParsedDocument`, reads only the body profile header plus an explicit basic-information Q&A fallback, while prompts and UI consume the existing contracts with five additive profile fields.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, lxml, pytest, React 18, TypeScript, Vitest, OpenAPI JSON.

## Global Constraints

- Preserve `[选中]`, `[未选]`, and `[状态不明]` in original document order beside their option text.
- Do not create a fixed 33-question or option catalog, decide single versus multiple choice, remove unselected options, or use VLM to guess electronic checkbox state.
- Keep `QuestionAnswerBlock` unchanged; checkbox markers remain ordinary text in `answer`.
- Unknown electronic checkbox encodings produce `[状态不明]` and a confirmable `DocumentWarning` without failing the whole document.
- Profile extraction uses body content before the first `问：` as its primary source; only a semantically explicit “基本情况/个人情况” Q&A may fill fields still missing.
- Do not restore the migrated flat `app/services/*`, `app/models.py`, or other old modules.
- Do not stage template DOCX/PDF files, generated output, Word lock files, `frontend/src/styles.css`, unrelated docs, logs, or databases.
- Use the approved regression fixture `backend/基于原模板填写-冒充客服退款诈骗询问笔录.docx` without committing it.

---

### Task 1: Preserve the package migration as a clean baseline

**Files:**
- Modify: `.idea/bilu.iml`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/main.py`
- Delete: migrated flat modules under `backend/app/` and `backend/app/services/`
- Create: package modules under `backend/app/api`, `core`, `data`, `llm`, `parsing`, `reporting`, `review`, and `storage`
- Modify: migration-related `backend/scripts/*.py`
- Modify: migration-related `backend/tests/*.py`

**Interfaces:**
- Consumes: the user's completed flat-module-to-package migration.
- Produces: an importable package baseline where `app.main` registers 23 routes and the backend suite passes before feature work.

- [ ] **Step 1: Recheck the migration-only diff and exclusions**

Run:

```powershell
git status --short
git diff --name-status
```

Expected: old flat modules are deleted, replacement package directories are untracked, and templates/generated files remain visibly separable and unstaged.

- [ ] **Step 2: Verify the migrated package baseline once**

Run:

```powershell
$env:PYTHONPATH='backend'; backend\.venv\Scripts\python.exe -c "from app.main import app; print(len(app.routes))"
Set-Location backend; .venv\Scripts\python.exe -m pytest -q tests
```

Expected: `23` routes and `151 passed, 1 skipped` (warnings may be reported separately).

- [ ] **Step 3: Stage only migration-owned paths and inspect the index**

Run explicit `git add` commands for `.idea/bilu.iml`, `backend/requirements.txt`, migrated backend source, scripts, and tests. Then run:

```powershell
git diff --cached --name-status
```

Expected: no DOCX/PDF, `output/`, lock file, unrelated spec/plan, `docs/project-technical-guide.md`, or `frontend/src/styles.css` is staged.

- [ ] **Step 4: Commit the baseline**

```powershell
git commit -m "refactor: organize backend modules into packages"
```

Expected: one migration-only commit, leaving all excluded user files untouched.

### Task 2: Transcribe electronic checkbox states in OOXML order

**Files:**
- Modify: `backend/app/parsing/openxml.py`
- Test: `backend/tests/test_template_document_parser.py`

**Interfaces:**
- Consumes: paragraph/table/story XML nodes in `read_docx_parts(content: bytes)`.
- Produces: `OpenXmlDocument.blocks` whose text contains inline checkbox markers, plus `DocumentWarning(code="checkbox_state_unknown", ...)` for undecidable boxes.

- [ ] **Step 1: Add failing text-character and `w:sym` tests**

Extend the existing DOCX rewrite helpers to create XML containing ordinary `☑/☒/☐/□` text and `w:sym` runs. Assert ordered transcription such as:

```python
assert "[选中] 电话 [未选] 短信 [选中] APP" in parsed.text
assert parsed.questionAnswers[0].answer == "[选中] 电话 [未选] 短信 [选中] APP"
```

For `Wingdings 2 / 00A3`, assert `[未选]` is retained rather than disappearing.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q tests/test_template_document_parser.py -k "checkbox or wingdings"
```

Expected: FAIL because `_node_text` currently ignores checkbox symbols and does not normalize text glyphs.

- [ ] **Step 3: Implement ordered glyph and symbol transcription**

Add namespace constants and small helpers in `openxml.py` that map:

```python
TEXT_CHECKBOX_MARKERS = {
    "☑": "[选中]",
    "☒": "[选中]",
    "☐": "[未选]",
    "□": "[未选]",
}
```

Iterate descendant nodes in their existing XML order. Normalize checkbox glyphs inside `w:t`, and interpret supported `w:sym` font/character pairs without reordering adjacent option text.

- [ ] **Step 4: Add failing content-control, legacy form, and unknown-state tests**

Create minimal XML fixtures for `w14:checkbox` checked/unchecked state and legacy `w:ffData/w:checkBox`. Add one structurally recognizable checkbox with an unsupported state and assert:

```python
assert "[状态不明] 其他" in parsed.text
assert any(w.code == "checkbox_state_unknown" for w in parsed.warnings)
```

- [ ] **Step 5: Run the new tests and verify RED**

Run the same focused command. Expected: the new control/form tests FAIL for missing state handling.

- [ ] **Step 6: Implement control/form state handling and warning propagation**

Thread a warning collector through body/story text extraction. Decode explicit truthy/falsy OOXML values, emit exactly one marker per checkbox control, and append a warning with the source part name for an unknown state. Do not warn when a document contains no checkbox.

- [ ] **Step 7: Run the focused parser tests once**

Run the focused command. Expected: PASS, including stable Q&A order and no regression to ordinary paragraph/table/header/footer extraction.

- [ ] **Step 8: Commit checkbox transcription**

```powershell
git add backend/app/parsing/openxml.py backend/tests/test_template_document_parser.py
git commit -m "feat: transcribe electronic docx checkboxes"
```

### Task 3: Bound victim-profile sources and add missing fields

**Files:**
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/review/victim.py`
- Modify: `backend/app/review/review.py`
- Test: `backend/tests/test_victim_profile.py`
- Test: `backend/tests/test_review_lifecycle.py`

**Interfaces:**
- Consumes: `extract_victim_profile(document: ParsedDocument)`.
- Produces: `VictimProfile` with nullable `birthDate`, `occupation`, `education`, `registeredAddress`, and `isNpcRepresentative`, without consuming unrelated case Q&A or header/footer text.

- [ ] **Step 1: Add failing source-boundary and new-field tests**

Build a `ParsedDocument` whose body header contains victim fields, whose header/footer and later Q&A contain conflicting officer/case values, and whose explicit “基本情况” answer supplies a missing occupation. Assert:

```python
assert profile.employer == "某测试科技有限公司"
assert profile.occupation == "软件工程师"
assert profile.birthDate == "1990年1月2日"
assert profile.education == "本科"
assert profile.registeredAddress == "湖南省长沙市测试区"
assert profile.isNpcRepresentative is False
```

Add separate cases proving an unrelated Q&A cannot fill occupation/employer and explicit “是/否人大代表” maps to `True/False`, otherwise `None`.

- [ ] **Step 2: Run victim-profile tests and verify RED**

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q tests/test_victim_profile.py tests/test_review_lifecycle.py -k "victim or profile"
```

Expected: FAIL because the function accepts flat text, scans the full document, and the five fields do not exist.

- [ ] **Step 3: Extend the Pydantic contract**

Add nullable fields with `None` defaults:

```python
birthDate: str | None = None
occupation: str | None = None
education: str | None = None
registeredAddress: str | None = None
isNpcRepresentative: bool | None = None
```

- [ ] **Step 4: Implement structured source selection and minimal fallback**

Change `extract_victim_profile` to accept `ParsedDocument`. Select only `SourceType.NATIVE_TEXT`/`TABLE` body paragraphs before the first question marker for primary matching. Inspect `document.questionAnswers` only when the question explicitly contains `基本情况` or `个人情况`, and only use that answer to fill fields still `None`.

Keep existing explicit-value regexes, add patterns for the five new fields, and never infer age from birth date, employer from occupation, or representative status from silence.

- [ ] **Step 5: Update review orchestration call sites**

Replace both upload and demo calls with:

```python
task.victimProfile = extract_victim_profile(task.document)
```

- [ ] **Step 6: Run the focused profile/lifecycle tests once**

Run the focused command. Expected: PASS and the officer-unit collision is covered by regression.

- [ ] **Step 7: Commit profile extraction**

```powershell
git add backend/app/core/models.py backend/app/review/victim.py backend/app/review/review.py backend/tests/test_victim_profile.py backend/tests/test_review_lifecycle.py
git commit -m "feat: expand source-bounded victim profiles"
```

### Task 4: Explain checkbox markers to all seven review domains

**Files:**
- Modify: `backend/app/review/extraction.py`
- Test: `backend/tests/test_template_extraction.py`

**Interfaces:**
- Consumes: Q&A answer text containing the three inline markers.
- Produces: every `build_domain_prompt(...)` with a shared, explicit marker interpretation policy.

- [ ] **Step 1: Add a failing prompt-contract test**

For each configured domain, assert the built prompt contains all three markers and states that `[未选]` is not an affirmative case fact, `[状态不明]` remains unknown, and selection count does not represent parser-level single/multiple-choice validation.

- [ ] **Step 2: Run the test and verify RED**

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q tests/test_template_extraction.py -k checkbox
```

Expected: FAIL because the marker policy is absent.

- [ ] **Step 3: Add one shared marker instruction block**

Insert concise Chinese instructions into `build_domain_prompt` before the anchored Q&A text. Do not modify the seven-domain JSON Schema, rule catalog, or `QuestionAnswerBlock`.

- [ ] **Step 4: Run the focused prompt test once**

Run the focused command. Expected: PASS.

- [ ] **Step 5: Commit prompt semantics**

```powershell
git add backend/app/review/extraction.py backend/tests/test_template_extraction.py
git commit -m "feat: explain checkbox markers in review prompts"
```

### Task 5: Keep frontend profile display aligned with the API

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/VictimProfileCard.tsx`
- Modify: `frontend/src/VictimProfileCard.test.tsx`
- Modify: `frontend/src/victimProfile.test.ts` only if shared completeness behavior requires coverage

**Interfaces:**
- Consumes: additive `VictimProfile` JSON fields from the backend.
- Produces: typed and labeled display of all profile fields without changing the card's existing layout system.

- [ ] **Step 1: Add a failing card test**

Render a complete profile and assert labels/values for `出生日期`, `职业`, `文化程度`, `户籍所在地`, and `是否人大代表`; assert booleans display as `是`/`否` and null remains the existing missing-value presentation.

- [ ] **Step 2: Run the component test and verify RED**

```powershell
npm --prefix frontend run test -- src/VictimProfileCard.test.tsx
```

Expected: FAIL because the TypeScript fields and rows are absent.

- [ ] **Step 3: Extend the TypeScript interface and field rows**

Add:

```typescript
birthDate: string | null;
occupation: string | null;
education: string | null;
registeredAddress: string | null;
isNpcRepresentative: boolean | null;
```

Add matching `VictimProfileCard` row definitions and a boolean formatter. Do not modify `frontend/src/styles.css`.

- [ ] **Step 4: Run focused frontend tests once**

```powershell
npm --prefix frontend run test -- src/VictimProfileCard.test.tsx src/victimProfile.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit frontend contract changes**

```powershell
git add frontend/src/types.ts frontend/src/VictimProfileCard.tsx frontend/src/VictimProfileCard.test.tsx frontend/src/victimProfile.test.ts
git commit -m "feat: display complete victim profile"
```

### Task 6: Regenerate OpenAPI and validate the real fixture

**Files:**
- Modify: `docs/openapi.json`
- Modify: `backend/tests/test_template_document_parser.py`
- Modify: `backend/tests/test_victim_profile.py`
- Modify: `docs/project-technical-guide.md` only where its current contract description is stale
- Modify: `docs/superpowers/specs/2026-07-18-electronic-docx-faithful-extraction-design.md`

**Interfaces:**
- Consumes: final backend models/parser and the local approved DOCX fixture.
- Produces: checked-in API snapshot and an environment-skippable regression proving the fixture has 33 Q&A blocks and the correct victim employer.

- [ ] **Step 1: Add the real-fixture regression**

Skip only when the local fixture is absent. Parse it with `parse_document`, then assert:

```python
assert len(parsed.questionAnswers) == 33
assert extract_victim_profile(parsed).employer == "某测试科技有限公司"
```

Inspect the fixture's `word/document.xml` before asserting checkbox markers. If the filled file contains no checkbox node or glyph because the author replaced options with natural-language answers, record zero markers as a source-file fact and rely on Task 2's synthetic OOXML fixtures for checkbox adjacency/order coverage.

- [ ] **Step 2: Run the regression once**

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q tests/test_template_document_parser.py tests/test_victim_profile.py
```

Expected: PASS against the named fixture with 33 Q&A blocks and the correct complete profile. If its actual electronic representation exposes an unsupported but recognizable state, the result must be `[状态不明]` plus warning rather than a guess.

- [ ] **Step 3: Regenerate and inspect OpenAPI**

```powershell
backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py
rg -n 'birthDate|occupation|education|registeredAddress|isNpcRepresentative' docs/openapi.json
```

Expected: all five properties are present under `VictimProfile` and nullable/default-compatible.

- [ ] **Step 4: Update only stale technical documentation**

Correct package paths and document the faithful marker/profile boundaries. Preserve unrelated user edits in `docs/project-technical-guide.md` and avoid broad reformatting.

- [ ] **Step 5: Commit fixture regression, API snapshot, spec correction, and required docs**

Stage only the tests and documentation actually changed; do not stage the fixture itself.

```powershell
git commit -m "test: cover electronic record extraction contract"
```

### Task 7: Final verification and scope audit

**Files:**
- Verify only: all files changed by Tasks 2-6

**Interfaces:**
- Consumes: completed implementation.
- Produces: evidence that backend, frontend, build, fixture behavior, and commit scope satisfy the approved design.

- [ ] **Step 1: Run one final backend suite**

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q tests
```

Expected: all tests pass; the prior baseline count grows by the new tests, with the same intentional skip unless the fixture makes it runnable.

- [ ] **Step 2: Run one final frontend suite and build**

```powershell
npm --prefix frontend run test
npm --prefix frontend run build
```

Expected: all Vitest tests pass and TypeScript/Vite build succeeds.

- [ ] **Step 3: Audit the final diff and exclusions**

```powershell
git status --short
git log --oneline -7
git diff HEAD~5 --stat
```

Expected: feature commits contain only planned source/tests/API/docs; local templates, output, Word lock files, unrelated plans/specs, styles, logs, and databases remain uncommitted and untouched.

- [ ] **Step 4: Report exact fixture output**

Report the actual Q&A count, checkbox-marker counts, extracted `VictimProfile`, backend/frontend test totals, build result, warnings, and all intentionally excluded working-tree files. Do not claim support for scanned or handwritten checkboxes.
