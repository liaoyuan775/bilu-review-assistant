"""打印全部 34 条规则的逐字段检查过程 + 最终结果。

展示规则引擎的完整判断逻辑：
  1. 适用性检查（appliesWhen）
  2. 逐个 requiredField 检查（clarity + value）
  3. 重复实体检查（repeatEntity）
  4. 一致性检查（consistencyChecks）
  5. 最终状态判定
"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.data.rules import TEMPLATE_RULES
from app.storage.store import get_task

TASK_ID = "265aa636-4ff2-4f53-ad70-eb41e9b7b3c1"

rules = TEMPLATE_RULES

task = get_task(TASK_ID)
if not task:
    print(f"[ERROR] 未找到任务: {TASK_ID}")
    sys.exit(1)

# ── 加载 extractionPayload 中的 facts 和 entities ──────────────
ep = task.extractionPayload or {}
facts: dict = ep.get("facts", {})
entities: dict = ep.get("entities", {})

# ── 构建 SHA-256 → 原文 反向查找 ──────────────────────────────
paragraph_map: dict[str, str] = {}
if task.document:
    for page in task.document.pages:
        for para in page.paragraphs:
            paragraph_map[para.id] = para.text

# ── 结果映射（用于对比最终结果）────────────────────────────────
results_map: dict[str, dict] = {}
for r in task.results:
    results_map[r.ruleId] = r.model_dump(mode="json")


def _clarity_label(fact: dict | None) -> str:
    if fact is None:
        return "[ERR] None"
    c = fact.get("clarity", "missing")
    v = fact.get("value")
    labels = {
        "clear": f"[OK] clear (value={v!r})",
        "unclear": f"[WARN] unclear (value={v!r})",
        "unknown": f"[?] unknown",
        "missing": f"[ERR] missing",
    }
    return labels.get(c, f"[?] {c}")


# ═══════════════════════════════════════════════════════════════════
print("=" * 72)
print(f"  规则引擎逐字段检查过程 (TASK={TASK_ID})")
print(f"  规则数: {len(rules)}  |  事实数: {len(facts)}  |  实体验: {list(entities.keys())}")
print(f"  段落数: {len(paragraph_map)}")
print("=" * 72)

PASSED = 0
FAILED = 0
SKIPPED = 0

for i, rule in enumerate(rules, start=1):
    rid = rule.ruleId
    result = results_map.get(rid)

    print(f"\n{'=' * 72}")
    print(f"  [{i:02d}/{len(rules)}] {rid} — {rule.name}")
    print(f"       分组: {rule.group}  |  严重度: {rule.severity}  |  范围: {rule.scope}")
    print(f"{'─' * 72}")

    # ── Step 1: 适用性检查 ─────────────────────────────────────
    if rule.appliesWhen:
        cond = rule.appliesWhen
        cond_fact = facts.get(cond.path)
        print(f"  [Step1] 适用条件: {cond.operator} {cond.path} == {cond.value!r}")
        print(f"           事实值: {_clarity_label(cond_fact)}")
    else:
        cond_fact = None
        print(f"  [Step1] 适用条件: 无条件(始终适用)")

    if result is None:
        print(f"  [Final] 未匹配到审查结果")
        SKIPPED += 1
        continue

    # ── Step 2: 逐个 requiredField 检查 ─────────────────────────
    print(f"  [Step2] 必需字段 ({len(rule.requiredFields)} 个):")
    for path in rule.requiredFields:
        fact = facts.get(path)
        required_val = rule.requiredValues.get(path)
        label = _clarity_label(fact)

        extra = ""
        if fact and required_val is not None:
            actual = fact.get("value")
            match = actual == required_val
            extra = f"  requiredValue={required_val!r} -> {'OK' if match else 'ERR'} 不匹配"

        # 关联的 evidenceAnchorIds
        anchor_ids = (fact or {}).get("evidenceAnchorIds", [])
        if anchor_ids:
            texts = []
            for aid in anchor_ids[:2]:
                t = paragraph_map.get(aid, "")
                texts.append(f"{aid[:16]}…→{t[:40]}")
            extra += f"\n           src: {' | '.join(texts)}"

        print(f"      · {path}")
        print(f"          {label}{extra}")

    # ── Step 3: 提醒字段 ────────────────────────────────────────
    if rule.advisoryFields:
        print(f"  [Step3] 提醒字段:")
        for path in rule.advisoryFields:
            fact = facts.get(path)
            print(f"      · {path} → {_clarity_label(fact)}")

    # ── Step 4: 重复实体检查 ──────────────────────────────────
    if rule.repeatEntity:
        re = rule.repeatEntity
        ents = entities.get(re.entityType, [])
        print(f"  [Step4] 重复实体 ({re.entityType}): count={len(ents)}")
        if re.countPath:
            count_fact = facts.get(re.countPath)
            print(f"      声明计数 {re.countPath} → {_clarity_label(count_fact)}")

        for ei, ent in enumerate(ents):
            print(f"      实例 [{ei + 1}] {ent.get('id', '?')}:")
            for fn in re.requiredFields:
                f = ent.get("fields", {}).get(fn, {})
                print(f"        · {fn} → {_clarity_label(f)}")

    # ── Step 5: 一致性检查 ────────────────────────────────────
    if rule.consistencyChecks:
        print(f"  [Step5] 一致性检查 ({len(rule.consistencyChecks)} 项):")
        for cc in rule.consistencyChecks:
            info = json.dumps(cc.model_dump(), ensure_ascii=False)
            print(f"      · {cc.type}: {info}")

    # ── 最终状态 ──────────────────────────────────────────────
    status = result["status"]
    missing_facts = result.get("missingFacts", [])
    advisories = result.get("advisories", [])
    reason = result.get("reason", "")
    suggested = result.get("suggestedQuestion", "")

    if status == "covered":
        PASSED += 1
        icon = "[PASS] 通过"
    elif status in ("missing", "incomplete"):
        FAILED += 1
        icon = "[WARN] 不完整"
    elif status == "inconsistent":
        FAILED += 1
        icon = "[FAIL] 不一致"
    else:
        SKIPPED += 1
        icon = "[SKIP] 跳过"

    print(f"  {'-' * 72}")
    print(f"  [Final] {icon}  (status={status})")
    if missing_facts:
        print(f"     问题字段: {missing_facts}")
    if advisories:
        print(f"     提醒事项: {advisories}")
    if reason:
        print(f"     原因: {reason}")
    if suggested:
        print(f"     建议补问: {suggested}")

print(f"\n{'=' * 72}")
print(f"  汇总: 通过={PASSED}  发现问题={FAILED}  跳过/不适用={SKIPPED}  合计={len(rules)}")
print(f"{'=' * 72}")
