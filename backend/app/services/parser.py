import logging
from pathlib import Path
import re
from hashlib import sha256

import fitz
from app.config import MAX_FILE_SIZE
from app.development_logging import log_event, log_payload
from app.errors import AppError
from app.models import DocumentPage, DocumentParagraph, ParsedDocument, SourceType
from app.services.openxml import read_docx_parts
from app.services.question_answer import reconstruct_question_answers
from app.services.vision import transcribe_image


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
    return " ".join(text.split())


def _join_question_lines(lines: list[str]) -> str:
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
    confidence = float(payload["confidence"])
    return [
        DocumentParagraph(text=_normalize(text), sourceType=SourceType.VISION, confidence=confidence)
        for text in payload["paragraphs"]
        if _normalize(text)
    ]


def _merge_unique(blocks: list[DocumentParagraph], additions: list[DocumentParagraph]) -> None:
    existing = {_normalize(block.text) for block in blocks}
    for block in additions:
        normalized = _normalize(block.text)
        if normalized and normalized not in existing:
            blocks.append(block)
            existing.add(normalized)


def _paginate(blocks: list[DocumentParagraph], target_chars: int = 1800) -> list[DocumentPage]:
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


def _finalize_pages(pages: list[DocumentPage], content: bytes) -> tuple[list[DocumentPage], str]:
    document_digest = sha256(content).hexdigest()
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
    try:
        package = read_docx_parts(content)
        blocks = [
            DocumentParagraph(text=_normalize(block.text), sourceType=block.source_type)
            for block in package.blocks
            if _normalize(block.text)
        ]
    except Exception as exc:
        raise AppError("parse_failed", "DOCX 文件无法解析，请确认文件未损坏。", 422) from exc
    for image_part in package.images:
        image = image_part.content
        media_type = image_part.media_type
        log_event(logging.DEBUG, "parser.docx_image", filename=filename, media_type=media_type, bytes=len(image))
        blocks.extend(_vision_blocks(await transcribe_image(image, media_type)))
    if not blocks:
        raise AppError("empty_document", "文档中没有可供审查的文字或图片内容。", 422)
    pages, full_text = _finalize_pages(_paginate(blocks), content)
    parsed = ParsedDocument(
        name=filename,
        format="DOCX",
        pageCount=len(pages),
        pages=pages,
        text=full_text,
        sizeLabel=f"{len(content) / 1024 / 1024:.2f} MB",
        warnings=package.warnings,
        questionAnswers=reconstruct_question_answers(pages),
    )
    log_event(logging.INFO, "parser.docx_complete", filename=filename, pages=parsed.pageCount, paragraphs=len(blocks), images=len(package.images), warnings=len(package.warnings), chars=len(parsed.text))
    log_payload("document.parsed_text", parsed.text, filename=filename, format=parsed.format)
    return parsed


async def _parse_pdf(filename: str, content: bytes) -> ParsedDocument:
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
    pages, full_text = _finalize_pages(pages, content)
    if not full_text:
        raise AppError("empty_document", "PDF 中没有识别到可供审查的内容。", 422)
    parsed = ParsedDocument(
        name=filename,
        format="PDF",
        pageCount=len(pages),
        pages=pages,
        text=full_text,
        sizeLabel=f"{len(content) / 1024 / 1024:.2f} MB",
        questionAnswers=reconstruct_question_answers(pages),
    )
    log_event(logging.INFO, "parser.pdf_complete", filename=filename, pages=parsed.pageCount, paragraphs=sum(len(page.paragraphs) for page in pages), chars=len(parsed.text))
    log_payload("document.parsed_text", parsed.text, filename=filename, format=parsed.format)
    return parsed


async def parse_document(filename: str, content: bytes) -> ParsedDocument:
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
