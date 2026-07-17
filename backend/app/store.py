"""
持久化层 — 基于 SQLite 的审查任务存储。

设计决策：
- 使用 SQLite 而非内存存储，确保页面刷新后审查记录不丢失。
- 采用 JSON 序列化整条 ReviewTask（payload_json），避免复杂的 ORM 映射。
- 单表设计，id 为主键，支持 upsert（ON CONFLICT ... DO UPDATE）。
- updated_at 字段用于列表排序，标识最近活跃的任务。

并发说明：
- SQLite 默认串行化写操作，单个后端进程下无需额外锁机制。
"""

from pathlib import Path
import sqlite3

from app.config import REVIEW_DATABASE_PATH
from app.models import ReviewTask, now_iso


class SqliteTaskStore:
    """基于 SQLite 的审查任务存储实现。

    Args:
        database_path: SQLite 数据库文件路径（自动创建父目录）。
    """

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """创建新的数据库连接（每次操作独立连接，避免跨请求竞争）。"""
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        """初始化表结构（幂等 — IF NOT EXISTS）。"""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_tasks (
                    id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save_task(self, task: ReviewTask) -> ReviewTask:
        """保存或更新审查任务（upsert 语义 — 按 id 去重）。"""
        task.updatedAt = now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO review_tasks (id, updated_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (task.id, task.updatedAt, task.model_dump_json()),
            )
        return task

    def get_task(self, task_id: str) -> ReviewTask | None:
        """按 ID 获取审查任务，不存在时返回 None。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM review_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return ReviewTask.model_validate_json(row[0]) if row else None

    def list_tasks(self) -> list[ReviewTask]:
        """按更新时间降序返回全部任务（最新优先）。"""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM review_tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [ReviewTask.model_validate_json(row[0]) for row in rows]


# ── 模块级单例 ──────────────────────────────────────────────────
STORE = SqliteTaskStore(REVIEW_DATABASE_PATH)


def save_task(task: ReviewTask) -> ReviewTask:
    """保存任务到持久化存储。"""
    return STORE.save_task(task)


def get_task(task_id: str) -> ReviewTask | None:
    """从持久化存储获取任务。"""
    return STORE.get_task(task_id)


def list_tasks() -> list[ReviewTask]:
    """列出所有任务（按更新时间降序）。"""
    return STORE.list_tasks()
