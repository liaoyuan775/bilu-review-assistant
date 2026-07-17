import sqlite3

from app.models import ReviewMode, ReviewTask
from app.store import SqliteTaskStore


def test_sqlite_store_survives_new_store_instance(tmp_path):
    database = tmp_path / "reviews.db"
    first_store = SqliteTaskStore(database)
    task = ReviewTask(mode=ReviewMode.LOCAL)

    first_store.save_task(task)

    second_store = SqliteTaskStore(database)
    restored = second_store.get_task(task.id)
    assert restored is not None
    assert restored.id == task.id
    assert restored.mode == ReviewMode.LOCAL


def test_schema_migration_keeps_legacy_review_task_payload_readable(tmp_path):
    database = tmp_path / "legacy.db"
    task = ReviewTask(mode=ReviewMode.LOCAL)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE review_tasks (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO review_tasks (id, updated_at, payload_json) VALUES (?, ?, ?)",
            (task.id, task.updatedAt, task.model_dump_json()),
        )

    restored = SqliteTaskStore(database).get_task(task.id)

    assert restored is not None
    assert restored.id == task.id
    assert restored.mode == ReviewMode.LOCAL
