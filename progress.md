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

## Error Log

| Time | Error | Attempt | Resolution |
|------|-------|---------|------------|
| 2026-07-18 00:24 | Actual-template test expected more than 4000 normalized characters; parser returned all 144 paragraphs in 3623 characters | 1 | Replaced arbitrary size threshold with exact paragraph/question/key-content assertions |
| 2026-07-18 00:25 | Test counted only the 32 paragraph-leading questions | 2 | Corrected oracle to 33 question markers: 32 paragraph-leading plus one same-paragraph rights-notice question |
| 2026-07-18 00:35 | Header/footer preservation made the actual-template aggregate block count 145 | 3 | Verified the source split is 144 native body blocks plus one footer and scoped the assertion accordingly |
| 2026-07-18 00:35 | Scanned-PDF API test expected the old three-field paragraph schema | 4 | Updated the contract assertion to include stable ID, offsets, and nullable bbox |
