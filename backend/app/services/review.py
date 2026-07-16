from app.data import DEMOS
from app.errors import AppError
from app.models import ManualStatus, ReviewMode, ReviewTask, TaskStatus
from app.services.analyzer import analyze_document
from app.services.parser import parse_document
from app.services.qwen import review_with_qwen
from app.store import get_task, save_task


def create_task(mode: ReviewMode) -> ReviewTask:
    return save_task(ReviewTask(mode=mode))


async def process_upload(task_id: str, filename: str, content: bytes) -> None:
    task = get_task(task_id)
    if task is None:
        return
    try:
        task.status = TaskStatus.RECOGNIZING
        save_task(task)
        task.document = await parse_document(filename, content)
        task.status = TaskStatus.CHECKING
        save_task(task)
        results = await review_with_qwen(task.document)
        task.status = TaskStatus.VALIDATING
        save_task(task)
        task.results = results
        task.status = TaskStatus.COMPLETED
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
    save_task(task)


async def process_demo(task_id: str, demo_id: str) -> None:
    task = get_task(task_id)
    if task is None:
        return
    document = next((item for item in DEMOS if item.id == demo_id), None)
    if document is None:
        task.status = TaskStatus.FAILED
        task.errorCode = "demo_not_found"
        task.errorMessage = "演示样例不存在。"
        save_task(task)
        return
    task.document = document.model_copy(deep=True)
    task.status = TaskStatus.CHECKING
    save_task(task)
    try:
        results = await review_with_qwen(task.document) if task.mode == ReviewMode.QWEN else analyze_document(task.document)
        task.status = TaskStatus.VALIDATING
        save_task(task)
        task.results = results
        task.status = TaskStatus.COMPLETED
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
    save_task(task)


def update_decision(task_id: str, rule_id: str, status: ManualStatus, reason: str):
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    if task.status != TaskStatus.COMPLETED:
        raise AppError("task_not_completed", "任务尚未完成，不能提交人工处理。", 409)
    if status not in {ManualStatus.CONFIRMED, ManualStatus.SUPPLEMENTED, ManualStatus.IGNORED}:
        raise AppError("invalid_decision", "人工处理状态无效。", 422)
    if status == ManualStatus.IGNORED and not reason.strip():
        raise AppError("ignore_reason_required", "忽略原因不能为空。", 422)
    result = next((item for item in task.results if item.ruleId == rule_id), None)
    if result is None:
        raise AppError("rule_result_not_found", "规则结果不存在。", 404)
    result.manualDecision.status = status
    result.manualDecision.reason = reason.strip()
    save_task(task)
    return result
