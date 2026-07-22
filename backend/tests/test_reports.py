from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from docx import Document
from fastapi.testclient import TestClient
import fitz

from app.storage import store
from app.main import app
from app.core.models import ReviewMode, ReviewTask, RuleStatus
from app.reporting.docx_report import _STATUS_LABELS as DOCX_STATUS_LABELS
from app.reporting.reports import _STATUS_LABELS as PDF_STATUS_LABELS
from app.storage import artifacts
from app.reporting.reports import build_structured_report
from app.storage.artifacts import ArtifactStorage
from app.storage.store import SqliteTaskStore


client = TestClient(app)


def test_not_applicable_status_label_is_explicit_in_reports():
    assert PDF_STATUS_LABELS["not_applicable"] == "规则不适用"
    assert DOCX_STATUS_LABELS[RuleStatus.NOT_APPLICABLE] == "规则不适用"


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
    created = client.post("/api/v1/reviews/demos/case-01-baseline", json={})
    task_id = created.json()["taskId"]
    action = client.post(
        f"/api/v1/reviews/{task_id}/issues/RISK-001/actions",
        json={"status": "supplemented", "reason": "需补充核实风险提示情况。", "actorId": "test-operator"},
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


def test_generate_endpoint_produces_the_two_user_facing_reports(tmp_path, monkeypatch):
    task_id = _ready_demo(tmp_path, monkeypatch)

    task, payloads = _generate(task_id)

    expected_types = {"review_pdf", "follow_up_docx"}
    assert set(payloads) == expected_types
    assert task["requiredArtifacts"] == ["review_pdf", "follow_up_docx"]
    summaries = {item["type"]: item for item in task["artifacts"]}
    assert all(sha256(payloads[kind]).hexdigest() == summaries[kind]["sha256"] for kind in expected_types)
    assert summaries["follow_up_docx"]["filename"].endswith("-补问工作清单.docx")



def test_generated_documents_contain_review_evidence_and_page_fields(tmp_path, monkeypatch):
    task_id = _ready_demo(tmp_path, monkeypatch)

    task, payloads = _generate(task_id)

    docx = Document(BytesIO(payloads["follow_up_docx"]))
    assert round(docx.sections[0].page_width.cm, 1) == 21.0
    assert round(docx.sections[0].page_height.cm, 1) == 29.7
    docx_text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    assert "补问工作清单" in docx_text
    assert "RISK-001" in docx_text
    assert "多次转账风险提示" in docx_text
    assert "人工判断：已加入补问清单" in docx_text
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
    assert "已加入补问清单" in pdf_text
    assert "人工处理汇总" in pdf_text
    assert "需补充核实风险提示情况" in pdf_text
    assert pdf_text.index("人工处理汇总") < pdf_text.index("逐项审查与人工处置")
    assert f"共 {pdf.page_count} 页" in pdf[-1].get_text()
    assert task["status"] == "completed"
