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
- Task 9 RED/GREEN backend complete: four new report/archive tests pass, including PDF/DOCX/JSON content, manifest hashes, immutable archive, and tamper rejection. Related backend suite is 48 passed; frontend remains 41 passed and production build succeeds.
- Task 9 browser flow reached post-follow-up state on a fresh persisted demo; high-risk issue resolved and derived artifacts remain invalidated pending explicit generation.
- Browser generated all four artifacts, enabled archive, and successfully entered immutable archived state. Downloaded the live PDF/DOCX/JSON/manifest to `tmp/docs/task9-live` with recorded SHA-256 values.
- Re-rendered the final eight-page review PDF with embedded Microsoft YaHei and visually inspected every page; Chinese labels, evidence wrapping, page numbers, and the operation-record page have no clipping, overlap, or missing glyphs.
- Restarted the backend, generated the latest A4 follow-up DOCX through the live API, exported it with Microsoft Word, and visually verified the rendered page including Chinese status labels and dynamic PAGE/NUMPAGES fields.
- Task 9 complete: full backend returned 103 passed / 1 optional actual-template skip, frontend returned 41 passed, production build succeeded, OpenAPI was regenerated, and `git diff --check` was clean before the phase commit.
- Task 10 resumed from a live-model failure. Confirmed no stale verifier process, preserved five valid three-run case reports, and traced `gold-06` to one 240-second model read timeout followed by two strict-schema failures in the `offline_delivery` domain.
- Reproduced `gold-06` in isolation and found all retries repeated a duplicate entity ID because correction feedback was null. Added two failing tests, implemented explicit global-unique-ID instructions, and verified the extraction/rule/performance regression set with 24 passed.
- The next single live `gold-06` run reached six metrics at 100%, but its formal three-run gate exposed a stable entity-recall gap: 94.12% applicability/issue/required recall with `CASH-003` and `OFFLINE-001` inconsistent in all runs because their repeat-entity arrays were empty.
- Added a failing prompt-contract test for domain entity arrays, then dynamically injected entity types, required fields, single-occurrence creation, and evidence-free empty-array rules. The new test passed and the related regression set returned 25 passed.
- Entity-aware live diagnostic reached 100% with one withdrawal and one handoff, but the next three-run report scored 91.18% on unrelated timeline facts. Traced the cross-process variability to paragraph IDs based on raw DOCX bytes rather than normalized visible structure.
- Added a RED/GREEN parser regression for identical visible DOCX text with different core metadata. Anchors now use normalized document structure; 37 related tests passed with 1 optional skip, and independently generated gold files produced identical anchor lists and prompt hashes.
- Stable-anchor `gold-06` passed its final three-run live gate with all six metrics at 100%, zero mismatches, and zero sensitive findings.
- `gold-07` passed three live runs. The isolated-case loop stopped at `gold-08` after two 240-second targeted-recheck timeouts around one invalid-anchor response; the same domain completed alone in 55 seconds, identifying targeted recheck concurrency as the reliability boundary.
- A RED/GREEN serial-recheck experiment passed 38 related tests but the live `gold-08` rerun reproduced the identical failure sequence. Concurrency is ruled out; next fix is a domain-filtered focus-only prompt and Schema, and the serial experiment will be removed.
- Replaced the advisory-only recheck with domain-filtered focus paths and focus-only Schema/validation, removed the serial experiment, and passed 40 related tests with 1 optional skip. The exact failing live contact recheck then completed in 11.5 seconds without retry.
- `gold-08` completed three runs after the focus fix, but log inspection found an entity drift hidden by the verifier's status-only stability check. The report is rejected pending a test-backed connection to the full semantic fingerprint.
- Connected the live verifier to the full semantic fingerprint and added entity applicability/count validation. Related tests passed, and `gold-08` then passed three full-fingerprint live runs at six metrics of 100%.
- Added field-path-only semantic drift diagnostics and gold-equivalent value canonicalization; `gold-09`, `gold-10`, `gold-11`, and `gold-12` each passed their current-code three-run live gates at all six metrics of 100%.
- Offline Task 10 verification regenerated 12 DOCX/PDF pairs and 136 rule mutations; all ten offline metrics were 100% with zero prohibited identity, phone, card, URL, or public-IP shapes.
- Added a benchmark that records per-stage/total P50/P95, request count, token usage, and a gold-semantic quality fingerprint; every timed sample must pass facts, entities, rules, and evidence before it is included.
- Formal five-run baseline at domain concurrency 2 produced total P50 135.361s and P95 146.894s. Five-run concurrency 7 produced P50 71.426s and P95 71.819s with the identical quality fingerprint, improving 47.23% and 51.11%.
- Accepted concurrency 7 as the production default. It completed 35/35 requests with zero retry or timeout; concurrency 5 and 3 were not tested because the user requested the highest passing candidate.
- Rewrote the README and technical guide to replace the stale seven-rule/three-present-four-flow, non-persistent, and unverified-model descriptions with the template-driven lifecycle and current boundaries.
- Fresh pre-final regression returned backend 134 passed / 1 optional actual-template skip, frontend 12 files / 44 tests passed, production build 1755 modules, and a refreshed OpenAPI snapshot.
- Pre-merge review blocked landing on false completion after failed-domain retry, cross-domain manual-decision loss, stale lifecycle writes, circular gold evidence, hidden OOXML parts, mixed-run report facts, and unbounded DOCX expansion. Added RED/GREEN coverage and fixed each path without weakening extraction or archive gates.
- SQLite schema v2 now uses revision/CAS; task plus event writes and run/fact/issue completion are transactional. A model response that returns after archive can no longer restore an editable snapshot.
- Failed parallel extraction now carries successful domains and per-domain root diagnostics. Recovery with no partial base reruns all seven domains and requires 92 facts, all entity collections, and 34 rule results before completion.
- Added four static hand-authored natural document mutations and real DOCX/PDF execution. The natural corpus found and fixed missing repeated entities for known counts and online/offline money-domain leakage.
- Fresh regression after review hardening: backend 151 passed / 1 optional actual-template skip, frontend 45 passed, production build 1755 modules, OpenAPI regenerated, and `git diff --check` clean.
- Final combined live gate completed the first 20-document round (12 contract DOCX plus four natural cases in DOCX/PDF) with zero failed domains. The user explicitly waived rounds 2 and 3 and directed the workflow to proceed, so the still-running repeated requests were terminated without treating an absent three-run aggregate as evidence.

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
| Task 9 report/archive tests | `pytest -q test_reports.py test_archive_manifest.py ...` | 48 passed |
| Task 9 frontend regression | `npm --prefix frontend run test` | 11 files / 41 tests passed |
| Task 9 frontend production build | `npm --prefix frontend run build` | 1754 modules transformed, exit 0 |
| Task 9 final PDF visual QA | ReportLab PDF -> Poppler PNG, all pages inspected | 8/8 pages readable; no clipping, overlap, or missing glyphs |
| Task 9 final DOCX visual QA | live API -> Word PDF export -> Poppler PNG | A4, 1/1 page; Chinese labels and dynamic footer verified |
| Task 9 full backend | `backend\.venv\Scripts\python.exe -m pytest -q backend\tests` | 103 passed, 1 optional actual-template test skipped |
| Task 9 OpenAPI export | `backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py` | `docs/openapi.json` updated |
| Task 10 offline quality | `verify_template_quality.py --offline` | 32 documents: 24 contract + 8 natural, 136 mutations, all ten metrics 100%, zero sensitive findings |
| Task 10 isolated live completion | cases `gold-09` through `gold-12`, three runs each | all six metrics 100%, zero mismatches/drift paths/sensitive findings |
| Task 10 natural live coverage | four hand-authored complete/missing/unclear/inconsistent cases, DOCX/PDF | isolated cases calibrated; combined first round completed all 20 documents with zero failed domains; repeated rounds waived by user |
| Task 11 concurrency 2 baseline | `benchmark_template_review.py --runs 5 --domain-concurrency 2` | P50 135.361s, P95 146.894s, quality passed |
| Task 11 concurrency 7 candidate | `benchmark_template_review.py --runs 5 --domain-concurrency 7 --baseline ...` | identical quality; P50 -47.23%, P95 -51.11%; accepted |
| Pre-final backend regression | `backend\.venv\Scripts\python.exe -m pytest -q backend\tests` | 151 passed, 1 optional actual-template skip |
| Pre-final frontend regression | `npm --prefix frontend run test` | 13 files / 45 tests passed |
| Pre-final production build | `npm --prefix frontend run build` | 1755 modules transformed, exit 0 |
| Pre-final OpenAPI export | `backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py` | `docs/openapi.json` updated |

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
| 2026-07-18 04:12 | `pip install reportlab==4.4.9` timed out while downloading the Pillow wheel | 12 | Retry once with a 120-second read timeout; fall back to installed PyMuPDF if the dependency remains unavailable |
| 2026-07-18 04:31 | Bundled Poppler wrapper returned `The system cannot find the path specified` | 13 | Inspect the wrapper and invoke its resolved runtime executable explicitly before changing the PDF implementation |
| 2026-07-18 04:37 | Word COM exported the DOCX successfully, then `Quit()` returned RPC unavailable | 14 | Confirm output and process cleanup; treat as post-export automation cleanup if no WINWORD process remains |
| 2026-07-18 04:41 | Windows PowerShell 5 rejected `Invoke-RestMethod -NoProxy` | 15 | Remove the unsupported parameter for localhost; no task or artifact was created by the failed script |
