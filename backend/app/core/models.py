"""
核心 Pydantic 数据模型 — 整个应用的统一类型定义。

本文件定义了全系统共享的数据结构，跨度从文件上传、文档解析、
模型抽取、规则计算到 UI 展示和报告生成。所有模型通过 Pydantic
实现序列化/反序列化，确保 API 响应和 SQLite 存储的一致性。

注意：本文件不导入应用内任何其他模块，是整个依赖图的最底层节点。
     依赖本文件的有约 17 个模块，修改时需考虑全面回归。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════

class TaskStatus(StrEnum):
    """审查任务状态机 — 按执行顺序严格流转。"""
    UPLOADING = "uploading"    # 文件上传中
    PARSING = "parsing"        # 文档解析中
    RECOGNIZING = "recognizing"  # 图像文字识别中
    CHECKING = "checking"      # 规则审查中（三现四流）
    VALIDATING = "validating"  # 证据校验中
    COMPLETED = "completed"    # 审查完成
    FAILED = "failed"          # 审查失败（不可恢复）


class ReviewMode(StrEnum):
    """审查执行模式。"""
    QWEN = "qwen"      # 真实 Qwen 模型审查（默认）
    LOCAL = "local"    # 旧版本地模式（历史兼容）
    MOCK = "mock"      # 快速模拟演示（不调用模型）


class ReviewStatus(StrEnum):
    """复核整体状态。"""
    IN_REVIEW = "in_review"
    ARCHIVED = "archived"


class RuleStatus(StrEnum):
    """单条规则的状态 — 由规则引擎计算得出，人工处置不改变此值。"""
    COVERED = "covered"                  # 验证通过
    MISSING = "missing"                  # 提问遗漏
    INCOMPLETE = "incomplete"            # 回答不完整
    INCONSISTENT = "inconsistent"        # 事实矛盾
    NOT_APPLICABLE = "not_applicable"    # 不适用
    NEEDS_MANUAL_REVIEW = "needs_manual_review"  # 无法判断适用性


class ManualStatus(StrEnum):
    """人工处置状态 — 与 RuleStatus 并列，不覆盖自动计算结果。"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SUPPLEMENTED = "supplemented"
    IGNORED = "ignored"
    RESOLVED = "resolved"
    NOT_APPLICABLE = "not_applicable"


class SourceType(StrEnum):
    """段落来源类型 — 用于 UI 标注和锚点追溯。"""
    NATIVE_TEXT = "native_text"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    VISION = "vision"


# ═══════════════════════════════════════════════════════════════════
# 文档解析模型
# ═══════════════════════════════════════════════════════════════════

class ParsedDocument(BaseModel):
    """统一解析文档 — 无论 DOCX/PDF，解析后都转为此结构。

    关键设计：
    - pages 中的每个 paragraph 都有稳定的 id（内容哈希），
      作为模型证据锚点和 UI 高亮的连接键。
    - text 是全文拼接，用于正则提取和全文搜索。
    - questionAnswers 由独立的状态机重建，与原始段落并行。
    """
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    name: str = ""
    format: str = ""           # "DOCX" | "PDF"
    pageCount: int = 0
    pages: list[DocumentPage] = []
    text: str = ""             # 全文拼接（用于搜索和正则）
    sizeLabel: str = ""
    warnings: list[DocumentWarning] = []
    questionAnswers: list[QuestionAnswerBlock] = []


class DocumentPage(BaseModel):
    """文档的一页（逻辑页，非 Word/PDF 物理页）。"""
    model_config = ConfigDict(extra="forbid")
    page: int = 1
    paragraphs: list[DocumentParagraph] = []


class DocumentParagraph(BaseModel):
    """文档的一个段落 — 证据的最小定位单元。

    id 字段是稳定锚点：SHA-256(文档指纹:页码:段序:来源:文本)[:24]，
    同一文档的同一段落每次解析结果一致。
    """
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    text: str = ""
    sourceType: SourceType = SourceType.NATIVE_TEXT
    confidence: float | None = None  # VLM 转写置信度（仅 vision 来源时有值）
    charStart: int = 0
    charEnd: int = 0
    bbox: list[float] | None = None  # PDF 原生文本的坐标框 [x0,y0,x1,y1]


class DocumentWarning(BaseModel):
    """解析过程中的非致命警告，确认后方可归档。"""
    model_config = ConfigDict(extra="forbid")
    code: str = ""
    message: str = ""
    partName: str = ""


class QuestionAnswerBlock(BaseModel):
    """从段落中重建的一个问答对。

    guidance 字段存放从问题/答案中移除的括号模板说明和填写示例，
    避免被模型误当成案件事实。
    """
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    question: str = ""
    answer: str = ""
    guidance: list[str] = Field(default_factory=list)  # 移除的模板说明
    anchorIds: list[str] = Field(default_factory=list)  # 该问答涉及的段落锚点
    answerClarity: str = "unknown"  # clear / blank / unknown


# ═══════════════════════════════════════════════════════════════════
# 规则结果模型
# ═══════════════════════════════════════════════════════════════════

class EvidenceLocation(BaseModel):
    """证据在笔录中的位置（页号 + 段号，均从 1 开始计数）。"""
    page: int
    paragraph: int


class ManualDecision(BaseModel):
    """人工处置决定 — 对一条规则结果的人工确认/补问/忽略。"""
    model_config = ConfigDict(extra="forbid")
    status: ManualStatus = ManualStatus.PENDING
    reason: str = ""


class ReviewResult(BaseModel):
    """单条规则的审查结果 — 前端展示和人工处置的基本单元。

    包含规则状态、缺失事实、原文证据、锚点位置和建议补问。
    evidenceLocation 是历史兼容字段（只含首项位置），
    新代码应优先使用 evidenceLocations（全部位置）和 evidenceAnchorIds（稳定锚点）。
    """
    model_config = ConfigDict(extra="forbid")
    ruleId: str = ""
    ruleName: str = ""
    category: str = ""
    group: str = ""
    status: RuleStatus = RuleStatus.MISSING
    missingFacts: list[str] = []
    evidence: str = ""                              # 证据原文（多段换行拼接）
    evidenceLocation: EvidenceLocation | None = None  # 兼容旧消费者
    evidenceLocations: list[EvidenceLocation] = []
    evidenceAnchorIds: list[str] = []
    reason: str = ""
    suggestedQuestion: str = ""                     # 建议补问内容
    advisories: list[str] = []
    manualDecision: ManualDecision = Field(default_factory=ManualDecision)
    source: str = ""                                # 审查来源信息
    severity: str = "medium"                        # high / medium / low


# ═══════════════════════════════════════════════════════════════════
# 被害人信息模型
# ═══════════════════════════════════════════════════════════════════

class VictimProfile(BaseModel):
    """从笔录中提取的被害人基础信息，全部字段可为空（提取失败时）。"""
    name: str | None = None
    gender: str | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    birthDate: str | None = None
    ethnicity: str | None = None
    idNumber: str | None = None
    occupation: str | None = None
    education: str | None = None
    employer: str | None = None
    address: str | None = None
    registeredAddress: str | None = None
    contact: str | None = None
    isNpcRepresentative: bool | None = None


# ═══════════════════════════════════════════════════════════════════
# 审查任务模型
# ═══════════════════════════════════════════════════════════════════

def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


class ReviewTimings(BaseModel):
    """各阶段耗时统计（毫秒）。"""
    model_config = ConfigDict(extra="forbid")
    parseMs: int | None = None         # 文档解析耗时
    modelReviewMs: int | None = None   # 模型事实抽取耗时
    modelGroupsMs: dict[str, int] = Field(default_factory=dict)  # 各域耗时明细
    totalMs: int | None = None         # 总耗时


class ArtifactSummary(BaseModel):
    """产物摘要 — 用于前端产物列表展示和后端哈希登记。"""
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    type: str = ""           # original / review_pdf / follow_up_docx / structured_json / archive_manifest
    filename: str = ""
    sha256: str = ""
    sizeBytes: int = 0


class ReviewTask(BaseModel):
    """审查任务 — 全系统的核心聚合根。

    包含从上传到归档的完整状态。前端轮询此对象获取进度和结果。
    通过 revision 字段实现乐观锁并发控制。
    整个对象作为 payload_json 序列化到 SQLite review_tasks 表。
    """
    model_config = ConfigDict(extra="forbid")  # 配置模型，禁止额外字段
    #基础标识，id和乐观锁字段
    id: str = Field(default_factory=lambda: str(uuid4()))  # 任务ID，使用UUID生成
    revision: int = Field(default=0, ge=0)  # 版本号，用于乐观锁控制，最小值为0
    mode: ReviewMode  # 审查模式
    demoId: str | None = None  # 内置脱敏演示标识；普通上传为空
    status: TaskStatus = TaskStatus.PARSING  # 任务状态，默认为PARSING
    document: ParsedDocument | None = None  # 解析后的文档内容
    documentId: str | None = None  # 文档ID
    documentVersionId: str | None = None  # 文档版本ID
    reviewRunId: str | None = None  # 审查运行ID
    extractionPayload: dict | None = None  # 提取的数据负载
    victimProfile: VictimProfile | None = None  # 受害者档案
    results: list[ReviewResult] = Field(default_factory=list)  # 审查结果列表
    failedDomains: list[str] = Field(default_factory=list)  # 失败的域名列表
    domainErrors: dict[str, str] = Field(default_factory=dict)  # 域级机器可读错误码
    domainErrorDetails: dict[str, str] = Field(default_factory=dict)  # 域级字段校验详情
    acknowledgedWarnings: list[str] = Field(default_factory=list)  # 已确认的警告列表
    artifacts: list[ArtifactSummary] = Field(default_factory=list)  # 工件摘要列表
    requiredArtifacts: list[str] = Field(default_factory=list)  # 所需工件列表
    timings: ReviewTimings = Field(default_factory=lambda: ReviewTimings())  # 审查时间记录
    reviewStatus: ReviewStatus = ReviewStatus.IN_REVIEW  # 审查状态，默认为IN_REVIEW
    archivedAt: str | None = None  # 归档时间
    createdAt: str = Field(default_factory=now_iso)  # 创建时间，使用ISO格式
    updatedAt: str = Field(default_factory=now_iso)  # 更新时间，使用ISO格式
    errorCode: str | None = None  # 错误代码
    errorMessage: str | None = None  # 错误消息


# ═══════════════════════════════════════════════════════════════════
# API 请求/响应模型
# ═══════════════════════════════════════════════════════════════════

class CreateTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taskId: str
    status: str


class CompleteReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewStatus: str
    archivedAt: str | None


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ManualStatus
    reason: str = ""


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: ReviewResult


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    qwen: dict
    ruleCount: int


class RuleListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[dict]


class DemoListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demos: list[dict]


class ReviewListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviews: list[dict]


class FollowUpListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ReviewResult]


class ReportData(BaseModel):
    """审查报告数据 — 包含文档、被害人信息、审查结果和复核状态。"""
    model_config = ConfigDict(extra="forbid")
    id: str
    document: ParsedDocument | None
    victimProfile: VictimProfile | None
    mode: ReviewMode
    createdAt: str
    archivedAt: str | None
    reviewStatus: ReviewStatus
    results: list[ReviewResult]


class IssueActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ManualStatus
    reason: str = ""
    actorId: str = "local-operator"


class FollowUpAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    answer: str
    actorId: str = "local-operator"


class RetryDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actorId: str = "local-operator"


class WarningAcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codes: list[str]
    actorId: str = "local-operator"
