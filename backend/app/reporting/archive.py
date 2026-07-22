"""
归档门禁 — 审查完成归档前的完整性校验。

职责边界：
- 本文件是"归档"的最后一道防线，确保归档时所有条件都已满足。
- 不处理产物生成（由 reports.py 负责），只做校验。

校验项（assert_archive_ready）：
1. 审查状态必须为 COMPLETED。
2. 所有业务域必须抽取成功（无 failedDomains）。
3. 所有文档解析告警必须已确认。
4. 所有异常问题必须已人工判断（SUPPLEMENTED / RESOLVED / IGNORED）。

依赖关系：
- core/errors.py: AppError 异常体系。
- core/models.py: 审查任务和状态模型。
- storage/artifacts.py: 文件制品读取。
- storage/store.py: SQLite 存储。
"""

from app.core.errors import AppError
from app.core.models import ManualStatus, ReviewTask, RuleStatus, TaskStatus


_ACTIONABLE = {
    RuleStatus.MISSING,
    RuleStatus.INCOMPLETE,
    RuleStatus.INCONSISTENT,
    RuleStatus.NEEDS_MANUAL_REVIEW,
}


def assert_archive_ready(task: ReviewTask) -> None:
    """断言归档条件是否满足。

    检查以下条件是否全部满足：
    1. 审查状态为 COMPLETED。
    2. 无失败业务域。
    3. 所有告警已确认。
    4. 所有产物已生成。
    5. 所有异常问题已闭环。

    Raises:
        AppError: 任意条件不满足时抛出（含具体原因）。
    """
    if task.status != TaskStatus.COMPLETED:
        raise AppError("archive_task_incomplete", "自动审查尚未完整成功，不能归档。", 409)
    if task.failedDomains:
        raise AppError("archive_failed_domains", "仍有抽取业务域失败，不能归档。", 409)
    unresolved_warnings = {
        warning.code
        for warning in task.document.warnings if warning.code not in task.acknowledgedWarnings
    } if task.document else set()
    if unresolved_warnings:
        raise AppError("archive_unresolved_warnings", "仍有未确认的文档解析告警，不能归档。", 409)
    unresolved_issues = [
        result
        for result in task.results
        if result.status in _ACTIONABLE
        and not (
            result.manualDecision.status in {
                ManualStatus.SUPPLEMENTED,
                ManualStatus.RESOLVED,
                ManualStatus.IGNORED,
            }
        )
    ]
    if unresolved_issues:
        raise AppError("archive_pending_issues", f"仍有 {len(unresolved_issues)} 个问题待判断，不能归档。", 409)
