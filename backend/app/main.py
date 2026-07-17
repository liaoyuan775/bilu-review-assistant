"""
API 路由层 — FastAPI 应用入口，定义全部 HTTP 端点。

端点概览：
  GET    /api/v1/health               — 健康检查与 Qwen 连通性
  GET    /api/v1/rules                — 规则列表
  GET    /api/v1/demos                — 演示样例列表
  POST   /api/v1/reviews              — 上传文件并发起审查（异步）
  POST   /api/v1/reviews/demos/{id}   — 对演示样例发起审查（异步）
  GET    /api/v1/reviews              — 审查历史列表
  GET    /api/v1/reviews/{id}         — 任务详情
  POST   /api/v1/reviews/{id}/complete     — 完成复核并归档
  GET    /api/v1/reviews/{id}/follow-ups    — 补问清单
  GET    /api/v1/reviews/{id}/report-data   — 审查报告数据
  PATCH  /api/v1/reviews/{id}/results/{rid}/decision — 人工分流决策

错误处理：
- 所有已知业务异常通过 AppError 抛出，由统一异常处理器捕获。
- 非预期的 Exception 由 FastAPI 默认处理（返回 500）。
"""

import logging

from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import FRONTEND_ORIGIN, MAX_FILE_SIZE, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.data import RULES
from app.demo_cases import DEMO_CASES, get_demo_case, load_demo_document
from app.development_logging import configure_logging, log_event
from app.errors import AppError
from app.models import (
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
)
from app.services.qwen import check_qwen
from app.services.review import complete_review, create_task, follow_ups, process_demo, process_upload, report_data, review_history, update_decision
from app.store import get_task


configure_logging()
app = FastAPI(title="Bilu Review API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, error: AppError):
    """统一的应用级异常处理器 — 将 AppError 转为结构化 JSON 响应。"""
    log_event(logging.WARNING, "api.app_error", code=error.code, status_code=error.status_code, message=error.message)
    return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code, "message": error.message}})


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    """健康检查端点 — 返回服务状态、Qwen 连接状态与规则数量。"""
    reachable = await check_qwen()
    return {
        "ok": True,
        "qwen": {"configured": bool(QWEN_BASE_URL and QWEN_API_KEY and QWEN_MODEL), "reachable": reachable, "model": QWEN_MODEL or None},
        "ruleCount": len(RULES),
    }


@app.get("/api/v1/rules", response_model=RuleListResponse)
async def list_rules():
    """返回"三现四流"完整规则列表（供前端规则管理页使用）。"""
    return {"rules": [{
        "id": rule["id"], "name": rule["name"], "category": rule["category"], "group": rule["group"],
        "scope": rule["scope"], "requiredFacts": [fact["label"] for fact in rule["requiredFacts"]],
        "source": rule["source"],
    } for rule in RULES]}


@app.get("/api/v1/demos", response_model=DemoListResponse)
async def list_demos():
    """返回脱敏演示样例列表。"""
    demos = []
    for case in DEMO_CASES:
        page_count = (await load_demo_document(case)).pageCount if case.path.is_file() else 0
        demos.append({
            "id": case.id,
            "name": case.filename,
            "pageCount": page_count,
            "intent": case.intent,
            "executionMode": case.executionMode,
        })
    return {"demos": demos}


@app.post("/api/v1/reviews", status_code=202, response_model=CreateTaskResponse)
async def create_upload_review(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """上传文件并发起异步审查任务。

    在后台任务中执行：解析 → OCR → 模型审查 → 证据校验。
    前端通过轮询 GET /api/v1/reviews/{task_id} 获取进度。
    """
    content = await file.read(MAX_FILE_SIZE + 1)
    log_event(
        logging.INFO,
        "upload.received",
        filename=file.filename or "unnamed",
        content_type=file.content_type or "unknown",
        bytes=len(content),
    )
    if len(content) > MAX_FILE_SIZE:
        raise AppError("file_too_large", "文件超过 20 MB 限制。", 413)
    task = create_task(ReviewMode.QWEN)
    log_event(logging.INFO, "upload.task_created", task_id_created=task.id, mode=task.mode.value)
    background_tasks.add_task(process_upload, task.id, file.filename or "unnamed", content)
    return {"taskId": task.id, "status": task.status}


@app.post("/api/v1/reviews/demos/{demo_id}", status_code=202, response_model=CreateTaskResponse)
async def create_demo_review(demo_id: str, background_tasks: BackgroundTasks):
    """按服务端案例目录指定的执行模式发起演示审查。"""
    case = get_demo_case(demo_id)
    if case is None:
        raise AppError("demo_not_found", "演示样例不存在。", 404)
    if not case.path.is_file():
        raise AppError("demo_file_missing", "演示文档暂不可用。", 503)
    mode = ReviewMode(case.executionMode)
    task = create_task(mode)
    background_tasks.add_task(process_demo, task.id, demo_id)
    return {"taskId": task.id, "status": task.status}


@app.get("/api/v1/reviews", response_model=ReviewListResponse)
async def list_reviews():
    """返回审查历史列表（包括未完成的审查）。"""
    return {"reviews": review_history()}


@app.get("/api/v1/reviews/{task_id}", response_model=ReviewTask)
async def review_detail(task_id: str):
    """获取单条审查任务的完整详情（用于前端轮询进度与结果）。"""
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return task


@app.post("/api/v1/reviews/{task_id}/complete", response_model=CompleteReviewResponse)
async def archive_review(task_id: str):
    """完成复核 — 将审查任务置为已归档状态（只读）。"""
    task = complete_review(task_id)
    return {"reviewStatus": task.reviewStatus, "archivedAt": task.archivedAt}


@app.get("/api/v1/reviews/{task_id}/follow-ups", response_model=FollowUpListResponse)
async def review_follow_ups(task_id: str):
    """返回被标记为"补问清单"的规则项列表。"""
    return {"items": follow_ups(task_id)}


@app.get("/api/v1/reviews/{task_id}/report-data", response_model=ReportData)
async def review_report_data(task_id: str):
    """返回审查报告所需的全部数据（打印/导出用）。"""
    return report_data(task_id)


@app.patch("/api/v1/reviews/{task_id}/results/{rule_id}/decision", response_model=DecisionResponse)
async def save_decision(task_id: str, rule_id: str, payload: DecisionRequest):
    """人工分流决策 — 对某条规则结果标记确认/补问/忽略。"""
    return {"result": update_decision(task_id, rule_id, payload.status, payload.reason)}
