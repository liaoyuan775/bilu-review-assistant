"""Run one comparable template-review latency sample with the model from env."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def run(input_path: Path) -> dict:
    # Import after the caller has set QWEN_* environment variables.
    from app.parsing.parser import parse_document
    from app.review.extraction import run_template_review

    content = input_path.read_bytes()
    total_started = perf_counter()
    parse_started = perf_counter()
    document = await parse_document(input_path.name, content)
    parse_ms = round((perf_counter() - parse_started) * 1000)
    timings: dict[str, int] = {}
    review_started = perf_counter()
    outcome = await run_template_review(document, group_timings=timings)
    review_ms = round((perf_counter() - review_started) * 1000)
    statuses: dict[str, int] = {}
    for issue in outcome.issues:
        statuses[issue.status.value] = statuses.get(issue.status.value, 0) + 1
    return {
        "model": os.environ.get("QWEN_MODEL", ""),
        "baseUrl": os.environ.get("QWEN_BASE_URL", ""),
        "input": str(input_path),
        "bytes": len(content),
        "pages": document.pageCount,
        "paragraphs": sum(len(page.paragraphs) for page in document.pages),
        "questionAnswers": len(document.questionAnswers),
        "parseMs": parse_ms,
        "reviewMs": review_ms,
        "totalMs": round((perf_counter() - total_started) * 1000),
        "domainMs": timings,
        "resultCount": len(outcome.results),
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.input))
    except Exception as exc:
        result = {
            "model": os.environ.get("QWEN_MODEL", ""),
            "baseUrl": os.environ.get("QWEN_BASE_URL", ""),
            "input": str(args.input),
            "status": "failed",
            "errorType": type(exc).__name__,
            "error": str(exc),
        }
    else:
        result["status"] = "completed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
