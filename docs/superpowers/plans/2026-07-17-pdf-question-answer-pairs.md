# PDF Question-Answer Pair Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge PDF visual lines into semantic question-answer paragraphs before Qwen review and evidence highlighting.

**Architecture:** Extend the PDF native-block parser with a narrow state machine. It recognizes numbered questions, question starts, answers, continuation lines, and closing boundaries while leaving DOCX and OCR parsing unchanged.

**Tech Stack:** Python 3.12, PyMuPDF, Pydantic, pytest.

## Global Constraints

- Preserve all concurrent uncommitted changes in the shared `main` worktree.
- Do not commit unless the user explicitly requests it.
- Do not change the frontend evidence-location contract.

---

### Task 1: Merge native PDF lines into question-answer pairs

**Files:**
- Create: `backend/tests/test_parser.py`
- Modify: `backend/app/services/parser.py`

**Interfaces:**
- Consumes: `_native_blocks(text: str) -> list[DocumentParagraph]`.
- Produces: one native-text `DocumentParagraph` per complete PDF question-answer pair.

- [ ] Write a failing test with a numeric line, a question line, a three-line answer, a second question, and signature markers.
- [ ] Run `python -m pytest -q backend/tests/test_parser.py` and verify the current line-based parser fails.
- [ ] Add question-start and closing-boundary predicates plus a single-pass merge in `_native_blocks`.
- [ ] Re-run the focused test and all backend tests.
- [ ] Restart the local backend, upload the PDF fixture through real Qwen, and verify the selected evidence block contains the full question and answer.
- [ ] Verify the browser highlights the complete semantic block with no console errors.
