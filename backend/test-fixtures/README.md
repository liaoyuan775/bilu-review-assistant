# DOCX adaptation fixtures

All five files are derived from the supplied completed customer-service refund fraud record. They intentionally exercise different parser inputs:

| File | Difference under test |
|---|---|
| `01-baseline.docx` | Unchanged completed source record; baseline for comparison. |
| `02-line-breaks.docx` | A same-paragraph question/answer pair is split into adjacent paragraphs. |
| `03-blank-answer.docx` | One answer is retained as an empty `答：` marker. |
| `04-long-answer.docx` | One answer is expanded with long Chinese text, punctuation, and amounts to force an extra logical page. |
| `05-table-and-symbols.docx` | Adds a structured table containing dates, channels, amounts, punctuation, and a note. |

The upload evidence is written to `backend/test-results/adaptation-test-results.json`; the human-readable summary is `adaptation-test-results.md`. Each per-file JSON record includes the parsed paragraphs, question/answer reconstruction, raw upload response, final task response, timings, and errors.
