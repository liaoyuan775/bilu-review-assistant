import hashlib
import json
import sqlite3

import pytest

from app.core.errors import AppError
from app.core.models import ReviewMode, ReviewResult, ReviewStatus, ReviewTask
from app.storage.artifacts import ArtifactStorage
from app.storage.store import SqliteTaskStore


def test_schema_migration_is_versioned_and_idempotent(tmp_path):
    database = tmp_path / "reviews.db"

    first = SqliteTaskStore(database)
    second = SqliteTaskStore(database)

    assert first.schema_version() == 2
    assert second.schema_version() == 2
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


def test_stale_task_snapshot_cannot_overwrite_newer_archive_state(tmp_path):
    store = SqliteTaskStore(tmp_path / "reviews.db")
    task = store.save_task(ReviewTask(mode=ReviewMode.QWEN))
    stale = store.get_task(task.id)
    current = store.get_task(task.id)
    current.reviewStatus = ReviewStatus.ARCHIVED
    store.save_task(current)

    stale.errorMessage = "late model response"
    with pytest.raises(AppError) as error:
        store.save_task(stale)

    assert error.value.code == "task_revision_conflict"
    assert store.get_task(task.id).reviewStatus.value == "archived"


def test_legacy_evidence_location_does_not_break_task_history(tmp_path):
    database = tmp_path / "reviews.db"
    store = SqliteTaskStore(database)
    task = store.save_task(ReviewTask(mode=ReviewMode.QWEN, results=[ReviewResult(ruleId="CASE-001")]))

    payload = task.model_dump(mode="json")
    payload["results"][0]["evidenceLocation"] = {"page": 1, "paragraph": 2}
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE review_tasks SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), task.id),
        )

    assert store.get_task(task.id).results[0].ruleId == "CASE-001"
    assert store.list_tasks()[0].results[0].ruleId == "CASE-001"


def test_review_run_children_are_rolled_back_when_issue_persistence_fails(tmp_path):
    store = SqliteTaskStore(tmp_path / "reviews.db")
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

    with pytest.raises(sqlite3.IntegrityError):
        store.persist_review_outcome(
            task,
            version_id,
            rule_version="1.0.0",
            model="Qwen3.6-35B-A3B",
            timings={},
            facts={"case.report_reason": {"value": "测试"}},
            entities={},
            issues=[("CASE-001", {"status": "covered"}), ("CASE-001", {"status": "covered"})],
        )

    snapshot = store.get_audit_snapshot(task.id)
    assert snapshot["runs"] == []
    assert snapshot["facts"] == []
    assert snapshot["issues"] == []


def test_stale_task_and_manual_event_are_rejected_together(tmp_path):
    store = SqliteTaskStore(tmp_path / "reviews.db")
    task = store.save_task(ReviewTask(mode=ReviewMode.QWEN))
    stale = store.get_task(task.id)
    current = store.get_task(task.id)
    current.reviewStatus = ReviewStatus.ARCHIVED
    store.save_task(current)

    with pytest.raises(AppError) as error:
        store.save_task_with_events(stale, [{
            "issue_id": None,
            "event_type": "resolved",
            "actor_id": "test-operator",
            "payload": {"ruleId": "CASE-001"},
        }])

    assert error.value.code == "task_revision_conflict"
    assert store.get_audit_snapshot(task.id)["events"] == []


def test_review_outcome_atomically_updates_current_task_run_and_children(tmp_path):
    store = SqliteTaskStore(tmp_path / "reviews.db")
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
    task.documentVersionId = version_id

    run_id = store.persist_review_outcome(
        task,
        version_id,
        rule_version="1.0.0",
        model="Qwen3.6-35B-A3B",
        timings={"case_timeline": 12},
        facts={"case.report_reason": {"value": "测试"}},
        entities={},
        issues=[("CASE-001", {"status": "covered"})],
        events=[{
            "issue_id": None,
            "event_type": "follow_up_answer",
            "actor_id": "test-operator",
            "payload": {"ruleId": "CASE-001"},
        }],
    )

    saved = store.get_task(task.id)
    snapshot = store.get_audit_snapshot(task.id)
    assert task.reviewRunId == run_id
    assert saved.reviewRunId == run_id
    assert snapshot["runs"][0]["status"] == "completed"
    assert snapshot["facts"][0]["run_id"] == run_id
    assert snapshot["issues"][0]["run_id"] == run_id
    assert snapshot["events"][0]["event_type"] == "follow_up_answer"


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
