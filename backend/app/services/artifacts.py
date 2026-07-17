from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from app.config import REVIEW_ARTIFACT_ROOT
from app.errors import AppError
from app.models import now_iso


_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_INVALID_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")


@dataclass(frozen=True)
class DocumentArtifact:
    id: str
    taskId: str
    filename: str
    path: Path
    sha256: str
    sizeBytes: int
    artifactType: str
    createdAt: str


class ArtifactStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_original(self, task_id: str, filename: str, content: bytes) -> DocumentArtifact:
        safe_task_id = self._task_id(task_id)
        safe_filename = self._filename(filename)
        digest = sha256(content).hexdigest()
        directory = (self.root / safe_task_id / "original").resolve()
        if not directory.is_relative_to(self.root):
            raise AppError("invalid_artifact_path", "产物路径超出受控目录。", 422)
        directory.mkdir(parents=True, exist_ok=True)
        target = (directory / f"{digest[:16]}-{safe_filename}").resolve()
        if not target.is_relative_to(self.root):
            raise AppError("invalid_artifact_path", "产物路径超出受控目录。", 422)
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != digest:
                raise AppError("artifact_hash_collision", "同名内容寻址产物的哈希不一致。", 500)
        else:
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        return DocumentArtifact(
            id=str(uuid4()),
            taskId=safe_task_id,
            filename=safe_filename,
            path=target,
            sha256=digest,
            sizeBytes=len(content),
            artifactType="original",
            createdAt=now_iso(),
        )

    def read(self, artifact: DocumentArtifact) -> bytes:
        path = artifact.path.resolve()
        if not path.is_relative_to(self.root):
            raise AppError("invalid_artifact_path", "产物路径超出受控目录。", 422)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise AppError("artifact_not_found", "归档产物不存在或无法读取。", 404) from exc
        if sha256(content).hexdigest() != artifact.sha256:
            raise AppError("artifact_hash_mismatch", "归档产物哈希校验失败。", 409)
        return content

    @staticmethod
    def _task_id(task_id: str) -> str:
        if not _TASK_ID.fullmatch(task_id) or ".." in task_id:
            raise AppError("invalid_artifact_path", "任务标识不能用于产物路径。", 422)
        return task_id

    @staticmethod
    def _filename(filename: str) -> str:
        value = filename.strip()
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise AppError("invalid_artifact_name", "原件文件名包含非法路径。", 422)
        safe = _INVALID_FILENAME.sub("_", value).rstrip(". ")
        if not safe:
            raise AppError("invalid_artifact_name", "原件文件名无效。", 422)
        return safe


ARTIFACT_STORAGE = ArtifactStorage(REVIEW_ARTIFACT_ROOT)


def save_original(task_id: str, filename: str, content: bytes) -> DocumentArtifact:
    return ARTIFACT_STORAGE.save_original(task_id, filename, content)
