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
