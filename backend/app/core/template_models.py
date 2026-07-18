"""
模板审查专用的 Pydantic 模型 — 规则目录、事实抽取、审查问题。

此模型集与 core/models.py 分离的原因是：
- models.py 是"全系统共享"的核心类型
- 本文件是"模板审查路径专用"的类型，随规则版本变化可能调整

依赖：app.core.models（RuleStatus 枚举）

类概览：

规则目录：
  TemplateSource        — 规则来源文档元数据（名称、SHA256、段落/问题计数）
  RuleCondition         — 规则的适用条件（路径 + 运算符 + 值）
  RepeatEntityRule      — 重复实体验证规则（如"多次转账需每笔记录"）
  ConsistencyCheck      — 事实间数值/时间一致性校验
  TemplateRule          — 单条审查规则完整定义
  TemplateRuleCatalog   — 版本化规则集合

事实抽取：
  ExtractedFact         — 单个事实（值+清晰度+证据锚点+模型置信度）
  ExtractedEntity       — 重复实体实例（如一次转账记录）
  CaseExtraction        — 7 域合并后的全案事实抽取

审查问题：
  TemplateReviewIssue   — 规则引擎输出的一条审查结论
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.models import RuleStatus


# ═══════════════════════════════════════════════════════════════════
# 规则目录模型
# ═══════════════════════════════════════════════════════════════════

TemplateGroup = Literal[
    "META", "PROC", "CASE", "PREV", "RISK", "CASH", "TIME", "PRIV",
    "LEAD", "MOTIVE", "CONTACT", "MONEY", "OFFLINE", "EXTRA", "EVID",
]


class TemplateSource(BaseModel):
    """规则来源说明 — 记录规则从哪个模板文件派生。

    属性：
        document:        模板文件名（如"询问笔录模版(1).docx"）
        sha256:          模板文件的 SHA-256 哈希
        paragraphCount:  模板文档总段落数
        questionCount:   模板文档中的询问问题数
    """
    model_config = ConfigDict(extra="forbid")

    document: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paragraphCount: int = Field(ge=1)
    questionCount: int = Field(ge=1)


class RuleCondition(BaseModel):
    """规则的适用条件 — 满足此条件后规则才会生效。

    属性：
        path:     条件事实路径，如 "online_money.used"
        operator: 比较运算符
        value:    比较值（operator 为 equals/in/gt/gte 时使用）
    """
    model_config = ConfigDict(extra="forbid")

    path: str
    operator: Literal["equals", "not_equals", "exists", "truthy", "gt", "gte", "in"]
    value: Any = None


class RepeatEntityRule(BaseModel):
    """重复实体验证规则 — 对可能多次发生的事实要求保留每次独立记录。

    属性：
        entityType:      实体类型名，如 "transfers"
        countPath:       笔录中声明的计数事实路径，如 "money.transfer_count"
        requiredFields:  每个实体实例必填的字段列表
    """
    model_config = ConfigDict(extra="forbid")

    entityType: str
    countPath: str | None = None
    requiredFields: list[str] = Field(min_length=1)


class ConsistencyCheck(BaseModel):
    """事实间一致性校验规则 — 做数值求和、时间先后等交叉验证。

    属性：
        type:        校验类型（count_matches / sum_matches / rebate_net_loss / chronology）
        entityType:  参与校验的实体类型（count_matches / sum_matches 用）
        entityField: 实体中参与求和的字段名（sum_matches 用）
        totalPath:   声明总数的事实路径（sum_matches / count_matches 用）
        countPath:   声明计数的事实路径（count_matches 用）
        leftPath / rightPath / resultPath:  运算左右操作数和结果（rebate_net_loss 用）
        earlierPath / laterPath:            时间先后比较（chronology 用）
    """
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
    """单条审查规则 — 从 JSON 目录反序列化的完整业务规则定义。

    一条规则完整描述：
    - 从模板文档哪个位置派生（sourceParagraphs / sourceMarker / sourceKind）
    - 何时适用（appliesWhen）
    - 要求哪些事实清晰（requiredFields）
    - 是否有重复实体及校验（repeatEntity）
    - 事实间一致性校验（consistencyChecks）
    """
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
    """规则目录 — 版本化的规则集合。

    属性：
        version:  规则版本号
        source:   来源模板文件的元数据
        rules:    规则列表
    """
    model_config = ConfigDict(extra="forbid")

    version: str
    source: TemplateSource
    rules: list[TemplateRule] = Field(min_length=1)


# ═══════════════════════════════════════════════════════════════════
# 事实抽取模型
# ═══════════════════════════════════════════════════════════════════

class ExtractedFact(BaseModel):
    """模型抽取的一个事实 — 包含值、清晰度和证据锚点。

    clarity 含义：
    - clear:    模型在原文中找到明确答案
    - unclear:  原文提及但信息模糊
    - unknown:  原文未提及（模型不确定是否存在）
    - missing:  原文确实缺失（evidenceAnchorIds 必须为空列表）

    sourceConfidence: 模型对该事实抽取结果的置信度 [0, 1]
    """
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    clarity: Literal["clear", "unclear", "unknown", "missing"] = "missing"
    evidenceAnchorIds: list[str] = Field(default_factory=list)
    sourceConfidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedEntity(BaseModel):
    """一个重复实体实例 — 如一次转账记录、一次线下交付。

    属性：
        id:         域内唯一标识
        entityType: 实体类型（必须与所属数组类型一致）
        fields:     该实体的字段值集合
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    entityType: str
    fields: dict[str, ExtractedFact] = Field(default_factory=dict)


class CaseExtraction(BaseModel):
    """整个案件的事实抽取结果 — 7 个业务域合并后的统一结构。

    属性：
        facts:         全部事实的键值对（dot.path → ExtractedFact）
        entities:      重复实体分组（entity_type → [ExtractedEntity]）
        failedDomains: 完全抽取失败的域列表（可能导致部分结果不可用）
    """
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    entities: dict[str, list[ExtractedEntity]] = Field(default_factory=dict)
    failedDomains: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# 审查问题模型
# ═══════════════════════════════════════════════════════════════════

class TemplateReviewIssue(BaseModel):
    """规则引擎执行一条规则后产生的审查结论。

    属性：
        ruleId:          规则 ID
        ruleName:        规则名称
        group:           规则所属分组
        status:          规则状态（已覆盖 / 缺失 / 不完整 / 不一致 / 不适用）
        missingFields:   缺席/冲突的字段路径列表
        reason:          审查结论的自然语言说明
        anchorIds:       相关证据段落锚点
        suggestedQuestion: 审查员建议下一步询问的问题
        severity:        问题严重等级（high / medium / low）
    """
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
