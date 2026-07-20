"""
模板域事实抽取 — 将笔录原文通过多模态模型映射到结构化业务域。

职责边界：
- 本文件是"模型驱动"的事实抽取器，每个业务域有独立的 JSON Schema。
- 不负责规则判断（由 rules.py 完成），只负责从笔录中抽取结构化证据。

核心流程：
1. 将 7 个业务域并行发给 Qwen 模型。
2. 每个域有独立的事实路径集合和 JSON Schema。
3. 模型输出经 _restore_anchor_aliases 将短锚点转回真实 ID。
4. validate_domain_extraction 校验锚点有效性、实体数量一致性等。
5. 每个域最多重试 3 次，失败后抛出 TemplateDomainFailure。

7 个业务域：
1. header_procedure   — 笔录头部信息与程序性事项
2. case_timeline      — 案件经过时间线
3. contact_channels   — 接触渠道（含 contact_switches 实体）
4. risk_and_evidence  — 风险与证据
5. online_money       — 线上资金（含 transfers、rebates 实体）
6. offline_delivery   — 线下交付（含 withdrawals、offline_handoffs 实体）
7. special_scenarios  — 特殊场景标记

依赖关系：
- core/config.py: QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL。
- data/rules.py: TEMPLATE_RULE_CATALOG, TEMPLATE_RULES。
- core/development_logging.py: 结构化日志。
- core/errors.py: AppError 异常体系。
- core/models.py: 核心 Pydantic 模型。
- core/template_models.py: CaseExtraction、ExtractedFact 等模板模型。
- llm/qwen.py: request_structured_payload 通用结构化提取。
- review/rules.py: evaluate_template_rules 规则引擎（用于 recheck_ambiguous_facts）。
"""

import asyncio
from hashlib import sha256
import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter

import httpx
from pydantic import ValidationError

from app.core.config import (
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_DOMAIN_CONCURRENCY,
    QWEN_MODEL,
    QWEN_SCHEMA_RETRIES,
)
from app.data.domain_contracts import (
    DOMAIN_CONTRACTS,
    DOMAIN_ENTITY_APPLICABILITY,
    DOMAIN_ENTITY_FIELDS,
    DOMAIN_FACT_PATHS,
    DOMAIN_ORDER,
    ENTITY_COUNT_PATHS,
)
from app.data.rules import TEMPLATE_RULE_CATALOG, TEMPLATE_RULES
from app.core.development_logging import log_event, log_payload
from app.core.errors import AppError
from app.core.models import EvidenceLocation, ManualDecision, ParsedDocument, ReviewResult, RuleStatus
from app.llm.qwen import request_structured_payload
from app.review.domain_contract_rendering import (
    build_domain_schema,
    render_domain_prompt,
    validate_schema_payload,
)
from app.review.rules import _boolean_value, evaluate_template_rules
from app.core.template_models import CaseExtraction, ExtractedFact, TemplateReviewIssue, TemplateRule


# 可通过 QWEN_DOMAIN_CONCURRENCY 调整，范围 1-7。
DEFAULT_DOMAIN_CONCURRENCY = QWEN_DOMAIN_CONCURRENCY
MAX_FACTS_PER_SCHEMA_REQUEST = 8


class TemplateDomainFailure(AppError):
    """业务域抽取失败异常 — 携带部分结果和失败信息。

    当某个域在重试 3 次后仍然失败时抛出。
    调用方（review.py）利用 partial_extraction 做部分结果持久化。
    """

    def __init__(
        self,
        *,
        partial_extraction: CaseExtraction,
        failed_domains: list[str],
        domain_errors: dict[str, str] | None = None,
        domain_error_details: dict[str, str] | None = None,
    ) -> None:
        domains = list(dict.fromkeys(failed_domains))
        super().__init__(
            "template_domain_failed",
            "部分业务域连续抽取失败，审查不能标记为完成。",
            502,
            field=domains[0] if domains else None,
        )
        self.partial_extraction = partial_extraction
        self.failed_domains = domains
        self.domain_errors = domain_errors or {}
        self.domain_error_details = domain_error_details or {}


_PATH_DOMAINS = {
    path: domain
    for domain, paths in DOMAIN_FACT_PATHS.items()
    for path in paths
}


def _domain_for_path(path: str) -> str:
    """根据域合同确定事实路径所属业务域。"""
    try:
        return _PATH_DOMAINS[path]
    except KeyError as exc:
        raise ValueError(f"Unknown template fact path: {path}") from exc


@dataclass
class TemplateReviewOutcome:
    """一次完整的模板审查结果。

    Attributes:
        extraction: 跨域合并后的事实与实体抽取结果。
        issues:     规则引擎输出的审查问题列表。
        results:    前端可展示的 ReviewResult 列表。
    """
    extraction: CaseExtraction
    issues: list[TemplateReviewIssue]
    results: list[ReviewResult]


def template_extraction_schema(
    domain: str,
    *,
    fact_paths: tuple[str, ...] | None = None,
    allowed_anchor_ids: tuple[str, ...] | None = None,
) -> dict:
    """兼容入口：从域合同生成指定业务域的 JSON Schema。"""
    try:
        contract = DOMAIN_CONTRACTS[domain]
    except KeyError as exc:
        raise ValueError(f"Unknown extraction domain: {domain}") from exc
    return build_domain_schema(
        contract,
        fact_paths=fact_paths,
        allowed_anchor_ids=allowed_anchor_ids,
    )


def build_domain_prompt(
    document: ParsedDocument,
    domain: str,
    *,
    focus_paths: tuple[str, ...] | None = None,
) -> str:
    """兼容入口：从域合同和固定模板生成提示词。"""
    try:
        contract = DOMAIN_CONTRACTS[domain]
    except KeyError as exc:
        raise ValueError(f"Unknown extraction domain: {domain}") from exc
    return render_domain_prompt(document, contract, fact_paths=focus_paths)


def _anchor_aliases(document: ParsedDocument) -> dict[str, str]:
    """将真实锚点 ID 映射为短别名（A001, A002, ...）。

    长锚点 ID 是 SHA-256 哈希的前 24 位（如 "a1b2c3d4e5f6g7h8i9j0k1l2"），
    对模型不友好。短别名（A001）更容易让模型理解和引用。
    """
    return {
        paragraph.id: f"A{index:03d}"
        for index, paragraph in enumerate(
            (paragraph for page in document.pages for paragraph in page.paragraphs),
            start=1,
        )
    }


def _evidence_anchor_aliases(document: ParsedDocument) -> tuple[str, ...]:
    """返回可作为事实证据的短锚点，排除空答案问答。"""
    aliases = _anchor_aliases(document)
    blank_anchors = {
        anchor
        for block in document.questionAnswers
        if block.answerClarity == "blank"
        for anchor in block.anchorIds
    }
    return tuple(alias for anchor, alias in aliases.items() if anchor not in blank_anchors)


def _normalize_unsupported_evidence(payload: dict, allowed_anchor_ids: set[str]) -> list[str]:
    """Fail closed when a claimed fact has no usable evidence anchor."""
    normalized: list[str] = []

    def normalize(path: str, fact: object) -> None:
        if not isinstance(fact, dict):
            return
        clarity = fact.get("clarity")
        anchors = fact.get("evidenceAnchorIds")
        if not isinstance(anchors, list):
            return
        unsupported_claim = clarity in {"clear", "unclear"} and (
            not anchors or any(anchor not in allowed_anchor_ids for anchor in anchors)
        )
        unsupported_absence = clarity in {"unknown", "missing"} and (
            fact.get("value") is not None or bool(anchors)
        )
        if not unsupported_claim and not unsupported_absence:
            return
        fact["value"] = None
        fact["clarity"] = "unknown" if unsupported_claim else clarity
        fact["evidenceAnchorIds"] = []
        normalized.append(path)

    for path, fact in payload.get("facts", {}).items():
        normalize(path, fact)
    for entity_type, entities in payload.get("entities", {}).items():
        if not isinstance(entities, list):
            continue
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                continue
            for field, fact in entity.get("fields", {}).items():
                normalize(f"{entity_type}[{index}].{field}", fact)
    return normalized


def _restore_anchor_aliases(document: ParsedDocument, extraction: CaseExtraction) -> None:
    """将模型输出的短锚点别名恢复为真实锚点 ID。

    模型在 response 中引用的是 A001 这样的短别名，
    但系统内部使用的是 SHA-256 哈希 ID。这个函数负责转换。
    """
    aliases = {alias: anchor for anchor, alias in _anchor_aliases(document).items()}

    def restore(fact: ExtractedFact) -> None:
        restored: list[str] = []
        for anchor in fact.evidenceAnchorIds:
            pieces = [piece.strip() for piece in re.split(r"[,，;；\s]+", anchor) if piece.strip()]
            if pieces and all(piece in aliases for piece in pieces):
                restored.extend(aliases[piece] for piece in pieces)
            else:
                restored.append(aliases.get(anchor, anchor))
        fact.evidenceAnchorIds = list(dict.fromkeys(restored))

    for fact in extraction.facts.values():
        restore(fact)
    for entities in extraction.entities.values():
        for entity in entities:
            for fact in entity.fields.values():
                restore(fact)


def _anchor_index(document: ParsedDocument) -> dict[str, str]:
    """构建锚点 ID → 段落原文的索引。"""
    return {
        paragraph.id: paragraph.text
        for page in document.pages
        for paragraph in page.paragraphs
    }


def validate_domain_extraction(
    document: ParsedDocument,
    domain: str,
    extraction: CaseExtraction,
    *,
    fact_paths: tuple[str, ...] | None = None,
) -> CaseExtraction:
    """校验单个业务域的抽取结果。

    校验项：
    1. 事实路径集合是否完整（不能多不能少）。
    2. 缺失事实不能附带证据锚点。
    3. 所有锚点 ID 必须存在于文档中。
    4. 空答案不能作为证据引用。
    5. 实体 ID 唯一性、类型一致性。
    6. 实体数量与计数字段一致。
    7. 实体适用性条件（适用域才有实体）。

    Raises:
        AppError: 任意校验项不通过时抛出（带 correction_hint 供重试）。
    """
    expected_paths = set(fact_paths if fact_paths is not None else DOMAIN_FACT_PATHS[domain])
    if set(extraction.facts) != expected_paths:
        raise AppError(
            "invalid_model_schema",
            f"{domain} 域事实字段不完整。",
            502,
            retry_strategy="schema",
            field="facts",
            correction_hint="返回该域 Schema 要求的全部事实路径，缺失事实使用 clarity=missing。",
        )
    anchors = _anchor_index(document)
    qa_by_anchor = {
        anchor: block
        for block in document.questionAnswers
        for anchor in block.anchorIds
    }

    def validate_fact(path: str, fact: ExtractedFact) -> None:
        if fact.clarity in {"missing", "unknown"}:
            if fact.evidenceAnchorIds:
                raise AppError(
                    "invalid_model_evidence",
                    "缺失或未知事实不得附带证据锚点。",
                    502,
                    retry_strategy="schema",
                    field=path,
                    correction_hint=(
                        f"{path} 的 clarity 为 missing 或 unknown 时，"
                        "必须返回 value=null 且 evidenceAnchorIds=[]。"
                    ),
                )
            return
        normalized_anchors: list[str] = []
        for anchor in fact.evidenceAnchorIds:
            if anchor in anchors:
                normalized_anchors.append(anchor)
                continue
            pieces = [piece.strip() for piece in re.split(r"[,，;；\s]+", anchor) if piece.strip()]
            if len(pieces) > 1 and all(piece in anchors for piece in pieces):
                normalized_anchors.extend(pieces)
            else:
                normalized_anchors.append(anchor)
        fact.evidenceAnchorIds = list(dict.fromkeys(normalized_anchors))
        if not fact.evidenceAnchorIds or any(anchor not in anchors for anchor in fact.evidenceAnchorIds):
            invalid_anchors = [anchor for anchor in fact.evidenceAnchorIds if anchor not in anchors]
            log_event(
                logging.WARNING,
                "template_extraction.invalid_anchors",
                domain=domain,
                field=path,
                invalid_anchor_ids=invalid_anchors,
                allowed_anchor_count=len(anchors),
            )
            raise AppError(
                "invalid_model_evidence",
                "模型返回了不存在的证据锚点。",
                502,
                retry_strategy="schema",
                field=path,
                correction_hint="只能使用提示词中列出的真实锚点 ID。",
            )
        linked_questions = [qa_by_anchor[anchor] for anchor in fact.evidenceAnchorIds if anchor in qa_by_anchor]
        if linked_questions and all(block.answerClarity == "blank" for block in linked_questions):
            raise AppError(
                "invalid_model_evidence",
                "空答案或纯模板说明不能作为案件事实证据。",
                502,
                retry_strategy="schema",
                field=path,
                correction_hint="该问答没有案件答案，必须返回 clarity=missing。",
            )

    for path, fact in extraction.facts.items():
        validate_fact(path, fact)
    allowed_entities = {} if fact_paths is not None else DOMAIN_ENTITY_FIELDS[domain]
    if not set(extraction.entities).issubset(allowed_entities):
        raise AppError("invalid_model_schema", f"{domain} 返回了未声明的实体类型。", 502, retry_strategy="schema", field="entities")
    seen_ids: set[str] = set()
    for entity_type, entities in extraction.entities.items():
        for entity in entities:
            if entity.entityType != entity_type or entity.id in seen_ids:
                raise AppError(
                    "invalid_model_schema",
                    "重复实体 ID 或实体类型不一致。",
                    502,
                    retry_strategy="schema",
                    field=entity_type,
                    correction_hint="每个重复事实使用独立实体；实体 ID 在整个业务域内必须唯一，entityType 必须与所在实体数组一致。",
                )
            seen_ids.add(entity.id)
            for field_name, fact in entity.fields.items():
                validate_fact(f"{entity.id}.{field_name}", fact)

    entity_count = sum(len(entities) for entities in extraction.entities.values())
    applicability_path = DOMAIN_ENTITY_APPLICABILITY.get(domain)
    if entity_count and applicability_path is not None:
        applicability = extraction.facts.get(applicability_path)
        if (
            applicability is None
            or applicability.clarity != "clear"
            or _boolean_value(applicability.value) is not True
        ):
            raise AppError(
                "invalid_model_schema",
                "业务域未明确适用时不得返回重复实体。",
                502,
                retry_strategy="schema",
                field=applicability_path,
                correction_hint=f"只有 {applicability_path} 明确为 true 时才能返回本域实体，否则实体数组必须为空。",
            )

    for entity_type, count_path in ENTITY_COUNT_PATHS.items():
        if entity_type not in allowed_entities:
            continue
        entities = extraction.entities.get(entity_type, [])
        count_fact = extraction.facts.get(count_path)
        if count_fact is None or count_fact.clarity != "clear":
            if not entities:
                continue
            expected_count = None
        else:
            try:
                expected_count = int(count_fact.value)
            except (TypeError, ValueError):
                expected_count = None
        if expected_count != len(entities):
            raise AppError(
                "invalid_model_schema",
                "重复实体数量与笔录中的计数字段不一致。",
                502,
                retry_strategy="schema",
                field=entity_type,
                correction_hint=f"{entity_type} 数组长度必须与 {count_path} 的明确数值完全一致。",
            )
    return extraction


async def _request_domain(
    client: httpx.AsyncClient,
    document: ParsedDocument,
    domain: str,
    correction: AppError | None = None,
    focus_paths: tuple[str, ...] | None = None,
) -> CaseExtraction:
    """向模型请求单个业务域的事实抽取。"""
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        raise AppError("model_not_configured", "Qwen 模型尚未配置。", 503)
    correction_feedback = None
    if correction is not None:
        correction_feedback = json.dumps({
            "code": correction.code,
            "field": correction.field,
            "instruction": correction.correction_hint,
        }, ensure_ascii=False)
    contract = DOMAIN_CONTRACTS[domain]
    prompt = render_domain_prompt(
        document,
        contract,
        fact_paths=focus_paths,
        correction=correction_feedback,
    )
    messages = [
        {"role": "system", "content": "严格按服务端 Schema 抽取证据事实，只能引用提供的锚点。"},
        {"role": "user", "content": prompt},
    ]
    log_payload("template_extraction.prompt", prompt, domain=domain, retry=correction is not None)
    allowed_anchor_ids = _evidence_anchor_aliases(document)
    schema = build_domain_schema(
        contract,
        fact_paths=focus_paths,
        allowed_anchor_ids=allowed_anchor_ids,
    )
    payload = await request_structured_payload(
        client,
        messages=messages,
        schema=schema,
        schema_name=f"extract_{domain}",
    )
    top_level_fields = set(payload) if isinstance(payload, dict) else set()
    expected_fields = {"facts", "entities", "failedDomains"}
    if top_level_fields != expected_fields:
        raise AppError(
            "structured_output_not_enforced",
            "模型接口接受了 JSON Schema 参数，但返回结果未执行该 Schema。",
            502,
            field="payload",
            correction_hint="structured_output_not_enforced",
        )
    normalized_evidence = _normalize_unsupported_evidence(payload, set(allowed_anchor_ids))
    if normalized_evidence:
        log_event(
            logging.WARNING,
            "template_extraction.evidence_downgraded",
            domain=domain,
            fields=normalized_evidence,
        )
    validate_schema_payload(payload, schema, domain)
    try:
        extraction = CaseExtraction.model_validate(payload)
        _restore_anchor_aliases(document, extraction)
        return extraction
    except ValidationError as exc:
        raise AppError(
            "invalid_model_schema",
            f"{domain} 域结果不符合结构约束。",
            502,
            retry_strategy="schema",
            field="payload",
            correction_hint=str(exc.errors(include_url=False)[:3]),
        ) from exc


async def extract_template_facts(
    document: ParsedDocument,
    timings: dict[str, int],
    *,
    domains: tuple[str, ...] = DOMAIN_ORDER,
    focus_paths: tuple[str, ...] | None = None,
    max_concurrency: int = DEFAULT_DOMAIN_CONCURRENCY,
) -> CaseExtraction:
    """对指定业务域并行执行事实抽取。

    每个域最多重试 3 次，使用 asyncio.Semaphore 控制并发数。
    成功的结果被合并到统一的 CaseExtraction 中。

    Args:
        document:       标准化笔录文档。
        timings:        用于记录每个域的耗时（ms）。
        domains:        要抽取的业务域列表。
        focus_paths:    如果指定，只抽取这些路径（纠错模式）。
        max_concurrency:最大并发域数。

    Returns:
        合并后的跨域 CaseExtraction。

    Raises:
        TemplateDomainFailure: 部分或全部域抽取失败。
    """
    merged = CaseExtraction()
    timeout = httpx.Timeout(240.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def extract_domain(domain: str) -> tuple[str, CaseExtraction]:
            started = perf_counter()
            domain_focus_paths = (
                tuple(path for path in focus_paths if _domain_for_path(path) == domain)
                if focus_paths is not None
                else None
            )
            if domain_focus_paths is not None:
                request_batches: tuple[tuple[str, ...] | None, ...] = (domain_focus_paths,)
            elif not DOMAIN_ENTITY_FIELDS[domain] and len(DOMAIN_FACT_PATHS[domain]) > MAX_FACTS_PER_SCHEMA_REQUEST:
                paths = DOMAIN_FACT_PATHS[domain]
                request_batches = tuple(
                    paths[index:index + MAX_FACTS_PER_SCHEMA_REQUEST]
                    for index in range(0, len(paths), MAX_FACTS_PER_SCHEMA_REQUEST)
                )
            else:
                request_batches = (None,)
            async with semaphore:
                try:
                    extracted = CaseExtraction()
                    for batch_paths in request_batches:
                        correction: AppError | None = None
                        for attempt in range(1 + QWEN_SCHEMA_RETRIES):
                            try:
                                batch = await _request_domain(
                                    client,
                                    document,
                                    domain,
                                    correction,
                                    batch_paths,
                                )
                                validate_domain_extraction(
                                    document,
                                    domain,
                                    batch,
                                    fact_paths=batch_paths,
                                )
                                break
                            except AppError as error:
                                if error.code in {"model_not_configured", "model_auth_failed"}:
                                    raise
                                if error.retry_strategy != "schema":
                                    raise
                                correction = (
                                    None
                                    if error.code in {"model_unreachable", "model_request_failed"}
                                    else error
                                )
                                if attempt == QWEN_SCHEMA_RETRIES:
                                    raise
                        overlap = set(extracted.facts).intersection(batch.facts)
                        if overlap:
                            raise AppError("template_domain_overlap", "业务域批次返回了重复事实路径。", 502, field=sorted(overlap)[0])
                        extracted.facts.update(batch.facts)
                        for entity_type, entities in batch.entities.items():
                            extracted.entities.setdefault(entity_type, []).extend(entities)
                    validate_domain_extraction(
                        document,
                        domain,
                        extracted,
                        fact_paths=domain_focus_paths,
                    )
                except AppError as error:
                    log_event(logging.ERROR, "template_extraction.domain_failed", domain=domain, code=error.code)
                    raise AppError(
                        "template_domain_failed",
                        f"{domain} 业务域多次抽取失败，审查不能标记为完成。",
                        502,
                        field=domain,
                        correction_hint=error.code,
                    ) from error
                finally:
                    timings[domain] = round((perf_counter() - started) * 1000)
            return domain, extracted

        domain_results = await asyncio.gather(
            *(extract_domain(domain) for domain in domains),
            return_exceptions=True,
        )
        failures: list[str] = []
        domain_errors: dict[str, str] = {}
        domain_error_details: dict[str, str] = {}
        extracted_domains: list[tuple[str, CaseExtraction]] = []
        for domain, result in zip(domains, domain_results, strict=True):
            if isinstance(result, BaseException):
                failures.append(domain)
                domain_errors[domain] = (
                    result.correction_hint
                    if isinstance(result, AppError) and result.correction_hint
                    else result.code if isinstance(result, AppError)
                    else type(result).__name__
                )
                cause = result.__cause__
                if isinstance(cause, AppError) and cause.correction_hint:
                    domain_error_details[domain] = cause.correction_hint
            else:
                extracted_domains.append(result)
        for domain, extracted in extracted_domains:
            overlap = set(merged.facts).intersection(extracted.facts)
            if overlap:
                raise AppError("template_domain_overlap", "业务域返回了重复事实路径。", 502, field=sorted(overlap)[0])
            merged.facts.update(extracted.facts)
            for entity_type, entities in extracted.entities.items():
                merged.entities.setdefault(entity_type, []).extend(entities)
        if failures:
            raise TemplateDomainFailure(
                partial_extraction=merged,
                failed_domains=failures,
                domain_errors=domain_errors,
                domain_error_details=domain_error_details,
            )
    log_event(logging.INFO, "template_extraction.completed", domains=list(domains), facts=len(merged.facts), entities={key: len(value) for key, value in merged.entities.items()})
    return merged


def semantic_fingerprint(
    extraction: CaseExtraction,
    issues: list[TemplateReviewIssue],
) -> str:
    """生成语义指纹 — 用于检测抽取结果是否有实质性变化。

    指纹包含事实值、清晰度、锚点、问题状态等信息。
    相同的指纹 = 语义上完全一致的结果。
    """
    payload = {
        "facts": {
            path: {
                "value": fact.value,
                "clarity": fact.clarity,
                "anchors": sorted(fact.evidenceAnchorIds),
            }
            for path, fact in sorted(extraction.facts.items())
        },
        "entities": {
            entity_type: [
                {
                    "id": entity.id,
                    "fields": {
                        field: {
                            "value": fact.value,
                            "clarity": fact.clarity,
                            "anchors": sorted(fact.evidenceAnchorIds),
                        }
                        for field, fact in sorted(entity.fields.items())
                    },
                }
                for entity in sorted(entities, key=lambda item: item.id)
            ]
            for entity_type, entities in sorted(extraction.entities.items())
        },
        "issues": {
            issue.ruleId: {
                "status": issue.status.value,
                "missingFields": sorted(issue.missingFields),
                "anchors": sorted(issue.anchorIds),
            }
            for issue in sorted(issues, key=lambda item: item.ruleId)
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


async def recheck_ambiguous_facts(
    document: ParsedDocument,
    extraction: CaseExtraction,
    timings: dict[str, int],
    ambiguous_rules: list[TemplateRule],
    *,
    max_concurrency: int = DEFAULT_DOMAIN_CONCURRENCY,
) -> CaseExtraction:
    """对 NEEDS_MANUAL_REVIEW 的规则重新提取关键事实。

    有时模型第一次抽取时某些事实没看清（clarity=unknown），
    导致规则引擎无法判定。这里聚焦在这些关键路径上重新抽取。
    """
    focus_paths = tuple(dict.fromkeys(
        rule.appliesWhen.path
        for rule in ambiguous_rules
        if rule.appliesWhen is not None
    ))
    if not focus_paths:
        return extraction
    domains = tuple(dict.fromkeys(_domain_for_path(path) for path in focus_paths))
    refreshed = await extract_template_facts(
        document,
        timings,
        domains=domains,
        focus_paths=focus_paths,
        max_concurrency=max_concurrency,
    )
    merged = extraction.model_copy(deep=True)
    for domain in domains:
        for path in DOMAIN_FACT_PATHS[domain]:
            if path in refreshed.facts:
                merged.facts[path] = refreshed.facts[path]
        for entity_type in DOMAIN_ENTITY_FIELDS[domain]:
            if entity_type in refreshed.entities:
                merged.entities[entity_type] = refreshed.entities[entity_type]
    return merged


def _review_result(document: ParsedDocument, issue: TemplateReviewIssue) -> ReviewResult:
    """将规则引擎的输出（TemplateReviewIssue）转为前端可用的 ReviewResult。"""
    anchor_index = {
        paragraph.id: (paragraph.text, EvidenceLocation(page=page.page, paragraph=index + 1))
        for page in document.pages
        for index, paragraph in enumerate(page.paragraphs)
    }
    located = [anchor_index[anchor] for anchor in issue.anchorIds if anchor in anchor_index]
    locations: list[EvidenceLocation] = []
    evidence_parts: list[str] = []
    for text, location in located:
        if location not in locations:
            locations.append(location)
        if text not in evidence_parts:
            evidence_parts.append(text)
    return ReviewResult(
        ruleId=issue.ruleId,
        ruleName=issue.ruleName,
        category=issue.group,
        group=issue.group,
        status=issue.status,
        missingFacts=issue.missingFields,
        evidence="\n".join(evidence_parts) if evidence_parts else "未找到可核验的原文证据。",
        evidenceLocation=locations[0] if locations else None,
        evidenceLocations=locations,
        evidenceAnchorIds=issue.anchorIds,
        reason=issue.reason,
        suggestedQuestion=issue.suggestedQuestion,
        advisories=[],
        manualDecision=ManualDecision(),
        source=f"内部询问笔录模板 v{TEMPLATE_RULE_CATALOG.version}（{QWEN_MODEL} 事实抽取，确定性规则校验）",
        severity=issue.severity,
    )


def _merge_refreshed_domains(
    base: CaseExtraction,
    refreshed: CaseExtraction,
    domains: tuple[str, ...],
) -> CaseExtraction:
    """将刷新后的域的结果合并到基准抽取结果中。

    用于补问重审和失败域重试场景。
    只替换 domains 中指定的域，其他域保持不动。
    """
    merged = base.model_copy(deep=True)
    for domain in domains:
        for path in DOMAIN_FACT_PATHS[domain]:
            if path in refreshed.facts:
                merged.facts[path] = refreshed.facts[path]
        for entity_type in DOMAIN_ENTITY_FIELDS[domain]:
            if entity_type in refreshed.entities:
                merged.entities[entity_type] = refreshed.entities[entity_type]
    return merged


async def run_template_review(
    document: ParsedDocument,
    *,
    group_timings: dict[str, int] | None = None,
    rules: list[TemplateRule] | None = None,
    domains: tuple[str, ...] = DOMAIN_ORDER,
    base_extraction: CaseExtraction | None = None,
    max_concurrency: int = DEFAULT_DOMAIN_CONCURRENCY,
) -> TemplateReviewOutcome:
    """执行完整的模板审查流程。

    这是模板审查的顶层入口：
    1. 事实抽取（并行 7 域）。
    2. 规则评估。
    3. 如果有 NEEDS_MANUAL_REVIEW → 重新抽取关键路径 → 重新评估。
    4. 生成前端可用的 ReviewResult 列表。

    Args:
        document:        标准化笔录文档。
        group_timings:   可选，记录每个域的耗时。
        rules:           可选的规则子集（默认全部规则）。
        domains:         要审查的业务域。
        base_extraction: 可选，用于增量审查的基础抽取结果。
        max_concurrency: 最大并发域数。

    Returns:
        TemplateReviewOutcome: 包含提取结果、问题和最终结果的完整审查输出。
    """
    timings = group_timings if group_timings is not None else {}
    selected_rules = rules or TEMPLATE_RULES
    refreshed = await extract_template_facts(
        document,
        timings,
        domains=domains,
        max_concurrency=max_concurrency,
    )
    extraction = (
        _merge_refreshed_domains(base_extraction, refreshed, domains)
        if base_extraction is not None
        else refreshed
    )
    issues = evaluate_template_rules(extraction, selected_rules)
    ambiguous_ids = {
        issue.ruleId
        for issue in issues
        if issue.status == RuleStatus.NEEDS_MANUAL_REVIEW
    }
    if ambiguous_ids:
        ambiguous_rules = [rule for rule in selected_rules if rule.ruleId in ambiguous_ids]
        extraction = await recheck_ambiguous_facts(
            document,
            extraction,
            timings,
            ambiguous_rules,
            max_concurrency=max_concurrency,
        )
        issues = evaluate_template_rules(extraction, selected_rules)
    results = [_review_result(document, issue) for issue in issues]
    log_payload(
        "template_review.results",
        [result.model_dump(mode="json") for result in results],
        rules=len(results),
    )
    return TemplateReviewOutcome(extraction=extraction, issues=issues, results=results)


async def review_template_document(
    document: ParsedDocument,
    *,
    group_timings: dict[str, int] | None = None,
    rules: list[TemplateRule] | None = None,
) -> list[ReviewResult]:
    """便捷入口 — 直接返回审查结果列表（不需要完整的 TemplateReviewOutcome）。"""
    outcome = await run_template_review(
        document,
        group_timings=group_timings,
        rules=rules,
    )
    return outcome.results
