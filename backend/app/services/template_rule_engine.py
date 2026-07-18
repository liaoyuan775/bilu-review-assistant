from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models import RuleStatus
from app.template_models import (
    CaseExtraction,
    ConsistencyCheck,
    ExtractedFact,
    TemplateReviewIssue,
    TemplateRule,
)


def _anchors(*facts: ExtractedFact | None) -> list[str]:
    values: list[str] = []
    for fact in facts:
        if fact is None:
            continue
        for anchor in fact.evidenceAnchorIds:
            if anchor not in values:
                values.append(anchor)
    return values


def _has_value(fact: ExtractedFact | None) -> bool:
    return fact is not None and fact.value not in (None, "", [])


def _is_clear(fact: ExtractedFact | None) -> bool:
    return _has_value(fact) and fact.clarity == "clear"


def _boolean_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "是", "有", "已发生", "已确认"} or normalized.startswith(("是，", "是,", "是。")):
            return True
        if normalized in {"false", "no", "否", "无", "未发生", "未确认"} or normalized.startswith(("否，", "否,", "否。")):
            return False
    return None


def _condition_result(extraction: CaseExtraction, rule: TemplateRule) -> tuple[bool | None, list[str]]:
    condition = rule.appliesWhen
    if condition is None:
        return True, []
    fact = extraction.facts.get(condition.path)
    anchors = _anchors(fact)
    if fact is None or fact.clarity != "clear":
        return None, anchors
    value = fact.value
    if condition.operator == "exists":
        return _has_value(fact), anchors
    if condition.operator == "truthy":
        boolean = _boolean_value(value)
        return (boolean if boolean is not None else bool(value)), anchors
    if condition.operator == "equals":
        if isinstance(condition.value, bool):
            boolean = _boolean_value(value)
            if boolean is not None:
                return boolean == condition.value, anchors
        return value == condition.value, anchors
    if condition.operator == "not_equals":
        if isinstance(condition.value, bool):
            boolean = _boolean_value(value)
            if boolean is not None:
                return boolean != condition.value, anchors
        return value != condition.value, anchors
    if condition.operator == "in":
        return value in condition.value, anchors
    try:
        left = Decimal(str(value))
        right = Decimal(str(condition.value))
    except (InvalidOperation, TypeError, ValueError):
        return None, anchors
    if condition.operator == "gt":
        return left > right, anchors
    return left >= right, anchors


def _decimal(fact: ExtractedFact | None) -> Decimal | None:
    if not _is_clear(fact):
        return None
    try:
        return Decimal(str(fact.value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _datetime(fact: ExtractedFact | None) -> datetime | None:
    if not _is_clear(fact) or not isinstance(fact.value, str):
        return None
    try:
        return datetime.fromisoformat(fact.value)
    except ValueError:
        return None


def _check_consistency(
    extraction: CaseExtraction,
    check: ConsistencyCheck,
) -> tuple[str | None, list[str]]:
    if check.type == "sum_matches":
        entities = extraction.entities.get(check.entityType or "", [])
        values = [_decimal(entity.fields.get(check.entityField or "")) for entity in entities]
        total = _decimal(extraction.facts.get(check.totalPath or ""))
        if entities and total is not None and all(value is not None for value in values):
            if sum(value for value in values if value is not None) != total:
                return check.totalPath, _anchors(extraction.facts.get(check.totalPath or ""))
    elif check.type == "rebate_net_loss":
        left = _decimal(extraction.facts.get(check.leftPath or ""))
        right = _decimal(extraction.facts.get(check.rightPath or ""))
        result = _decimal(extraction.facts.get(check.resultPath or ""))
        if None not in (left, right, result) and left - right != result:
            return check.resultPath, _anchors(
                extraction.facts.get(check.leftPath or ""),
                extraction.facts.get(check.rightPath or ""),
                extraction.facts.get(check.resultPath or ""),
            )
    elif check.type == "chronology":
        earlier = _datetime(extraction.facts.get(check.earlierPath or ""))
        later = _datetime(extraction.facts.get(check.laterPath or ""))
        if earlier is not None and later is not None and earlier > later:
            return check.laterPath, _anchors(
                extraction.facts.get(check.earlierPath or ""),
                extraction.facts.get(check.laterPath or ""),
            )
    elif check.type == "count_matches":
        count = _decimal(extraction.facts.get(check.countPath or ""))
        entities = extraction.entities.get(check.entityType or "", [])
        if count is not None and count != len(entities):
            return f"{check.entityType}.count", _anchors(extraction.facts.get(check.countPath or ""))
    return None, []


def _reason(status: RuleStatus, fields: list[str]) -> str:
    joined = "、".join(fields)
    if status == RuleStatus.COVERED:
        return "适用规则所需事实明确，且确定性一致性校验通过。"
    if status == RuleStatus.NOT_APPLICABLE:
        return "已有明确事实证明当前条件未触发。"
    if status == RuleStatus.NEEDS_MANUAL_REVIEW:
        return f"无法可靠判断规则适用性，需要人工核对：{joined}。"
    if status == RuleStatus.INCONSISTENT:
        return f"已提取事实存在数量、金额或时间矛盾：{joined}。"
    if status == RuleStatus.MISSING:
        return f"未检索到规则要求的明确问答：{joined}。"
    return f"已询问相关事项，但答案不清或明细不足：{joined}。"


def evaluate_template_rules(
    extraction: CaseExtraction,
    rules: list[TemplateRule],
) -> list[TemplateReviewIssue]:
    issues: list[TemplateReviewIssue] = []
    for rule in rules:
        applies, condition_anchors = _condition_result(extraction, rule)
        if applies is False:
            issues.append(TemplateReviewIssue(
                ruleId=rule.ruleId,
                ruleName=rule.name,
                group=rule.group,
                status=RuleStatus.NOT_APPLICABLE,
                reason=_reason(RuleStatus.NOT_APPLICABLE, []),
                anchorIds=condition_anchors,
                suggestedQuestion="",
                severity=rule.severity,
            ))
            continue
        if applies is None:
            fields = [rule.appliesWhen.path] if rule.appliesWhen else []
            issues.append(TemplateReviewIssue(
                ruleId=rule.ruleId,
                ruleName=rule.name,
                group=rule.group,
                status=RuleStatus.NEEDS_MANUAL_REVIEW,
                missingFields=fields,
                reason=_reason(RuleStatus.NEEDS_MANUAL_REVIEW, fields),
                anchorIds=condition_anchors,
                suggestedQuestion=rule.suggestedQuestion,
                severity=rule.severity,
            ))
            continue

        missing: list[str] = []
        unclear: list[str] = []
        clear_count = 0
        anchor_ids = list(condition_anchors)
        for path in rule.requiredFields:
            fact = extraction.facts.get(path)
            for anchor in _anchors(fact):
                if anchor not in anchor_ids:
                    anchor_ids.append(anchor)
            if fact is None or fact.clarity == "missing":
                missing.append(path)
            elif fact.clarity != "clear":
                unclear.append(path)
            elif not _has_value(fact):
                missing.append(path)
            else:
                clear_count += 1

        inconsistent: list[str] = []
        if rule.repeatEntity is not None:
            repeated = rule.repeatEntity
            entities = extraction.entities.get(repeated.entityType, [])
            if repeated.countPath:
                count = _decimal(extraction.facts.get(repeated.countPath))
                if count is not None and count != len(entities):
                    inconsistent.append(f"{repeated.entityType}.count")
            for entity in entities:
                for field_name in repeated.requiredFields:
                    fact = entity.fields.get(field_name)
                    for anchor in _anchors(fact):
                        if anchor not in anchor_ids:
                            anchor_ids.append(anchor)
                    if not _is_clear(fact):
                        unclear.append(f"{entity.id}.{field_name}")

        for check in rule.consistencyChecks:
            field, check_anchors = _check_consistency(extraction, check)
            if field and field not in inconsistent:
                inconsistent.append(field)
            for anchor in check_anchors:
                if anchor not in anchor_ids:
                    anchor_ids.append(anchor)

        if inconsistent:
            status = RuleStatus.INCONSISTENT
            fields = [*missing, *unclear, *inconsistent]
        elif missing:
            status = RuleStatus.MISSING if clear_count == 0 and not unclear else RuleStatus.INCOMPLETE
            fields = [*missing, *unclear]
        elif unclear:
            status = RuleStatus.INCOMPLETE
            fields = unclear
        else:
            status = RuleStatus.COVERED
            fields = []
        issues.append(TemplateReviewIssue(
            ruleId=rule.ruleId,
            ruleName=rule.name,
            group=rule.group,
            status=status,
            missingFields=list(dict.fromkeys(fields)),
            reason=_reason(status, list(dict.fromkeys(fields))),
            anchorIds=anchor_ids,
            suggestedQuestion="" if status == RuleStatus.COVERED else rule.suggestedQuestion,
            severity=rule.severity,
        ))
    return issues
