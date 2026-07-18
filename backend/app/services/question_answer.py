from dataclasses import dataclass, field
from hashlib import sha256
import re

from app.models import DocumentPage, QuestionAnswerBlock


_MARKER = re.compile(r"([问答])\s*[:：]")
_GUIDANCE = re.compile(r"（([^（）]*)）|\(([^()]*)\)")
_UNCLEAR_PHRASES = ("不知道", "不清楚", "不详", "记不清", "不记得", "无法确定")


@dataclass
class _OpenQuestion:
    question_parts: list[str] = field(default_factory=list)
    answer_parts: list[str] = field(default_factory=list)
    anchor_ids: list[str] = field(default_factory=list)
    answer_started: bool = False

    def add_anchor(self, block_id: str) -> None:
        if block_id and block_id not in self.anchor_ids:
            self.anchor_ids.append(block_id)


def _join_parts(parts: list[str]) -> str:
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def _without_guidance(text: str) -> tuple[str, list[str]]:
    guidance: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = (match.group(1) or match.group(2) or "").strip()
        if value:
            guidance.append(value)
        return ""

    cleaned = _GUIDANCE.sub(replace, text)
    return " ".join(cleaned.split()), guidance


def _finish(current: _OpenQuestion | None) -> QuestionAnswerBlock | None:
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
    identity = "\0".join([question, *current.anchor_ids])
    return QuestionAnswerBlock(
        id=sha256(identity.encode("utf-8")).hexdigest()[:24],
        question=question,
        answer=answer,
        guidance=[*question_guidance, *answer_guidance],
        anchorIds=current.anchor_ids,
        answerClarity=clarity,
    )


def reconstruct_question_answers(pages: list[DocumentPage]) -> list[QuestionAnswerBlock]:
    blocks: list[QuestionAnswerBlock] = []
    current: _OpenQuestion | None = None

    for page in pages:
        for paragraph in page.paragraphs:
            text = paragraph.text.strip()
            matches = list(_MARKER.finditer(text))
            if not matches:
                if current is not None and current.answer_started and text:
                    current.answer_parts.append(text)
                    current.add_anchor(paragraph.id)
                continue

            prefix = text[:matches[0].start()].strip()
            if current is not None and current.answer_started and prefix:
                current.answer_parts.append(prefix)
                current.add_anchor(paragraph.id)

            for index, match in enumerate(matches):
                value_start = match.end()
                value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                value = text[value_start:value_end].strip()
                if match.group(1) == "问":
                    finished = _finish(current)
                    if finished is not None:
                        blocks.append(finished)
                    current = _OpenQuestion(question_parts=[value] if value else [])
                    current.add_anchor(paragraph.id)
                elif current is not None:
                    current.answer_started = True
                    if value:
                        current.answer_parts.append(value)
                    current.add_anchor(paragraph.id)

    finished = _finish(current)
    if finished is not None:
        blocks.append(finished)
    return blocks
