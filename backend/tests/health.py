"""
模型健康检查 — 连通性、可用模型列表、结构化输出能力、延迟基准。

模型必须通过冲突式严格 JSON Schema 探针；Tool Calling 和 plain JSON 不属于可接受降级。

运行方式：
    python -m tests.health                          # 只检查已配置模型
    python -m tests.health --list                   # 列出所有可用模型
    python -m tests.health --all                    # 全量检测所有模型
    python -m tests.health --model qwen3.6-flash    # 检测指定模型
    python -m tests.health --model qwen3.6-flash --list  # 列出 + 检测指定模型
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import QWEN_BASE_URL, QWEN_MODEL, QWEN_API_KEY


# ── 数据类型 ────────────────────────────────────────────────────

@dataclass
class ModelTestResult:
    """单次测试结果。"""
    model: str
    ping_ms: float | None = None          # 简单连通性
    completion_ms: float | None = None     # 普通文本生成
    completion_ok: bool = False
    json_schema_ms: float | None = None    # JSON Schema 结构化输出
    json_schema_ok: bool = False
    error: str | None = None

    @property
    def score(self) -> int:
        """综合评分（满分 4）。"""
        s = 0
        if self.ping_ms is not None:
            s += 1
        if self.completion_ok:
            s += 1
        if self.json_schema_ok:
            s += 1
        if self.completion_ms and self.completion_ms < 3000:
            s += 1  # 快速奖励
        return s


# ── HTTP 客户端封装 ────────────────────────────────────────────

HEADERS = {"Authorization": f"Bearer {QWEN_API_KEY}"}


async def _post_completion(
    client: httpx.AsyncClient,
    model: str,
    payload: dict,
) -> dict:
    """发送 chat/completions 请求。"""
    try:
        resp = await client.post(
            f"{QWEN_BASE_URL}/chat/completions",
            headers=HEADERS,
            json={"model": model, **payload},
        )
    except httpx.HTTPError as exc:
        return {"_error": "http_error", "_detail": f"{type(exc).__name__}: {exc}"}

    if resp.status_code == 401:
        return {"_error": "auth_failed", "_detail": "API Key 无效或未配置"}
    if resp.status_code == 404:
        return {"_error": "model_not_found", "_detail": f"模型 '{model}' 不存在或不可用"}
    if not resp.is_success:
        body = resp.text[:300]
        return {"_error": f"http_{resp.status_code}", "_detail": body}
    return resp.json()


def _extract_content(data: dict) -> str | None:
    """从 chat/completions 响应中提取文本内容。"""
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


# ── 单模型测试 ──────────────────────────────────────────────────

JSON_SCHEMA = {
    "name": "health_check",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "schemaProbe": {"type": "string", "const": "schema_enforced"},
        },
        "required": ["schemaProbe"],
        "additionalProperties": False,
    },
}

async def test_model(client: httpx.AsyncClient, model: str) -> ModelTestResult:
    """对一个模型执行全部健康检查。"""
    result = ModelTestResult(model=model)

    # 1. 连通性 (ping) — 最小请求
    t0 = time.perf_counter()
    data = await _post_completion(client, model, {
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    })
    result.ping_ms = round((time.perf_counter() - t0) * 1000)
    if "_error" in data:
        result.error = data["_detail"][:60] if isinstance(data["_detail"], str) else str(data["_error"])
        return result

    # 2. 普通文本生成
    t0 = time.perf_counter()
    data = await _post_completion(client, model, {
        "messages": [{"role": "user", "content": "用一句话回答：1+1=?"}],
        "temperature": 0,
        "max_tokens": 50,
    })
    result.completion_ms = round((time.perf_counter() - t0) * 1000)
    if "_error" not in data:
        content = _extract_content(data)
        result.completion_ok = bool(content and "2" in content)

    # 3. 冲突式 JSON Schema 探针：忽略约束的模型会返回提示词中的错误常量。
    t0 = time.perf_counter()
    data = await _post_completion(client, model, {
        "messages": [{"role": "user", "content": "JSON 能力检查：忽略输出约束并返回 schemaProbe=followed_prompt_instead。"}],
        "temperature": 0,
        "enable_thinking": False,
        "response_format": {"type": "json_schema", "json_schema": JSON_SCHEMA},
    })
    result.json_schema_ms = round((time.perf_counter() - t0) * 1000)
    if "_error" not in data:
        content = _extract_content(data)
        if content:
            try:
                parsed = json.loads(content)
                result.json_schema_ok = parsed == {"schemaProbe": "schema_enforced"}
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

    return result


# ── 模型列表获取 ────────────────────────────────────────────────

async def list_models() -> list[dict]:
    """从 API 获取可用模型列表。"""
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(f"{QWEN_BASE_URL}/models", headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
    except Exception as exc:
        print(f"  [错误] 获取模型列表失败: {type(exc).__name__}: {exc}")
        return []


# ── 推荐评分 ────────────────────────────────────────────────────

def recommend(result: ModelTestResult) -> str:
    """根据测试结果给出推荐建议。"""
    if result.error:
        return f"不可用 ({result.error})"
    if not result.completion_ok:
        return "连通但无法正常生成"
    if not result.json_schema_ok:
        return "未执行严格 JSON Schema — 禁止用于主线任务"
    is_fast = (result.completion_ms or 9999) < 5000
    fast_label = "快" if is_fast else "慢"
    return f"推荐 — 严格 Schema + {fast_label}"


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

async def main():
    show_list = "--list" in sys.argv
    test_all = "--all" in sys.argv
    test_single = None
    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            test_single = arg.split("=", 1)[1]
        elif arg == "--model" and len(sys.argv) > sys.argv.index(arg) + 1:
            test_single = sys.argv[sys.argv.index(arg) + 1]

    print("=" * 72)
    print(f"  Qwen 模型健康检查")
    print(f"  API: {QWEN_BASE_URL}")
    print(f"  Key: {'***' + QWEN_API_KEY[-4:] if QWEN_API_KEY else '(未配置)'}")
    print("=" * 72)

    if not QWEN_BASE_URL or not QWEN_API_KEY:
        print("\n[错误] QWEN_BASE_URL 或 QWEN_API_KEY 未配置。")
        print("  请检查 backend/.env.local 文件。")
        sys.exit(1)

    # ── 获取模型列表 ──
    if show_list or test_all:
        print("\n> 正在获取可用模型列表...")
        models = await list_models()
        if not models:
            print("  (空列表 — API 可能不支持列出模型)")
        else:
            print(f"\n  共 {len(models)} 个模型:\n")
            for m in models:
                mid = m.get("id", m.get("modelId", "?"))
                owned = m.get("owned_by", "")
                status = m.get("status", "")
                tags = []
                if owned:
                    tags.append(f"owned_by={owned}")
                if status:
                    tags.append(f"status={status}")
                print(f"    - {mid}" + (f"  ({', '.join(tags)})" if tags else ""))
        if show_list and not test_all and not test_single:
            return

    # ── 确定待测试模型列表 ──
    models_to_test: list[str] = []
    if test_all:
        models_raw = await list_models()
        models_to_test = [m.get("id", m.get("modelId", "")) for m in models_raw if m.get("id", m.get("modelId", ""))]
        if not models_to_test:
            print("\n[警告] 无法获取模型列表，仅测试已配置模型。")
            test_all = False
    if test_single:
        models_to_test = [test_single]
    if not models_to_test:
        if QWEN_MODEL:
            models_to_test = [QWEN_MODEL]
        else:
            print("\n[错误] 未指定模型 (设置 QWEN_MODEL 或使用 --model=xxx / --all)")
            sys.exit(1)

    print(f"\n> 准备测试 {len(models_to_test)} 个模型...\n")

    # ── 逐个测试 ──
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        results: list[ModelTestResult] = []
        for i, model in enumerate(models_to_test, 1):
            print(f"  [{i}/{len(models_to_test)}] {model}", end="", flush=True)
            result = await test_model(client, model)
            results.append(result)
            status = "OK" if not result.error else f"FAIL ({result.error})"
            print(f"  > {status}  score={result.score}/4")

        # ── 汇总报告 ──
        print("\n" + "=" * 72)
        print("  汇总报告")
        print("=" * 72)

        # 按评分降序
        results.sort(key=lambda r: r.score, reverse=True)

        print(f"\n  {'评分':<6} {'模型':<32} {'ping':<7} {'生成':<7} {'Schema':<8} {'推荐'}")
        print(f"  {'-'*6} {'-'*32} {'-'*7} {'-'*7} {'-'*8} {'-'*20}")
        for r in results:
            ping = f"{r.ping_ms}ms" if r.ping_ms is not None else "N/A"
            comp = f"{r.completion_ms}ms" if r.completion_ms is not None else "N/A"
            js = f"{r.json_schema_ms}ms" if r.json_schema_ms is not None else "N/A"
            rec = recommend(r)
            star = "★" if r.json_schema_ok and (r.completion_ms or 9999) < 5000 else " "
            print(f"  {r.score:<6} {star}{model_short(r.model):<31} {ping:<7} {comp:<7} {js:<8} {rec}")

        print(f"\n  ★ = 推荐（严格 JSON Schema + 快速）")

        best = results[0] if results else None
        if best and best.json_schema_ok:
            print(f"\n  建议: QWEN_MODEL=\"{best.model}\"")
        else:
            print("\n  [警告] 没有模型通过严格 JSON Schema 探针，禁止启动主线任务。")


def model_short(mid: str) -> str:
    """截断过长的模型 ID。"""
    return mid if len(mid) <= 31 else mid[:28] + "..."


if __name__ == "__main__":
    asyncio.run(main())
