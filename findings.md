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
