"""
API 路由定义 — FastAPI 应用的全部 HTTP 端点。

端点概览：
  GET    /api/v1/health                          — 健康检查与 Qwen 连通性
  GET    /api/v1/rules                           — 规则列表
  GET    /api/v1/demos                           — 演示样例列表
  POST   /api/v1/reviews                         — 上传文件并发起审查（异步）
  POST   /api/v1/reviews/demos/{id}              — 对演示样例发起审查（异步）
  GET    /api/v1/reviews                         — 审查历史列表
  GET    /api/v1/reviews/{id}                    — 任务详情
  GET    /api/v1/reviews/{id}/versions           — 文档版本历史
  POST   /api/v1/reviews/{id}/issues/{rid}/actions       — 人工操作
  POST   /api/v1/reviews/{id}/domains/{domain}/retry     — 重试域
  POST   /api/v1/reviews/{id}/warnings/acknowledge       — 确认告警
  POST   /api/v1/reviews/{id}/artifacts/generate         — 生成产物
  GET    /api/v1/reviews/{id}/artifacts/{aid}            — 下载产物
  POST   /api/v1/reviews/{id}/complete           — 完成复核
  POST   /api/v1/reviews/{id}/archive            — 归档（别名）
  GET    /api/v1/reviews/{id}/follow-ups         — 补问清单
  GET    /api/v1/reviews/{id}/report-data        — 报告数据
  PATCH  /api/v1/reviews/{id}/results/{rid}/decision     — 人工分流

错误处理：
- 所有已知业务异常通过 AppError 抛出，由 main.py 中的统一异常处理器捕获。
- 非预期的 Exception 由 FastAPI 默认处理（返回 500）。
"""

import logging
from urllib.parse import quote

from fastapi import BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse, Response

from app.core.config import APP_ENV, FRONTEND_ORIGIN, MAX_FILE_SIZE, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.data.rules import TEMPLATE_RULE_CATALOG, TEMPLATE_RULES
from app.data.demo_cases import DEMO_CASES, get_demo_case, load_demo_document
from app.core.development_logging import log_event
from app.core.errors import AppError
from app.core.models import (
    CreateTaskResponse,
    CompleteReviewResponse,
    DecisionRequest,
    DecisionResponse,
    DemoListResponse,
    HealthResponse,
    FollowUpListResponse,
    ReportData,
    ReviewListResponse,
    ReviewMode,
    ReviewTask,
    RuleListResponse,
    IssueActionRequest,
    RetryDomainRequest,
    WarningAcknowledgementRequest,
)
from app.storage.artifacts import read_artifact_record
from app.llm.qwen import check_qwen
from app.reporting.reports import generate_review_artifacts
from app.review.review import (
    acknowledge_warnings,
    artifact_record,
    complete_review,
    create_task,
    follow_ups,
    pass_demo_review,
    process_demo,
    process_upload,
    record_issue_action,
    report_data,
    retry_failed_domain,
    review_history,
    review_versions,
    update_decision,
)
from app.storage.store import get_task


# ═══════════════════════════════════════════════════════════
# 健康检查与元数据
# ═══════════════════════════════════════════════════════════

async def health():
    """健康检查端点 — 返回环境信息、服务状态、Qwen 连接状态与规则数量。"""
    import sys
    reachable = await check_qwen()
    return {
        "ok": True,
        "env": {
            "name": APP_ENV,
            "python": sys.version.split()[0],
        },
        "qwen": {
            "configured": bool(QWEN_BASE_URL and QWEN_API_KEY and QWEN_MODEL),
            "endpoint": QWEN_BASE_URL or None,
            "model": QWEN_MODEL or None,
            "reachable": reachable,
        },
        "ruleCount": len(TEMPLATE_RULES),
    }


async def list_rules():
    """返回内部询问笔录模板派生的版本化规则目录。"""
    return {"rules": [{
        "id": rule.ruleId,
        "name": rule.name,
        "category": rule.group,
        "group": rule.group,
        "scope": rule.scope,
        "requiredFacts": rule.requiredFields,
        "source": f"内部询问笔录模板 v{TEMPLATE_RULE_CATALOG.version}",
    } for rule in TEMPLATE_RULES]}


async def list_demos():
    """返回脱敏演示样例列表。"""
    demos = []
    for case in DEMO_CASES:
        page_count = (await load_demo_document(case)).pageCount if case.path.is_file() else 0
        demos.append({
            "id": case.id,
            "name": case.display_name,
            "pageCount": page_count,
            "intent": case.intent,
            "executionMode": case.executionMode,
        })
    return {"demos": demos}


# ═══════════════════════════════════════════════════════════
# 审查任务 CRUD
# ═══════════════════════════════════════════════════════════

async def create_upload_review(
    background_tasks: BackgroundTasks,  # 背景任务对象，用于添加异步任务
    file: UploadFile = File(...),  # 文件上传对象，使用File装饰器标记为必需参数
):
    """上传文件并发起异步审查任务。

    在后台任务中执行：解析 → OCR → 模型审查 → 证据校验。
    前端通过轮询 GET /api/v1/reviews/{task_id} 获取进度。
    """
    content = await file.read(MAX_FILE_SIZE + 1)  # 读取文件内容，多读取1字节用于判断是否超出大小限制
    log_event(  # 记录文件上传事件
        logging.INFO,
        "upload.received",
        filename=file.filename or "unnamed",  # 如果文件名不存在则使用"unnamed"
        content_type=file.content_type or "unknown",  # 如果内容类型不存在则使用"unknown"
        bytes=len(content),  # 记录文件字节数
    )
    if len(content) > MAX_FILE_SIZE:  # 检查文件大小是否超过限制
        raise AppError("file_too_large", "文件超过 20 MB 限制。", 413)  # 抛出应用错误，状态码413表示请求实体过大
    task = create_task(ReviewMode.QWEN)  # 创建审查任务，使用QWEN模式
    log_event(logging.INFO, "upload.task_created", task_id_created=task.id, mode=task.mode.value)
    background_tasks.add_task(process_upload, task.id, file.filename or "unnamed", content)
    return {"taskId": task.id, "status": task.status}


async def create_demo_review(demo_id: str, background_tasks: BackgroundTasks):
    """按服务端案例目录指定的执行模式发起演示审查。"""
    case = get_demo_case(demo_id)
    if case is None:
        raise AppError("demo_not_found", "演示样例不存在。", 404)
    if not case.path.is_file():
        raise AppError("demo_file_missing", "演示文档暂不可用。", 503)
    mode = ReviewMode(case.executionMode)
    task = create_task(mode, demo_id=demo_id)
    background_tasks.add_task(process_demo, task.id, demo_id)
    return {"taskId": task.id, "status": task.status}


async def list_reviews():
    """返回审查历史列表（包括未完成的审查）。"""
    return {"reviews": review_history()}


async def review_detail(task_id: str):
    """获取单条审查任务的完整详情（用于前端轮询进度与结果）。"""
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return task


async def list_review_versions(task_id: str):
    return {"versions": review_versions(task_id)}


# ═══════════════════════════════════════════════════════════
# 人工操作与处置
# ═══════════════════════════════════════════════════════════

async def save_issue_action(task_id: str, rule_id: str, payload: IssueActionRequest):
    return {"result": record_issue_action(task_id, rule_id, payload.status, payload.reason, payload.actorId)}


async def retry_review_domain(task_id: str, domain: str, payload: RetryDomainRequest):
    return await retry_failed_domain(task_id, domain, payload.actorId)


async def acknowledge_review_warnings(task_id: str, payload: WarningAcknowledgementRequest):
    return acknowledge_warnings(task_id, payload.codes, payload.actorId)


# ═══════════════════════════════════════════════════════════
# 产物生成与下载
# ═══════════════════════════════════════════════════════════

async def generate_artifacts(task_id: str):
    return generate_review_artifacts(task_id)


async def demo_pass_review(task_id: str):
    pass_demo_review(task_id)
    return generate_review_artifacts(task_id)


async def download_review_artifact(task_id: str, artifact_id: str):
    record = artifact_record(task_id, artifact_id)
    content = read_artifact_record(record)
    filename = record["filename"]
    media_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".json": "application/json",
    }.get("." + filename.rsplit(".", 1)[-1].lower() if "." in filename else "", "application/octet-stream")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════
# 完成与归档
# ═══════════════════════════════════════════════════════════

async def archive_review(task_id: str):
    """完成复核 — 将审查任务置为已归档状态（只读）。"""
    task = complete_review(task_id)
    return {"reviewStatus": task.reviewStatus, "archivedAt": task.archivedAt}


async def archive_review_v2(task_id: str):
    task = complete_review(task_id)
    return {"reviewStatus": task.reviewStatus, "archivedAt": task.archivedAt}


async def review_follow_ups(task_id: str):
    """返回被标记为"补问清单"的规则项列表。"""
    return {"items": follow_ups(task_id)}


async def review_report_data(task_id: str):
    """返回审查报告所需的全部数据（打印/导出用）。"""
    return report_data(task_id)


async def save_decision(task_id: str, rule_id: str, payload: DecisionRequest):
    """人工分流决策 — 对某条规则结果标记确认/补问/忽略。"""
    return {"result": update_decision(task_id, rule_id, payload.status, payload.reason)}
