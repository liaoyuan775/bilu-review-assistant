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

from app.core.models import DocumentPage, QuestionAnswerBlock


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


def _finish(current: _OpenQuestion | None) -> QuestionAnswerBlock | None:
    """完成一个问答对的构建，返回 QuestionAnswerBlock 或 None（无效）。"""
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
    blocks: list[QuestionAnswerBlock] = []
    current: _OpenQuestion | None = None

    for page in pages:
        for paragraph in page.paragraphs:
            text = paragraph.text.strip()
            matches = list(_MARKER.finditer(text))
            if not matches:
                # 非问答标记行：若正在收集答案则追加
                if current is not None and current.answer_started and text:
                    current.answer_parts.append(text)
                    current.add_anchor(paragraph.id)
                continue

            # 处理问答标记前的文本前缀
            prefix = text[:matches[0].start()].strip()
            if current is not None and current.answer_started and prefix:
                current.answer_parts.append(prefix)
                current.add_anchor(paragraph.id)

            # 逐个处理本段中的问答标记
            for index, match in enumerate(matches):
                value_start = match.end()
                value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                value = text[value_start:value_end].strip()
                if match.group(1) == "问":
                    # 新问题：结束当前问答，开启下一个
                    finished = _finish(current)
                    if finished is not None:
                        blocks.append(finished)
                    current = _OpenQuestion(question_parts=[value] if value else [])
                    current.add_anchor(paragraph.id)
                elif current is not None:
                    # "答："标记
                    current.answer_started = True
                    if value:
                        current.answer_parts.append(value)
                    current.add_anchor(paragraph.id)

    finished = _finish(current)
    if finished is not None:
        blocks.append(finished)
    return blocks
