"""
问答对重建状态机 — 从已分段的段落中识别"问：/答："模式。

核心逻辑：
1. 遍历所有页面和段落，通过正则匹配"问：/答："标记。
2. 跨段、跨页组装完整问答对。
3. 将括号模板说明移入 guidance 字段，避免模型误当成案件事实。
4. 根据答案内容判断 clarity（clear / unclear / blank）。
"""

from dataclasses import dataclass, field
from hashlib import sha256
import re

from app.core.models import DocumentPage, DocumentParagraph, EvidenceBlock, QuestionAnswerBlock


# "问："或"答："前导标记（支持中文冒号和英文冒号）
_MARKER = re.compile(r"([问答])\s*[:：]")
# 括号模板说明（中英文括号） — 会被移入 guidance
_GUIDANCE = re.compile(r"（([^（）]*)）|\(([^()]*)\)")
# 常识性不清短语
_UNCLEAR_PHRASES = ("不知道", "不清楚", "不详", "记不清", "不记得", "无法确定")


@dataclass
class _OpenQuestion:
    """状态机内部状态 — 一个正在构建的问答对。"""
    question_parts: list[str] = field(default_factory=list)
    answer_parts: list[str] = field(default_factory=list)
    anchor_ids: list[str] = field(default_factory=list)
    answer_started: bool = False

    def add_anchor(self, block_id: str) -> None:
        if block_id and block_id not in self.anchor_ids:
            self.anchor_ids.append(block_id)


def _join_parts(parts: list[str]) -> str:
    """合并问答碎片为完整语句。"""
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def _without_guidance(text: str) -> tuple[str, list[str]]:
    """移除括号内的模板说明/填写示例，返回清理后的文本和 guidance 列表。"""
    guidance: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = (match.group(1) or match.group(2) or "").strip()
        if value:
            guidance.append(value)
        return ""

    cleaned = _GUIDANCE.sub(replace, text)
    return " ".join(cleaned.split()), guidance


def _finish(
    current: _OpenQuestion | None,
    locations: dict[str, tuple[int, int]],
) -> tuple[QuestionAnswerBlock, EvidenceBlock] | None:
    """完成一个问答对，同时返回兼容问答对象和统一证据块。"""
    if current is None:
        return None
    raw_question = _join_parts(current.question_parts)
    question, question_guidance = _without_guidance(raw_question)
    if not question:
        return None
    raw_answer = _join_parts(current.answer_parts)
    answer, answer_guidance = _without_guidance(raw_answer)
    if not answer:
        clarity = "blank"
    elif any(phrase in answer for phrase in _UNCLEAR_PHRASES):
        clarity = "unclear"
    else:
        clarity = "clear"
    text = f"问：{question}\n答：{answer}"
    identity = "\0".join(["qa", text, *current.anchor_ids])
    block_id = sha256(identity.encode("utf-8")).hexdigest()[:24]
    first_page, first_paragraph = locations[current.anchor_ids[0]]
    question_answer = QuestionAnswerBlock(
        id=block_id,
        question=question,
        answer=answer,
        guidance=[*question_guidance, *answer_guidance],
        anchorIds=current.anchor_ids,
        answerClarity=clarity,
    )
    evidence = EvidenceBlock(
        id=block_id,
        kind="qa",
        text=text,
        paragraphIds=current.anchor_ids,
        page=first_page,
        paragraph=first_paragraph,
    )
    return question_answer, evidence


def _text_block(paragraph: DocumentParagraph, page: int, index: int) -> EvidenceBlock:
    return EvidenceBlock(
        id=paragraph.id,
        kind="text",
        text=paragraph.text,
        paragraphIds=[paragraph.id],
        page=page,
        paragraph=index,
    )


def reconstruct_document_structure(
    pages: list[DocumentPage],
) -> tuple[list[QuestionAnswerBlock], list[EvidenceBlock]]:
    """从原始段落一次生成兼容问答对象和统一证据块。"""
    question_answers: list[QuestionAnswerBlock] = []
    evidence_blocks: list[EvidenceBlock] = []
    current: _OpenQuestion | None = None
    locations = {
        paragraph.id: (page.page, index)
        for page in pages
        for index, paragraph in enumerate(page.paragraphs, start=1)
    }

    def finish_current() -> None:
        nonlocal current
        finished = _finish(current, locations)
        if finished is not None:
            question_answer, evidence = finished
            question_answers.append(question_answer)
            evidence_blocks.append(evidence)
        current = None

    for page in pages:
        for paragraph_index, paragraph in enumerate(page.paragraphs, start=1):
            text = paragraph.text.strip()
            matches = list(_MARKER.finditer(text))
            if not matches:
                if current is None:
                    if text:
                        evidence_blocks.append(_text_block(paragraph, page.page, paragraph_index))
                elif text:
                    target = current.answer_parts if current.answer_started else current.question_parts
                    target.append(text)
                    current.add_anchor(paragraph.id)
                continue

            prefix = text[:matches[0].start()].strip()
            if current is not None and prefix:
                target = current.answer_parts if current.answer_started else current.question_parts
                target.append(prefix)
                current.add_anchor(paragraph.id)
            elif prefix:
                evidence_blocks.append(EvidenceBlock(
                    id=sha256(f"text\0{prefix}\0{paragraph.id}".encode("utf-8")).hexdigest()[:24],
                    kind="text",
                    text=prefix,
                    paragraphIds=[paragraph.id],
                    page=page.page,
                    paragraph=paragraph_index,
                ))

            for index, match in enumerate(matches):
                value_start = match.end()
                value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                value = text[value_start:value_end].strip()
                if match.group(1) == "问":
                    finish_current()
                    current = _OpenQuestion(question_parts=[value] if value else [])
                    current.add_anchor(paragraph.id)
                elif current is not None:
                    current.answer_started = True
                    if value:
                        current.answer_parts.append(value)
                    current.add_anchor(paragraph.id)

    finish_current()
    return question_answers, evidence_blocks


def reconstruct_question_answers(pages: list[DocumentPage]) -> list[QuestionAnswerBlock]:
    """从已解析的页面段落中重建问答对。

    状态机算法：
    - 遇到"问：" → 结束上一个问答（若有），开启新问题
    - 遇到"答：" → 标记当前问答开始进入答案收集阶段
    - 非标记行 → 追加到当前正在收集的部分（问题或答案）
    - 遇到段落结束标记（如"询问结束"）→ 终止收集

    Args:
        pages: 已分页的文档段落列表。

    Returns:
        重建的问答对列表。
    """
    question_answers, _ = reconstruct_document_structure(pages)
    return question_answers


def reconstruct_evidence_blocks(pages: list[DocumentPage]) -> list[EvidenceBlock]:
    """构建按原文顺序排列的 text/qa 统一证据块。"""
    _, evidence_blocks = reconstruct_document_structure(pages)
    return evidence_blocks
