import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import store
from app.data import TEMPLATE_RULE_CATALOG
from app.demo_cases import DEMO_CASES, get_demo_case, load_demo_document
from app.main import app
from app.models import ManualDecision, ReviewResult, RuleStatus
from app.services import artifacts
from app.services.artifacts import ArtifactStorage
from app.services.template_extraction import TemplateReviewOutcome
from app.store import SqliteTaskStore
from app.template_models import CaseExtraction


client = TestClient(app)


EXPECTED_IDS = [
    "case-01-basic-complete",
    "case-02-explicit-omissions",
    "case-03-app-rebate",
    "case-04-fake-prosecutor-atm",
    "case-05-investment-crypto",
    "case-06-fake-service-remote-control",
    "case-07-cash-gold-delivery",
]


def test_demo_catalog_uses_only_the_seven_docx_cases():
    assert [case.id for case in DEMO_CASES] == EXPECTED_IDS
    assert [case.executionMode for case in DEMO_CASES] == ["mock", *("qwen" for _ in range(6))]
    assert all(case.path.suffix.lower() == ".docx" and case.path.is_file() for case in DEMO_CASES)
    assert get_demo_case("sample-covered") is None
    assert get_demo_case("sample-missing") is None
    assert get_demo_case("sample-telecom") is None


def test_all_demo_docx_files_parse_into_non_empty_documents():
    documents = [asyncio.run(load_demo_document(case)) for case in DEMO_CASES]

    assert all(document.format == "DOCX" for document in documents)
    assert all(document.pageCount > 0 and document.text.strip() for document in documents)
    assert [document.name for document in documents] == [case.filename for case in DEMO_CASES]


def test_demo_api_lists_seven_cases_and_rejects_old_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))

    response = client.get("/api/v1/demos")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["demos"]] == EXPECTED_IDS
    assert [item["executionMode"] for item in response.json()["demos"]] == ["mock", *("qwen" for _ in range(6))]
    assert client.post("/api/v1/reviews/demos/sample-covered", json={}).status_code == 404


def test_case_01_uses_mock_results_without_calling_qwen(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))

    with patch("app.services.review.run_template_review", new=AsyncMock(side_effect=AssertionError("Qwen must not be called"))):
        created = client.post("/api/v1/reviews/demos/case-01-basic-complete", json={})

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
    with patch("app.services.review.run_template_review", new=AsyncMock(side_effect=AssertionError("mock follow-up must not call Qwen"))):
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

    with patch("app.services.review.run_template_review", new=AsyncMock(return_value=outcome)) as review:
        created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={"mode": "local"})

    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "qwen"
    assert task["status"] == "completed"
    review.assert_awaited_once()
