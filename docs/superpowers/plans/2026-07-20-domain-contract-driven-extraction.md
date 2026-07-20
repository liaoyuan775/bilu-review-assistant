# Domain Contract Driven Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Generate every domain prompt, strict JSON Schema, and local value-type validation from seven independently editable JSON domain contracts.

**Architecture:** Load and cross-validate seven UTF-8 contracts at startup. A focused rendering module produces deterministic prompt fragments and provider-compatible field-level Schemas. The extraction orchestrator keeps seven-domain concurrency, retries complete failed batches for entity-free domains, retries complete entity-bearing domains, and never falls back to plain JSON or Tool Calling.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, jsonschema 4.26.0, httpx, pytest

## Global Constraints

- Keep QWEN_MODEL=qwen3.6-35b-a3b.
- Every request and retry uses response_format.type=json_schema, json_schema.strict=true, and enable_thinking=false.
- Plain JSON and Tool Calling fallback are forbidden.
- Keep QWEN_DOMAIN_CONCURRENCY configurable with default 7 and range 1..7.
- Store one UTF-8 JSON contract per domain under backend/domain-contracts/.
- Never stitch a single-field response.
- Entity-free domains retry a complete failed fixed batch and retain successful batches.
- Entity-bearing domains retry the complete domain atomically.
- Preserve unrelated dirty-worktree changes and stage only task-owned paths.

---

## File Structure

Create:

- backend/domain-contracts/header_procedure.json
- backend/domain-contracts/case_timeline.json
- backend/domain-contracts/contact_channels.json
- backend/domain-contracts/risk_and_evidence.json
- backend/domain-contracts/online_money.json
- backend/domain-contracts/offline_delivery.json
- backend/domain-contracts/special_scenarios.json
- backend/prompt-templates/domain-extraction.txt
- backend/app/data/domain_contracts.py
- backend/app/review/domain_contract_rendering.py
- backend/tests/test_domain_contracts.py

Modify:

- backend/requirements.txt
- backend/app/core/config.py
- backend/.env.example
- backend/app/core/models.py
- backend/app/review/extraction.py
- backend/app/review/review.py
- backend/tests/test_template_extraction.py
- backend/tests/test_template_performance_contract.py
- backend/tests/test_demo_cases.py
- backend/tests/test_review_lifecycle.py

---

### Task 1: Load And Validate Seven Domain Contracts

**Files:**

- Create: backend/app/data/domain_contracts.py
- Create: backend/domain-contracts/*.json
- Create: backend/tests/test_domain_contracts.py
- Modify: backend/requirements.txt

**Interfaces:**

- Produces DOMAIN_ORDER: tuple[str, ...]
- Produces DOMAIN_CONTRACTS: dict[str, DomainContract]
- Produces DOMAIN_FACT_PATHS: dict[str, tuple[str, ...]]
- Produces DOMAIN_ENTITY_FIELDS: dict[str, dict[str, tuple[str, ...]]]
- Produces ENTITY_COUNT_PATHS: dict[str, str]
- Produces DOMAIN_ENTITY_APPLICABILITY: dict[str, str]
- Produces load_domain_contracts(root: Path) -> dict[str, DomainContract]
- Produces catalog_paths_from_rules() -> set[str]
- Consumes TEMPLATE_RULES from app.data.rules for coverage checks.

- [ ] **Step 1: Write failing loader tests**

~~~python
def test_all_seven_domain_contracts_load():
    assert tuple(DOMAIN_CONTRACTS) == DOMAIN_ORDER
    assert set(DOMAIN_CONTRACTS) == {
        "header_procedure", "case_timeline", "contact_channels",
        "risk_and_evidence", "online_money", "offline_delivery",
        "special_scenarios",
    }


def test_contracts_cover_catalog_paths_exactly_once():
    configured = [
        path
        for contract in DOMAIN_CONTRACTS.values()
        for path in contract.facts
    ]
    assert len(configured) == len(set(configured))
    assert set(configured) == catalog_paths_from_rules()


def test_representative_types_are_specific():
    online = DOMAIN_CONTRACTS["online_money"]
    assert online.facts["online_money.used"].valueSchema.type == ("boolean", "null")
    assert online.facts["online_money.total"].valueSchema.type == ("number", "null")
    assert online.facts["online_money.transfer_count"].valueSchema.type == ("integer", "null")
    evidence = DOMAIN_CONTRACTS["risk_and_evidence"]
    assert evidence.facts["evidence.record_types"].valueSchema.type == ("array", "null")
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
cd D:\AgentLearning\bilu\backend
$env:PYTHONUTF8='1'
python -m pytest tests/test_domain_contracts.py -q
~~~

Expected: collection fails because app.data.domain_contracts does not exist.

- [ ] **Step 3: Implement strict models and loader**

~~~python
ValueType = Literal["string", "number", "integer", "boolean", "array", "null"]

class ValueSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: tuple[ValueType, ...]
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[str | int | float | bool, ...] | None = None
    items: Literal["string"] | None = None
    minItems: int | None = Field(default=None, ge=0)
    maxItems: int | None = Field(default=None, ge=0)

class FactContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str = Field(min_length=1)
    valueSchema: ValueSchema

class EntityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str = Field(min_length=1)
    applicabilityPath: str | None = None
    countPath: str | None = None
    fields: dict[str, FactContract]

class DomainContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    domain: str
    title: str = Field(min_length=1)
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    facts: dict[str, FactContract]
    entities: dict[str, EntityContract]
~~~

Reject unsupported type combinations, array schemas without items="string",
scalar schemas with items, reversed bounds, and duplicate enum values. Read
exactly the seven named files with encoding="utf-8". Cross-check every rule
path and repeat-entity relationship against template_rules.json.

- [ ] **Step 4: Populate the seven contracts**

Move every current fact path and entity definition into its domain file.
Use boolean|null for flags, integer|null with minimum 0 for counts,
number|null with minimum 0 for amounts, array<string>|null for
evidence.record_types, and string|null for text, identifiers, dates, and
times. Explicitly define ambiguous paths such as
risk.suspect_chat_real_name and risk.victim_chat_real_name as boolean|null.

- [ ] **Step 5: Add direct dependency and verify GREEN**

Add jsonschema==4.26.0 to requirements.txt, then run:

~~~powershell
python -m pytest tests/test_domain_contracts.py -q
~~~

Expected: all contract tests pass.

- [ ] **Step 6: Commit Task 1 paths only**

~~~powershell
git add -- backend/requirements.txt backend/domain-contracts backend/app/data/domain_contracts.py backend/tests/test_domain_contracts.py
git commit -m "feat: add extraction domain contracts"
~~~

---

### Task 2: Generate Prompts And Field-Level Schemas

**Files:**

- Create: backend/prompt-templates/domain-extraction.txt
- Create: backend/app/review/domain_contract_rendering.py
- Modify: backend/tests/test_template_extraction.py

**Interfaces:**

- Produces render_domain_prompt(document, contract, fact_paths=None) -> str
- Produces build_domain_schema(contract, fact_paths=None, allowed_anchor_ids=None) -> dict
- Produces validate_schema_payload(payload, schema, domain) -> None

- [ ] **Step 1: Write failing rendering tests**

~~~python
def test_online_money_prompt_renders_type_and_boundary():
    prompt = render_domain_prompt(_document(), DOMAIN_CONTRACTS["online_money"])
    assert "online_money.used" in prompt
    assert "boolean|null" in prompt
    assert "银行取现" in prompt


def test_online_money_schema_rejects_amount_in_used_flag():
    schema = build_domain_schema(
        DOMAIN_CONTRACTS["online_money"],
        allowed_anchor_ids=("A001",),
    )
    used = schema["properties"]["facts"]["properties"]["online_money.used"]
    assert used["properties"]["value"]["type"] == ["boolean", "null"]


def test_record_types_schema_allows_string_array():
    schema = build_domain_schema(DOMAIN_CONTRACTS["risk_and_evidence"])
    value = schema["properties"]["facts"]["properties"]["evidence.record_types"]["properties"]["value"]
    assert value["type"] == ["array", "null"]
    assert value["items"] == {"type": "string"}
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
python -m pytest tests/test_template_extraction.py -k "renders_type or amount_in_used or record_types_schema" -q
~~~

Expected: imports fail because the rendering module does not exist.

- [ ] **Step 3: Create the shared template**

The file contains the fixed role, no-inference rule, clarity/value/evidence
rules, anchor syntax, structural text placeholder, Q&A placeholder, domain
contract placeholder, requested-contract placeholder, and correction
placeholder. It contains no domain-specific field definition.

- [ ] **Step 4: Implement deterministic rendering**

Render every selected fact and entity field with its path, Chinese
description, exact type, and bounds. Render include/exclude boundaries.
Include entities only for complete entity-domain requests. Reuse the current
short-anchor mapping and structural/Q&A extraction behavior.

- [ ] **Step 5: Implement field-specific Schema generation**

Each fact property gets its exact valueSchema. Reuse only clarity and anchor
definitions. Keep every declared key required, additionalProperties=false,
evidenceAnchorIds.maxItems=3, allowed anchors as enum, and
failedDomains.maxItems=0.

- [ ] **Step 6: Implement local generated-Schema validation**

~~~python
def validate_schema_payload(payload: dict, schema: dict, domain: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        field = ".".join(str(part) for part in error.absolute_path)
        raise AppError(
            "invalid_model_schema",
            f"{domain} 域结果不符合字段类型约束。",
            502,
            retry_strategy="schema",
            field=field or "payload",
            correction_hint=error.message,
        )
~~~

- [ ] **Step 7: Verify GREEN and commit**

~~~powershell
python -m pytest tests/test_template_extraction.py tests/test_domain_contracts.py -q
git add -- backend/prompt-templates/domain-extraction.txt backend/app/review/domain_contract_rendering.py backend/tests/test_template_extraction.py
git commit -m "feat: generate extraction prompts and schemas"
~~~

---

### Task 3: Integrate Contracts Into Extraction

**Files:**

- Modify: backend/app/review/extraction.py
- Modify: backend/tests/test_template_extraction.py
- Modify: backend/tests/test_template_performance_contract.py

**Interfaces:**

- Imports compatibility DOMAIN_* values from app.data.domain_contracts.
- Preserves extract_template_facts(...) -> CaseExtraction.
- Preserves run_template_review(...) -> TemplateReviewOutcome.

- [ ] **Step 1: Write failing integration test**

~~~python
def test_request_uses_same_contract_for_prompt_and_schema(monkeypatch):
    request = AsyncMock(return_value=_missing_domain("online_money").model_dump())
    monkeypatch.setattr(extraction_mod, "request_structured_payload", request)
    asyncio.run(extraction_mod._request_domain(
        _DummyClient(), _document(), "online_money",
    ))
    kwargs = request.await_args.kwargs
    assert "是否发生线上资金转出" in kwargs["messages"][1]["content"]
    used = kwargs["schema"]["properties"]["facts"]["properties"]["online_money.used"]
    assert used["properties"]["value"]["type"] == ["boolean", "null"]
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
python -m pytest tests/test_template_extraction.py tests/test_template_performance_contract.py -q
~~~

Expected: typed-contract assertions fail against the current shared fact schema.

- [ ] **Step 3: Replace hard-coded definitions**

Import derived domain values from app.data.domain_contracts. Remove only the
old fact/entity/count/applicability construction. Keep domain ordering,
concurrency, failure types, evaluation logic, and unrelated behavior.

- [ ] **Step 4: Use generated prompt, Schema, and local validation**

~~~python
contract = DOMAIN_CONTRACTS[domain]
prompt = render_domain_prompt(document, contract, fact_paths=focus_paths)
schema = build_domain_schema(
    contract,
    fact_paths=focus_paths,
    allowed_anchor_ids=evidence_anchor_aliases(document),
)
payload = await request_structured_payload(
    client,
    messages=messages,
    schema=schema,
    schema_name=f"extract_{domain}",
)
validate_schema_payload(payload, schema, domain)
~~~

Then convert to CaseExtraction, restore aliases, and run semantic validation.

- [ ] **Step 5: Verify GREEN and commit**

~~~powershell
python -m pytest tests/test_domain_contracts.py tests/test_template_extraction.py tests/test_template_performance_contract.py tests/test_qwen_health.py -q
git add -- backend/app/review/extraction.py backend/tests/test_template_extraction.py backend/tests/test_template_performance_contract.py
git commit -m "refactor: drive extraction from domain contracts"
~~~

---

### Task 4: Enforce Stable Retry Boundaries

**Files:**

- Modify: backend/app/core/config.py
- Modify: backend/.env.example
- Modify: backend/app/review/extraction.py
- Modify: backend/tests/test_template_extraction.py

**Interfaces:**

- Keeps MAX_FACTS_PER_SCHEMA_REQUEST=8.
- Adds QWEN_SCHEMA_RETRIES, default 1, range 0..2.
- Entity-free request unit is a complete fixed batch.
- Entity-bearing request unit is the complete domain.
- No response unit is an individual field.

- [ ] **Step 1: Write failing retry-boundary tests**

~~~python
def test_entity_free_failure_retries_complete_batch_and_keeps_prior_batch(monkeypatch):
    calls = []
    attempts = Counter()
    paths = DOMAIN_FACT_PATHS["case_timeline"]
    first_batch = paths[:MAX_FACTS_PER_SCHEMA_REQUEST]
    failed_batch = paths[MAX_FACTS_PER_SCHEMA_REQUEST:2 * MAX_FACTS_PER_SCHEMA_REQUEST]

    async def request(_client, _document, _domain, correction=None, focus_paths=None):
        calls.append(focus_paths)
        attempts[focus_paths] += 1
        if focus_paths == failed_batch and attempts[focus_paths] == 1:
            raise AppError(
                "invalid_model_evidence",
                "测试证据错误。",
                502,
                retry_strategy="schema",
                field=failed_batch[0],
                correction_hint="完整重做本批次。",
            )
        return CaseExtraction(facts={
            path: ExtractedFact(clarity="missing")
            for path in focus_paths
        })

    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())
    asyncio.run(extraction_mod.extract_template_facts(
        _document(), {}, domains=("case_timeline",),
    ))

    assert calls.count(first_batch) == 1
    assert calls.count(failed_batch) == 2


def test_entity_domain_failure_retries_complete_domain(monkeypatch):
    error = AppError(
        "invalid_model_schema",
        "测试字段类型错误。",
        502,
        retry_strategy="schema",
        field="online_money.used",
        correction_hint="必须返回 boolean。",
    )
    valid = _missing_domain("online_money")
    request = AsyncMock(side_effect=[error, valid])
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    asyncio.run(extraction_mod.extract_template_facts(
        _document(), {}, domains=("online_money",),
    ))

    assert [call.args[4] for call in request.await_args_list] == [None, None]
    assert request.await_args_list[1].args[3] is error
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
python -m pytest tests/test_template_extraction.py -k "complete_batch or complete_domain" -q
~~~

- [ ] **Step 3: Implement explicit request units**

~~~python
if contract.entities:
    request_units = (None,)
else:
    paths = selected_domain_paths
    request_units = tuple(
        paths[index:index + MAX_FACTS_PER_SCHEMA_REQUEST]
        for index in range(0, len(paths), MAX_FACTS_PER_SCHEMA_REQUEST)
    )
~~~

Retry the same unit with correction feedback. Merge it only after generated
Schema and semantic validation pass. Validate the complete merged domain
after all units finish.

- [ ] **Step 4: Add retry configuration**

Parse QWEN_SCHEMA_RETRIES from the environment, default to 1, and clamp to
0..2. Loop over 1 + QWEN_SCHEMA_RETRIES attempts. Every attempt calls the
same strict Schema request path.

- [ ] **Step 5: Verify GREEN and commit**

~~~powershell
python -m pytest tests/test_template_extraction.py tests/test_template_performance_contract.py -q
git add -- backend/app/core/config.py backend/.env.example backend/app/review/extraction.py backend/tests/test_template_extraction.py
git commit -m "fix: retry extraction at stable boundaries"
~~~

---

### Task 5: Persist Actionable Demo And Upload Failures

**Files:**

- Modify: backend/app/core/models.py
- Modify: backend/app/review/review.py
- Modify: backend/tests/test_demo_cases.py
- Modify: backend/tests/test_review_lifecycle.py

**Interfaces:**

- Adds ReviewTask.domainErrors: dict[str, str].
- Adds ReviewTask.domainErrorDetails: dict[str, str].
- Keeps ReviewTask.failedDomains.
- Applies one TemplateDomainFailure mapping to upload and demo paths.

- [ ] **Step 1: Write failing persistence test**

~~~python
def test_qwen_demo_persists_failed_domain_and_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))
    failure = TemplateDomainFailure(
        partial_extraction=CaseExtraction(),
        failed_domains=["case_timeline"],
        domain_errors={"case_timeline": "invalid_model_evidence"},
        domain_error_details={
            "case_timeline": "privacy.disclosure_reason 引用了空答案锚点",
        },
    )
    with patch(
        "app.review.review.run_template_review",
        new=AsyncMock(side_effect=failure),
    ):
        created = client.post(
            "/api/v1/reviews/demos/case-02-line-breaks",
            json={},
        )

    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "failed"
    assert task["failedDomains"] == ["case_timeline"]
    assert task["domainErrors"] == {
        "case_timeline": "invalid_model_evidence",
    }
    assert "privacy.disclosure_reason" in task["domainErrorDetails"]["case_timeline"]
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
python -m pytest tests/test_demo_cases.py tests/test_review_lifecycle.py -q
~~~

Expected: demo task exposes only the aggregate error.

- [ ] **Step 3: Add fields and shared failure mapping**

~~~python
def apply_template_domain_failure(task, error):
    task.extractionPayload = error.partial_extraction.model_dump(mode="json")
    task.failedDomains = list(dict.fromkeys(
        [*task.failedDomains, *error.failed_domains]
    ))
    task.domainErrors.update(error.domain_errors)
    task.domainErrorDetails.update(error.domain_error_details)
~~~

Call the helper from process_upload and process_demo. Keep other AppError
behavior unchanged.

- [ ] **Step 4: Verify GREEN and commit**

~~~powershell
python -m pytest tests/test_demo_cases.py tests/test_review_lifecycle.py tests/test_api.py -q
git add -- backend/app/core/models.py backend/app/review/review.py backend/tests/test_demo_cases.py backend/tests/test_review_lifecycle.py
git commit -m "fix: persist extraction failure details"
~~~

---

### Task 6: Full Verification And Original DOCX Run

**Evidence:**

- Write backend/test-results/qwen36-domain-contract-final/e2e-result.json.
- Audit backend/logs/development.log by task ID.

- [ ] **Step 1: Run full backend tests once**

~~~powershell
cd D:\AgentLearning\bilu\backend
$env:PYTHONUTF8='1'
python -m pytest -q
~~~

Expected: zero failures; the existing intentional skip may remain.

- [ ] **Step 2: Restart only the backend listener**

Resolve and terminate only the process tree listening on 8789. Start
python -m uvicorn app.main:app --host 127.0.0.1 --port 8789. Do not terminate
unrelated Python or Node processes.

- [ ] **Step 3: Verify strict health**

~~~powershell
curl.exe --noproxy "*" http://127.0.0.1:8789/api/v1/health
~~~

Expected: ok=true, model=qwen3.6-35b-a3b, ruleCount=34.

- [ ] **Step 4: Submit the original DOCX through port 4173**

~~~powershell
curl.exe --noproxy "*" -F "file=@D:\AgentLearning\bilu\backend\test-fixtures\06-all-statuses-demo.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document" http://127.0.0.1:4173/api/v1/reviews
~~~

Poll GET /api/v1/reviews/{taskId} until completed or failed and save the full
UTF-8 response.

- [ ] **Step 5: Audit completion evidence**

Require status=completed, result count=34, failed domain count=0, every
qwen.request_started line strategy=schema, plain/tool count=0, and
structured_output_not_enforced count=0. Report API total time, model time,
per-domain times, initial request count, correction retry count, and result
status distribution.

- [ ] **Step 6: Verify services remain available**

~~~powershell
curl.exe --noproxy "*" -sS http://127.0.0.1:8789/api/v1/health
curl.exe --noproxy "*" -sS -o NUL -w "%{http_code}" http://127.0.0.1:4173/
~~~

Expected: backend health succeeds and frontend returns HTTP 200.
