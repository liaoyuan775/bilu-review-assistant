# Evidence-Block Driven Document Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 将 QA 问答对和非 QA 原文统一投影为证据块，修复问题续行丢失、模型只引用问段落和高亮范围错误。

**Architecture:** 保留 `ParsedDocument.pages[].paragraphs[]` 原始底稿，新增由段落顺序派生的 `evidenceBlocks`。QA block 只暴露一个稳定 ID，内部保留组成它的段落 ID；模型、规则结果和前端优先使用 block ID，旧任务继续兼容段落位置。

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, React/TypeScript, Vitest, pytest

## Global Constraints

- 非 QA 原文必须保留且顺序不变。
- 一个完整 QA 只产生一个证据块 ID。
- 模型不得收到 QA 内部单个问/答段落 ID作为可选证据锚点。
- 原始段落字段和旧任务 API 兼容。
- 不修改用户未提交的 `backend/app/data/domain_contracts.py` 注释改动或生成文件。

---

### Task 1: Extend Document Evidence Models

**Files:**
- Modify: `backend/app/core/models.py`
- Test: `backend/tests/test_question_answer.py`

**Interfaces:**
- Produce `EvidenceBlock(id, kind, text, paragraphIds, page, paragraph)`.
- Add `ParsedDocument.evidenceBlocks: list[EvidenceBlock]` with a default for old payloads.

- [ ] **Step 1: Write failing model tests**

```python
def test_evidence_block_model_defaults_and_serializes():
    block = EvidenceBlock(id="qa-1", kind="qa", text="问：问题 答：答案", paragraphIds=["p1", "p2"])
    assert block.kind == "qa"
    assert block.paragraphIds == ["p1", "p2"]
    assert ParsedDocument().evidenceBlocks == []
```

- [ ] **Step 2: Run RED**

Run `python -m pytest tests/test_question_answer.py -k evidence_block -q`.
Expected: collection fails because `EvidenceBlock` and `evidenceBlocks` do not exist.

- [ ] **Step 3: Add minimal Pydantic models**

```python
class EvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["qa", "text"]
    text: str
    paragraphIds: list[str] = Field(default_factory=list)
    page: int | None = None
    paragraph: int | None = None
```

- [ ] **Step 4: Run GREEN**

Run `python -m pytest tests/test_question_answer.py -k evidence_block -q` and expect passing tests.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/app/core/models.py backend/tests/test_question_answer.py
git commit -m "feat: add document evidence block model"
```

### Task 2: Rebuild QA State Machine Without Dropping Continuations

**Files:**
- Modify: `backend/app/parsing/question_answer.py`
- Modify: `backend/app/parsing/parser.py`
- Test: `backend/tests/test_question_answer.py`

**Interfaces:**
- Produce `reconstruct_evidence_blocks(pages) -> list[EvidenceBlock]`.
- Preserve `reconstruct_question_answers(pages)` as a compatibility projection from the same state-machine output.

- [ ] **Step 1: Write failing parser tests**

```python
def test_question_continuation_before_answer_is_preserved():
    pages = [_page("问：第一行", "问题续行", "答：答案")] 
    blocks = reconstruct_evidence_blocks(pages)
    assert blocks[0].kind == "qa"
    assert "问题续行" in blocks[0].text

def test_non_qa_text_stays_in_order_around_one_qa_block():
    pages = [_page("页眉原文", "问：问题", "答：答案", "页尾原文")]
    blocks = reconstruct_evidence_blocks(pages)
    assert [block.kind for block in blocks] == ["text", "qa", "text"]
    assert blocks[1].paragraphIds == ["p2", "p3"]

def test_one_qa_has_one_stable_block_id():
    first = reconstruct_evidence_blocks([_page("问：问题", "答：答案")])
    second = reconstruct_evidence_blocks([_page("问：问题", "答：答案")])
    assert first[0].id == second[0].id
    assert len(first) == 1
```

- [ ] **Step 2: Run RED**

Run `python -m pytest tests/test_question_answer.py -k "continuation or non_qa or stable_block" -q`.
Expected: import or assertion failure because blocks are not produced and question continuations are dropped.

- [ ] **Step 3: Implement one shared state-machine projection**

The state machine must append unmarked lines to `question_parts` before `答：`, append all answer lines after `答：`, finish a QA only on the next `问：` or end of input, and emit each non-QA paragraph as a text block. Hash the ordered kind/text/paragraph IDs for the block ID. Build legacy `QuestionAnswerBlock` values from the QA blocks.

- [ ] **Step 4: Run GREEN**

Run `python -m pytest tests/test_question_answer.py -q` and expect all parser tests to pass.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/app/parsing/question_answer.py backend/app/parsing/parser.py backend/tests/test_question_answer.py
git commit -m "fix: preserve complete QA evidence blocks"
```

### Task 3: Use Evidence Block IDs In Model Extraction

**Files:**
- Modify: `backend/app/review/domain_contract_rendering.py`
- Modify: `backend/app/review/extraction.py`
- Modify: `backend/app/core/models.py`
- Test: `backend/tests/test_template_extraction.py`

**Interfaces:**
- Prompt rendering consumes `document.evidenceBlocks`.
- `_evidence_anchor_aliases` maps block IDs to short model aliases.
- Restore maps aliases back to block IDs; old paragraph IDs remain accepted only for legacy payloads.

- [ ] **Step 1: Write failing rendering tests**

```python
def test_prompt_exposes_one_anchor_for_a_complete_qa_block():
    prompt = render_domain_prompt(document_with_one_qa(), DOMAIN_CONTRACTS["case_timeline"])
    assert "问答块" in prompt
    assert "A001,A002" not in prompt
```

- [ ] **Step 2: Run RED**

Run `python -m pytest tests/test_template_extraction.py -k "one_anchor_for_a_complete" -q`.
Expected: current renderer exposes multiple paragraph aliases.

- [ ] **Step 3: Render block text and block aliases**

Use one alias per evidence block in the prompt and schema. Include the block kind and full QA text; do not expose `paragraphIds` as selectable IDs. Update restore/validation to resolve aliases against block IDs.

- [ ] **Step 4: Run GREEN**

Run `python -m pytest tests/test_template_extraction.py tests/test_domain_contracts.py -q`.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/app/review/domain_contract_rendering.py backend/app/review/extraction.py backend/app/core/models.py backend/tests/test_template_extraction.py
git commit -m "refactor: use evidence block anchors for extraction"
```

### Task 4: Map Rule Evidence And Frontend Highlighting To Blocks

**Files:**
- Modify: `backend/app/review/extraction.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/evidenceSelection.ts`
- Modify: `frontend/src/DocumentEvidencePane.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `backend/tests/test_template_extraction.py`
- Test: `frontend/src/evidenceSelection.test.ts`

**Interfaces:**
- Review results continue exposing `evidenceLocations` for old consumers.
- New results include block IDs and block locations; a QA block location covers its first-to-last paragraph range.

- [ ] **Step 1: Write failing location/highlight tests**

```typescript
it("selects every paragraph in one QA evidence block", () => {
  const ranges = evidenceAnchorRangesFor(resultWithBlockId, documentWithQaBlock);
  expect(ranges.map((range) => range.paragraph)).toEqual([2, 3]);
});
```

- [ ] **Step 2: Run RED**

Run `npm test -- evidenceSelection.test.ts`.
Expected: current helper finds no paragraph because result anchors are block IDs.

- [ ] **Step 3: Add block-aware location projection**

Map a block ID to all its paragraph locations for rendering/highlight; keep old exact paragraph-ID behavior when `evidenceBlocks` is absent. Ensure the pane highlights every paragraph in a QA block, not unrelated neighboring QA blocks.

- [ ] **Step 4: Run GREEN**

Run `python -m pytest -q` and `npm test`.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/app/review/extraction.py frontend/src/types.ts frontend/src/evidenceSelection.ts frontend/src/DocumentEvidencePane.tsx frontend/src/App.tsx backend/tests/test_template_extraction.py frontend/src/evidenceSelection.test.ts
git commit -m "fix: highlight complete QA evidence blocks"
```

### Task 5: Original DOCX Verification

**Files:**
- Write: `backend/test-results/evidence-block-final/e2e-result.json`

- [ ] **Step 1: Run backend and frontend tests once after implementation**

Run `python -m pytest -q`, `npm test`, and `npm run build`.

- [ ] **Step 2: Submit the original fixture through `http://127.0.0.1:4173/`**

Poll until terminal status and save the complete task JSON. Confirm model prompts expose one anchor per QA, question continuations are present, and result evidence locations cover the full QA block.

- [ ] **Step 3: Verify services and report**

Run health on `8789` and HTTP 200 on `4173`; report status, result count, evidence block counts, and any remaining manual-review items.
