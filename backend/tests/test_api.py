import asyncio
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
from app.data import RULES, TEMPLATE_RULES
from app.demo_cases import DEMO_CASES, load_demo_document
from app.services import qwen
from app.services.analyzer import analyze_document
from app import store
from app.store import SqliteTaskStore


client = TestClient(app)


def _demo_document(index: int = 1):
    return asyncio.run(load_demo_document(DEMO_CASES[index]))


@pytest.fixture(autouse=True)
def isolated_review_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))


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
    async def fixture_review(document, group_timings=None):
        if group_timings is not None:
            group_timings.update({"三现": 12, "四流": 18})
        return analyze_document(document)

    with patch("app.services.review.review_template_document", side_effect=fixture_review):
        created = client.post(
            "/api/v1/reviews",
            data={"mode": "local"},
            files={"file": (filename, content, "application/octet-stream")},
        )
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["mode"] == "qwen"
    return task


def test_upload_records_stage_and_group_timings():
    task = _upload("timed.docx", _docx_bytes(["问：案发经过？答：脱敏测试内容。"]))

    assert task["timings"]["parseMs"] >= 0
    assert task["timings"]["modelReviewMs"] >= 0
    assert task["timings"]["modelGroupsMs"] == {"三现": 12, "四流": 18}
    assert task["timings"]["totalMs"] >= task["timings"]["modelReviewMs"]


def test_health_and_rules():
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["ruleCount"] == len(TEMPLATE_RULES)
    rules = client.get("/api/v1/rules")
    assert rules.status_code == 200
    payload = rules.json()["rules"]
    assert len(payload) == len(TEMPLATE_RULES)
    assert {rule["group"] for rule in payload} == {rule.group for rule in TEMPLATE_RULES}
    assert all(rule["source"].startswith("内部询问笔录模板 v") for rule in payload)
    assert all(rule["requiredFacts"] for rule in payload)

    schema = client.get("/api/openapi.json").json()
    task_statuses = schema["components"]["schemas"]["TaskStatus"]["enum"]
    assert task_statuses == ["uploading", "parsing", "recognizing", "checking", "validating", "completed", "failed"]
    review_response = schema["paths"]["/api/v1/reviews/{task_id}"]["get"]["responses"]["200"]
    assert review_response["content"]["application/json"]["schema"]["$ref"].endswith("/ReviewTask")


def test_demo_review_decisions_complete_and_report():
    created = client.post("/api/v1/reviews/demos/case-01-basic-complete", json={})
    assert created.status_code == 202
    task_id = created.json()["taskId"]
    task = client.get(f"/api/v1/reviews/{task_id}").json()
    assert task["status"] == "completed"
    assert len(task["results"]) == 7
    blocked = client.post(f"/api/v1/reviews/{task_id}/complete")
    assert blocked.status_code == 409

    actionable = [item for item in task["results"] if item["status"] in {"missing", "incomplete"}]
    for index, item in enumerate(actionable):
        status = ["confirmed", "supplemented", "ignored"][index % 3]
        saved = client.patch(
            f"/api/v1/reviews/{task_id}/results/{item['ruleId']}/decision",
            json={"status": status, "reason": ""},
        )
        assert saved.status_code == 200

    completed = client.post(f"/api/v1/reviews/{task_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["reviewStatus"] == "archived"
    assert completed.json()["archivedAt"]

    follow_ups = client.get(f"/api/v1/reviews/{task_id}/follow-ups")
    assert follow_ups.status_code == 200
    assert all(item["manualDecision"]["status"] == "supplemented" for item in follow_ups.json()["items"])

    report = client.get(f"/api/v1/reviews/{task_id}/report-data")
    assert report.status_code == 200
    assert report.json()["reviewStatus"] == "archived"
    assert report.json()["victimProfile"] == task["victimProfile"]
    assert len(report.json()["results"]) == 7

    history = client.get("/api/v1/reviews")
    assert history.status_code == 200
    assert any(item["id"] == task_id and item["reviewStatus"] == "archived" for item in history.json()["reviews"])


def test_three_present_four_flows_results_locate_source_paragraphs():
    created = client.post("/api/v1/reviews/demos/case-01-basic-complete", json={})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    for item in task["results"]:
        location = item["evidenceLocation"]
        assert location is not None
        page = task["document"]["pages"][location["page"] - 1]
        assert 1 <= location["paragraph"] <= len(page["paragraphs"])


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
    assert paragraph["text"] == "问：转账金额是多少？答：5000元。"
    assert paragraph["sourceType"] == "vision"
    assert paragraph["confidence"] == 0.96
    assert paragraph["id"]
    assert paragraph["charStart"] == 0
    assert paragraph["charEnd"] == len(paragraph["text"])
    assert paragraph["bbox"] is None


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
    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "failed"
    assert task["errorCode"] == expected_code
    assert task["results"] == []


def test_supplementary_hints_cannot_be_reported_as_hard_missing_facts():
    demo = _demo_document(0)
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
    demo = _demo_document(0)
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


def _request_rule_ids(request_body: dict) -> list[str]:
    if "response_format" in request_body:
        return request_body["response_format"]["json_schema"]["schema"]["required"]
    return request_body["tools"][0]["function"]["parameters"]["required"]


def _structured_review_output(
    demo,
    *,
    invalid_location: bool = False,
    rule_ids: list[str] | None = None,
) -> dict:
    output = {}
    for rule in RULES:
        if rule_ids is not None and rule["id"] not in rule_ids:
            continue
        fact_coverage = {fact["label"]: "covered" for fact in rule["requiredFacts"]}
        fact_coverage[rule["requiredFacts"][0]["label"]] = "missing"
        output[rule["id"]] = {
            "factCoverage": fact_coverage,
            "evidenceLocations": [{"page": 99 if invalid_location else 1, "paragraph": 1}],
            "reason": "演示模型返回了可定位的不完整结果。",
            "suggestedQuestion": rule["suggestedQuestion"],
            "advisories": [],
        }
    return output


def test_qwen_reviews_three_present_and_four_flows_concurrently(monkeypatch):
    demo = _demo_document()
    full_output = _structured_review_output(demo)
    active = 0
    max_active = 0
    group_calls: list[list[str]] = []

    async def fake_review_group(_client, _document, rules, _correction=None):
        nonlocal active, max_active
        group_calls.append([rule["group"] for rule in rules])
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {rule["id"]: qwen.ModelRuleResult.model_validate(full_output[rule["id"]]) for rule in rules}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen, "_review_rule_group", fake_review_group, raising=False)
    monkeypatch.setattr(qwen.httpx, "AsyncClient", lambda **_kwargs: DummyClient())
    group_timings: dict[str, int] = {}

    results = asyncio.run(qwen.review_with_qwen(demo, group_timings=group_timings))

    assert max_active == 2
    assert sorted(group_calls) == [["三现"] * 3, ["四流"] * 4]
    assert set(group_timings) == {"三现", "四流"}
    assert all(duration >= 0 for duration in group_timings.values())
    assert len(results) == len(RULES)


def test_qwen_accepts_multiple_evidence_locations_per_rule():
    demo = _demo_document()
    first = demo.pages[0].paragraphs[0].text
    second = demo.pages[0].paragraphs[1].text
    payload = {"results": []}
    for rule in RULES:
        payload["results"].append({
            "ruleId": rule["id"],
            "status": "incomplete",
            "missingFacts": [rule["requiredFacts"][0]["label"]],
            "evidence": f"{first}\n{second}",
            "evidenceLocations": [
                {"page": 1, "paragraph": 1},
                {"page": 1, "paragraph": 2},
            ],
            "reason": "相关事实分布在相邻问答段落中。",
            "suggestedQuestion": rule["suggestedQuestion"],
            "advisories": [],
        })

    results = qwen._validate(payload, demo)

    assert all(len(result.evidenceLocations) == 2 for result in results)
    assert all(result.evidenceLocation == result.evidenceLocations[0] for result in results)


def test_strict_review_schema_uses_only_supported_provider_keywords():
    serialized = json.dumps(qwen.structured_review_schema(), ensure_ascii=False)
    assert "uniqueItems" not in serialized
    for rule in RULES:
        locations = qwen.structured_review_schema()["properties"][rule["id"]]["properties"]["evidenceLocations"]
        assert locations["maxItems"] == 3


def test_qwen_retries_only_the_failed_group(monkeypatch):
    demo = _demo_document()
    full_output = _structured_review_output(demo)
    attempts = {"三现": 0, "四流": 0}

    async def fake_review_group(_client, _document, rules, _correction=None):
        group = rules[0]["group"]
        attempts[group] += 1
        if group == "三现" and attempts[group] == 1:
            raise AppError("invalid_model_response", "首次结构错误。", 502)
        return {rule["id"]: qwen.ModelRuleResult.model_validate(full_output[rule["id"]]) for rule in rules}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen, "_review_rule_group_once", fake_review_group, raising=False)
    monkeypatch.setattr(qwen.httpx, "AsyncClient", lambda **_kwargs: DummyClient())

    results = asyncio.run(qwen.review_with_qwen(demo))

    assert len(results) == len(RULES)
    assert attempts == {"三现": 2, "四流": 1}


def test_qwen_openai_compatible_success_path(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    requested_groups: list[list[str]] = []

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
        rule_ids = schema["required"]
        requested_groups.append(rule_ids)
        assert rule_ids in [
            [rule["id"] for rule in RULES if rule["group"] == "三现"],
            [rule["id"] for rule in RULES if rule["group"] == "四流"],
        ]
        assert schema["additionalProperties"] is False
        content = json.dumps(_structured_review_output(demo, rule_ids=rule_ids), ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def client_factory(*_args, **kwargs):
        assert kwargs["timeout"].read >= 120
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    assert created.status_code == 202
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(task["results"]) == len(RULES)
    assert len(requested_groups) == 2
    assert set(task["timings"]["modelGroupsMs"]) == {"三现", "四流"}
    assert all("Qwen 辅助判断" in item["source"] for item in task["results"])
    assert all(item["evidence"] == demo.pages[0].paragraphs[0].text for item in task["results"])


def test_qwen_retries_once_with_validation_feedback(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    requests: list[dict] = []
    attempts: dict[tuple[str, ...], int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        rule_ids = _request_rule_ids(request_body)
        group_key = tuple(rule_ids)
        attempts[group_key] = attempts.get(group_key, 0) + 1
        output = _structured_review_output(
            demo,
            invalid_location=attempts[group_key] == 1,
            rule_ids=rule_ids,
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 4
    correction_requests = [request for request in requests if len(request["messages"]) == 3]
    assert len(correction_requests) == 2
    assert all("evidenceLocations" in request["messages"][-1]["content"] for request in correction_requests)
    assert any("PRESENT-001" in request["messages"][-1]["content"] for request in correction_requests)


def test_qwen_correction_lists_allowed_fact_coverage_keys(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    requests: list[dict] = []
    present_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal present_attempts
        request_body = json.loads(request.content)
        requests.append(request_body)
        rule_ids = _request_rule_ids(request_body)
        output = _structured_review_output(demo, rule_ids=rule_ids)
        if "PRESENT-001" in rule_ids:
            present_attempts += 1
        if "PRESENT-001" in rule_ids and present_attempts == 1:
            output["PRESENT-001"]["factCoverage"][RULES[0]["referenceHints"][0]["label"]] = "missing"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    feedback = next(request["messages"][-1]["content"] for request in requests if len(request["messages"]) == 3)
    assert "factCoverage 只允许以下键" in feedback
    assert all(fact["label"] in feedback for fact in RULES[0]["requiredFacts"])


def test_qwen_fails_without_partial_results_after_two_invalid_responses(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        request_body = json.loads(request.content)
        output = _structured_review_output(demo, invalid_location=True, rule_ids=_request_rule_ids(request_body))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert request_count == 4
    assert task["status"] == "failed"
    assert task["errorCode"] == "insufficient_evidence"
    assert task["results"] == []


def test_qwen_falls_back_to_function_calling_when_json_schema_is_unsupported(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    requests: list[dict] = []
    attempts: dict[tuple[str, ...], int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        rule_ids = _request_rule_ids(request_body)
        group_key = tuple(rule_ids)
        attempts[group_key] = attempts.get(group_key, 0) + 1
        if attempts[group_key] == 1:
            return httpx.Response(400, json={"error": {"message": "response_format json_schema is not supported"}})
        assert request_body["tool_choice"]["function"]["name"] == qwen.TOOL_NAME
        assert request_body["tools"][0]["function"]["parameters"]["required"] == rule_ids
        arguments = json.dumps(_structured_review_output(demo, rule_ids=rule_ids), ensure_ascii=False)
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

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 4


def test_qwen_retries_transient_http_failure_with_json_schema(monkeypatch):
    real_async_client = httpx.AsyncClient
    demo = _demo_document()
    requests: list[dict] = []
    attempts: dict[tuple[str, ...], int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        requests.append(request_body)
        rule_ids = _request_rule_ids(request_body)
        group_key = tuple(rule_ids)
        attempts[group_key] = attempts.get(group_key, 0) + 1
        if attempts[group_key] == 1:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        assert request_body["response_format"]["type"] == "json_schema"
        content = json.dumps(_structured_review_output(demo, rule_ids=rule_ids), ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def client_factory(*_args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(qwen, "QWEN_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setattr(qwen, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(qwen, "QWEN_MODEL", "test-model")
    monkeypatch.setattr(qwen.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(qwen.asyncio, "sleep", AsyncMock())

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert task["status"] == "completed"
    assert len(requests) == 4


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

    created = client.post("/api/v1/reviews/demos/case-02-explicit-omissions", json={})
    task = client.get(f"/api/v1/reviews/{created.json()['taskId']}").json()
    assert request_count == 2
    assert task["status"] == "failed"
    assert task["errorCode"] == "model_auth_failed"
    assert task["results"] == []
