"""打印模型经过提示词+JSON Schema约束后的产出（extractionPayload）。"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.storage.store import get_task

TASK_ID = "265aa636-4ff2-4f53-ad70-eb41e9b7b3c1"

task = get_task(TASK_ID)
if not task:
    print(f"[ERROR] 未找到任务: {TASK_ID}")
    sys.exit(1)

ep = task.extractionPayload
if not ep:
    print(f"[ERROR] 任务 {TASK_ID} 没有 extractionPayload")
    sys.exit(1)

print("=" * 60)
print(f"  模型产出 extractionPayload (task={TASK_ID})")
print("=" * 60)
print(json.dumps(ep, ensure_ascii=False, indent=2))
print()
print(f"[OK] facts 数: {len(ep.get('facts', {}))}")
print(f"[OK] entities 域: {list(ep.get('entities', {}).keys())}")
print(f"[OK] failedDomains: {ep.get('failedDomains', [])}")
