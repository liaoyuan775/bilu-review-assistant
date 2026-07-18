"""
文件制品存储 — 内存寻址的文件持久化服务。

职责边界：
- 本文件负责源文件和生成产物的磁盘读写。
- 不关心业务语义（如报告格式、审查状态），只关心文件的安全存取。
- 使用"内容寻址"方式：文件存储路径包含 SHA-256 前 16 位，相同内容只存一份。

安全设计：
1. 路径穿越防护：所有路径必须先 resolve()，再检查是否在 root 目录下。
2. 内容完整性：读文件时会校验 SHA-256 是否匹配。
3. 原子写入：先写 .tmp 文件，再 rename 到目标路径（防止写一半崩溃）。
4. 文件名净化：剔除文件名中的非法字符（< > : " / \\ | ? * 等）。

目录结构：
    {root}/{task_id}/{artifact_type}/{sha256[:16]}-{filename}

依赖关系：
    - core/config.py: REVIEW_ARTIFACT_ROOT 制品根目录。
    - core/errors.py: AppError 异常体系。
    - core/models.py: now_iso 时间工具。
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from app.core.config import REVIEW_ARTIFACT_ROOT
from app.core.errors import AppError
from app.core.models import now_iso


# task_id 允许的字符集（字母数字 + ._-，最多 128 字）
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# Windows 和 Linux 下的非法文件名字符
_INVALID_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
# 合法的生成产物类型枚举
GENERATED_REVIEW_ARTIFACT_TYPES = (
    "review_pdf",
    "follow_up_docx",
    "structured_json",
    "archive_manifest",
)


@dataclass(frozen=True)
class DocumentArtifact:
    """文件制品的数据封装。

    这是一个不可变数据类，包含文件的所有元数据。
    不持有文件内容（bytes），只持有定位信息（path + sha256）。

    Attributes:
        id:           唯一标识。
        taskId:       所属审查任务 ID。
        filename:     原始文件名（已净化）。
        path:         文件在磁盘上的完整路径。
        sha256:       文件内容的 SHA-256 摘要。
        sizeBytes:    文件大小（字节）。
        artifactType: 产物类型（original / review_pdf / follow_up_docx 等）。
        createdAt:    创建时间（ISO 格式）。
    """
    id: str
    taskId: str
    filename: str
    path: Path
    sha256: str
    sizeBytes: int
    artifactType: str
    createdAt: str


class ArtifactStorage:
    """文件制品存储 — 内容寻址的安全文件管理。

    使用示例：
        storage = ArtifactStorage(Path("./artifacts"))
        # 保存用户上传的源文件
        artifact = storage.save_original("task-123", "笔录.docx", content)
        # 读取已保存的制品
        content = storage.read(artifact)
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_original(self, task_id: str, filename: str, content: bytes) -> DocumentArtifact:
        """保存用户上传的原始文件。"""
        return self._save(task_id, "original", filename, content)

    def save_generated(
        self,
        task_id: str,
        artifact_type: str,
        filename: str,
        content: bytes,
    ) -> DocumentArtifact:
        """保存系统生成的产物（PDF、DOCX 等）。

        Raises:
            AppError: artifact_type 不在 GENERATED_REVIEW_ARTIFACT_TYPES 中。
        """
        if artifact_type not in GENERATED_REVIEW_ARTIFACT_TYPES:
            raise AppError("invalid_artifact_type", "归档产物类型无效。", 422)
        return self._save(task_id, artifact_type, filename, content)

    def _save(
        self,
        task_id: str,
        artifact_type: str,
        filename: str,
        content: bytes,
    ) -> DocumentArtifact:
        """内部保存方法 — 执行安全检查和内容寻址写入。"""
        safe_task_id = self._task_id(task_id)
        safe_filename = self._filename(filename)
        digest = sha256(content).hexdigest()
        directory = (self.root / safe_task_id / artifact_type).resolve()
        if not directory.is_relative_to(self.root):
            raise AppError("invalid_artifact_path", "产物路径超出受控目录。", 422)
        directory.mkdir(parents=True, exist_ok=True)
        target = (directory / f"{digest[:16]}-{safe_filename}").resolve()
        if not target.is_relative_to(self.root):
            raise AppError("invalid_artifact_path", "产物路径超出受控目录。", 422)
        if target.exists():
            # 内容寻址：如果文件已存在，校验 SHA-256 是否一致
            if sha256(target.read_bytes()).hexdigest() != digest:
                raise AppError("artifact_hash_collision", "同名内容寻址产物的哈希不一致。", 500)
        else:
            # 原子写入：先写 .tmp 后缀，然后 rename
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
            artifactType=artifact_type,
            createdAt=now_iso(),
        )

    def read(self, artifact: DocumentArtifact) -> bytes:
        """读取制品文件内容，并校验 SHA-256 完整性。"""
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
        """验证 task_id 格式安全。"""
        if not _TASK_ID.fullmatch(task_id) or ".." in task_id:
            raise AppError("invalid_artifact_path", "任务标识不能用于产物路径。", 422)
        return task_id

    @staticmethod
    def _filename(filename: str) -> str:
        """净化文件名：移除非法路径字符和遍历风险。"""
        value = filename.strip()
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise AppError("invalid_artifact_name", "原件文件名包含非法路径。", 422)
        safe = _INVALID_FILENAME.sub("_", value).rstrip(". ")
        if not safe:
            raise AppError("invalid_artifact_name", "原件文件名无效。", 422)
        return safe


# ── 模块级单例与便捷函数 ──────────────────────────────────────

ARTIFACT_STORAGE = ArtifactStorage(REVIEW_ARTIFACT_ROOT)


def save_original(task_id: str, filename: str, content: bytes) -> DocumentArtifact:
    return ARTIFACT_STORAGE.save_original(task_id, filename, content)


def save_generated(
    task_id: str,
    artifact_type: str,
    filename: str,
    content: bytes,
) -> DocumentArtifact:
    return ARTIFACT_STORAGE.save_generated(task_id, artifact_type, filename, content)


def read_artifact_record(record: dict) -> bytes:
    """从数据库记录中读取制品文件内容。"""
    artifact = DocumentArtifact(
        id=record["id"],
        taskId=record["task_id"],
        filename=record["filename"],
        path=Path(record["path"]),
        sha256=record["sha256"],
        sizeBytes=record["size_bytes"],
        artifactType=record["artifact_type"],
        createdAt=record["created_at"],
    )
    return ARTIFACT_STORAGE.read(artifact)
