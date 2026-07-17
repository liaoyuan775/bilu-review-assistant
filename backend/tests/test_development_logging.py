import logging
from contextlib import contextmanager

from app import development_logging


@contextmanager
def capture_bilu(caplog):
    logger = development_logging.get_logger()
    logger.addHandler(caplog.handler)
    try:
        yield
    finally:
        logger.removeHandler(caplog.handler)


def test_payload_logging_defaults_to_metadata_only(monkeypatch, caplog):
    monkeypatch.delenv("BILU_LOG_PAYLOADS", raising=False)
    sensitive = "身份证号码430123199001011234，联系电话13812345678。" + "完整正文" * 100

    with capture_bilu(caplog), caplog.at_level(logging.DEBUG, logger="bilu"):
        development_logging.log_payload("test.payload", sensitive)

    message = caplog.records[-1].getMessage()
    assert "chars=" in message
    assert "sha256=" in message
    assert "430123199001011234" not in message
    assert "13812345678" not in message
    assert "完整正文" not in message
    assert "preview=" not in message
    assert sensitive not in message


def test_payload_logging_can_be_explicitly_enabled(monkeypatch, caplog):
    monkeypatch.setenv("BILU_LOG_PAYLOADS", "true")
    payload = '{"ruleId":"PRESENT-001","status":"covered"}'

    with capture_bilu(caplog), caplog.at_level(logging.DEBUG, logger="bilu"):
        development_logging.log_payload("test.payload", payload)

    assert payload in caplog.records[-1].getMessage()


def test_task_context_is_added_to_log_events(caplog):
    token = development_logging.set_task_id("task-123")
    try:
        with capture_bilu(caplog), caplog.at_level(logging.INFO, logger="bilu"):
            development_logging.log_event(logging.INFO, "review.started", filename="demo.docx")
    finally:
        development_logging.reset_task_id(token)

    message = caplog.records[-1].getMessage()
    assert "event=review.started" in message
    assert "task_id=task-123" in message
    assert "filename=demo.docx" in message
