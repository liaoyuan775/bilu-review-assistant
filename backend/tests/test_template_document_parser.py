import asyncio
import base64
from io import BytesIO
import os
from pathlib import Path
import struct
from zipfile import ZipFile

import pytest
from docx import Document
from docx.shared import Inches

from app.services.parser import parse_document


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl9sAAAAASUVORK5CYII="
)


def _docx_with_corrupt_media() -> bytes:
    document = Document()
    document.add_paragraph("电信网络诈骗案件询问笔录（模板）")
    document.add_paragraph("问：你听清楚了没有？")
    document.add_paragraph("答：我听清楚了。")
    document.add_picture(BytesIO(PNG_1X1), width=Inches(0.2))
    output = BytesIO()
    document.save(output)

    content = bytearray(output.getvalue())
    with ZipFile(BytesIO(content)) as archive:
        image = archive.getinfo("word/media/image1.png")

    filename_length, extra_length = struct.unpack_from("<HH", content, image.header_offset + 26)
    compressed_start = image.header_offset + 30 + filename_length + extra_length
    content[compressed_start + image.compress_size // 2] ^= 0x01
    return bytes(content)


def test_docx_with_corrupt_nonessential_media_keeps_document_text():
    parsed = asyncio.run(parse_document("template.docx", _docx_with_corrupt_media()))

    assert "电信网络诈骗案件询问笔录" in parsed.text
    assert any(warning.code == "media_corrupt" for warning in parsed.warnings)


@pytest.mark.skipif(not os.getenv("BILU_TEMPLATE_PATH"), reason="BILU_TEMPLATE_PATH is not configured")
def test_provided_internal_template_is_parseable_when_available():
    path = Path(os.environ["BILU_TEMPLATE_PATH"])

    parsed = asyncio.run(parse_document(path.name, path.read_bytes()))

    assert "电信网络诈骗案件询问笔录" in parsed.text
    assert sum(len(page.paragraphs) for page in parsed.pages) == 144
    assert parsed.text.count("问：") + parsed.text.count("问:") == 33
    assert "以上笔录给你看一下" in parsed.text
    assert any(warning.code == "media_corrupt" for warning in parsed.warnings)
