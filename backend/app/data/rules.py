"""
规则目录加载 — 从 JSON 文件反序列化版本化规则定义。

本文件在模块加载时读取当前模板规则目录。

路径说明：
  当前文件位于 backend/app/data/rules.py
  __file__.parent.parent.parent = backend/（JSON 文件位于此目录）
"""

from pathlib import Path

from app.core.template_models import TemplateRuleCatalog

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_RULE_CATALOG = TemplateRuleCatalog.model_validate_json(
    (ROOT / "template_rules.json").read_text(encoding="utf-8")
)
TEMPLATE_RULES = TEMPLATE_RULE_CATALOG.rules
