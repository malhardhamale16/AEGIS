"""Health checks behind ``aegis doctor``. No hardware is probed here."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from aegis.apps.runtime import build_registry
from aegis.core.registry import RegistryError
from aegis.models.config import Settings
from aegis.models.llm import HealthStatus


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


class OllamaAdmin(Protocol):
    def health(self) -> HealthStatus: ...
    def list_models(self) -> list[str]: ...


def check_python() -> Check:
    v = sys.version_info
    ok = v >= (3, 11)
    return Check("python", Status.OK if ok else Status.FAIL, f"{v.major}.{v.minor}.{v.micro}")


def check_safety(settings: Settings) -> Check:
    s = settings.aegis.safety
    if s.dry_run:
        return Check("safety", Status.OK, "dry-run on (state changes are only simulated)")
    if not s.require_confirmation:
        return Check("safety", Status.WARN, "dry-run OFF and confirmation OFF")
    return Check("safety", Status.WARN, "dry-run OFF (confirm-level skills ask before acting)")


def check_ollama(settings: Settings, client: OllamaAdmin) -> list[Check]:
    url = settings.models.ollama.base_url
    health = client.health()
    if not health.ok:
        checks = [
            Check("ollama", Status.FAIL, f"{url}: {health.error} (is `ollama serve` running?)")
        ]
        return checks + [
            Check(f"model:{role}", Status.FAIL, f"{model} (not checked: Ollama unreachable)")
            for role, model in settings.models.roles.model_dump().items()
        ]
    checks = [Check("ollama", Status.OK, f"{url} v{health.version} ({health.latency_ms} ms)")]
    try:
        installed = set(client.list_models())
    except Exception as exc:  # report, never crash the doctor
        return [*checks, Check("models", Status.FAIL, f"could not list models: {exc}")]
    for role, model in settings.models.roles.model_dump().items():
        if model in installed:
            checks.append(Check(f"model:{role}", Status.OK, model))
        else:
            checks.append(
                Check(f"model:{role}", Status.FAIL, f"{model} not pulled (`ollama pull {model}`)")
            )
    return checks


def check_skills(settings: Settings) -> Check:
    try:
        registry = build_registry(settings)
    except RegistryError as exc:
        return Check("skills", Status.FAIL, str(exc))
    infos = registry.describe()
    by_risk: dict[str, int] = {}
    for info in infos:
        by_risk[info.risk.value] = by_risk.get(info.risk.value, 0) + 1
    summary = ", ".join(f"{n} {risk}" for risk, n in sorted(by_risk.items()))
    return Check("skills", Status.OK, f"{len(infos)} enabled ({summary or 'none'})")


def check_write_roots(settings: Settings) -> Check:
    roots = [Path(r).expanduser() for r in settings.skills.write_file.allowed_roots]
    if not roots:
        return Check("write_file", Status.WARN, "no allowed_roots: write_file will refuse all")
    missing = [str(r) for r in roots if not r.is_dir()]
    if missing:
        return Check("write_file", Status.WARN, f"created on first write: {', '.join(missing)}")
    return Check("write_file", Status.OK, ", ".join(str(r) for r in roots))


def check_voice(settings: Settings) -> Check:
    a = settings.voice.audio
    return Check(
        "voice",
        Status.OK,
        f"input device {a.input_device} via {a.host_api}, {a.sample_rate} Hz, {a.frame_ms} ms "
        "frames (config only; probe with scripts/diagnose_audio.py)",
    )


VOICE_PACKAGES = {
    "sounddevice": "microphone/speaker",
    "webrtcvad": "voice activity detection",
    "faster_whisper": "speech-to-text",
    "kokoro": "text-to-speech (--speak)",
}


def check_voice_packages(find_spec=importlib.util.find_spec) -> Check:
    """Voice is optional, so missing packages are a warning. Nothing is imported."""
    missing = [f"{pkg} ({what})" for pkg, what in VOICE_PACKAGES.items() if find_spec(pkg) is None]
    if missing:
        return Check("voice packages", Status.WARN, "not installed: " + ", ".join(missing))
    return Check("voice packages", Status.OK, ", ".join(VOICE_PACKAGES))


def run_checks(settings: Settings, client: OllamaAdmin) -> list[Check]:
    return [
        check_python(),
        Check("config", Status.OK, "all YAML files valid"),
        check_safety(settings),
        *check_ollama(settings, client),
        check_skills(settings),
        check_write_roots(settings),
        check_voice(settings),
        check_voice_packages(),
    ]
