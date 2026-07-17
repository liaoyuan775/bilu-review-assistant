from app.data import RULES
from app.models import EvidenceLocation, ManualDecision, ParsedDocument, ReviewResult, RuleStatus


MOCK_SOURCE = "模拟结果，仅用于功能演示；证据摘自当前演示文档。"


def _find_evidence(document: ParsedDocument, rule: dict) -> tuple[str, list[EvidenceLocation]]:
    keywords = {
        keyword.lower()
        for fact in rule["requiredFacts"]
        for keyword in fact["keywords"]
    }
    candidates: list[tuple[int, int, int, str]] = []
    for page in document.pages:
        for paragraph_index, paragraph in enumerate(page.paragraphs, start=1):
            text = paragraph.text.strip()
            score = sum(keyword in text.lower() for keyword in keywords)
            if text and score:
                candidates.append((score, page.page, paragraph_index, text))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected = candidates[:3]
    if not selected:
        for page in document.pages:
            if page.paragraphs:
                selected = [(0, page.page, 1, page.paragraphs[0].text.strip())]
                break

    locations = [EvidenceLocation(page=page, paragraph=paragraph) for _, page, paragraph, _ in selected]
    evidence = "\n".join(text for _, _, _, text in selected)
    return evidence, locations


def build_mock_review(document: ParsedDocument) -> list[ReviewResult]:
    """基于当前规则和真实 DOCX 段落构造一组明确标识的快速演示结果。"""
    results: list[ReviewResult] = []
    for rule in RULES:
        evidence, locations = _find_evidence(document, rule)
        is_incomplete = rule["id"] == "PRESENT-002"
        results.append(ReviewResult(
            ruleId=rule["id"],
            ruleName=rule["name"],
            category=rule["category"],
            group=rule["group"],
            status=RuleStatus.INCOMPLETE if is_incomplete else RuleStatus.COVERED,
            missingFacts=["提取或查验情况"] if is_incomplete else [],
            evidence=evidence,
            evidenceLocation=locations[0] if locations else None,
            evidenceLocations=locations,
            reason=(
                "演示文档已说明涉案载体及保存状态，但未明确记录提取或查验情况。"
                if is_incomplete
                else "演示文档已覆盖该规则要求的主要事实。"
            ),
            suggestedQuestion=rule["suggestedQuestion"] if is_incomplete else "",
            advisories=[],
            manualDecision=ManualDecision(),
            source=MOCK_SOURCE,
        ))
    return results
