import asyncio
import importlib

import pytest

from app.core.models import RuleStatus
from app.core import config
from app.review import extraction as extraction_mod
from app.core.template_models import CaseExtraction, ExtractedFact, TemplateReviewIssue


class _DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def _domain_result(domain: str) -> CaseExtraction:
    return CaseExtraction(facts={
        path: ExtractedFact(clarity="missing")
        for path in extraction_mod.DOMAIN_FACT_PATHS[domain]
    })


def test_independent_domains_use_configured_concurrency_without_losing_facts(monkeypatch):
    domains = extraction_mod.DOMAIN_ORDER
    active = 0
    max_active = 0

    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        result = _domain_result(domain)
        if focus_paths is None:
            return result
        return CaseExtraction(facts={path: result.facts[path] for path in focus_paths})

    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())
    timings = {}

    extraction = asyncio.run(extraction_mod.extract_template_facts(
        extraction_mod.ParsedDocument(
            name="performance.docx", format="DOCX", pageCount=1,
            pages=[], text="脱敏性能测试", sizeLabel="test",
        ),
        timings,
        domains=domains,
    ))

    assert extraction_mod.DEFAULT_DOMAIN_CONCURRENCY == config.QWEN_DOMAIN_CONCURRENCY
    assert max_active == config.QWEN_DOMAIN_CONCURRENCY
    assert set(extraction.facts) == {
        path for domain in domains for path in extraction_mod.DOMAIN_FACT_PATHS[domain]
    }
    assert set(timings) == set(domains)


def test_domain_concurrency_can_be_reduced_for_a_sequential_baseline(monkeypatch):
    domains = extraction_mod.DOMAIN_ORDER[:3]
    active = 0
    max_active = 0

    async def request(_client, _document, domain, _correction=None, focus_paths=None):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        result = _domain_result(domain)
        if focus_paths is None:
            return result
        return CaseExtraction(facts={path: result.facts[path] for path in focus_paths})

    monkeypatch.setattr(extraction_mod, "_request_domain", request)
    monkeypatch.setattr(extraction_mod.httpx, "AsyncClient", lambda **_kwargs: _DummyClient())

    asyncio.run(extraction_mod.extract_template_facts(
        extraction_mod.ParsedDocument(
            name="performance.docx", format="DOCX", pageCount=1,
            pages=[], text="脱敏性能测试", sizeLabel="test",
        ),
        {},
        domains=domains,
        max_concurrency=1,
    ))

    assert max_active == 1


def test_review_workflow_forwards_benchmark_concurrency(monkeypatch):
    observed: list[int] = []

    async def extract(
        _document,
        _timings,
        *,
        domains=extraction_mod.DOMAIN_ORDER,
        focus_paths=None,
        max_concurrency=2,
    ):
        observed.append(max_concurrency)
        return CaseExtraction()

    monkeypatch.setattr(extraction_mod, "extract_template_facts", extract)
    monkeypatch.setattr(extraction_mod, "evaluate_template_rules", lambda *_args: [])

    outcome = asyncio.run(extraction_mod.run_template_review(
        extraction_mod.ParsedDocument(
            name="performance.docx", format="DOCX", pageCount=1,
            pages=[], text="脱敏性能测试", sizeLabel="test",
        ),
        max_concurrency=1,
    ))

    assert observed == [1]
    assert outcome.results == []


def test_semantic_fingerprint_ignores_wording_but_detects_evidence_changes():
    extraction = CaseExtraction(facts={
        "case.summary": ExtractedFact(
            value="VALUE_TEST_CASE", clarity="clear", evidenceAnchorIds=["anchor-1"]
        )
    })
    issue = TemplateReviewIssue(
        ruleId="CASE-001", ruleName="案件概述", group="CASE",
        status=RuleStatus.COVERED, reason="第一种说明措辞", anchorIds=["anchor-1"],
        suggestedQuestion="", severity="high",
    )
    reworded = issue.model_copy(update={"reason": "另一种说明措辞"})

    first = extraction_mod.semantic_fingerprint(extraction, [issue])
    second = extraction_mod.semantic_fingerprint(extraction, [reworded])
    changed = extraction_mod.semantic_fingerprint(
        extraction,
        [reworded.model_copy(update={"anchorIds": ["anchor-2"]})],
    )

    assert first == second
    assert first != changed


def test_benchmark_summary_and_comparison_enforce_quality_and_ten_percent_gate():
    try:
        benchmark = importlib.import_module("scripts.benchmark_template_review")
    except ModuleNotFoundError:
        benchmark = None
    assert benchmark is not None, "benchmark_template_review must exist"

    before = benchmark.summarize_samples([
        {
            "totalMs": value,
            "parseMs": 10,
            "reviewMs": value - 10,
            "stageMs": {"case_timeline": value - 20},
            "requestCount": 8,
            "tokens": {"prompt": 100, "completion": 200, "total": 300},
            "qualityFingerprint": "same",
        }
        for value in (100, 120, 140, 160, 180)
    ])
    after = benchmark.summarize_samples([
        {
            "totalMs": value,
            "parseMs": 10,
            "reviewMs": value - 10,
            "stageMs": {"case_timeline": value - 20},
            "requestCount": 8,
            "tokens": {"prompt": 100, "completion": 200, "total": 300},
            "qualityFingerprint": "same",
        }
        for value in (80, 90, 100, 110, 120)
    ])

    assert before["durationMs"]["total"]["p50"] == 140
    assert before["durationMs"]["total"]["p95"] == 176
    assert before["requests"]["total"] == 40
    assert before["tokens"]["total"] == 1500
    comparison = benchmark.compare_summaries(before, after)
    assert comparison["qualityIdentical"] is True
    assert comparison["accepted"] is True
    assert comparison["p50ImprovementPercent"] > 10

    changed = dict(after)
    changed["qualityFingerprint"] = "changed"
    with pytest.raises(ValueError, match="quality fingerprint"):
        benchmark.compare_summaries(before, changed)


def test_benchmark_fingerprint_accepts_only_gold_equivalent_semantics_and_anchors():
    benchmark = importlib.import_module("scripts.benchmark_template_review")
    expected = CaseExtraction(facts={
        "case.report_reason": ExtractedFact(
            value="VALUE_TEST_CASE",
            clarity="clear",
            evidenceAnchorIds=["expected-anchor"],
        ),
    })
    first = expected.model_copy(deep=True)
    first.facts["case.report_reason"].evidenceAnchorIds = ["first-valid-anchor"]
    equivalent = expected.model_copy(deep=True)
    equivalent.facts["case.report_reason"].value = "笔录记录为 VALUE_TEST_CASE。"
    equivalent.facts["case.report_reason"].evidenceAnchorIds = ["second-valid-anchor"]
    changed = expected.model_copy(deep=True)
    changed.facts["case.report_reason"].value = "DIFFERENT_TEST_VALUE"

    assert benchmark.quality_fingerprint(first, [], expected) == (
        benchmark.quality_fingerprint(equivalent, [], expected)
    )
    assert benchmark.quality_fingerprint(first, [], expected) != (
        benchmark.quality_fingerprint(changed, [], expected)
    )
