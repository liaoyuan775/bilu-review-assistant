from __future__ import annotations

import argparse
from collections import defaultdict
from html import escape
import json
from pathlib import Path
import sys
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.models import ReviewTask  # noqa: E402
from app.data.rules import TEMPLATE_RULE_CATALOG, TEMPLATE_RULES  # noqa: E402
from app.review.extraction import DOMAIN_ENTITY_FIELDS, DOMAIN_FACT_PATHS, DOMAIN_ORDER  # noqa: E402
from app.storage.store import SqliteTaskStore  # noqa: E402


DOMAIN_LABELS = {
    "header_procedure": "笔录头、个人信息与程序确认",
    "case_timeline": "案件经过、时间地点与主观原因",
    "contact_channels": "首次接触与联系渠道切换",
    "risk_and_evidence": "反诈宣传、风险提示与证据留存",
    "online_money": "线上资金流",
    "offline_delivery": "取现与线下交付",
    "special_scenarios": "特殊场景与补充事实",
}

CLARITY_LABELS = {
    "clear": "明确",
    "unclear": "表述不清",
    "unknown": "未知",
    "missing": "原文缺失",
}

PROFILE_LABELS = {
    "name": "姓名",
    "gender": "性别",
    "age": "年龄",
    "birthDate": "出生日期",
    "ethnicity": "民族",
    "idNumber": "身份证号",
    "occupation": "职业",
    "education": "文化程度",
    "employer": "工作单位",
    "address": "现住址",
    "registeredAddress": "户籍所在地",
    "contact": "联系方式",
    "isNpcRepresentative": "是否人大代表",
}

FACT_LABELS = {
    "procedure.key_information_reconfirmed": "重要信息再次确认",
    "procedure.record_matches_statement": "笔录与陈述一致",
    "procedure.record_reviewed": "笔录已经阅看",
    "procedure.recusal_requested": "是否申请回避",
    "procedure.rights_notice_read": "权利义务告知书已阅",
    "procedure.rights_request": "权利请求",
    "procedure.statement_confirmed_true": "陈述真实性确认",
    "procedure.truth_notice_confirmed": "如实作答义务确认",
    "record.interviewers": "询问人员",
    "record.location": "询问地点",
    "record.respondent": "被询问人",
    "record.signatures": "签名确认",
    "record.started_at": "询问开始时间",
    "victim.age": "年龄",
    "victim.education": "文化程度",
    "victim.employer": "工作单位",
    "victim.gender": "性别",
    "victim.id_number": "身份证件号码",
    "victim.name": "姓名",
    "victim.occupation": "职业",
    "victim.phone": "联系电话",
    "case.channel_changes": "联系渠道变化",
    "case.contact_method": "联系方式",
    "case.fraud_method": "诈骗方式",
    "case.fraud_tools": "诈骗工具",
    "case.initial_channel": "首次联系渠道",
    "case.initial_contact": "首次接触情况",
    "case.location": "案发地点",
    "case.payment_reason": "付款原因",
    "case.payment_summary": "付款概况",
    "case.rebate_summary": "返利概况",
    "case.report_reason": "报案原因",
    "case.timeline": "诈骗经过时间线",
    "case.total_loss": "损失总额",
    "motive.continued_contact_reason": "持续联系原因",
    "privacy.disclosed_information": "泄露的个人信息",
    "privacy.disclosure_occurred": "案发前是否泄露个人信息",
    "privacy.disclosure_reason": "个人信息泄露原因",
    "privacy.disclosure_time": "个人信息泄露时间",
    "timeline.first_contact_at": "最早联系时间",
    "timeline.incident_at": "案发时间",
    "timeline.incident_community": "案发社区",
    "timeline.incident_district": "案发区县",
    "timeline.incident_street": "案发街道",
    "contact.chat_used": "是否使用聊天软件",
    "contact.initial_account": "首次联系账号",
    "contact.initial_channel": "首次联系渠道",
    "contact.initial_content": "首次联系内容",
    "contact.phone_used": "是否通过电话联系",
    "contact.switch_count": "后续联系人或渠道切换次数",
    "contact.voice_call": "是否进行语音通话",
    "evidence.can_provide": "相关记录能否提供",
    "evidence.record_types": "留存记录类型",
    "evidence.records_retained": "相关记录是否留存",
    "evidence.voice_recording_available": "语音录音能否提供",
    "evidence.voice_recording_exists": "语音通话是否录音",
    "prevention.anti_fraud_app_installed": "国家反诈中心 App 安装情况",
    "prevention.community_police_publicity": "社区民警反诈宣传",
    "prevention.received_publicity": "是否接受反诈宣传",
    "risk.account_loss_reported": "被骗后账户处置",
    "risk.loss_report_time": "账户处置时间",
    "risk.payment_warning_channel": "支付风险提示渠道",
    "risk.payment_warning_content": "支付风险提示内容",
    "risk.payment_warning_received": "是否收到支付风险提示",
    "risk.phone_card_real_name": "电话卡实名情况",
    "risk.phone_warning_received": "是否收到电话卡风险提示",
    "risk.post_report_transfers": "账户处置后是否继续转账",
    "risk.suspect_chat_real_name": "嫌疑人聊天账号实名情况",
    "risk.victim_chat_real_name": "被害人聊天账号实名情况",
    "money.credentials_disclosed": "是否泄露支付凭证",
    "money.gross_loss": "被骗总额",
    "money.net_loss": "净损失",
    "money.rebate_total": "返利总额",
    "money.remote_control_used": "是否使用远程控制",
    "money.transfer_control_method": "资金转出控制方式",
    "online_money.total": "线上转账总额",
    "online_money.transfer_count": "线上转账笔数",
    "online_money.used": "是否发生线上资金转移",
    "cash.bank_appointment": "是否预约银行取款",
    "cash.bank_warning_channel": "银行取款风险提示渠道",
    "cash.bank_warning_received": "是否收到银行取款风险提示",
    "cash.withdrawal_count": "取款笔数",
    "offline.appointment_amount": "预约拿款金额",
    "offline.appointment_location": "预约拿款地点",
    "offline.appointment_time": "预约拿款时间",
    "offline.handoff_count": "线下交付次数",
    "offline.property_source": "现金或实物来源",
    "offline.suspect_appointment": "嫌疑人是否预约拿款",
    "offline.used": "是否发生取现或线下交付",
    "case.additional_statement": "其他补充事实",
    "special.ecommerce_logistics_impersonation": "是否涉及电商物流冒充场景",
    "special.gambling_related": "是否涉及赌博场景",
}

ENTITY_LABELS = {
    "contact_switches": "后续联系人与渠道切换",
    "transfers": "转账记录",
    "rebates": "返利记录",
    "withdrawals": "取款记录",
    "offline_handoffs": "线下交付记录",
}

ENTITY_FIELD_LABELS = {
    "time": "时间",
    "channel": "联系渠道",
    "account": "账号",
    "important_information": "重要信息",
    "details": "详细内容",
    "amount": "金额",
    "payment_method": "支付方式",
    "payer_account": "付款账号",
    "recipient_account": "收款账号",
    "transaction_id": "交易流水号",
    "method": "方式",
    "bank": "银行",
    "branch": "银行网点",
    "address": "地址",
    "location": "地点",
    "property_type": "财物类型",
    "amount_or_value": "金额或价值",
    "recipient_or_logistics": "接收人或物流信息",
}


def _value(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    if value is None:
        return "未提取"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _anchor_index(task: ReviewTask) -> tuple[dict[str, str], dict[str, str]]:
    labels: dict[str, str] = {}
    texts: dict[str, str] = {}
    qa_by_anchor: dict[str, int] = {}
    for number, block in enumerate(task.document.questionAnswers, start=1):
        for anchor in block.anchorIds:
            qa_by_anchor[anchor] = number
    for page in task.document.pages:
        for paragraph_number, paragraph in enumerate(page.paragraphs, start=1):
            qa_number = qa_by_anchor.get(paragraph.id)
            labels[paragraph.id] = (
                f"问答{qa_number}" if qa_number is not None else f"第{page.page}页第{paragraph_number}段"
            )
            texts[paragraph.id] = paragraph.text
    return labels, texts


def _rule_reasons() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    fact_rules: dict[str, list[str]] = defaultdict(list)
    entity_rules: dict[str, list[str]] = defaultdict(list)
    for rule in TEMPLATE_RULES:
        source = (
            f"{rule.ruleId} {rule.name}；模板段落 {','.join(map(str, rule.sourceParagraphs))}；"
            f"来源标记 {rule.sourceMarker}；规则类型 {rule.sourceKind}/{rule.scope}"
        )
        for path in rule.requiredFields:
            fact_rules[path].append(source)
        if rule.appliesWhen:
            fact_rules[rule.appliesWhen.path].append(source + "（用于判断规则是否适用）")
        if rule.repeatEntity:
            entity_rules[rule.repeatEntity.entityType].append(source)
            if rule.repeatEntity.countPath:
                fact_rules[rule.repeatEntity.countPath].append(source + "（用于核对实体数量）")
        for check in rule.consistencyChecks:
            for path in (
                check.totalPath, check.countPath, check.leftPath, check.rightPath,
                check.resultPath, check.earlierPath, check.laterPath,
            ):
                if path:
                    fact_rules[path].append(source + f"（用于 {check.type} 一致性检查）")
    return fact_rules, entity_rules


def build_markdown(task: ReviewTask) -> str:
    extraction = task.extractionPayload or {}
    facts = extraction.get("facts", {})
    entities = extraction.get("entities", {})
    anchor_labels, anchor_texts = _anchor_index(task)
    fact_rules, entity_rules = _rule_reasons()
    lines = [
        "# 上传笔录解析与七域提取明细",
        "",
        f"- 任务 ID：`{task.id}`",
        f"- 文件：`{task.document.name}`",
        f"- 最终状态：`{task.status.value}`",
        f"- 规则目录：`{TEMPLATE_RULE_CATALOG.source.document}` v{TEMPLATE_RULE_CATALOG.version}",
        f"- 问答数：{len(task.document.questionAnswers)}",
        f"- 七域事实数：{len(facts)}",
        f"- 失败域：{', '.join(task.failedDomains) if task.failedDomains else '无'}",
        "",
        "## 提取机制说明",
        "",
        "1. DOCX 解析层按 OpenXML 原始顺序读取正文和表格，把电子方框原位转换为 `[选中]`、`[未选]` 或 `[状态不明]`。",
        "2. 问答重建层只根据 `问：/答：` 边界生成 QA，不依赖固定33题目录；本文件实际得到33个 QA。",
        "3. 个人信息由规则从首道问题前的被询问人信息区提取；只有明确的“基本情况/个人情况”QA可以补空，其他案件QA不参与。",
        "4. 七域字段集合主要从版本化模板规则 `template_rules.json` 的必查事实、条件、重复实体和一致性检查自动推导。",
        "5. Qwen 接收带稳定锚点的完整 QA 和必要结构文本，按域返回事实值、清晰度和证据锚点；后端再校验字段完整性、锚点真实性、重复实体数量以及金额/时间一致性。",
        "6. 因此不是“第N题固定对应一个值”。模板决定要检查什么，原文语义和证据决定从哪些 QA 提取；模板题目变化时，只要语义仍明确，模型仍可跨 QA 找证据。规则目录变化则需要发布新的规则版本。",
        "",
        "## 一、个人信息（规则提取）",
        "",
        "| 字段 | 提取结果 |",
        "|---|---|",
    ]
    profile = task.victimProfile.model_dump() if task.victimProfile else {}
    for field, label in PROFILE_LABELS.items():
        lines.append(f"| {label} | {_value(profile.get(field))} |")

    lines.extend(["", "## 二、问答对（文档解析结果）", ""])
    for number, block in enumerate(task.document.questionAnswers, start=1):
        lines.extend([
            f"### QA {number}",
            "",
            f"**问：** {block.question}",
            "",
            f"**答：** {block.answer or '（空）'}",
            "",
            f"- 回答清晰度：{block.answerClarity}",
            f"- 模板说明：{'；'.join(block.guidance) if block.guidance else '无'}",
            f"- 证据锚点：{', '.join(block.anchorIds)}",
            "",
        ])

    lines.extend(["## 三、七域模型提取", ""])
    for domain in DOMAIN_ORDER:
        lines.extend([
            f"## 3.{DOMAIN_ORDER.index(domain) + 1} {DOMAIN_LABELS[domain]}",
            "",
            f"- 机器域名：`{domain}`",
            f"- 本域事实字段：{len(DOMAIN_FACT_PATHS[domain])}",
            f"- 本域重复实体类型：{', '.join(ENTITY_LABELS.get(x, x) for x in DOMAIN_ENTITY_FIELDS[domain]) or '无'}",
            "",
            "| 中文字段 | 提取值 | 清晰度 | 原文证据位置 | 为什么提取 |",
            "|---|---|---|---|---|",
        ])
        for path in DOMAIN_FACT_PATHS[domain]:
            fact = facts.get(path, {})
            anchors = fact.get("evidenceAnchorIds", [])
            locations = "、".join(dict.fromkeys(anchor_labels.get(x, x) for x in anchors)) or "无"
            reasons = "；".join(dict.fromkeys(fact_rules.get(path, []))) or "七域辅助判定字段"
            lines.append(
                f"| {FACT_LABELS[path]} (`{path}`) | {_value(fact.get('value'))} | "
                f"{CLARITY_LABELS.get(fact.get('clarity'), fact.get('clarity', '未返回'))} | {locations} | {reasons} |"
            )
        for entity_type in DOMAIN_ENTITY_FIELDS[domain]:
            items = entities.get(entity_type, [])
            lines.extend([
                "",
                f"### {ENTITY_LABELS[entity_type]}（{len(items)}项）",
                "",
                f"提取依据：{'；'.join(dict.fromkeys(entity_rules.get(entity_type, []))) or '七域重复实体契约'}",
                "",
            ])
            if not items:
                lines.extend(["无记录。", ""])
            for index, item in enumerate(items, start=1):
                lines.extend([f"#### 第{index}项（技术 ID：`{item.get('id', '')}`）", ""])
                for field in DOMAIN_ENTITY_FIELDS[domain][entity_type]:
                    fact = item.get("fields", {}).get(field, {})
                    anchors = fact.get("evidenceAnchorIds", [])
                    locations = "、".join(dict.fromkeys(anchor_labels.get(x, x) for x in anchors)) or "无"
                    lines.append(
                        f"- {ENTITY_FIELD_LABELS[field]}：{_value(fact.get('value'))}；"
                        f"清晰度={CLARITY_LABELS.get(fact.get('clarity'), fact.get('clarity', '未返回'))}；证据={locations}"
                    )
                lines.append("")

    lines.extend(["## 四、证据锚点原文索引", ""])
    used_anchors = []
    for fact in facts.values():
        used_anchors.extend(fact.get("evidenceAnchorIds", []))
    for items in entities.values():
        for item in items:
            for fact in item.get("fields", {}).values():
                used_anchors.extend(fact.get("evidenceAnchorIds", []))
    for anchor in dict.fromkeys(used_anchors):
        lines.extend([
            f"### {anchor_labels.get(anchor, '未知位置')} (`{anchor}`)",
            "",
            anchor_texts.get(anchor, "锚点原文未找到"),
            "",
        ])
    return "\n".join(lines)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    in_table = False
    for line in lines:
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            cells = [escape(cell.strip()) for cell in line.strip("|").split("|")]
            if not in_table:
                body.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            body.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("#### "):
            body.append(f"<h4>{escape(line[5:])}</h4>")
        elif line.startswith("### "):
            body.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("- "):
            body.append(f"<p class='item'>{escape(line[2:])}</p>")
        elif line:
            body.append(f"<p>{escape(line)}</p>")
    if in_table:
        body.append("</table>")
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>上传笔录解析与七域提取明细</title>
<style>
@page { size: A4; margin: 16mm; }
body { font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; color: #172033; font-size: 12px; line-height: 1.65; max-width: 1080px; margin: 24px auto; }
h1 { font-size: 24px; border-bottom: 2px solid #1d4ed8; padding-bottom: 10px; }
h2 { font-size: 18px; margin-top: 30px; page-break-after: avoid; }
h3 { font-size: 15px; margin-top: 22px; page-break-after: avoid; }
h4 { font-size: 13px; page-break-after: avoid; }
p { white-space: pre-wrap; overflow-wrap: anywhere; }
.item { margin: 3px 0; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 18px; table-layout: fixed; }
th, td { border: 1px solid #cbd5e1; padding: 6px 8px; vertical-align: top; overflow-wrap: anywhere; }
th { background: #eef4ff; text-align: left; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, monospace; }
@media print { body { margin: 0; max-width: none; } }
</style></head><body>""" + "\n".join(body) + "</body></html>"


def markdown_to_pdf(markdown: str, target: Path) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "ChineseNormal", parent=styles["BodyText"], fontName="STSong-Light",
        fontSize=8.5, leading=13, spaceAfter=4,
    )
    bullet = ParagraphStyle("ChineseBullet", parent=normal, leftIndent=12, firstLineIndent=-8)
    headings = {
        1: ParagraphStyle("ChineseH1", parent=normal, fontSize=18, leading=24, spaceAfter=12, textColor=colors.HexColor("#163b70")),
        2: ParagraphStyle("ChineseH2", parent=normal, fontSize=13, leading=18, spaceBefore=10, spaceAfter=7, textColor=colors.HexColor("#163b70")),
        3: ParagraphStyle("ChineseH3", parent=normal, fontSize=10.5, leading=15, spaceBefore=7, spaceAfter=5),
        4: ParagraphStyle("ChineseH4", parent=normal, fontSize=9.5, leading=14, spaceBefore=5, spaceAfter=3),
    }
    table_text = ParagraphStyle("ChineseTable", parent=normal, fontSize=6.5, leading=9)

    def paragraph_text(value: str) -> str:
        escaped = escape(value)
        escaped = escaped.replace("`", "")
        escaped = escaped.replace("**", "")
        return escaped

    story: list[Any] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        columns = len(table_rows[0])
        available = landscape(A4)[0] - 24 * mm
        if columns == 2:
            widths = [42 * mm, available - 42 * mm]
        elif columns == 5:
            widths = [38 * mm, 55 * mm, 18 * mm, 38 * mm, available - 149 * mm]
        else:
            widths = [available / columns] * columns
        data = [
            [Paragraph(paragraph_text(cell), table_text) for cell in row]
            for row in table_rows
        ]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#15345f")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b9c7d8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.extend([table, Spacer(1, 5 * mm)])
        table_rows = []

    for line in markdown.splitlines():
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            table_rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        flush_table()
        if line.startswith("#### "):
            story.append(Paragraph(paragraph_text(line[5:]), headings[4]))
        elif line.startswith("### "):
            story.append(Paragraph(paragraph_text(line[4:]), headings[3]))
        elif line.startswith("## "):
            story.append(Paragraph(paragraph_text(line[3:]), headings[2]))
        elif line.startswith("# "):
            story.append(Paragraph(paragraph_text(line[2:]), headings[1]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + paragraph_text(line[2:]), bullet))
        elif line:
            story.append(Paragraph(paragraph_text(line), normal))
        else:
            story.append(Spacer(1, 2 * mm))
    flush_table()

    def page_footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("STSong-Light", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawCentredString(landscape(A4)[0] / 2, 6 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target), pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title="上传笔录解析与七域提取明细",
        author="笔录辅助审查系统",
    )
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--database", type=Path, default=BACKEND_ROOT / "data" / "reviews.db")
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT.parent / "output" / "reports")
    args = parser.parse_args()
    task = SqliteTaskStore(args.database).get_task(args.task_id)
    if task is None:
        raise SystemExit(f"Task not found: {args.task_id}")
    if task.document is None or task.extractionPayload is None:
        raise SystemExit("Task does not contain a parsed document and completed extraction payload")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{task.document.name.removesuffix('.docx')}-解析与七域提取明细"
    markdown_path = args.output_dir / f"{stem}.md"
    html_path = args.output_dir / f"{stem}.html"
    pdf_path = BACKEND_ROOT.parent / "output" / "pdf" / f"{stem}.pdf"
    markdown = build_markdown(task)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(markdown_to_html(markdown), encoding="utf-8")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_to_pdf(markdown, pdf_path)
    print(markdown_path)
    print(html_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
