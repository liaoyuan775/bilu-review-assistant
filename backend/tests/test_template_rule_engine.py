from app.core.models import RuleStatus
from app.review.rules import evaluate_template_rules
from app.core.template_models import (
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
    explicit_answer_fields: list[str] | None = None,
    advisory_fields: list[str] | None = None,
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
        explicitAnswerFields=explicit_answer_fields or [],
        advisoryFields=advisory_fields or [],
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


def test_asked_question_with_blank_answer_is_incomplete_not_missing():
    issue = evaluate_template_rules(
        CaseExtraction(),
        [_rule("procedure.recusal_requested")],
        question_states={"TEST-001": "blank"},
    )[0]

    assert issue.status == RuleStatus.INCOMPLETE
    assert issue.missingFields == ["procedure.recusal_requested"]


def test_clear_answer_can_cover_an_answer_presence_rule_when_model_misses_fact():
    rule = _rule("procedure.recusal_requested").model_copy(update={
        "answerPresenceSatisfies": True,
    })

    issue = evaluate_template_rules(
        CaseExtraction(),
        [rule],
        question_states={"TEST-001": "answered"},
    )[0]

    assert issue.status == RuleStatus.COVERED
    assert issue.missingFields == []


def test_unclear_answer_does_not_cover_an_answer_presence_rule():
    rule = _rule("procedure.recusal_requested").model_copy(update={
        "answerPresenceSatisfies": True,
    })

    issue = evaluate_template_rules(
        CaseExtraction(),
        [rule],
        question_states={"TEST-001": "unclear"},
    )[0]

    assert issue.status == RuleStatus.INCOMPLETE


def test_explicit_clear_null_answer_can_complete_a_rule():
    issue = evaluate_template_rules(
        CaseExtraction(facts={
            "procedure.rights_request": _fact(None, "clear", "rights-answer"),
        }),
        [_rule(
            "procedure.rights_request",
            explicit_answer_fields=["procedure.rights_request"],
        )],
    )[0]

    assert issue.status == RuleStatus.COVERED


def test_required_affirmative_value_rejects_a_clear_negative_answer():
    rule = _rule("procedure.statement_confirmed_true").model_copy(update={
        "requiredValues": {"procedure.statement_confirmed_true": True},
    })

    issue = evaluate_template_rules(
        CaseExtraction(facts={
            "procedure.statement_confirmed_true": _fact(False, "clear", "answer"),
        }),
        [rule],
    )[0]

    assert issue.status == RuleStatus.INCOMPLETE
    assert issue.missingFields == ["procedure.statement_confirmed_true"]


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


def test_boolean_condition_accepts_explicit_chinese_affirmative_answer():
    issue = evaluate_template_rules(
        CaseExtraction(facts={
            "offline.used": _fact("是，已明确发生或确认", "clear", "a1"),
            "offline.delivery_method": _fact("线下交付", "clear", "a2"),
        }),
        [_rule(
            "offline.delivery_method",
            scope="conditional",
            condition=RuleCondition(path="offline.used", operator="equals", value=True),
        )],
    )[0]

    assert issue.status == RuleStatus.COVERED


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


def test_explicit_numeric_value_still_participates_in_consistency_check_when_marked_unclear():
    extraction = CaseExtraction(facts={
        "money.gross_loss": _fact(36400),
        "money.rebate_total": _fact(0),
        "money.net_loss": _fact(30000, "unclear", "net-loss"),
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


def test_missing_advisory_entity_field_does_not_block_rule():
    extraction = CaseExtraction(
        facts={"money.transfer_count": _fact(1)},
        entities={
            "transfers": [ExtractedEntity(
                id="t1",
                entityType="transfers",
                fields={
                    "amount": _fact(100),
                    "transaction_id": _fact(None, "missing"),
                },
            )],
        },
    )
    rule = _rule(
        "money.transfer_count",
        repeat=RepeatEntityRule(
            entityType="transfers",
            countPath="money.transfer_count",
            requiredFields=["amount"],
            advisoryFields=["transaction_id"],
        ),
    )

    issue = evaluate_template_rules(extraction, [rule])[0]

    assert issue.status == RuleStatus.COVERED
    assert issue.advisories == ["t1.transaction_id"]


def test_missing_advisory_fact_does_not_block_rule():
    extraction = CaseExtraction(facts={
        "risk.payment_warning_received": _fact(False, "clear", "warning-answer"),
        "risk.payment_warning_channel": _fact(None, "missing"),
        "risk.payment_warning_content": _fact(None, "missing"),
    })
    rule = _rule(
        "risk.payment_warning_received",
        advisory_fields=["risk.payment_warning_channel", "risk.payment_warning_content"],
    )

    issue = evaluate_template_rules(extraction, [rule])[0]

    assert issue.status == RuleStatus.COVERED
    assert issue.advisories == ["risk.payment_warning_channel", "risk.payment_warning_content"]


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
