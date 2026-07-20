"""
应用配置 — 从环境变量与 .env.local 文件中加载运行时参数。

所有配置项在模块加载时一次初始化，后续通过变量引用读取。
敏感信息（QWEN_API_KEY）不得写入日志或提交到代码仓库。

路径说明：
  当前文件位于 backend/app/core/config.py
  __file__.parent.parent.parent = backend/（项目根）
"""

from pathlib import Path
import os

from dotenv import load_dotenv


# ── 项目根路径 ──────────────────────────────────────────────────
# BACKEND_ROOT 指向 backend/ 目录，用于定位 template_rules.json、数据库等。
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_ROOT / ".env.local")

# ── Qwen 多模态模型配置 ─────────────────────────────────────────
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "").rstrip("/")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "")
try:
    QWEN_DOMAIN_CONCURRENCY = max(1, min(7, int(os.getenv("QWEN_DOMAIN_CONCURRENCY", "7"))))
except ValueError:
    QWEN_DOMAIN_CONCURRENCY = 7

# ── CORS 与上传限制 ─────────────────────────────────────────────
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:4173")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB — 超过此大小直接拒绝，不读多余字节

# ── 持久化路径 ──────────────────────────────────────────────────
REVIEW_DATABASE_PATH = Path(os.getenv("REVIEW_DATABASE_PATH", BACKEND_ROOT / "data" / "reviews.db"))
REVIEW_ARTIFACT_ROOT = Path(os.getenv("REVIEW_ARTIFACT_ROOT", BACKEND_ROOT / "data" / "artifacts"))
