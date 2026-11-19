"""Text-to-speech via Kokoro. Imported lazily; offline by default."""

from __future__ import annotations

import os
import re
from array import array
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from aegis.core.logging import get_logger
from aegis.models.config import TtsConfig

log = get_logger("voice.tts")

KOKORO_SAMPLE_RATE = 24000


class TtsError(Exception):
    pass


@dataclass(frozen=True)
class AudioChunk:
    pcm: bytes  # int16 little-endian mono
    sample_rate: int


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> Iterator[AudioChunk]: ...


def float_to_int16(samples: Any) -> bytes:
    """Float samples in [-1, 1] (torch tensor, numpy array or sequence) -> int16 bytes."""
    if hasattr(samples, "detach"):  # torch tensor
        samples = samples.detach().cpu().numpy()
    if hasattr(samples, "astype"):  # numpy array
        import numpy as np

        return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return array("h", (int(max(-1.0, min(1.0, float(x))) * 32767) for x in samples)).tobytes()


_MARKDOWN = re.compile(r"[*`#>]+")  # not "_": skill names like system_info must survive
_BULLET = re.compile(r"^\s*(?:[-•]|\d+\.)\s+", re.MULTILINE)


def speakable(text: str) -> str:
    """Strip markdown and list markers so they aren't read aloud."""
    text = _BULLET.sub("", text)
    text = _MARKDOWN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class KokoroTTS:
    def __init__(self, config: TtsConfig, *, pipeline: Any = None) -> None:
        self._config = config
        self._pipeline = pipeline if pipeline is not None else self._load(config)

    @staticmethod
    def _load(config: TtsConfig) -> Any:
        if config.offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise TtsError('kokoro is not installed (pip install -e ".[speak]")') from exc
        try:
            return KPipeline(lang_code=config.lang_code, repo_id=config.repo_id)
        except Exception as exc:
            raise TtsError(
                f"could not load Kokoro: {exc}. With tts.offline=true the model must "
                "already be in the local Hugging Face cache."
            ) from exc

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        """Yield audio chunk by chunk (Kokoro splits long text), so playback starts early."""
        try:
            for result in self._pipeline(text, voice=self._config.voice, speed=self._config.speed):
                audio = result[2] if isinstance(result, tuple) else result.audio
                if audio is None:
                    continue
                yield AudioChunk(pcm=float_to_int16(audio), sample_rate=KOKORO_SAMPLE_RATE)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError(f"synthesis failed: {exc}") from exc
