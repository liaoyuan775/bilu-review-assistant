"""
审查编排层 — 任务生命周期管理、异步处理与人工分流。

职责边界：
- 本文件是整个审查流程的"总指挥"，不处理具体的文档解析、模型调用或规则校验。
- 负责协调下层各模块完成一次完整的审查任务。

核心流程：
1. create_task:      创建新任务，状态 = PARSING
2. process_upload:   异步审查流程：解析 → 图片转写 → 模型事实抽取 → 规则校验
3. process_demo:     演示模式的白名单 DOCX 解析与审查
4. update_decision:  人工分流（确认/补问/忽略/不适用）
5. complete_review:  完成复核并归档

状态转换：
  PARSING → RECOGNIZING → CHECKING → VALIDATING → COMPLETED
                                                     ↓ (异常)
                                                  FAILED

异常处理：
- AppError 被精确捕获，设置 task.errorCode/errorMessage。
- 非预期的 Exception 以 "review_service_failed" 兜底。
- 在任何步骤失败后，任务状态被置为 FAILED 并持久化。

依赖关系：
- data/demo_cases.py: 演示样例加载。
- core/config.py: QWEN_MODEL 模型配置。
- data/rules.py: TEMPLATE_RULE_CATALOG 规则目录。
- core/development_logging.py: 结构化日志。
- core/errors.py: AppError 异常体系。
- core/models.py: ReviewTask、TaskStatus 等核心模型。
- core/template_models.py: CaseExtraction 模板模型。
- parsing/parser.py: 文档解析。
- parsing/question_answer.py: 问答对重建。
- review/mock.py: 模拟审查（演示模式）。
- review/extraction.py: 模板事实抽取。
- review/victim.py: 被害人信息正则提取。
- reporting/archive.py: 归档门禁。
- storage/artifacts.py: 文件制品存储。
- storage/store.py: SQLite 持久化。
"""

import logging
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from app.data.demo_cases import get_demo_case
from app.core.config import QWEN_MODEL
from app.data.rules import TEMPLATE_RULE_CATALOG
from app.core.development_logging import log_event, log_payload, reset_task_id, set_task_id
from app.core.errors import AppError
from app.core.models import ArtifactSummary, DocumentParagraph, ManualDecision, ManualStatus, ReviewMode, ReviewResult, ReviewStatus, ReviewTask, RuleStatus, SourceType, TaskStatus, now_iso
from app.reporting.archive import assert_archive_ready
from app.storage.artifacts import GENERATED_REVIEW_ARTIFACT_TYPES, save_original
from app.parsing.question_answer import reconstruct_question_answers
from app.review.mock import build_mock_review
from app.parsing.parser import parse_document
from app.review.extraction import (
    DOMAIN_ENTITY_FIELDS,
    DOMAIN_FACT_PATHS,
    DOMAIN_ORDER,
    TemplateDomainFailure,
    TemplateReviewOutcome,
    review_template_document,
    run_template_review,
)
from app.review.victim import extract_victim_profile
from app.core.template_models import CaseExtraction
from app.storage.store import (
    get_audit_snapshot,
    get_artifact_record,
    get_task,
    list_tasks,
    persist_review_outcome,
    save_artifact_record,
    save_document,
    save_document_version,
    save_review_run,
    save_task,
    save_task_with_events,
)


_GROUP_DOMAINS = {
    "META": "header_procedure",
    "PROC": "header_procedure",
    "CASE": "case_timeline",
    "TIME": "case_timeline",
    "PRIV": "case_timeline",
    "MOTIVE": "case_timeline",
    "LEAD": "contact_channels",
    "CONTACT": "contact_channels",
    "PREV": "risk_and_evidence",
    "RISK": "risk_and_evidence",
    "EVID": "risk_and_evidence",
    "MONEY": "online_money",
    "CASH": "offline_delivery",
    "OFFLINE": "offline_delivery",
    "EXTRA": "case_timeline",
}

_REQUIRED_ARTIFACTS = list(GENERATED_REVIEW_ARTIFACT_TYPES)


def _invalidate_generated_artifacts(task: ReviewTask) -> None:
    """当人工操作导致之前结果失效时，清除非源文件制品。"""
    task.requiredArtifacts = list(GENERATED_REVIEW_ARTIFACT_TYPES)
    task.artifacts = [item for item in task.artifacts if item.type == "original"]


def _missing_extraction_domains(extraction: CaseExtraction) -> list[str]:
    """检查哪些业务域的事实或实体尚未成功抽取。"""
    missing: list[str] = list(extraction.failedDomains)
    for domain in DOMAIN_ORDER:
        required_entities = DOMAIN_ENTITY_FIELDS[domain]
        if (
            any(path not in extraction.facts for path in DOMAIN_FACT_PATHS[domain])
            or any(entity_type not in extraction.entities for entity_type in required_entities)
        ):
            missing.append(domain)
    return missing


def _apply_template_domain_failure(task: ReviewTask, error: TemplateDomainFailure) -> None:
    task.extractionPayload = error.partial_extraction.model_dump(mode="json")
    task.failedDomains = list(dict.fromkeys([
        *task.failedDomains,
        *error.failed_domains,
    ]))
    task.domainErrors.update(error.domain_errors)
    task.domainErrorDetails.update(error.domain_error_details)


def _merge_manual_decisions(
    previous_results: list[ReviewResult],
    refreshed_results: list[ReviewResult],
    *,
    affected_domains: set[str],
    resolved_rule_id: str | None = None,
) -> list[str]:
    """合并人工决策状态到刷新后的结果。

    当某个域被重新审查时，受影响域的手动决策会被重置。
    未受影响的域保留原有人工决策。
    """
    previous = {item.ruleId: item for item in previous_results}
    invalidated: list[str] = []
    for item in refreshed_results:
        prior = previous.get(item.ruleId)
        if prior is None:
            continue
        domain = _GROUP_DOMAINS.get(item.group)
        if domain not in affected_domains:
            item.manualDecision = prior.manualDecision.model_copy(deep=True)
        elif (
            item.ruleId != resolved_rule_id
            and prior.manualDecision.status != ManualStatus.PENDING
        ):
            invalidated.append(item.ruleId)
    return sorted(invalidated)


def create_task(mode: ReviewMode, demo_id: str | None = None) -> ReviewTask:
    """创建新的审查任务并持久化。

    Args:
        mode: 审查模式（QWEN 或 MOCK）。

    Returns:
        已保存的 ReviewTask 实例（status = PARSING）。
    """
    return save_task(ReviewTask(mode=mode, demoId=demo_id))


async def process_upload(task_id: str, filename: str, content: bytes) -> None:
    """处理文件上传后的异步审查流程。

    执行步骤（严格顺序）：
    1. RECOGNIZING — 调用 parser 解析文档格式，提取段落与图片。
    2. CHECKING   — 调用 victim_profile 提取被害人信息。
                   按模板业务域并发调用 Qwen 提取带锚点事实。
    3. VALIDATING — 使用确定性规则引擎校验事实完整性。
    4. COMPLETED  — 审查完成，持久化结果。

    任何步骤失败 → 状态置为 FAILED，记录错误码与信息。
    """
    task = get_task(task_id)
    if task is None:
        log_event(logging.WARNING, "review.task_missing", requested_task_id=task_id)
        return
    context_token = set_task_id(task_id)
    total_started = perf_counter()
    try:
        log_event(logging.INFO, "review.started", filename=filename, bytes=len(content), mode=task.mode.value)
        original = save_original(task.id, filename, content)
        task.documentId = save_document(
            task.id,
            filename=original.filename,
            mime_type=(
                "application/pdf"
                if original.filename.lower().endswith(".pdf")
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            sha256=original.sha256,
            original_path=str(original.path),
        )
        original_record_id = save_artifact_record(
            task.id,
            None,
            artifact_type="original",
            filename=original.filename,
            path=str(original.path),
            sha256=original.sha256,
            size_bytes=original.sizeBytes,
            metadata={"source": "upload"},
        )
        task.artifacts = [ArtifactSummary(
            id=original_record_id,
            type="original",
            filename=original.filename,
            sha256=original.sha256,
            sizeBytes=original.sizeBytes,
        )]
        task.requiredArtifacts = list(_REQUIRED_ARTIFACTS)
        task.status = TaskStatus.RECOGNIZING
        save_task(task)
        log_event(logging.INFO, "review.status_changed", status=task.status.value)
        parse_started = perf_counter()
        task.document = await parse_document(filename, content)
        task.documentVersionId = save_document_version(
            task.documentId,
            content_sha256=original.sha256,
            parsed_payload=task.document.model_dump(mode="json"),
        )
        task.timings.parseMs = round((perf_counter() - parse_started) * 1000)
        log_event(logging.INFO, "review.parse_complete", duration_ms=task.timings.parseMs, pages=task.document.pageCount, chars=len(task.document.text))
        task.victimProfile = extract_victim_profile(task.document)
        extracted_fields = (
            [key for key, value in task.victimProfile.model_dump().items() if value is not None]
            if task.victimProfile
            else []
        )
        log_event(logging.DEBUG, "review.victim_profile", extracted_fields=extracted_fields)
        task.status = TaskStatus.CHECKING
        save_task(task)
        log_event(logging.INFO, "review.status_changed", status=task.status.value)
        model_started = perf_counter()
        group_timings: dict[str, int] = {}
        try:
            outcome = await run_template_review(task.document, group_timings=group_timings)
        finally:
            task.timings.modelReviewMs = round((perf_counter() - model_started) * 1000)
            task.timings.modelGroupsMs = group_timings
            log_event(logging.INFO, "review.model_complete", duration_ms=task.timings.modelReviewMs, group_durations_ms=group_timings)
        task.status = TaskStatus.VALIDATING
        save_task(task)
        log_event(logging.INFO, "review.status_changed", status=task.status.value)
        task.results = outcome.results
        task.status = TaskStatus.COMPLETED
        _persist_outcome(task, outcome)
        log_payload("review.results_merged", [result.model_dump(mode="json") for result in task.results], rules=len(task.results))
    except AppError as error:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = error.code
        task.errorMessage = error.message
        if isinstance(error, TemplateDomainFailure):
            _apply_template_domain_failure(task, error)
        elif error.code == "template_domain_failed" and error.field:
            task.failedDomains = list(dict.fromkeys([*task.failedDomains, error.field]))
        if task.documentVersionId:
            task.reviewRunId = save_review_run(
                task.id,
                task.documentVersionId,
                rule_version=TEMPLATE_RULE_CATALOG.version,
                model=QWEN_MODEL,
                status="failed",
                timings=task.timings.modelGroupsMs,
            )
        log_event(logging.ERROR, "review.failed", code=error.code, message=error.message, field=error.field, rule_id=error.rule_id)
    except Exception:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = "review_service_failed"
        task.errorMessage = "审查任务处理失败。"
        log_event(logging.ERROR, "review.failed_unexpected", message=task.errorMessage)
        logging.getLogger("bilu").exception("event=review.exception task_id=%s", task_id)
    task.timings.totalMs = round((perf_counter() - total_started) * 1000)
    save_task(task)
    log_event(
        logging.INFO,
        "review.finished",
        status=task.status.value,
        total_ms=task.timings.totalMs,
        parse_ms=task.timings.parseMs,
        model_ms=task.timings.modelReviewMs,
        group_ms=task.timings.modelGroupsMs,
        result_count=len(task.results),
    )
    reset_task_id(context_token)


async def process_demo(task_id: str, demo_id: str) -> None:
    """解析白名单中的真实 DOCX，并按目录指定模式执行审查。

    审查模式由 DemoCase.executionMode 决定：
    - "mock"：使用模拟结果（快速演示，不调用模型）。
    - "qwen"：执行完整的 Qwen 模型审查流程。
    """
    task = get_task(task_id)
    if task is None:
        return
    context_token = set_task_id(task_id)
    case = get_demo_case(demo_id)
    if case is None:
        task.status = TaskStatus.FAILED
        task.errorCode = "demo_not_found"
        task.errorMessage = "演示样例不存在。"
        save_task(task)
        reset_task_id(context_token)
        return
    total_started = perf_counter()
    log_event(logging.INFO, "demo_review.started", demo_id=demo_id, mode=task.mode.value)
    try:
        task.status = TaskStatus.RECOGNIZING
        save_task(task)
        parse_started = perf_counter()
        content = case.path.read_bytes()
        original = save_original(task.id, case.filename, content)
        task.documentId = save_document(
            task.id,
            filename=original.filename,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256=original.sha256,
            original_path=str(original.path),
        )
        original_record_id = save_artifact_record(
            task.id,
            None,
            artifact_type="original",
            filename=original.filename,
            path=str(original.path),
            sha256=original.sha256,
            size_bytes=original.sizeBytes,
            metadata={"source": "demo", "demoId": demo_id},
        )
        task.artifacts = [ArtifactSummary(
            id=original_record_id,
            type="original",
            filename=original.filename,
            sha256=original.sha256,
            sizeBytes=original.sizeBytes,
        )]
        task.requiredArtifacts = list(_REQUIRED_ARTIFACTS)
        task.document = await parse_document(case.filename, content)
        task.documentVersionId = save_document_version(
            task.documentId,
            content_sha256=original.sha256,
            parsed_payload=task.document.model_dump(mode="json"),
        )
        task.timings.parseMs = round((perf_counter() - parse_started) * 1000)
        task.victimProfile = extract_victim_profile(task.document)
        task.status = TaskStatus.CHECKING
        save_task(task)
        model_started = perf_counter()
        group_timings: dict[str, int] = {}
        try:
            if task.mode == ReviewMode.QWEN:
                outcome = await run_template_review(task.document, group_timings=group_timings)
                results = outcome.results
            else:
                results = build_mock_review(task.document)
        finally:
            task.timings.modelReviewMs = round((perf_counter() - model_started) * 1000)
            task.timings.modelGroupsMs = group_timings
        task.status = TaskStatus.VALIDATING
        save_task(task)
        task.results = results
        task.status = TaskStatus.COMPLETED
        if task.mode == ReviewMode.QWEN:
            _persist_outcome(task, outcome)
    except FileNotFoundError:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = "demo_file_missing"
        task.errorMessage = "演示文档暂不可用。"
    except AppError as error:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = error.code
        task.errorMessage = error.message
        if isinstance(error, TemplateDomainFailure):
            _apply_template_domain_failure(task, error)
    except Exception:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = "review_service_failed"
        task.errorMessage = "审查任务处理失败。"
    task.timings.totalMs = round((perf_counter() - total_started) * 1000)
    save_task(task)
    log_event(logging.INFO, "demo_review.finished", status=task.status.value, total_ms=task.timings.totalMs, result_count=len(task.results))
    reset_task_id(context_token)


def _issue_id(task_id: str, rule_id: str) -> str | None:
    """从审计快照中查找指定规则的最近 issue_id。"""
    issues = get_audit_snapshot(task_id)["issues"]
    return next((item["id"] for item in reversed(issues) if item["rule_id"] == rule_id), None)


def _persist_outcome(
    task: ReviewTask,
    outcome: TemplateReviewOutcome,
    *,
    events: list[dict] | None = None,
) -> bool:
    """持久化审查结果到 SQLite。

    保存的内容包括：提取的事实、实体、审查问题、人工事件。
    返回是否成功。
    """
    task.extractionPayload = outcome.extraction.model_dump(mode="json")
    task.failedDomains = list(dict.fromkeys([*task.failedDomains, *outcome.failed_domains]))
    task.domainErrors.update(outcome.domain_errors)
    task.domainErrorDetails.update(outcome.domain_error_details)
    snapshot = get_audit_snapshot(task.id)
    if not task.documentVersionId or not any(
        version["id"] == task.documentVersionId for version in snapshot["versions"]
    ):
        return False
    run_id = persist_review_outcome(
        task,
        task.documentVersionId,
        rule_version=TEMPLATE_RULE_CATALOG.version,
        model=QWEN_MODEL,
        timings=task.timings.modelGroupsMs,
        facts={
            path: fact.model_dump(mode="json")
            for path, fact in outcome.extraction.facts.items()
        },
        entities={
            entity_type: {"items": [entity.model_dump(mode="json") for entity in entities]}
            for entity_type, entities in outcome.extraction.entities.items()
        },
        issues=[
            (issue.ruleId, issue.model_dump(mode="json"))
            for issue in outcome.issues
        ],
        events=events,
    )
    task.reviewRunId = run_id
    return True


def record_issue_action(
    task_id: str,
    rule_id: str,
    status: ManualStatus,
    reason: str,
    actor_id: str,
):
    """记录人工操作并对规则结果做处置。

    Args:
        task_id: 审查任务 ID。
        rule_id: 规则 ID。
        status:  人工处置状态。
        reason:  分流原因或补问内容。
        actor_id: 操作人标识。

    Raises:
        AppError: 任务不存在、未完成、已归档、状态无效等。
    """
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能继续修改。", 409)
    if task.status != TaskStatus.COMPLETED:
        raise AppError("task_not_completed", "任务尚未完成，不能提交人工处理。", 409)
    allowed = {
        ManualStatus.CONFIRMED,
        ManualStatus.SUPPLEMENTED,
        ManualStatus.IGNORED,
        ManualStatus.RESOLVED,
        ManualStatus.NOT_APPLICABLE,
    }
    if status not in allowed:
        raise AppError("invalid_decision", "人工处理状态无效。", 422)
    result = next((item for item in task.results if item.ruleId == rule_id), None)
    if result is None:
        raise AppError("rule_result_not_found", "规则结果不存在。", 404)
    normalized_reason = reason.strip()
    previous = result.manualDecision.model_dump(mode="json")
    result.manualDecision.status = status
    result.manualDecision.reason = normalized_reason
    _invalidate_generated_artifacts(task)
    save_task_with_events(task, [{
        "issue_id": _issue_id(task.id, rule_id),
        "event_type": status,
        "actor_id": actor_id.strip() or "local-operator",
        "payload": {
            "ruleId": rule_id,
            "previous": previous,
            "current": result.manualDecision.model_dump(mode="json"),
        },
    }])
    return result


def pass_demo_review(task_id: str) -> ReviewTask:
    """Close all outstanding issues for a built-in sanitized demo."""
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能继续修改。", 409)
    if task.status != TaskStatus.COMPLETED:
        raise AppError("task_not_completed", "任务尚未完成，不能执行演示处理。", 409)
    if not task.demoId:
        raise AppError("demo_action_not_allowed", "测试通过仅适用于内置脱敏演示。", 409)
    if task.failedDomains:
        raise AppError("demo_has_failed_domains", "仍有抽取失败域，不能执行一键测试通过。", 409)

    actionable = {
        RuleStatus.MISSING,
        RuleStatus.INCOMPLETE,
        RuleStatus.INCONSISTENT,
        RuleStatus.NEEDS_MANUAL_REVIEW,
    }
    terminal = {
        ManualStatus.RESOLVED,
        ManualStatus.NOT_APPLICABLE,
        ManualStatus.IGNORED,
    }
    events = []
    for result in task.results:
        decision = result.manualDecision
        if result.status not in actionable or (
            decision.status in terminal and bool(decision.reason.strip())
        ):
            continue
        previous = decision.model_dump(mode="json")
        result.manualDecision = ManualDecision(
            status=ManualStatus.RESOLVED,
            reason="脱敏演示：一键测试通过",
        )
        events.append({
            "issue_id": _issue_id(task.id, result.ruleId),
            "event_type": ManualStatus.RESOLVED,
            "actor_id": "demo-operator",
            "payload": {
                "ruleId": result.ruleId,
                "previous": previous,
                "current": result.manualDecision.model_dump(mode="json"),
            },
        })

    warning_codes = [warning.code for warning in task.document.warnings] if task.document else []
    newly_acknowledged = [code for code in warning_codes if code not in task.acknowledgedWarnings]
    task.acknowledgedWarnings = list(dict.fromkeys([*task.acknowledgedWarnings, *warning_codes]))
    if newly_acknowledged:
        events.append({
            "issue_id": None,
            "event_type": "warnings_acknowledged",
            "actor_id": "demo-operator",
            "payload": {"codes": newly_acknowledged},
        })
    _invalidate_generated_artifacts(task)
    return save_task_with_events(task, events)


def acknowledge_warnings(task_id: str, codes: list[str], actor_id: str) -> ReviewTask:
    """确认文档解析告警。

    当解析器发现非关键问题（如页眉损坏、不支持的图片格式），
    用户确认后这些告警不再显示。
    """
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能修改告警。", 409)
    available = {warning.code for warning in task.document.warnings} if task.document else set()
    unknown = set(codes) - available
    if unknown:
        raise AppError("warning_not_found", "包含当前文档不存在的告警代码。", 404)
    task.acknowledgedWarnings = list(dict.fromkeys([*task.acknowledgedWarnings, *codes]))
    _invalidate_generated_artifacts(task)
    return save_task_with_events(task, [{
        "issue_id": None,
        "event_type": "warnings_acknowledged",
        "actor_id": actor_id.strip() or "local-operator",
        "payload": {"codes": codes},
    }])


def review_versions(task_id: str) -> list[dict]:
    """获取文档版本历史。"""
    if get_task(task_id) is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return [{
        "id": item["id"],
        "versionNumber": item["version_number"],
        "contentSha256": item["content_sha256"],
        "createdAt": item["created_at"],
    } for item in get_audit_snapshot(task_id)["versions"]]


def artifact_record(task_id: str, artifact_id: str) -> dict:
    """获取产物记录。"""
    if get_task(task_id) is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    record = get_artifact_record(task_id, artifact_id)
    if record is None:
        raise AppError("artifact_not_found", "归档产物不存在。", 404)
    return record


def _append_follow_up(document, question: str, answer: str):
    """将补问对追加到文档末尾，生成新的版本。"""
    updated = document.model_copy(deep=True)
    question_text = f"问：{question.strip()}"
    answer_text = f"答：{answer.strip()}"
    if not updated.pages:
        raise AppError("document_has_no_pages", "当前文档没有可追加补问的页面。", 409)
    offset = len(updated.text) + (1 if updated.text else 0)
    question_id = sha256(f"{updated.id}:{offset}:{question_text}".encode("utf-8")).hexdigest()[:24]
    answer_start = offset + len(question_text) + 1
    answer_id = sha256(f"{updated.id}:{answer_start}:{answer_text}".encode("utf-8")).hexdigest()[:24]
    updated.pages[-1].paragraphs.extend([
        DocumentParagraph(
            id=question_id,
            text=question_text,
            sourceType=SourceType.NATIVE_TEXT,
            charStart=offset,
            charEnd=offset + len(question_text),
        ),
        DocumentParagraph(
            id=answer_id,
            text=answer_text,
            sourceType=SourceType.NATIVE_TEXT,
            charStart=answer_start,
            charEnd=answer_start + len(answer_text),
        ),
    ])
    updated.text = "\n".join(part for part in (updated.text, question_text, answer_text) if part)
    updated.questionAnswers = reconstruct_question_answers(updated.pages)
    updated.id = str(uuid4())
    return updated


async def record_follow_up_answer(
    task_id: str,
    rule_id: str,
    *,
    question: str,
    answer: str,
    actor_id: str,
) -> ReviewTask:
    """记录补问的答案，触发相关域的重新审查。

    当人工补问完成后，调用此函数：
    1. 将补问对追加到文档。
    2. 重新审查受影响域。
    3. 合并新旧人工决策状态。
    """
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能继续修改。", 409)
    if task.status != TaskStatus.COMPLETED or task.document is None or task.documentId is None:
        raise AppError("task_not_completed", "审查文档尚未完成，不能记录补问。", 409)
    result = next((item for item in task.results if item.ruleId == rule_id), None)
    if result is None:
        raise AppError("rule_result_not_found", "规则结果不存在。", 404)
    if not question.strip() or not answer.strip():
        raise AppError("follow_up_answer_required", "实际补问和答案均不能为空。", 422)
    starting_revision = task.revision
    previous_results = task.results
    updated_document = _append_follow_up(task.document, question, answer)
    domain = _GROUP_DOMAINS.get(result.group)
    if domain is None:
        raise AppError("unknown_rule_domain", "无法确定该问题所属的复核业务域。", 500)
    if task.mode == ReviewMode.MOCK:
        task.results = build_mock_review(updated_document)
        refreshed = next((item for item in task.results if item.ruleId == rule_id), None)
        if refreshed is not None:
            refreshed.status = RuleStatus.COVERED
            refreshed.missingFacts = []
            refreshed.reason = "已记录实际补问和答案，快速演示复核已覆盖该模板要求。"
            refreshed.suggestedQuestion = ""
    else:
        base = CaseExtraction.model_validate(task.extractionPayload or {})
        outcome = await run_template_review(
            updated_document,
            group_timings=task.timings.modelGroupsMs,
            domains=(domain,),
            base_extraction=base,
        )
        task.results = outcome.results
    latest = get_task(task.id)
    if latest is None or latest.revision != starting_revision:
        raise AppError("task_revision_conflict", "审查任务已被其他操作更新，请刷新后重试。", 409)
    if latest.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能继续修改。", 409)
    task.documentVersionId = save_document_version(
        task.documentId,
        content_sha256=sha256(updated_document.text.encode("utf-8")).hexdigest(),
        parsed_payload=updated_document.model_dump(mode="json"),
    )
    task.document = updated_document
    invalidated = _merge_manual_decisions(
        previous_results,
        task.results,
        affected_domains={domain},
        resolved_rule_id=rule_id,
    )
    refreshed = next((item for item in task.results if item.ruleId == rule_id), None)
    if refreshed is not None:
        refreshed.manualDecision = ManualDecision(
            status=ManualStatus.RESOLVED,
            reason="已记录实际补问和答案并完成受影响域复核。",
        )
    _invalidate_generated_artifacts(task)
    events: list[dict] = []
    if invalidated:
        events.append({
            "issue_id": None,
            "event_type": "decisions_invalidated",
            "actor_id": actor_id.strip() or "local-operator",
            "payload": {"domain": domain, "ruleIds": invalidated},
        })
    events.append({
        "issue_id": _issue_id(task.id, rule_id),
        "event_type": "follow_up_answer",
        "actor_id": actor_id.strip() or "local-operator",
        "payload": {"ruleId": rule_id, "question": question.strip(), "answer": answer.strip(), "documentVersionId": task.documentVersionId},
    })
    if task.mode != ReviewMode.MOCK:
        if _persist_outcome(task, outcome, events=events):
            return task
    return save_task_with_events(task, events)


async def retry_failed_domain(task_id: str, domain: str, actor_id: str) -> ReviewTask:
    """重试失败的模型抽取业务域。

    当某个域因网络或模型错误失败时，可以单独重试该域，
    而不需要重新审查整个文档。
    """
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能重试。", 409)
    if domain not in task.failedDomains:
        raise AppError("domain_not_failed", "该业务域当前不在失败列表中。", 409)
    if task.document is None:
        raise AppError("document_not_available", "审查文档不可用，无法重试。", 409)
    starting_revision = task.revision
    previous_results = task.results
    base = CaseExtraction.model_validate(task.extractionPayload or {})
    missing_before = _missing_extraction_domains(base)
    retry_domains = DOMAIN_ORDER if set(missing_before) == set(DOMAIN_ORDER) else (domain,)
    outcome = await run_template_review(
        task.document,
        group_timings=task.timings.modelGroupsMs,
        domains=retry_domains,
        base_extraction=base,
    )
    latest = get_task(task.id)
    if latest is None or latest.revision != starting_revision:
        raise AppError("task_revision_conflict", "审查任务已被其他操作更新，请刷新后重试。", 409)
    if latest.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能重试。", 409)
    missing_after = _missing_extraction_domains(outcome.extraction)
    completed = not missing_after and len(outcome.results) == len(TEMPLATE_RULE_CATALOG.rules)
    task.results = outcome.results if completed else []
    task.failedDomains = missing_after
    task.status = TaskStatus.COMPLETED if completed else TaskStatus.FAILED
    task.errorCode = None if not task.failedDomains else task.errorCode
    task.errorMessage = None if not task.failedDomains else task.errorMessage
    invalidated = _merge_manual_decisions(
        previous_results,
        task.results,
        affected_domains=set(retry_domains),
    )
    _invalidate_generated_artifacts(task)
    events: list[dict] = []
    if invalidated:
        events.append({
            "issue_id": None,
            "event_type": "decisions_invalidated",
            "actor_id": actor_id.strip() or "local-operator",
            "payload": {"domain": domain, "ruleIds": invalidated},
        })
    events.append({
        "issue_id": None,
        "event_type": "domain_retried",
        "actor_id": actor_id.strip() or "local-operator",
        "payload": {"domain": domain, "completed": completed},
    })
    if completed:
        if _persist_outcome(task, outcome, events=events):
            return task
    return save_task_with_events(task, events)


def update_decision(task_id: str, rule_id: str, status: ManualStatus, reason: str):
    """人工分流 — 对某条规则结果做出处置决策。

    Args:
        task_id: 审查任务 ID。
        rule_id: 规则 ID。
        status:  人工处置状态（CONFIRMED / SUPPLEMENTED / IGNORED）。
        reason:  分流原因或补问内容。

    Raises:
        AppError: 任务不存在、未完成、状态无效、规则结果不存在。
    """
    return record_issue_action(task_id, rule_id, status, reason, "local-operator")


def complete_review(task_id: str) -> ReviewTask:
    """完成复核 — 将任务置为 ARCHIVED 状态。

    前置条件：
    - 所有 missing/incomplete 的规则项必须完成人工分流（不可有 PENDING）。
    - 否则抛出 409 并告知剩余待处置数量。

    Returns:
        更新后的 ReviewTask（reviewStatus = ARCHIVED）。
    """
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.documentVersionId:
        assert_archive_ready(task)
        from app.reporting.reports import generate_review_artifacts
        task = generate_review_artifacts(task_id)
    else:
        pending = [
            item for item in task.results
            if item.status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE}
            and item.manualDecision.status == ManualStatus.PENDING
        ]
        if pending:
            raise AppError("review_has_pending_results", f"还有 {len(pending)} 项待处置。", 409)
    task.reviewStatus = ReviewStatus.ARCHIVED
    task.archivedAt = now_iso()
    return save_task_with_events(task, [{
        "issue_id": None,
        "event_type": "archived",
        "actor_id": "local-operator",
        "payload": {"archivedAt": task.archivedAt},
    }])


def review_history() -> list[dict]:
    """返回所有审查任务的历史摘要列表（按更新时间降序）。"""
    return [{
        "id": task.id,
        "documentName": task.document.name if task.document else "未命名笔录",
        "createdAt": task.createdAt,
        "updatedAt": task.updatedAt,
        "reviewStatus": task.reviewStatus,
        "pendingCount": sum(
            1 for item in task.results
            if item.status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE}
            and item.manualDecision.status == ManualStatus.PENDING
        ),
    } for task in list_tasks()]


def follow_ups(task_id: str):
    """获取指定任务的补问清单（人工标记为 SUPPLEMENTED 的规则项）。"""
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return [item for item in task.results if item.manualDecision.status == ManualStatus.SUPPLEMENTED]


def report_data(task_id: str) -> dict:
    """获取审查报告所需的全部数据。"""
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return {
        "id": task.id,
        "document": task.document,
        "victimProfile": task.victimProfile,
        "mode": task.mode,
        "createdAt": task.createdAt,
        "archivedAt": task.archivedAt,
        "reviewStatus": task.reviewStatus,
        "results": task.results,
    }
    save_artifact_record,
    save_document,
