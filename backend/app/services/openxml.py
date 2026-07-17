from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile
import zlib

from lxml import etree

from app.models import DocumentWarning, SourceType


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NAMESPACE}}}"
NAMESPACES = {"w": WORD_NAMESPACE}


@dataclass(frozen=True)
class OpenXmlBlock:
    text: str
    source_type: SourceType


@dataclass(frozen=True)
class OpenXmlImage:
    content: bytes
    media_type: str
    part_name: str


@dataclass(frozen=True)
class OpenXmlDocument:
    blocks: list[OpenXmlBlock]
    images: list[OpenXmlImage]
    warnings: list[DocumentWarning]


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


def _node_text(node: etree._Element) -> str:
    parts: list[str] = []
    for element in node.iter():
        if element.tag == W + "t" and element.text:
            parts.append(element.text)
        elif element.tag == W + "tab":
            parts.append("\t")
        elif element.tag in {W + "br", W + "cr"}:
            parts.append("\n")
    return "".join(parts)


def _body_blocks(document_xml: bytes) -> list[OpenXmlBlock]:
    root = etree.fromstring(document_xml)
    body = root.find("w:body", NAMESPACES)
    if body is None:
        return []

    blocks: list[OpenXmlBlock] = []
    for child in body:
        if child.tag == W + "p":
            text = _node_text(child).strip()
            if text:
                blocks.append(OpenXmlBlock(text=text, source_type=SourceType.NATIVE_TEXT))
        elif child.tag == W + "tbl":
            for row in child.findall("./w:tr", NAMESPACES):
                cells = [
                    _node_text(cell).strip()
                    for cell in row.findall("./w:tc", NAMESPACES)
                ]
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    blocks.append(OpenXmlBlock(text=text, source_type=SourceType.TABLE))
    return blocks


def _story_blocks(part_xml: bytes, source_type: SourceType) -> list[OpenXmlBlock]:
    root = etree.fromstring(part_xml)
    blocks: list[OpenXmlBlock] = []
    for paragraph in root.findall(".//w:p", NAMESPACES):
        text = _node_text(paragraph).strip()
        if text:
            blocks.append(OpenXmlBlock(text=text, source_type=source_type))
    return blocks


def _optional_story(
    archive: ZipFile,
    part_name: str,
    source_type: SourceType,
    warnings: list[DocumentWarning],
) -> list[OpenXmlBlock]:
    try:
        return _story_blocks(archive.read(part_name), source_type)
    except (BadZipFile, EOFError, RuntimeError, zlib.error, etree.XMLSyntaxError):
        warnings.append(DocumentWarning(
            code="part_corrupt",
            message="DOCX 的可选页眉或页脚已损坏，正文仍继续解析。",
            partName=part_name,
        ))
        return []


def read_docx_parts(content: bytes) -> OpenXmlDocument:
    warnings: list[DocumentWarning] = []
    images: list[OpenXmlImage] = []

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")
        names = archive.namelist()
        header_blocks = [
            block
            for part_name in sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml"))
            for block in _optional_story(archive, part_name, SourceType.HEADER, warnings)
        ]
        footer_blocks = [
            block
            for part_name in sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml"))
            for block in _optional_story(archive, part_name, SourceType.FOOTER, warnings)
        ]
        blocks = [*header_blocks, *_body_blocks(document_xml), *footer_blocks]

        for part_name in names:
            if not part_name.startswith("word/media/"):
                continue
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
            images.append(OpenXmlImage(content=image, media_type=media_type, part_name=part_name))

    return OpenXmlDocument(blocks=blocks, images=images, warnings=warnings)
