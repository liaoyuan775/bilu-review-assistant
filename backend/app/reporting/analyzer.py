"""
文档分析器 — 基于 RULES 关键字的确定性审查（已废弃，仅用于兼容）。

职责边界：
- 使用老版本的三现四流 RULES 做基于关键字匹配的审查。
- 不调用模型，只做简单的关键字搜索。
- 当前仅用于显式的本地演示模式，新流程使用 template_extraction。

注意：
- 这个文件不走"模板规则"路线，直接使用老版 RULES 列表。
- 它和 review/mock.py 的区别：mock.py 使用 TemplateRule，
  而 analyzer.py 使用旧版 RULES（dict 格式）。
- 不建议在新流程中使用。

依赖关系：
- data/rules.py: RULES 旧版规则列表。
- core/models.py: 核心模型。
"""

from app.data.rules import RULES
from app.core.models import EvidenceLocation, ManualDecision, ParsedDocument, ReviewResult, RuleStatus


def _includes_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _locate_evidence(document: ParsedDocument, rule: dict) -> tuple[str, EvidenceLocation | None]:
    candidates: list[tuple[int, str, EvidenceLocation]] = []
    for page in document.pages:
        for index, paragraph in enumerate(page.paragraphs):
            score = sum(1 for fact in rule["requiredFacts"] if _includes_any(paragraph.text, fact["keywords"]))
            if score:
                candidates.append((score, paragraph.text, EvidenceLocation(page=page.page, paragraph=index + 1)))
    if not candidates:
        return "全文未检索到能够满足该规则的问答记录。", None
    _, text, location = max(candidates, key=lambda item: item[0])
    return text, location


def analyze_document(document: ParsedDocument) -> list[ReviewResult]:
    """基于关键字的文档确定性审查（老版三现四流）。

    使用 RULES 中的关键字在文档中搜索匹配。
    不调用模型，结果仅供参考。

    Args:
        document: 已解析的笔录文档。

    Returns:
        审查结果列表（每个规则一条）。
    """
    results: list[ReviewResult] = []
    for rule in RULES:
        applicable = rule["scope"] == "base" or _includes_any(document.text, rule["triggers"])
        if not applicable:
            results.append(ReviewResult(
                ruleId=rule["id"], ruleName=rule["name"], category=rule["category"], group=rule["group"],
                status=RuleStatus.NOT_APPLICABLE, missingFacts=[], evidence="笔录未出现该条件规则的触发事实。",
                evidenceLocation=None, reason="当前笔录未触发该条件规则。", suggestedQuestion="", advisories=[],
                source="三现四流工作规则（本地样例分析，仅供演示）",
            ))
            continue

        matched = [fact for fact in rule["requiredFacts"] if _includes_any(document.text, fact["keywords"])]
        missing = [fact["label"] for fact in rule["requiredFacts"] if not _includes_any(document.text, fact["keywords"])]
        status = RuleStatus.COVERED if not missing else RuleStatus.MISSING if not matched else RuleStatus.INCOMPLETE
        evidence, location = _locate_evidence(document, rule)
        if status == RuleStatus.COVERED:
            reason = "笔录已覆盖该规则要求的全部强制字段。"
        elif status == RuleStatus.MISSING:
            reason = f"规则适用，但未检索到{'、'.join(missing)}等必要问答记录。"
        else:
            reason = f"已询问相关事项，但仍缺少{'、'.join(missing)}。"
        advisories = [
            f"可进一步核对：{hint['label']}"
            for hint in rule["referenceHints"]
            if not _includes_any(document.text, hint["keywords"])
        ]
        results.append(ReviewResult(
            ruleId=rule["id"], ruleName=rule["name"], category=rule["category"], group=rule["group"],
            status=status, missingFacts=missing, evidence=evidence, evidenceLocation=location, reason=reason,
            suggestedQuestion="" if status == RuleStatus.COVERED else rule["suggestedQuestion"],
            advisories=advisories, manualDecision=ManualDecision(),
            source="三现四流工作规则（本地样例分析，仅供演示）",
        ))
    return results
