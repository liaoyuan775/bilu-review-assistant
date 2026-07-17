import asyncio
from unittest.mock import AsyncMock

import pytest

from app.errors import AppError
from app.models import DocumentPage, DocumentParagraph, ParsedDocument, RuleStatus, SourceType
from app.services.question_answer import reconstruct_question_answers
from app.services import template_extraction
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
    return CaseExtraction(facts={
        path: ExtractedFact(clarity="missing")
        for path in template_extraction.DOMAIN_FACT_PATHS[domain]
    })


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


def test_prompt_excludes_parenthetical_template_guidance():
    document = _document(
        "讲一下基本情况？（只能作为模板指导）",
        "（不要当作案件事实）",
    )

    prompt = template_extraction.build_domain_prompt(document, "header_procedure")

    assert "讲一下基本情况？" in prompt
    assert "只能作为模板指导" not in prompt
    assert "不要当作案件事实" not in prompt


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


def test_domain_merge_preserves_all_repeated_entities(monkeypatch):
    document = _document()
    online = _missing_domain("online_money")
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

    assert request.await_count == 2
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
