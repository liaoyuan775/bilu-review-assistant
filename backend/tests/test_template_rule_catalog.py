from app.data.rules import TEMPLATE_RULE_CATALOG, TEMPLATE_RULES


EXPECTED_GROUPS = {
    "META", "PROC", "CASE", "PREV", "RISK", "CASH", "TIME", "PRIV",
    "LEAD", "MOTIVE", "CONTACT", "MONEY", "OFFLINE", "EXTRA", "EVID",
}
EXPECTED_QUESTION_PARAGRAPHS = {
    13, 14, 16, 18, 20, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44,
    46, 48, 50, 53, 55, 57, 87, 89, 98, 100, 102, 104, 125, 137, 139,
    141, 143,
}


def test_catalog_has_versioned_source_metadata_and_unique_rules():
    assert TEMPLATE_RULE_CATALOG.version
    assert TEMPLATE_RULE_CATALOG.source.document == "询问笔录模版(1).docx"
    assert TEMPLATE_RULE_CATALOG.source.sha256 == "c37c38663c282a8acd6f4ca2e10e609c517f64c33895c73843a0b4f6dbdee329"
    assert TEMPLATE_RULE_CATALOG.source.paragraphCount == 144
    assert TEMPLATE_RULE_CATALOG.source.questionCount == 33
    assert len({rule.ruleId for rule in TEMPLATE_RULES}) == len(TEMPLATE_RULES)
    assert len({rule.sourceMarker for rule in TEMPLATE_RULES}) == len(TEMPLATE_RULES)


def test_every_template_question_and_structural_item_is_source_backed():
    question_rules = [rule for rule in TEMPLATE_RULES if rule.sourceKind == "question"]
    structural_rules = [rule for rule in TEMPLATE_RULES if rule.sourceKind == "structural"]

    assert len(question_rules) == 33
    assert {rule.sourceParagraphs[0] for rule in question_rules} == EXPECTED_QUESTION_PARAGRAPHS
    assert structural_rules
    assert all(rule.sourceParagraphs for rule in TEMPLATE_RULES)
    assert all(1 <= paragraph <= 144 for rule in TEMPLATE_RULES for paragraph in rule.sourceParagraphs)


def test_catalog_uses_valid_groups_fields_and_conditions():
    assert {rule.group for rule in TEMPLATE_RULES} == EXPECTED_GROUPS
    assert all(rule.requiredFields for rule in TEMPLATE_RULES)
    assert all(rule.suggestedQuestion.strip() for rule in TEMPLATE_RULES)

    for rule in TEMPLATE_RULES:
        assert len(rule.requiredFields) == len(set(rule.requiredFields))
        if rule.appliesWhen is not None:
            assert rule.scope == "conditional"
            assert rule.appliesWhen.path
        if rule.repeatEntity is not None:
            assert rule.repeatEntity.entityType
            assert rule.repeatEntity.requiredFields

