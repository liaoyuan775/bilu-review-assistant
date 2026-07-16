import asyncio
import json

import httpx
from pydantic import ValidationError

from app.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.data import RULES
from app.errors import AppError
from app.models import EvidenceLocation, ManualDecision, ModelReviewOutput, ParsedDocument, ReviewResult, RuleStatus


TOOL_NAME = "submit_three_present_four_flows_review"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


async def check_qwen() -> bool:
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        return False
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{QWEN_BASE_URL}/models", headers={"Authorization": f"Bearer {QWEN_API_KEY}"})
            return response.is_success
    except httpx.HTTPError:
        return False


def _location_schema() -> dict:
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
        "evidenceLocation": {"anyOf": [_location_schema(), {"type": "null"}]},
        "reason": {"type": "string", "minLength": 1},
        "suggestedQuestion": {"type": "string"},
        "advisories": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["factCoverage", "evidenceLocation", "reason", "suggestedQuestion", "advisories"],
        "additionalProperties": False,
    }


def structured_review_schema() -> dict:
    return {
        "type": "object",
        "properties": {rule["id"]: _rule_result_schema(rule) for rule in RULES},
        "required": [rule["id"] for rule in RULES],
        "additionalProperties": False,
    }


def _prompt(document: ParsedDocument) -> str:
    located = "\n".join(
        f"[第{page.page}页-第{index + 1}段][{paragraph.sourceType.value}] {paragraph.text}"
        for page in document.pages
        for index, paragraph in enumerate(page.paragraphs)
    )
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
    } for rule in RULES]
    return f"""你是公安机关电信网络诈骗询问笔录的辅助复盘工具。你只检查固定的三现四流工作规则，不得作出案件定性、法律结论、责任判断或证据效力判断，不得补写笔录中没有的事实。

逐项判断 requiredFacts，并填写 factCoverage：
- covered：该强制事实有明确问答或可核验证据。
- missing：全文没有询问或回答该强制事实。
- unknown：已经问到该事实，但回答为不知道、不记得、无法提供等不可核验内容。

factCoverage 的键必须逐字复制当前规则 requiredFacts，不能使用 referenceHints、改写标签或新增字段。程序将根据全部固定事实键确定性生成总体 status 和 missingFacts，模型不要自行输出这两个字段。
referenceHints 来自补充资料，只能帮助搜索和生成 advisories，绝不能写入 missingFacts，也不能改变 status。advisories 是非强制的“补充关注”，不得表述为明确漏问。

证据要求：如果任一事实为 covered 或 unknown，evidenceLocation 必须从标准笔录索引中选择一个真实存在、最能支持本规则判断的页码和段落号；如果全部事实为 missing，位置必须为 null。不要输出 evidence，程序会根据位置直接读取原文。存在 missing 或 unknown 事实时必须给出建议补问。
严格按照服务端提供的 JSON Schema 输出。顶层七个固定键分别对应七条规则，不得遗漏、增加或重复。每个键下必须逐项填写所有 factCoverage。

固定规则：
{json.dumps(public_rules, ensure_ascii=False)}

标准笔录（唯一事实来源）：
{located}"""


def _parse_structured(content: str) -> ModelReviewOutput:
    try:
        return ModelReviewOutput.model_validate_json(content)
    except ValidationError as exc:
        raise AppError(
            "invalid_model_response",
            "模型返回内容不符合严格 JSON Schema。",
            502,
            retry_strategy="tool",
            field="structuredOutput",
            correction_hint="必须严格返回固定七条规则及 Schema 中声明的全部字段。",
        ) from exc


def _validation_error(
    code: str,
    message: str,
    *,
    rule_id: str | None = None,
    field: str | None = None,
    correction_hint: str,
) -> AppError:
    return AppError(
        code,
        message,
        502,
        retry_strategy="schema",
        rule_id=rule_id,
        field=field,
        correction_hint=correction_hint,
    )


def _validate(payload: dict, document: ParsedDocument) -> list[ReviewResult]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or len(raw_results) != len(RULES):
        raise _validation_error(
            "incomplete_model_results",
            "模型未返回完整规则结果。",
            field="results",
            correction_hint=f"必须完整返回 {len(RULES)} 条固定规则。",
        )
    rules_by_id = {rule["id"]: rule for rule in RULES}
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
        if rule["scope"] == "base" and status == RuleStatus.NOT_APPLICABLE:
            raise _validation_error(
                "invalid_model_results",
                "基础规则不能标记为不适用。",
                rule_id=rule_id,
                field="status",
                correction_hint="基础规则必须判断为 covered、missing 或 incomplete。",
            )
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
        if any(fact not in allowed_facts for fact in missing_facts):
            allowed_labels = [fact["label"] for fact in rule["requiredFacts"]]
            raise _validation_error(
                "invalid_model_results",
                "模型把非强制补充项写入了缺失字段。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="missingFacts 只允许以下值：" + "、".join(allowed_labels) + "。不得使用 referenceHints 或自建字段。",
            )
        if status in {RuleStatus.COVERED, RuleStatus.NOT_APPLICABLE} and missing_facts:
            raise _validation_error(
                "invalid_model_results",
                "规则状态与强制缺失字段不一致。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="covered 或 not_applicable 的 missingFacts 必须为空。",
            )
        if status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE} and not missing_facts:
            raise _validation_error(
                "invalid_model_results",
                "问题项缺少明确的强制缺失字段。",
                rule_id=rule_id,
                field="missingFacts",
                correction_hint="missing 或 incomplete 至少列出一个当前规则的强制缺失字段。",
            )
        if not reason or (status != RuleStatus.NOT_APPLICABLE and not evidence):
            raise _validation_error(
                "insufficient_evidence",
                "模型结果缺少可核验证据。",
                rule_id=rule_id,
                field="evidence",
                correction_hint="reason 不能为空；适用规则必须引用原文 evidence。",
            )
        if status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE} and not suggestion:
            raise _validation_error(
                "invalid_model_results",
                "问题项缺少建议补问。",
                rule_id=rule_id,
                field="suggestedQuestion",
                correction_hint="missing 或 incomplete 必须给出可直接使用的建议补问。",
            )

        location = None
        source_paragraph = None
        raw_location = raw.get("evidenceLocation")
        if isinstance(raw_location, dict):
            page_no, paragraph_no = raw_location.get("page"), raw_location.get("paragraph")
            page = next((item for item in document.pages if item.page == page_no), None)
            if page and isinstance(paragraph_no, int) and 1 <= paragraph_no <= len(page.paragraphs):
                location = EvidenceLocation(page=page_no, paragraph=paragraph_no)
                source_paragraph = page.paragraphs[paragraph_no - 1].text
        if status in {RuleStatus.COVERED, RuleStatus.INCOMPLETE} and location is None:
            raise _validation_error(
                "insufficient_evidence",
                "已覆盖或回答不完整的结论缺少原文定位。",
                rule_id=rule_id,
                field="evidenceLocation",
                correction_hint="从标准笔录索引中复制真实存在的 page 和 paragraph。",
            )
        if status == RuleStatus.MISSING and raw_location is not None:
            raise _validation_error(
                "invalid_model_results",
                "完全缺失的结论不应伪造原文定位。",
                rule_id=rule_id,
                field="evidenceLocation",
                correction_hint="missing 的 evidenceLocation 必须为 null。",
            )
        if source_paragraph is not None:
            compact_evidence = "".join(evidence.split())
            compact_source = "".join(source_paragraph.split())
            if compact_evidence not in compact_source and compact_source not in compact_evidence:
                raise _validation_error(
                    "insufficient_evidence",
                    "模型证据与定位段落不一致。",
                    rule_id=rule_id,
                    field="evidence",
                    correction_hint="逐字引用 evidenceLocation 指向段落中的原文，不得概括。",
                )

        results.append(ReviewResult(
            ruleId=rule_id,
            ruleName=rule["name"],
            category=rule["category"],
            group=rule["group"],
            status=status,
            missingFacts=missing_facts,
            evidence=evidence,
            evidenceLocation=location,
            reason=reason,
            suggestedQuestion="" if status in {RuleStatus.COVERED, RuleStatus.NOT_APPLICABLE} else suggestion,
            advisories=advisories,
            manualDecision=ManualDecision(),
            source="三现四流工作规则（Qwen 辅助判断，结果需人工复核）",
        ))
    return results


def _messages(document: ParsedDocument, correction: AppError | None = None) -> list[dict]:
    messages = [
        {"role": "system", "content": "严格依据固定规则审查，只能使用标准笔录中的事实，并按服务端结构化输出约束返回完整结果。"},
        {"role": "user", "content": _prompt(document)},
    ]
    if correction is not None:
        feedback = {
            "previousResultAccepted": False,
            "errorCode": correction.code,
            "ruleId": correction.rule_id,
            "field": correction.field,
            "instruction": correction.correction_hint or "重新生成全部七条规则并严格满足 JSON Schema。",
        }
        messages.append({
            "role": "user",
            "content": "上一次完整结果未通过确定性校验。不要局部修补，重新生成全部七条规则。校验反馈："
            + json.dumps(feedback, ensure_ascii=False),
        })
    return messages


async def _post_completion(client: httpx.AsyncClient, payload: dict, *, strategy: str) -> dict:
    try:
        response = await client.post(
            f"{QWEN_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {QWEN_API_KEY}"},
            json=payload,
        )
    except httpx.HTTPError as exc:
        raise AppError(
            "model_unreachable",
            "Qwen 模型服务当前不可达，请检查网络或模型配置。",
            503,
            retry_strategy="schema",
        ) from exc
    if response.status_code in {401, 403}:
        raise AppError("model_auth_failed", "Qwen 模型鉴权失败，请检查模型配置。", 503)
    if not response.is_success:
        response_text = response.text.lower()
        unsupported_markers = ("json_schema", "response_format", "tool_choice", "tool_calls", "tools")
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
    return message


async def _request_schema_review(client: httpx.AsyncClient, document: ParsedDocument, correction: AppError | None = None) -> ModelReviewOutput:
    message = await _post_completion(client, {
        "model": QWEN_MODEL,
        "temperature": 0.1,
        "messages": _messages(document, correction),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "three_present_four_flows_review",
                "strict": True,
                "schema": structured_review_schema(),
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
    return _parse_structured(content)


async def _request_tool_review(client: httpx.AsyncClient, document: ParsedDocument) -> ModelReviewOutput:
    message = await _post_completion(client, {
        "model": QWEN_MODEL,
        "temperature": 0.1,
        "messages": _messages(document),
        "tools": [{
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": "提交固定七条三现四流审查结果。",
                "parameters": structured_review_schema(),
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
    return _parse_structured(function["arguments"])


def _evidence_from_location(document: ParsedDocument, raw_location: dict | None) -> str:
    if isinstance(raw_location, dict):
        page_no = raw_location.get("page")
        paragraph_no = raw_location.get("paragraph")
        page = next((item for item in document.pages if item.page == page_no), None)
        if page and isinstance(paragraph_no, int) and 1 <= paragraph_no <= len(page.paragraphs):
            return page.paragraphs[paragraph_no - 1].text
    return "原文定位无效，需重新选择页码和段落号。"


def _validation_payload(output: ModelReviewOutput, document: ParsedDocument) -> dict:
    keyed = output.as_keyed_payload()
    results = []
    for rule in RULES:
        raw = keyed[rule["id"]]
        coverage = raw.pop("factCoverage")
        labels = [fact["label"] for fact in rule["requiredFacts"]]
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
            f"全文未检索到“{rule['name']}”相关强制事实。"
            if status == RuleStatus.MISSING
            else _evidence_from_location(document, raw.get("evidenceLocation"))
        )
        results.append({
            "ruleId": rule["id"],
            "status": status.value,
            "missingFacts": missing_facts,
            "evidence": evidence,
            **raw,
        })
    return {"results": results}


def _validated_results(output: ModelReviewOutput, document: ParsedDocument) -> list[ReviewResult]:
    return _validate(_validation_payload(output, document), document)


async def review_with_qwen(document: ParsedDocument) -> list[ReviewResult]:
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        raise AppError("model_not_configured", "Qwen 模型尚未配置。", 503)
    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        try:
            return _validated_results(await _request_schema_review(client, document), document)
        except AppError as first_error:
            if first_error.retry_strategy is None:
                raise
            if first_error.retry_strategy == "tool":
                return _validated_results(await _request_tool_review(client, document), document)
            if first_error.code in {"model_unreachable", "model_request_failed"}:
                await asyncio.sleep(1)
                return _validated_results(await _request_schema_review(client, document), document)
            return _validated_results(await _request_schema_review(client, document, first_error), document)
