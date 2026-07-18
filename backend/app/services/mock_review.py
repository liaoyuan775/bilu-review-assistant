from app.data import TEMPLATE_RULE_CATALOG
from app.models import EvidenceLocation, ManualDecision, ParsedDocument, ReviewResult, RuleStatus
from app.template_models import TemplateRule


MOCK_SOURCE = (
    f"内部询问笔录模板 v{TEMPLATE_RULE_CATALOG.version}"
    "（模拟结果，仅用于界面流程演示；证据摘自当前脱敏文档）"
)

_GROUP_KEYWORDS = {
    "META": ("姓名", "身份证", "询问地点", "签名"),
    "PROC": ("告知", "回避", "核对", "真实"),
    "CASE": ("事情经过", "报警", "被骗", "转账"),
    "PREV": ("反诈", "宣传"),
    "RISK": ("转账", "风险", "报警"),
    "CASH": ("取款", "银行", "现金"),
    "TIME": ("时间", "时", "地点"),
    "PRIV": ("个人信息", "身份证", "手机号"),
    "LEAD": ("广告", "最初", "联系"),
    "MOTIVE": ("要求", "继续", "联系"),
    "CONTACT": ("平台", "微信", "账号", "APP"),
    "MONEY": ("转账", "金额", "损失", "返利"),
    "OFFLINE": ("寄递", "物品", "现金"),
    "EXTRA": ("补充", "陈述"),
    "EVID": ("记录", "截图", "证据", "保存", "提交"),
}


def _find_evidence(
    document: ParsedDocument,
    rule: TemplateRule,
) -> tuple[str, list[EvidenceLocation], list[str]]:
    keywords = {keyword.lower() for keyword in _GROUP_KEYWORDS[rule.group]}
    candidates: list[tuple[int, int, int, str, str]] = []
    for page in document.pages:
        for paragraph_index, paragraph in enumerate(page.paragraphs, start=1):
            text = paragraph.text.strip()
            score = sum(keyword in text.lower() for keyword in keywords)
            if text and score:
                candidates.append((score, page.page, paragraph_index, text, paragraph.id))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected = candidates[:3]
    if not selected:
        for page in document.pages:
            if page.paragraphs:
                paragraph = page.paragraphs[0]
                selected = [(0, page.page, 1, paragraph.text.strip(), paragraph.id)]
                break

    locations = [EvidenceLocation(page=page, paragraph=paragraph) for _, page, paragraph, _, _ in selected]
    evidence = "\n".join(text for _, _, _, text, _ in selected)
    anchor_ids = [anchor_id for _, _, _, _, anchor_id in selected]
    return evidence, locations, anchor_ids


def build_mock_review(document: ParsedDocument) -> list[ReviewResult]:
    """基于内部模板规则和真实 DOCX 段落构造明确标识的快速演示结果。"""
    results: list[ReviewResult] = []
    for rule in TEMPLATE_RULE_CATALOG.rules:
        evidence, locations, anchor_ids = _find_evidence(document, rule)
        is_incomplete = rule.ruleId == "RISK-001"
        is_not_applicable = rule.group in {"CASH", "OFFLINE"}
        status = (
            RuleStatus.INCOMPLETE
            if is_incomplete
            else RuleStatus.NOT_APPLICABLE
            if is_not_applicable
            else RuleStatus.COVERED
        )
        results.append(ReviewResult(
            ruleId=rule.ruleId,
            ruleName=rule.name,
            category=rule.group,
            group=rule.group,
            status=status,
            missingFacts=["risk.payment_warning_channel", "risk.payment_warning_content"] if is_incomplete else [],
            evidence=evidence,
            evidenceLocation=locations[0] if locations else None,
            evidenceLocations=locations,
            evidenceAnchorIds=anchor_ids,
            reason=(
                "演示文档记录了多笔转账，但未明确询问转账前是否收到风险提示及提示内容。"
                if is_incomplete
                else "文档已明确说明当前条件未触发。"
                if is_not_applicable
                else "演示文档已覆盖该模板规则要求的主要事实。"
            ),
            suggestedQuestion=rule.suggestedQuestion if is_incomplete else "",
            advisories=[],
            manualDecision=ManualDecision(),
            source=MOCK_SOURCE,
            severity=rule.severity,
        ))
    return results
