"""Capture pipeline: audio source -> VAD -> turn detector -> utterances."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from aegis.core.events import EventBus
from aegis.core.logging import get_logger
from aegis.ui.voice.audio import AudioSource
from aegis.ui.voice.turn import SpeechStarted, TurnDetector, TurnDiscarded, Utterance
from aegis.ui.voice.vad import Vad

log = get_logger("voice.capture")

TOPIC_SPEECH_STARTED = "voice.speech_started"
TOPIC_UTTERANCE = "voice.utterance"
TOPIC_DISCARDED = "voice.discarded"


@dataclass
class CaptureStats:
    frames: int = 0
    speech_frames: int = 0
    utterances: int = 0
    discarded: int = 0


class VoiceCapture:
    """Pulls frames on the consumer thread. The audio callback only enqueues."""

    def __init__(
        self,
        source: AudioSource,
        vad: Vad,
        detector: TurnDetector,
        *,
        bus: EventBus | None = None,
    ) -> None:
        self.source = source
        self.vad = vad
        self.detector = detector
        self.bus = bus
        self.stats = CaptureStats()
        # Called with each frame's VAD decision (used for barge-in).
        self.frame_listener: Callable[[bool], None] | None = None

    def _publish(self, topic: str, payload: dict) -> None:
        if self.bus:
            self.bus.publish(topic, payload)

    def _handle(self, event: object) -> Utterance | None:
        if isinstance(event, SpeechStarted):
            self._publish(TOPIC_SPEECH_STARTED, {"pre_roll_ms": event.pre_roll_ms})
        elif isinstance(event, TurnDiscarded):
            self.stats.discarded += 1
            self._publish(TOPIC_DISCARDED, {"duration_ms": event.duration_ms})
        elif isinstance(event, Utterance):
            self.stats.utterances += 1
            self._publish(
                TOPIC_UTTERANCE,
                {"duration_ms": event.duration_ms, "end_reason": event.end_reason},
            )
            return event
        return None

    def process(self, frame: bytes) -> Utterance | None:
        """Feed one frame through VAD and the turn detector."""
        speech = self.vad.is_speech(frame)
        self.stats.frames += 1
        self.stats.speech_frames += int(speech)
        if self.frame_listener is not None:
            self.frame_listener(speech)
        return self._handle(self.detector.feed(frame, speech))

    def utterances(
        self,
        stop: threading.Event | None = None,
        *,
        poll_timeout: float = 0.1,
        deadline: float | None = None,
    ) -> Iterator[Utterance]:
        """Yield utterances until ``stop`` is set, ``deadline`` (monotonic) passes, or the
        source goes inactive with an empty queue. An open turn is flushed at the end."""
        stop = stop or threading.Event()
        while not stop.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                break
            frame = self.source.read(poll_timeout)
            if frame is None:
                if not self.source.active:
                    break
                continue
            utt = self.process(frame)
            if utt is not None:
                yield utt
        tail = self._handle(self.detector.flush())
        if tail is not None:
            yield tail

    def listen_once(self, timeout_s: float, *, poll_timeout: float = 0.1) -> Utterance | None:
        """Return the first utterance within ``timeout_s`` seconds, or ``None``."""
        deadline = time.monotonic() + timeout_s
        for utt in self.utterances(poll_timeout=poll_timeout, deadline=deadline):
            self.detector.reset()
            return utt
        return None
