import json
import base64
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
import fitz
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import pytest

from app.errors import AppError
from app.main import app
from app.data import DEMOS, RULES
from app.services import qwen
from app.services.analyzer import analyze_document


client = TestClient(app)


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_with_table_bytes() -> bytes:
    document = Document()
    document.add_paragraph("问：请说明转账情况。答：我通过手机银行转账。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "转账时间"
    table.cell(0, 1).text = "转账金额"
    table.cell(1, 0).text = "2026年7月15日10时30分"
    table.cell(1, 1).text = "5000元"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_with_image_bytes() -> bytes:
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    document = Document()
    document.add_paragraph("问：是否保留转账凭证？答：凭证截图附后。")
    document.add_picture(BytesIO(image))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _text_pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)


def _blank_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _mixed_pdf_bytes() -> bytes:
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Native interview text retained for evidence location.")
    page.insert_image(fitz.Rect(72, 100, 180, 208), stream=image)
    content = document.tobytes()
    document.close()
    return content


def _upload(filename: str, content: bytes):
    async def fixture_review(document):
        return analyze_document(document)

    with patch("app.services.review.review_with_qwen", side_effect=fixture_review):
        created = client.post(
            "/api/v1/reviews",
            data={"mode": "local"},
            files={"file": (filename, content, "application/octet-stream")},
        )
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "qwen"
    return task


def test_health_and_rules():
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["ruleCount"] == 7
    rules = client.get("/api/v1/rules")
    assert rules.status_code == 200
    payload = rules.json()["rules"]
    assert len(payload) == 7
    assert {rule["group"] for rule in payload} == {"三现", "四流"}
    assert all(rule["source"] == "working_rule" for rule in payload)
    assert all(rule["requiredFacts"] for rule in payload)

    schema = client.get("/api/openapi.json").json()
    task_statuses = schema["components"]["schemas"]["TaskStatus"]["enum"]
    assert task_statuses == ["uploading", "parsing", "recognizing", "checking", "validating", "completed", "failed"]
    review_response = schema["paths"]["/api/v1/reviews/{task_id}"]["get"]["responses"]["200"]
    assert review_response["content"]["application/json"]["schema"]["$ref"].endswith("/ReviewTask")


def test_demo_review_and_ignore_reason_validation():
    created = client.post("/api/v1/reviews/demos/sample-missing", json={"mode": "local"})
    assert created.status_code == 202
    task_id = created.json()["taskId"]
    task = client.get(f"/api/v1/reviews/{task_id}").json()
    assert task["status"] == "completed"
    assert len(task["results"]) == 7
    problem = next(item for item in task["results"] if item["status"] in {"missing", "incomplete"})
    invalid = client.patch(f"/api/v1/reviews/{task_id}/results/{problem['ruleId']}/decision", json={"status": "ignored", "reason": ""})
    assert invalid.status_code == 422
    saved = client.patch(f"/api/v1/reviews/{task_id}/results/{problem['ruleId']}/decision", json={"status": "ignored", "reason": "已由其他材料核实"})
    assert saved.status_code == 200
    assert saved.json()["result"]["manualDecision"]["status"] == "ignored"


def test_three_present_four_flows_results_locate_source_paragraphs():
    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "local"})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    locations = {item["ruleId"]: item["evidenceLocation"] for item in task["results"]}
    assert locations["PRESENT-003"] == {"page": 1, "paragraph": 5}
    assert locations["FLOW-003"] == {"page": 1, "paragraph": 6}
    assert locations["FLOW-004"] == {"page": 1, "paragraph": 4}


def test_docx_upload_completes_with_all_four_state_results():
    task = _upload("脱敏笔录.docx", _docx_bytes([
        "问：请说明案发时间、地点和经过。答：2026年7月15日，我在测试路附近接到陌生电话。",
        "问：对方使用什么方式联系？答：通过电话联系，让我点击一个链接并转账。",
        "问：损失金额和支付方式？答：通过银行卡转账5000元，交易流水号为TEST-001。",
        "问：是否保存聊天记录和转账凭证？答：相关截图已经保存。",
    ]))
    assert task["status"] == "completed"
    assert task["document"]["format"] == "DOCX"
    assert len(task["results"]) == 7
    assert {item["status"] for item in task["results"]} <= {"covered", "missing", "incomplete", "not_applicable"}


def test_text_pdf_upload_completes():
    text = (
        "Interview record for anonymized demo. The incident occurred on July 15 at Test Road. "
        "The caller requested a bank transfer. The transaction reference is TEST-002 and screenshots were retained."
    )
    task = _upload("anonymized-record.pdf", _text_pdf_bytes(text))
    assert task["status"] == "completed"
    assert task["document"]["format"] == "PDF"
    assert len(task["results"]) == 7


def test_scanned_pdf_uses_multimodal_transcription(monkeypatch):
    transcribe = AsyncMock(return_value={
        "paragraphs": ["问：转账金额是多少？答：5000元。"],
        "confidence": 0.96,
    })
    monkeypatch.setattr("app.services.parser.transcribe_image", transcribe, raising=False)

    task = _upload("scanned.pdf", _blank_pdf_bytes())

    assert task["status"] == "completed"
    assert transcribe.await_count == 1
    paragraph = task["document"]["pages"][0]["paragraphs"][0]
    assert paragraph == {
        "text": "问：转账金额是多少？答：5000元。",
        "sourceType": "vision",
        "confidence": 0.96,
    }


def test_mixed_pdf_keeps_native_text_and_transcribes_embedded_images(monkeypatch):
    transcribe = AsyncMock(return_value={
        "paragraphs": ["图片凭证流水号：MIXED-001"],
        "confidence": 0.9,
    })
    monkeypatch.setattr("app.services.parser.transcribe_image", transcribe)

    task = _upload("mixed-record.pdf", _mixed_pdf_bytes())

    assert task["status"] == "completed"
    blocks = task["document"]["pages"][0]["paragraphs"]
    assert {block["sourceType"] for block in blocks} == {"native_text", "vision"}
    assert any("MIXED-001" in block["text"] for block in blocks)


def test_docx_tables_are_preserved_as_structured_blocks():
    task = _upload("table-record.docx", _docx_with_table_bytes())

    assert task["status"] == "completed"
    blocks = [paragraph for page in task["document"]["pages"] for paragraph in page["paragraphs"]]
    assert any(block["sourceType"] == "table" and "2026年7月15日10时30分" in block["text"] for block in blocks)


def test_docx_embedded_images_use_multimodal_transcription(monkeypatch):
    transcribe = AsyncMock(return_value={
        "paragraphs": ["交易流水号：TEST-VISION-001"],
        "confidence": 0.91,
    })
    monkeypatch.setattr("app.services.parser.transcribe_image", transcribe, raising=False)

    task = _upload("image-record.docx", _docx_with_image_bytes())

    assert task["status"] == "completed"
    assert transcribe.await_count == 1
    blocks = [paragraph for page in task["document"]["pages"] for paragraph in page["paragraphs"]]
    assert any(block["sourceType"] == "vision" and "TEST-VISION-001" in block["text"] for block in blocks)


def test_legacy_doc_is_rejected_with_conversion_guidance():
    task = _upload("legacy-record.doc", b"legacy-word-content")

    assert task["status"] == "failed"
    assert task["errorCode"] == "unsupported_legacy_word"
    assert "DOCX" in task["errorMessage"]


def test_long_docx_is_accepted_without_page_limit():
    paragraphs = [f"第 {index + 1} 部分。" + "脱敏测试内容" * 300 for index in range(11)]
    task = _upload("long-record.docx", _docx_bytes(paragraphs))
    assert task["status"] == "completed"
    assert task["document"]["pageCount"] >= 11
    assert len(task["results"]) == 7


def test_empty_and_corrupt_files_fail_cleanly():
    empty = _upload("empty.docx", b"")
    assert empty["status"] == "failed"
    assert empty["errorCode"] == "empty_document"
    assert empty["results"] == []

    corrupt = _upload("corrupt.pdf", b"not a pdf")
    assert corrupt["status"] == "failed"
    assert corrupt["errorCode"] == "parse_failed"
    assert corrupt["results"] == []


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (AppError("model_unreachable", "模型服务不可达。", 503), "model_unreachable"),
        (RuntimeError("unexpected model adapter failure"), "review_service_failed"),
    ],
)
def test_qwen_failures_fail_the_whole_demo_task(monkeypatch, failure, expected_code):
    monkeypatch.setattr("app.services.review.review_with_qwen", AsyncMock(side_effect=failure))
    created = client.post("/api/v1/reviews/demos/sample-missing", json={"mode": "qwen"})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "failed"
    assert task["errorCode"] == expected_code
    assert task["results"] == []


def test_supplementary_hints_cannot_be_reported_as_hard_missing_facts():
    demo = DEMOS[0]
    first_rule = RULES[0]
    supplementary = first_rule["referenceHints"][0]["label"]
    assert supplementary not in {fact["label"] for fact in first_rule["requiredFacts"]}

    payload = {"results": []}
    for index, rule in enumerate(RULES):
        missing = supplementary if index == 0 else rule["requiredFacts"][0]["label"]
        payload["results"].append({
            "ruleId": rule["id"],
            "status": "incomplete",
            "missingFacts": [missing],
            "evidence": demo.pages[0].paragraphs[0].text,
            "evidenceLocation": {"page": 1, "paragraph": 1},
            "reason": "已涉及相关事项，但信息尚不完整。",
            "suggestedQuestion": rule["suggestedQuestion"],
            "advisories": [],
        })

    with pytest.raises(AppError) as error:
        qwen._validate(payload, demo)
    assert error.value.code == "invalid_model_results"


def test_supplementary_advisories_are_kept_separate_from_status():
    demo = DEMOS[0]
    payload = {"results": []}
    for rule in RULES:
        payload["results"].append({
            "ruleId": rule["id"],
            "status": "covered",
            "missingFacts": [],
            "evidence": demo.pages[0].paragraphs[0].text,
            "evidenceLocation": {"page": 1, "paragraph": 1},
            "reason": "强制字段已有可定位的问答记录。",
            "suggestedQuestion": "",
            "advisories": ["可进一步核对关联平台账号。"],
        })

    results = qwen._validate(payload, demo)
    assert all(result.status.value == "covered" for result in results)
    assert results[0].advisories == ["可进一步核对关联平台账号。"]


def _structured_review_output(demo, *, invalid_location: bool = False) -> dict:
    output = {}
    for rule in RULES:
        fact_coverage = {fact["label"]: "covered" for fact in rule["requiredFacts"]}
        fact_coverage[rule["requiredFacts"][0]["label"]] = "missing"
        output[rule["id"]] = {
            "factCoverage": fact_coverage,
            "evidenceLocation": {"page": 99 if invalid_location else 1, "paragraph": 1},
            "reason": "演示模型返回了可定位的不完整结果。",
            "suggestedQuestion": rule["suggestedQuestion"],
            "advisories": [],
        }
    return output


def test_strict_review_schema_uses_only_supported_provider_keywords():
    serialized = json.dumps(qwen.structured_review_schema(), ensure_ascii=False)
    assert "uniqueItems" not in serialized


def test_qwen_openai_compatible_success_path(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        request_body = json.loads(request.content)
        assert request_body["model"] == "test-model"
        assert len(request_body["messages"]) == 2
        assert "逐字复制当前规则 requiredFacts" in request_body["messages"][1]["content"]
        response_format = request_body["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        schema = response_format["json_schema"]["schema"]
        assert schema["required"] == [rule["id"] for rule in RULES]
        assert schema["additionalProperties"] is False
        content = json.dumps(_structured_review_output(demo), ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def client_factory(*_args, **kwargs):
        assert kwargs["timeout"].read >= 120
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(task["results"]) == len(RULES)
    assert all("Qwen 辅助判断" in item["source"] for item in task["results"])
    assert all(item["evidence"] == demo.pages[0].paragraphs[0].text for item in task["results"])


def test_qwen_retries_once_with_validation_feedback(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        output = _structured_review_output(demo, invalid_location=len(requests) == 1)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 2
    assert "evidenceLocation" in requests[1]["messages"][-1]["content"]
    assert "PRESENT-001" in requests[1]["messages"][-1]["content"]


def test_qwen_correction_lists_allowed_fact_coverage_keys(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        output = _structured_review_output(demo)
        if len(requests) == 1:
            output["PRESENT-001"]["factCoverage"][RULES[0]["referenceHints"][0]["label"]] = "missing"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    feedback = requests[1]["messages"][-1]["content"]
    assert "factCoverage 只允许以下键" in feedback
    assert all(fact["label"] in feedback for fact in RULES[0]["requiredFacts"])


def test_qwen_fails_without_partial_results_after_two_invalid_responses(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        output = _structured_review_output(demo, invalid_location=True)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert request_count == 2
    assert task["status"] == "failed"
    assert task["errorCode"] == "insufficient_evidence"
    assert task["results"] == []


def test_qwen_falls_back_to_function_calling_when_json_schema_is_unsupported(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        if len(requests) == 1:
            return httpx.Response(400, json={"error": {"message": "response_format json_schema is not supported"}})
        assert request_body["tool_choice"]["function"]["name"] == qwen.TOOL_NAME
        assert request_body["tools"][0]["function"]["parameters"]["required"] == [rule["id"] for rule in RULES]
        arguments = json.dumps(_structured_review_output(demo), ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{
            "id": "call-1",
            "type": "function",
            "function": {"name": qwen.TOOL_NAME, "arguments": arguments},
        }]}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 2


def test_qwen_retries_transient_http_failure_with_json_schema(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = next(item for item in DEMOS if item.id == "sample-telecom")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        assert request_body["response_format"]["type"] == "json_schema"
        content = json.dumps(_structured_review_output(demo), ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(qwen.asyncio, "sleep", AsyncMock())

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 2


def test_qwen_does_not_retry_authentication_failure(monkeypatch):
    real_async_client = httpx.AsyncClient
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(401, json={"error": {"message": "invalid token"}})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/sample-telecom", json={"mode": "qwen"})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert request_count == 1
    assert task["status"] == "failed"
    assert task["errorCode"] == "model_auth_failed"
    assert task["results"] == []
