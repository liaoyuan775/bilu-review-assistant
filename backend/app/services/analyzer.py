from app.data import RULES
from app.models import EvidenceLocation, ManualDecision, ParsedDocument, ReviewResult, RuleStatus


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
    """Deterministic fixture analyzer used only by explicit local demo mode."""
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
