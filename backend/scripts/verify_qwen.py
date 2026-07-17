import asyncio
import json
from pathlib import Path
import sys


backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL  # noqa: E402
from app.data import RULES  # noqa: E402
from app.demo_cases import DEMO_CASES, load_demo_document  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.services.qwen import check_qwen, review_with_qwen  # noqa: E402


async def verify() -> int:
    summary = {
        "configured": bool(QWEN_BASE_URL and QWEN_API_KEY and QWEN_MODEL),
        "reachable": False,
        "model": QWEN_MODEL or None,
        "status": "failed",
        "resultCount": 0,
        "errorCode": None,
    }
    summary["reachable"] = await check_qwen()
    if not summary["configured"]:
        summary["errorCode"] = "model_not_configured"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1
    if not summary["reachable"]:
        summary["errorCode"] = "model_unreachable"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    demo = await load_demo_document(DEMO_CASES[1])
    try:
        results = await review_with_qwen(demo)
    except AppError as error:
        summary["errorCode"] = error.code
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    summary["status"] = "completed"
    summary["resultCount"] = len(results)
    if len(results) != len(RULES):
        summary["status"] = "failed"
        summary["errorCode"] = "incomplete_model_results"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify()))
