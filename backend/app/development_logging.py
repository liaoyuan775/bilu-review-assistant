from __future__ import annotations

from contextvars import ContextVar, Token
from hashlib import sha256
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from typing import Any


LOGGER_NAME = "bilu"
_task_id: ContextVar[str] = ContextVar("bilu_task_id", default="-")
_configured = False


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> logging.Logger:
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger
    level = logging.DEBUG if _enabled("BILU_DEBUG_LOGS", True) else logging.INFO
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_dir = Path(os.getenv("BILU_LOG_DIR", Path(__file__).resolve().parent.parent / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "development.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    _configured = True
    return logger


def get_logger() -> logging.Logger:
    return configure_logging()


def set_task_id(task_id: str) -> Token:
    return _task_id.set(task_id)


def reset_task_id(token: Token) -> None:
    _task_id.reset(token)


def _value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("\n", "\\n")


def log_event(level: int, event: str, **fields: Any) -> None:
    details = [f"event={event}", f"task_id={_task_id.get()}"]
    details.extend(f"{key}={_value(value)}" for key, value in fields.items() if value is not None)
    get_logger().log(level, " ".join(details))


def log_payload(label: str, payload: Any, *, level: int = logging.DEBUG, **fields: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    metadata = {
        "label": label,
        "chars": len(text),
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
        **fields,
    }
    if _enabled("BILU_LOG_PAYLOADS"):
        log_event(level, "payload.full", **metadata, content=f"\n{text}")
    else:
        log_event(level, "payload.summary", **metadata)
