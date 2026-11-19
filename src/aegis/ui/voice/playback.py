"""Cancellable audio playback on a worker thread.

Synthesis is lazy: chunks are pulled from the TTS iterator inside the worker, so playback
starts after the first chunk and cancelling also stops further synthesis.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any, Protocol

from aegis.core.logging import get_logger
from aegis.models.config import TtsConfig
from aegis.ui.voice.tts import AudioChunk

log = get_logger("voice.playback")


class Playback:
    """Handle for one playback. Thread-safe."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._done = threading.Event()
        self.error: Exception | None = None

    @property
    def playing(self) -> bool:
        return not self._done.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        """True once playback has finished (or was cancelled)."""
        return self._done.wait(timeout)

    def _finish(self) -> None:
        self._done.set()


class AudioPlayer(Protocol):
    def play(self, chunks: Iterable[AudioChunk]) -> Playback: ...


class SoundDevicePlayer:
    def __init__(self, config: TtsConfig, *, sd: Any = None) -> None:
        self._config = config
        self._sd = sd

    def play(self, chunks: Iterable[AudioChunk]) -> Playback:
        handle = Playback()
        thread = threading.Thread(
            target=self._run, args=(chunks, handle), name="aegis-playback", daemon=True
        )
        thread.start()
        return handle

    def _run(self, chunks: Iterable[AudioChunk], handle: Playback) -> None:
        stream = None
        try:
            sd = self._sd
            if sd is None:
                import sounddevice as sd

                self._sd = sd
            for chunk in chunks:
                if handle.cancelled:
                    break
                if stream is None:
                    stream = sd.RawOutputStream(
                        samplerate=chunk.sample_rate,
                        channels=1,
                        dtype="int16",
                        device=self._config.output_device,
                    )
                    stream.start()
                block = chunk.sample_rate * self._config.block_ms // 1000 * 2
                for i in range(0, len(chunk.pcm), block):
                    if handle.cancelled:
                        break
                    stream.write(chunk.pcm[i : i + block])
                if handle.cancelled:
                    break  # before pulling (= synthesizing) the next chunk
        except Exception as exc:
            handle.error = exc
            log.exception("playback failed")
        finally:
            if stream is not None:
                try:
                    if handle.cancelled:
                        stream.abort()  # stop now, drop what is buffered
                    else:
                        stream.stop()  # let the tail drain
                finally:
                    stream.close()
            handle._finish()
