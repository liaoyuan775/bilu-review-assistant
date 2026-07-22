# Domain JSON Schema Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate concise semantic `description` annotations in every strict domain JSON Schema from the existing domain contracts.

**Architecture:** Keep `domain-contracts/*.json` as the sole field-description source. Extend only `build_domain_schema` helpers so fact and entity schemas receive annotations while all validation keywords and response fields remain unchanged.

**Tech Stack:** Python 3.11+, pytest, JSON Schema Draft 2020-12, Qwen OpenAI-compatible structured output.

## Global Constraints

- Do not add new fields to the domain contract JSON files.
- Do not change model output fields, strict mode, retry policy, concurrency, rules, parsing, API, or frontend.
- `description` remains an annotation and must not replace `type`, `enum`, `required`, ranges, anchor enums, or `additionalProperties: false`.
- Reuse the exact existing `FactContract.description` and entity contract descriptions.

---

### Task 1: Generate Fact and Entity Descriptions

**Files:**
- Modify: `backend/tests/test_template_extraction.py`
- Modify: `backend/app/review/domain_contract_rendering.py`
- Test: `backend/tests/test_template_extraction.py`

**Interfaces:**
- Consumes: `FactContract.description`, `EntityContract.description`, and `build_domain_schema(contract, fact_paths=None, allowed_anchor_ids=None) -> dict`.
- Produces: The same JSON Schema shape plus annotation-only `description` keys.

- [x] **Step 1: Write failing tests**

Add one test for a normal fact and one for an entity:

```python
def test_domain_schema_includes_fact_semantic_descriptions():
    schema = build_domain_schema(DOMAIN_CONTRACTS["header_procedure"])
    fact = schema["properties"]["facts"]["properties"]["procedure.record_reviewed"]
    assert fact["description"] == "被询问人是否核对笔录"
    assert fact["properties"]["value"]["description"] == "被询问人是否核对笔录"
    assert "clear" in fact["properties"]["clarity"]["description"]
    assert "直接支持" in fact["properties"]["evidenceAnchorIds"]["description"]


def test_domain_schema_includes_entity_semantic_descriptions():
    schema = build_domain_schema(DOMAIN_CONTRACTS["online_money"])
    transfers = schema["properties"]["entities"]["properties"]["transfers"]
    amount = transfers["items"]["properties"]["fields"]["properties"]["amount"]
    assert transfers["description"] == "每笔线上转账记录"
    assert amount["description"] == "转账金额"
    assert amount["properties"]["value"]["description"] == "转账金额"
```

- [x] **Step 2: Run the two tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_extraction.py -k "semantic_descriptions"
```

Expected: two assertion failures because the generated schema has no `description` keys.

- [x] **Step 3: Implement the minimal generator change**

In `domain_contract_rendering.py`, define shared clarity and evidence descriptions, add `description` to the fact object and its three child properties, and annotate entity arrays plus their `id`, `entityType`, and `fields` properties. Use `_fact_schema` for entity fields so their contract descriptions are generated identically.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_domain_contracts.py backend\tests\test_template_extraction.py
```

Expected: all selected tests pass.

- [x] **Step 5: Verify the provider and real fixture**

Call the existing backend health endpoint to verify strict Schema support, then submit `backend/test-fixtures/06-all-statuses-demo.docx` once. Require completed status, 34 results, zero failed domains, only Schema strategy, and record retry count and timing.

- [ ] **Step 6: Commit and push**

Stage only the generator, tests, this plan, and approved design spec if needed. Commit with:

```powershell
git commit -m "feat: describe strict domain schemas"
git push origin codex/review-stability-and-rule-generality
```
