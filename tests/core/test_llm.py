"""Ollama client tests against httpx.MockTransport. No real network is used."""

import json

import httpx
import pytest

from aegis.core.llm import (
    LLMResponseError,
    LLMUnavailableError,
    ModelNotFoundError,
    OllamaClient,
)
from aegis.models.config import GenerationConfig, OllamaConfig
from aegis.models.llm import ChatMessage

MSGS = [ChatMessage(role="user", content="hi")]


def client(handler, **cfg) -> OllamaClient:
    return OllamaClient(
        OllamaConfig(**cfg),
        GenerationConfig(temperature=0.1, max_tokens=50),
        transport=httpx.MockTransport(handler),
    )


def test_health_ok():
    def handler(req):
        assert req.url.path == "/api/version"
        return httpx.Response(200, json={"version": "0.9.0"})

    status = client(handler).health()
    assert status.ok and status.version == "0.9.0" and status.latency_ms is not None


def test_health_unreachable_does_not_raise():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    status = client(handler).health()
    assert not status.ok and "unreachable" in status.error


def test_health_timeout():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    assert client(handler).health().error == "timed out"


def test_health_http_error():
    assert client(lambda r: httpx.Response(500)).health().error == "HTTP 500"


def test_list_models():
    def handler(req):
        return httpx.Response(200, json={"models": [{"name": "b:1"}, {"name": "a:1"}]})

    assert client(handler).list_models() == ["a:1", "b:1"]


def test_chat_payload_and_response():
    captured = {}

    def handler(req):
        captured.update(json.loads(req.content))
        return httpx.Response(
            200,
            json={"model": "m", "message": {"role": "assistant", "content": "yo"}, "done": True},
        )

    resp = client(handler).chat(MSGS, "m", format="json")
    assert resp.content == "yo" and resp.model == "m"
    assert captured["stream"] is False
    assert captured["format"] == "json"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["options"] == {"temperature": 0.1, "num_predict": 50}


def test_chat_per_call_options_override_config():
    captured = {}

    def handler(req):
        captured.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": ""}})

    client(handler).chat(MSGS, "m", temperature=0.9, max_tokens=7)
    assert captured["options"] == {"temperature": 0.9, "num_predict": 7}
    assert "format" not in captured


def test_chat_model_not_found():
    def handler(req):
        return httpx.Response(404, json={"error": "model 'x' not found"})

    with pytest.raises(ModelNotFoundError, match="not found"):
        client(handler).chat(MSGS, "x")


def test_chat_server_error():
    with pytest.raises(LLMResponseError, match="HTTP 500"):
        client(lambda r: httpx.Response(500, text="oops")).chat(MSGS, "m")


def test_chat_malformed_body():
    with pytest.raises(LLMResponseError):
        client(lambda r: httpx.Response(200, json={"nope": 1})).chat(MSGS, "m")


def test_chat_invalid_json():
    with pytest.raises(LLMResponseError, match="Invalid JSON"):
        client(lambda r: httpx.Response(200, text="not json")).chat(MSGS, "m")


def test_chat_timeout_raises_unavailable():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(LLMUnavailableError, match="timed out"):
        client(handler).chat(MSGS, "m")


def test_chat_stream_yields_chunks():
    lines = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    body = "\n".join(json.dumps(x) for x in lines) + "\n"

    def handler(req):
        assert json.loads(req.content)["stream"] is True
        return httpx.Response(200, text=body)

    assert list(client(handler).chat_stream(MSGS, "m")) == ["Hel", "lo"]


def test_chat_stream_error_line():
    body = json.dumps({"error": "boom"}) + "\n"
    with pytest.raises(LLMResponseError, match="boom"):
        list(client(lambda r: httpx.Response(200, text=body)).chat_stream(MSGS, "m"))


def test_chat_stream_http_error():
    def handler(req):
        return httpx.Response(404, json={"error": "model 'x' not found"})

    with pytest.raises(ModelNotFoundError):
        list(client(handler).chat_stream(MSGS, "x"))


def test_chat_stream_unreachable():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(LLMUnavailableError):
        list(client(handler).chat_stream(MSGS, "m"))


def test_context_manager_closes():
    with client(lambda r: httpx.Response(200, json={})) as c:
        assert isinstance(c, OllamaClient)
