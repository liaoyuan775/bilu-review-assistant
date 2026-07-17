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
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
