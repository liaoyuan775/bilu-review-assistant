"""Strict JSON Schema capability checks for the configured Qwen model."""

import asyncio
import json

import httpx
import pytest

from app.llm import qwen


def _configure_qwen(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str = "http://qwen.test/v1",
    api_key: str = "test-key",
    model: str = "test-model",
) -> None:
    monkeypatch.setattr(qwen, "QWEN_BASE_URL", base_url)
    monkeypatch.setattr(qwen, "QWEN_API_KEY", api_key)
    monkeypatch.setattr(qwen, "QWEN_MODEL", model)


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(qwen.httpx, "AsyncClient", factory)


@pytest.mark.parametrize(
    ("base_url", "api_key", "model"),
    [("", "test-key", "test-model"), ("http://qwen.test/v1", "", "test-model"), ("http://qwen.test/v1", "test-key", "")],
)
def test_health_rejects_incomplete_configuration(monkeypatch, base_url, api_key, model):
    _configure_qwen(monkeypatch, base_url, api_key, model)
    assert asyncio.run(qwen.check_qwen()) is False


def test_health_requires_strict_json_schema_enforcement(monkeypatch):
    _configure_qwen(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["enable_thinking"] is False
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert not {"tools", "tool_choice"} & payload.keys()
        content = json.dumps({"schemaProbe": "schema_enforced"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    _mock_transport(monkeypatch, handler)
    assert asyncio.run(qwen.check_qwen()) is True


def test_health_rejects_model_that_ignores_json_schema(monkeypatch):
    _configure_qwen(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        content = json.dumps({"schemaProbe": "followed_prompt_instead"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    _mock_transport(monkeypatch, handler)
    assert asyncio.run(qwen.check_qwen()) is False


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_health_rejects_schema_request_errors(monkeypatch, status):
    _configure_qwen(monkeypatch)
    _mock_transport(monkeypatch, lambda _request: httpx.Response(status, json={"error": {"message": "failed"}}))
    assert asyncio.run(qwen.check_qwen()) is False


def test_health_rejects_network_errors(monkeypatch):
    _configure_qwen(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_transport(monkeypatch, handler)
    assert asyncio.run(qwen.check_qwen()) is False
