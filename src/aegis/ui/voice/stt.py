"""Speech-to-text via Faster-Whisper. Imported lazily; never downloads unless configured to."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from typing import Any, Protocol

from aegis.core.logging import get_logger
from aegis.models.config import SttConfig
from aegis.ui.voice.turn import Utterance

log = get_logger("voice.stt")


class SttError(Exception):
    pass


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    duration_ms: int


class SpeechToText(Protocol):
    def transcribe(self, utterance: Utterance) -> Transcript: ...


def pcm_to_float(pcm: bytes) -> Any:
    """int16 PCM -> float32 samples in [-1, 1) (numpy array if available, else a list)."""
    try:
        import numpy as np
    except ImportError:
        return [s / 32768.0 for s in array("h", pcm)]
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


class FasterWhisperSTT:
    def __init__(self, config: SttConfig, *, model: Any = None) -> None:
        self._config = config
        self._model = model if model is not None else self._load(config)

    @staticmethod
    def _load(config: SttConfig) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttError('faster-whisper is not installed (pip install -e ".[voice]")') from exc
        try:
            return WhisperModel(
                config.model,
                device=config.device,
                compute_type=config.compute_type,
                download_root=str(config.model_dir) if config.model_dir else None,
                local_files_only=config.local_files_only,
            )
        except Exception as exc:
            hint = (
                " The model is not on disk and stt.local_files_only is true: download it "
                "yourself, or point stt.model at a local model directory."
                if config.local_files_only
                else ""
            )
            raise SttError(f"could not load Whisper model {config.model!r}: {exc}.{hint}") from exc

    def transcribe(self, utterance: Utterance) -> Transcript:
        if utterance.sample_rate != 16000:
            raise SttError(f"Whisper needs 16000 Hz audio, got {utterance.sample_rate}")
        try:
            segments, info = self._model.transcribe(
                pcm_to_float(utterance.pcm),
                language=self._config.language,
                beam_size=self._config.beam_size,
                vad_filter=False,  # turn detection already did this
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            raise SttError(f"transcription failed: {exc}") from exc
        language = getattr(info, "language", None)
        log.debug("transcribed %d ms -> %r", utterance.duration_ms, text)
        return Transcript(text=text, language=language, duration_ms=utterance.duration_ms)
