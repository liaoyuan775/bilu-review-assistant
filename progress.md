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
- Resumed Task 8 in the existing linked worktree and confirmed the pushed baseline, intended uncommitted frontend scope, running frontend, and backend route map before browser QA.
- Started Task 8 browser QA in installed Microsoft Edge at 1440x900; initial screen and all sanitized demo rows render correctly with zero console errors or warnings.
- Task 8 browser QA failed the rule-contract check after demo 01: the workspace rendered a legacy `三现` group from the seven-result mock adapter. Root-cause tracing and a regression test are required before visual sign-off.
- Template demo RED/GREEN completed: `backend/tests/test_demo_cases.py` now passes 5/5, proving mock mode returns the 34-rule catalog and Qwen mode calls the template pipeline. Restarted production preview/backend on ports 4173/8787 for fresh browser QA.
- Extended the same demo contract test to cover original/version persistence and mock follow-up re-review; 5/5 still pass. Restarted the non-reloading preview backend and returned the browser to a fresh demo selection.
- Completed the real browser follow-up workflow at 1440x900: selected RISK-001, recorded the actual answer, observed a new document version and appended exact anchors, and cleared the high-risk archive blocker.
- Task 8 mobile QA at 390x844 reports document/body scroll width 375px with no horizontal overflow; console remains at zero errors/warnings.
- Applied the mobile grid and long-token wrapping fix; frontend regression is 11 files / 41 tests passed and the production build completed with 1754 modules. Browser re-verification continues on a fresh demo because reload resets in-memory navigation state.
- Mobile visual re-check passed after the fix: all measured nested containers fit exactly, five status cells and two archive gates remain readable, and the document/problem panes no longer expose horizontal scrollbars.
- Restored the browser to 1440x900 at the page top and captured the final desktop regression screenshot for visual inspection.
- Updated stale legacy transport tests to call the compatibility adapter directly while product demos remain on the 34-rule template pipeline.
- Task 8 complete: desktop/mobile browser QA passed, mock follow-up lifecycle passed, console remained clean, and full backend regression returned 99 passed / 1 optional actual-template skip after the temporary WeChat source disappeared.

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
| Task 8 template demo contract | `pytest -q backend/tests/test_demo_cases.py` | 5 passed |
| Task 8 frontend regression | `npm --prefix frontend run test` | 11 files / 41 tests passed |
| Task 8 frontend production build | `npm --prefix frontend run build` | 1754 modules transformed, exit 0 |
| Task 8 browser QA | Playwright CLI, Edge, 1440x900 and 390x844 | Dynamic template groups, exact anchors, follow-up re-review, zero console errors, no nested horizontal overflow |
| Task 8 selected backend | `pytest -q test_api.py test_demo_cases.py` | 33 passed |
| Task 8 full backend | `pytest -q backend/tests` | 99 passed, 1 optional actual-template test skipped |

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
| 2026-07-18 03:11 | Playwright CLI could not start because Chrome was absent at its default Windows path | 8 | Confirmed the CLI supports `--browser msedge` and Edge exists under Program Files; browser QA will use that installed channel |
| 2026-07-18 03:25 | Task 8 demo contract tests returned seven legacy rules; the Qwen demo test also reached the legacy live endpoint | 9 | RED confirmed the orchestration defect; tests now forbid the legacy entry point and production demos use the template paths |
| 2026-07-18 03:45 | Playwright CLI `run-code` rejected a raw `await page.screenshot(...)` expression | 10 | Use the documented screenshot command/options instead; application state was unaffected |
| 2026-07-18 03:57 | Full backend regression: 11 failed / 89 passed | 11 | Ten failures are stale tests coupling legacy Qwen transport to the now-template demo API; one is the expired WeChat temporary template path. Update test boundaries and locate a current source copy, without restoring legacy product behavior |
