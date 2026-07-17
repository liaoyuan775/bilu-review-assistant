import hashlib
import sqlite3

import pytest

from app.errors import AppError
from app.models import ReviewMode, ReviewTask
from app.services.artifacts import ArtifactStorage
from app.store import SqliteTaskStore


def test_schema_migration_is_versioned_and_idempotent(tmp_path):
    database = tmp_path / "reviews.db"

    first = SqliteTaskStore(database)
    second = SqliteTaskStore(database)

    assert first.schema_version() == 1
    assert second.schema_version() == 1
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {
        "review_tasks",
        "documents",
        "document_versions",
        "review_runs",
        "extracted_facts",
        "review_issues",
        "manual_events",
        "artifacts",
        "schema_migrations",
    } <= tables


def test_audit_records_survive_a_new_store_instance(tmp_path):
    database = tmp_path / "reviews.db"
    store = SqliteTaskStore(database)
    task = store.save_task(ReviewTask(mode=ReviewMode.QWEN))
    document_id = store.save_document(
        task.id,
        filename="测试笔录.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="a" * 64,
        original_path="task/original/test.docx",
    )
    version_id = store.save_document_version(
        document_id,
        content_sha256="a" * 64,
        parsed_payload={"text": "脱敏测试问答"},
    )
    run_id = store.save_review_run(
        task.id,
        version_id,
        rule_version="1.0.0",
        model="Qwen3.6-35B-A3B",
        status="completed",
        timings={"case_timeline": 12},
    )
    store.save_extracted_fact(run_id, "case.report_reason", {"value": "测试原因"})
    issue_id = store.save_review_issue(run_id, "CASE-001", {"status": "covered"})
    store.append_manual_event(
        task.id,
        issue_id=issue_id,
        event_type="confirmed",
        actor_id="test-operator",
        payload={"reason": "测试确认"},
    )
    store.save_artifact_record(
        task.id,
        version_id,
        artifact_type="original",
        filename="测试笔录.docx",
        path="task/original/test.docx",
        sha256="a" * 64,
        size_bytes=10,
        metadata={"source": "upload"},
    )

    snapshot = SqliteTaskStore(database).get_audit_snapshot(task.id)

    assert snapshot["document"]["id"] == document_id
    assert snapshot["versions"][0]["id"] == version_id
    assert snapshot["runs"][0]["id"] == run_id
    assert snapshot["facts"][0]["path"] == "case.report_reason"
    assert snapshot["issues"][0]["rule_id"] == "CASE-001"
    assert snapshot["events"][0]["actor_id"] == "test-operator"
    assert snapshot["artifacts"][0]["sha256"] == "a" * 64


def test_manual_events_are_append_only_at_the_database_layer(tmp_path):
    database = tmp_path / "reviews.db"
    store = SqliteTaskStore(database)
    task = store.save_task(ReviewTask(mode=ReviewMode.QWEN))
    event_id = store.append_manual_event(
        task.id,
        issue_id=None,
        event_type="note",
        actor_id="test-operator",
        payload={"text": "first"},
    )

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE manual_events SET actor_id = 'changed' WHERE id = ?",
                (event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM manual_events WHERE id = ?", (event_id,))


def test_original_artifact_is_content_addressed_and_verified(tmp_path):
    storage = ArtifactStorage(tmp_path / "artifacts")
    content = b"sanitized interview bytes"

    artifact = storage.save_original("task-001", "record.docx", content)

    assert artifact.sha256 == hashlib.sha256(content).hexdigest()
    assert artifact.path.resolve().is_relative_to((tmp_path / "artifacts").resolve())
    assert storage.read(artifact) == content

    artifact.path.write_bytes(b"tampered")
    with pytest.raises(AppError) as error:
        storage.read(artifact)
    assert error.value.code == "artifact_hash_mismatch"


@pytest.mark.parametrize("filename", ["../record.docx", "..\\record.docx", "folder/record.docx"])
def test_original_artifact_rejects_path_traversal(tmp_path, filename):
    storage = ArtifactStorage(tmp_path / "artifacts")

    with pytest.raises(AppError) as error:
        storage.save_original("task-001", filename, b"content")

    assert error.value.code == "invalid_artifact_name"

