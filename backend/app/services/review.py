"""
审查编排层 — 任务生命周期管理、异步处理与人工分流。

职责边界：
- create_task:      创建任务并持久化（状态 = PARSING）。
- process_upload:   完整的异步审查流程（解析 → OCR → 模型 → 校验）。
- process_demo:     解析白名单 DOCX，再按目录执行模拟结果或模型审查。
- update_decision:  人工分流（确认/补问/忽略）。
- complete_review:  完成复核并归档（所有待处置项必须已分流）。
- follow_ups:       获取补问清单。
- report_data:      获取审查报告数据。
- review_history:   获取历史列表。

异常处理：
- AppError 被精确捕获，set 到 task.errorCode/errorMessage。
- 非预期的 Exception 以 "review_service_failed" 兜底。
- 在任何步骤失败后，任务状态被置为 FAILED 并持久化。

时序记录：
- 使用 perf_counter 精确记录解析、模型、总耗时。
- 即使模型审查失败，仍记录已完成的阶段耗时。
"""

import logging
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from app.demo_cases import get_demo_case
from app.config import QWEN_MODEL
from app.data import TEMPLATE_RULE_CATALOG
from app.development_logging import log_event, log_payload, reset_task_id, set_task_id
from app.errors import AppError
from app.models import ArtifactSummary, DocumentParagraph, ManualDecision, ManualStatus, ReviewMode, ReviewStatus, ReviewTask, RuleStatus, SourceType, TaskStatus, now_iso
from app.services.archive import assert_archive_ready, verify_archive_artifacts
from app.services.artifacts import GENERATED_REVIEW_ARTIFACT_TYPES, save_original
from app.services.question_answer import reconstruct_question_answers
from app.services.mock_review import build_mock_review
from app.services.parser import parse_document
from app.services.template_extraction import TemplateReviewOutcome, review_template_document, run_template_review
from app.services.victim_profile import extract_victim_profile
from app.template_models import CaseExtraction
from app.store import (
    append_manual_event,
    get_audit_snapshot,
    get_artifact_record,
    get_task,
    list_tasks,
    save_artifact_record,
    save_document,
    save_document_version,
    save_extracted_fact,
    save_review_issue,
    save_review_run,
    save_task,
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
    "EXTRA": "special_scenarios",
}

_REQUIRED_ARTIFACTS = list(GENERATED_REVIEW_ARTIFACT_TYPES)


def _invalidate_generated_artifacts(task: ReviewTask) -> None:
    task.requiredArtifacts = list(GENERATED_REVIEW_ARTIFACT_TYPES)
    task.artifacts = [item for item in task.artifacts if item.type == "original"]


def create_task(mode: ReviewMode) -> ReviewTask:
    """创建新的审查任务并持久化。

    Args:
        mode: 审查模式（QWEN、MOCK，或历史兼容的 LOCAL）。

    Returns:
        已保存的 ReviewTask 实例（status = PARSING）。
    """
    return save_task(ReviewTask(mode=mode))


async def process_upload(task_id: str, filename: str, content: bytes) -> None:
    """处理文件上传后的异步审查流程。

    执行步骤（严格顺序）：
    1. RECOGNIZING — 调用 parser 解析文档格式。
    2. CHECKING   — 调用 victim_profile 提取被害人信息。
                   按模板业务域调用 Qwen 提取带锚点事实。
    3. VALIDATING — 使用版本化模板规则确定性校验事实与证据。
    4. COMPLETED  — 审查完成。

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
        task.victimProfile = extract_victim_profile(task.document.text)
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
        _persist_outcome(task, outcome)
        task.status = TaskStatus.COMPLETED
        log_payload("review.results_merged", [result.model_dump(mode="json") for result in task.results], rules=len(task.results))
    except AppError as error:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = error.code
        task.errorMessage = error.message
        if error.code == "template_domain_failed" and error.field:
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
    """解析白名单中的真实 DOCX，并按目录指定模式执行审查。"""
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
        task.victimProfile = extract_victim_profile(task.document.text)
        task.status = TaskStatus.CHECKING
        save_task(task)
        model_started = perf_counter()
        group_timings: dict[str, int] = {}
        try:
            if task.mode == ReviewMode.QWEN:
                outcome = await run_template_review(task.document, group_timings=group_timings)
                results = outcome.results
                _persist_outcome(task, outcome)
            else:
                results = build_mock_review(task.document)
        finally:
            task.timings.modelReviewMs = round((perf_counter() - model_started) * 1000)
            task.timings.modelGroupsMs = group_timings
        task.status = TaskStatus.VALIDATING
        save_task(task)
        task.results = results
        task.status = TaskStatus.COMPLETED
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
    issues = get_audit_snapshot(task_id)["issues"]
    return next((item["id"] for item in reversed(issues) if item["rule_id"] == rule_id), None)


def _persist_outcome(task: ReviewTask, outcome: TemplateReviewOutcome) -> None:
    task.extractionPayload = outcome.extraction.model_dump(mode="json")
    snapshot = get_audit_snapshot(task.id)
    if not task.documentVersionId or not any(
        version["id"] == task.documentVersionId for version in snapshot["versions"]
    ):
        return
    run_id = save_review_run(
        task.id,
        task.documentVersionId,
        rule_version=TEMPLATE_RULE_CATALOG.version,
        model=QWEN_MODEL,
        status="completed",
        timings=task.timings.modelGroupsMs,
    )
    task.reviewRunId = run_id
    for path, fact in outcome.extraction.facts.items():
        save_extracted_fact(run_id, path, fact.model_dump(mode="json"))
    for entity_type, entities in outcome.extraction.entities.items():
        save_extracted_fact(
            run_id,
            f"entities.{entity_type}",
            {"items": [entity.model_dump(mode="json") for entity in entities]},
        )
    for issue in outcome.issues:
        save_review_issue(run_id, issue.ruleId, issue.model_dump(mode="json"))


def record_issue_action(
    task_id: str,
    rule_id: str,
    status: ManualStatus,
    reason: str,
    actor_id: str,
):
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
    if status in {ManualStatus.IGNORED, ManualStatus.RESOLVED, ManualStatus.NOT_APPLICABLE} and not normalized_reason:
        raise AppError("decision_reason_required", "该处理动作必须填写依据。", 422)
    previous = result.manualDecision.model_dump(mode="json")
    result.manualDecision.status = status
    result.manualDecision.reason = normalized_reason
    _invalidate_generated_artifacts(task)
    append_manual_event(
        task.id,
        issue_id=_issue_id(task.id, rule_id),
        event_type=status.value,
        actor_id=actor_id.strip() or "local-operator",
        payload={
            "ruleId": rule_id,
            "previous": previous,
            "current": result.manualDecision.model_dump(mode="json"),
        },
    )
    save_task(task)
    return result


def acknowledge_warnings(task_id: str, codes: list[str], actor_id: str) -> ReviewTask:
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
    append_manual_event(
        task.id,
        issue_id=None,
        event_type="warnings_acknowledged",
        actor_id=actor_id.strip() or "local-operator",
        payload={"codes": codes},
    )
    return save_task(task)


def review_versions(task_id: str) -> list[dict]:
    if get_task(task_id) is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return [{
        "id": item["id"],
        "versionNumber": item["version_number"],
        "contentSha256": item["content_sha256"],
        "createdAt": item["created_at"],
    } for item in get_audit_snapshot(task_id)["versions"]]


def artifact_record(task_id: str, artifact_id: str) -> dict:
    if get_task(task_id) is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    record = get_artifact_record(task_id, artifact_id)
    if record is None:
        raise AppError("artifact_not_found", "归档产物不存在。", 404)
    return record


def _append_follow_up(document, question: str, answer: str):
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
    updated_document = _append_follow_up(task.document, question, answer)
    task.documentVersionId = save_document_version(
        task.documentId,
        content_sha256=sha256(updated_document.text.encode("utf-8")).hexdigest(),
        parsed_payload=updated_document.model_dump(mode="json"),
    )
    task.document = updated_document
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
        _persist_outcome(task, outcome)
    refreshed = next((item for item in task.results if item.ruleId == rule_id), None)
    if refreshed is not None:
        refreshed.manualDecision = ManualDecision(
            status=ManualStatus.RESOLVED,
            reason="已记录实际补问和答案并完成受影响域复核。",
        )
    _invalidate_generated_artifacts(task)
    append_manual_event(
        task.id,
        issue_id=_issue_id(task.id, rule_id),
        event_type="follow_up_answer",
        actor_id=actor_id.strip() or "local-operator",
        payload={"ruleId": rule_id, "question": question.strip(), "answer": answer.strip(), "documentVersionId": task.documentVersionId},
    )
    return save_task(task)


async def retry_failed_domain(task_id: str, domain: str, actor_id: str) -> ReviewTask:
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.reviewStatus == ReviewStatus.ARCHIVED:
        raise AppError("review_archived", "已归档审查为只读，不能重试。", 409)
    if domain not in task.failedDomains:
        raise AppError("domain_not_failed", "该业务域当前不在失败列表中。", 409)
    if task.document is None:
        raise AppError("document_not_available", "审查文档不可用，无法重试。", 409)
    base = CaseExtraction.model_validate(task.extractionPayload or {})
    outcome = await run_template_review(
        task.document,
        group_timings=task.timings.modelGroupsMs,
        domains=(domain,),
        base_extraction=base,
    )
    task.results = outcome.results
    task.failedDomains = [value for value in task.failedDomains if value != domain]
    task.status = TaskStatus.COMPLETED if not task.failedDomains else TaskStatus.FAILED
    task.errorCode = None if not task.failedDomains else task.errorCode
    task.errorMessage = None if not task.failedDomains else task.errorMessage
    _persist_outcome(task, outcome)
    _invalidate_generated_artifacts(task)
    append_manual_event(
        task.id,
        issue_id=None,
        event_type="domain_retried",
        actor_id=actor_id.strip() or "local-operator",
        payload={"domain": domain, "completed": not task.failedDomains},
    )
    return save_task(task)


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
        verify_archive_artifacts(task)
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
    append_manual_event(
        task.id,
        issue_id=None,
        event_type="archived",
        actor_id="local-operator",
        payload={"archivedAt": task.archivedAt},
    )
    return save_task(task)


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
