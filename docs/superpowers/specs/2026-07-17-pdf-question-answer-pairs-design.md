# PDF Question-Answer Pair Segmentation Design

## Goal

Convert line-oriented native PDF extraction into semantic question-answer blocks so one evidence location highlights one complete inquiry pair.

## Scope

- Change only native text extracted from PDF pages.
- Keep DOCX paragraph/table extraction, OCR blocks, evidence DTOs, Qwen schema, and frontend highlighting unchanged.
- Preserve non-question text as independent blocks.

## Segmentation

1. Normalize non-empty extracted lines.
2. Start a question-answer block at either `问：...` or a numeric-only line immediately followed by `问：...`.
3. Append `答：...` and continuation lines to that block.
4. End the block before the next numbered question, the next `问：`, or a closing/signature marker.
5. Keep closing and signature markers as separate blocks.

## Verification

- A five-line PDF question and answer becomes one `DocumentParagraph`.
- Two adjacent questions remain two blocks.
- Closing and signature text is not absorbed by the final answer.
- Existing backend tests pass, then a real PDF review shows one complete highlighted question-answer pair.
