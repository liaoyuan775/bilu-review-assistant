"""
Qwen 多模态模型集成 — LLM 调用、结构化输出解析与确定性校验。

职责边界：
- 本文件是唯一直接调用外部大语言模型的模块。
- 不处理业务逻辑（如规则判断、报告生成），只负责：
  1. 构建 Prompt 并调用 Qwen API。
  2. 解析模型返回的 JSON/Tool Calling 输出。
  3. 对模型输出执行 20+ 项确定性校验。
  4. 支持失败自动重试与策略降级。

依赖关系：
- core/config.py: API 地址、密钥、模型名。
- data/rules.py: 规则定义（RULES）。
- core/development_logging.py: 结构化日志。
- core/errors.py: AppError 异常体系。
- core/models.py: ModelRuleResult、ReviewResult 等模型。

重试策略：
- 首次失败且错误可恢复 → 带 correction_hint 重试一次。
- Schema 模式失败且服务端不支持 → 自动降级到 Tool 模式。
- 鉴权/配置错误 → 直接终止，不重试。

安全约束：
- 模型不得编造证据（evidence 必须来自定位段落的原文）。
- 模型不得输出规则 ID 之外的字段（extra="forbid"）。
- 基础规则（scope="base"）不能标记为 NOT_APPLICABLE。
"""

import asyncio
import json
import logging
from time import perf_counter

import httpx
from pydantic import ValidationError

from app.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.data.rules import RULES
from app.core.development_logging import log_event, log_payload
from app.core.errors import AppError
from app.core.models import EvidenceLocation, ManualDecision, ModelRuleResult, ParsedDocument, ReviewResult, RuleStatus

# ── 常量 ────────────────────────────────────────────────────────
TOOL_NAME = "submit_three_present_four_flows_review"
# HTTP 状态码：临时性错误（可重试）
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


# ═══════════════════════════════════════════════════════════════
# 模型连通性检查
# ═══════════════════════════════════════════════════════════════

async def check_qwen() -> bool:
    """检查 Qwen 模型服务是否可达（超时 3 秒）。

    用在系统启动时或健康检查接口，如果模型未配置或不可达，
    前端可以降级为 mock 模式（演示模式）。
    """
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        log_event(logging.DEBUG, "qwen.health_skipped", configured=False)
        return False
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{QWEN_BASE_URL}/models", headers={"Authorization": f"Bearer {QWEN_API_KEY}"})
            log_event(logging.DEBUG, "qwen.health_response", status_code=response.status_code, reachable=response.is_success, model=QWEN_MODEL)
            return response.is_success
    except httpx.HTTPError as error:
        log_event(logging.WARNING, "qwen.health_failed", error_type=type(error).__name__)
        return False


# ═══════════════════════════════════════════════════════════════
# JSON Schema 构建
# ═══════════════════════════════════════════════════════════════

def _location_schema() -> dict:
    """生成单条证据定位的 JSON Schema（页号、段号从 1 开始）。

    这个 Schema 会被嵌套在每条规则的 evidenceLocations 数组中，
    约束模型输出有效的 (page, paragraph) 二元组。
    """
    return {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "minimum": 1},
            "paragraph": {"type": "integer", "minimum": 1},
        },
        "required": ["page", "paragraph"],
        "additionalProperties": False,
    }


def _rule_result_schema(rule: dict) -> dict:
    """根据规则定义生成单条规则结果的 JSON Schema。

    关键设计：
    - factCoverage 的键直接从 rule["requiredFacts"] 提取，确保键名一致。
    - evidenceLocations 最多 3 个，超过会导致 Schema 校验失败。
    - 所有字段均为 required，不允许额外属性（additionalProperties: false）。
    """
    allowed_facts = [fact["label"] for fact in rule["requiredFacts"]]
    properties = {
        "factCoverage": {
            "type": "object",
            "properties": {
                label: {"type": "string", "enum": ["covered", "missing", "unknown"]}
                for label in allowed_facts
            },
            "required": allowed_facts,
            "additionalProperties": False,
        },
        "evidenceLocations": {
            "type": "array",
            "items": _location_schema(),
            "maxItems": 3,
        },
        "reason": {"type": "string", "minLength": 1},
        "suggestedQuestion": {"type": "string"},
        "advisories": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["factCoverage", "evidenceLocations", "reason", "suggestedQuestion", "advisories"],
        "additionalProperties": False,
    }


def structured_review_schema(rules: list[dict] | None = None) -> dict:
    """生成包含多条规则的完整 JSON Schema（顶层键为规则 ID）。

    这是发送给模型的"输出约束"——模型必须按照这个 Schema
    来组织它的返回内容。程序会严格校验每个字段。
    """
    selected_rules = rules or RULES
    schema = {
        "type": "object",
        "properties": {rule["id"]: _rule_result_schema(rule) for rule in selected_rules},
        "required": [rule["id"] for rule in selected_rules],
        "additionalProperties": False,
    }
    log_event(logging.DEBUG, "qwen.schema_built", rule_ids=[rule["id"] for rule in selected_rules], strict=True, max_evidence_locations=3)
    return schema


# ═══════════════════════════════════════════════════════════════
# Prompt 构造
# ═══════════════════════════════════════════════════════════════

def _prompt(document: ParsedDocument, rules: list[dict] | None = None) -> str:
    """构建模型审查提示词。

    包含三个部分：
    1. 角色定义与行为约束（不得定性、不得补写）。
    2. factCoverage 填报规则（covered/missing/unknown 的判别标准）。
    3. 序列化的规则定义与标准笔录全文。

    注意：这里只暴露规则的 public 字段（ruleId、name、group 等），
    不暴露内部的元数据字段。
    """
    selected_rules = rules or RULES
    # 将段落文本按 "第X页-第Y段[来源] 原文" 格式编号
    # 这个编号就是 evidenceLocations 的定位依据
    located = "\n".join(
        f"[第{page.page}页-第{index + 1}段][{paragraph.sourceType.value}] {paragraph.text}"
        for page in document.pages
        for index, paragraph in enumerate(page.paragraphs)
    )
    # 仅暴露规则的必要字段（隐藏内部元数据）
    public_rules = [{
        "ruleId": rule["id"],
        "ruleName": rule["name"],
        "group": rule["group"],
        "scope": rule["scope"],
        "triggers": rule["triggers"],
        "requiredFacts": [fact["label"] for fact in rule["requiredFacts"]],
        "referenceHints": [hint["label"] for hint in rule["referenceHints"]],
        "evidencePolicy": rule["evidencePolicy"],
        "suggestedQuestion": rule["suggestedQuestion"],
    } for rule in selected_rules]
    return f"""你是公安机关电信网络诈骗询问笔录的辅助复盘工具。你只检查固定的三现四流工作规则，不得作出案件定性、法律结论、责任判断或证据效力判断，不得补写笔录中没有的事实。

逐项判断 requiredFacts，并填写 factCoverage：
- covered：该强制事实有明确问答或可核验证据。
- missing：全文没有询问或回答该强制事实。
- unknown：已经问到该事实，但回答为不知道、不记得、无法提供等不可核验内容。

factCoverage 的键必须逐字复制当前规则 requiredFacts，不能使用 referenceHints、改写标签或新增字段。程序将根据全部固定事实键确定性生成总体 status 和 missingFacts，模型不要自行输出这两个字段。
referenceHints 来自补充资料，只能帮助搜索和生成 advisories，绝不能写入 missingFacts，也不能改变 status。advisories 是非强制的"补充关注"，不得表述为明确漏问。

证据要求：如果任一事实为 covered 或 unknown，evidenceLocations 必须从标准笔录索引中选择 1 到 3 个真实存在、最能支持本规则判断的页码和段落号；如果全部事实为 missing，位置必须为空数组。不要输出 evidence，程序会根据位置直接读取原文。存在 missing 或 unknown 事实时必须给出建议补问。
严格按照服务端提供的 JSON Schema 输出。顶层键只能是当前分组提供的固定规则 ID，不得遗漏、增加或重复。每个键下必须逐项填写所有 factCoverage。

固定规则：
{json.dumps(public_rules, ensure_ascii=False)}

标准笔录（唯一事实来源）：
{located}"""


# ═══════════════════════════════════════════════════════════════
# 模型原始输出解析
# ═══════════════════════════════════════════════════════════════

def _parse_structured(content: str, rules: list[dict]) -> dict[str, ModelRuleResult]:
    """将模型输出的 JSON 字符串解析为 ModelRuleResult 字典。

    这个函数的输入是模型返回的"原始 JSON 字符串"，
    输出是经过 Pydantic 校验的结构化 ModelRuleResult 对象。

    Raises:
        AppError: 解析失败或规则键不匹配时抛出（可重试）。
    """
    try:
        log_payload("qwen.raw_structured_content", content, rule_ids=[rule["id"] for rule in rules])
        payload = json.loads(content)
        if not isinstance(payload, dict) or set(payload) != {rule["id"] for rule in rules}:
            raise ValueError("rule keys do not match the selected group")
        parsed = {rule["id"]: ModelRuleResult.model_validate(payload[rule["id"]]) for rule in rules}
        log_event(logging.DEBUG, "qwen.structured_parsed", rule_ids=list(parsed), result_count=len(parsed))
        return parsed
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log_event(logging.WARNING, "qwen.structured_parse_failed", error_type=type(exc).__name__, rule_ids=[rule["id"] for rule in rules])
        raise AppError(
            "invalid_model_response",
            "模型返回内容不符合严格 JSON Schema。",
            502,
            retry_strategy="tool",
            field="structuredOutput",
            correction_hint="必须严格返回固定七条规则及 Schema 中声明的全部字段。",
        ) from exc


# ═══════════════════════════════════════════════════════════════
# 确定性校验（20+ 项业务规则）
# ═══════════════════════════════════════════════════════════════

def _validation_error(
    code: str,
    message: str,
    *,
    rule_id: str | None = None,
    field: str | None = None,
    correction_hint: str,
) -> AppError:
    """构造带重试策略的校验错误（retry_strategy="schema"）。"""
    return AppError(
        code,
        message,
        502,
        retry_strategy="schema",
        rule_id=rule_id,
        field=field,
        correction_hint=correction_hint,
    )


def _validate(payload: dict, document: ParsedDocument, rules: list[dict] | None = None) -> list[ReviewResult]:
    """确定性校验的核心函数 — 验证模型输出是否符合全部业务规则。

    校验项（按执行顺序）：
    1. results 字段存在且长度与规则数一致。
    2. 每条结果包含有效的 ruleId（无重复、无未知规则）。
    3. RuleStatus 合法且与 scope 兼容（base 规则不能为 NOT_APPLICABLE）。
    4. 条件规则的 triggered/not_applicable 逻辑一致性。
    5. missingFacts 只包含白名单标签。
    6. evidenceLocations 指向真实段落且证据原文匹配。
    7. 状态与缺失字段的一致性（covered 不能有缺失，missing 必须有缺失）。
    8. 证据内容与定位段落原文一致（逐字匹配）。

    为什么不依赖 LLM 自行判断？
    - 模型有时会编造规则、编造字段、编造证据位置。
    - 这 20+ 项检查是"防模型幻觉"的最后一道防线。
    - 任何一项不通过，都需要带着具体反馈重试。

    Args:
        payload:  模型完整的输出字典（含 results 列表）。
        document: 标准笔录文档，用于验证证据位置与原文。
        rules:    当前分组的规则列表。

    Returns:
        确定性校验通过后的 ReviewResult 列表。

    Raises:
        AppError: 任意校验项不通过时抛出（带有具体的字段和修正提示）。
    """
    selected_rules = rules or RULES
    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or len(raw_results) != len(selected_rules):
        raise _validation_error(
            "incomplete_model_results",
            "模型未返回完整规则结果。",
            field="results",
            correction_hint=f"必须完整返回当前分组的 {len(selected_rules)} 条固定规则。",
        )
    rules_by_id = {rule["id"]: rule for rule in selected_rules}
    seen: set[str] = set()
    results: list[ReviewResult] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise _validation_error(
                "invalid_model_results",
                "模型返回的规则结果格式无效。",
                field="ruleResult",
                correction_hint="每条规则结果必须是符合 Schema 的对象。",
            )
        rule_id = raw.get("ruleId")
        if rule_id not in rules_by_id or rule_id in seen:
            raise _validation_error(
                "invalid_model_results",
                "模型返回未知或重复规则。",
                rule_id=rule_id if isinstance(rule_id, str) else None,
                field="ruleId",
                correction_hint="只能返回固定七条规则，每条恰好一次。",
            )
        seen.add(rule_id)
        try:
            status = RuleStatus(raw.get("status"))
        except ValueError as exc:
            raise _validation_error(
                "invalid_model_results",
                "模型返回非法状态。",
                rule_id=rule_id,
                field="status",
                correction_hint="状态必须使用当前规则允许的枚举值。",
            ) from exc
        rule = rules_by_id[rule_id]
        # 基础规则不得为 NOT_APPLICABLE
        # 因为基础规则对所有笔录都适用（如"是否核实身份"）
        if rule["scope"] == "base" and status == RuleStatus.NOT_APPLICABLE:
            raise _validation_error(
                "invalid_model_results",
                "基础规则不能标记为不适用。",
                rule_id=rule_id,
                field="status",
                correction_hint="基础规则必须判断为 covered、missing 或 incomplete。",
            )
        # 条件规则：有触发词 → 不能为 NOT_APPLICABLE；无触发词 → 必须为 NOT_APPLICABLE
        if rule["scope"] == "conditional":
            triggered = any(trigger in document.text for trigger in rule["triggers"])
            if triggered == (status == RuleStatus.NOT_APPLICABLE):
                raise _validation_error(
                    "invalid_model_results",
                    "条件规则状态与笔录触发事实不一致。",
                    rule_id=rule_id,
                    field="status",
                    correction_hint="重新核对条件触发词与规则状态。",
                )

        reason = str(raw.get("reason") or "").strip()
        evidence = str(raw.get("evidence") or "").strip()
        suggestion = str(raw.get("suggestedQuestion") or "").strip()
        raw_missing_facts = raw.get("missingFacts")
        raw_advisories = raw.get("advisories", [])
        if not isinstance(raw_missing_facts, list) or not all(isinstance(item, str) for item in raw_missing_facts):
            raise _validation_error(
                "invalid_model_results",
                "模型结果缺少有效的强制缺失字段列表。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="missingFacts 必须是当前规则强制字段标签组成的数组。",
            )
        if not isinstance(raw_advisories, list) or not all(isinstance(item, str) for item in raw_advisories):
            raise _validation_error(
                "invalid_model_results",
                "模型结果缺少有效的补充关注列表。",
                rule_id=rule_id,
                field="advisories",
                correction_hint="advisories 必须是字符串数组。",
            )
        missing_facts = [item.strip() for item in raw_missing_facts if item.strip()]
        advisories = [item.strip() for item in raw_advisories if item.strip()]
        allowed_facts = {fact["label"] for fact in rule["requiredFacts"]}
        # 缺失字段必须在当前规则的 requiredFacts 白名单内
        # 防止模型把 referenceHints 或自建字段写入 missingFacts
        if any(fact not in allowed_facts for fact in missing_facts):
            allowed_labels = [fact["label"] for fact in rule["requiredFacts"]]
            raise _validation_error(
                "invalid_model_results",
                "模型把非强制补充项写入了缺失字段。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="missingFacts 只允许以下值：" + "、".join(allowed_labels) + "。不得使用 referenceHints 或自建字段。",
            )
        # covered 和 not_applicable 的 missingFacts 必须为空
        if status in {RuleStatus.COVERED, RuleStatus.NOT_APPLICABLE} and missing_facts:
            raise _validation_error(
                "invalid_model_results",
                "规则状态与强制缺失字段不一致。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="covered 或 not_applicable 的 missingFacts 必须为空。",
            )
        # missing 和 incomplete 必须有缺失字段
        if status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE} and not missing_facts:
            raise _validation_error(
                "invalid_model_results",
                "问题项缺少明确的强制缺失字段。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="missing 或 incomplete 至少列出一个当前规则的强制缺失字段。",
            )
        # reason 不能为空；适用规则必须有 evidence
        if not reason or (status != RuleStatus.NOT_APPLICABLE and not evidence):
            raise _validation_error(
                "insufficient_evidence",
                "模型结果缺少可核验证据。",
                rule_id=rule_id,
                field="evidence",
                correction_hint="reason 不能为空；适用规则必须引用原文 evidence。",
            )
        # missing 和 incomplete 必须有建议补问
        if status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE} and not suggestion:
            raise _validation_error(
                "invalid_model_results",
                "问题项缺少建议补问。",
                rule_id=rule_id,
                field="suggestedQuestion",
                correction_hint="missing 或 incomplete 必须给出可直接使用的建议补问。",
            )

        # ── evidenceLocations 校验 ──
        raw_locations = raw.get("evidenceLocations")
        # 兼容旧版单字段 evidenceLocation
        if raw_locations is None and isinstance(raw.get("evidenceLocation"), dict):
            raw_locations = [raw["evidenceLocation"]]
        if not isinstance(raw_locations, list) or len(raw_locations) > 3:
            raise _validation_error(
                "invalid_model_results",
                "证据定位必须是最多三个页段位置。",
                rule_id=rule_id,
                field="evidenceLocations",
                correction_hint="evidenceLocations 必须是最多 3 个真实页段位置的数组。",
            )
        locations: list[EvidenceLocation] = []
        source_paragraphs: list[str] = []
        for raw_location in raw_locations:
            if not isinstance(raw_location, dict):
                raise _validation_error(
                    "invalid_model_results",
                    "证据定位格式无效。",
                    rule_id=rule_id,
                    field="evidenceLocations",
                    correction_hint="每个证据定位必须包含 page 和 paragraph。",
                )
            page_no, paragraph_no = raw_location.get("page"), raw_location.get("paragraph")
            page = next((item for item in document.pages if item.page == page_no), None)
            if not page or not isinstance(paragraph_no, int) or not 1 <= paragraph_no <= len(page.paragraphs):
                continue
            location = EvidenceLocation(page=page_no, paragraph=paragraph_no)
            if location not in locations:
                locations.append(location)
                source_paragraphs.append(page.paragraphs[paragraph_no - 1].text)
        # covered 和 incomplete 必须至少有一个有效的证据定位
        if status in {RuleStatus.COVERED, RuleStatus.INCOMPLETE} and not locations:
            raise _validation_error(
                "insufficient_evidence",
                "已覆盖或回答不完整的结论缺少原文定位。",
                rule_id=rule_id,
                field="evidenceLocations",
                correction_hint="从标准笔录索引中复制至少一个真实存在的 page 和 paragraph。",
            )
        # missing 的 evidenceLocations 必须为空
        if status == RuleStatus.MISSING and locations:
            raise _validation_error(
                "invalid_model_results",
                "完全缺失的结论不应伪造原文定位。",
                rule_id=rule_id,
                field="evidenceLocations",
                correction_hint="missing 的 evidenceLocations 必须为空数组。",
            )
        # 证据原文必须与定位段落原文匹配（逐字检查）
        # 这是防止"模型编造证据"的最后拦截
        if source_paragraphs:
            compact_evidence = "".join(evidence.split())
            if any("".join(source.split()) not in compact_evidence for source in source_paragraphs):
                raise _validation_error(
                    "insufficient_evidence",
                    "模型证据与定位段落不一致。",
                    rule_id=rule_id,
                    field="evidence",
                    correction_hint="逐字引用 evidenceLocations 指向段落中的原文，不得概括。",
                )

        results.append(ReviewResult(
            ruleId=rule_id,
            ruleName=rule["name"],
            category=rule["category"],
            group=rule["group"],
            status=status,
            missingFacts=missing_facts,
            evidence=evidence,
            evidenceLocation=locations[0] if locations else None,
            evidenceLocations=locations,
            reason=reason,
            suggestedQuestion="" if status in {RuleStatus.COVERED, RuleStatus.NOT_APPLICABLE} else suggestion,
            advisories=advisories,
            manualDecision=ManualDecision(),
            source="三现四流工作规则（Qwen 辅助判断，结果需人工复核）",
        ))
    return results


# ═══════════════════════════════════════════════════════════════
# LLM 消息构造与通信
# ═══════════════════════════════════════════════════════════════

def _messages(document: ParsedDocument, rules: list[dict], correction: AppError | None = None) -> list[dict]:
    """构造 LLM 对话消息列表。

    首次请求：system + user（含提示词与笔录）。
    重试请求：增加一条 user 消息，包含上次校验失败的具体反馈。
    """
    messages = [
        {"role": "system", "content": "严格依据固定规则审查，只能使用标准笔录中的事实，并按服务端结构化输出约束返回完整结果。"},
        {"role": "user", "content": _prompt(document, rules)},
    ]
    if correction is not None:
        feedback = {
            "previousResultAccepted": False,
            "errorCode": correction.code,
            "ruleId": correction.rule_id,
            "field": correction.field,
            "instruction": correction.correction_hint or "重新生成当前分组的全部规则并严格满足 JSON Schema。",
        }
        messages.append({
            "role": "user",
            "content": "上一次完整结果未通过确定性校验。不要局部修补，重新生成当前分组的全部规则。校验反馈："
            + json.dumps(feedback, ensure_ascii=False),
        })
    return messages


async def _post_completion(client: httpx.AsyncClient, payload: dict, *, strategy: str) -> dict:
    """向 Qwen API 发送聊天补全请求并返回消息内容。

    这是最底层的 HTTP 通信函数，上层所有调用最终都汇集到这里。
    它负责：
    - 发送请求并记录耗时。
    - 识别 HTTP 错误（临时 vs 永久）。
    - 解析 JSON 响应并提取 message 字段。

    Args:
        client:   HTTP 客户端。
        payload:  请求体（含 model、messages、response_format 等）。
        strategy: 当前策略标识（"schema" 或 "tool"），用于错误处理。

    Raises:
        AppError: 网络错误、鉴权失败、模型不可达等。
    """
    started = perf_counter()
    rule_ids = []
    if strategy == "schema":
        rule_ids = payload.get("response_format", {}).get("json_schema", {}).get("schema", {}).get("required", [])
    elif payload.get("tools"):
        rule_ids = payload["tools"][0].get("function", {}).get("parameters", {}).get("required", [])
    log_event(
        logging.INFO,
        "qwen.request_started",
        strategy=strategy,
        model=payload.get("model"),
        rule_ids=rule_ids,
        message_count=len(payload.get("messages", [])),
    )
    log_payload("qwen.request_messages", payload.get("messages", []), strategy=strategy, rule_ids=rule_ids)
    try:
        response = await client.post(
            f"{QWEN_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {QWEN_API_KEY}"},
            json=payload,
        )
    except httpx.HTTPError as exc:
        log_event(logging.WARNING, "qwen.request_network_failed", strategy=strategy, rule_ids=rule_ids, duration_ms=round((perf_counter() - started) * 1000), error_type=type(exc).__name__)
        raise AppError(
            "model_unreachable",
            "Qwen 模型服务当前不可达，请检查网络或模型配置。",
            503,
            retry_strategy="schema",
        ) from exc
    if response.status_code in {401, 403}:
        log_event(logging.ERROR, "qwen.request_auth_failed", strategy=strategy, rule_ids=rule_ids, status_code=response.status_code)
        raise AppError("model_auth_failed", "Qwen 模型鉴权失败，请检查模型配置。", 503)
    if not response.is_success:
        log_event(logging.WARNING, "qwen.request_http_failed", strategy=strategy, rule_ids=rule_ids, status_code=response.status_code, duration_ms=round((perf_counter() - started) * 1000))
        response_text = response.text.lower()
        unsupported_markers = (
            "json_schema",
            "response_format",
            "tool_choice",
            "tool_calls",
            "tools",
            "grammar error",
            "unimplemented keys",
        )
        # 400/422 + 不受支持的 Schema 关键字 → 服务端不支持 JSON Schema
        if strategy == "schema" and response.status_code in {400, 422} and any(marker in response_text for marker in unsupported_markers):
            raise AppError(
                "structured_output_unsupported",
                "当前模型接口不支持严格 JSON Schema。",
                502,
                retry_strategy="tool",
            )
        if response.status_code in TRANSIENT_STATUS_CODES:
            raise AppError(
                "model_request_failed",
                f"Qwen 返回 HTTP {response.status_code}。",
                502,
                retry_strategy="schema",
            )
        raise AppError("model_request_failed", f"Qwen 返回 HTTP {response.status_code}。", 502)
    try:
        data = response.json()
    except ValueError as exc:
        raise AppError(
            "invalid_model_response",
            "Qwen 未返回有效 JSON 响应。",
            502,
            retry_strategy="tool" if strategy == "schema" else None,
        ) from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise AppError(
            "invalid_model_response",
            "Qwen 未返回有效消息。",
            502,
            retry_strategy="tool" if strategy == "schema" else None,
        )
    usage = data.get("usage") if isinstance(data, dict) else None
    log_event(
        logging.INFO,
        "qwen.request_completed",
        strategy=strategy,
        rule_ids=rule_ids,
        status_code=response.status_code,
        duration_ms=round((perf_counter() - started) * 1000),
        usage=usage,
    )
    log_payload("qwen.response_message", message, strategy=strategy, rule_ids=rule_ids)
    return message


async def request_structured_payload(
    client: httpx.AsyncClient,
    *,
    messages: list[dict],
    schema: dict,
    schema_name: str,
    tool_description: str,
) -> dict:
    """通用结构化提取请求 — 优先 JSON Schema，降级到 Tool Calling。

    这是 docx_report.py 等外部调用者的入口，用于需要模型
    输出结构化数据的场景（如报告生成中的字段提取）。

    降级机制：
    1. 先尝试 response_format=json_schema。
    2. 如果服务端返回"不支持"的错误 → 自动切换到 tools 模式。
    3. 如果两种模式都失败 → 抛出异常。
    """
    try:
        message = await _post_completion(client, {
            "model": QWEN_MODEL,
            "temperature": 0,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }, strategy="schema")
        content = message.get("content")
        if not isinstance(content, str):
            raise AppError(
                "invalid_model_response",
                "Qwen 未返回严格 JSON Schema 内容。",
                502,
                retry_strategy="tool",
                field="content",
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError(
                "invalid_model_response",
                "Qwen 返回的结构化内容不是有效 JSON。",
                502,
                retry_strategy="schema",
            ) from exc
        if not isinstance(payload, dict):
            raise AppError("invalid_model_response", "Qwen 结构化结果必须是对象。", 502, retry_strategy="schema")
        return payload
    except AppError as error:
        if error.retry_strategy != "tool":
            raise

    message = await _post_completion(client, {
        "model": QWEN_MODEL,
        "temperature": 0,
        "messages": messages,
        "tools": [{
            "type": "function",
            "function": {
                "name": schema_name,
                "description": tool_description,
                "parameters": schema,
                "strict": True,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": schema_name}},
    }, strategy="tool")
    tool_calls = message.get("tool_calls")
    function = tool_calls[0].get("function") if isinstance(tool_calls, list) and len(tool_calls) == 1 else None
    if not isinstance(function, dict) or function.get("name") != schema_name:
        raise AppError("invalid_model_response", "Qwen 未调用指定的结构化提取工具。", 502)
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        raise AppError("invalid_model_response", "Qwen 返回了无效的结构化工具参数。", 502)
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise AppError("invalid_model_response", "Qwen 工具参数不是有效 JSON。", 502) from exc
    if not isinstance(payload, dict):
        raise AppError("invalid_model_response", "Qwen 结构化结果必须是对象。", 502)
    return payload


# ═══════════════════════════════════════════════════════════════
# 两种审查调用策略
# ═══════════════════════════════════════════════════════════════

async def _request_schema_review(
    client: httpx.AsyncClient,
    document: ParsedDocument,
    rules: list[dict],
    correction: AppError | None = None,
) -> dict[str, ModelRuleResult]:
    """使用 JSON Schema 模式调用模型（优先策略）。"""
    messages = _messages(document, rules, correction)
    prompt = messages[1]["content"]
    log_payload("qwen.constraint_prompt", prompt, strategy="schema", group=rules[0]["group"], rule_ids=[rule["id"] for rule in rules], retry=correction is not None)
    message = await _post_completion(client, {
        "model": QWEN_MODEL,
        "temperature": 0.1,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "three_present_four_flows_review",
                "strict": True,
                "schema": structured_review_schema(rules),
            },
        },
    }, strategy="schema")
    content = message.get("content")
    if not isinstance(content, str):
        raise AppError(
            "invalid_model_response",
            "Qwen 未返回严格 JSON Schema 内容。",
            502,
            retry_strategy="tool",
            field="content",
        )
    return _parse_structured(content, rules)


async def _request_tool_review(
    client: httpx.AsyncClient,
    document: ParsedDocument,
    rules: list[dict],
) -> dict[str, ModelRuleResult]:
    """使用 Tool Calling 模式调用模型（降级策略 — 当 Schema 模式不可用时）。"""
    messages = _messages(document, rules)
    log_payload("qwen.constraint_prompt", messages[1]["content"], strategy="tool", group=rules[0]["group"], rule_ids=[rule["id"] for rule in rules])
    message = await _post_completion(client, {
        "model": QWEN_MODEL,
        "temperature": 0.1,
        "messages": messages,
        "tools": [{
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": "提交固定七条三现四流审查结果。",
                "parameters": structured_review_schema(rules),
                "strict": True,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": TOOL_NAME}},
    }, strategy="tool")
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise AppError("invalid_model_response", "Qwen 未调用指定的结构化审查工具。", 502)
    function = tool_calls[0].get("function") if isinstance(tool_calls[0], dict) else None
    if not isinstance(function, dict) or function.get("name") != TOOL_NAME or not isinstance(function.get("arguments"), str):
        raise AppError("invalid_model_response", "Qwen 返回了无效的结构化审查工具参数。", 502)
    return _parse_structured(function["arguments"], rules)


# ═══════════════════════════════════════════════════════════════
# 结果构造辅助函数
# ═══════════════════════════════════════════════════════════════

def _evidence_from_locations(document: ParsedDocument, raw_locations: list[dict]) -> str:
    """根据模型输出的证据定位，从文档中提取原文作为证据。

    模型输出的是 (page, paragraph) 定位，但实际展示时需要
    从文档中取出对应的原文。这个函数负责"解引用"定位。
    """
    paragraphs: list[str] = []
    for raw_location in raw_locations:
        page_no = raw_location.get("page")
        paragraph_no = raw_location.get("paragraph")
        page = next((item for item in document.pages if item.page == page_no), None)
        if page and isinstance(paragraph_no, int) and 1 <= paragraph_no <= len(page.paragraphs):
            text = page.paragraphs[paragraph_no - 1].text
            if text not in paragraphs:
                paragraphs.append(text)
    return "\n".join(paragraphs) if paragraphs else "原文定位无效，需重新选择页码和段落号。"


def _validation_payload(
    output: dict[str, ModelRuleResult],
    document: ParsedDocument,
    rules: list[dict] | None = None,
) -> dict:
    """将模型结构化输出转换为确定性校验所需的统一 payload 格式。

    核心功能：
    - 根据 factCoverage 自动推导 status（全部 covered → COVERED，
      全部 missing → MISSING，否则 → INCOMPLETE）。
    - 从定位位置提取原文作为 evidence。
    - 注入规则元数据（ruleId、status、missingFacts、evidence）。
    - 校验 factCoverage 的键是否与规则定义完全一致。
    """
    selected_rules = rules or RULES
    results = []
    for rule in selected_rules:
        raw = output[rule["id"]].model_dump(mode="json")
        coverage = raw.pop("factCoverage")
        labels = [fact["label"] for fact in rule["requiredFacts"]]
        # 校验键名一致性
        if set(coverage) != set(labels):
            raise _validation_error(
                "invalid_model_results",
                "模型返回的强制事实覆盖项与当前规则不一致。",
                rule_id=rule["id"],
                field="factCoverage",
                correction_hint="factCoverage 只允许以下键：" + "、".join(labels) + "。必须全部填写且不得增加其他键。",
            )
        values = [coverage[label] for label in labels]
        if all(value == "covered" for value in values):
            status = RuleStatus.COVERED
        elif all(value == "missing" for value in values):
            status = RuleStatus.MISSING
        else:
            status = RuleStatus.INCOMPLETE
        missing_facts = [label for label in labels if coverage[label] != "covered"]
        evidence = (
            f"全文未检索到「{rule['name']}」相关强制事实。"
            if status == RuleStatus.MISSING
            else _evidence_from_locations(document, raw.get("evidenceLocations", []))
        )
        results.append({
            "ruleId": rule["id"],
            "status": status.value,
            "missingFacts": missing_facts,
            "evidence": evidence,
            **raw,
        })
    return {"results": results}


def _validated_results(output: dict[str, ModelRuleResult], document: ParsedDocument) -> list[ReviewResult]:
    """从模型结构化输出到最终校验结果的完整转换。"""
    return _validate(_validation_payload(output, document), document)


# ═══════════════════════════════════════════════════════════════
# 分组审查与重试逻辑
# ═══════════════════════════════════════════════════════════════

async def _review_rule_group_once(
    client: httpx.AsyncClient,
    document: ParsedDocument,
    rules: list[dict],
    correction: AppError | None = None,
) -> dict[str, ModelRuleResult]:
    """单次规则分组审查（无重试）。"""
    group = rules[0]["group"]
    log_event(logging.INFO, "qwen.group_attempt", group=group, attempt=2 if correction else 1, rule_ids=[rule["id"] for rule in rules], correction_code=correction.code if correction else None)
    output = await _request_schema_review(client, document, rules, correction)
    validated = _validate(_validation_payload(output, document, rules), document, rules)
    log_event(logging.INFO, "qwen.group_validated", group=group, attempt=2 if correction else 1, statuses={result.ruleId: result.status.value for result in validated})
    return output


async def _review_rule_group(
    client: httpx.AsyncClient,
    document: ParsedDocument,
    rules: list[dict],
) -> dict[str, ModelRuleResult]:
    """带重试机制的规则分组审查。

    重试顺序：
    1. 首次尝试 Schema 模式调用。
    2. 若 Schema 模式失败 → 降级为 Tool 模式。
    3. 若网络/服务临时故障 → 等待 1 秒后带反馈重试 Schema 模式。
    4. 鉴权/配置错误 → 直接抛出。
    """
    try:
        return await _review_rule_group_once(client, document, rules)
    except AppError as first_error:
        group = rules[0]["group"]
        log_event(logging.WARNING, "qwen.group_first_attempt_failed", group=group, code=first_error.code, retry_strategy=first_error.retry_strategy, rule_id=first_error.rule_id, field=first_error.field)
        if first_error.code in {"model_not_configured", "model_auth_failed"}:
            log_event(logging.ERROR, "qwen.group_not_retryable", group=group, code=first_error.code)
            raise
        if first_error.retry_strategy == "tool":
            log_event(logging.INFO, "qwen.group_retry", group=group, attempt=2, strategy="tool", reason=first_error.code)
            output = await _request_tool_review(client, document, rules)
            validated = _validate(_validation_payload(output, document, rules), document, rules)
            log_event(logging.INFO, "qwen.group_validated", group=group, attempt=2, statuses={result.ruleId: result.status.value for result in validated})
            return output
        if first_error.code in {"model_unreachable", "model_request_failed"}:
            log_event(logging.INFO, "qwen.group_retry_wait", group=group, delay_ms=1000, reason=first_error.code)
            await asyncio.sleep(1)
        log_event(logging.INFO, "qwen.group_retry", group=group, attempt=2, strategy="schema", reason=first_error.code)
        return await _review_rule_group_once(client, document, rules, first_error)


# ═══════════════════════════════════════════════════════════════
# 公开入口
# ═══════════════════════════════════════════════════════════════

async def review_with_qwen(
    document: ParsedDocument,
    *,
    group_timings: dict[str, int] | None = None,
) -> list[ReviewResult]:
    """对一份笔录执行完整的 Qwen 三现四流审查。

    执行流程：
    1. 按"三现"、"四流"两个分组并行调用模型。
    2. 每个分组内部带有自动重试与降级机制。
    3. 合并两个分组的结果，校验完整性。
    4. 返回通过确定性校验的 ReviewResult 列表。

    这是整个审查流程的"引擎室"——所有与 LLM 的交互都从这里发起。
    调用方（review.py）只关心返回的 7 条 ReviewResult。

    Args:
        document:       标准化笔录文档。
        group_timings:  可选，用于记录每个分组的耗时。

    Returns:
        通过确定性校验的审查结果列表（7 条规则）。

    Raises:
        AppError: 模型未配置、返回不完整结果等。
    """
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        raise AppError("model_not_configured", "Qwen 模型尚未配置。", 503)
    groups = [
        (group, [rule for rule in RULES if rule["group"] == group])
        for group in ("三现", "四流")
    ]
    log_event(logging.INFO, "qwen.review_started", model=QWEN_MODEL, document= document.name, pages=document.pageCount, chars=len(document.text), groups={group: [rule["id"] for rule in rules] for group, rules in groups})
    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        async def run_group(group: str, rules: list[dict]):
            started = perf_counter()
            log_event(logging.INFO, "qwen.group_started", group=group, rule_count=len(rules))
            try:
                return group, await _review_rule_group(client, document, rules)
            finally:
                duration_ms = round((perf_counter() - started) * 1000)
                if group_timings is not None:
                    group_timings[group] = duration_ms
                log_event(logging.INFO, "qwen.group_finished", group=group, duration_ms=duration_ms)

        completed = await asyncio.gather(*(run_group(group, rules) for group, rules in groups))
    merged: dict[str, ModelRuleResult] = {}
    for _group, output in completed:
        merged.update(output)
    if set(merged) != {rule["id"] for rule in RULES}:
        log_event(logging.ERROR, "qwen.merge_incomplete", expected=[rule["id"] for rule in RULES], actual=list(merged))
        raise AppError("incomplete_model_results", "模型未返回完整规则结果。", 502)
    log_payload("qwen.groups_merged", {rule_id: result.model_dump(mode="json") for rule_id, result in merged.items()}, rule_ids=list(merged))
    validated = _validated_results(merged, document)
    log_event(logging.INFO, "qwen.review_completed", result_count=len(validated), statuses={result.ruleId: result.status.value for result in validated}, group_durations_ms=group_timings or {})
    return validated
