from app.models import RuleStatus
from app.services.template_rule_engine import evaluate_template_rules
from app.template_models import (
    CaseExtraction,
    ConsistencyCheck,
    ExtractedEntity,
    ExtractedFact,
    RepeatEntityRule,
    RuleCondition,
    TemplateRule,
)


def _fact(value=None, clarity="clear", *anchors: str) -> ExtractedFact:
    return ExtractedFact(value=value, clarity=clarity, evidenceAnchorIds=list(anchors))


def _rule(
    *required_fields: str,
    scope: str = "common",
    condition: RuleCondition | None = None,
    repeat: RepeatEntityRule | None = None,
    checks: list[ConsistencyCheck] | None = None,
) -> TemplateRule:
    return TemplateRule(
        ruleId="TEST-001",
        name="测试规则",
        group="CASE",
        sourceParagraphs=[20],
        sourceMarker="p020-q1",
        sourceKind="question",
        scope=scope,
        appliesWhen=condition,
        requiredFields=list(required_fields),
        repeatEntity=repeat,
        consistencyChecks=checks or [],
        suggestedQuestion="请补充测试事实。",
        severity="high",
    )


def test_common_rule_with_no_required_facts_is_missing():
    issue = evaluate_template_rules(
        CaseExtraction(),
        [_rule("case.summary", "case.location")],
    )[0]

    assert issue.status == RuleStatus.MISSING
    assert issue.missingFields == ["case.summary", "case.location"]


def test_false_conditional_path_is_not_applicable():
    issue = evaluate_template_rules(
        CaseExtraction(facts={"offline.used": _fact(False, "clear", "a1")}),
        [_rule(
            "offline.delivery_method",
            scope="conditional",
            condition=RuleCondition(path="offline.used", operator="equals", value=True),
        )],
    )[0]

    assert issue.status == RuleStatus.NOT_APPLICABLE
    assert issue.missingFields == []
    assert issue.anchorIds == ["a1"]


def test_unknown_answer_is_incomplete_not_missing():
    issue = evaluate_template_rules(
        CaseExtraction(facts={"money.total": _fact(None, "unknown", "a1")}),
        [_rule("money.total")],
    )[0]

    assert issue.status == RuleStatus.INCOMPLETE
    assert issue.missingFields == ["money.total"]


def test_repeated_entity_count_mismatch_is_inconsistent():
    issue = evaluate_template_rules(
        CaseExtraction(
            facts={"money.transfer_count": _fact(2, "clear", "count")},
            entities={
                "transfers": [ExtractedEntity(
                    id="transfer-1",
                    entityType="transfers",
                    fields={"amount": _fact(100, "clear", "t1")},
                )],
            },
        ),
        [_rule(
            "money.transfer_count",
            repeat=RepeatEntityRule(
                entityType="transfers",
                countPath="money.transfer_count",
                requiredFields=["amount"],
            ),
        )],
    )[0]

    assert issue.status == RuleStatus.INCONSISTENT
    assert "transfers.count" in issue.missingFields


def test_transaction_sum_mismatch_is_inconsistent():
    extraction = CaseExtraction(
        facts={"money.total": _fact(250, "clear", "total")},
        entities={
            "transfers": [
                ExtractedEntity(id="t1", entityType="transfers", fields={"amount": _fact(100)}),
                ExtractedEntity(id="t2", entityType="transfers", fields={"amount": _fact(100)}),
            ],
        },
    )
    rule = _rule(
        "money.total",
        checks=[ConsistencyCheck(
            type="sum_matches",
            entityType="transfers",
            entityField="amount",
            totalPath="money.total",
        )],
    )

    issue = evaluate_template_rules(extraction, [rule])[0]

    assert issue.status == RuleStatus.INCONSISTENT
    assert "money.total" in issue.missingFields


def test_rebate_and_net_loss_mismatch_is_inconsistent():
    extraction = CaseExtraction(facts={
        "money.gross_loss": _fact(1000),
        "money.rebate_total": _fact(100),
        "money.net_loss": _fact(950),
    })
    rule = _rule(
        "money.gross_loss",
        "money.rebate_total",
        "money.net_loss",
        checks=[ConsistencyCheck(
            type="rebate_net_loss",
            leftPath="money.gross_loss",
            rightPath="money.rebate_total",
            resultPath="money.net_loss",
        )],
    )

    issue = evaluate_template_rules(extraction, [rule])[0]

    assert issue.status == RuleStatus.INCONSISTENT
    assert "money.net_loss" in issue.missingFields


def test_chronological_contradiction_is_inconsistent():
    extraction = CaseExtraction(facts={
        "timeline.first_contact_at": _fact("2026-07-18T10:00:00"),
        "timeline.transfer_at": _fact("2026-07-18T09:00:00"),
    })
    rule = _rule(
        "timeline.first_contact_at",
        "timeline.transfer_at",
        checks=[ConsistencyCheck(
            type="chronology",
            earlierPath="timeline.first_contact_at",
            laterPath="timeline.transfer_at",
        )],
    )

    issue = evaluate_template_rules(extraction, [rule])[0]

    assert issue.status == RuleStatus.INCONSISTENT
    assert "timeline.transfer_at" in issue.missingFields
