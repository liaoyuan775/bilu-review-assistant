"""
DOCX 补问工作清单生成 — 使用 python-docx 库生成 Word 格式的补问清单。

职责边界：
- 只负责生成补问清单 DOCX 文件（用于线下补充询问）。
- 不处理其他类型的产物（PDF、JSON 等）。

设计说明：
- 使用 Microsoft YaHei 字体（Windows 系统默认中文字体）。
- 支持 Word 域代码（PAGE / NUMPAGES）用于自动页码。
- 表格显示元信息（文件名、任务编号、审查模式等）。
- 按规则逐项列出审查结果和人工处置情况。

依赖关系：
- core/models.py: ReviewTask、RuleStatus 模型。
- reporting/report_labels.py: 标签格式化工具。
"""

from io import BytesIO

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.core.models import ReviewTask, RuleStatus
from app.reporting.presentation import fact_label, localize_fact_paths, sort_review_results
from app.reporting.report_labels import event_type_label, format_datetime, manual_status_label, mode_label, review_status_label, severity_label


_STATUS_LABELS = {
    RuleStatus.COVERED: "已通过",
    RuleStatus.MISSING: "未询问",
    RuleStatus.INCOMPLETE: "回答不清",
    RuleStatus.INCONSISTENT: "事实矛盾",
    RuleStatus.NOT_APPLICABLE: "规则不适用",
    RuleStatus.NEEDS_MANUAL_REVIEW: "待人工判断",
}


def _set_cell_text(cell, text: str, *, bold: bool = False) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(9)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _add_field(paragraph, instruction: str) -> None:
    """添加 Word 域代码（如 PAGE、NUMPAGES）。"""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t")
    value.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, text, separate, value, end])


def _configure(document: Document) -> None:
    """配置文档默认样式、页边距和页码。"""
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(5)
    for name, size in (("Title", 18), ("Heading 1", 14), ("Heading 2", 11)):
        style = document.styles[name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(37, 59, 91)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("第 ")
    _add_field(footer, "PAGE")
    footer.add_run(" 页 / 共 ")
    _add_field(footer, "NUMPAGES")
    footer.add_run(" 页")


def build_follow_up_docx(task: ReviewTask, manual_events: list[dict]) -> bytes:
    """生成补问工作清单 DOCX。

    清单包含：
    1. 元信息表格（文件名、任务编号、审查模式等）。
    2. 逐项审查详情（规则 ID、状态、证据、补问建议）。
    3. 人工操作记录。

    Args:
        task:          审查任务。
        manual_events: 人工操作事件列表。

    Returns:
        DOCX 文件的二进制内容。
    """
    document = Document()
    _configure(document)
    title = document.add_heading("电信网络诈骗询问笔录补问工作清单", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = document.add_paragraph("内部审查辅助材料 - 结论以承办民警复核为准")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    table = document.add_table(rows=3, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    metadata = [
        ("文件名称", task.document.name if task.document else "未命名笔录"),
        ("任务编号", task.id),
        ("文档版本", task.documentVersionId or "-"),
        ("审查模式", mode_label(task.mode)),
        ("创建时间", format_datetime(task.createdAt)),
        ("当前状态", review_status_label(task.reviewStatus)),
    ]
    pairs = zip(metadata[::2], metadata[1::2])
    for row, ((left_key, left_value), (right_key, right_value)) in zip(table.rows, pairs):
        _set_cell_text(row.cells[0], left_key, bold=True)
        _set_cell_text(row.cells[1], left_value)
        _set_cell_text(row.cells[2], right_key, bold=True)
        _set_cell_text(row.cells[3], right_value)

    document.add_heading("补问事项", level=1)
    selected = sort_review_results([
        item for item in task.results
        if item.manualDecision.status.value == "supplemented"
    ])
    if not selected:
        document.add_paragraph("当前没有需要补问或记录处置依据的事项。")
    for index, item in enumerate(selected, start=1):
        document.add_heading(f"{index}. {item.ruleId} {item.ruleName}", level=2)
        paragraph = document.add_paragraph()
        paragraph.add_run("审查状态：").bold = True
        paragraph.add_run(_STATUS_LABELS[item.status])
        paragraph.add_run("    风险等级：").bold = True
        paragraph.add_run(severity_label(item.severity))
        document.add_paragraph(f"审查说明：{localize_fact_paths(item.reason)}")
        if item.missingFacts:
            document.add_paragraph(f"缺失或不清字段：{'、'.join(fact_label(path) for path in item.missingFacts)}")
        if item.evidence:
            document.add_paragraph(f"证据原文：{item.evidence}")
        if item.suggestedQuestion:
            document.add_paragraph(f"建议补问：{item.suggestedQuestion}")
        decision = item.manualDecision
        document.add_paragraph(f"人工判断：{manual_status_label(decision.status)}；说明：{decision.reason or '未填写'}")

    document.add_heading("人工操作记录", level=1)
    if not manual_events:
        document.add_paragraph("暂无人工操作记录。")
    for event in manual_events:
        document.add_paragraph(f"{format_datetime(event['createdAt'])}  {event['actorId']}  {event_type_label(event['eventType'])}")
    document.add_heading("使用说明", level=1)
    document.add_paragraph("本清单仅用于检查询问完整性和记录补问过程，不替代案件定性、证据判断或执法决定。")
    output = BytesIO()
    document.save(output)
    return output.getvalue()
