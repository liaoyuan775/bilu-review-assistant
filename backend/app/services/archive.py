import json

from app.errors import AppError
from app.models import ManualStatus, ReviewTask, RuleStatus, TaskStatus
from app.services.artifacts import read_artifact_record
from app.store import get_artifact_record


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


def verify_archive_artifacts(task: ReviewTask) -> None:
    summaries = {artifact.type: artifact for artifact in task.artifacts}
    contents = {}
    for artifact_type in ["original", *task.requiredArtifacts]:
        summary = summaries.get(artifact_type)
        if summary is None:
            raise AppError("archive_missing_artifacts", "归档产物不完整，不能归档。", 409)
        record = get_artifact_record(task.id, summary.id)
        if record is None:
            raise AppError("artifact_not_found", "归档产物记录不存在。", 404)
        contents[artifact_type] = read_artifact_record(record)
    try:
        manifest = json.loads(contents["archive_manifest"])
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AppError("archive_manifest_invalid", "归档清单无法解析。", 409) from exc
    if manifest.get("documentVersionId") != task.documentVersionId:
        raise AppError("archive_manifest_mismatch", "归档清单与当前文档版本不一致。", 409)
    manifest_hashes = {item.get("type"): item.get("sha256") for item in manifest.get("artifacts", [])}
    for artifact_type in ["original", "review_pdf", "follow_up_docx", "structured_json"]:
        if manifest_hashes.get(artifact_type) != summaries[artifact_type].sha256:
            raise AppError("archive_manifest_mismatch", "归档清单中的产物哈希不一致。", 409)
