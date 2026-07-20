"""
文档解析入口 — 按文件扩展名分派到 DOCX 或 PDF 解析分支。

整体流程：
1. 统一入口 parse_document(filename, content)
2. 按扩展名分派到 _parse_docx 或 _parse_pdf
3. DOCX 和 PDF 各自读出 DocumentParagraph 列表
4. _paginate 按字符数切分逻辑页（非 Word/PDF 物理页）
5. _finalize_pages 为每个段落生成稳定的 ID 和字符范围
6. 调用 reconstruct_question_answers 构建问答对

注意：
- 逻辑页（1800 字符/页）不等于 Word 打印页或 PDF 页面
- 段落 ID 是证据定位的锚点，不可随意变更哈希算法
"""

import logging
from pathlib import Path
import re
from hashlib import sha256

import fitz
from app.core.config import MAX_FILE_SIZE
from app.core.development_logging import log_event, log_payload
from app.core.errors import AppError
from app.core.models import DocumentPage, DocumentParagraph, ParsedDocument, SourceType
from app.parsing.openxml import read_docx_parts
from app.parsing.question_answer import reconstruct_document_structure
from app.parsing.vision import transcribe_image


PARSER_VERSION = "openxml-pymupdf-v1"

# 段落实体边界标记 — 遇到这些内容时停止问答收集
_QUESTION_PAIR_BOUNDARIES = (
    "询问结束",
    "被询问人已逐页核对",
    "被询问人确认笔录",
    "本次笔录重点记录",
    "本笔录为虚构测试材料",
    "被询问人签名",
    "询问人签名",
    "记录人签名",
    "核对结果",
    "本文件全部信息",
)


def _normalize(text: str) -> str:
    """规范化空白字符为单个空格。"""
    return " ".join(text.split())


def _join_question_lines(lines: list[str]) -> str:
    """将多行问答合并为一段，英文单词间加空格，中文直接拼接。"""
    merged = lines[0]
    for line in lines[1:]:
        separate = line.startswith(("问：", "问:", "答：", "答:")) or (
            merged[-1].isascii()
            and merged[-1].isalnum()
            and line[0].isascii()
            and line[0].isalnum()
        )
        merged += (" " if separate else "") + line
    return merged


def _native_blocks(text: str) -> list[DocumentParagraph]:
    """将纯文本按问答结构分段，合并同组问答行。

    "问："开头或编号+"问："开头的行会被合并为一个段落，
    其他行保持独立段落。
    """
    lines = [_normalize(line) for line in text.splitlines() if _normalize(line)]
    blocks: list[DocumentParagraph] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        has_number_prefix = (
            re.fullmatch(r"\d{1,3}", line) is not None
            and index + 1 < len(lines)
            and lines[index + 1].startswith(("问：", "问:"))
        )
        if not has_number_prefix and not line.startswith(("问：", "问:")):
            blocks.append(DocumentParagraph(text=line, sourceType=SourceType.NATIVE_TEXT))
            index += 1
            continue

        parts = [line]
        index += 1
        if has_number_prefix:
            parts.append(lines[index])
            index += 1

        while index < len(lines):
            if lines[index].startswith(_QUESTION_PAIR_BOUNDARIES):
                break
            starts_next_question = lines[index].startswith(("问：", "问:"))
            starts_next_numbered_question = (
                re.fullmatch(r"\d{1,3}", lines[index]) is not None
                and index + 1 < len(lines)
                and lines[index + 1].startswith(("问：", "问:"))
            )
            if starts_next_question or starts_next_numbered_question:
                break
            parts.append(lines[index])
            index += 1

        blocks.append(DocumentParagraph(text=_join_question_lines(parts), sourceType=SourceType.NATIVE_TEXT))

    return blocks


def _native_pdf_blocks(pdf_page: fitz.Page) -> list[DocumentParagraph]:
    """从 PyMuPDF 页面对象提取原生文本块，按 (y, x) 排序后转化为段落。"""
    text_blocks = [
        block
        for block in pdf_page.get_text("dict").get("blocks", [])
        if block.get("type") == 0 and block.get("lines")
    ]
    text_blocks.sort(key=lambda block: (block["bbox"][1], block["bbox"][0]))

    paragraphs: list[DocumentParagraph] = []
    for block in text_blocks:
        lines = [
            "".join(span.get("text", "") for span in line.get("spans", []))
            for line in block["lines"]
        ]
        bbox = [float(value) for value in block["bbox"]]
        paragraphs.extend(
            paragraph.model_copy(update={"bbox": bbox})
            for paragraph in _native_blocks("\n".join(lines))
        )
    return paragraphs


def _vision_blocks(payload: dict) -> list[DocumentParagraph]:
    """将 VLM 转写的 JSON 段落列表转为标准段落（来源标记为 vision）。"""
    confidence = float(payload["confidence"])
    return [
        DocumentParagraph(text=_normalize(text), sourceType=SourceType.VISION, confidence=confidence)
        for text in payload["paragraphs"]
        if _normalize(text)
    ]


def _merge_unique(blocks: list[DocumentParagraph], additions: list[DocumentParagraph]) -> None:
    """去重追加段落，避免 PDF 中原生文本和嵌图转写结果重复。"""
    existing = {_normalize(block.text) for block in blocks}
    for block in additions:
        normalized = _normalize(block.text)
        if normalized and normalized not in existing:
            blocks.append(block)
            existing.add(normalized)


def _paginate(blocks: list[DocumentParagraph], target_chars: int = 1800) -> list[DocumentPage]:
    """将段落列表按目标字符数分页（逻辑页）。"""
    pages: list[DocumentPage] = []
    current: list[DocumentParagraph] = []
    chars = 0
    for block in blocks:
        if current and chars + len(block.text) > target_chars:
            pages.append(DocumentPage(page=len(pages) + 1, paragraphs=current))
            current = []
            chars = 0
        current.append(block)
        chars += len(block.text)
    if current:
        pages.append(DocumentPage(page=len(pages) + 1, paragraphs=current))
    return pages


def _finalize_pages(pages: list[DocumentPage]) -> tuple[list[DocumentPage], str]:
    """为每个页面中的段落生成稳定 ID、字符范围和全文拼接。

    段落 ID 算法：
      document_digest = SHA-256(全文档段落指纹)
      paragraph.id = SHA-256(document_digest:page:index:sourceType:text)[:24]

    只要文档内容不变，同一段落的 ID 在每次解析中保持一致。
    这是证据锚点的稳定性保证。
    """
    document_identity = "\0".join(
        f"{page.page}:{index}:{paragraph.sourceType.value}:{paragraph.text}"
        for page in pages
        for index, paragraph in enumerate(page.paragraphs, start=1)
    )
    document_digest = sha256(document_identity.encode("utf-8")).hexdigest()
    text_parts: list[str] = []
    offset = 0
    finalized_pages: list[DocumentPage] = []
    for page in pages:
        paragraphs: list[DocumentParagraph] = []
        for index, paragraph in enumerate(page.paragraphs, start=1):
            start = offset
            end = start + len(paragraph.text)
            identity = f"{document_digest}:{page.page}:{index}:{paragraph.sourceType.value}:{paragraph.text}"
            paragraphs.append(paragraph.model_copy(update={
                "id": sha256(identity.encode("utf-8")).hexdigest()[:24],
                "charStart": start,
                "charEnd": end,
            }))
            text_parts.append(paragraph.text)
            offset = end + 1
        finalized_pages.append(page.model_copy(update={"paragraphs": paragraphs}))
    return finalized_pages, "\n".join(text_parts)


async def _parse_docx(filename: str, content: bytes) -> ParsedDocument:
    """解析 DOCX 文件：读取 OpenXML → 提取段落 → 转写图片 → 分页 → 问答重建。"""
    try:
        package = read_docx_parts(content)
        native_blocks = [
            DocumentParagraph(text=_normalize(block.text), sourceType=block.source_type)
            for block in package.blocks
            if _normalize(block.text)
        ]
    except Exception as exc:
        raise AppError("parse_failed", "DOCX 文件无法解析，请确认文件未损坏。", 422) from exc

    positioned_images: dict[int, list] = {}
    trailing_images = []
    for image_part in package.images:
        if image_part.block_index is None:
            trailing_images.append(image_part)
        else:
            positioned_images.setdefault(image_part.block_index, []).append(image_part)

    blocks: list[DocumentParagraph] = []
    for block_index, native_block in enumerate(native_blocks):
        for image_part in positioned_images.get(block_index, []):
            log_event(logging.DEBUG, "parser.docx_image", filename=filename, media_type=image_part.media_type, bytes=len(image_part.content))
            blocks.extend(_vision_blocks(await transcribe_image(image_part.content, image_part.media_type)))
        blocks.append(native_block)
    for image_part in [*positioned_images.get(len(native_blocks), []), *trailing_images]:
        image = image_part.content
        media_type = image_part.media_type
        log_event(logging.DEBUG, "parser.docx_image", filename=filename, media_type=media_type, bytes=len(image))
        blocks.extend(_vision_blocks(await transcribe_image(image, media_type)))
    if not blocks:
        raise AppError("empty_document", "文档中没有可供审查的文字或图片内容。", 422)
    pages, full_text = _finalize_pages(_paginate(blocks))
    question_answers, evidence_blocks = reconstruct_document_structure(pages)
    parsed = ParsedDocument(
        name=filename,
        format="DOCX",
        pageCount=len(pages),
        pages=pages,
        text=full_text,
        sizeLabel=f"{len(content) / 1024 / 1024:.2f} MB",
        warnings=package.warnings,
        questionAnswers=question_answers,
        evidenceBlocks=evidence_blocks,
    )
    log_event(logging.INFO, "parser.docx_complete", filename=filename, pages=parsed.pageCount, paragraphs=len(blocks), images=len(package.images), warnings=len(package.warnings), chars=len(parsed.text))
    log_payload("document.parsed_text", parsed.text, filename=filename, format=parsed.format)
    return parsed


async def _parse_pdf(filename: str, content: bytes) -> ParsedDocument:
    """解析 PDF 文件：逐页提取原生文本 → 按策略处理图片 → 分页 → 问答重建。

    每页策略：
    - 原生文本 < 20 字：整页 2x 渲染为图片，交给 VLM 转写
    - 原生文本 >= 20 字：保留原生文本，对每张嵌入图片单独调用 VLM，去重合并
    """
    try:
        document = fitz.open(stream=content, filetype="pdf")
        if document.needs_pass:
            raise AppError("parse_failed", "PDF 已加密，无法解析。", 422)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("parse_failed", "PDF 文件无法解析，请确认文件未损坏。", 422) from exc
    pages: list[DocumentPage] = []
    try:
        for index, pdf_page in enumerate(document):
            blocks = _native_pdf_blocks(pdf_page)
            image_refs = pdf_page.get_images(full=True)
            native_length = sum(len(block.text) for block in blocks)
            if native_length < 20:
                log_event(logging.DEBUG, "parser.pdf_page_ocr", filename=filename, page=index + 1, native_chars=native_length)
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                blocks = _vision_blocks(await transcribe_image(pixmap.tobytes("png"), "image/png"))
            else:
                seen_xrefs: set[int] = set()
                for image_ref in image_refs:
                    xref = image_ref[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    extracted = document.extract_image(xref)
                    media_type = f"image/{extracted.get('ext', 'png')}"
                    log_event(logging.DEBUG, "parser.pdf_embedded_image", filename=filename, page=index + 1, xref=xref, media_type=media_type, bytes=len(extracted["image"]))
                    _merge_unique(blocks, _vision_blocks(await transcribe_image(extracted["image"], media_type)))
            log_event(
                logging.DEBUG,
                "parser.pdf_page_complete",
                filename=filename,
                page=index + 1,
                paragraphs=len(blocks),
                native_chars=native_length,
                images=len(image_refs),
                sources={source.value: sum(1 for block in blocks if block.sourceType == source) for source in SourceType},
            )
            pages.append(DocumentPage(page=index + 1, paragraphs=blocks))
    finally:
        document.close()
    pages, full_text = _finalize_pages(pages)
    if not full_text:
        raise AppError("empty_document", "PDF 中没有识别到可供审查的内容。", 422)
    question_answers, evidence_blocks = reconstruct_document_structure(pages)
    parsed = ParsedDocument(
        name=filename,
        format="PDF",
        pageCount=len(pages),
        pages=pages,
        text=full_text,
        sizeLabel=f"{len(content) / 1024 / 1024:.2f} MB",
        questionAnswers=question_answers,
        evidenceBlocks=evidence_blocks,
    )
    log_event(logging.INFO, "parser.pdf_complete", filename=filename, pages=parsed.pageCount, paragraphs=sum(len(page.paragraphs) for page in pages), chars=len(parsed.text))
    log_payload("document.parsed_text", parsed.text, filename=filename, format=parsed.format)
    return parsed


async def parse_document(filename: str, content: bytes) -> ParsedDocument:
    """文档解析统一入口 — 按扩展名分派到对应解析器。

    Args:
        filename: 原文件名（用于判断格式和展示名称，不依赖 MIME type）。
        content: 文件完整二进制内容。

    Returns:
        统一结构的 ParsedDocument。

    Raises:
        AppError("file_too_large"): 超过 20 MB。
        AppError("unsupported_format"): 非 DOCX/PDF。
        AppError("parse_failed"): 加密/损坏。
        AppError("empty_document"): 无可用内容。
    """
    log_event(logging.INFO, "parser.started", filename=filename, bytes=len(content), extension=Path(filename).suffix.lower())
    if not content:
        raise AppError("empty_document", "文件为空，请重新选择。", 422)
    if len(content) > MAX_FILE_SIZE:
        raise AppError("file_too_large", "文件超过 20 MB 限制。", 413)
    extension = Path(filename).suffix.lower()
    if extension == ".docx":
        return await _parse_docx(filename, content)
    if extension == ".pdf":
        return await _parse_pdf(filename, content)
    if extension == ".doc":
        raise AppError("unsupported_legacy_word", "暂不支持旧版 DOC，请先转换为 DOCX 后上传。", 415)
    raise AppError("unsupported_format", "仅支持 PDF 和 DOCX 文件。", 415)
