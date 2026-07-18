from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from docx import Document
from fastapi.testclient import TestClient
import fitz

from app.storage import store
from app.main import app
from app.core.models import ReviewMode, ReviewTask
from app.storage import artifacts
from app.reporting.reports import build_structured_report
from app.storage.artifacts import ArtifactStorage
from app.storage.store import SqliteTaskStore


client = TestClient(app)


def test_structured_report_exports_only_current_run_facts_with_provenance():
    task = ReviewTask(
        mode=ReviewMode.QWEN,
        documentVersionId="version-current",
        reviewRunId="run-current",
    )
    snapshot = {
        "events": [],
        "runs": [
            {"id": "run-old", "document_version_id": "version-old"},
            {"id": "run-current", "document_version_id": "version-current"},
        ],
        "facts": [
            {"run_id": "run-old", "path": "case.report_reason", "payload": {"value": "旧轮次"}, "created_at": "old"},
            {"run_id": "run-current", "path": "case.report_reason", "payload": {"value": "当前轮次"}, "created_at": "new"},
        ],
    }

    report = build_structured_report(task, snapshot)

    assert report["facts"] == [{
        "runId": "run-current",
        "documentVersionId": "version-current",
        "path": "case.report_reason",
        "payload": {"value": "当前轮次"},
        "createdAt": "new",
    }]


def _ready_demo(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))
    created = client.post("/api/v1/reviews/demos/case-01-basic-complete", json={})
    task_id = created.json()["taskId"]
    action = client.post(
        f"/api/v1/reviews/{task_id}/issues/RISK-001/actions",
        json={"status": "resolved", "reason": "已记录脱敏补问答案。", "actorId": "test-operator"},
    )
    assert action.status_code == 200
    return task_id


def _generate(task_id: str) -> tuple[dict, dict[str, bytes]]:
    response = client.post(f"/api/v1/reviews/{task_id}/artifacts/generate")
    assert response.status_code == 200
    task = response.json()
    payloads = {
        artifact["type"]: client.get(
            f"/api/v1/reviews/{task_id}/artifacts/{artifact['id']}"
        ).content
        for artifact in task["artifacts"]
        if artifact["type"] != "original"
    }
    return task, payloads


def test_generate_endpoint_produces_hashed_report_bundle(tmp_path, monkeypatch):
    task_id = _ready_demo(tmp_path, monkeypatch)

    task, payloads = _generate(task_id)

    expected_types = {"review_pdf", "follow_up_docx", "structured_json", "archive_manifest"}
    assert set(payloads) == expected_types
    assert task["requiredArtifacts"] == [
        "review_pdf", "follow_up_docx", "structured_json", "archive_manifest",
    ]
    summaries = {item["type"]: item for item in task["artifacts"]}
    assert all(sha256(payloads[kind]).hexdigest() == summaries[kind]["sha256"] for kind in expected_types)

    manifest = json.loads(payloads["archive_manifest"])
    assert manifest["taskId"] == task_id
    assert manifest["documentVersionId"] == task["documentVersionId"]
    assert manifest["versions"]["rule"]
    assert manifest["versions"]["model"] == "mock-review-v1"
    assert manifest["versions"]["parser"]
    manifest_entries = {item["type"]: item for item in manifest["artifacts"]}
    for kind in {"original", "review_pdf", "follow_up_docx", "structured_json"}:
        assert manifest_entries[kind]["sha256"] == summaries[kind]["sha256"]


def test_generated_documents_contain_review_evidence_and_page_fields(tmp_path, monkeypatch):
    task_id = _ready_demo(tmp_path, monkeypatch)

    task, payloads = _generate(task_id)

    structured = json.loads(payloads["structured_json"])
    assert structured["task"]["id"] == task_id
    assert len(structured["results"]) == 34
    risk = next(item for item in structured["results"] if item["ruleId"] == "RISK-001")
    assert risk["manualDecision"]["status"] == "resolved"
    assert risk["evidenceAnchorIds"]
    assert any(event["eventType"] == "resolved" for event in structured["manualEvents"])

    docx = Document(BytesIO(payloads["follow_up_docx"]))
    assert round(docx.sections[0].page_width.cm, 1) == 21.0
    assert round(docx.sections[0].page_height.cm, 1) == 29.7
    docx_text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    assert "补问工作清单" in docx_text
    assert "RISK-001" in docx_text
    assert "多次转账风险提示" in docx_text
    assert "人工处置：已解决" in docx_text
    assert "风险等级：高" in docx_text
    with ZipFile(BytesIO(payloads["follow_up_docx"])) as package:
        footer_xml = package.read("word/footer1.xml").decode("utf-8")
    assert "PAGE" in footer_xml and "NUMPAGES" in footer_xml

    pdf = fitz.open(stream=payloads["review_pdf"], filetype="pdf")
    assert pdf.page_count >= 2
    pdf_text = "\n".join(page.get_text() for page in pdf)
    assert "询问笔录审查复核报告" in pdf_text
    assert "RISK-001" in pdf_text
    assert "快速模拟" in pdf_text
    assert "已解决" in pdf_text
    assert f"共 {pdf.page_count} 页" in pdf[-1].get_text()
    assert task["status"] == "completed"
