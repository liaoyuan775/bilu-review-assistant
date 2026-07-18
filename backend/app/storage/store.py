"""
SQLite 持久化层 — 审查任务快照与可重放审计记录。

职责边界：
- 本文件是系统中唯一的 SQLite 数据库操作模块。
- 管理 8 张业务表和 schema migration（当前版本 v2）。
- 支持乐观锁（revision 字段）防止并发写入冲突。
- manual_events 表有 BEFORE UPDATE/DELETE 触发器，确保审计日志只增不删。

存储策略：
- 文件二进制内容不存入 SQLite（存在磁盘 artifact 目录）。
- SQLite 只存元数据：JSON 快照、文件路径、哈希值等。
- 所有 *_json 后缀的列为 JSON 字符串，通过 _row() 自动反序列化。

表结构：
1. schema_migrations     — 数据库版本记录
2. review_tasks          — 审查任务主表（含 revision 乐观锁）
3. documents             — 文档注册表
4. document_versions     — 文档版本历史（版本号递增）
5. review_runs           — 审查运行记录
6. extracted_facts       — 提取的事实快照（含 entities）
7. review_issues         — 审查问题记录
8. manual_events         — 人工操作审计日志（只增不删）
9. artifacts             — 产物记录表

依赖关系：
- core/config.py: REVIEW_DATABASE_PATH 数据库路径。
- core/errors.py: AppError 异常体系。
- core/models.py: ReviewTask 模型。
"""

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.core.config import REVIEW_DATABASE_PATH
from app.core.errors import AppError
from app.core.models import ReviewTask, now_iso


SCHEMA_VERSION = 2


class SqliteTaskStore:
    """SQLite 持久化存储 — 审查任务及其关联数据的 CRUD。

    核心设计：
    - 通过 revision 乐观锁防止并发写入冲突。
    - manual_events 只增不删（BEFORE UPDATE/DELETE 触发器）。
    - 所有 JSON 字段在写入时序列化，读取时自动反序列化。

    使用示例：
        store = SqliteTaskStore(Path("./review.db"))
        task = ReviewTask(id="task-123")
        store.save_task(task)
        loaded = store.get_task("task-123")
    """

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current < 1:
                self._migrate_v1(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (1, now_iso()),
                )
            if current < 2:
                self._migrate_v2(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (2, now_iso()),
                )
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema {current} is newer than supported {SCHEMA_VERSION}")

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
        """初始表结构：9 张表 + manual_events 的只增不删触发器。"""
        statements = (
            """
            CREATE TABLE IF NOT EXISTS review_tasks (
                id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                original_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES review_tasks(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                content_sha256 TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, version_number),
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                document_version_id TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                timings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(task_id) REFERENCES review_tasks(id),
                FOREIGN KEY(document_version_id) REFERENCES document_versions(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS extracted_facts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                path TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, path),
                FOREIGN KEY(run_id) REFERENCES review_runs(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_issues (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, rule_id),
                FOREIGN KEY(run_id) REFERENCES review_runs(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS manual_events (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                issue_id TEXT,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES review_tasks(id),
                FOREIGN KEY(issue_id) REFERENCES review_issues(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                document_version_id TEXT,
                artifact_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES review_tasks(id),
                FOREIGN KEY(document_version_id) REFERENCES document_versions(id)
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS manual_events_no_update
            BEFORE UPDATE ON manual_events
            BEGIN SELECT RAISE(ABORT, 'manual_events_append_only'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS manual_events_no_delete
            BEFORE DELETE ON manual_events
            BEGIN SELECT RAISE(ABORT, 'manual_events_append_only'); END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _migrate_v2(connection: sqlite3.Connection) -> None:
        """v2 升级：review_tasks 增加 revision 乐观锁字段。"""
        connection.execute(
            "ALTER TABLE review_tasks ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"
        )

    def schema_version(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0])

    @staticmethod
    def _write_task(connection: sqlite3.Connection, task: ReviewTask) -> ReviewTask:
        """写入或更新审查任务（带乐观锁）。

        如果 task.id 不存在 → 插入新记录（revision=0）。
        如果存在 → 检查 revision 匹配后更新（revision+1）。
        不匹配 → 抛出 409 冲突异常。
        """
        updated_at = now_iso()
        row = connection.execute(
            "SELECT revision FROM review_tasks WHERE id = ?",
            (task.id,),
        ).fetchone()
        if row is None:
            saved = task.model_copy(update={"revision": 0, "updatedAt": updated_at})
            connection.execute(
                "INSERT INTO review_tasks (id, updated_at, payload_json, revision) VALUES (?, ?, ?, ?)",
                (task.id, updated_at, saved.model_dump_json(), 0),
            )
            return saved
        current_revision = int(row[0])
        if current_revision != task.revision:
            raise AppError(
                "task_revision_conflict",
                "审查任务已被其他操作更新，请刷新后重试。",
                409,
            )
        next_revision = current_revision + 1
        saved = task.model_copy(update={"revision": next_revision, "updatedAt": updated_at})
        cursor = connection.execute(
            """
            UPDATE review_tasks
            SET updated_at = ?, payload_json = ?, revision = ?
            WHERE id = ? AND revision = ?
            """,
            (updated_at, saved.model_dump_json(), next_revision, task.id, current_revision),
        )
        if cursor.rowcount != 1:
            raise AppError(
                "task_revision_conflict",
                "审查任务已被其他操作更新，请刷新后重试。",
                409,
            )
        return saved

    @staticmethod
    def _apply_saved_task(task: ReviewTask, saved: ReviewTask) -> None:
        """将数据库写回后的 revision 和 updatedAt 应用到传入对象。

        由于 ReviewTask 是可变对象，这里直接修改其属性。
        """
        task.revision = saved.revision
        task.updatedAt = saved.updatedAt

    @staticmethod
    def _insert_events(
        connection: sqlite3.Connection,
        task_id: str,
        events: list[dict],
    ) -> None:
        for event in events:
            connection.execute(
                """
                INSERT INTO manual_events
                    (id, task_id, issue_id, event_type, actor_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    task_id,
                    event.get("issue_id"),
                    event["event_type"],
                    event["actor_id"],
                    _json(event.get("payload", {})),
                    now_iso(),
                ),
            )

    def save_task(self, task: ReviewTask) -> ReviewTask:
        """保存审查任务（插入或更新）。"""
        with self._connect() as connection:
            saved = self._write_task(connection, task)
        self._apply_saved_task(task, saved)
        return task

    def save_task_with_events(self, task: ReviewTask, events: list[dict]) -> ReviewTask:
        """保存任务的同时记录人工操作事件（事务性）。"""
        with self._connect() as connection:
            saved = self._write_task(connection, task)
            self._insert_events(connection, task.id, events)
        self._apply_saved_task(task, saved)
        return task

    def get_task(self, task_id: str) -> ReviewTask | None:
        """根据 ID 获取审查任务。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM review_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return ReviewTask.model_validate_json(row[0]) if row else None

    def list_tasks(self) -> list[ReviewTask]:
        """列出所有审查任务（按更新时间倒序）。"""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM review_tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [ReviewTask.model_validate_json(row[0]) for row in rows]

    def save_document(
        self,
        task_id: str,
        *,
        filename: str,
        mime_type: str,
        sha256: str,
        original_path: str,
    ) -> str:
        """注册文档元数据，返回生成的 document_id。

                注意：这里不保存文件内容（文件在 artifact 目录）。
        """
        document_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (id, task_id, filename, mime_type, sha256, original_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, task_id, filename, mime_type, sha256, original_path, now_iso()),
            )
        return document_id

    def save_document_version(
        self,
        document_id: str,
        *,
        content_sha256: str,
        parsed_payload: dict,
    ) -> str:
        """保存文档解析版本，返回 version_id。

        version_number 自动递增（基于已有版本数 +1）。
        """
        version_id = str(uuid4())
        with self._connect() as connection:
            version_number = int(connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM document_versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0])
            connection.execute(
                """
                INSERT INTO document_versions
                    (id, document_id, version_number, content_sha256, parsed_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (version_id, document_id, version_number, content_sha256, _json(parsed_payload), now_iso()),
            )
        return version_id

    def save_review_run(
        self,
        task_id: str,
        document_version_id: str,
        *,
        rule_version: str,
        model: str,
        status: str,
        timings: dict,
    ) -> str:
        run_id = str(uuid4())
        completed_at = now_iso() if status == "completed" else None
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO review_runs
                    (id, task_id, document_version_id, rule_version, model, status, timings_json, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, task_id, document_version_id, rule_version, model, status, _json(timings), now_iso(), completed_at),
            )
        return run_id

    def save_extracted_fact(self, run_id: str, path: str, payload: dict) -> str:
        """保存单条提取事实。"""
        record_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO extracted_facts (id, run_id, path, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (record_id, run_id, path, _json(payload), now_iso()),
            )
        return record_id

    def save_review_issue(self, run_id: str, rule_id: str, payload: dict) -> str:
        """保存单条审查问题。"""
        issue_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO review_issues (id, run_id, rule_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (issue_id, run_id, rule_id, _json(payload), now_iso()),
            )
        return issue_id

    def persist_review_outcome(
        self,
        task: ReviewTask,
        document_version_id: str,
        *,
        rule_version: str,
        model: str,
        timings: dict,
        facts: dict[str, dict],
        entities: dict[str, dict],
        issues: list[tuple[str, dict]],
        events: list[dict] | None = None,
    ) -> str:
        """事务性保存一次审查的完整结果。

        在同一个事务中完成：
        1. 更新任务状态（写入 reviewRunId）。
        2. 创建 review_runs 记录。
        3. 保存所有提取事实（facts + entities）。
        4. 保存所有审查问题。
        5. 记录人工操作事件。

        Args:
            task:                  审查任务（会被更新 reviewRunId）。
            document_version_id:   文档版本 ID。
            rule_version:          规则版本标识。
            model:                 模型名称。
            timings:               各阶段耗时。
            facts:                 事实字典 {path: payload}。
            entities:              实体字典 {entity_type: payload}。
            issues:                问题列表 [(rule_id, payload)]。
            events:                人工事件列表。

        Returns:
            生成的 run_id。
        """
        run_id = str(uuid4())
        created_at = now_iso()
        with self._connect() as connection:
            saved = self._write_task(
                connection,
                task.model_copy(update={"reviewRunId": run_id}),
            )
            connection.execute(
                """
                INSERT INTO review_runs
                    (id, task_id, document_version_id, rule_version, model, status, timings_json, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?, ?, NULL)
                """,
                (run_id, task.id, document_version_id, rule_version, model, _json(timings), created_at),
            )
            for path, payload in facts.items():
                connection.execute(
                    "INSERT INTO extracted_facts (id, run_id, path, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), run_id, path, _json(payload), now_iso()),
                )
            for entity_type, payload in entities.items():
                connection.execute(
                    "INSERT INTO extracted_facts (id, run_id, path, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), run_id, f"entities.{entity_type}", _json(payload), now_iso()),
                )
            for rule_id, payload in issues:
                connection.execute(
                    "INSERT INTO review_issues (id, run_id, rule_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), run_id, rule_id, _json(payload), now_iso()),
                )
            connection.execute(
                "UPDATE review_runs SET status = 'completed', completed_at = ? WHERE id = ?",
                (now_iso(), run_id),
            )
            self._insert_events(connection, task.id, events or [])
        task.reviewRunId = run_id
        self._apply_saved_task(task, saved)
        return run_id

    def append_manual_event(
        self,
        task_id: str,
        *,
        issue_id: str | None,
        event_type: str,
        actor_id: str,
        payload: dict,
    ) -> str:
        """追加一条人工操作事件（仅插入，不可修改或删除）。"""
        event_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO manual_events
                    (id, task_id, issue_id, event_type, actor_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, task_id, issue_id, event_type, actor_id, _json(payload), now_iso()),
            )
        return event_id

    def save_artifact_record(
        self,
        task_id: str,
        document_version_id: str | None,
        *,
        artifact_type: str,
        filename: str,
        path: str,
        sha256: str,
        size_bytes: int,
        metadata: dict,
    ) -> str:
        """保存产物记录。"""
        artifact_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts
                    (id, task_id, document_version_id, artifact_type, filename, path, sha256, size_bytes, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, task_id, document_version_id, artifact_type, filename, path, sha256, size_bytes, _json(metadata), now_iso()),
            )
        return artifact_id

    def get_audit_snapshot(self, task_id: str) -> dict:
        """获取完整的审查审计快照。

                返回一个包含 7 个列表的字典：
                document, versions, runs, facts, issues, events, artifacts。
        """
        with self._connect() as connection:
            document = connection.execute(
                "SELECT * FROM documents WHERE task_id = ? ORDER BY created_at LIMIT 1",
                (task_id,),
            ).fetchone()
            versions = connection.execute(
                """
                SELECT document_versions.* FROM document_versions
                JOIN documents ON documents.id = document_versions.document_id
                WHERE documents.task_id = ? ORDER BY version_number
                """,
                (task_id,),
            ).fetchall()
            runs = connection.execute(
                "SELECT * FROM review_runs WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ).fetchall()
            facts = connection.execute(
                """
                SELECT extracted_facts.* FROM extracted_facts
                JOIN review_runs ON review_runs.id = extracted_facts.run_id
                WHERE review_runs.task_id = ? ORDER BY extracted_facts.created_at
                """,
                (task_id,),
            ).fetchall()
            issues = connection.execute(
                """
                SELECT review_issues.* FROM review_issues
                JOIN review_runs ON review_runs.id = review_issues.run_id
                WHERE review_runs.task_id = ? ORDER BY review_issues.created_at
                """,
                (task_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT * FROM manual_events WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ).fetchall()
            artifacts = connection.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ).fetchall()
        return {
            "document": _row(document),
            "versions": [_row(row) for row in versions],
            "runs": [_row(row) for row in runs],
            "facts": [_row(row) for row in facts],
            "issues": [_row(row) for row in issues],
            "events": [_row(row) for row in events],
            "artifacts": [_row(row) for row in artifacts],
        }

    def get_artifact_record(self, task_id: str, artifact_id: str) -> dict | None:
        """获取单条产物记录。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE task_id = ? AND id = ?",
                (task_id, artifact_id),
            ).fetchone()
        return _row(row)


def _json(value: dict) -> str:
    """紧凑 JSON 序列化（无空格、无 Unicode 转义）。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _row(row: sqlite3.Row | None) -> dict | None:
    """将 sqlite3.Row 转为字典，自动反序列化 *_json 字段。"""
    if row is None:
        return None
    value = dict(row)
    for key in tuple(value):
        if key.endswith("_json"):
            value[key[:-5]] = json.loads(value.pop(key))
    return value


# ── 模块级单例与便捷函数 ──────────────────────────────────────

STORE = SqliteTaskStore(REVIEW_DATABASE_PATH)


def save_task(task: ReviewTask) -> ReviewTask:
    return STORE.save_task(task)


def save_task_with_events(task: ReviewTask, events: list[dict]) -> ReviewTask:
    return STORE.save_task_with_events(task, events)


def get_task(task_id: str) -> ReviewTask | None:
    return STORE.get_task(task_id)


def list_tasks() -> list[ReviewTask]:
    return STORE.list_tasks()


def save_document(*args, **kwargs) -> str:
    return STORE.save_document(*args, **kwargs)


def save_document_version(*args, **kwargs) -> str:
    return STORE.save_document_version(*args, **kwargs)


def save_review_run(*args, **kwargs) -> str:
    return STORE.save_review_run(*args, **kwargs)


def save_extracted_fact(*args, **kwargs) -> str:
    return STORE.save_extracted_fact(*args, **kwargs)


def save_review_issue(*args, **kwargs) -> str:
    return STORE.save_review_issue(*args, **kwargs)


def persist_review_outcome(*args, **kwargs) -> str:
    return STORE.persist_review_outcome(*args, **kwargs)


def append_manual_event(*args, **kwargs) -> str:
    return STORE.append_manual_event(*args, **kwargs)


def save_artifact_record(*args, **kwargs) -> str:
    return STORE.save_artifact_record(*args, **kwargs)


def get_audit_snapshot(task_id: str) -> dict:
    return STORE.get_audit_snapshot(task_id)


def get_artifact_record(task_id: str, artifact_id: str) -> dict | None:
    return STORE.get_artifact_record(task_id, artifact_id)
