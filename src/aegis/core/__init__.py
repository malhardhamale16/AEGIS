"""Core services: config, logging, event bus, LLM client, skill registry, permission gate."""

from aegis.core.config import ConfigError, load_config
from aegis.core.events import Event, EventBus
from aegis.core.llm import (
    LLMClient,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
    ModelNotFoundError,
    OllamaClient,
)
from aegis.core.logging import get_logger, setup_logging
from aegis.core.permission import PermissionGate
from aegis.core.registry import (
    RegistryError,
    SkillBlockedError,
    SkillDisabledError,
    SkillRegistry,
    UnknownSkillError,
)

__all__ = [
    "ConfigError",
    "Event",
    "EventBus",
    "LLMClient",
    "LLMError",
    "LLMResponseError",
    "LLMUnavailableError",
    "ModelNotFoundError",
    "OllamaClient",
    "PermissionGate",
    "RegistryError",
    "SkillBlockedError",
    "SkillDisabledError",
    "SkillRegistry",
    "UnknownSkillError",
    "get_logger",
    "load_config",
    "setup_logging",
]
