"""Voice conversation loop: utterance -> STT -> agent -> (optional) TTS, with barge-in."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from aegis.core.logging import get_logger
from aegis.models.config import BargeInConfig
from aegis.models.plan import AgentReply
from aegis.ui.voice.capture import VoiceCapture
from aegis.ui.voice.playback import AudioPlayer, Playback
from aegis.ui.voice.stt import SpeechToText, SttError
from aegis.ui.voice.tts import TextToSpeech, speakable
from aegis.ui.voice.turn import Utterance

log = get_logger("voice.session")

# (kind, text) where kind is "you", "aegis", "status" or "error"
EventSink = Callable[[str, str], None]


class Agent(Protocol):
    def handle(self, user_text: str, *, dry_run: bool | None = None) -> AgentReply: ...


@dataclass
class SessionStats:
    utterances: int = 0
    empty_transcripts: int = 0
    replies: int = 0
    spoken: int = 0
    barge_ins: int = 0
    errors: int = 0


class VoiceSession:
    """Single-threaded loop over captured utterances.

    Playback runs on its own thread. With barge-in enabled the mic keeps being read while
    AEGIS speaks, and ``min_speech_ms`` of continuous speech cancels playback (the speech
    itself is captured as the next turn). With barge-in disabled the session is
    half-duplex: it waits for playback to finish and discards what the mic heard meanwhile.
    """

    def __init__(
        self,
        capture: VoiceCapture,
        stt: SpeechToText,
        agent: Agent,
        *,
        barge_in: BargeInConfig,
        frame_ms: int,
        tts: TextToSpeech | None = None,
        player: AudioPlayer | None = None,
        on_event: EventSink | None = None,
        dry_run: bool | None = None,
    ) -> None:
        if (tts is None) != (player is None):
            raise ValueError("tts and player must both be given (or neither)")
        self.capture = capture
        self.stt = stt
        self.agent = agent
        self.tts = tts
        self.player = player
        self.barge_in = barge_in
        self.dry_run = dry_run
        self.stats = SessionStats()
        self._emit = on_event or (lambda kind, text: None)
        self._barge_frames = max(1, math.ceil(barge_in.min_speech_ms / frame_ms))
        self._speech_run = 0
        self._playback: Playback | None = None
        capture.frame_listener = self._on_frame

    @property
    def speaking(self) -> bool:
        return self._playback is not None and self._playback.playing

    # ------------------------------------------------------------------ barge-in

    def _on_frame(self, is_speech: bool) -> None:
        # A cancelled playback stays "playing" until its thread winds down; ignore it then,
        # so one interruption is handled (and reported) exactly once.
        playback = self._playback
        if not (self.barge_in.enabled and self.speaking) or (playback and playback.cancelled):
            self._speech_run = 0
            return
        self._speech_run = self._speech_run + 1 if is_speech else 0
        if self._speech_run >= self._barge_frames:
            assert self._playback is not None
            self._playback.cancel()
            self._speech_run = 0
            self.stats.barge_ins += 1
            self._emit("status", "interrupted")

    # --------------------------------------------------------------------- turns

    def handle_utterance(self, utterance: Utterance) -> None:
        self.stats.utterances += 1
        try:
            text = self.stt.transcribe(utterance).text.strip()
        except SttError as exc:
            self.stats.errors += 1
            self._emit("error", str(exc))
            return
        if not text:
            self.stats.empty_transcripts += 1
            return
        self._emit("you", text)
        reply = self.agent.handle(text, dry_run=self.dry_run)
        self.stats.replies += 1
        self._emit("aegis", reply.text)
        self.speak(reply.text)

    def speak(self, text: str) -> None:
        if self.tts is None or self.player is None:
            return
        if self.speaking:
            self._playback.cancel()  # type: ignore[union-attr]
        clean = speakable(text)
        if not clean:
            return
        self._playback = self.player.play(self.tts.synthesize(clean))
        self.stats.spoken += 1
        if not self.barge_in.enabled:
            self._playback.wait()
            self.capture.source.clear()
            self.capture.detector.reset()
            if self._playback.error is not None:
                self.stats.errors += 1
                self._emit("error", f"playback failed: {self._playback.error}")

    # ---------------------------------------------------------------------- loop

    def run(
        self, stop: threading.Event | None = None, *, deadline: float | None = None
    ) -> SessionStats:
        source = self.capture.source
        source.start()
        try:
            for utterance in self.capture.utterances(stop, deadline=deadline):
                self.handle_utterance(utterance)
        finally:
            if self._playback is not None:
                self._playback.cancel()
                self._playback.wait(2)
            source.stop()
        return self.stats
