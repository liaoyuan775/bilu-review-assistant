r"""
被害人信息提取 — 基于结构化文档边界和正则表达式的笔录解析。

设计说明：
- 纯正则匹配，无模型依赖，执行速度快，适合实时提取。
- 两种匹配策略：
  1. 单行匹配（_match）: 适用于 "姓名：XXX" 等连续格式。
  2. 跨行表格匹配（_extract_label_value）: 适用于 PDF/DOCX 表格
     中 label 与 value 跨行分布的场景。
- 支持表格分隔符（|）清洗。

字段覆盖：
  姓名、性别、年龄、出生日期、民族、身份证号、职业、文化程度、
  工作单位、现住址、户籍所在地、联系电话、是否人大代表。
全部字段可为空（提取失败时返回 None）。

注意：
- 年龄提取使用了负向零宽断言 (?<!\d) 避免匹配其他数字。
- 民族字段有去重逻辑（排除将"民族"本身作为值）。

依赖关系：
- core/models.py: VictimProfile 模型。
"""

import re

from app.core.models import ParsedDocument, SourceType, VictimProfile

# 常用字段标签列表 — 用于 all match 终止判断 + 行内截断
_LABELS = [
    "姓名", "性别", "年龄", "民族", "出生日期", "职业", "文化程度", "学历",
    "身份证号码", "身份证号", "联系电话", "联系方式", "手机号", "手机号码",
    "工作单位", "户籍所在地", "户籍地址", "现住址", "住址", "电子邮箱", "是否人大代表",
    "询问人", "记录人", "被询问人", "权利义务",
]
_LABEL_OR = "|".join(_LABELS)


def _clean_value(value: str) -> str | None:
    """清洗原始值：去掉首尾的表格竖线(|)分隔符，空值返回 None。"""
    cleaned = re.sub(r"^\s*\|\s*|\s*\|\s*$", "", value).strip()
    return cleaned or None


def _match(text: str, pattern: str) -> str | None:
    """单行正则匹配，结果经 _clean_value 清洗。"""
    result = re.search(pattern, text)
    return _clean_value(result.group(1)) if result else None


def _extract_label_value(text: str, label: str) -> str | None:
    """跨行匹配：从文本中找到 label 所在行，取后续内容直到遇到下一个标签或末尾。

    适配场景：PDF 表格中 label 与 value 分处两行的情况。
    例如：
      姓名
      张三
      年龄
      35

    Args:
        text:  全文文本。
        label: 要查找的字段标签（如"姓名"）。

    Returns:
        提取到的值，未找到时返回 None。
    """
    lines = text.splitlines()
    next_label_re = re.compile(rf"^(?:{_LABEL_OR})\s*[：:]?\s*")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(rf"^{re.escape(label)}\s*[：:]?\s*$", stripped):
            # label 单独占一行，取下几行直到下一个标签
            parts = []
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                if next_label_re.match(next_line):
                    break
                parts.append(next_line)
            if parts:
                return _clean_value("".join(parts))
        elif re.match(rf"^{re.escape(label)}\s*[：:]\s*", stripped):
            # label: value 在同一行 → 截断到下一个标签
            value_part = re.sub(rf"^{re.escape(label)}\s*[：:]\s*", "", stripped)
            value_part = re.split(rf"(?:{_LABEL_OR})\s*[：:]\s*", value_part, maxsplit=1)[0]
            if value_part:
                return _clean_value(value_part)
    return None


def _better_of(a: str | None, b: str | None) -> str | None:
    """取两者中较长的一个，都为空则返回 None。"""
    if a and b:
        return a if len(a) >= len(b) else b
    return a or b


def _body_profile_text(document: ParsedDocument) -> str:
    paragraphs: list[str] = []
    reached_question = False
    for page in document.pages:
        for paragraph in page.paragraphs:
            if paragraph.sourceType not in {SourceType.NATIVE_TEXT, SourceType.TABLE}:
                continue
            if re.search(r"(?:^|\s)问\s*[：:]", paragraph.text):
                reached_question = True
                break
            paragraphs.append(paragraph.text)
        if reached_question:
            break
    text = "\n".join(paragraphs)
    victim_start = re.search(r"被询问人\s*[（(]?[^\n]*", text)
    if victim_start:
        text = text[victim_start.start():]
    return text


def _basic_information_text(document: ParsedDocument) -> str:
    return "\n".join(
        block.answer
        for block in document.questionAnswers
        if "基本情况" in block.question or "个人情况" in block.question
    )


def _npc_representative(text: str) -> bool | None:
    value = _match(text, r"是否人大代表(?:是|为|：|:)?(?:\s*\|\s*)?\s*(是|否)")
    if value == "是":
        return True
    if value == "否":
        return False
    return None


def _extract_fields(text: str) -> dict[str, str | int | bool | None]:
    """从已限定来源的文本中提取显式字段。"""
    table_separator = r"(?:\s*\|\s*)?"
    ws = r"\s*"

    # ── 姓名 ──
    name = _match(text, rf"(?:我叫|被询问人(?:是|为|：|:)?{table_separator}{ws}|姓名(?:是|为|：|:)?{table_separator}{ws})([\u4e00-\u9fff·]{{1,20}})")

    # ── 性别 ──
    gender = _match(
        text,
        rf"(?:性别(?:是|为|：|:)?{table_separator}{ws}|(?:^|[，,；;。\s|]))([男女])(?:[，,；;。\s|]|$)",
    )

    # ── 年龄（使用负向零宽断言避免匹配身份证号中的数字）──
    age_text = _match(text, r"(?<!\d)(\d{1,3})\s*岁")

    birth_date = _match(
        text,
        rf"出生日期(?:是|为|：|:)?{table_separator}{ws}(\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
    )

    # ── 民族 ──
    ethnicity = _match(text, rf"民族(?:是|为|：|:)?{table_separator}{ws}([\u4e00-\u9fff]{{1,8}}族)")
    if ethnicity is None:
        ethnicity = _match(
            text,
            r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{1,8}族)(?:[，,；;。\s|]|$)",
        )
    if ethnicity == "民族":
        ethnicity = None

    # ── 身份证号 ──
    id_number = _match(
        text,
        rf"身份证(?:号码|号)?(?:是|为|：|:)?{table_separator}{ws}([0-9Xx*]{{6,18}})",
    )

    occupation = _match(
        text,
        rf"职业(?:是|为|：|:)?{table_separator}{ws}([^|，,。；;\n]+)",
    )
    education = _match(
        text,
        rf"(?:文化程度|学历)(?:是|为|：|:)?{table_separator}{ws}([^|，,。；;\n]+)",
    )

    # ── 工作单位 ──
    employer = _better_of(
        _match(text, rf"工作单位(?:是|为|：|:)?{table_separator}{ws}([^|，,。；;\n]+)"),
        _extract_label_value(text, "工作单位"),
    )

    # ── 住址 ──
    address = _better_of(
        _match(text, rf"(?:现住址|住址)(?:是|为|：|:)?{table_separator}{ws}([^|，,。；;\n]+)"),
        _extract_label_value(text, "现住址") or _extract_label_value(text, "住址"),
    )
    registered_address = _better_of(
        _match(text, rf"(?:户籍所在地|户籍地址)(?:是|为|：|:)?{table_separator}{ws}([^|，,。；;\n]+)"),
        _extract_label_value(text, "户籍所在地") or _extract_label_value(text, "户籍地址"),
    )

    # ── 联系电话 ──
    contact = _match(
        text,
        rf"(?:联系电话|联系方式|手机号|手机号码)(?:是|为|：|:)?{table_separator}{ws}([0-9*+\-]{{7,20}})",
    )

    # ── Fallback：跨行表格格式（PDF 表格换行提取）──
    if name is None:
        name = _extract_label_value(text, "姓名")
    if ethnicity is None:
        ethnicity = _extract_label_value(text, "民族")
    if id_number is None:
        id_number = _extract_label_value(text, "身份证号码") or _extract_label_value(text, "身份证号")
    if employer is None:
        employer = _extract_label_value(text, "工作单位")
    if address is None:
        address = _extract_label_value(text, "现住址") or _extract_label_value(text, "住址")
    if contact is None:
        contact = _extract_label_value(text, "联系电话") or _extract_label_value(text, "联系方式") or _extract_label_value(text, "手机号")
    if birth_date is None:
        birth_date = _extract_label_value(text, "出生日期")
    if occupation is None:
        occupation = _extract_label_value(text, "职业")
    if education is None:
        education = _extract_label_value(text, "文化程度") or _extract_label_value(text, "学历")
    if registered_address is None:
        registered_address = _extract_label_value(text, "户籍所在地") or _extract_label_value(text, "户籍地址")

    return {
        "name": name,
        "gender": gender,
        "age": int(age_text) if age_text else None,
        "birthDate": birth_date,
        "ethnicity": ethnicity,
        "idNumber": id_number,
        "occupation": occupation,
        "education": education,
        "employer": employer,
        "address": address,
        "registeredAddress": registered_address,
        "contact": contact,
        "isNpcRepresentative": _npc_representative(text),
    }


def extract_victim_profile(document: ParsedDocument) -> VictimProfile | None:
    """从页首被询问人信息区提取，并由明确的基本情况问答补空。"""
    values = _extract_fields(_body_profile_text(document))
    fallback_text = _basic_information_text(document)
    if fallback_text:
        fallback = _extract_fields(fallback_text)
        if fallback["occupation"] is None:
            fallback["occupation"] = _match(
                fallback_text,
                r"有限公司([\u4e00-\u9fff]{2,12}(?:人员|职员|员工|工程师))",
            )
        for field, value in fallback.items():
            if values[field] is None and value is not None:
                values[field] = value

    if not any(values.values()):
        return None
    return VictimProfile(**values)
