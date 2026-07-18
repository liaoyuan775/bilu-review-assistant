"""
被害人信息提取 — 基于正则表达式的笔录文本解析。

设计说明：
- 纯正则匹配，无模型依赖，执行速度快，适合实时提取。
- 两种匹配策略：
  1. 单行匹配（_match）: 适用于 "姓名：XXX" 等连续格式。
  2. 跨行表格匹配（_extract_label_value）: 适用于 PDF/DOCX 表格
     中 label 与 value 跨行分布的场景。
- 支持表格分隔符（|）清洗。

字段覆盖：
  姓名、性别、年龄、民族、身份证号、工作单位、住址、联系电话。
全部字段可为空（提取失败时返回 None）。

注意：
- 年龄提取使用了负向零宽断言 (?<!\d) 避免匹配其他数字。
- 民族字段有去重逻辑（排除将"民族"本身作为值）。
"""

import re

from app.models import VictimProfile

# 常用字段标签列表 — 用于 all match 终止判断 + 行内截断
_LABELS = [
    "姓名", "性别", "年龄", "民族", "出生日期",
    "身份证号码", "身份证号", "联系电话", "联系方式", "手机号", "手机号码",
    "工作单位", "户籍地址", "现住址", "住址", "电子邮箱",
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


def extract_victim_profile(text: str) -> VictimProfile | None:
    """从笔录文本中提取被害人基础信息。

    优先使用单行正则匹配（_match），失败时降级到跨行表格匹配（_extract_label_value）。
    如果全部字段都未提取到，返回 None（UI 不展示被害人信息卡）。

    Args:
        text: 笔录全文文本（已标准化）。

    Returns:
        VictimProfile 实例（部分或全部字段可为 None），
        或 None（未提取到任何信息）。
    """
    table_separator = r"(?:\s*\|\s*)?"
    ws = r"\s*"

    # ── 姓名 ──
    name = _match(text, rf"(?:我叫|姓名(?:是|为|：|:)?{table_separator}{ws})([\u4e00-\u9fff·]{{1,20}})")

    # ── 性别 ──
    gender = _match(
        text,
        rf"(?:性别(?:是|为|：|:)?{table_separator}{ws}|(?:^|[，,；;。\s|]))([男女])(?:[，,；;。\s|]|$)",
    )

    # ── 年龄（使用负向零宽断言避免匹配身份证号中的数字）──
    age_text = _match(text, r"(?<!\d)(\d{1,3})\s*岁")

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

    values = (name, gender, age_text, ethnicity, id_number, employer, address, contact)
    if not any(values):
        return None
    return VictimProfile(
        name=name,
        gender=gender,
        age=int(age_text) if age_text else None,
        ethnicity=ethnicity,
        idNumber=id_number,
        employer=employer,
        address=address,
        contact=contact,
    )
