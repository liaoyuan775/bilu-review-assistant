from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import QWEN_MODEL  # noqa: E402
from app.core.development_logging import get_logger  # noqa: E402
from app.parsing.parser import parse_document  # noqa: E402
from app.review.extraction import DEFAULT_DOMAIN_CONCURRENCY, run_template_review  # noqa: E402
from app.core.template_models import CaseExtraction  # noqa: E402
from scripts.generate_template_gold_cases import _case_extraction, build_gold_corpus  # noqa: E402
from scripts.verify_template_quality import _gold_accuracy, _gold_semantic_fingerprint  # noqa: E402


EXPECTED_MODEL = "Qwen3.6-35B-A3B"


def quality_fingerprint(extraction, issues, expected: CaseExtraction) -> str:
    return _gold_semantic_fingerprint(extraction, issues, expected)


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _duration_summary(values: list[int]) -> dict[str, int]:
    return {
        "min": min(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
        "mean": round(statistics.fmean(values)),
    }


def summarize_samples(samples: list[dict]) -> dict:
    if not samples:
        raise ValueError("benchmark requires at least one sample")
    fingerprints = {sample["qualityFingerprint"] for sample in samples}
    if len(fingerprints) != 1:
        raise ValueError("benchmark runs produced different quality fingerprints")

    stage_names = sorted({name for sample in samples for name in sample["stageMs"]})
    durations = {
        "total": _duration_summary([sample["totalMs"] for sample in samples]),
        "parse": _duration_summary([sample["parseMs"] for sample in samples]),
        "review": _duration_summary([sample["reviewMs"] for sample in samples]),
        "stages": {
            name: _duration_summary([sample["stageMs"].get(name, 0) for sample in samples])
            for name in stage_names
        },
    }
    request_values = [sample["requestCount"] for sample in samples]
    return {
        "runs": len(samples),
        "qualityFingerprint": fingerprints.pop(),
        "durationMs": durations,
        "requests": {
            "total": sum(request_values),
            "perRunP50": _percentile(request_values, 0.50),
            "perRunP95": _percentile(request_values, 0.95),
        },
        "tokens": {
            key: sum(sample["tokens"].get(key, 0) for sample in samples)
            for key in ("prompt", "completion", "total")
        },
    }


def _improvement(before: int, after: int) -> float:
    return round((before - after) * 100.0 / before, 2) if before else 0.0


def compare_summaries(before: dict, after: dict) -> dict:
    if before["qualityFingerprint"] != after["qualityFingerprint"]:
        raise ValueError("quality fingerprint changed between baseline and candidate")
    p50 = _improvement(
        before["durationMs"]["total"]["p50"],
        after["durationMs"]["total"]["p50"],
    )
    p95 = _improvement(
        before["durationMs"]["total"]["p95"],
        after["durationMs"]["total"]["p95"],
    )
    return {
        "qualityIdentical": True,
        "p50ImprovementPercent": p50,
        "p95ImprovementPercent": p95,
        "accepted": max(p50, p95) >= 10.0,
        "requiredImprovementPercent": 10.0,
    }


class _UsageHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.request_count = 0
        self.tokens = {"prompt": 0, "completion": 0, "total": 0}

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "event=qwen.request_completed" not in message:
            return
        self.request_count += 1
        marker = " usage="
        if marker not in message:
            return
        try:
            usage, _ = json.JSONDecoder().raw_decode(message.split(marker, 1)[1])
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(usage, dict):
            return
        self.tokens["prompt"] += int(usage.get("prompt_tokens") or 0)
        self.tokens["completion"] += int(usage.get("completion_tokens") or 0)
        self.tokens["total"] += int(usage.get("total_tokens") or 0)


async def _run_sample(
    filename: str,
    content: bytes,
    max_concurrency: int,
    expected_extraction: CaseExtraction,
    expected_statuses: dict[str, str],
) -> dict:
    total_started = perf_counter()
    parse_started = perf_counter()
    document = await parse_document(filename, content)
    parse_ms = round((perf_counter() - parse_started) * 1000)

    usage = _UsageHandler()
    logger = get_logger()
    logger.addHandler(usage)
    stage_ms: dict[str, int] = {}
    review_started = perf_counter()
    try:
        outcome = await run_template_review(
            document,
            group_timings=stage_ms,
            max_concurrency=max_concurrency,
        )
    finally:
        logger.removeHandler(usage)
    review_ms = round((perf_counter() - review_started) * 1000)
    passed, total, mismatches = _gold_accuracy(outcome.extraction, expected_extraction)
    if passed != total:
        paths = sorted({item["path"] for item in mismatches})
        raise ValueError(f"benchmark quality mismatch at paths: {','.join(paths)}")
    issue_mismatches = [
        issue.ruleId
        for issue in outcome.issues
        if issue.status.value != expected_statuses[issue.ruleId]
    ]
    if issue_mismatches:
        raise ValueError(f"benchmark rule mismatch: {','.join(sorted(issue_mismatches))}")
    missing_anchors = [
        issue.ruleId
        for issue in outcome.issues
        if expected_statuses[issue.ruleId] not in {"missing", "needs_manual_review", "not_applicable"}
        and not issue.anchorIds
    ]
    if missing_anchors:
        raise ValueError(f"benchmark evidence mismatch: {','.join(sorted(missing_anchors))}")
    return {
        "totalMs": round((perf_counter() - total_started) * 1000),
        "parseMs": parse_ms,
        "reviewMs": review_ms,
        "stageMs": stage_ms,
        "requestCount": usage.request_count,
        "tokens": usage.tokens,
        "qualityFingerprint": quality_fingerprint(
            outcome.extraction,
            outcome.issues,
            expected_extraction,
        ),
    }


async def run_benchmark(runs: int, case_id: str, max_concurrency: int) -> list[dict]:
    with TemporaryDirectory(prefix="bilu-template-benchmark-") as temporary:
        corpus_dir = Path(temporary)
        corpus = build_gold_corpus(corpus_dir)
        case = next((item for item in corpus["cases"] if item["id"] == case_id), None)
        if case is None:
            raise ValueError(f"unknown gold case: {case_id}")
        path = corpus_dir / case["docx"]
        content = path.read_bytes()
        expected_extraction = _case_extraction(tuple(case["domains"]))
        samples = []
        for index in range(runs):
            print(f"benchmark run {index + 1}/{runs}: concurrency={max_concurrency}", flush=True)
            samples.append(await _run_sample(
                path.name,
                content,
                max_concurrency,
                expected_extraction,
                case["expectedRuleStatuses"],
            ))
        return samples


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark sanitized template-review quality and latency.")
    parser.add_argument("--runs", type=_positive, default=5)
    parser.add_argument("--case-id", default="gold-12-complete")
    parser.add_argument(
        "--domain-concurrency",
        type=_positive,
        default=DEFAULT_DOMAIN_CONCURRENCY,
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if QWEN_MODEL != EXPECTED_MODEL:
        raise SystemExit(f"configured model must remain {EXPECTED_MODEL}, got {QWEN_MODEL}")
    samples = asyncio.run(run_benchmark(args.runs, args.case_id, args.domain_concurrency))
    summary = summarize_samples(samples)
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": QWEN_MODEL,
        "caseId": args.case_id,
        "domainConcurrency": args.domain_concurrency,
        "samples": samples,
        "summary": summary,
    }
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report["comparison"] = compare_summaries(baseline["summary"], summary)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "summary": summary,
        "comparison": report.get("comparison"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
