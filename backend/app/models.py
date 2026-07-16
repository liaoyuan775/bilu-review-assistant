from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ReviewMode(StrEnum):
    QWEN = "qwen"
    LOCAL = "local"


class TaskStatus(StrEnum):
    UPLOADING = "uploading"
    PARSING = "parsing"
    RECOGNIZING = "recognizing"
    CHECKING = "checking"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(StrEnum):
    NATIVE_TEXT = "native_text"
    TABLE = "table"
    VISION = "vision"


class RuleStatus(StrEnum):
    COVERED = "covered"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"


class ManualStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SUPPLEMENTED = "supplemented"
    IGNORED = "ignored"


class QwenHealth(BaseModel):
    configured: bool
    reachable: bool
    model: str | None


class HealthResponse(BaseModel):
    ok: bool
    qwen: QwenHealth
    ruleCount: int


class RuleSummary(BaseModel):
    id: str
    name: str
    category: str
    group: str
    scope: str
    requiredFacts: list[str]
    source: str


class RuleListResponse(BaseModel):
    rules: list[RuleSummary]


class DemoSummary(BaseModel):
    id: str
    name: str
    pageCount: int
    intent: str


class DemoListResponse(BaseModel):
    demos: list[DemoSummary]


class CreateTaskResponse(BaseModel):
    taskId: str
    status: TaskStatus


class DocumentParagraph(BaseModel):
    text: str
    sourceType: SourceType
    confidence: float | None = Field(default=None, ge=0, le=1)


class DocumentPage(BaseModel):
    page: int
    paragraphs: list[DocumentParagraph]


class ParsedDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    format: Literal["DOCX", "PDF", "SAMPLE"]
    pageCount: int
    pages: list[DocumentPage]
    text: str
    sizeLabel: str


class EvidenceLocation(BaseModel):
    page: int
    paragraph: int


class ModelEvidenceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)


class ModelRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factCoverage: dict[str, Literal["covered", "missing", "unknown"]]
    evidenceLocation: ModelEvidenceLocation | None
    reason: str
    suggestedQuestion: str
    advisories: list[str]


class ModelReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    present_001: ModelRuleResult = Field(alias="PRESENT-001")
    present_002: ModelRuleResult = Field(alias="PRESENT-002")
    present_003: ModelRuleResult = Field(alias="PRESENT-003")
    flow_001: ModelRuleResult = Field(alias="FLOW-001")
    flow_002: ModelRuleResult = Field(alias="FLOW-002")
    flow_003: ModelRuleResult = Field(alias="FLOW-003")
    flow_004: ModelRuleResult = Field(alias="FLOW-004")

    def as_keyed_payload(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class ManualDecision(BaseModel):
    status: ManualStatus = ManualStatus.PENDING
    reason: str = ""


class ReviewResult(BaseModel):
    ruleId: str
    ruleName: str
    category: str
    group: str
    status: RuleStatus
    missingFacts: list[str]
    evidence: str
    evidenceLocation: EvidenceLocation | None
    reason: str
    suggestedQuestion: str
    advisories: list[str] = Field(default_factory=list)
    manualDecision: ManualDecision = Field(default_factory=ManualDecision)
    source: str


class DecisionResponse(BaseModel):
    result: ReviewResult


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: ReviewMode
    status: TaskStatus = TaskStatus.PARSING
    document: ParsedDocument | None = None
    results: list[ReviewResult] = Field(default_factory=list)
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)
    errorCode: str | None = None
    errorMessage: str | None = None


class DecisionRequest(BaseModel):
    status: ManualStatus
    reason: str = ""
