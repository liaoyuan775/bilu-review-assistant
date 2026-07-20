import asyncio
import inspect
import json
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.errors import AppError
from app.core.models import DocumentPage, DocumentParagraph, EvidenceBlock, ParsedDocument, RuleStatus, SourceType
from app.parsing.question_answer import reconstruct_question_answers
from app.parsing.parser import parse_document
from app.review import extraction as extraction_mod
from app.data.domain_contracts import DOMAIN_CONTRACTS
from app.llm import qwen
from app.review.domain_contract_rendering import build_domain_schema, render_domain_prompt
from app.core.template_models import (
    CaseExtraction,
    ExtractedEntity,
    ExtractedFact,
    RuleCondition,
    TemplateRule,
)


class _DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def test_structured_fact_requests_disable_sampling(monkeypatch):
    request = AsyncMock(return_value={"content": "{}"})
    monkeypatch.setattr(qwen, "_post_completion", request)

    asyncio.run(qwen.request_structured_payload(
        _DummyClient(),
        messages=[{"role": "user", "content": "脱敏测试"}],
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_name="deterministic_test",
    ))

    payload = request.await_args.args[1]
    assert payload["temperature"] == 0
    assert payload["enable_thinking"] is False
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert not {"tools", "tool_choice"} & payload.keys()
    assert "json" in json.dumps(payload["messages"], ensure_ascii=False).lower()
    assert any("json" in message["content"].lower() for message in payload["messages"])
    system_content = payload["messages"][0]["content"]
    assert json.dumps(payload["response_format"]["json_schema"]["schema"], ensure_ascii=False, separators=(",", ":")) in system_content


def test_template_flow_does_not_expose_legacy_three_present_four_flows_model_review():
    source = inspect.getsource(qwen)

    assert "three_present_four_flows_review" not in source
    assert "review_with_qwen" not in source
    assert "structured_review_schema" not in source


def test_structured_payload_fails_without_falling_back_when_schema_is_unsupported(monkeypatch):
    real_async_client = httpx.AsyncClient
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(400, json={"error": {"message": "response_format json_schema is not supported"}})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    async def run_request():
        async with qwen.httpx.AsyncClient(timeout=30) as client:
            return await qwen.request_structured_payload(
                client,
                messages=[{"role": "user", "content": "Return JSON."}],
                schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                schema_name="plain_json_probe",
            )

    with pytest.raises(AppError) as error:
        asyncio.run(run_request())

    assert error.value.code == "structured_output_unsupported"
    assert len(requests) == 1
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[0]["enable_thinking"] is False
    assert not {"tools", "tool_choice"} & requests[0].keys()


def test_structured_payload_does_not_fallback_for_generic_bad_schema_request(monkeypatch):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={
            "error": {"message": "invalid response_format json_schema: required field mismatch"},
        })

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")

    async def run_request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await qwen.request_structured_payload(
                client,
                messages=[{"role": "user", "content": "Return JSON."}],
                schema={"type": "object", "properties": {}, "additionalProperties": False},
                schema_name="invalid_schema_probe",
            )

    with pytest.raises(AppError) as error:
        asyncio.run(run_request())

    assert error.value.code == "model_request_failed"
    assert len(requests) == 1


def test_domain_response_that_violates_schema_is_not_retried(monkeypatch):
    document = _document()
    request = AsyncMock(return_value={"unexpected": {"value": "ignored schema"}})
    monkeypatch.setattr(extraction_mod, "request_structured_payload", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(extraction_mod.TemplateDomainFailure) as error:
        asyncio.run(extraction_mod.extract_template_facts(
            document,
            {},
            domains=("header_procedure",),
        ))

    assert request.await_count == 1
    assert error.value.domain_errors["header_procedure"] == "structured_output_not_enforced"


def _document(question: str = "是否收到风险提示？", answer: str = "收到银行短信提示。") -> ParsedDocument:
    paragraphs = [
        DocumentParagraph(id="q1", text=f"问：{question}", sourceType=SourceType.NATIVE_TEXT),
        DocumentParagraph(id="a1", text=f"答：{answer}", sourceType=SourceType.NATIVE_TEXT),
    ]
    pages = [DocumentPage(page=1, paragraphs=paragraphs)]
    return ParsedDocument(
        name="record.docx",
        format="DOCX",
        pageCount=1,
        pages=pages,
        text="\n".join(paragraph.text for paragraph in paragraphs),
        sizeLabel="test",
        questionAnswers=reconstruct_question_answers(pages),
    )


def _missing_domain(domain: str) -> CaseExtraction:
    return CaseExtraction(
        facts={
            path: ExtractedFact(clarity="missing")
            for path in extraction_mod.DOMAIN_FACT_PATHS[domain]
        },
        entities={
            entity_type: []
            for entity_type in extraction_mod.DOMAIN_ENTITY_FIELDS[domain]
        },
    )


def test_domain_failure_keeps_successful_parallel_extractions(monkeypatch):
    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        if domain == "contact_channels":
            raise AppError(
                "model_unreachable",
                "测试域失败",
                502,
                correction_hint="测试连接错误明细",
            )
        result = _missing_domain(domain)
        if focus_paths is None:
            return result
        return CaseExtraction(facts={path: result.facts[path] for path in focus_paths})

    monkeypatch.setattr(extraction_mod, "_request_domain", request)

    with pytest.raises(extraction_mod.TemplateDomainFailure) as error:
        asyncio.run(extraction_mod.extract_template_facts(
            _document(),
            {},
            max_concurrency=7,
        ))

    assert error.value.failed_domains == ["contact_channels"]
    assert error.value.domain_errors == {"contact_channels": "model_unreachable"}
    assert error.value.domain_error_details == {"contact_channels": "测试连接错误明细"}
    expected_paths = {
        path
        for domain in extraction_mod.DOMAIN_ORDER
        if domain != "contact_channels"
        for path in extraction_mod.DOMAIN_FACT_PATHS[domain]
    }
    assert set(error.value.partial_extraction.facts) == expected_paths


def _rule(*required_fields: str, condition: RuleCondition | None = None) -> TemplateRule:
    return TemplateRule(
        ruleId="CASE-TEST",
        name="模板测试规则",
        group="CASE",
        sourceParagraphs=[20],
        sourceMarker="p020-q1",
        sourceKind="question",
        scope="conditional" if condition else "common",
        appliesWhen=condition,
        requiredFields=list(required_fields),
        suggestedQuestion="请补充测试事实。",
        severity="high",
    )


def test_domain_schema_is_strict_and_requires_all_declared_fact_paths():
    schema = extraction_mod.template_extraction_schema("online_money")

    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"facts", "entities", "failedDomains"}
    facts = schema["properties"]["facts"]
    assert facts["additionalProperties"] is False
    assert facts["required"] == list(extraction_mod.DOMAIN_FACT_PATHS["online_money"])
    assert facts["properties"]["online_money.used"]["properties"]["value"]["type"] == ["boolean", "null"]
    assert facts["properties"]["online_money.total"]["properties"]["value"]["type"] == ["number", "null"]
    assert all(value["additionalProperties"] is False for value in facts["properties"].values())
    assert all("sourceConfidence" not in value["properties"] for value in facts["properties"].values())


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


def test_request_uses_same_contract_for_prompt_and_schema(monkeypatch):
    payload = _missing_domain("online_money").model_dump()
    for fact in payload["facts"].values():
        fact.pop("sourceConfidence")
    request = AsyncMock(return_value=payload)
    monkeypatch.setattr(extraction_mod, "request_structured_payload", request)

    asyncio.run(extraction_mod._request_domain(
        _DummyClient(),
        _document(),
        "online_money",
    ))

    kwargs = request.await_args.kwargs
    assert "是否发生线上资金转出" in kwargs["messages"][1]["content"]
    used = kwargs["schema"]["properties"]["facts"]["properties"]["online_money.used"]
    assert used["properties"]["value"]["type"] == ["boolean", "null"]


def test_domain_prompt_hides_blank_answer_anchor_blocks():
    document = _document()
    document.questionAnswers[0].answerClarity = "blank"

    prompt = render_domain_prompt(document, DOMAIN_CONTRACTS["online_money"])

    assert "[锚点:A001,A002]" not in prompt


def test_invalid_or_missing_model_evidence_is_normalized_fail_closed():
    payload = {
        "facts": {
            "money.credentials_disclosed": {
                "value": True,
                "clarity": "clear",
                "evidenceAnchorIds": ["A022"],
            },
            "money.remote_control_used": {
                "value": True,
                "clarity": "clear",
                "evidenceAnchorIds": [],
            },
        },
        "entities": {},
        "failedDomains": [],
    }

    normalized = extraction_mod._normalize_unsupported_evidence(payload, {"A001"})

    assert normalized == ["money.credentials_disclosed", "money.remote_control_used"]
    for fact in payload["facts"].values():
        assert fact == {"value": None, "clarity": "unknown", "evidenceAnchorIds": []}


def test_valid_model_evidence_is_not_normalized():
    fact = {"value": True, "clarity": "clear", "evidenceAnchorIds": ["A001"]}
    payload = {"facts": {"online_money.used": fact.copy()}, "entities": {}, "failedDomains": []}

    normalized = extraction_mod._normalize_unsupported_evidence(payload, {"A001"})

    assert normalized == []
    assert payload["facts"]["online_money.used"] == fact


def test_domain_schema_constrains_evidence_to_document_anchor_aliases():
    schema = extraction_mod.template_extraction_schema(
        "header_procedure",
        allowed_anchor_ids=("A001", "A002"),
    )

    fact = next(iter(schema["properties"]["facts"]["properties"].values()))
    evidence = fact["properties"]["evidenceAnchorIds"]
    assert evidence["maxItems"] == 5
    assert evidence["items"] == {
        "$ref": "#/$defs/anchorId",
    }
    assert schema["$defs"]["anchorId"] == {"type": "string", "enum": ["A001", "A002"]}


def test_unknown_fact_requires_no_evidence_anchor():
    document = _document()
    extraction = _missing_domain("case_timeline")
    extraction.facts["case.report_reason"] = ExtractedFact(
        clarity="unknown",
        evidenceAnchorIds=[],
    )

    validated = extraction_mod.validate_domain_extraction(document, "case_timeline", extraction)

    assert validated.facts["case.report_reason"].clarity == "unknown"


def test_unknown_fact_with_evidence_returns_an_actionable_correction_hint():
    document = _document()
    extraction = _missing_domain("case_timeline")
    extraction.facts["case.report_reason"] = ExtractedFact(
        clarity="unknown",
        evidenceAnchorIds=["a1"],
    )

    with pytest.raises(AppError) as error:
        extraction_mod.validate_domain_extraction(document, "case_timeline", extraction)

    assert error.value.field == "case.report_reason"
    assert "evidenceAnchorIds=[]" in (error.value.correction_hint or "")


def test_domain_schema_avoids_provider_unsupported_unique_items_keyword():
    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    assert "uniqueItems" not in set(keys(extraction_mod.template_extraction_schema("online_money")))


def test_focused_domain_schema_requires_only_selected_fact_paths():
    schema = extraction_mod.template_extraction_schema(
        "contact_channels",
        fact_paths=("contact.chat_used",),
    )

    facts = schema["properties"]["facts"]
    assert facts["required"] == ["contact.chat_used"]
    assert set(facts["properties"]) == {"contact.chat_used"}
    assert schema["properties"]["entities"]["properties"] == {}


def test_prompt_excludes_question_when_only_answer_is_template_guidance():
    document = _document(
        "讲一下基本情况？（只能作为模板指导）",
        "（不要当作案件事实）",
    )

    prompt = extraction_mod.build_domain_prompt(document, "header_procedure")

    assert "讲一下基本情况？" not in prompt
    assert "只能作为模板指导" not in prompt
    assert "不要当作案件事实" not in prompt


def test_all_domain_prompts_explain_checkbox_markers_without_choice_inference():
    document = _document("你选择哪些渠道？", "[选中] 电话 [未选] 短信 [状态不明] APP")

    for domain in extraction_mod.DOMAIN_ORDER:
        prompt = extraction_mod.build_domain_prompt(document, domain)

        assert "[选中]" in prompt
        assert "[未选]" in prompt
        assert "不得作为肯定的案件事实" in prompt
        assert "[状态不明]" in prompt
        assert "不得自行判断" in prompt
        assert "不代表解析程序已经判断单选或多选" in prompt


def test_prompt_requires_entity_ids_to_be_unique_across_the_domain():
    prompt = extraction_mod.build_domain_prompt(_document(), "offline_delivery")

    assert "实体 ID 在整个业务域内必须唯一" in prompt


def test_prompt_declares_required_entities_even_for_one_occurrence():
    prompt = extraction_mod.build_domain_prompt(_document(), "offline_delivery")

    assert '"withdrawals": ["bank", "branch", "address", "time", "amount"]' in prompt
    assert '"offline_handoffs": ["time", "location", "property_type", "amount_or_value", "method", "recipient_or_logistics"]' in prompt
    assert "即使只发生一次也必须创建一条实体" in prompt
    assert "已明确笔数但逐笔信息缺失时，也必须创建与笔数相同的实体" in prompt
    assert "缺少的实体字段按 missing 或 unknown 返回" in prompt


def test_focused_prompt_requests_only_the_selected_domain_paths():
    prompt = extraction_mod.build_domain_prompt(
        _document(),
        "contact_channels",
        focus_paths=("contact.chat_used",),
    )

    assert '必须逐项返回这些事实路径：["contact.chat_used"]' in prompt
    assert "contact.initial_channel" not in prompt


def test_prompt_uses_short_anchor_aliases_instead_of_raw_paragraph_ids():
    prompt = extraction_mod.build_domain_prompt(_document(), "case_timeline")

    assert "[锚点:A001,A002]" in prompt
    assert "[锚点:q1,a1]" not in prompt


def test_prompt_exposes_one_anchor_for_a_complete_qa_evidence_block():
    document = _document()
    qa_id = document.questionAnswers[0].id
    document.evidenceBlocks = [
        EvidenceBlock(id=qa_id, kind="qa", text="问：完整问题？\n答：完整答案。", paragraphIds=["q1", "a1"], page=1, paragraph=1),
    ]

    prompt = extraction_mod.build_domain_prompt(document, "case_timeline")
    schema = extraction_mod.template_extraction_schema("case_timeline", allowed_anchor_ids=("A001",))

    assert "[锚点:A001]" in prompt
    assert "[锚点:A001,A002]" not in prompt
    assert schema["$defs"]["anchorId"]["enum"] == ["A001"]


def test_case_timeline_prompt_forbids_inference_from_isolated_events():
    prompt = extraction_mod.build_domain_prompt(_document(), "case_timeline")

    assert "case.timeline 只在笔录明确形成完整、连续的经过陈述时抽取" in prompt
    assert "不得用零散联系、风险提示、转账或交付时间推断" in prompt


def test_money_domain_prompts_separate_online_transfers_from_offline_delivery():
    online = extraction_mod.build_domain_prompt(_document(), "online_money")
    offline = extraction_mod.build_domain_prompt(_document(), "offline_delivery")

    assert "不得把现金取款或线下交付次数当成线上转账笔数" in online
    assert "不得把线上转账、扫码付款或返款笔数当成取现或线下交付次数" in offline
    assert "只有明确出现银行取现、现金或实物线下交接证据" in offline


def test_domain_request_maps_anchor_aliases_back_to_paragraph_ids(monkeypatch):
    document = _document()
    monkeypatch.setattr(extraction_mod, "QWEN_BASE_URL", "http://model.test/v1")
    monkeypatch.setattr(extraction_mod, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(extraction_mod, "QWEN_MODEL", "test-model")
    request = AsyncMock(return_value={
        "facts": {
            "case.report_reason": {
                "value": "测试报案原因",
                "clarity": "clear",
                "evidenceAnchorIds": ["A002"],
            },
        },
        "entities": {},
        "failedDomains": [],
    })
    monkeypatch.setattr(extraction_mod, "request_structured_payload", request)

    extraction = asyncio.run(extraction_mod._request_domain(
        _DummyClient(),
        document,
        "case_timeline",
        focus_paths=("case.report_reason",),
    ))

    assert extraction.facts["case.report_reason"].evidenceAnchorIds == ["a1"]


def test_invalid_anchor_retries_once_with_schema_feedback(monkeypatch):
    document = _document()
    invalid = CaseExtraction(
        facts={
            "case.report_reason": ExtractedFact(
                value="测试报案原因",
                clarity="clear",
                evidenceAnchorIds=["missing-anchor"],
            ),
        },
    )
    request = AsyncMock(return_value=invalid)
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod, "QWEN_SCHEMA_RETRIES", 1, raising=False)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(extraction_mod.TemplateDomainFailure):
        asyncio.run(extraction_mod.extract_template_facts(
            document,
            {},
            domains=("case_timeline",),
            focus_paths=("case.report_reason",),
        ))

    assert request.await_count == 2


def test_guidance_only_anchor_cannot_support_a_case_fact():
    document = _document(
        "讲一下基本情况？（模板填写说明）",
        "（这里只是填写指导）",
    )
    extraction = _missing_domain("header_procedure")
    extraction.facts["victim.name"] = ExtractedFact(
        value="这里只是填写指导",
        clarity="clear",
        evidenceAnchorIds=["a1"],
    )

    with pytest.raises(AppError) as error:
        extraction_mod.validate_domain_extraction(document, "header_procedure", extraction)

    assert error.value.code == "invalid_model_evidence"


def test_comma_joined_valid_anchor_ids_are_normalized_without_weakening_validation():
    document = _document()
    extraction = _missing_domain("contact_channels")
    extraction.facts["contact.initial_channel"] = ExtractedFact(
        value="测试短信", clarity="clear", evidenceAnchorIds=["q1,a1"],
    )

    validated = extraction_mod.validate_domain_extraction(
        document, "contact_channels", extraction,
    )

    assert validated.facts["contact.initial_channel"].evidenceAnchorIds == ["q1", "a1"]


def test_known_scalar_fact_shape_is_wrapped_only_with_unique_qa_evidence():
    document = _document(
        "你有没有在什么地方透露过相关个人信息？",
        "我填写过姓名和手机号。",
    )
    payload = {"facts": {"privacy.disclosure_occurred": True}}

    normalized = extraction_mod._normalize_known_fact_deviations(document, payload)

    assert normalized == ["privacy.disclosure_occurred"]
    assert payload["facts"]["privacy.disclosure_occurred"] == {
        "value": True,
        "clarity": "clear",
        "evidenceAnchorIds": ["A002"],
    }


def test_explicit_chat_use_uncertainty_overrides_false_inference():
    document = _document(
        "你使用的聊天软件是否进行了实名登记？",
        "无法判断我和对方是否使用过聊天软件，也无法核验账号是否实名。",
    )
    payload = {"facts": {"contact.chat_used": {
        "value": False,
        "clarity": "clear",
        "evidenceAnchorIds": ["A002"],
    }}}

    normalized = extraction_mod._normalize_known_fact_deviations(document, payload)

    assert normalized == ["contact.chat_used"]
    assert payload["facts"]["contact.chat_used"] == {
        "value": None,
        "clarity": "unknown",
        "evidenceAnchorIds": [],
    }


def test_domain_merge_preserves_all_repeated_entities(monkeypatch):
    document = _document()
    online = _missing_domain("online_money")
    online.facts["online_money.used"] = ExtractedFact(
        value=True, clarity="clear", evidenceAnchorIds=["a1"],
    )
    online.facts["online_money.transfer_count"] = ExtractedFact(
        value=2, clarity="clear", evidenceAnchorIds=["a1"],
    )
    online.entities["transfers"] = [
        ExtractedEntity(
            id="transfer-1",
            entityType="transfers",
            fields={"amount": ExtractedFact(value=100, clarity="clear", evidenceAnchorIds=["a1"])},
        ),
        ExtractedEntity(
            id="transfer-2",
            entityType="transfers",
            fields={"amount": ExtractedFact(value=200, clarity="clear", evidenceAnchorIds=["a1"])},
        ),
    ]
    request = AsyncMock(return_value=online)
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(extraction_mod.extract_template_facts(
        document,
        {},
        domains=("online_money",),
    ))

    assert [entity.id for entity in extraction.entities["transfers"]] == ["transfer-1", "transfer-2"]


def test_duplicate_entity_id_returns_an_actionable_correction_hint():
    document = _document()
    extraction = _missing_domain("offline_delivery")
    extraction.entities["withdrawals"] = [
        ExtractedEntity(id="offline-1", entityType="withdrawals", fields={}),
    ]
    extraction.entities["offline_handoffs"] = [
        ExtractedEntity(id="offline-1", entityType="offline_handoffs", fields={}),
    ]

    with pytest.raises(AppError) as error:
        extraction_mod.validate_domain_extraction(document, "offline_delivery", extraction)

    assert "实体 ID 在整个业务域内必须唯一" in (error.value.correction_hint or "")


def test_repeat_entity_count_must_match_the_declared_count_fact():
    document = _document()
    extraction = _missing_domain("online_money")
    extraction.facts["online_money.used"] = ExtractedFact(
        value=True, clarity="clear", evidenceAnchorIds=["a1"],
    )
    extraction.facts["online_money.transfer_count"] = ExtractedFact(
        value=1, clarity="clear", evidenceAnchorIds=["a1"],
    )
    extraction.entities["transfers"] = [
        ExtractedEntity(id="transfer-1", entityType="transfers", fields={}),
        ExtractedEntity(id="transfer-2", entityType="transfers", fields={}),
    ]

    with pytest.raises(AppError) as error:
        extraction_mod.validate_domain_extraction(document, "online_money", extraction)

    assert "online_money.transfer_count" in (error.value.correction_hint or "")


def test_domain_entities_require_clear_positive_applicability():
    document = _document()
    extraction = _missing_domain("online_money")
    extraction.entities["transfers"] = [
        ExtractedEntity(id="transfer-1", entityType="transfers", fields={}),
    ]

    with pytest.raises(AppError) as error:
        extraction_mod.validate_domain_extraction(document, "online_money", extraction)

    assert "online_money.used" in (error.value.correction_hint or "")


def test_multiple_domains_merge_without_overwriting_facts(monkeypatch):
    document = _document()
    first = _missing_domain("case_timeline")
    first.facts["case.report_reason"] = ExtractedFact(value="测试原因", clarity="clear", evidenceAnchorIds=["a1"])
    second = _missing_domain("contact_channels")
    second.facts["contact.initial_channel"] = ExtractedFact(value="测试短信", clarity="clear", evidenceAnchorIds=["a1"])

    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        source = first if domain == "case_timeline" else second
        if focus_paths is None:
            return source
        return CaseExtraction(facts={path: source.facts[path] for path in focus_paths})

    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(extraction_mod.extract_template_facts(
        document,
        {},
        domains=("case_timeline", "contact_channels"),
    ))

    assert extraction.facts["case.report_reason"].value == "测试原因"
    assert extraction.facts["contact.initial_channel"].value == "测试短信"


def test_focused_extraction_accepts_the_selected_fact_subset(monkeypatch):
    document = _document()
    focused = CaseExtraction(facts={
        "contact.chat_used": ExtractedFact(clarity="missing"),
    })
    request = AsyncMock(return_value=focused)
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(extraction_mod.extract_template_facts(
        document,
        {},
        domains=("contact_channels",),
        focus_paths=("contact.chat_used",),
    ))

    assert set(extraction.facts) == {"contact.chat_used"}
    assert request.await_args.args[4] == ("contact.chat_used",)


def test_large_entity_free_domain_uses_one_strict_schema_request(monkeypatch):
    document = _document()
    requested_batches: list[tuple[str, ...] | None] = []

    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        assert domain == "case_timeline"
        requested_batches.append(focus_paths)
        return _missing_domain(domain)

    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(extraction_mod.extract_template_facts(
        document,
        {},
        domains=("case_timeline",),
    ))

    assert requested_batches == [None]
    assert set(extraction.facts) == set(extraction_mod.DOMAIN_FACT_PATHS["case_timeline"])


def test_schema_failure_retries_domain_once_with_validation_feedback(monkeypatch):
    error = AppError(
        "invalid_model_schema",
        "测试字段类型错误。",
        502,
        retry_strategy="schema",
        field="online_money.used",
        correction_hint="必须返回 boolean。",
    )
    request = AsyncMock(side_effect=[error, _missing_domain("online_money")])
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod, "QWEN_SCHEMA_RETRIES", 1, raising=False)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    asyncio.run(extraction_mod.extract_template_facts(
        _document(),
        {},
        domains=("online_money",),
    ))

    assert request.await_count == 2
    assert request.await_args_list[0].args[3] is None
    assert request.await_args_list[1].args[3] is error


def test_configured_schema_retries_control_attempt_count(monkeypatch):
    document = _document()
    schema_error = AppError(
        "invalid_model_response",
        "模型域结果无效。",
        502,
        retry_strategy="schema",
        correction_hint="必须返回有效 JSON。",
    )
    request = AsyncMock(side_effect=schema_error)
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod, "QWEN_SCHEMA_RETRIES", 2, raising=False)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(AppError) as error:
        asyncio.run(extraction_mod.extract_template_facts(
            document,
            {},
            domains=("case_timeline",),
        ))

    assert request.await_count == 3
    assert request.await_args_list[0].args[3] is None
    assert all(call.args[3] is schema_error for call in request.await_args_list[1:])
    assert error.value.code == "template_domain_failed"


def test_non_retryable_domain_error_stops_after_one_attempt(monkeypatch):
    document = _document()
    request = AsyncMock(side_effect=AppError("model_request_failed", "Qwen 返回 HTTP 400。", 502))
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(AppError):
        asyncio.run(extraction_mod.extract_template_facts(
            document,
            {},
            domains=("case_timeline",),
        ))

    assert request.await_count == 1


def test_network_failure_retries_once_without_content_correction(monkeypatch):
    document = _document()
    request = AsyncMock(side_effect=AppError(
        "model_unreachable",
        "模型服务不可达。",
        503,
        retry_strategy="schema",
    ))
    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod, "QWEN_TRANSIENT_RETRIES", 1, raising=False)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(AppError):
        asyncio.run(extraction_mod.extract_template_facts(
            document,
            {},
            domains=("case_timeline",),
        ))

    assert request.await_count == 2
    assert all(call.args[3] is None for call in request.await_args_list)


def test_review_uses_deterministic_results_without_semantic_recheck_when_clear(monkeypatch):
    document = _document()
    extraction = CaseExtraction(facts={
        "case.report_reason": ExtractedFact(
            value="测试报案原因",
            clarity="clear",
            evidenceAnchorIds=["a1"],
        ),
    })
    extract = AsyncMock(return_value=extraction)
    recheck = AsyncMock()
    monkeypatch.setattr(extraction_mod, "extract_template_facts", extract)
    monkeypatch.setattr(extraction_mod, "recheck_ambiguous_facts", recheck)

    results = asyncio.run(extraction_mod.review_template_document(
        document,
        group_timings={},
        rules=[_rule("case.report_reason")],
    ))

    assert results[0].status == RuleStatus.COVERED
    assert results[0].evidenceAnchorIds == ["a1"]
    recheck.assert_not_awaited()


def test_blank_question_evidence_replaces_unrelated_model_anchor(monkeypatch):
    document = _document("是否还有补充?", "")
    extraction = CaseExtraction(facts={
        "case.additional_statement": ExtractedFact(
            value="没有其他要求",
            clarity="unclear",
            evidenceAnchorIds=["q1"],
        ),
    })
    extract = AsyncMock(return_value=extraction)
    monkeypatch.setattr(extraction_mod, "extract_template_facts", extract)
    rule = _rule("case.additional_statement").model_copy(update={
        "ruleId": "EXTRA-001",
        "questionPatterns": ["是否还有补充"],
    })

    results = asyncio.run(extraction_mod.review_template_document(
        document,
        group_timings={},
        rules=[rule],
    ))

    assert results[0].status == RuleStatus.INCOMPLETE
    assert results[0].evidence == "问：是否还有补充?\n答："


def test_question_matching_ignores_punctuation_and_accepts_synonym_alternatives():
    document = _document("请问：你下载过国家反诈中心应用吗？", "已经下载安装。")
    rule = _rule("prevention.anti_fraud_app_installed").model_copy(update={
        "ruleId": "PREV-003",
        "questionPatterns": ["国家反诈中心", "APP|应用"],
    })

    states, anchors = extraction_mod._question_states(document, [rule])

    assert states == {"PREV-003": "answered"}
    assert anchors["PREV-003"]


def test_question_state_keeps_unclear_answer_distinct_from_clear_answer():
    document = _document("你以前是否接收过反诈宣传？", "我不清楚。")
    rule = _rule("prevention.received_publicity").model_copy(update={
        "ruleId": "PREV-001",
        "questionPatterns": ["反诈宣传"],
    })

    states, _ = extraction_mod._question_states(document, [rule])

    assert states == {"PREV-001": "unclear"}


def test_every_question_rule_has_patterns_for_missing_vs_blank_classification():
    question_rules = [rule for rule in extraction_mod.TEMPLATE_RULES if rule.sourceKind == "question"]

    assert question_rules
    assert all(rule.questionPatterns for rule in question_rules)


def test_all_question_rules_match_the_baseline_fixture():
    fixture = Path(__file__).parent.parent / "test-fixtures" / "01-baseline.docx"
    document = asyncio.run(parse_document(fixture.name, fixture.read_bytes()))
    question_rules = [rule for rule in extraction_mod.TEMPLATE_RULES if rule.sourceKind == "question"]

    states, _ = extraction_mod._question_states(document, question_rules)

    assert set(states) == {rule.ruleId for rule in question_rules}


def test_general_publicity_blank_answer_is_not_masked_by_answered_community_question():
    fixture = Path(__file__).parent.parent / "test-fixtures" / "03-blank-answer.docx"
    document = asyncio.run(parse_document(fixture.name, fixture.read_bytes()))
    rule = next(rule for rule in extraction_mod.TEMPLATE_RULES if rule.ruleId == "PREV-001")

    states, _ = extraction_mod._question_states(document, [rule])

    assert states == {"PREV-001": "blank"}


def test_ambiguous_applicability_does_not_trigger_model_recheck(monkeypatch):
    document = _document()
    initial = CaseExtraction(facts={
        "offline.used": ExtractedFact(clarity="missing"),
        "offline.delivery_method": ExtractedFact(clarity="missing"),
    })
    extract = AsyncMock(return_value=initial)
    recheck = AsyncMock()
    monkeypatch.setattr(extraction_mod, "extract_template_facts", extract)
    monkeypatch.setattr(extraction_mod, "recheck_ambiguous_facts", recheck)
    rule = _rule(
        "offline.delivery_method",
        condition=RuleCondition(path="offline.used", operator="equals", value=True),
    )

    results = asyncio.run(extraction_mod.review_template_document(
        document,
        group_timings={},
        rules=[rule],
    ))

    assert results[0].status == RuleStatus.NEEDS_MANUAL_REVIEW
    recheck.assert_not_awaited()
