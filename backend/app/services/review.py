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
from time import perf_counter

from app.demo_cases import get_demo_case, load_demo_document
from app.development_logging import log_event, log_payload, reset_task_id, set_task_id
from app.errors import AppError
from app.models import ManualStatus, ReviewMode, ReviewStatus, ReviewTask, RuleStatus, TaskStatus, now_iso
from app.services.mock_review import build_mock_review
from app.services.parser import parse_document
from app.services.qwen import review_with_qwen
from app.services.template_extraction import review_template_document
from app.services.victim_profile import extract_victim_profile
from app.store import get_task, list_tasks, save_task


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
        task.status = TaskStatus.RECOGNIZING
        save_task(task)
        log_event(logging.INFO, "review.status_changed", status=task.status.value)
        parse_started = perf_counter()
        task.document = await parse_document(filename, content)
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
            results = await review_template_document(task.document, group_timings=group_timings)
        finally:
            task.timings.modelReviewMs = round((perf_counter() - model_started) * 1000)
            task.timings.modelGroupsMs = group_timings
            log_event(logging.INFO, "review.model_complete", duration_ms=task.timings.modelReviewMs, group_durations_ms=group_timings)
        task.status = TaskStatus.VALIDATING
        save_task(task)
        log_event(logging.INFO, "review.status_changed", status=task.status.value)
        task.results = results
        task.status = TaskStatus.COMPLETED
        log_payload("review.results_merged", [result.model_dump(mode="json") for result in results], rules=len(results))
    except AppError as error:
        task.status = TaskStatus.FAILED
        task.results = []
        task.errorCode = error.code
        task.errorMessage = error.message
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
        task.document = await load_demo_document(case)
        task.timings.parseMs = round((perf_counter() - parse_started) * 1000)
        task.victimProfile = extract_victim_profile(task.document.text)
        task.status = TaskStatus.CHECKING
        save_task(task)
        model_started = perf_counter()
        group_timings: dict[str, int] = {}
        try:
            results = (
                await review_with_qwen(task.document, group_timings=group_timings)
                if task.mode == ReviewMode.QWEN
                else build_mock_review(task.document)
            )
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
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.status != TaskStatus.COMPLETED:
        raise AppError("task_not_completed", "任务尚未完成，不能提交人工处理。", 409)
    if status not in {ManualStatus.CONFIRMED, ManualStatus.SUPPLEMENTED, ManualStatus.IGNORED}:
        raise AppError("invalid_decision", "人工处理状态无效。", 422)
    result = next((item for item in task.results if item.ruleId == rule_id), None)
    if result is None:
        raise AppError("rule_result_not_found", "规则结果不存在。", 404)
    result.manualDecision.status = status
    result.manualDecision.reason = reason.strip()
    save_task(task)
    return result


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
    pending = [
        item for item in task.results
        if item.status in {RuleStatus.MISSING, RuleStatus.INCOMPLETE}
        and item.manualDecision.status == ManualStatus.PENDING
    ]
    if pending:
        raise AppError("review_has_pending_results", f"还有 {len(pending)} 项待处置。", 409)
    task.reviewStatus = ReviewStatus.ARCHIVED
    task.archivedAt = now_iso()
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
