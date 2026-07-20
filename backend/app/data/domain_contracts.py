from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.data.rules import TEMPLATE_RULES


ROOT = Path(__file__).resolve().parent.parent.parent
DOMAIN_ORDER = (
    "header_procedure",
    "case_timeline",
    "contact_channels",
    "risk_and_evidence",
    "online_money",
    "offline_delivery",
    "special_scenarios",
)

ValueType = Literal["string", "number", "integer", "boolean", "array", "null"]


class ValueSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: tuple[ValueType, ...]
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[str | int | float | bool, ...] | None = None
    items: Literal["string"] | None = None
    minItems: int | None = Field(default=None, ge=0)
    maxItems: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> "ValueSchema":
        if not self.type or len(set(self.type)) != len(self.type):
            raise ValueError("valueSchema.type must contain unique types")
        if "array" in self.type:
            if self.items != "string":
                raise ValueError("array valueSchema requires items=string")
        elif self.items is not None or self.minItems is not None or self.maxItems is not None:
            raise ValueError("scalar valueSchema cannot declare array constraints")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("valueSchema minimum cannot exceed maximum")
        if self.minItems is not None and self.maxItems is not None and self.minItems > self.maxItems:
            raise ValueError("valueSchema minItems cannot exceed maxItems")
        if self.enum is not None and len({(type(value).__name__, value) for value in self.enum}) != len(self.enum):
            raise ValueError("valueSchema enum values must be unique")
        return self


class FactContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1)
    valueSchema: ValueSchema


class EntityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1)
    applicabilityPath: str | None = None
    countPath: str | None = None
    fields: dict[str, FactContract]


class DomainContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str
    title: str = Field(min_length=1)
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    facts: dict[str, FactContract]
    entities: dict[str, EntityContract]


def catalog_paths_from_rules() -> set[str]:
    paths: set[str] = set()
    for rule in TEMPLATE_RULES:
        paths.update(rule.requiredFields)
        if rule.appliesWhen:
            paths.add(rule.appliesWhen.path)
        if rule.repeatEntity and rule.repeatEntity.countPath:
            paths.add(rule.repeatEntity.countPath)
        for check in rule.consistencyChecks:
            for value in (
                check.totalPath,
                check.countPath,
                check.leftPath,
                check.rightPath,
                check.resultPath,
                check.earlierPath,
                check.laterPath,
            ):
                if value:
                    paths.add(value)
    paths.update({"special.gambling_related", "special.ecommerce_logistics_impersonation"})
    return paths


def _validate_contract_relationships(contracts: dict[str, DomainContract]) -> None:
    configured = [path for contract in contracts.values() for path in contract.facts]
    if len(configured) != len(set(configured)):
        raise ValueError("domain contracts contain duplicate fact paths")
    expected = catalog_paths_from_rules()
    if set(configured) != expected:
        missing = sorted(expected - set(configured))
        extra = sorted(set(configured) - expected)
        raise ValueError(f"domain contract fact coverage mismatch: missing={missing}, extra={extra}")

    entities = {
        entity_type: (contract, entity)
        for contract in contracts.values()
        for entity_type, entity in contract.entities.items()
    }
    for rule in TEMPLATE_RULES:
        repeated = rule.repeatEntity
        if repeated is None:
            continue
        if repeated.entityType not in entities:
            raise ValueError(f"missing entity contract: {repeated.entityType}")
        contract, entity = entities[repeated.entityType]
        if entity.countPath != repeated.countPath:
            raise ValueError(f"entity countPath mismatch: {repeated.entityType}")
        if tuple(entity.fields) != tuple(repeated.requiredFields):
            raise ValueError(f"entity fields mismatch: {repeated.entityType}")
        if entity.countPath not in contract.facts:
            raise ValueError(f"entity countPath must belong to its domain: {repeated.entityType}")

    for contract in contracts.values():
        applicability_paths = {
            entity.applicabilityPath
            for entity in contract.entities.values()
            if entity.applicabilityPath is not None
        }
        if len(applicability_paths) > 1:
            raise ValueError(f"domain entities use conflicting applicability paths: {contract.domain}")
        if not applicability_paths.issubset(contract.facts):
            raise ValueError(f"entity applicabilityPath must belong to its domain: {contract.domain}")


def load_domain_contracts(root: Path) -> dict[str, DomainContract]:
    expected_names = {f"{domain}.json" for domain in DOMAIN_ORDER}
    actual_names = {path.name for path in root.glob("*.json")}
    if actual_names != expected_names:
        raise ValueError(
            f"domain contract files mismatch: missing={sorted(expected_names - actual_names)}, "
            f"extra={sorted(actual_names - expected_names)}"
        )
    contracts: dict[str, DomainContract] = {}
    for domain in DOMAIN_ORDER:
        contract = DomainContract.model_validate_json(
            (root / f"{domain}.json").read_text(encoding="utf-8")
        )
        if contract.domain != domain:
            raise ValueError(f"domain contract name mismatch: expected={domain}, actual={contract.domain}")
        contracts[domain] = contract
    _validate_contract_relationships(contracts)
    return contracts


DOMAIN_CONTRACTS = load_domain_contracts(ROOT / "domain-contracts")
DOMAIN_FACT_PATHS = {
    domain: tuple(contract.facts)
    for domain, contract in DOMAIN_CONTRACTS.items()
}
DOMAIN_ENTITY_FIELDS = {
    domain: {
        entity_type: tuple(entity.fields)
        for entity_type, entity in contract.entities.items()
    }
    for domain, contract in DOMAIN_CONTRACTS.items()
}
ENTITY_COUNT_PATHS = {
    entity_type: entity.countPath
    for contract in DOMAIN_CONTRACTS.values()
    for entity_type, entity in contract.entities.items()
    if entity.countPath is not None
}
DOMAIN_ENTITY_APPLICABILITY = {
    domain: next(
        (
            entity.applicabilityPath
            for entity in contract.entities.values()
            if entity.applicabilityPath is not None
        ),
        None,
    )
    for domain, contract in DOMAIN_CONTRACTS.items()
}
DOMAIN_ENTITY_APPLICABILITY = {
    domain: path
    for domain, path in DOMAIN_ENTITY_APPLICABILITY.items()
    if path is not None
}
