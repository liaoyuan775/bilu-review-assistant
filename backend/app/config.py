from pathlib import Path
import os

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env.local")

QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "").rstrip("/")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:4173")
MAX_FILE_SIZE = 20 * 1024 * 1024
