from app.data.domain_contracts import (
    DOMAIN_CONTRACTS,
    DOMAIN_ENTITY_APPLICABILITY,
    DOMAIN_ENTITY_FIELDS,
    DOMAIN_FACT_PATHS,
    DOMAIN_ORDER,
    ENTITY_COUNT_PATHS,
    catalog_paths_from_rules,
)


def test_all_seven_domain_contracts_load():
    assert tuple(DOMAIN_CONTRACTS) == DOMAIN_ORDER
    assert set(DOMAIN_CONTRACTS) == {
        "header_procedure",
        "case_timeline",
        "contact_channels",
        "risk_and_evidence",
        "online_money",
        "offline_delivery",
        "special_scenarios",
    }


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
