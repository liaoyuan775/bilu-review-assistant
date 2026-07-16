from app.models import ReviewTask, now_iso


TASKS: dict[str, ReviewTask] = {}


def save_task(task: ReviewTask) -> ReviewTask:
    task.updatedAt = now_iso()
    TASKS[task.id] = task
    return task


def get_task(task_id: str) -> ReviewTask | None:
    return TASKS.get(task_id)
