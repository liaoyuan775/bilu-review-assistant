# Interactive Flow And Test Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive review execution flow to the existing React app and generate three formal, fictional DOCX inquiry records for upload testing.

**Architecture:** Keep flow metadata in a standalone TypeScript module and render it with `@xyflow/react` in a dedicated page selected from the existing sidebar. Keep document content in a Python data structure and generate stable DOCX artifacts through a repeatable script.

**Tech Stack:** React 18, TypeScript, Vite, `@xyflow/react`, Python 3.11, `python-docx`, pytest, Microsoft Edge.

## Global Constraints

- The workflow page must preserve the current light government-workbench visual language.
- Workflow nodes must be clickable and the canvas must support pan, zoom and fit-view.
- Every document value must be fictional; unknown data must appear only as an explicit answer containing “我不知道”.
- Final DOCX files must be written to `output/doc/`.
- This directory is not a Git repository, so commit steps are omitted.

---

### Task 1: Workflow Data Contract

**Files:**
- Create: `frontend/src/workflowData.test.ts`
- Create: `frontend/src/workflowData.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `WorkflowNodeData`, `workflowNodes`, `workflowEdges` and `workflowStages`.
- Each node data object contains `title`, `summary`, `input`, `process`, `output`, `exception`, `phase` and `status`.

- [ ] **Step 1: Install test and graph dependencies**

Run: `npm --prefix frontend install @xyflow/react && npm --prefix frontend install -D vitest`

- [ ] **Step 2: Write the failing data-contract test**

Assert eight main stages, ordered main edges, at least four failure edges and complete detail fields for every node.

- [ ] **Step 3: Run the test and verify RED**

Run: `npm --prefix frontend run test -- --run frontend/src/workflowData.test.ts`

Expected: FAIL because `workflowData.ts` is missing.

- [ ] **Step 4: Implement the workflow data**

Define eight main nodes plus a shared failed terminal node. Mark main edges as animated and failure edges as red dashed lines.

- [ ] **Step 5: Run the test and verify GREEN**

Run: `npm --prefix frontend run test -- --run src/workflowData.test.ts`

Expected: PASS.

### Task 2: Interactive Workflow Page

**Files:**
- Create: `frontend/src/WorkflowView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `workflowNodes` and `workflowEdges` from `workflowData.ts`.
- Produces: `WorkflowView`, selected with `view === "workflow"`.

- [ ] **Step 1: Add the sidebar navigation state**

Extend the view union to `"new" | "result" | "workflow"` and add a `Workflow` icon navigation button.

- [ ] **Step 2: Build the interactive page**

Render `ReactFlow` with `Controls`, `Background`, `MiniMap`, `fitView`, node selection and a right-side node details panel.

- [ ] **Step 3: Add responsive workbench styling**

Use a fixed-height canvas, 4-6 px radii, white surfaces, gray-blue canvas, blue main edges and red failure edges. Collapse the details panel below the canvas on narrow screens.

- [ ] **Step 4: Build the frontend**

Run: `npm run build`

Expected: TypeScript and Vite exit 0.

### Task 3: Formal DOCX Test Records

**Files:**
- Create: `backend/tests/test_generate_test_records.py`
- Create: `backend/scripts/generate_test_records.py`
- Generate: `output/doc/01-基本完整-电诈询问笔录.docx`
- Generate: `output/doc/02-明确漏问-电诈询问笔录.docx`
- Generate: `output/doc/03-复杂场景-APP返利询问笔录.docx`

**Interfaces:**
- Produces: `generate_test_records(output_dir: Path) -> list[Path]`.

- [ ] **Step 1: Write the failing generator test**

Generate into pytest `tmp_path`, open each file with `python-docx`, and assert title, fictional marker, case metadata, signature area, mock identity/contact/account values and prohibited placeholder absence.

- [ ] **Step 2: Run the test and verify RED**

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_generate_test_records.py`

Expected: FAIL because the generator module is missing.

- [ ] **Step 3: Implement the generator**

Create common document styles, metadata table, identity table, rights notice, Q&A paragraphs, continuation footer and signature section. Populate the three approved scenarios with reserved test data.

- [ ] **Step 4: Generate final files and verify GREEN**

Run: `backend\.venv\Scripts\python.exe backend\scripts\generate_test_records.py --output-dir output\doc`

Run: `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_generate_test_records.py`

Expected: three files generated and tests pass.

### Task 4: End-To-End Verification

**Files:**
- Render outputs under: `tmp/docs/`
- Capture browser evidence under: `output/playwright/`

- [ ] **Step 1: Run all automated checks**

Run: `npm run test && npm run build`

Expected: all pytest tests pass and the production frontend build exits 0.

- [ ] **Step 2: Validate every DOCX page visually**

Convert DOCX to PDF with LibreOffice or Microsoft Word automation, render all PDF pages to PNG, inspect title, tables, line breaks, page numbers and signature blocks, and correct any layout defects.

- [ ] **Step 3: Validate in Microsoft Edge**

Open `http://127.0.0.1:4173`, enter “执行流程”, click multiple nodes, zoom, pan, use fit-view and confirm details change without console errors.

- [ ] **Step 4: Upload all three DOCX files**

Create local review tasks for each generated file and verify parsing succeeds with non-empty text and ten review results.
