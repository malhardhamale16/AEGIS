"""Contracts for LLM interaction."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    model: str
    content: str
    done: bool = True


class HealthStatus(BaseModel):
    ok: bool
    latency_ms: float | None = None
    version: str | None = None
    error: str | None = None


# Ollama's ``format`` field: the string "json" or a JSON schema object.
ResponseFormat = str | dict[str, Any]
