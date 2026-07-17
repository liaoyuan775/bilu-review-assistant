"""
数据模型 — 定义系统全部 Pydantic 模型、枚举与 API 响应结构。

分层说明：
- 枚举（StrEnum）: 状态机常量，确保状态流转在编译期可追踪。
- 内部模型: 文档结构（ParsedDocument）、被害人信息（VictimProfile）、
  证据位置（EvidenceLocation）等核心领域对象。
- 模型通信模型（Model*）: 用于 Qwen 模型 JSON Schema 的严格校验，
  extra="forbid" 确保不会出现未声明字段。
- API 响应模型: 与 HTTP 接口一一对应，保障 OpenAPI 文档的一致性。
- 元信息模型: ReviewTimings 记录各阶段耗时，用于性能分析。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════

class ReviewMode(StrEnum):
    """审查结果的执行来源。"""
    QWEN = "qwen"    # 调用 Qwen 多模态模型进行审查
    MOCK = "mock"    # 固定模拟结果，仅用于快速功能演示
    LOCAL = "local"  # 仅用于反序列化旧版历史记录


class TaskStatus(StrEnum):
    """审查任务状态机 — 按执行顺序严格流转。"""
    UPLOADING = "uploading"    # 文件上传中
    PARSING = "parsing"        # 文档解析中
    RECOGNIZING = "recognizing"  # 图像文字识别中
    CHECKING = "checking"      # 规则审查中（三现四流）
    VALIDATING = "validating"  # 证据校验中
    COMPLETED = "completed"    # 审查完成
    FAILED = "failed"          # 审查失败（不可恢复）


class SourceType(StrEnum):
    """段落内容来源类型 — 决定该段文本的可信度与展示方式。"""
    NATIVE_TEXT = "native_text"  # DOCX 原生文本或 PDF 可提取文本
    TABLE = "table"              # 表格内容（按阅读顺序重组）
    VISION = "vision"            # 图像 OCR 识别文本
    HEADER = "header"            # DOCX 页眉文本
    FOOTER = "footer"            # DOCX 页脚文本


class RuleStatus(StrEnum):
    """单条规则的审查结论状态。"""
    COVERED = "covered"                # 全部强制事实已覆盖
    MISSING = "missing"                # 全部强制事实缺失
    INCOMPLETE = "incomplete"          # 部分覆盖（含回答"不知道"等）
    NOT_APPLICABLE = "not_applicable"  # 条件规则不适用（笔录无触发事实）


class ManualStatus(StrEnum):
    """人工分流 — 办案人员对模型结果的最终处置状态。"""
    PENDING = "pending"              # 待处理（默认）
    CONFIRMED = "confirmed"          # 确认存在问题
    SUPPLEMENTED = "supplemented"    # 已加入补问清单
    IGNORED = "ignored"              # 已忽略


class ReviewStatus(StrEnum):
    """审查复核状态 — 控制 UI 是否允许修改操作。"""
    IN_REVIEW = "in_review"  # 复核中（可修改人工分流）
    ARCHIVED = "archived"    # 已归档（只读）


# ═══════════════════════════════════════════════════════════════
# API 响应模型
# ═══════════════════════════════════════════════════════════════

class QwenHealth(BaseModel):
    """Qwen 模型连接状态快照。"""
    configured: bool
    reachable: bool
    model: str | None


class HealthResponse(BaseModel):
    ok: bool
    qwen: QwenHealth
    ruleCount: int


class RuleSummary(BaseModel):
    """对前端暴露的规则摘要（省略 triggers、requiredFacts 详情等内部字段）。"""
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
    """演示样例的对外摘要。"""
    id: str
    name: str
    pageCount: int
    intent: str
    executionMode: Literal["mock", "qwen"]


class DemoListResponse(BaseModel):
    demos: list[DemoSummary]


class CreateTaskResponse(BaseModel):
    """创建审查任务的即时响应（异步处理，需轮询最终结果）。"""
    taskId: str
    status: TaskStatus


# ═══════════════════════════════════════════════════════════════
# 文档结构模型
# ═══════════════════════════════════════════════════════════════

class DocumentParagraph(BaseModel):
    """文档中的单个段落。

    Attributes:
        text:       段落原文。
        sourceType: 来源类型，决定如何渲染（文本/表格/图像识别）。
        confidence: 图像识别的置信度（0-1），仅 VISION 类型有效。
    """
    id: str = ""
    text: str
    sourceType: SourceType
    confidence: float | None = Field(default=None, ge=0, le=1)
    charStart: int = Field(default=0, ge=0)
    charEnd: int = Field(default=0, ge=0)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)


class DocumentPage(BaseModel):
    """文档中的一页，包含段落列表。"""
    page: int
    paragraphs: list[DocumentParagraph]


class DocumentWarning(BaseModel):
    """Recoverable document issue that must remain visible to reviewers."""
    code: str
    message: str
    partName: str | None = None


class ParsedDocument(BaseModel):
    """标准化后的文档 — 统一 PDF/DOCX/SAMPLE 的内部表示。"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    format: Literal["DOCX", "PDF", "SAMPLE"]
    pageCount: int
    pages: list[DocumentPage]
    text: str         # 全文拼接文本，用于关键词搜索
    sizeLabel: str    # 用户可读的大小标签（如"脱敏样例"）
    warnings: list[DocumentWarning] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 被害人信息
# ═══════════════════════════════════════════════════════════════

class VictimProfile(BaseModel):
    """从笔录中提取的被害人基础信息，全部字段可为空（提取失败时）。"""
    name: str | None = None
    gender: str | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    ethnicity: str | None = None
    idNumber: str | None = None
    employer: str | None = None
    address: str | None = None
    contact: str | None = None


# ═══════════════════════════════════════════════════════════════
# 模型通信模型（严格模式 — extra="forbid"）
# ═══════════════════════════════════════════════════════════════

class EvidenceLocation(BaseModel):
    """证据在笔录中的位置（页号 + 段号，均从 1 开始计数）。"""
    page: int
    paragraph: int


class ModelEvidenceLocation(BaseModel):
    """模型输出中的证据定位 — 与 EvidenceLocation 结构相同但通过严格 Schema 校验。"""
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)


class ModelRuleResult(BaseModel):
    """模型对单条规则的完整判断结果（原始输出，未经过确定性校验）。"""
    model_config = ConfigDict(extra="forbid")

    factCoverage: dict[str, Literal["covered", "missing", "unknown"]]
    evidenceLocations: list[ModelEvidenceLocation] = Field(max_length=3)
    reason: str
    suggestedQuestion: str
    advisories: list[str]


class ModelReviewOutput(BaseModel):
    """模型七条规则的结构化输出（仅用于 JSON Schema 验证）。"""
    model_config = ConfigDict(extra="forbid")

    present_001: ModelRuleResult = Field(alias="PRESENT-001")
    present_002: ModelRuleResult = Field(alias="PRESENT-002")
    present_003: ModelRuleResult = Field(alias="PRESENT-003")
    flow_001: ModelRuleResult = Field(alias="FLOW-001")
    flow_002: ModelRuleResult = Field(alias="FLOW-002")
    flow_003: ModelRuleResult = Field(alias="FLOW-003")
    flow_004: ModelRuleResult = Field(alias="FLOW-004")

    def as_keyed_payload(self) -> dict:
        """以规则 ID 为键的字典，供下游校验直接使用。"""
        return self.model_dump(mode="json", by_alias=True)


# ═══════════════════════════════════════════════════════════════
# 人工分流与审查结果
# ═══════════════════════════════════════════════════════════════

class ManualDecision(BaseModel):
    """办案人员对单条规则结果的人工处置记录。"""
    status: ManualStatus = ManualStatus.PENDING
    reason: str = ""


class ReviewResult(BaseModel):
    """经过确定性校验后的最终规则审查结果（含人工分流状态）。"""
    ruleId: str
    ruleName: str
    category: str
    group: str
    status: RuleStatus
    missingFacts: list[str]         # 该规则下缺失的强制事实标签列表
    evidence: str                   # 证据原文（摘录自笔录）
    evidenceLocation: EvidenceLocation | None  # 兼容旧版单定位字段
    evidenceLocations: list[EvidenceLocation] = Field(default_factory=list)  # 新版多证据定位
    reason: str                     # 模型判断理由
    suggestedQuestion: str          # 建议的补问内容
    advisories: list[str] = Field(default_factory=list)  # 非强制补充关注
    manualDecision: ManualDecision = Field(default_factory=ManualDecision)
    source: str                     # 结果来源说明（如模型名或规则版本）


class DecisionResponse(BaseModel):
    result: ReviewResult


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════
# 审查任务聚合
# ═══════════════════════════════════════════════════════════════

class ReviewTimings(BaseModel):
    """审查任务各阶段的耗时统计（毫秒）。"""
    parseMs: int | None = None              # 文档解析阶段耗时
    modelReviewMs: int | None = None        # 模型审查总耗时
    modelGroupsMs: dict[str, int] = Field(default_factory=dict)  # 分组耗时（如 "三现"/"四流"）
    totalMs: int | None = None              # 任务总耗时


class ReviewTask(BaseModel):
    """审查任务 — 系统的核心聚合根，包含一份笔录的全部审查状态。"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: ReviewMode
    status: TaskStatus = TaskStatus.PARSING
    document: ParsedDocument | None = None
    victimProfile: VictimProfile | None = None
    results: list[ReviewResult] = Field(default_factory=list)
    timings: ReviewTimings = Field(default_factory=lambda: ReviewTimings())
    reviewStatus: ReviewStatus = ReviewStatus.IN_REVIEW
    archivedAt: str | None = None
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)
    errorCode: str | None = None       # 失败时的错误码
    errorMessage: str | None = None    # 失败时的错误描述


# ═══════════════════════════════════════════════════════════════
# API 请求/响应模型
# ═══════════════════════════════════════════════════════════════

class DecisionRequest(BaseModel):
    status: ManualStatus
    reason: str = ""


class CompleteReviewResponse(BaseModel):
    reviewStatus: ReviewStatus
    archivedAt: str


class FollowUpListResponse(BaseModel):
    items: list[ReviewResult]


class ReportData(BaseModel):
    """审查报告的全部数据 — 用于打印/导出。"""
    id: str
    document: ParsedDocument | None
    victimProfile: VictimProfile | None
    mode: ReviewMode
    createdAt: str
    archivedAt: str | None
    reviewStatus: ReviewStatus
    results: list[ReviewResult]


class ReviewSummary(BaseModel):
    """审查历史列表中的单条摘要。"""
    id: str
    documentName: str
    createdAt: str
    updatedAt: str
    reviewStatus: ReviewStatus
    pendingCount: int  # 待人工处置的规则项数量


class ReviewListResponse(BaseModel):
    reviews: list[ReviewSummary]
