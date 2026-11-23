"""Pydantic schemas for every file in ``configs/``.

All models forbid unknown keys so a typo in YAML fails loudly instead of being ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aegis.models.skill import RiskLevel


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- aegis.yaml


class AppConfig(_Strict):
    name: str = "AEGIS"
    data_dir: Path = Path("data")


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggingConfig(_Strict):
    level: LogLevel = "INFO"  # log file level
    console: bool = True
    console_level: LogLevel = "WARNING"  # terminal level; keeps command output clean
    file: Path | None = Path("logs/aegis.log")


class SafetyConfig(_Strict):
    dry_run: bool = True
    require_confirmation: bool = True


class PlannerSettings(_Strict):
    max_steps: int = Field(5, ge=1, le=20)
    max_retries: int = Field(1, ge=0, le=5)  # re-asks the LLM after an invalid plan


class ExecutorSettings(_Strict):
    stop_on_failure: bool = True


class ConversationSettings(_Strict):
    max_history: int = Field(20, ge=0)  # messages kept (user + assistant)
    summary_max_chars: int = Field(4000, gt=0)  # cap on result JSON sent for summarizing


class AgentsConfig(_Strict):
    planner: PlannerSettings = Field(default_factory=PlannerSettings)
    executor: ExecutorSettings = Field(default_factory=ExecutorSettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)


class AegisConfig(_Strict):
    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)


# -------------------------------------------------------------------------- models.yaml


class OllamaConfig(_Strict):
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = Field(60.0, gt=0)
    health_timeout_seconds: float = Field(3.0, gt=0)

    @field_validator("base_url")
    @classmethod
    def _local_only(cls, v: str) -> str:
        # AEGIS is local-first: no cloud endpoints, ever.
        from urllib.parse import urlparse

        host = urlparse(v).hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(f"Ollama base_url must be local (got host {host!r})")
        return v.rstrip("/")


class ModelRoles(_Strict):
    planner: str = "llama3.2:3b"
    executor: str = "llama3.2:3b"
    conversation: str = "llama3.2:3b"


class GenerationConfig(_Strict):
    temperature: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(1024, gt=0)


class ModelsConfig(_Strict):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    roles: ModelRoles = Field(default_factory=ModelRoles)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


# -------------------------------------------------------------------------- skills.yaml


class SkillOverride(_Strict):
    enabled: bool | None = None
    risk: RiskLevel | None = None


class FileSearchSettings(_Strict):
    default_root: Path = Path("~")
    max_results: int = Field(50, gt=0, le=1000)
    exclude_dirs: list[str] = Field(
        default_factory=lambda: [".git", "node_modules", "__pycache__", "AppData", "$Recycle.Bin"]
    )


class OpenAppSettings(_Strict):
    # alias -> executable or shell target. Only these can be launched.
    aliases: dict[str, str] = Field(default_factory=dict)


class ClipboardSettings(_Strict):
    max_chars: int = Field(2000, gt=0, le=100_000)


class ProcessListSettings(_Strict):
    max_results: int = Field(100, gt=0, le=2000)


class WriteFileSettings(_Strict):
    # Writes outside these directories are refused, even after confirmation.
    allowed_roots: list[Path] = Field(default_factory=lambda: [Path("~/Documents/AEGIS")])
    max_bytes: int = Field(1_000_000, gt=0)


class SkillsConfig(_Strict):
    enabled: list[str] = Field(default_factory=list)
    overrides: dict[str, SkillOverride] = Field(default_factory=dict)
    file_search: FileSearchSettings = Field(default_factory=FileSearchSettings)
    open_app: OpenAppSettings = Field(default_factory=OpenAppSettings)
    clipboard_read: ClipboardSettings = Field(default_factory=ClipboardSettings)
    list_processes: ProcessListSettings = Field(default_factory=ProcessListSettings)
    write_file: WriteFileSettings = Field(default_factory=WriteFileSettings)


# -------------------------------------------------------------------------- voice.yaml


class AudioConfig(_Strict):
    input_device: int = Field(1, ge=0)
    host_api: Literal["MME", "WASAPI", "DirectSound", "WDM-KS"] = "MME"
    mode: Literal["callback"] = "callback"
    sample_rate: Literal[8000, 16000, 32000, 48000] = 16000
    channels: Literal[1] = 1
    frame_ms: Literal[10, 20, 30] = 30
    queue_max_frames: int = Field(200, gt=0)

    @property
    def frame_samples(self) -> int:
        return self.sample_rate * self.frame_ms // 1000


class VadConfig(_Strict):
    aggressiveness: int = Field(2, ge=0, le=3)
    start_frames: int = Field(5, gt=0)  # consecutive speech frames that open a turn
    end_silence_ms: int = Field(700, gt=0)  # trailing silence that closes a turn
    max_utterance_seconds: float = Field(30.0, gt=0)  # hard cap; turn is cut here
    pre_roll_ms: int = Field(300, ge=0)  # audio kept from before the turn opened
    min_utterance_ms: int = Field(250, ge=0)  # shorter turns (clicks, coughs) are dropped


class SttConfig(_Strict):
    engine: Literal["faster-whisper"] = "faster-whisper"
    model: str = "base"  # model name or a local directory
    language: str = "en"
    device: Literal["cpu", "cuda"] = "cpu"
    compute_type: Literal["int8", "int8_float16", "float16", "float32"] = "int8"
    beam_size: int = Field(1, ge=1, le=10)
    # Never download at runtime: the model must already be on disk.
    local_files_only: bool = True
    model_dir: Path | None = None


class TtsConfig(_Strict):
    engine: Literal["kokoro"] = "kokoro"
    voice: str = "af_heart"
    lang_code: str = "a"  # Kokoro language: a = American English, b = British English
    repo_id: str = "hexgrad/Kokoro-82M"  # resolved from the local cache only (see offline)
    speed: float = Field(1.0, gt=0)
    output_device: int | None = None
    # Sets HF_HUB_OFFLINE=1 before loading Kokoro, so it never fetches anything at runtime.
    offline: bool = True
    block_ms: int = Field(20, ge=5, le=200)  # playback write size = cancel granularity


class BargeInConfig(_Strict):
    # true: keep listening while speaking; sustained speech stops playback.
    # false: half-duplex; mic input during playback is discarded (no echo problems).
    enabled: bool = True
    min_speech_ms: int = Field(300, gt=0)


class VoiceConfig(_Strict):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    barge_in: BargeInConfig = Field(default_factory=BargeInConfig)


# ---------------------------------------------------------------------------- aggregate


class Settings(_Strict):
    """Everything loaded from ``configs/``."""

    aegis: AegisConfig = Field(default_factory=AegisConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
