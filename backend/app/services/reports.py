from collections import Counter
from html import escape
from io import BytesIO
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import QWEN_MODEL
from app.data import TEMPLATE_RULE_CATALOG
from app.errors import AppError
from app.models import ArtifactSummary, ReviewStatus, ReviewTask, TaskStatus, now_iso
from app.services.artifacts import GENERATED_REVIEW_ARTIFACT_TYPES, save_generated
from app.services.docx_report import build_follow_up_docx
from app.services.parser import PARSER_VERSION
from app.services.report_labels import event_type_label, format_datetime, manual_status_label, mode_label, severity_label
from app.store import get_audit_snapshot, get_task, save_artifact_record, save_task_with_events


_PDF_FONT = "BiluYaHei"
_WINDOWS_CJK_FONT = Path("C:/Windows/Fonts/msyh.ttc")
if _WINDOWS_CJK_FONT.is_file():
    pdfmetrics.registerFont(TTFont(_PDF_FONT, str(_WINDOWS_CJK_FONT), subfontIndex=0))
else:
    _PDF_FONT = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(_PDF_FONT))
_STATUS_LABELS = {
    "covered": "已覆盖",
    "missing": "未询问",
    "incomplete": "回答不清",
    "inconsistent": "事实矛盾",
    "not_applicable": "不适用",
    "needs_manual_review": "待人工判断",
}


def _json_value(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _manual_events(snapshot: dict) -> list[dict]:
    return [{
        "id": event["id"],
        "eventType": event["event_type"],
        "actorId": event["actor_id"],
        "payload": _json_value(event.get("payload_json"), {}),
        "createdAt": event["created_at"],
    } for event in snapshot["events"]]


def build_structured_report(task: ReviewTask, snapshot: dict) -> dict:
    counts = Counter(item.status.value for item in task.results)
    current_run = next(
        (run for run in snapshot.get("runs", []) if run["id"] == task.reviewRunId),
        None,
    )
    current_version_id = (
        current_run["document_version_id"]
        if current_run is not None
        else task.documentVersionId
    )
    return {
        "schemaVersion": "template-review-report-v1",
        "task": {
            "id": task.id,
            "mode": task.mode.value,
            "status": task.status.value,
            "reviewStatus": task.reviewStatus.value,
            "createdAt": task.createdAt,
            "updatedAt": task.updatedAt,
            "documentId": task.documentId,
            "documentVersionId": task.documentVersionId,
            "reviewRunId": task.reviewRunId,
        },
        "document": task.document.model_dump(mode="json") if task.document else None,
        "victimProfile": task.victimProfile.model_dump(mode="json") if task.victimProfile else None,
        "versions": {
            "rule": TEMPLATE_RULE_CATALOG.version,
            "model": QWEN_MODEL,
            "parser": PARSER_VERSION,
        },
        "counts": {status: counts.get(status, 0) for status in _STATUS_LABELS},
        "results": [item.model_dump(mode="json") for item in task.results],
        "manualEvents": _manual_events(snapshot),
        "facts": [{
            "runId": fact["run_id"],
            "documentVersionId": current_version_id,
            "path": fact["path"],
            "payload": _json_value(fact.get("payload"), {}),
            "createdAt": fact["created_at"],
        } for fact in snapshot["facts"] if fact["run_id"] == task.reviewRunId],
    }


def _paragraph_text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_states = []

    def showPage(self):
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            self.setFont(_PDF_FONT, 8)
            self.setFillColor(colors.HexColor("#607086"))
            self.drawCentredString(A4[0] / 2, 11 * mm, f"第 {self._pageNumber} 页 / 共 {page_count} 页")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def build_review_pdf(task: ReviewTask, payload: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title="询问笔录审查复核报告",
        author="笔录审查助手",
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle("CnTitle", parent=base["Title"], fontName=_PDF_FONT, fontSize=18, leading=25, alignment=TA_CENTER, textColor=colors.HexColor("#253b5b"))
    heading = ParagraphStyle("CnHeading", parent=base["Heading2"], fontName=_PDF_FONT, fontSize=11, leading=16, textColor=colors.HexColor("#253b5b"), spaceBefore=6, spaceAfter=5, wordWrap="CJK")
    body = ParagraphStyle("CnBody", parent=base["BodyText"], fontName=_PDF_FONT, fontSize=8.5, leading=14, textColor=colors.HexColor("#344258"), wordWrap="CJK")
    small = ParagraphStyle("CnSmall", parent=body, fontSize=7.5, leading=12, textColor=colors.HexColor("#5a687a"))
    centered = ParagraphStyle("CnSub", parent=small, alignment=TA_CENTER)
    story = [
        Paragraph("电信网络诈骗询问笔录审查复核报告", title),
        Paragraph("内部辅助审查材料 - 结论以承办民警复核为准", centered),
        Spacer(1, 7 * mm),
    ]
    metadata = [
        ["文件名称", task.document.name if task.document else "未命名笔录", "任务编号", task.id],
        ["文档版本", task.documentVersionId or "-", "审查模式", mode_label(task.mode)],
        ["规则版本", TEMPLATE_RULE_CATALOG.version, "模型", QWEN_MODEL],
    ]
    meta_table = Table(metadata, colWidths=[22 * mm, 60 * mm, 22 * mm, 58 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _PDF_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f7")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef3f7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5df")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([meta_table, Spacer(1, 5 * mm), Paragraph("审查概览", heading)])
    count_cells = [
        Paragraph(f"{_STATUS_LABELS[key]}<br/><b>{payload['counts'][key]}</b>", centered)
        for key in _STATUS_LABELS
    ]
    count_table = Table([count_cells], colWidths=[27 * mm] * len(_STATUS_LABELS))
    count_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5df")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([count_table, Spacer(1, 5 * mm), Paragraph("逐项审查与人工处置", heading)])
    for index, item in enumerate(task.results, start=1):
        story.append(Paragraph(
            f"<b>{index}. {escape(item.ruleId)} {escape(item.ruleName)}</b>　{_STATUS_LABELS[item.status.value]}　{severity_label(item.severity)}风险",
            heading,
        ))
        story.append(Paragraph(f"审查说明：{_paragraph_text(item.reason)}", body))
        if item.missingFacts:
            story.append(Paragraph(f"缺失或不清字段：{_paragraph_text('、'.join(item.missingFacts))}", small))
        if item.evidence:
            story.append(Paragraph(f"证据原文：{_paragraph_text(item.evidence)}", small))
        if item.suggestedQuestion:
            story.append(Paragraph(f"建议补问：{_paragraph_text(item.suggestedQuestion)}", body))
        decision = item.manualDecision
        story.append(Paragraph(f"人工处置：{manual_status_label(decision.status)}；依据：{_paragraph_text(decision.reason or '未填写')}", small))
        story.append(Spacer(1, 2.5 * mm))
    story.extend([PageBreak(), Paragraph("人工操作记录", heading)])
    if not payload["manualEvents"]:
        story.append(Paragraph("暂无人工操作记录。", body))
    for event in payload["manualEvents"]:
        story.append(Paragraph(f"{format_datetime(event['createdAt'])}　{escape(event['actorId'])}　{event_type_label(event['eventType'])}", body))
    story.extend([
        Spacer(1, 5 * mm),
        Paragraph("说明", heading),
        Paragraph("本报告用于检查询问完整性、回答清晰度和事实一致性，不替代案件定性、证据效力判断或执法决定。", body),
    ])
    document.build(story, canvasmaker=_NumberedCanvas)
    return output.getvalue()


def _save_record(task: ReviewTask, artifact_type: str, filename: str, content: bytes) -> ArtifactSummary:
    artifact = save_generated(task.id, artifact_type, filename, content)
    record_id = save_artifact_record(
        task.id,
        task.documentVersionId,
        artifact_type=artifact_type,
        filename=artifact.filename,
        path=str(artifact.path),
        sha256=artifact.sha256,
        size_bytes=artifact.sizeBytes,
        metadata={
            "ruleVersion": TEMPLATE_RULE_CATALOG.version,
            "model": QWEN_MODEL,
            "parserVersion": PARSER_VERSION,
        },
    )
    return ArtifactSummary(id=record_id, type=artifact_type, filename=artifact.filename, sha256=artifact.sha256, sizeBytes=artifact.sizeBytes)


def generate_review_artifacts(task_id: str) -> ReviewTask:
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能重新生成产物。", 409)
    if task.status != TaskStatus.COMPLETED or task.document is None or not task.documentVersionId:
        raise AppError("task_not_completed", "审查尚未完成，不能生成归档产物。", 409)
    snapshot = get_audit_snapshot(task.id)
    payload = build_structured_report(task, snapshot)
    structured_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    docx = build_follow_up_docx(task, payload["manualEvents"])
    pdf = build_review_pdf(task, payload)
    stem = Path(task.document.name).stem
    current = [item for item in task.artifacts if item.type == "original"]
    if not current:
        raise AppError("original_artifact_missing", "审查原件缺失，不能生成归档清单。", 409)
    generated = [
        _save_record(task, "review_pdf", f"{stem}-审查复核报告.pdf", pdf),
        _save_record(task, "follow_up_docx", f"{stem}-补问工作清单.docx", docx),
        _save_record(task, "structured_json", f"{stem}-结构化审查.json", structured_json),
    ]
    listed = [*current, *generated]
    manifest_payload = {
        "schemaVersion": "template-review-archive-v1",
        "taskId": task.id,
        "documentVersionId": task.documentVersionId,
        "generatedAt": now_iso(),
        "versions": {"rule": TEMPLATE_RULE_CATALOG.version, "model": QWEN_MODEL, "parser": PARSER_VERSION},
        "artifacts": [{
            "type": item.type,
            "filename": item.filename,
            "sha256": item.sha256,
            "sizeBytes": item.sizeBytes,
        } for item in listed],
    }
    manifest_bytes = json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    manifest = _save_record(task, "archive_manifest", f"{stem}-归档清单.json", manifest_bytes)
    task.requiredArtifacts = list(GENERATED_REVIEW_ARTIFACT_TYPES)
    task.artifacts = [*listed, manifest]
    return save_task_with_events(task, [{
        "issue_id": None,
        "event_type": "artifacts_generated",
        "actor_id": "local-operator",
        "payload": {"documentVersionId": task.documentVersionId, "artifactIds": [item.id for item in generated] + [manifest.id]},
    }])
