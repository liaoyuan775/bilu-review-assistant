# 执行进度

## 2026-07-18

- Created local branch and isolated worktree: `codex/template-complete-review`.
- Pushed the branch to `origin/codex/template-complete-review`.
- Wrote the approved design and 12-task implementation plan.
- Self-review found no placeholder markers and `git diff --check` reported no whitespace errors.
- Installed isolated Node and Python dependencies.
- Baseline: backend 49 passed, frontend 36 passed, frontend production build passed.
- Added a synthetic bad-CRC DOCX regression and an optional integration test for the provided internal template.
- Replaced all-or-nothing `python-docx` package loading with selective Open XML body/media reading.
- Actual template result: 144 paragraphs, 33 question markers, full start/end content, and four recoverable media warnings.
- Added deterministic paragraph IDs and exact global character ranges for DOCX/PDF/OCR blocks.
- Preserved DOCX header/footer stories as distinct source types without changing the 144-body-paragraph oracle.
- Preserved native PDF text-block coordinates from PyMuPDF layout dictionaries.
- Reconstructed same-paragraph, cross-paragraph, and cross-page question/answer blocks with stable source anchors.
- Separated parenthetical template guidance from case answers and classified blank/unclear answers deterministically.
- Verified the supplied template reconstructs exactly 33 question/answer blocks and keeps basic-information guidance out of facts.
- Added a versioned internal-template catalog with source SHA-256, 33 source-backed question rules, one structural rule, and all 15 review groups.
- Added a network-free deterministic engine for applicability, required facts, repeated entities, amount relationships, and chronology.
- Added seven strict Qwen fact-extraction domains using the configured model, stable anchors, schema/tool fallback, and one validation retry.
- Excluded reconstructed template guidance from prompts and rejected missing, invalid, or guidance-only evidence anchors.
- Routed uploads through template facts plus deterministic rules; retained the legacy demo adapter only as compatibility coverage.
- Published the 34 internal-template rules through the health and rule APIs instead of seven three/four-flow rules.
- Added explicit SQLite schema v1 migrations for documents, versions, runs, facts, issues, append-only events, and artifacts while retaining legacy task snapshots.
- Added controlled content-addressed original storage with traversal prevention, atomic writes, and SHA-256 verification on read.
- Connected uploads to original/version/run/fact/issue/artifact audit records and exposed version, action, follow-up, retry, warning, download, and archive endpoints.
- Added affected-domain follow-up re-review, append-only operator events, archived read-only enforcement, and explicit archive gates.
- Removed the configured Qwen provider's unsupported `uniqueItems` schema keyword; a synthetic strict-schema request then returned HTTP 200.

## Verification Log

| Phase | Command | Result |
|-------|---------|--------|
| Isolated backend baseline | `pytest -q tests` | 49 passed, 6 pre-existing warnings |
| Isolated frontend baseline | `npm run test` | 10 files / 36 tests passed |
| Isolated frontend build | `npm run build` | 1750 modules transformed, exit 0 |
| Tolerant parser full backend | `pytest -q tests` with actual template path | 51 passed |
| Parser-compatible frontend | `npm run test` | 36 passed |
| Parser-compatible build | `npm run build` | exit 0 |
| Task 2 selected backend | `pytest -q test_template_document_parser.py test_parser.py test_api.py` with actual template path | 35 passed |
| Task 2 full backend | `pytest -q tests` with actual template path | 54 passed |
| Task 2 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 2 production build | `npm run build` | 1750 modules transformed, exit 0 |
| Task 3 selected backend | `pytest -q test_question_answer.py test_template_document_parser.py test_api.py` with actual template path | 40 passed |
| Task 3 full backend | `pytest -q tests` with actual template path | 61 passed |
| Task 3 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 3 production build | `npm run build` | 1750 modules transformed, exit 0 |
| Task 4 catalog and engine | `pytest -q test_template_rule_catalog.py test_template_rule_engine.py` | 10 passed |
| Task 4 full backend | `pytest -q tests` with actual template path | 71 passed |
| Task 4 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 4 production build | `npm run build` | 1750 modules transformed, exit 0 |
| Task 5 selected backend | `pytest -q test_template_extraction.py test_template_rule_engine.py test_api.py` | 44 passed |
| Task 5 full backend | `pytest -q tests` with actual template path | 80 passed |
| Task 5 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 5 production build | `npm run build` | 1750 modules transformed, exit 0 |
| Task 6 persistence | `pytest -q test_template_store.py test_store.py` | 9 passed |
| Task 6 full backend | `pytest -q tests` with actual template path | 88 passed |
| Task 6 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 6 production build | `npm run build` | 1750 modules transformed, exit 0 |
| Task 7 lifecycle and API | `pytest -q test_review_lifecycle.py test_template_store.py test_store.py test_api.py` | 48 passed |
| Task 7 strict-schema live compatibility | synthetic `header_procedure` request using configured model | HTTP 200 |
| Task 7 full backend | `pytest -q tests` with actual template path | 100 passed |
| Task 7 OpenAPI export | `python scripts/export_openapi.py` | `docs/openapi.json` updated |
| Task 7 frontend regression | `npm run test` | 10 files / 36 tests passed |
| Task 7 production build | `npm run build` | 1750 modules transformed, exit 0 |

## Error Log

| Time | Error | Attempt | Resolution |
|------|-------|---------|------------|
| 2026-07-18 00:24 | Actual-template test expected more than 4000 normalized characters; parser returned all 144 paragraphs in 3623 characters | 1 | Replaced arbitrary size threshold with exact paragraph/question/key-content assertions |
| 2026-07-18 00:25 | Test counted only the 32 paragraph-leading questions | 2 | Corrected oracle to 33 question markers: 32 paragraph-leading plus one same-paragraph rights-notice question |
| 2026-07-18 00:35 | Header/footer preservation made the actual-template aggregate block count 145 | 3 | Verified the source split is 144 native body blocks plus one footer and scoped the assertion accordingly |
| 2026-07-18 00:35 | Scanned-PDF API test expected the old three-field paragraph schema | 4 | Updated the contract assertion to include stable ID, offsets, and nullable bbox |
| 2026-07-18 00:52 | A fact with `clarity=unknown`, evidence, and no normalized value was classified as missing | 5 | Separated missing facts from present-but-unclear facts before checking normalized value |
| 2026-07-18 01:10 | Seven legacy Qwen transport tests received the new domain schema through the demo route | 6 | Kept demo protocol tests on the legacy adapter and switched only the upload pipeline to template extraction |
| 2026-07-18 01:40 | Configured Qwen returned HTTP 400 with `Grammar error: Unimplemented keys: ["uniqueItems"]` | 7 | Added a provider-compatibility regression, removed `uniqueItems`, and verified the same strict schema returns HTTP 200 |
