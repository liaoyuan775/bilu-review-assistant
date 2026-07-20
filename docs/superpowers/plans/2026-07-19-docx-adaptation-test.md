# DOCX Adaptation Test Plan

**Goal:** Create five differentiated DOCX fixtures based on the supplied customer-service refund fraud record, upload each through the running application, and preserve paragraph-level parsing, frontend/API response, timing, and averages as optimization evidence.

**Scope:** Add only test fixtures, a repeatable local test runner, and generated evidence. Do not alter existing review logic or overwrite unrelated working-tree changes.

## Test matrix

1. `01-baseline`: copy of the supplied completed record.
2. `02-line-breaks`: same facts with question/answer text split across paragraphs.
3. `03-blank-answer`: selected answers left blank or marked unknown.
4. `04-long-answer`: one answer expanded with long Chinese prose and punctuation.
5. `05-table-and-symbols`: selected facts moved into a table and mixed with dates, amounts, and symbols.

## Evidence per sample

- fixture path, SHA-256, byte size, and variation description;
- upload HTTP response and task ID;
- final task response returned by `GET /api/v1/reviews/{taskId}`;
- parsed page/paragraph/question-answer summary, including IDs, ranges, source types, and text;
- `parseMs`, `modelReviewMs`, `modelGroupsMs`, `totalMs`, wall-clock upload-to-completion time;
- error code/message when a sample cannot complete.

## Verification

- Run the backend and frontend using the repository startup command.
- Upload all five files through the HTTP API, polling until a terminal state.
- Write one JSON file containing all raw results and an `average` object over completed samples.
- Write a Markdown summary for human review.
- Re-open all five DOCX files with `python-docx` and assert non-empty text.

## Execution result

- The stable local frontend/backend were started on ports 4173/8787.
- Qwen health was reachable and reported 34 template rules.
- All five uploads completed successfully with 34 returned review results each.
- Average evidence was written to `backend/test-results/adaptation-test-results.json` and `.md`.
