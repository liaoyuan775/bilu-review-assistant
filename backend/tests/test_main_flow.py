"""
通过 API 测试主线流程 — 调演示案例，等待结果，查看审查是否通过。
"""

import httpx
import time
import json
import sys

BASE = "http://127.0.0.1:8788/api/v1"


def main():
    print("=" * 60)
    print("  主线流程端到端测试 (通过 API)")
    print("=" * 60)

    # 1. 查演示案例
    print("\n> 查询演示案例...")
    r = httpx.get(f"{BASE}/reviews", timeout=5)
    r.raise_for_status()
    reviews = r.json().get("reviews", [])
    print(f"  现有审查任务: {len(reviews)} 个")

    # 2. 发起演示审查 (用 case-02-line-breaks，qwen 模式)
    print("\n> 发起演示审查 (case-02-line-breaks)...")
    r = httpx.post(f"{BASE}/reviews/demos/case-02-line-breaks", timeout=5)

    r.raise_for_status()
    data = r.json()
    task_id = data["taskId"]
    status = data["status"]
    print(f"  任务已创建: taskId={task_id}, status={status}")

    # 3. 轮询等待完成
    print("\n> 等待审查完成...")
    max_wait = 300  # 5 分钟
    polled = 0
    result = None
    while polled < max_wait:
        time.sleep(3)
        polled += 3
        r = httpx.get(f"{BASE}/reviews/{task_id}", timeout=5)
        r.raise_for_status()
        result = r.json()
        status = result.get("status")
        if status == "completed":
            print(f"  完成! (耗时 {polled}s)")
            break
        elif status == "failed":
            print(f"  失败! (耗时 {polled}s)")
            break
        else:
            progress = result.get("progress", {})
            pct = progress.get("percent", 0)
            print(f"  ... 进度 {pct}% ({polled}s)", end="\r", flush=True)
    else:
        print("\n  [超时] 5 分钟内未完成")
        sys.exit(1)

    # 4. 打印结果
    print("\n" + "-" * 60)
    print("  审查结果:")
    print("-" * 60)

    results = result.get("results", [])
    group_timings = result.get("groupTimings", {})
    qwen_status = result.get("qwenStatus", "")

    print(f"  总体状态: {result.get('reviewStatus', '?')}")
    print(f"  Qwen 状态: {qwen_status}")
    print(f"  分组耗时: {json.dumps(group_timings, ensure_ascii=False)}")
    print(f"  规则数: {len(results)}")
    print()

    for r_item in results:
        rid = r_item.get("ruleId", "?")
        rname = r_item.get("ruleName", "?")
        rst = r_item.get("status", "?")
        rsn = (r_item.get("reason") or "")[:80]
        missing = r_item.get("missingFacts", [])
        ev = (r_item.get("evidence") or "")[:60]
        print(f"  [{rst:>14}] {rid:<8} {rname}")
        if missing:
            print(f"     ├ 缺失: {', '.join(missing)}")
        print(f"     ├ 理由: {rsn}")
        if ev:
            print(f"     └ 证据: {ev}")
        print()

    # 统计
    statuses = [r.get("status") for r in results]
    n_covered = statuses.count("covered")
    n_missing = statuses.count("missing")
    n_incomplete = statuses.count("incomplete")
    n_not_applicable = statuses.count("not_applicable")
    total = len(results)

    print(f"  统计: covered={n_covered}  missing={n_missing}  "
          f"incomplete={n_incomplete}  not_applicable={n_not_applicable}  / {total}")

    if n_missing == 0 and n_incomplete == 0:
        print("\n  [通过] 全部规则已覆盖")
    elif n_missing > 0:
        print(f"\n  [部分通过] {n_missing} 条缺失需补充")
    else:
        print(f"\n  [部分通过] {n_incomplete} 条不完整需补充")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)

    # 5. 清理: 完成归档
    print(f"\n> 归档任务...")
    r = httpx.post(f"{BASE}/reviews/{task_id}/complete", timeout=5)
    print(f"  归档结果: {r.status_code}")


if __name__ == "__main__":
    main()
