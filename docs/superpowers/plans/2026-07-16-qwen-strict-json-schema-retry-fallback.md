# Qwen Strict JSON Schema Retry And Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-form JSON review output with provider-native strict JSON Schema, add one bounded corrective/fallback attempt, and keep all Three-Present Four-Flows and evidence checks deterministic.

**Architecture:** The Qwen adapter first requests provider-native `response_format=json_schema` with `strict=true`. The schema is keyed by all seven rule IDs and every rule's required facts are fixed `factCoverage` keys. The backend derives aggregate status and missing facts, then copies evidence text from the model-selected source location; Function Calling uses the same schema only as a compatibility fallback.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, pytest, React, TypeScript, Vitest

## Global Constraints

- Uploaded files always use Qwen; local keyword analysis remains demo-only.
- Three-Present hard rules remain 案发现场, 涉案现物, 电子现痕.
- Four-Flows hard rules remain 人员流, 信息流, 资金流, 行为流.
- `referenceHints` can only create `advisories`; they never affect `status` or `missingFacts`.
- Every successful task contains exactly seven unique known rule results.
- A failed task contains no partial results.
- Never log document text, model response content, authorization headers, or API keys.
- The review-model call budget is two requests per task. Image transcription calls are separate from this budget.
- The same deterministic validator runs after strict JSON Schema and Function Calling.
- Uploaded reviews never downgrade to prompt-only JSON or local keyword analysis.

---

## Retry And Fallback Decision Matrix

| First attempt outcome | Second and final attempt | Final behavior if attempt 2 fails |
|---|---|---|
| Valid strict JSON Schema response and valid evidence | None | Complete task |
| Provider response violates the declared Schema | Function Calling with the same Schema | Fail with `invalid_model_response` |
| Seven-rule or evidence validation fails | Strict JSON Schema with rule ID, field, and safe correction hint | Fail with original stable validation code |
| Connect reset, read timeout, HTTP 408/429/500/502/503/504 | Repeat strict JSON Schema after 1 second | Fail with `model_unreachable` or `model_request_failed` |
| HTTP response explicitly says `json_schema` or strict `response_format` is unsupported | Function Calling with the same Schema | Fail with `structured_output_unsupported` |
| HTTP 401/403 | No retry | Fail immediately as configuration/authentication error |
| HTTP 400 unrelated to structured-output support | No retry | Fail immediately with `model_request_failed` |
| File parsing, empty document, unsupported format | No review-model call | Preserve parser error |

The second attempt is selected once. Strategies are not chained. A failed strict-schema correction or Function Calling fallback does not downgrade to prompt JSON.

## Corrective Retry Contract

The first semantically invalid structured response is not repaired in code. The application appends a short correction message such as:

```json
{
  "accepted": false,
  "errorCode": "insufficient_evidence",
  "ruleId": "FLOW-003",
  "field": "evidenceLocation",
  "instruction": "Regenerate all seven results. For covered or incomplete, copy a valid page and paragraph number from the indexed document."
}
```

The model must regenerate the complete seven-rule object under the same strict JSON Schema. The application must not merge the first and second responses.

## Strict Review Schema

Create input-only Pydantic models separate from API response models:

```python
class ModelEvidenceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)


class ModelRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factCoverage: dict[str, Literal["covered", "missing", "unknown"]]
    evidenceLocation: ModelEvidenceLocation | None
    reason: str
    suggestedQuestion: str
    advisories: list[str]


class ModelReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    PRESENT_001: ModelRuleResult = Field(alias="PRESENT-001")
    PRESENT_002: ModelRuleResult = Field(alias="PRESENT-002")
    PRESENT_003: ModelRuleResult = Field(alias="PRESENT-003")
    FLOW_001: ModelRuleResult = Field(alias="FLOW-001")
    FLOW_002: ModelRuleResult = Field(alias="FLOW-002")
    FLOW_003: ModelRuleResult = Field(alias="FLOW-003")
    FLOW_004: ModelRuleResult = Field(alias="FLOW-004")
```

Generate every rule's `factCoverage` as a fixed object whose required keys exactly match that rule's `requiredFacts`; each value is `covered`, `missing`, or `unknown`. The model does not output aggregate `status`, `missingFacts`, or evidence text. The backend derives status and missing facts and copies evidence from the selected page and paragraph. Submit this Schema through provider-native strict JSON Schema first and reuse it for Function Calling fallback. Page existence, paragraph bounds, and factual correctness remain the responsibility of deterministic validation.

---

### Task 1: Add Input Schema And Safe Validation Feedback

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/errors.py`
- Modify: `backend/app/services/qwen.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `ModelReviewOutput`, `ModelRuleResult`, `ModelEvidenceLocation`.
- Produces: safe internal validation metadata containing `code`, optional `rule_id`, `field`, and `correction_hint`.
- Preserves: public API error response `{error: {code, message}}`.

- [ ] Write failing tests proving extra fields, illegal rule IDs, non-positive locations, and result counts other than seven are rejected by Pydantic.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_api.py -k "model_review_output"` and confirm RED.
- [ ] Add the three input-only Pydantic models with `extra="forbid"`, enums, and list length bounds.
- [ ] Extend internal validation errors with safe retry metadata while keeping public messages unchanged.
- [ ] Add the offending `ruleId` and field name at every `_validate` failure point.
- [ ] Re-run the targeted tests and confirm GREEN.
- [ ] Suggested commit: `feat: define structured qwen review contract`.

### Task 2: Replace Primary JSON Prompt Output With Strict JSON Schema

**Files:**
- Modify: `backend/app/services/qwen.py`
- Test: `backend/tests/test_api.py`
- Modify: `backend/scripts/verify_qwen.py`

**Interfaces:**
- Produces: `_request_schema_review(client, messages) -> ModelReviewOutput`.
- Consumes: the existing document/rule prompt as structured-output instructions and factual context.
- Preserves: `_validate(payload, document) -> list[ReviewResult]` as the final authority.

- [ ] Replace the current happy-path mock test with a failing test that requires `response_format.type == "json_schema"`, `strict == true`, all seven required keys, and `additionalProperties == false`.
- [ ] Add a failing test that returns valid strict-schema content and expects seven completed results.
- [ ] Run the two tests and confirm RED because the current adapter only requests prompt-described JSON.
- [ ] Generate the provider Schema from the fixed seven-key Pydantic contract and send it through `response_format`.
- [ ] Parse `message.content` directly into `ModelReviewOutput`; reject any provider response that violates the same schema locally.
- [ ] Pass parsed Pydantic data to the unchanged deterministic validator.
- [ ] Extend the verification script to report `strategy: json_schema_strict` and `attemptCount` without printing prompts or model output.
- [ ] Re-run the targeted tests and confirm GREEN.
- [ ] Suggested commit: `feat: use strict json schema for qwen reviews`.

### Task 3: Add The Two-Call Retry And Fallback Orchestrator

**Files:**
- Modify: `backend/app/services/qwen.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `review_with_qwen(document) -> list[ReviewResult]` with a hard maximum of two HTTP requests.
- Produces: a classifier that returns `correct_schema`, `retry_transport`, `fallback_tool`, or `fail`.
- Consumes: validation metadata from Task 1 and strict-schema response context from Task 2.

- [ ] Write a failing test where attempt 1 has `status=incomplete` and `evidenceLocation=null`, attempt 2 supplies a valid location, and the task completes.
- [ ] Assert the second strict-schema request contains a correction message naming `FLOW-003` and `evidenceLocation`.
- [ ] Write a failing test where both responses lack a valid location; assert `failed`, `results == []`, and exactly two calls.
- [ ] Write failing table-driven tests for timeout/503 retry, 401 no-retry, explicit unsupported-json-schema Function Calling fallback, and unrelated 400 no-retry.
- [ ] Implement the decision matrix with one shared attempt counter and one-second transport backoff.
- [ ] Add `_request_tool_fallback` using the identical strict Schema and forced tool name. Remove the current prompt-only JSON path from uploaded reviews.
- [ ] On the second failure, return the stable public code/message from the most relevant failure, never raw provider text.
- [ ] Run all retry tests and confirm GREEN.
- [ ] Suggested commit: `feat: add bounded qwen retry and fallback`.

### Task 4: Correct User-Facing Failure States And Polling Budget

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Test: create `frontend/src/errorPresentation.test.ts`

**Interfaces:**
- Produces: `getReviewErrorPresentation(errorCode) -> {title, action}`.
- Preserves: the backend's stable `errorCode` and `errorMessage`.

- [ ] Write failing Vitest cases mapping configuration/connection errors to `无法开始审查`, parser errors to `文件解析失败`, and validation errors to `审查结果校验未通过`.
- [ ] Extract the title mapping and use it in the error banner. The current blanket `无法开始审查` title must be removed.
- [ ] Increase client polling from 300 seconds to 600 seconds so two 120-second review calls plus multimodal parsing do not create a false client timeout in normal cases.
- [ ] Keep the retry server-side; do not add a browser retry loop that could create duplicate tasks.
- [ ] Run `npm --prefix frontend run test` and confirm GREEN.
- [ ] Suggested commit: `fix: present review failures accurately`.

### Task 5: Verify Provider Capability And End-To-End Boundaries

**Files:**
- Modify: `README.md`
- Modify: `docs/openapi.json` only if API schemas change
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Verifies: the configured OpenAI-compatible Qwen endpoint accepts strict `json_schema`; Function Calling remains available as fallback.
- Documents: the exact two-call budget and fallback behavior.

- [ ] Record the completed basic desensitized probe: strict JSON Schema returned HTTP 200 with matching content; Function Calling returned HTTP 200 with matching tool arguments.
- [ ] Probe the exact generated seven-key Schema, including status branches, before replacing the production path. Basic Schema acceptance alone is not evidence that every complex keyword is supported.
- [ ] If the provider rejects `strict`, omit that optional provider flag while retaining Pydantic and deterministic validation. Do not weaken the schema itself.
- [ ] Run `npm run test`; expected frontend and backend suites both pass.
- [ ] Run `npm run build`; expected TypeScript/Vite and Python compilation pass.
- [ ] Run `npm run verify:model`; expected `completed`, `resultCount: 7`, `strategy: json_schema_strict`, and `attemptCount <= 2`.
- [ ] Run an injected first-attempt evidence-location failure; expected correction on attempt 2 and no partial first-attempt data.
- [ ] Confirm logs contain no API key, document text, prompt, evidence quote, or raw model response.
- [ ] Update README with the strategy matrix and the statement that structured output enforces shape but deterministic code enforces evidence consistency against the uploaded document.
- [ ] Suggested commit: `docs: document qwen structured review fallback`.

## Acceptance Criteria

- A compliant structured response completes with exactly seven validated results.
- Missing or invalid evidence location is corrected once through a second strict-schema response.
- No review path makes more than two model requests.
- Strict JSON Schema incompatibility can fall back to Function Calling once, but semantic violations stay on strict JSON Schema and prompt-only JSON is never used for uploads.
- Authentication errors and document parsing errors never retry.
- Invalid second responses fail the complete task with `results == []`.
- Structured output never replaces page/paragraph existence checks, evidence-to-source matching, required-fact whitelists, or status consistency checks.
- The UI no longer labels a post-processing validation failure as `无法开始审查`.
