"""Ollama client (localhost only) and the LLM protocol agents depend on."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from typing import Any, Protocol

import httpx

from aegis.core.logging import get_logger
from aegis.models.config import GenerationConfig, OllamaConfig
from aegis.models.llm import ChatMessage, ChatResponse, HealthStatus, ResponseFormat

log = get_logger("llm")


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMUnavailableError(LLMError):
    """Ollama could not be reached or timed out."""


class LLMResponseError(LLMError):
    """Ollama answered with an error or an unparseable body."""


class ModelNotFoundError(LLMResponseError):
    """The requested model is not pulled locally."""


class LLMClient(Protocol):
    """What agents need from an LLM. Tests provide a fake implementation."""

    def chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        format: ResponseFormat | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse: ...


class OllamaClient:
    def __init__(
        self,
        config: OllamaConfig,
        generation: GenerationConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._generation = generation or GenerationConfig()
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            transport=transport,
        )

    # ------------------------------------------------------------------- lifecycle

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------------- health

    def health(self) -> HealthStatus:
        """Never raises: returns ``ok=False`` with an error message instead."""
        start = time.perf_counter()
        try:
            resp = self._http.get("/api/version", timeout=self._config.health_timeout_seconds)
            resp.raise_for_status()
            version = resp.json().get("version")
        except httpx.TimeoutException:
            return HealthStatus(ok=False, error="timed out")
        except httpx.HTTPStatusError as exc:
            return HealthStatus(ok=False, error=f"HTTP {exc.response.status_code}")
        except httpx.TransportError as exc:
            return HealthStatus(ok=False, error=f"unreachable: {exc}")
        except ValueError:
            return HealthStatus(ok=False, error="invalid JSON from /api/version")
        latency = (time.perf_counter() - start) * 1000
        return HealthStatus(ok=True, latency_ms=round(latency, 1), version=version)

    def list_models(self) -> list[str]:
        data = self._request_json("GET", "/api/tags")
        return sorted(m["name"] for m in data.get("models", []) if "name" in m)

    # ------------------------------------------------------------------------ chat

    def _chat_payload(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        stream: bool,
        format: ResponseFormat | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": stream,
            "options": {
                "temperature": (
                    self._generation.temperature if temperature is None else temperature
                ),
                "num_predict": self._generation.max_tokens if max_tokens is None else max_tokens,
            },
        }
        if format is not None:
            payload["format"] = format
        return payload

    def chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        format: ResponseFormat | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        payload = self._chat_payload(
            messages,
            model,
            stream=False,
            format=format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        data = self._request_json("POST", "/api/chat", json=payload)
        try:
            return ChatResponse(
                model=data.get("model", model),
                content=data["message"]["content"],
                done=bool(data.get("done", True)),
            )
        except (KeyError, TypeError) as exc:
            raise LLMResponseError(f"Unexpected /api/chat response: {data!r}") from exc

    def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        format: ResponseFormat | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Yield content chunks as Ollama produces them (NDJSON stream)."""
        payload = self._chat_payload(
            messages,
            model,
            stream=True,
            format=format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            with self._http.stream("POST", "/api/chat", json=payload) as resp:
                if resp.is_error:
                    resp.read()
                    self._raise_for_error(resp)
                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMResponseError(f"Bad stream line: {line!r}") from exc
                    if "error" in chunk:
                        raise LLMResponseError(chunk["error"])
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        return
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("Ollama timed out") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"Ollama unreachable: {exc}") from exc

    # --------------------------------------------------------------------- helpers

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("Ollama timed out") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"Ollama unreachable: {exc}") from exc
        self._raise_for_error(resp)
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMResponseError(f"Invalid JSON from {path}") from exc
        if not isinstance(data, dict):
            raise LLMResponseError(f"Expected a JSON object from {path}")
        return data

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if not resp.is_error:
            return
        try:
            message = resp.json().get("error", resp.text)
        except ValueError:
            message = resp.text
        if resp.status_code == 404:
            raise ModelNotFoundError(message or "model not found")
        raise LLMResponseError(f"HTTP {resp.status_code}: {message}")
