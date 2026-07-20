"""
结构化日志工具 — 提供带 task_id 上下文的日志记录。

设计要点：
- 使用 ContextVar 在每个审查任务的处理线程中注入 task_id
- 日志事件包含结构化字段（event=xxx key=value），便于日志分析
- 敏感负载（完整解析文本、模型提示、响应）只在 BILU_LOG_PAYLOADS=true
  时记录，默认只记录长度和 SHA-256 摘要

路径说明：
  当前文件位于 backend/app/core/development_logging.py
  __file__.parent.parent.parent = backend/（日志目录默认在此）
"""

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
    """读取布尔型环境变量。"""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> logging.Logger:
    """配置日志系统 — 输出到控制台和旋转日志文件。

    日志文件默认位于 backend/logs/development.log，
    可通过 BILU_LOG_DIR 环境变量修改。
    """
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

    log_dir = Path(os.getenv("BILU_LOG_DIR", Path(__file__).resolve().parent.parent.parent / "logs"))
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
    """获取已配置的日志器。"""
    return configure_logging()


def set_task_id(task_id: str) -> Token:
    """设置当前上下文的 task_id，返回 Token 用于后续 reset。"""
    return _task_id.set(task_id)


def reset_task_id(token: Token) -> None:
    """恢复 task_id 到设置前的值。"""
    _task_id.reset(token)


def _value(value: Any) -> str:
    """将任意值转为日志友好的字符串。"""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("\n", "\\n")


def log_event(level: int, event: str, **fields: Any) -> None:
    """记录一个结构化日志事件。

    Args:
        level:   日志级别（logging.INFO / logging.WARNING 等）
        event:   事件名称（如 "upload.received"、"review.started"）
        **fields: 随事件记录的键值对，None 值会被自动忽略
    """
    details = [f"event={event}", f"task_id={_task_id.get()}"]
    details.extend(f"{key}={_value(value)}" for key, value in fields.items() if value is not None)
    get_logger().log(level, " ".join(details))


def log_payload(label: str, payload: Any, *, level: int = logging.DEBUG, **fields: Any) -> None:
    """记录负载信息的摘要（默认）或完整内容（BILU_LOG_PAYLOADS=true）。

    Args:
        label:   负载描述标签
        payload: 负载数据（字符串或可 JSON 序列化的对象）
        level:   日志级别
        **fields: 额外字段
    """
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
