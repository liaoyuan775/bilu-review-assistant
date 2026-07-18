"""
标签与格式化工具 — 将枚举值/状态码转换为人类可读的中文标签。

职责边界：
- 纯展示层工具，不包含任何业务逻辑。
- 所有函数都是纯函数，输入枚举值 → 输出中文字符串。
- 不依赖任何业务模块（零依赖，除 Python 标准库）。

用途：
- 报告生成（PDF / DOCX）中需要显示中文标签的地方。
- 前端可能也会用后端返回的原始值自行翻译。

函数列表：
- mode_label():              审查模式标签
- review_status_label():     审查状态标签
- severity_label():          风险等级标签
- manual_status_label():     人工处置状态标签
- event_type_label():        事件类型标签
- format_datetime():         ISO 时间格式化
"""

from datetime import datetime


_MODE = {"qwen": "Qwen 模型", "mock": "快速模拟", "local": "历史本地模式"}
_REVIEW = {"in_review": "复核中", "archived": "已归档"}
_SEVERITY = {"high": "高", "medium": "中", "low": "低"}
_MANUAL = {
    "pending": "待处置",
    "confirmed": "已确认问题",
    "supplemented": "已加入补问",
    "ignored": "已忽略",
    "resolved": "已解决",
    "not_applicable": "确认不适用",
}
_EVENT = {
    **_MANUAL,
    "follow_up_answer": "记录补问答案",
    "warnings_acknowledged": "确认解析告警",
    "domain_retried": "重试业务域",
    "artifacts_generated": "生成归档产物",
    "archived": "完成归档",
}


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def mode_label(value) -> str:
    raw = _value(value)
    return _MODE.get(raw, raw)


def review_status_label(value) -> str:
    raw = _value(value)
    return _REVIEW.get(raw, raw)


def severity_label(value) -> str:
    raw = _value(value)
    return _SEVERITY.get(raw, raw)


def manual_status_label(value) -> str:
    raw = _value(value)
    return _MANUAL.get(raw, raw)


def event_type_label(value) -> str:
    raw = _value(value)
    return _EVENT.get(raw, raw)


def format_datetime(value: str) -> str:
    """将 ISO 格式时间转为可读格式（如 "2026-07-18 14:30"）。"""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
