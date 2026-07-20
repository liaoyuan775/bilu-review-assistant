"""
可用模型探测脚本

解析 .env.local 中所有 QWEN 配置组（包括被注释掉的），
逐个调用 OpenAI 兼容的 /models 接口列出可用模型，
并对当前配置的模型执行一次简短的 chat/completions 验证。

用法：
    cd backend && python scripts/check_available_models.py
"""

import asyncio
import httpx
from pathlib import Path
import re

# ── 配置文件路径 ─────────────────────────────────────────────────
ENV_LOCAL = Path(__file__).resolve().parent.parent / ".env.local"


def parse_env_configs(text: str) -> list[dict]:
    """解析 .env.local 文本，提取所有 QWEN 配置组（含被注释掉的）。

    按 "BASE_URL + API_KEY + MODEL" 三元组分组成配置组。
    """
    configs: list[dict] = []
    current = {"base_url": None, "api_key": None, "model": None, "enabled": True}

    for line in text.splitlines():
        enabled = True
        content = line.strip()
        if not content:
            continue
        if content.startswith("#"):
            enabled = False
            content = content.lstrip("#").strip()

        m = re.match(r"QWEN_BASE_URL\s*=\s*(.+)", content)
        if m:
            # 前一组如果已经有 base_url 则保存
            if current["base_url"] is not None:
                configs.append(current)
            current = {"base_url": None, "api_key": None, "model": None, "enabled": enabled}
            current["base_url"] = m.group(1).strip().strip('"').strip("'").rstrip("/")
            continue

        m = re.match(r"QWEN_API_KEY\s*=\s*(.+)", content)
        if m:
            current["api_key"] = m.group(1).strip().strip('"').strip("'")
            continue

        m = re.match(r"QWEN_MODEL\s*=\s*(.+)", content)
        if m:
            current["model"] = m.group(1).strip().strip('"').strip("'")
            continue

    # 保存最后一组
    if current["base_url"] is not None:
        configs.append(current)

    return configs


async def check_models(config: dict) -> dict:
    """对一组配置，调用 /models 接口 + 简短的 chat/completions 验证。"""
    base_url = config["base_url"]
    api_key = config["api_key"]
    model = config["model"]
    enabled = config["enabled"]

    label = f"[{'启用' if enabled else '注释'}][{model or '未指定'}]"
    result = {
        "label": label,
        "base_url": base_url,
        "api_key_prefix": api_key[:8] + "..." if api_key and len(api_key) > 8 else (api_key[:4] + "..." if api_key else "(空)"),
        "model": model,
        "enabled": enabled,
        "models_list": [],
        "chat_test": None,
        "error": None,
    }

    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        # 1) 获取模型列表
        try:
            resp = await client.get(f"{base_url}/models", headers=headers)
            if resp.is_success:
                data = resp.json()
                models = [m["id"] for m in data.get("data", []) if isinstance(m, dict)]
                result["models_list"] = sorted(models)
            else:
                result["error"] = f"GET /models → HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as e:
            result["error"] = f"GET /models → 网络错误: {type(e).__name__}: {e}"

        # 2) 如果当前配置了 model，做一次简短的 chat/completions 测试
        if model:
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "回复'连通正常'四个字"}],
                    "temperature": 0,
                    "max_tokens": 50,
                }
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.is_success:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "") or ""
                    result["chat_test"] = content.strip()
                else:
                    # 可能是 model 名字不对，尝试列表中的第一个模型
                    result["chat_test"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except httpx.HTTPError as e:
                result["chat_test"] = f"网络错误: {type(e).__name__}: {e}"

    return result


def print_result(result: dict):
    """格式化打印探测结果。"""
    print(f"\n{'='*60}")
    print(f"  配置: {result['label']}")
    print(f"  URL:  {result['base_url']}")
    print(f"  Key:  {result['api_key_prefix']}")
    print(f"  Model: {result['model'] or '(未配置)'}")
    print(f"{'='*60}")

    if result["error"]:
        print(f"  [错误] {result['error']}")
        return

    models = result["models_list"]
    if models:
        print(f"  可用模型 ({len(models)}):")
        for m in models:
            current_mark = "  ← 当前配置" if m == result["model"] else ""
            print(f"    - {m}{current_mark}")
    else:
        print(f"  [警告] 未返回任何模型")

    if result["chat_test"] is not None:
        status = "[OK]" if "连通正常" in result["chat_test"] else "[WARN]"
        print(f"  Chat测试: {status} {result['chat_test']}")
    elif result["model"]:
        print(f"  Chat测试: 未执行")


async def main():
    if not ENV_LOCAL.exists():
        print(f"错误: 找不到 {ENV_LOCAL}")
        return

    text = ENV_LOCAL.read_text(encoding="utf-8")
    configs = parse_env_configs(text)

    if not configs:
        print("未在 .env.local 中找到任何 QWEN 配置。")
        return

    print(f"在 .env.local 中发现 {len(configs)} 组 QWEN 配置，开始探测...\n")

    tasks = [check_models(cfg) for cfg in configs]
    results = await asyncio.gather(*tasks)

    for r in results:
        print_result(r)

    print(f"\n{'='*60}")
    print("  探测完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
