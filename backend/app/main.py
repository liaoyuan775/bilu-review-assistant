from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import FRONTEND_ORIGIN, MAX_FILE_SIZE, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.data import DEMOS, DEMO_INTENTS, RULES
from app.errors import AppError
from app.models import (
    CreateTaskResponse,
    DecisionRequest,
    DecisionResponse,
    DemoListResponse,
    HealthResponse,
    ReviewMode,
    ReviewTask,
    RuleListResponse,
)
from app.services.qwen import check_qwen
from app.services.review import create_task, process_demo, process_upload, update_decision
from app.store import get_task


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
    return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code, "message": error.message}})


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    reachable = await check_qwen()
    return {
        "ok": True,
        "qwen": {"configured": bool(QWEN_BASE_URL and QWEN_API_KEY and QWEN_MODEL), "reachable": reachable, "model": QWEN_MODEL or None},
        "ruleCount": len(RULES),
    }


@app.get("/api/v1/rules", response_model=RuleListResponse)
async def list_rules():
    return {"rules": [{
        "id": rule["id"], "name": rule["name"], "category": rule["category"], "group": rule["group"],
        "scope": rule["scope"], "requiredFacts": [fact["label"] for fact in rule["requiredFacts"]],
        "source": rule["source"],
    } for rule in RULES]}


@app.get("/api/v1/demos", response_model=DemoListResponse)
async def list_demos():
    return {"demos": [{"id": demo.id, "name": demo.name, "pageCount": demo.pageCount, "intent": DEMO_INTENTS[index]} for index, demo in enumerate(DEMOS)]}


@app.post("/api/v1/reviews", status_code=202, response_model=CreateTaskResponse)
async def create_upload_review(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise AppError("file_too_large", "文件超过 20 MB 限制。", 413)
    task = create_task(ReviewMode.QWEN)
    background_tasks.add_task(process_upload, task.id, file.filename or "unnamed", content)
    return {"taskId": task.id, "status": task.status}


@app.post("/api/v1/reviews/demos/{demo_id}", status_code=202, response_model=CreateTaskResponse)
async def create_demo_review(demo_id: str, payload: dict, background_tasks: BackgroundTasks):
    try:
        mode = ReviewMode(payload.get("mode", ReviewMode.LOCAL))
    except ValueError as exc:
        raise AppError("invalid_mode", "审查模式无效。", 422) from exc
    if not any(item.id == demo_id for item in DEMOS):
        raise AppError("demo_not_found", "演示样例不存在。", 404)
    task = create_task(mode)
    background_tasks.add_task(process_demo, task.id, demo_id)
    return {"taskId": task.id, "status": task.status}


@app.get("/api/v1/reviews/{task_id}", response_model=ReviewTask)
async def review_detail(task_id: str):
    task = get_task(task_id)
    if task is None:
        raise AppError("task_not_found", "审查任务不存在。", 404)
    return task


@app.patch("/api/v1/reviews/{task_id}/results/{rule_id}/decision", response_model=DecisionResponse)
async def save_decision(task_id: str, rule_id: str, payload: DecisionRequest):
    return {"result": update_decision(task_id, rule_id, payload.status, payload.reason)}
