"""Versioned rule catalogs used by the legacy and template review paths."""

import json
from pathlib import Path

from app.template_models import TemplateRuleCatalog

ROOT = Path(__file__).resolve().parent.parent
RULES: list[dict] = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
TEMPLATE_RULE_CATALOG = TemplateRuleCatalog.model_validate_json(
    (ROOT / "template_rules.json").read_text(encoding="utf-8")
)
TEMPLATE_RULES = TEMPLATE_RULE_CATALOG.rules
