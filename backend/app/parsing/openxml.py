"""
DOCX 安全读取 — 在不依赖 Word 排版引擎的情况下，直接解析 OpenXML。

核心职责：
1. ZIP 安全展开（限制成员数、展开大小、压缩比、图片数）
2. 提取正文段落、表格、实际引用的页眉/页脚
3. 收集被引用的图片部件，供 VLM 转写
4. 非关键损坏（页眉/页脚/图片）不阻塞解析，生成 warning

安全设计：
- MAX_PACKAGE_MEMBERS = 2048：防止 zip bomb
- MAX_TOTAL_UNCOMPRESSED_BYTES = 64 MB
- MAX_COMPRESSION_RATIO = 200：防止压缩比攻击
- 压缩包 ZIP 的 central directory 在验证后才提取内容
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile
import zlib

from lxml import etree

from app.core.errors import AppError
from app.core.models import DocumentWarning, SourceType


# ── OpenXML 命名空间常量 ──────────────────────────────────────────
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NAMESPACE}}}"
WORD_2010_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
W14 = f"{{{WORD_2010_NAMESPACE}}}"
NAMESPACES = {"w": WORD_NAMESPACE, "w14": WORD_2010_NAMESPACE}
RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
R = f"{{{OFFICE_RELATIONSHIP_NAMESPACE}}}"

# ── 安全性阈值 ────────────────────────────────────────────────────
MAX_PACKAGE_MEMBERS = 2048
MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_IMAGES = 64


@dataclass(frozen=True)
class OpenXmlBlock:
    """解析出的一个内容块（段落/表格行/页眉/页脚）。"""
    text: str
    source_type: SourceType


@dataclass(frozen=True)
class OpenXmlImage:
    """从 DOCX 中提取的一张图片。"""
    content: bytes
    media_type: str
    part_name: str
    block_index: int | None = None


@dataclass(frozen=True)
class OpenXmlDocument:
    """完整的 OpenXML 解析结果。"""
    blocks: list[OpenXmlBlock]
    images: list[OpenXmlImage]
    warnings: list[DocumentWarning]


# 支持的图片 MIME 类型映射
MEDIA_TYPES = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}

TEXT_CHECKBOX_MARKERS = {
    "☑": "[选中]",
    "☒": "[选中]",
    "☐": "[未选]",
    "□": "[未选]",
}

SYMBOL_CHECKBOX_MARKERS = {
    ("wingdings 2", "00A3"): "[未选]",
    ("wingdings 2", "0052"): "[选中]",
}

TRUE_VALUES = {"1", "on", "true", "checked"}
FALSE_VALUES = {"0", "off", "false", "unchecked"}


def _checkbox_marker(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return "[选中]"
    if normalized in FALSE_VALUES:
        return "[未选]"
    return "[状态不明]"


def _checkbox_value(node: etree._Element) -> str | None:
    for attribute in (W14 + "val", W + "val", "val"):
        if node.get(attribute) is not None:
            return node.get(attribute)
    return None


def _warn_unknown_checkbox(warnings: list[DocumentWarning], part_name: str) -> None:
    warnings.append(DocumentWarning(
        code="checkbox_state_unknown",
        message="DOCX 包含无法确认选中状态的电子方框，请人工核对。",
        partName=part_name,
    ))


def _normalize_checkbox_glyphs(text: str) -> str:
    return "".join(TEXT_CHECKBOX_MARKERS.get(character, character) for character in text)


def _node_text(
    node: etree._Element,
    warnings: list[DocumentWarning] | None = None,
    part_name: str = "word/document.xml",
) -> str:
    """提取 XML 节点的纯文本内容，处理 w:t / w:tab / w:br 等元素。"""
    collected_warnings = warnings if warnings is not None else []

    def render(element: etree._Element) -> str:
        if element.tag == W + "t":
            return _normalize_checkbox_glyphs(element.text or "")
        if element.tag == W + "tab":
            return "\t"
        if element.tag in {W + "br", W + "cr"}:
            return "\n"
        if element.tag == W + "sdt":
            checkbox = element.find("./w:sdtPr/w14:checkbox", NAMESPACES)
            if checkbox is not None:
                checked = checkbox.find("./w14:checked", NAMESPACES)
                marker = _checkbox_marker(_checkbox_value(checked) if checked is not None else None)
                if marker == "[状态不明]":
                    _warn_unknown_checkbox(collected_warnings, part_name)
                return marker
        if element.tag == W + "fldChar":
            checkbox = element.find("./w:ffData/w:checkBox", NAMESPACES)
            if checkbox is not None:
                state = checkbox.find("./w:checked", NAMESPACES)
                if state is None:
                    state = checkbox.find("./w:default", NAMESPACES)
                marker = _checkbox_marker(_checkbox_value(state) if state is not None else None)
                if marker == "[状态不明]":
                    _warn_unknown_checkbox(collected_warnings, part_name)
                return marker
        if element.tag == W + "sym":
            font = (element.get(W + "font") or "").strip().lower()
            character = (element.get(W + "char") or "").strip().upper()
            marker = SYMBOL_CHECKBOX_MARKERS.get((font, character))
            if marker is not None:
                return marker
            if "checkbox" in font or font == "wingdings 2":
                _warn_unknown_checkbox(collected_warnings, part_name)
                return "[状态不明]"
            return ""
        return "".join(render(child) for child in element)

    return render(node)


def _body_content(
    document_xml: bytes,
    relationships: dict[str, tuple[str, str]],
    warnings: list[DocumentWarning],
) -> tuple[list[OpenXmlBlock], list[tuple[str, int]]]:
    """提取正文块，并记录图片相对正文块的插入位置。"""
    root = etree.fromstring(document_xml)
    body = root.find("w:body", NAMESPACES)
    if body is None:
        return [], []

    blocks: list[OpenXmlBlock] = []
    image_placements: list[tuple[str, int]] = []

    def append_images(node: etree._Element) -> None:
        for image_node in node.findall(".//*[@r:embed]", {**NAMESPACES, "r": OFFICE_RELATIONSHIP_NAMESPACE}):
            relationship = relationships.get(image_node.get(R + "embed") or "")
            if relationship is not None and relationship[0].endswith("/image"):
                image_placements.append((relationship[1], len(blocks)))

    def append_child(child: etree._Element) -> None:
        """递归处理正文子元素，支持 p（段落）、tbl（表格）、sdt（内容控件）。"""
        if child.tag == W + "p":
            text = _node_text(child, warnings).strip()
            if text:
                blocks.append(OpenXmlBlock(text=text, source_type=SourceType.NATIVE_TEXT))
            append_images(child)
        elif child.tag == W + "tbl":
            for row in child.findall("./w:tr", NAMESPACES):
                cells = [
                    _node_text(cell, warnings).strip()
                    for cell in row.findall("./w:tc", NAMESPACES)
                ]
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    blocks.append(OpenXmlBlock(text=text, source_type=SourceType.TABLE))
                append_images(row)
        elif child.tag == W + "sdt":
            content = child.find("./w:sdtContent", NAMESPACES)
            if content is not None:
                for nested in content:
                    append_child(nested)

    for child in body:
        append_child(child)
    return blocks, image_placements


def _body_blocks(document_xml: bytes, warnings: list[DocumentWarning]) -> list[OpenXmlBlock]:
    """从 word/document.xml 提取正文段落、表格和内容控件。"""
    blocks, _ = _body_content(document_xml, {}, warnings)
    return blocks


def _validate_package(archive: ZipFile) -> None:
    """安全验证：检查 DOCX ZIP 包是否超过各项阈值。"""
    infos = archive.infolist()
    if len(infos) > MAX_PACKAGE_MEMBERS:
        raise AppError("docx_expansion_limit", "DOCX 包含过多压缩包成员，已拒绝解析。", 422)
    total = 0
    for info in infos:
        total += info.file_size
        if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise AppError("docx_expansion_limit", "DOCX 单个部件展开后过大，已拒绝解析。", 422)
        if (
            info.file_size >= 1024 * 1024
            and (info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO)
        ):
            raise AppError("docx_expansion_limit", "DOCX 压缩比异常，已拒绝解析。", 422)
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise AppError("docx_expansion_limit", "DOCX 展开后总体积过大，已拒绝解析。", 422)


def _relationship_part(source_part: str) -> str:
    """计算指定部件对应的 .rels 关系文件路径。"""
    directory, filename = posixpath.split(source_part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def _relationships(archive: ZipFile, source_part: str) -> dict[str, tuple[str, str]]:
    """读取指定部件的 .rels 关系文件，返回 {id: (type, target_part)} 映射。"""
    relationship_part = _relationship_part(source_part)
    if relationship_part not in archive.namelist():
        return {}
    root = etree.fromstring(archive.read(relationship_part))
    relationships: dict[str, tuple[str, str]] = {}
    for item in root.findall(f"{{{RELATIONSHIP_NAMESPACE}}}Relationship"):
        if item.get("TargetMode") == "External":
            continue
        target = item.get("Target")
        relationship_id = item.get("Id")
        relationship_type = item.get("Type")
        if not target or not relationship_id or not relationship_type:
            continue
        if target.startswith("/"):
            part_name = target.lstrip("/")
        else:
            part_name = posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))
        if part_name == ".." or part_name.startswith("../"):
            continue
        relationships[relationship_id] = (relationship_type, part_name)
    return relationships


def _referenced_parts(
    archive: ZipFile,
    document_xml: bytes,
) -> tuple[list[tuple[str, SourceType]], list[str]]:
    """查找文档引用的页眉/页脚和图片部件。

    Returns:
        (stories, images) 二元组：
        - stories: 被引用的页眉/页脚部件列表
        - images: 被引用的唯一图片部件路径列表（去重）
    """
    root = etree.fromstring(document_xml)
    document_relationships = _relationships(archive, "word/document.xml")
    stories: list[tuple[str, SourceType]] = []
    images: list[str] = []
    story_ids = [
        (node.get(R + "id"), SourceType.HEADER if node.tag == W + "headerReference" else SourceType.FOOTER)
        for node in root.findall(".//w:sectPr/w:headerReference", NAMESPACES)
        + root.findall(".//w:sectPr/w:footerReference", NAMESPACES)
    ]
    for relationship_id, source_type in story_ids:
        relationship = document_relationships.get(relationship_id or "")
        if relationship is None:
            continue
        _, part_name = relationship
        stories.append((part_name, source_type))
        story_relationships = _relationships(archive, part_name)
        story_root = etree.fromstring(archive.read(part_name))
        for node in story_root.findall(".//*[@r:embed]", {**NAMESPACES, "r": OFFICE_RELATIONSHIP_NAMESPACE}):
            image_relationship = story_relationships.get(node.get(R + "embed") or "")
            if image_relationship is not None and image_relationship[0].endswith("/image"):
                images.append(image_relationship[1])
    for node in root.findall(".//*[@r:embed]", {**NAMESPACES, "r": OFFICE_RELATIONSHIP_NAMESPACE}):
        relationship = document_relationships.get(node.get(R + "embed") or "")
        if relationship is not None and relationship[0].endswith("/image"):
            images.append(relationship[1])
    return stories, list(dict.fromkeys(images))


def _story_blocks(
    part_xml: bytes,
    source_type: SourceType,
    warnings: list[DocumentWarning],
    part_name: str,
) -> list[OpenXmlBlock]:
    """提取页眉或页脚部件中的段落。"""
    root = etree.fromstring(part_xml)
    blocks: list[OpenXmlBlock] = []
    for paragraph in root.findall(".//w:p", NAMESPACES):
        text = _node_text(paragraph, warnings, part_name).strip()
        if text:
            blocks.append(OpenXmlBlock(text=text, source_type=source_type))
    return blocks


def _optional_story(
    archive: ZipFile,
    part_name: str,
    source_type: SourceType,
    warnings: list[DocumentWarning],
) -> list[OpenXmlBlock]:
    """安全读取页眉/页脚，损坏时生成 warning 而非抛出异常。"""
    try:
        return _story_blocks(archive.read(part_name), source_type, warnings, part_name)
    except (BadZipFile, EOFError, RuntimeError, zlib.error, etree.XMLSyntaxError):
        warnings.append(DocumentWarning(
            code="part_corrupt",
            message="DOCX 的可选页眉或页脚已损坏，正文仍继续解析。",
            partName=part_name,
        ))
        return []


def read_docx_parts(content: bytes) -> OpenXmlDocument:
    """读取 DOCX 文件内容为结构化 OpenXmlDocument。

    处理顺序：验证 ZIP → 读取正文 → 查找页眉/页脚/图片引用
    → 读取页眉/页脚 → 收集图片 → 返回结构化结果。

    Args:
        content: DOCX 文件的完整二进制内容。

    Returns:
        OpenXmlDocument: 包含内容块、图片列表和警告。
    """
    warnings: list[DocumentWarning] = []
    images: list[OpenXmlImage] = []

    with ZipFile(BytesIO(content)) as archive:
        _validate_package(archive)
        document_xml = archive.read("word/document.xml")
        story_parts, image_parts = _referenced_parts(archive, document_xml)
        document_relationships = _relationships(archive, "word/document.xml")

        header_blocks = [
            block
            for part_name, source_type in story_parts
            if source_type == SourceType.HEADER
            for block in _optional_story(archive, part_name, SourceType.HEADER, warnings)
        ]
        footer_blocks = [
            block
            for part_name, source_type in story_parts
            if source_type == SourceType.FOOTER
            for block in _optional_story(archive, part_name, SourceType.FOOTER, warnings)
        ]
        body_blocks, body_image_placements = _body_content(
            document_xml,
            document_relationships,
            warnings,
        )
        # 组合顺序：页眉优先，正文居中，页脚最后
        blocks = [*header_blocks, *body_blocks, *footer_blocks]
        first_body_image_positions: dict[str, int] = {}
        for part_name, block_index in body_image_placements:
            first_body_image_positions.setdefault(part_name, len(header_blocks) + block_index)

        if len(image_parts) > MAX_IMAGES:
            raise AppError("docx_expansion_limit", "DOCX 引用图片数量过多，已拒绝解析。", 422)
        for part_name in image_parts:
            suffix = PurePosixPath(part_name).suffix.lower()
            media_type = MEDIA_TYPES.get(suffix)
            if media_type is None:
                warnings.append(DocumentWarning(
                    code="media_unsupported",
                    message="DOCX 包含暂不支持识别的媒体格式。",
                    partName=part_name,
                ))
                continue
            try:
                image = archive.read(part_name)
            except (BadZipFile, EOFError, RuntimeError, zlib.error):
                warnings.append(DocumentWarning(
                    code="media_corrupt",
                    message="DOCX 中的非关键图片已损坏，正文仍继续解析。",
                    partName=part_name,
                ))
                continue
            images.append(OpenXmlImage(
                content=image,
                media_type=media_type,
                part_name=part_name,
                block_index=first_body_image_positions.get(part_name),
            ))

    return OpenXmlDocument(blocks=blocks, images=images, warnings=warnings)
