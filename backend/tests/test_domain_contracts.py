from pathlib import Path

from app.core.models import ParsedDocument
from app.data.domain_contracts import (
    DOMAIN_CONTRACTS,
    DOMAIN_ENTITY_APPLICABILITY,
    DOMAIN_ENTITY_FIELDS,
    DOMAIN_FACT_PATHS,
    DOMAIN_ORDER,
    ENTITY_COUNT_PATHS,
    catalog_paths_from_rules,
)
from app.data.rules import TEMPLATE_RULES
from app.review.domain_contract_rendering import render_domain_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompt-templates" / "domains"
DOMAIN_TEMPLATE_SECTIONS = (
    "【本域目标】",
    "【包含与排除】",
    "【clarity 判定】",
    "【字段与实体规则】",
    "【禁止推断】",
)
DOMAIN_UNIQUE_GUARDS = {
    "header_procedure": "不得从签名存在推断程序告知已经完成",
    "case_timeline": "案发地点按完整地点一次抽取",
    "contact_channels": "不得从存在电话号码推断使用过聊天软件",
    "risk_and_evidence": "不得从发生过通话推断存在录音",
    "online_money": "不得从总损失反推转账笔数或逐笔金额",
    "offline_delivery": "不得从取现推断现金已经交付",
}


def _empty_document() -> ParsedDocument:
    return ParsedDocument(
        name="提示词结构测试.docx",
        format="DOCX",
        pageCount=0,
        pages=[],
        text="",
        sizeLabel="0 KB",
    )


def test_six_domain_contracts_load():
    assert tuple(DOMAIN_CONTRACTS) == DOMAIN_ORDER
    assert set(DOMAIN_CONTRACTS) == {
        "header_procedure",
        "case_timeline",
        "contact_channels",
        "risk_and_evidence",
        "online_money",
        "offline_delivery",
    }


def test_domain_prompt_files_are_complete_semantic_templates():
    for domain in DOMAIN_ORDER:
        text = (PROMPT_ROOT / f"{domain.replace('_', '-')}.txt").read_text(encoding="utf-8")
        for section in DOMAIN_TEMPLATE_SECTIONS:
            assert section in text, f"{domain} missing {section}"
        assert DOMAIN_UNIQUE_GUARDS[domain] in text


def test_rendered_prompt_contains_only_its_domain_semantic_guard():
    document = _empty_document()
    for domain in DOMAIN_ORDER:
        prompt = render_domain_prompt(document, DOMAIN_CONTRACTS[domain])
        assert DOMAIN_UNIQUE_GUARDS[domain] in prompt
        assert prompt.count("clarity 只能是 clear、unclear、unknown、missing") == 1
        for other_domain, guard in DOMAIN_UNIQUE_GUARDS.items():
            if other_domain != domain:
                assert guard not in prompt


def test_model_fact_contract_is_reduced_without_reducing_rule_count():
    assert len(TEMPLATE_RULES) == 34
    assert sum(len(paths) for paths in DOMAIN_FACT_PATHS.values()) <= 80


def test_contracts_cover_catalog_paths_exactly_once():
    configured = [
        path
        for contract in DOMAIN_CONTRACTS.values()
        for path in contract.facts
    ]
    assert len(configured) == len(set(configured))
    assert set(configured) == catalog_paths_from_rules()
    assert DOMAIN_FACT_PATHS == {
        domain: tuple(contract.facts)
        for domain, contract in DOMAIN_CONTRACTS.items()
    }


def test_representative_types_are_specific():
    online = DOMAIN_CONTRACTS["online_money"]
    assert online.facts["online_money.used"].valueSchema.type == ("boolean", "null")
    assert online.facts["online_money.total"].valueSchema.type == ("number", "null")
    assert online.facts["online_money.transfer_count"].valueSchema.type == ("integer", "null")
    evidence = DOMAIN_CONTRACTS["risk_and_evidence"]
    assert evidence.facts["evidence.record_types"].valueSchema.type == ("array", "null")
    assert evidence.facts["evidence.record_types"].valueSchema.items == "string"


def test_incident_location_is_one_fact_used_by_case_and_time_rules():
    timeline = DOMAIN_CONTRACTS["case_timeline"]

    assert timeline.facts["timeline.incident_location"].valueSchema.type == ("string", "null")
    assert not {
        "timeline.incident_district",
        "timeline.incident_street",
        "timeline.incident_community",
    } & set(timeline.facts)

    rules = {rule.ruleId: rule for rule in TEMPLATE_RULES}
    assert "timeline.incident_location" in rules["CASE-001"].requiredFields
    assert rules["TIME-001"].requiredFields == [
        "timeline.incident_at",
        "timeline.incident_location",
    ]


def test_entity_relationships_are_derived_from_contracts():
    assert DOMAIN_ENTITY_FIELDS["online_money"]["transfers"] == (
        "time", "amount", "payment_method", "payer_account", "recipient_account", "transaction_id",
    )
    assert ENTITY_COUNT_PATHS["transfers"] == "online_money.transfer_count"
    assert ENTITY_COUNT_PATHS["withdrawals"] == "cash.withdrawal_count"
    assert DOMAIN_ENTITY_APPLICABILITY == {
        "online_money": "online_money.used",
        "offline_delivery": "offline.used",
    }
