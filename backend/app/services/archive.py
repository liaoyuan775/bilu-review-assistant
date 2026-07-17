from app.errors import AppError
from app.models import ManualStatus, ReviewTask, RuleStatus, TaskStatus


_ACTIONABLE = {
    RuleStatus.MISSING,
    RuleStatus.INCOMPLETE,
    RuleStatus.INCONSISTENT,
    RuleStatus.NEEDS_MANUAL_REVIEW,
}


def assert_archive_ready(task: ReviewTask) -> None:
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
    available_artifacts = {artifact.type for artifact in task.artifacts}
    if not set(task.requiredArtifacts).issubset(available_artifacts):
        raise AppError("archive_missing_artifacts", "审查报告、补问清单或结构化产物尚未生成，不能归档。", 409)
    pending_high_risk = [
        result
        for result in task.results
        if result.severity == "high"
        and result.status in _ACTIONABLE
        and not (
            result.manualDecision.status == ManualStatus.RESOLVED
            or result.manualDecision.status == ManualStatus.NOT_APPLICABLE
            or (
                result.manualDecision.status == ManualStatus.IGNORED
                and bool(result.manualDecision.reason.strip())
            )
        )
    ]
    if pending_high_risk:
        raise AppError("archive_pending_high_risk", f"仍有 {len(pending_high_risk)} 个高风险问题未闭环。", 409)
