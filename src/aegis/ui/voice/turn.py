"""Turn detection: per-frame VAD decisions -> utterances, captured into bounded buffers."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

from aegis.models.config import AudioConfig, VadConfig

EndReason = Literal["silence", "max_length", "flush"]


@dataclass(frozen=True)
class SpeechStarted:
    pre_roll_ms: int


@dataclass(frozen=True)
class TurnDiscarded:
    duration_ms: int  # too short to be speech (click, cough)


@dataclass(frozen=True)
class Utterance:
    pcm: bytes  # 16-bit little-endian mono PCM
    sample_rate: int
    duration_ms: int
    end_reason: EndReason


TurnEvent = SpeechStarted | TurnDiscarded | Utterance


class TurnDetector:
    """State machine fed one frame at a time.

    - Idle: keeps a ring buffer of the last ``pre_roll_ms`` of audio. ``start_frames``
      consecutive speech frames open a turn (the ring buffer becomes its start).
    - In turn: frames are appended. ``end_silence_ms`` of non-speech closes it; reaching
      ``max_utterance_seconds`` cuts it. Trailing silence is trimmed.
    - Turns shorter than ``min_utterance_ms`` of voiced audio are discarded.

    Memory is bounded: at most ``max(pre_roll, start_frames)`` frames while idle and
    ``max_utterance_seconds`` worth of frames in a turn.
    """

    def __init__(self, vad: VadConfig, audio: AudioConfig) -> None:
        fm = audio.frame_ms
        self.frame_ms = fm
        self.sample_rate = audio.sample_rate
        self.start_frames = vad.start_frames
        self.end_frames = max(1, math.ceil(vad.end_silence_ms / fm))
        self.max_frames = max(1, int(vad.max_utterance_seconds * 1000 // fm))
        self.min_frames = math.ceil(vad.min_utterance_ms / fm)
        self.pre_roll_frames = max(math.ceil(vad.pre_roll_ms / fm), vad.start_frames)
        self._ring: deque[bytes] = deque(maxlen=self.pre_roll_frames)
        self._frames: list[bytes] = []
        self._speech_run = 0
        self._silence_run = 0
        self._in_turn = False

    @property
    def in_turn(self) -> bool:
        return self._in_turn

    @property
    def buffered_frames(self) -> int:
        return len(self._frames) if self._in_turn else len(self._ring)

    @property
    def buffered_ms(self) -> int:
        return self.buffered_frames * self.frame_ms

    def reset(self) -> None:
        self._ring.clear()
        self._frames = []
        self._speech_run = 0
        self._silence_run = 0
        self._in_turn = False

    def feed(self, frame: bytes, is_speech: bool) -> TurnEvent | None:
        if not self._in_turn:
            self._ring.append(frame)
            self._speech_run = self._speech_run + 1 if is_speech else 0
            if self._speech_run < self.start_frames:
                return None
            self._in_turn = True
            self._frames = list(self._ring)
            self._ring.clear()
            self._speech_run = 0
            self._silence_run = 0
            lead = len(self._frames) - self.start_frames
            return SpeechStarted(pre_roll_ms=lead * self.frame_ms)

        self._frames.append(frame)
        self._silence_run = 0 if is_speech else self._silence_run + 1
        if self._silence_run >= self.end_frames:
            return self._finish("silence")
        if len(self._frames) >= self.max_frames:
            return self._finish("max_length")
        return None

    def flush(self) -> TurnEvent | None:
        """End any open turn now (e.g. the stream stopped)."""
        return self._finish("flush") if self._in_turn else None

    def _finish(self, reason: EndReason) -> TurnEvent:
        voiced = self._frames[: len(self._frames) - self._silence_run]
        self.reset()
        duration = len(voiced) * self.frame_ms
        if len(voiced) < self.min_frames:
            return TurnDiscarded(duration_ms=duration)
        return Utterance(
            pcm=b"".join(voiced),
            sample_rate=self.sample_rate,
            duration_ms=duration,
            end_reason=reason,
        )
