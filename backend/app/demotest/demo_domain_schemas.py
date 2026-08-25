"""打印各域最终传给 Qwen 的完整 JSON Schema 约束。"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.review.domain_contract_rendering import build_domain_schema
from app.data.domain_contracts import DOMAIN_CONTRACTS, DOMAIN_ORDER

OUT_DIR = _BACKEND / "output" / "demo_schemas"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("  各域完整 JSON Schema（最终传给 Qwen 的约束）")
print("=" * 60)

for domain_name in DOMAIN_ORDER:
    contract = DOMAIN_CONTRACTS[domain_name]
    schema = build_domain_schema(contract)

    print(f"\n{'=' * 60}")
    print(f"  {contract.domain} ({contract.title})")
    print(f"{'=' * 60}")
    print(json.dumps(schema, ensure_ascii=False, indent=2))

    filepath = OUT_DIR / f"{contract.domain}.json"
    filepath.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  [已写入] {filepath}")

print(f"\n[DONE] 全部 Schema 已写入 {OUT_DIR}/")
