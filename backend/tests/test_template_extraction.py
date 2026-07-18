import asyncio
from unittest.mock import AsyncMock

import pytest

from app.errors import AppError
from app.models import DocumentPage, DocumentParagraph, ParsedDocument, RuleStatus, SourceType
from app.services.question_answer import reconstruct_question_answers
from app.services import template_extraction
from app.services import qwen
from app.template_models import (
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
        tool_description="提交脱敏测试结果。",
    ))

    assert request.await_args.args[1]["temperature"] == 0


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
            for path in template_extraction.DOMAIN_FACT_PATHS[domain]
        },
        entities={
            entity_type: []
            for entity_type in template_extraction.DOMAIN_ENTITY_FIELDS[domain]
        },
    )


def test_domain_failure_keeps_successful_parallel_extractions(monkeypatch):
    async def request(_client, _document, domain, *_args):
        if domain == "contact_channels":
            raise AppError(
                "model_unreachable",
                "测试域失败",
                502,
                correction_hint="测试连接错误明细",
            )
        return _missing_domain(domain)

    monkeypatch.setattr(template_extraction, "_request_domain", request)

    with pytest.raises(template_extraction.TemplateDomainFailure) as error:
        asyncio.run(template_extraction.extract_template_facts(
            _document(),
            {},
            max_concurrency=7,
        ))

    assert error.value.failed_domains == ["contact_channels"]
    assert error.value.domain_errors == {"contact_channels": "model_unreachable"}
    assert error.value.domain_error_details == {"contact_channels": "测试连接错误明细"}
    expected_paths = {
        path
        for domain in template_extraction.DOMAIN_ORDER
        if domain != "contact_channels"
        for path in template_extraction.DOMAIN_FACT_PATHS[domain]
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
    schema = template_extraction.template_extraction_schema("online_money")

    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"facts", "entities", "failedDomains"}
    facts = schema["properties"]["facts"]
    assert facts["additionalProperties"] is False
    assert facts["required"] == list(template_extraction.DOMAIN_FACT_PATHS["online_money"])
    assert facts["properties"]["online_money.total"]["additionalProperties"] is False
    assert "sourceConfidence" not in facts["properties"]["online_money.total"]["properties"]


def test_domain_schema_avoids_provider_unsupported_unique_items_keyword():
    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    assert "uniqueItems" not in set(keys(template_extraction.template_extraction_schema("online_money")))


def test_focused_domain_schema_requires_only_selected_fact_paths():
    schema = template_extraction.template_extraction_schema(
        "contact_channels",
        fact_paths=("contact.chat_used",),
    )

    facts = schema["properties"]["facts"]
    assert facts["required"] == ["contact.chat_used"]
    assert set(facts["properties"]) == {"contact.chat_used"}
    assert schema["properties"]["entities"]["properties"] == {}


def test_prompt_excludes_parenthetical_template_guidance():
    document = _document(
        "讲一下基本情况？（只能作为模板指导）",
        "（不要当作案件事实）",
    )

    prompt = template_extraction.build_domain_prompt(document, "header_procedure")

    assert "讲一下基本情况？" in prompt
    assert "只能作为模板指导" not in prompt
    assert "不要当作案件事实" not in prompt


def test_prompt_requires_entity_ids_to_be_unique_across_the_domain():
    prompt = template_extraction.build_domain_prompt(_document(), "offline_delivery")

    assert "实体 ID 在整个业务域内必须唯一" in prompt


def test_prompt_declares_required_entities_even_for_one_occurrence():
    prompt = template_extraction.build_domain_prompt(_document(), "offline_delivery")

    assert '"withdrawals": ["bank", "branch", "address", "time", "amount"]' in prompt
    assert '"offline_handoffs": ["time", "location", "property_type", "amount_or_value", "method", "recipient_or_logistics"]' in prompt
    assert "即使只发生一次也必须创建一条实体" in prompt
    assert "已明确笔数但逐笔信息缺失时，也必须创建与笔数相同的实体" in prompt
    assert "缺少的实体字段按 missing 或 unknown 返回" in prompt


def test_focused_prompt_requests_only_the_selected_domain_paths():
    prompt = template_extraction.build_domain_prompt(
        _document(),
        "contact_channels",
        focus_paths=("contact.chat_used",),
    )

    assert '必须逐项返回这些事实路径：["contact.chat_used"]' in prompt
    assert "contact.initial_channel" not in prompt


def test_prompt_uses_short_anchor_aliases_instead_of_raw_paragraph_ids():
    prompt = template_extraction.build_domain_prompt(_document(), "case_timeline")

    assert "[锚点:A001,A002]" in prompt
    assert "[锚点:q1,a1]" not in prompt


def test_case_timeline_prompt_forbids_inference_from_isolated_events():
    prompt = template_extraction.build_domain_prompt(_document(), "case_timeline")

    assert "case.timeline 只在笔录明确形成完整、连续的经过陈述时抽取" in prompt
    assert "不得用零散联系、风险提示、转账或交付时间推断" in prompt


def test_money_domain_prompts_separate_online_transfers_from_offline_delivery():
    online = template_extraction.build_domain_prompt(_document(), "online_money")
    offline = template_extraction.build_domain_prompt(_document(), "offline_delivery")

    assert "不得把现金取款或线下交付次数当成线上转账笔数" in online
    assert "不得把线上转账、扫码付款或返款笔数当成取现或线下交付次数" in offline
    assert "只有明确出现银行取现、现金或实物线下交接证据" in offline


def test_domain_request_maps_anchor_aliases_back_to_paragraph_ids(monkeypatch):
    document = _document()
    monkeypatch.setattr(template_extraction, "QWEN_BASE_URL", "http://model.test/v1")
    monkeypatch.setattr(template_extraction, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(template_extraction, "QWEN_MODEL", "test-model")
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
    monkeypatch.setattr(template_extraction, "request_structured_payload", request)

    extraction = asyncio.run(template_extraction._request_domain(
        _DummyClient(),
        document,
        "case_timeline",
        focus_paths=("case.report_reason",),
    ))

    assert extraction.facts["case.report_reason"].evidenceAnchorIds == ["a1"]


def test_invalid_anchor_is_retried_once_and_valid_result_is_accepted(monkeypatch):
    document = _document()
    invalid = _missing_domain("case_timeline")
    invalid.facts["case.report_reason"] = ExtractedFact(
        value="测试报案原因",
        clarity="clear",
        evidenceAnchorIds=["missing-anchor"],
    )
    valid = _missing_domain("case_timeline")
    valid.facts["case.report_reason"] = ExtractedFact(
        value="测试报案原因",
        clarity="clear",
        evidenceAnchorIds=["a1"],
    )
    request = AsyncMock(side_effect=[invalid, valid])
    monkeypatch.setattr(template_extraction, "_request_domain", request)
    monkeypatch.setattr(template_extraction.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(template_extraction.extract_template_facts(
        document,
        {},
        domains=("case_timeline",),
    ))

    assert request.await_count == 2
    assert extraction.facts["case.report_reason"].evidenceAnchorIds == ["a1"]


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
        template_extraction.validate_domain_extraction(document, "header_procedure", extraction)

    assert error.value.code == "invalid_model_evidence"


def test_comma_joined_valid_anchor_ids_are_normalized_without_weakening_validation():
    document = _document()
    extraction = _missing_domain("contact_channels")
    extraction.facts["contact.initial_channel"] = ExtractedFact(
        value="测试短信", clarity="clear", evidenceAnchorIds=["q1,a1"],
    )

    validated = template_extraction.validate_domain_extraction(
        document, "contact_channels", extraction,
    )

    assert validated.facts["contact.initial_channel"].evidenceAnchorIds == ["q1", "a1"]


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
    monkeypatch.setattr(template_extraction, "_request_domain", request)
    monkeypatch.setattr(template_extraction.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(template_extraction.extract_template_facts(
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
        template_extraction.validate_domain_extraction(document, "offline_delivery", extraction)

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
        template_extraction.validate_domain_extraction(document, "online_money", extraction)

    assert "online_money.transfer_count" in (error.value.correction_hint or "")


def test_domain_entities_require_clear_positive_applicability():
    document = _document()
    extraction = _missing_domain("online_money")
    extraction.entities["rebates"] = [
        ExtractedEntity(id="rebate-1", entityType="rebates", fields={}),
    ]

    with pytest.raises(AppError) as error:
        template_extraction.validate_domain_extraction(document, "online_money", extraction)

    assert "online_money.used" in (error.value.correction_hint or "")


def test_multiple_domains_merge_without_overwriting_facts(monkeypatch):
    document = _document()
    first = _missing_domain("case_timeline")
    first.facts["case.report_reason"] = ExtractedFact(value="测试原因", clarity="clear", evidenceAnchorIds=["a1"])
    second = _missing_domain("contact_channels")
    second.facts["contact.initial_channel"] = ExtractedFact(value="测试短信", clarity="clear", evidenceAnchorIds=["a1"])

    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        assert focus_paths is None
        return first if domain == "case_timeline" else second

    monkeypatch.setattr(template_extraction, "_request_domain", request)
    monkeypatch.setattr(template_extraction.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(template_extraction.extract_template_facts(
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
    monkeypatch.setattr(template_extraction, "_request_domain", request)
    monkeypatch.setattr(template_extraction.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    extraction = asyncio.run(template_extraction.extract_template_facts(
        document,
        {},
        domains=("contact_channels",),
        focus_paths=("contact.chat_used",),
    ))

    assert set(extraction.facts) == {"contact.chat_used"}
    assert request.await_args.args[4] == ("contact.chat_used",)


def test_one_failed_domain_prevents_a_complete_extraction(monkeypatch):
    document = _document()
    request = AsyncMock(side_effect=AppError(
        "invalid_model_response",
        "模型域结果无效。",
        502,
        retry_strategy="schema",
    ))
    monkeypatch.setattr(template_extraction, "_request_domain", request)
    monkeypatch.setattr(template_extraction.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    with pytest.raises(AppError) as error:
        asyncio.run(template_extraction.extract_template_facts(
            document,
            {},
            domains=("case_timeline",),
        ))

    assert request.await_count == 3
    assert error.value.code == "template_domain_failed"


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
    monkeypatch.setattr(template_extraction, "extract_template_facts", extract)
    monkeypatch.setattr(template_extraction, "recheck_ambiguous_facts", recheck)

    results = asyncio.run(template_extraction.review_template_document(
        document,
        group_timings={},
        rules=[_rule("case.report_reason")],
    ))

    assert results[0].status == RuleStatus.COVERED
    assert results[0].evidenceAnchorIds == ["a1"]
    recheck.assert_not_awaited()


def test_only_ambiguous_applicability_receives_targeted_recheck(monkeypatch):
    document = _document()
    initial = CaseExtraction(facts={
        "offline.used": ExtractedFact(clarity="missing"),
        "offline.delivery_method": ExtractedFact(clarity="missing"),
    })
    resolved = CaseExtraction(facts={
        "offline.used": ExtractedFact(value=False, clarity="clear", evidenceAnchorIds=["a1"]),
        "offline.delivery_method": ExtractedFact(clarity="missing"),
    })
    extract = AsyncMock(return_value=initial)
    recheck = AsyncMock(return_value=resolved)
    monkeypatch.setattr(template_extraction, "extract_template_facts", extract)
    monkeypatch.setattr(template_extraction, "recheck_ambiguous_facts", recheck)
    rule = _rule(
        "offline.delivery_method",
        condition=RuleCondition(path="offline.used", operator="equals", value=True),
    )

    results = asyncio.run(template_extraction.review_template_document(
        document,
        group_timings={},
        rules=[rule],
    ))

    assert results[0].status == RuleStatus.NOT_APPLICABLE
    recheck.assert_awaited_once()
    assert recheck.await_args.args[3] == [rule]
