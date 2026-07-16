import json
from pathlib import Path
import sys

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.main import app  # noqa: E402


target = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(target)
