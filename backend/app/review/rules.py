"""
确定性规则引擎 — 基于提取事实的模板规则评估。

职责边界：
- 这是一个纯 Python 的确定性规则引擎，不调用任何外部模型。
- 输入是 CaseExtraction（从模型提取的结构化事实），
- 输出是 TemplateReviewIssue 列表（每项对应一条模板规则的评估结果）。

评估逻辑：
1. 条件判断（appliesWhen）：检查规则是否适用于当前案件。
   - 如果明确不适用 → NOT_APPLICABLE
   - 如果无法判断 → NEEDS_MANUAL_REVIEW
   - 如果适用 → 继续检查事实覆盖情况
2. 事实覆盖检查（requiredFields）：检查规则要求的强制事实是否已提取。
3. 重复实体检查（repeatEntity）：验证实体数量、字段完整性。
4. 一致性检查（consistencyChecks）：金额合计、时间顺序、数量匹配等。

设计原则：
- 所有判断都是确定性的：相同输入 → 相同输出。
- 不处理模型的"幻觉"问题（那是 qwen.py 的工作）。
- 只使用 extraction 中的数据，不直接访问原始文档文本。

依赖关系：
- core/models.py: RuleStatus 枚举。
- core/template_models.py: 模板模型（CaseExtraction、TemplateRule 等）。
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.models import RuleStatus
from app.core.template_models import (
    CaseExtraction,
    ConsistencyCheck,
    ExtractedFact,
    TemplateReviewIssue,
    TemplateRule,
)


def _anchors(*facts: ExtractedFact | None) -> list[str]:
    """收集多个事实的证据锚点 ID，去重后返回。"""
    values: list[str] = []
    for fact in facts:
        if fact is None:
            continue
        for anchor in fact.evidenceAnchorIds:
            if anchor not in values:
                values.append(anchor)
    return values


def _has_value(fact: ExtractedFact | None) -> bool:
    """检查事实是否有非空值。"""
    return fact is not None and fact.value not in (None, "", [])


def _is_clear(fact: ExtractedFact | None) -> bool:
    """检查事实是否清晰（有值且 clarity=clear）。"""
    return _has_value(fact) and fact.clarity == "clear"


def _boolean_value(value: Any) -> bool | None:
    """将各种形式的布尔值标准化为 Python bool 或 None。

    支持中英文布尔表示：
    - True: "true", "yes", "是", "有", "已发生" 等
    - False: "false", "no", "否", "无", "未发生" 等
    - 其他: None（无法判断）
    """
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
    """评估规则的触发条件（appliesWhen）。

    Returns:
        (result, anchors) 二元组：
        - result: True=适用, False=不适用, None=无法判断
        - anchors: 条件判断所依赖的段落锚点
    """
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
    """将事实的值转为 Decimal 类型（用于数值比较）。"""
    if not _is_clear(fact):
        return None
    try:
        return Decimal(str(fact.value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _datetime(fact: ExtractedFact | None) -> datetime | None:
    """将事实的值转为 datetime 类型（用于时间比较）。"""
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
    """执行单条一致性检查。

    检查类型：
    - sum_matches: 实体的某字段之和是否等于总数字段
    - rebate_net_loss: 损失 = 总转出 - 返利
    - chronology: 时间先后顺序
    - count_matches: 实体数量与计数字段一致

    Returns:
        (failed_field, anchors) 二元组：
        - failed_field: 检查失败的字段名，None 表示通过
        - anchors: 涉及的段落锚点
    """
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
    """根据规则状态生成人类可读的判断理由。"""
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
    """评估所有模板规则，生成审查问题列表。

    这是规则引擎的主入口函数。对每条规则：
    1. 判断是否适用。
    2. 如果适用，检查 requiredFields 的覆盖情况。
    3. 检查重复实体的数量和字段完整性。
    4. 执行一致性检查。

    Args:
        extraction: 已提取的结构化事实与实体。
        rules:      要评估的规则列表。

    Returns:
        每条规则的评估结果（TemplateReviewIssue 列表）。
    """
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
