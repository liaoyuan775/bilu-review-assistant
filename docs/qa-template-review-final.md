# QA Report: Bilu 电信诈骗询问笔录审查助手

| Field | Value |
|---|---|
| Date | 2026-07-18 |
| URL | `http://127.0.0.1:4173` |
| Branch | `codex/template-complete-review` |
| Commit | `f9d2bcc` plus current Task 10-12 working tree |
| Mode | Diff-aware regression |
| Scope | Internal-template copy, 34-rule mock review, evidence, follow-up, artifacts, archive, desktop/mobile |
| Pages visited | New review, template review workspace |
| Screenshots | 2 |

## Health Score: 100/100

| Category | Score |
|---|---:|
| Console | 100 |
| Functional | 100 |
| Visual | 100 |
| UX | 100 |
| Accessibility | 100 |

## Final Issues

No open critical, high, medium, or low issues in the tested scope.

## Resolved During QA

### QA-001: New-review copy referred to demo rules

| Field | Value |
|---|---|
| Severity | low |
| Category | content |
| URL | `http://127.0.0.1:4173/` |

Expected: the first screen identifies the internal inquiry template as the review authority.

Actual before fix: the description said the system used “演示规则”.

Resolution: changed the text to “依据内部询问笔录模板检查提问遗漏与回答不完整事项” and added `appCopy.test.ts`. The targeted test and production build pass, and the corrected text was verified in the browser.

## Verified Flow

1. Opened the app in installed Microsoft Edge at 1440x900.
2. Confirmed Qwen connected, internal template label, 34 rules, seven sanitized demos, and use boundary.
3. Opened mock demo 01 and confirmed one high-risk incomplete issue plus exact evidence anchors.
4. Recorded a sanitized follow-up answer and observed a new document version, appended question/answer anchors, zero actionable issues, and the issue changing to covered.
5. Generated review PDF, follow-up DOCX, structured JSON, and archive manifest.
6. Confirmed the archive gate became ready, archived the review, and observed read-only state with all download links retained.
7. Resized to 390x844. `body` and root client/scroll widths were all 375px; no horizontal overflow was present.
8. Checked the browser console after desktop and mobile flows: 0 errors, 0 warnings.

## Evidence

- Desktop archived state: `output/playwright/final-desktop.png`
- Mobile archived state: `output/playwright/final-mobile.png`
- Automated regression: backend 151 passed / 1 optional actual-template skip; frontend 45 passed; production build passed with 1,755 modules.

## Blind Spots

- Browser workflow used the deterministic sanitized mock demo to avoid competing with the running full-corpus model quality gate. Real Qwen fact quality is covered separately by `verify_template_quality.py` against 12 contract cases plus four hand-authored naturalistic cases in DOCX and PDF.
- Authentication and role authorization are not implemented in the current product and therefore were not testable.
- OCR image-region coordinate accuracy and formal intranet deployment topology remain outside this browser regression.
- The combined live gate completed one full 20-document round with zero failed domains. The user explicitly stopped repeat rounds 2 and 3; no three-run combined aggregate is claimed in this report.
