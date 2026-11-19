"""YAML config loader with pydantic validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from aegis.models.config import AegisConfig, ModelsConfig, Settings, SkillsConfig, VoiceConfig

CONFIG_DIR_ENV = "AEGIS_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path("configs")

# section name on Settings -> (file name, schema)
_FILES: dict[str, tuple[str, type[BaseModel]]] = {
    "aegis": ("aegis.yaml", AegisConfig),
    "models": ("models.yaml", ModelsConfig),
    "skills": ("skills.yaml", SkillsConfig),
    "voice": ("voice.yaml", VoiceConfig),
}


class ConfigError(Exception):
    """Raised when a config file is missing, unreadable, or invalid."""


def resolve_config_dir(config_dir: str | Path | None = None) -> Path:
    """Explicit argument > ``AEGIS_CONFIG_DIR`` env var > ``./configs``."""
    if config_dir is not None:
        return Path(config_dir)
    env = os.environ.get(CONFIG_DIR_ENV)
    return Path(env) if env else DEFAULT_CONFIG_DIR


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid config in {path}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_config(config_dir: str | Path | None = None) -> Settings:
    """Load and validate every YAML file in the config directory."""
    base = resolve_config_dir(config_dir)
    sections: dict[str, BaseModel] = {}
    for section, (filename, schema) in _FILES.items():
        path = base / filename
        raw = _read_yaml(path)
        try:
            sections[section] = schema.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(path, exc)) from exc
    return Settings(**sections)
