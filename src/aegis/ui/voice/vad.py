"""Voice activity detection. ``webrtcvad`` is imported lazily."""

from __future__ import annotations

from typing import Any, Protocol

from aegis.models.config import AudioConfig, VadConfig
from aegis.ui.voice.audio import SAMPLE_WIDTH


class Vad(Protocol):
    def is_speech(self, frame: bytes) -> bool: ...


class WebRtcVad:
    def __init__(self, vad: VadConfig, audio: AudioConfig, *, module: Any = None) -> None:
        if module is None:
            try:
                import webrtcvad as module
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise RuntimeError(
                    'webrtcvad is not installed (pip install -e ".[voice]")'
                ) from exc
        self._vad = module.Vad(vad.aggressiveness)
        self._rate = audio.sample_rate
        self._frame_bytes = audio.frame_samples * audio.channels * SAMPLE_WIDTH

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) != self._frame_bytes:
            raise ValueError(f"VAD frame must be {self._frame_bytes} bytes, got {len(frame)}")
        return bool(self._vad.is_speech(frame, self._rate))
