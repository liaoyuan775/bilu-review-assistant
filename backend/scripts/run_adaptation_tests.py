"""Upload five DOCX fixtures and persist parser/API/timing evidence."""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from docx import Document


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend" / "test-fixtures"
OUT = ROOT / "backend" / "test-results"
API = "http://127.0.0.1:8787/api/v1"
POLL_SECONDS = 2
TIMEOUT_SECONDS = 900
HTTP = request.build_opener(request.ProxyHandler({}))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_request(method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with HTTP.open(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def _multipart_upload(url: str, filename: str, content: bytes) -> tuple[int, dict]:
    boundary = f"----codex-adaptation-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    return _json_request(
        "POST",
        url,
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def _paragraph_summary(task: dict) -> list[dict]:
    result = []
    for page in task.get("document", {}).get("pages", []):
        for index, paragraph in enumerate(page.get("paragraphs", []), start=1):
            result.append({
                "page": page.get("page"),
                "paragraph": index,
                "id": paragraph.get("id"),
                "sourceType": paragraph.get("sourceType"),
                "charStart": paragraph.get("charStart"),
                "charEnd": paragraph.get("charEnd"),
                "text": paragraph.get("text", ""),
            })
    return result


def _averages(records: list[dict]) -> dict:
    completed = [r for r in records if r.get("status") == "completed"]

    def avg(values):
        return round(statistics.mean(values), 2) if values else None

    def values(path: str):
        return [r.get("timings", {}).get(path) for r in completed if r.get("timings", {}).get(path) is not None]

    return {
        "sampleCount": len(records),
        "completedCount": len(completed),
        "failedCount": len(records) - len(completed),
        "paragraphCountAverage": avg([r["paragraphCount"] for r in completed]),
        "questionAnswerCountAverage": avg([r["questionAnswerCount"] for r in completed]),
        "wallClockMsAverage": avg([r["wallClockMs"] for r in completed]),
        "parseMsAverage": avg(values("parseMs")),
        "modelReviewMsAverage": avg(values("modelReviewMs")),
        "apiTotalMsAverage": avg(values("totalMs")),
    }


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    health_status, health_payload = _json_request("GET", f"{API}/health")
    if health_status >= 400:
        raise RuntimeError(f"health check failed: HTTP {health_status} {health_payload}")
    records = []
    for fixture in sorted(FIXTURES.glob("*.docx")):
        content = fixture.read_bytes()
        started = time.perf_counter()
        record = {
            "fixture": fixture.name,
            "fixturePath": str(fixture),
            "fixtureSha256": hashlib.sha256(content).hexdigest(),
            "fixtureBytes": len(content),
            "fixtureParagraphCount": len(Document(fixture).paragraphs),
            "startedAt": _utc_now(),
        }
        try:
            upload_status, upload_payload = _multipart_upload(f"{API}/reviews", fixture.name, content)
            record["uploadHttpStatus"] = upload_status
            record["uploadResponse"] = upload_payload
            if upload_status >= 400:
                raise RuntimeError(f"upload failed: HTTP {upload_status} {upload_payload}")
            task_id = upload_payload["taskId"]
            record["taskId"] = task_id
            deadline = time.perf_counter() + TIMEOUT_SECONDS
            while True:
                task_status, task = _json_request("GET", f"{API}/reviews/{task_id}")
                record["finalHttpStatus"] = task_status
                if task.get("status") in {"completed", "failed"}:
                    break
                if time.perf_counter() >= deadline:
                    raise TimeoutError(f"task did not finish: {task.get('status')}")
                time.sleep(POLL_SECONDS)
            record["status"] = task.get("status")
            record["finalResponse"] = task
            record["paragraphs"] = _paragraph_summary(task)
            record["paragraphCount"] = len(record["paragraphs"])
            record["questionAnswerCount"] = len(task.get("document", {}).get("questionAnswers", []))
            record["timings"] = task.get("timings", {})
            record["error"] = task.get("error")
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        record["wallClockMs"] = round((time.perf_counter() - started) * 1000, 2)
        record["finishedAt"] = _utc_now()
        records.append(record)
        (OUT / f"{fixture.stem}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "generatedAt": _utc_now(),
        "apiBase": API,
        "healthResponse": health_payload,
        "records": records,
        "average": _averages(records),
    }
    (OUT / "adaptation-test-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report)
    return report


def _write_markdown(report: dict) -> None:
    lines = [
        "# DOCX adaptation test results",
        "",
        f"Generated at: {report['generatedAt']}",
        f"API: `{report['apiBase']}`",
        "",
        "## Averages",
        "",
        "| Metric | Average |",
        "|---|---:|",
    ]
    for key, value in report["average"].items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Per-file results",
        "",
        "| File | Status | Paragraphs | Q&A | API total ms | Wall clock ms |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for record in report["records"]:
        timing = record.get("timings", {})
        lines.append(
            f"| {record['fixture']} | {record.get('status')} | {record.get('paragraphCount', '-')} | "
            f"{record.get('questionAnswerCount', '-')} | {timing.get('totalMs', '-')} | {record.get('wallClockMs', '-')} |"
        )
    lines += [
        "",
        "See the JSON files in this directory for paragraph text, Q&A, raw upload response, final task response, and errors.",
        "",
    ]
    (OUT / "adaptation-test-results.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        report = run()
    except Exception as exc:
        print(f"adaptation test failed: {exc}", file=sys.stderr)
        raise
    print(json.dumps(report["average"], ensure_ascii=False, indent=2))
