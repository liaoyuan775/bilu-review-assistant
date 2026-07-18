# Victim Profile Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact victim profile card with a stable initial avatar and accessible detail popover to the review result header.

**Architecture:** The backend extracts explicitly stated victim fields from normalized transcript text into an optional `VictimProfile` on `ReviewTask`. The frontend renders that data through a focused profile utility and an accessible card without changing rule results or counts.

**Tech Stack:** FastAPI, Pydantic v2, Python regex, React 18, TypeScript, CSS, pytest, Vitest

## Global Constraints

- Do not add or change any three-present/four-flow rule.
- Do not infer missing personal information.
- Avatar variants must be deterministic for the same name.
- Hover cannot be the only way to open the detail view.

---

### Task 1: Victim profile extraction

**Files:**
- Create: `backend/app/services/victim_profile.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/data.py`
- Test: `backend/tests/test_victim_profile.py`

**Interfaces:**
- Consumes: `ParsedDocument.text`
- Produces: `extract_victim_profile(text: str) -> VictimProfile | None` and `ReviewTask.victimProfile`

- [ ] Write tests for explicit fields, partial profiles, and text with no identity facts.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_victim_profile.py` and confirm failure.
- [ ] Implement the minimal Pydantic model and explicit-field extractor.
- [ ] Attach the extracted profile during upload and demo processing.
- [ ] Run the focused backend tests and confirm success.

### Task 2: Stable initial avatar utility

**Files:**
- Create: `frontend/src/victimProfile.ts`
- Test: `frontend/src/victimProfile.test.ts`

**Interfaces:**
- Consumes: victim name
- Produces: `getVictimInitial(name)` and `getVictimAvatarVariant(name)`

- [ ] Write tests proving first-character selection, fallback behavior, and stable variant selection.
- [ ] Run `npm --prefix frontend run test -- victimProfile.test.ts` and confirm failure.
- [ ] Implement the minimal pure helpers.
- [ ] Run the focused frontend test and confirm success.

### Task 3: Accessible profile card

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `ReviewTask.victimProfile`
- Produces: compact identity summary and hover/focus/click detail popover

- [ ] Add the `VictimProfile` TypeScript contract.
- [ ] Render the card in the metrics band without changing rule metrics.
- [ ] Add hover, focus, click-pin, outside-blur, and Escape behavior.
- [ ] Add responsive styling so the card remains available on narrow layouts.
- [ ] Run frontend tests and production build.

### Task 4: End-to-end verification

**Files:**
- Modify only files required by failures found in verification.

**Interfaces:**
- Consumes: completed implementation
- Produces: verified backend API and browser-visible profile interaction

- [ ] Run `npm test`.
- [ ] Run `npm run build`.
- [ ] Start the application and verify the demo in desktop and mobile browser sizes.
- [ ] Confirm avatar pixels render, the popover stays within the viewport, and no text overlaps.
