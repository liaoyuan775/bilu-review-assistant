from app.core.models import ManualDecision, ManualStatus, ReviewResult, RuleStatus
from app.reporting.presentation import fact_label, localize_fact_paths, sort_review_results


def _result(
    rule_id: str,
    status: RuleStatus,
    *,
    severity: str = "medium",
    manual_status: ManualStatus = ManualStatus.PENDING,
    reason: str = "",
) -> ReviewResult:
    return ReviewResult(
        ruleId=rule_id,
        status=status,
        severity=severity,
        manualDecision=ManualDecision(status=manual_status, reason=reason),
    )


def test_fact_labels_cover_static_and_repeated_fields():
    assert fact_label("money.net_loss") == "净损失"
    assert fact_label("transfer_001.transaction_id") == "第1笔转账交易流水号"
    assert fact_label("withdrawals.count") == "取款记录数量"
    assert fact_label("unknown.path") == "unknown.path"


def test_localize_fact_paths_replaces_paths_inside_reason():
    assert localize_fact_paths(
        "缺少 money.net_loss、transfer_001.transaction_id。"
    ) == "缺少 净损失、第1笔转账交易流水号。"


def test_result_order_is_open_closed_not_applicable_covered():
    covered = _result("OK", RuleStatus.COVERED)
    not_applicable = _result("NA", RuleStatus.NOT_APPLICABLE)
    closed_issue = _result(
        "CLOSED",
        RuleStatus.MISSING,
        severity="high",
        manual_status=ManualStatus.RESOLVED,
        reason="已核实",
    )
    low_open = _result("LOW", RuleStatus.INCOMPLETE, severity="low")
    high_open = _result("HIGH", RuleStatus.MISSING, severity="high")

    ordered = sort_review_results([
        covered,
        not_applicable,
        closed_issue,
        low_open,
        high_open,
    ])

    assert [item.ruleId for item in ordered] == ["HIGH", "LOW", "CLOSED", "NA", "OK"]
