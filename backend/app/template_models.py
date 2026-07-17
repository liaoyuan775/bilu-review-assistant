from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import RuleStatus


TemplateGroup = Literal[
    "META", "PROC", "CASE", "PREV", "RISK", "CASH", "TIME", "PRIV",
    "LEAD", "MOTIVE", "CONTACT", "MONEY", "OFFLINE", "EXTRA", "EVID",
]


class TemplateSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paragraphCount: int = Field(ge=1)
    questionCount: int = Field(ge=1)


class RuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    operator: Literal["equals", "not_equals", "exists", "truthy", "gt", "gte", "in"]
    value: Any = None


class RepeatEntityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entityType: str
    countPath: str | None = None
    requiredFields: list[str] = Field(min_length=1)


class ConsistencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["count_matches", "sum_matches", "rebate_net_loss", "chronology"]
    entityType: str | None = None
    entityField: str | None = None
    totalPath: str | None = None
    countPath: str | None = None
    leftPath: str | None = None
    rightPath: str | None = None
    resultPath: str | None = None
    earlierPath: str | None = None
    laterPath: str | None = None


class TemplateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleId: str
    name: str
    group: TemplateGroup
    sourceParagraphs: list[int] = Field(min_length=1)
    sourceMarker: str
    sourceKind: Literal["question", "structural"]
    scope: Literal["common", "conditional", "structural", "repeated"]
    appliesWhen: RuleCondition | None = None
    requiredFields: list[str] = Field(min_length=1)
    repeatEntity: RepeatEntityRule | None = None
    consistencyChecks: list[ConsistencyCheck] = Field(default_factory=list)
    suggestedQuestion: str
    severity: Literal["high", "medium", "low"]


class TemplateRuleCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    source: TemplateSource
    rules: list[TemplateRule] = Field(min_length=1)


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    clarity: Literal["clear", "unclear", "unknown", "missing"] = "missing"
    evidenceAnchorIds: list[str] = Field(default_factory=list)
    sourceConfidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entityType: str
    fields: dict[str, ExtractedFact] = Field(default_factory=dict)


class CaseExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    entities: dict[str, list[ExtractedEntity]] = Field(default_factory=dict)
    failedDomains: list[str] = Field(default_factory=list)


class TemplateReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleId: str
    ruleName: str
    group: TemplateGroup
    status: RuleStatus
    missingFields: list[str] = Field(default_factory=list)
    reason: str
    anchorIds: list[str] = Field(default_factory=list)
    suggestedQuestion: str
    severity: Literal["high", "medium", "low"]

