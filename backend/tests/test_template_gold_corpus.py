import asyncio
from pathlib import Path
import re
from types import SimpleNamespace

from app.data.rules import TEMPLATE_RULE_CATALOG
from app.core.models import RuleStatus
from app.core.template_models import CaseExtraction, ExtractedEntity
from scripts import verify_template_quality
from scripts.generate_template_gold_cases import (
    PROHIBITED_SENSITIVE_PATTERNS,
    _extract_text,
    build_gold_corpus,
    scan_prohibited_sensitive_shapes,
)
from scripts.verify_template_quality import evaluate_offline_quality


def test_gold_corpus_has_twelve_pairs_and_four_mutations_per_rule(tmp_path):
    corpus = build_gold_corpus(tmp_path)

    assert len(corpus["cases"]) >= 12
    assert all((tmp_path / case["docx"]).exists() for case in corpus["cases"])
    assert all((tmp_path / case["pdf"]).exists() for case in corpus["cases"])
    mutations = {(item["ruleId"], item["kind"]) for item in corpus["mutations"]}
    assert mutations == {
        (rule.ruleId, kind)
        for rule in TEMPLATE_RULE_CATALOG.rules
        for kind in ("covered", "missing", "incomplete", "inconsistent")
    }


def test_naturalistic_gold_cases_are_hand_authored_document_mutations(tmp_path):
    corpus = build_gold_corpus(tmp_path)

    assert corpus["naturalOracleSource"] == "hand-authored-police-review-v1"
    assert {case["mutationKind"] for case in corpus["naturalCases"]} == {
        "complete", "missing", "unclear", "inconsistent",
    }
    assert all(case["expectedRuleStatuses"] for case in corpus["naturalCases"])
    for case in corpus["naturalCases"]:
        for key in ("docx", "pdf"):
            path = tmp_path / case[key]
            assert path.exists()
            text = _extract_text(path)
            assert "VALUE_TEST_" not in text
            assert "ENTITY_TEST_" not in text
            assert not re.search(r"\b[a-z_]+\.[a-z_]+\b", text)


def test_live_gate_runs_naturalistic_cases_through_docx_and_pdf(tmp_path, monkeypatch):
    corpus = build_gold_corpus(tmp_path)
    corpus["cases"] = []
    corpus["naturalCases"] = corpus["naturalCases"][:1]
    case = corpus["naturalCases"][0]
    observed_names: list[str] = []
    observed_concurrency: list[int] = []

    async def parse_document(name, _content):
        observed_names.append(name)
        return object()

    async def run_review(*_args, **kwargs):
        observed_concurrency.append(kwargs["max_concurrency"])
        extraction = verify_template_quality._natural_expected_extraction(case)
        results = [
            SimpleNamespace(
                ruleId=rule_id,
                status=RuleStatus(status),
                missingFacts=[],
                evidenceAnchorIds=[] if status == "missing" else ["anchor-test"],
            )
            for rule_id, status in case["expectedRuleStatuses"].items()
        ]
        return SimpleNamespace(extraction=extraction, issues=[], results=results)

    monkeypatch.setattr(verify_template_quality, "QWEN_MODEL", verify_template_quality.EXPECTED_MODEL)
    monkeypatch.setattr(verify_template_quality, "parse_document", parse_document)
    monkeypatch.setattr(verify_template_quality, "run_template_review", run_review)

    report = asyncio.run(verify_template_quality._evaluate_live(
        corpus,
        tmp_path,
        runs=1,
        max_concurrency=7,
    ))

    assert sorted(Path(name).suffix for name in observed_names) == [".docx", ".pdf"]
    assert observed_concurrency == [7, 7]
    assert report["contractCaseCount"] == 0
    assert report["naturalDocumentCount"] == 2
    assert all(value == 100.0 for value in report["metrics"].values())


def test_focused_natural_accuracy_accepts_unverifiable_value_wording():
    expected = CaseExtraction(facts={
        "risk.payment_warning_content": verify_template_quality._fact(None, "unclear"),
    })
    actual = expected.model_copy(deep=True)
    actual.facts["risk.payment_warning_content"].value = "无法确认具体提示内容"

    passed, total, mismatches = verify_template_quality._focused_accuracy(actual, expected)

    assert (passed, total, mismatches) == (1, 1, [])


def test_gold_corpus_and_demo_documents_have_no_sensitive_shapes(tmp_path):
    corpus = build_gold_corpus(tmp_path)
    scanned = [
        tmp_path / item[key]
        for item in [*corpus["cases"], *corpus["naturalCases"]]
        for key in ("docx", "pdf")
    ]

    assert set(PROHIBITED_SENSITIVE_PATTERNS) == {
        "identity_number", "phone_number", "bank_card", "url", "public_ip",
    }
    assert scan_prohibited_sensitive_shapes(scanned) == []


def test_offline_quality_gate_reports_one_hundred_percent(tmp_path):
    corpus = build_gold_corpus(tmp_path)

    report = evaluate_offline_quality(corpus, tmp_path)

    assert report["caseCount"] >= 12
    assert report["contractDocumentCount"] == 24
    assert report["naturalDocumentCount"] == 8
    assert report["ruleCount"] == len(TEMPLATE_RULE_CATALOG.rules)
    assert report["sensitiveFindings"] == []
    assert report["metrics"]
    assert all(value == 100.0 for value in report["metrics"].values())


def test_committed_gold_oracle_can_be_regenerated_without_drift(tmp_path):
    generated = build_gold_corpus(tmp_path)
    committed = Path(__file__).parent / "gold" / "template_cases.json"

    assert committed.exists()
    assert committed.read_text(encoding="utf-8").strip() == generated["oracleJson"].strip()


def test_live_stability_detects_entity_drift_when_rule_statuses_match(tmp_path, monkeypatch):
    corpus = build_gold_corpus(tmp_path)
    expected = corpus["cases"][0]["expectedRuleStatuses"]
    calls = 0
    observed_concurrency: list[int] = []

    async def parse_document(*_args):
        return object()

    async def run_review(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        observed_concurrency.append(_kwargs["max_concurrency"])
        extraction = CaseExtraction()
        if calls == 2:
            extraction.entities["transfers"] = [
                ExtractedEntity(id="transfer-extra", entityType="transfers", fields={}),
            ]
        results = [
            SimpleNamespace(
                ruleId=rule_id,
                status=RuleStatus(status),
                missingFacts=[],
                evidenceAnchorIds=["anchor-test"],
            )
            for rule_id, status in expected.items()
        ]
        return SimpleNamespace(extraction=extraction, issues=[], results=results)

    monkeypatch.setattr(verify_template_quality, "QWEN_MODEL", verify_template_quality.EXPECTED_MODEL)
    monkeypatch.setattr(verify_template_quality, "parse_document", parse_document)
    monkeypatch.setattr(verify_template_quality, "run_template_review", run_review, raising=False)

    report = asyncio.run(verify_template_quality._evaluate_live(
        corpus,
        tmp_path,
        runs=2,
        case_limit=1,
        max_concurrency=7,
    ))

    assert report["metrics"]["semanticStability"] == 0.0
    assert report["metrics"]["requiredRecall"] < 100.0
    assert report["semanticDriftPaths"] == ["entities.transfers"]
    assert observed_concurrency == [7, 7]


def test_gold_semantic_fingerprint_ignores_anchor_choice_but_detects_value_change():
    expected = CaseExtraction(facts={
        "case.report_reason": verify_template_quality._fact("VALUE_TEST_CASE", anchor="expected"),
    })
    first = expected.model_copy(deep=True)
    first.facts["case.report_reason"].evidenceAnchorIds = ["question-anchor"]
    second = expected.model_copy(deep=True)
    second.facts["case.report_reason"].evidenceAnchorIds = ["answer-anchor"]
    changed = second.model_copy(deep=True)
    changed.facts["case.report_reason"].value = "DIFFERENT_TEST_VALUE"

    first_fingerprint = verify_template_quality._gold_semantic_fingerprint(first, [], expected)
    second_fingerprint = verify_template_quality._gold_semantic_fingerprint(second, [], expected)
    changed_fingerprint = verify_template_quality._gold_semantic_fingerprint(changed, [], expected)

    assert first_fingerprint == second_fingerprint
    assert first_fingerprint != changed_fingerprint


def test_gold_semantic_fingerprint_canonicalizes_only_oracle_equivalent_values():
    expected = CaseExtraction(facts={
        "case.report_reason": verify_template_quality._fact("VALUE_TEST_CASE", anchor="expected"),
    })
    exact = expected.model_copy(deep=True)
    wrapped = expected.model_copy(deep=True)
    wrapped.facts["case.report_reason"].value = "笔录记录为 VALUE_TEST_CASE。"
    changed = expected.model_copy(deep=True)
    changed.facts["case.report_reason"].value = "DIFFERENT_TEST_VALUE"

    assert verify_template_quality._gold_semantic_fingerprint(exact, [], expected) == (
        verify_template_quality._gold_semantic_fingerprint(wrapped, [], expected)
    )
    assert verify_template_quality._gold_semantic_fingerprint(exact, [], expected) != (
        verify_template_quality._gold_semantic_fingerprint(changed, [], expected)
    )


def test_gold_semantic_fingerprint_canonicalizes_equivalent_entity_fields():
    expected = CaseExtraction(entities={
        "transfers": [ExtractedEntity(
            id="transfer-1",
            entityType="transfers",
            fields={"payment_method": verify_template_quality._fact("ENTITY_TEST_METHOD")},
        )],
    })
    exact = expected.model_copy(deep=True)
    wrapped = expected.model_copy(deep=True)
    wrapped.entities["transfers"][0].fields["payment_method"].value = (
        "方式记录为 ENTITY_TEST_METHOD。"
    )
    changed = expected.model_copy(deep=True)
    changed.entities["transfers"][0].fields["payment_method"].value = "DIFFERENT_TEST_METHOD"

    assert verify_template_quality._gold_semantic_fingerprint(exact, [], expected) == (
        verify_template_quality._gold_semantic_fingerprint(wrapped, [], expected)
    )
    assert verify_template_quality._gold_semantic_fingerprint(exact, [], expected) != (
        verify_template_quality._gold_semantic_fingerprint(changed, [], expected)
    )


def test_gold_value_matching_accepts_context_wrapped_tokens_and_numeric_units():
    assert verify_template_quality._values_equal(
        "该字段明确记录为 VALUE_TEST_CONTACT_INITIAL_CHANNEL。",
        "VALUE_TEST_CONTACT_INITIAL_CHANNEL",
    )
    assert verify_template_quality._values_equal("共 2 次", 2)


def test_gold_accuracy_accepts_reworded_cross_domain_semantic_aliases():
    from scripts.generate_template_gold_cases import _case_extraction

    expected = _case_extraction(("contact_channels",))
    actual = expected.model_copy(deep=True)
    actual.facts["case.channel_changes"].value = "已逐项记录两次渠道切换"
    actual.facts["case.contact_method"].value = "通过脱敏测试渠道建立联系"

    passed, total, mismatches = verify_template_quality._gold_accuracy(actual, expected)

    assert passed == total
    assert mismatches == []
