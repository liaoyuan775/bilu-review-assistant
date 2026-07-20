"""
FastAPI 应用启动入口 — 负责创建应用实例、注册路由和中间件。

本文件不包含业务逻辑，只做：
1. 创建 FastAPI 应用实例。
2. 添加 CORS 中间件。
3. 注册全局异常处理器。
4. 将路由函数挂载到端点路径。
5. 初始化日志配置。

路由函数定义在 api/routes.py 中。
"""

import logging

from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import FRONTEND_ORIGIN, MAX_FILE_SIZE
from app.core.development_logging import configure_logging, log_event
from app.core.errors import AppError
from app.core.models import (
    CreateTaskResponse,
    CompleteReviewResponse,
    DecisionRequest,
    DecisionResponse,
    DemoListResponse,
    FollowUpListResponse,
    FollowUpAnswerRequest,
    HealthResponse,
    ReportData,
    ReviewListResponse,
    ReviewTask,
    RuleListResponse,
    IssueActionRequest,
    RetryDomainRequest,
    WarningAcknowledgementRequest,
)
from app.api.routes import (
    acknowledge_review_warnings,
    archive_review,
    archive_review_v2,
    create_demo_review,
    create_upload_review,
    demo_pass_review,
    download_review_artifact,
    generate_artifacts,
    health,
    list_demos,
    list_reviews,
    list_rules,
    list_review_versions,
    retry_review_domain,
    review_detail,
    review_follow_ups,
    review_report_data,
    save_decision,
    save_follow_up_answer,
    save_issue_action,
)


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


# ── 健康检查与元数据 ────────────────────────────────────────
app.get("/api/v1/health", response_model=HealthResponse)(health)
app.get("/api/v1/rules", response_model=RuleListResponse)(list_rules)
app.get("/api/v1/demos", response_model=DemoListResponse)(list_demos)

# ── 审查任务 CRUD ───────────────────────────────────────────
app.post("/api/v1/reviews", status_code=202, response_model=CreateTaskResponse)(create_upload_review)
app.post("/api/v1/reviews/demos/{demo_id}", status_code=202, response_model=CreateTaskResponse)(create_demo_review)
app.get("/api/v1/reviews", response_model=ReviewListResponse)(list_reviews)
app.get("/api/v1/reviews/{task_id}", response_model=ReviewTask)(review_detail)
app.get("/api/v1/reviews/{task_id}/versions")(list_review_versions)

# ── 人工操作与处置 ──────────────────────────────────────────
app.post("/api/v1/reviews/{task_id}/issues/{rule_id}/actions", response_model=DecisionResponse)(save_issue_action)
app.post("/api/v1/reviews/{task_id}/issues/{rule_id}/follow-up-answer", response_model=ReviewTask)(save_follow_up_answer)
app.post("/api/v1/reviews/{task_id}/domains/{domain}/retry", response_model=ReviewTask)(retry_review_domain)
app.post("/api/v1/reviews/{task_id}/warnings/acknowledge", response_model=ReviewTask)(acknowledge_review_warnings)
app.post("/api/v1/reviews/{task_id}/demo-pass", response_model=ReviewTask)(demo_pass_review)

# ── 产物生成与下载 ──────────────────────────────────────────
app.post("/api/v1/reviews/{task_id}/artifacts/generate", response_model=ReviewTask)(generate_artifacts)
app.get("/api/v1/reviews/{task_id}/artifacts/{artifact_id}")(download_review_artifact)

# ── 完成与归档 ──────────────────────────────────────────────
app.post("/api/v1/reviews/{task_id}/complete", response_model=CompleteReviewResponse)(archive_review)
app.post("/api/v1/reviews/{task_id}/archive", response_model=CompleteReviewResponse)(archive_review_v2)
app.get("/api/v1/reviews/{task_id}/follow-ups", response_model=FollowUpListResponse)(review_follow_ups)
app.get("/api/v1/reviews/{task_id}/report-data", response_model=ReportData)(review_report_data)

# ── 人工分流 ────────────────────────────────────────────────
app.patch("/api/v1/reviews/{task_id}/results/{rule_id}/decision", response_model=DecisionResponse)(save_decision)
