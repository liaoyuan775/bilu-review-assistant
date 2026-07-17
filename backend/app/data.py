"""
数据层 — 审查规则定义。

职责边界：
- RULES: 从 rules.json 加载"三现四流"工作规则，是模型审查的唯一依据。
规则文件 rules.json 由办案机关维护，后端仅做加载不做修改。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES: list[dict] = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
