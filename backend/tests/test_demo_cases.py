import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.storage import store
from app.data.rules import TEMPLATE_RULE_CATALOG
from app.data.demo_cases import DEMO_CASES, get_demo_case, load_demo_document
from app.main import app
from app.core.models import ManualDecision, ReviewResult, RuleStatus
from app.storage import artifacts
from app.storage.artifacts import ArtifactStorage
from app.review.extraction import TemplateDomainFailure, TemplateReviewOutcome
from app.storage.store import SqliteTaskStore
from app.core.template_models import CaseExtraction


client = TestClient(app)


EXPECTED_IDS = [
    "case-01-baseline",
    "case-02-line-breaks",
    "case-03-blank-answer",
    "case-04-long-answer",
    "case-05-table-and-symbols",
    "case-06-all-statuses-demo",
]


def test_demo_catalog_uses_five_chinese_named_fixtures():
    assert [case.id for case in DEMO_CASES] == EXPECTED_IDS
    assert [case.executionMode for case in DEMO_CASES] == ["mock", *("qwen" for _ in range(5))]
    assert all(case.display_name for case in DEMO_CASES)
    assert "五类结果" in DEMO_CASES[-1].display_name
    assert all(case.path.suffix.lower() == ".docx" and case.path.is_file() for case in DEMO_CASES)
    assert get_demo_case("sample-covered") is None
    assert get_demo_case("sample-missing") is None
    assert get_demo_case("sample-telecom") is None


def test_all_demo_docx_files_parse_into_non_empty_documents():
    documents = [asyncio.run(load_demo_document(case)) for case in DEMO_CASES]

    assert all(document.format == "DOCX" for document in documents)
    assert all(document.pageCount > 0 and document.text.strip() for document in documents)
    assert [document.name for document in documents] == [case.filename for case in DEMO_CASES]


def test_demo_api_lists_five_cases_and_rejects_old_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))

    response = client.get("/api/v1/demos")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["demos"]] == EXPECTED_IDS
    assert [item["executionMode"] for item in response.json()["demos"]] == ["mock", *("qwen" for _ in range(5))]
    assert all(item["name"] for item in response.json()["demos"])
    assert client.post("/api/v1/reviews/demos/sample-covered", json={}).status_code == 404


def test_case_01_uses_mock_results_without_calling_qwen(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))

    with patch("app.review.review.run_template_review", new=AsyncMock(side_effect=AssertionError("Qwen must not be called"))):
        created = client.post("/api/v1/reviews/demos/case-01-baseline", json={})

    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "mock"
    assert task["status"] == "completed"
    assert task["documentId"]
    assert task["documentVersionId"]
    assert [artifact["type"] for artifact in task["artifacts"]] == ["original"]
    assert task["requiredArtifacts"] == ["review_pdf", "follow_up_docx", "structured_json", "archive_manifest"]
    assert [result["ruleId"] for result in task["results"]] == [
        rule.ruleId for rule in TEMPLATE_RULE_CATALOG.rules
    ]
    assert {result["group"] for result in task["results"]}.issubset({
        "META", "PROC", "CASE", "PREV", "RISK", "CASH", "TIME", "PRIV",
        "LEAD", "MOTIVE", "CONTACT", "MONEY", "OFFLINE", "EXTRA", "EVID",
    })
    assert all("内部询问笔录模板" in result["source"] and "模拟结果" in result["source"] for result in task["results"])
    incomplete = [result for result in task["results"] if result["status"] == "incomplete"]
    assert len(incomplete) == 1
    assert incomplete[0]["severity"] == "high"
    assert incomplete[0]["evidenceAnchorIds"]

    action = client.post(
        f"/api/v1/reviews/{task['id']}/issues/RISK-001/actions",
        json={"status": "supplemented", "reason": incomplete[0]["suggestedQuestion"], "actorId": "test-operator"},
    )
    assert action.status_code == 200
    with patch("app.review.review.run_template_review", new=AsyncMock(side_effect=AssertionError("mock follow-up must not call Qwen"))):
        follow_up = client.post(
            f"/api/v1/reviews/{task['id']}/issues/RISK-001/follow-up-answer",
            json={
                "question": incomplete[0]["suggestedQuestion"],
                "answer": "转账前未收到银行或支付机构的风险提示。",
                "actorId": "test-operator",
            },
        )
    assert follow_up.status_code == 200
    updated = follow_up.json()
    assert updated["documentVersionId"] != task["documentVersionId"]
    refreshed = next(result for result in updated["results"] if result["ruleId"] == "RISK-001")
    assert refreshed["status"] == "covered"
    assert refreshed["manualDecision"]["status"] == "resolved"


def test_case_02_uses_qwen_review(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))
    document = asyncio.run(load_demo_document(DEMO_CASES[1]))
    fixture_results = [
        ReviewResult(
            ruleId="CASE-001",
            ruleName="报案原因与案件概述",
            category="CASE",
            group="CASE",
            status=RuleStatus.COVERED,
            missingFacts=[],
            evidence=document.pages[0].paragraphs[0].text,
            evidenceLocation={"page": 1, "paragraph": 1},
            evidenceLocations=[{"page": 1, "paragraph": 1}],
            reason="测试模型结果。",
            suggestedQuestion="",
            advisories=[],
            manualDecision=ManualDecision(),
            source="内部询问笔录模板 v1（Qwen 事实抽取，确定性规则校验）",
            severity="high",
        )
    ]
    outcome = TemplateReviewOutcome(
        extraction=CaseExtraction(),
        issues=[],
        results=fixture_results,
    )

    with patch("app.review.review.run_template_review", new=AsyncMock(return_value=outcome)) as review:
        created = client.post("/api/v1/reviews/demos/case-02-line-breaks", json={"mode": "local"})

    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "qwen"
    assert task["status"] == "completed"
    review.assert_awaited_once()


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

    with patch("app.review.review.run_template_review", new=AsyncMock(side_effect=failure)):
        created = client.post("/api/v1/reviews/demos/case-02-line-breaks", json={})

    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "failed"
    assert task["failedDomains"] == ["case_timeline"]
    assert task["domainErrors"] == {"case_timeline": "invalid_model_evidence"}
    assert "privacy.disclosure_reason" in task["domainErrorDetails"]["case_timeline"]
