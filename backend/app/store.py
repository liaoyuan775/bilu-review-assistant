"""SQLite persistence for task snapshots and replayable review audit records."""

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.config import REVIEW_DATABASE_PATH
from app.models import ReviewTask, now_iso


SCHEMA_VERSION = 1


class SqliteTaskStore:
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
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema {current} is newer than supported {SCHEMA_VERSION}")

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
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

    def schema_version(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0])

    def save_task(self, task: ReviewTask) -> ReviewTask:
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM review_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return ReviewTask.model_validate_json(row[0]) if row else None

    def list_tasks(self) -> list[ReviewTask]:
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
        record_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO extracted_facts (id, run_id, path, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (record_id, run_id, path, _json(payload), now_iso()),
            )
        return record_id

    def save_review_issue(self, run_id: str, rule_id: str, payload: dict) -> str:
        issue_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO review_issues (id, run_id, rule_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (issue_id, run_id, rule_id, _json(payload), now_iso()),
            )
        return issue_id

    def append_manual_event(
        self,
        task_id: str,
        *,
        issue_id: str | None,
        event_type: str,
        actor_id: str,
        payload: dict,
    ) -> str:
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE task_id = ? AND id = ?",
                (task_id, artifact_id),
            ).fetchone()
        return _row(row)


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    value = dict(row)
    for key in tuple(value):
        if key.endswith("_json"):
            value[key[:-5]] = json.loads(value.pop(key))
    return value


STORE = SqliteTaskStore(REVIEW_DATABASE_PATH)


def save_task(task: ReviewTask) -> ReviewTask:
    return STORE.save_task(task)


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


def append_manual_event(*args, **kwargs) -> str:
    return STORE.append_manual_event(*args, **kwargs)


def save_artifact_record(*args, **kwargs) -> str:
    return STORE.save_artifact_record(*args, **kwargs)


def get_audit_snapshot(task_id: str) -> dict:
    return STORE.get_audit_snapshot(task_id)


def get_artifact_record(task_id: str, artifact_id: str) -> dict | None:
    return STORE.get_artifact_record(task_id, artifact_id)
