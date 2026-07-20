"""
归档门禁 — 审查完成归档前的完整性校验。

职责边界：
- 本文件是"归档"的最后一道防线，确保归档时所有条件都已满足。
- 不处理产物生成（由 reports.py 负责），只做校验。

校验项（assert_archive_ready）：
1. 审查状态必须为 COMPLETED。
2. 所有业务域必须抽取成功（无 failedDomains）。
3. 所有文档解析告警必须已确认。
4. 所有必要产物必须已生成。
5. 所有异常问题必须已人工闭环（RESOLVED / NOT_APPLICABLE / IGNORED+理由）。

校验项（verify_archive_artifacts）：
1. 所有产物在 SQLite 中有对应记录。
2. 归档清单文档版本号与当前一致。
3. 产物的 SHA-256 哈希与归档清单一致。

依赖关系：
- core/errors.py: AppError 异常体系。
- core/models.py: 审查任务和状态模型。
- storage/artifacts.py: 文件制品读取。
- storage/store.py: SQLite 存储。
"""

import json

from app.core.errors import AppError
from app.core.models import ManualStatus, ReviewTask, RuleStatus, TaskStatus
from app.storage.artifacts import read_artifact_record
from app.storage.store import get_artifact_record


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
    available_artifacts = {artifact.type for artifact in task.artifacts}
    if not set(task.requiredArtifacts).issubset(available_artifacts):
        raise AppError("archive_missing_artifacts", "审查报告、补问清单或结构化产物尚未生成，不能归档。", 409)
    unresolved_issues = [
        result
        for result in task.results
        if result.status in _ACTIONABLE
        and not (
            result.manualDecision.status in {
                ManualStatus.RESOLVED,
                ManualStatus.NOT_APPLICABLE,
                ManualStatus.IGNORED,
            }
            and bool(result.manualDecision.reason.strip())
        )
    ]
    if unresolved_issues:
        raise AppError("archive_pending_issues", f"仍有 {len(unresolved_issues)} 个问题未闭环，不能归档。", 409)


def verify_archive_artifacts(task: ReviewTask) -> None:
    """验证归档产物的完整性。

    检查：
    1. 所有产物（源文件 + 生成物）在 SQLite 有记录。
    2. 归档清单的 documentVersionId 匹配。
    3. 所有产物的 SHA-256 与归档清单一致。

    Raises:
        AppError: 任意校验不通过时抛出。
    """
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
