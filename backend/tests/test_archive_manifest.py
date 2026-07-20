from pathlib import Path

from fastapi.testclient import TestClient

from app.storage import store
from app.main import app
from app.storage import artifacts
from app.storage.artifacts import ArtifactStorage
from app.storage.store import SqliteTaskStore


client = TestClient(app)


def _generated_demo(tmp_path, monkeypatch) -> tuple[str, dict]:
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(tmp_path / "reviews.db"))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))
    created = client.post("/api/v1/reviews/demos/case-01-baseline", json={})
    task_id = created.json()["taskId"]
    client.post(
        f"/api/v1/reviews/{task_id}/issues/RISK-001/actions",
        json={"status": "resolved", "reason": "已完成脱敏核对。", "actorId": "test-operator"},
    )
    generated = client.post(f"/api/v1/reviews/{task_id}/artifacts/generate")
    assert generated.status_code == 200
    return task_id, generated.json()


def test_generated_bundle_can_archive_and_remains_downloadable_read_only(tmp_path, monkeypatch):
    task_id, task = _generated_demo(tmp_path, monkeypatch)

    archived = client.post(f"/api/v1/reviews/{task_id}/archive")

    assert archived.status_code == 200
    manifest = next(item for item in task["artifacts"] if item["type"] == "archive_manifest")
    assert client.get(f"/api/v1/reviews/{task_id}/artifacts/{manifest['id']}").status_code == 200
    mutation = client.post(
        f"/api/v1/reviews/{task_id}/issues/RISK-001/actions",
        json={"status": "ignored", "reason": "不得修改。", "actorId": "test-operator"},
    )
    assert mutation.status_code == 409
    assert mutation.json()["error"]["code"] == "review_archived"


def test_archive_rejects_a_tampered_generated_artifact(tmp_path, monkeypatch):
    task_id, _task = _generated_demo(tmp_path, monkeypatch)
    snapshot = store.STORE.get_audit_snapshot(task_id)
    report = next(item for item in snapshot["artifacts"] if item["artifact_type"] == "review_pdf")
    Path(report["path"]).write_bytes(b"tampered")

    archived = client.post(f"/api/v1/reviews/{task_id}/archive")

    assert archived.status_code == 409
    assert archived.json()["error"]["code"] == "artifact_hash_mismatch"
