import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import store
from app.demo_cases import DEMO_CASES, get_demo_case, load_demo_document
from app.main import app
from app.models import ManualDecision, ReviewResult, RuleStatus
from app.store import SqliteTaskStore


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

    with patch("app.services.review.review_with_qwen", new=AsyncMock(side_effect=AssertionError("Qwen must not be called"))):
        created = client.post("/api/v1/reviews/demos/case-01-basic-complete", json={})

    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "mock"
    assert task["status"] == "completed"
    assert len(task["results"]) == 7
    assert all("模拟结果" in result["source"] for result in task["results"])
    incomplete = [result for result in task["results"] if result["status"] == "incomplete"]
    assert [(result["ruleId"], result["missingFacts"]) for result in incomplete] == [
        ("PRESENT-002", ["提取或查验情况"]),
    ]


def test_case_02_uses_qwen_review(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    document = asyncio.run(load_demo_document(DEMO_CASES[1]))
    fixture_results = [
        ReviewResult(
            ruleId="PRESENT-001",
            ruleName="案发现场",
            category="三现",
            group="三现",
            status=RuleStatus.COVERED,
            missingFacts=[],
            evidence=document.pages[0].paragraphs[0].text,
            evidenceLocation={"page": 1, "paragraph": 1},
            evidenceLocations=[{"page": 1, "paragraph": 1}],
            reason="测试模型结果。",
            suggestedQuestion="",
            advisories=[],
            manualDecision=ManualDecision(),
            source="三现四流工作规则（Qwen 辅助判断，结果需人工复核）",
        )
    ]

    with patch("app.services.review.review_with_qwen", new=AsyncMock(return_value=fixture_results)) as review:
        created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={"mode": "local"})

    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "qwen"
    assert task["status"] == "completed"
    review.assert_awaited_once()
