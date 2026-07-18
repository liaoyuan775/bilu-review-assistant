# 实施发现

## Baseline

- Branch: `codex/template-complete-review`
- Base: `2d78f11 feat: optimize police review workflow and diagnostics`
- Remote tracking: `origin/codex/template-complete-review`
- Root checkout has unrelated uncommitted files; all implementation occurs in this isolated worktree.

## Confirmed Input Defect

- The provided DOCX contains readable `word/document.xml` but `word/media/image1.png` has a bad CRC.
- Current `python-docx` loading fails the whole document with `parse_failed`; selective Open XML reading is the required root-cause fix.

## Decisions

- Use the internal template as rule authority.
- Use existing Qwen only for evidence-backed extraction/semantic review.
- Derive completeness and consistency deterministically.
- Keep exact evidence and append-only human actions through archive.
## 2026-07-18 Task 8 resume verification

- The linked worktree remains on `codex/template-complete-review` at pushed commit `0402821`; only the intended Task 8 frontend files are modified or untracked.
- The running frontend responds at `http://127.0.0.1:4173`; the backend health endpoint is `/api/v1/health` rather than `/health`.
- The Task 8 workspace exposes server-driven groups, six review statuses, exact evidence anchors, follow-up capture, warning/domain recovery, artifact links, and archive gates. PowerShell display mojibake is an output-codepage issue; source files remain UTF-8.
- Playwright desktop QA at 1440x900 renders the full new-review screen, all seven sanitized demos, the 34-rule label, Qwen health, and the use-boundary notice without visible clipping. Browser console: 0 errors, 0 warnings.
- Browser QA found a contract mismatch after opening demo 01: the new dynamic workspace receives the legacy seven-item mock payload and visibly renders the old `三现` group. The mock demo adapter must emit the 34-rule internal-template contract before Task 8 can pass.
- Demo 01 contains syntactically complete identity, phone, card, URL, and IP-shaped values despite test labels. Task 10's sensitive-pattern gate must replace these with deliberately invalid/non-production tokens.
- The demo mismatch originated in `process_demo`: both mock and Qwen demo modes bypassed `run_template_review`. The mock builder now covers all 34 catalog rules with template groups, severities, stable anchor IDs, and one high-risk incomplete item; Qwen demos now use the same template pipeline as uploads.
- Demo tasks still lacked persisted document/version IDs, so `record_follow_up_answer` would reject the quick demo with `task_not_completed` even though the UI offered the action. Mock follow-up also needs a deterministic local refresh rather than an affected-domain Qwen call.
- Fresh browser verification now shows the persisted demo version prefix, original-artifact link, three missing artifact gates, one high-risk gate, exact highlighted anchors, and an enabled follow-up drawer with the template-derived question.
- The browser follow-up flow completes end to end in mock mode: the document version changes, appended question and answer receive stable highlighted anchors, the high-risk issue changes to covered/resolved, actionable count becomes zero, and only the three Task 9 artifact gates remain.
- After the full desktop interaction, the browser console still has zero errors and warnings. At 390x844 the app switches to its compact header and single-column review workspace; controls and document text remain represented in the accessibility snapshot.
- Visual inspection of the 390x844 screenshot found nested horizontal overflow despite root-level width passing: the metrics row shows vertically broken labels and the document pane exposes a horizontal scrollbar. Mobile sign-off is blocked until those containers fit without sideways scrolling.
- Browser measurements: `.template-metrics` is 350px client / 730px scroll width, while `.document-scroll` is 334px client / 376px scroll width and its first `.document-page` is 313px / 365px. The metrics fix should use a five-column mobile grid; document overflow requires identifying the exact descendant rather than clipping it.
- Post-fix browser measurements at 390x844 are exact fits: metrics 350/350, archive gates 350/350, document scroll 334/334, and page 313/313. The long URL wraps and no nested horizontal scrolling remains.
- The supplied WeChat temporary template path no longer exists and no matching DOCX remains under its July temp root. The optional actual-template integration test must therefore run without `BILU_TEMPLATE_PATH` in this session; prior exact 144-body-block/33-question evidence remains recorded.
- Full-suite legacy failures were test-boundary drift: transport tests still reached the demo API even though demos now correctly use the template pipeline. Legacy protocol coverage is retained by direct `qwen.review_with_qwen` calls; product API assertions now use the 34-rule contract and artifact archive gate.

## 2026-07-18 Task 9 artifact generation

- Backend venv has `python-docx`, PyMuPDF, and pypdf but not ReportLab. Bundled Poppler exposes `pdftoppm` and `pdfinfo`; LibreOffice is unavailable.
- Generate artifacts explicitly after operator handling so reports cannot silently predate follow-up actions. Require `review_pdf`, `follow_up_docx`, `structured_json`, and `archive_manifest`; manual mutations must invalidate derived summaries until regeneration.
- Use python-docx with PAGE/NUMPAGES fields for the follow-up document and pinned ReportLab for the Chinese PDF, then render every page through bundled Poppler.
- Fresh Task 9 browser state exposes `生成归档产物`, reports four missing artifacts, keeps archive disabled, and retains the high-risk follow-up gate before generation.
- Live Task 9 flow generated four links, cleared all gates, archived successfully, and kept downloads available in read-only state.
- PDF pages 1-4 have no clipping or overlap, but CID font substitution visibly inserts spaces inside Latin rule IDs and severity/model words. This fails document polish; embed Microsoft YaHei and regenerate before inspecting all pages.
- After embedding Microsoft YaHei, regenerated PDF pages 1-4 show intact rule IDs, model names, `mock`, and severity words with no clipping, overlap, missing glyphs, or substitution warnings. Pagination remains A4, 8 pages.
- PDF pages 5-8 also pass visual inspection; the manual-log/disclaimer section is intentionally isolated on the final page and footer numbering is continuous through 8/8.
- Word rendering exposed the python-docx default Letter page size. Added a regression requiring 21.0 x 29.7 cm and set the generated DOCX section to A4.

## 2026-07-18 Task 10 live quality gate

- Five isolated case reports (`gold-01` through `gold-05`) each contain three live runs with all six quality metrics at 100%, zero mismatches, and zero sensitive findings.
- The first `gold-06-offline-delivery` batch failed only in `offline_delivery`: one configured-model request reached the 240-second read timeout and the following two strict attempts returned invalid model schema. The other six extraction domains completed.
- No `verify_template_quality.py` process remained after the failure, so the next diagnostic run can isolate one case without hidden concurrent model load.
- Keep strict schema, evidence-anchor, semantic-fingerprint, and sensitive-data gates unchanged; use case-level reruns to absorb external model-service long tails.
- The isolated rerun proved a deterministic correction-protocol defect: all three `offline_delivery` responses returned HTTP 200, but attempts two and three had the identical response hash because duplicate entity IDs raised an `AppError` without `correction_hint`, so retry messages contained `instruction: null`.
- RED/GREEN regression now requires global entity-ID uniqueness in both the initial prompt and duplicate-ID correction feedback. The strict validator still rejects duplicate IDs; no automatic deduplication or threshold weakening was introduced.
- The formal three-run rerun remained semantically stable but scored 94.12%: every run left `withdrawals` and `offline_handoffs` empty, so `CASH-003` and `OFFLINE-001` correctly became inconsistent on their count checks.
- Gold text explicitly contains one fully populated item for each entity type and the rules require those counts to match. The prompt currently lists only fact paths, not the domain's entity arrays or required entity fields, and says only that repeated facts must be preserved. It must explicitly require entity extraction even when the event occurs once.
- Adding the entity contract fixed entity recall, but a new formal run scored 91.18% because `CASE-001`, `TIME-001`, and `TIME-002` became incomplete in all three runs. A single isolated `case_timeline` request on the same visible text returned every timeline fact as missing.
- Within one process, all three `case_timeline` prompts have the same hash and results are stable. Across regenerated gold files, the parsed text SHA is identical but prompt hashes change because paragraph IDs include the raw DOCX package SHA; ZIP timestamps or core metadata therefore change anchors even when visible content is unchanged.
- Stable evidence anchors should be derived from normalized pages, source types, and paragraph text. Raw-file integrity remains separately protected by original artifact SHA-256 and must not be conflated with semantic location identity.
- After switching paragraph identity to normalized page/position/source/text structure, two independently generated `gold-06` DOCX packages produced identical anchor lists and the identical `case_timeline` prompt hash `56a22c41...e64b5fb`.
- With stable anchors and the explicit entity contract, `gold-06-offline-delivery` passed three live runs at 100% for all six metrics with zero mismatches and zero sensitive findings; every run retained one withdrawal and one offline handoff.
- `gold-07-special` passed its current-code three-run live gate. `gold-08-case-procedure` stopped in its first targeted recheck after `contact_channels` timed out at 240 seconds, returned one invalid anchor on retry, and timed out again at 240 seconds.
- The same stable `gold-08` `contact_channels` domain run alone corrected its invalid anchor and completed in about 55 seconds. This isolates the long tail to concurrent targeted recheck load, not prompt size or schema impossibility.
- Preserve concurrency 2 for the initial seven independent domains, but serialize the much smaller ambiguous-applicability recheck. This keeps most of the measured latency gain while avoiding model-server contention on long prompts.
- Serializing targeted recheck reproduced the exact same deterministic failure, disproving concurrency as the root cause. The serial-only change should not remain.
- `focus_paths` currently changes only an advisory line: the base prompt still lists every fact in the domain, the strict Schema still requires every domain fact and entity array, and each domain receives focus paths belonging to other domains. A true targeted recheck must filter focus paths per domain and shrink prompt plus Schema to those facts.
- Focus-only Schema verification on the exact failing `gold-08` contact applicability paths completed in 11.5 seconds, returned only the three requested booleans as missing, and produced no invalid anchors or retries.
- The focus-only `gold-08` three-run gate completed, but one initial extraction contained unsupported transfer/rebate entities while the other runs did not. The report still said semantic stability 100% because `verify_template_quality.py` compares only `(ruleId, status)` pairs and does not use the existing full semantic fingerprint.
- All live reports must be regenerated after wiring the verifier to final fact values/clarity/anchors, entities, rule statuses, missing fields, and issue anchors. Previously persisted 100% reports are insufficient evidence under the intended metric.
- After adding entity applicability/count validation, `gold-08-case-procedure` passed three live runs with the full semantic fingerprint at 100% across all six metrics and no mismatches or sensitive findings.

## 2026-07-18 Task 10 isolated results and Task 11 performance

- Gold stability must compare semantic correctness, not raw model phrasing. Values are canonicalized only when the existing oracle comparator proves them equivalent; non-equivalent fact/entity changes still alter the fingerprint.
- Drift diagnostics expose only fact/entity/rule paths, clarity, counts, and booleans. They do not put synthetic or case values into failure reports.
- The benchmark uses `gold-12-complete`, the largest seven-domain record, and rejects a sample before timing aggregation if any of 92 facts, entity counts/fields, 34 rule statuses, or required evidence anchors fail.
- Sharing one `httpx.AsyncClient` and raising the bounded domain semaphore from 2 to 7 changes only request scheduling. Prompts, Schema, validation, retry limits, model, endpoint, and deterministic rules remain identical.
- Five concurrency-2 runs produced P50/P95 135.361s/146.894s. Five concurrency-7 runs produced 71.426s/71.819s with the exact same gold-semantic fingerprint and no retries, a 47.23%/51.11% improvement.

## 2026-07-18 pre-merge review hardening

- Read-only review found that retrying one failed domain from an empty extraction could falsely mark a 34-rule review complete. Domain extraction now preserves all successful parallel outputs and failure causes; recovery reruns all seven domains when no usable partial base exists and requires all 92 paths, entity collections, and 34 results before completion.
- Affected-domain review rebuilt `ManualDecision()` for every result. Re-review now preserves decisions outside the affected domain, invalidates affected prior decisions with an audit event, and resolves only the answered target.
- SQLite schema v2 adds task revisions and CAS. Task/event writes and completed run/fact/issue persistence are transactional; model awaits recheck revision/archive state so a stale response cannot overwrite an archive.
- Structured JSON now exports only facts from the current `reviewRunId` with run and document-version provenance.
- DOCX parsing now follows active OOXML relationships, preserves body content controls, ignores orphan headers/media, and rejects excessive member count, expansion size, compression ratio, or referenced image count.
- The original generated corpus is retained as a contract suite. Four hand-authored natural document mutations cover complete, missing, unclear, and inconsistent outcomes without internal path/token hints and run through both DOCX and PDF.
- Natural-case live tests exposed two prompt defects: explicit counts without detail must still create missing/unknown entities, and online transfers must never infer offline cash withdrawals or handoffs. Both boundaries are enforced without relaxing Schema, entity counts, rules, or anchors.
- Concurrency 7 is accepted as the production default. The fallback candidates 5 and 3 remain available for future capacity changes, but testing them now would add model cost without affecting selection because 7 passed.
