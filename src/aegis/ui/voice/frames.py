"""Fixed-size PCM frames and the bounded queue between the audio callback and the consumer."""

from __future__ import annotations

import threading
from collections import deque


class Reframer:
    """Turns arbitrary-length byte chunks into exact ``frame_bytes`` frames.

    The audio callback normally delivers exactly one frame, but this guarantees it even if
    a host API hands over a different block size.
    """

    def __init__(self, frame_bytes: int) -> None:
        if frame_bytes <= 0:
            raise ValueError("frame_bytes must be positive")
        self.frame_bytes = frame_bytes
        self._buf = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        self._buf += data
        n = self.frame_bytes
        frames = []
        while len(self._buf) >= n:
            frames.append(bytes(self._buf[:n]))
            del self._buf[:n]
        return frames

    @property
    def pending(self) -> int:
        return len(self._buf)

    def clear(self) -> None:
        self._buf.clear()


class BoundedFrameQueue:
    """Thread-safe FIFO with a hard size limit.

    ``put`` never blocks (it is called from the real-time audio callback). When full, the
    oldest frame is dropped and counted, so a slow consumer loses old audio, not new audio.
    """

    def __init__(self, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize = maxsize
        self._q: deque[bytes] = deque(maxlen=maxsize)
        self._cond = threading.Condition()
        self.dropped = 0
        self.total = 0

    def put(self, frame: bytes) -> None:
        with self._cond:
            if len(self._q) == self.maxsize:
                self.dropped += 1
            self._q.append(frame)
            self.total += 1
            self._cond.notify()

    def get(self, timeout: float | None = None) -> bytes | None:
        """Next frame, or ``None`` if nothing arrived within ``timeout`` seconds."""
        with self._cond:
            if not self._cond.wait_for(lambda: bool(self._q), timeout):
                return None
            return self._q.popleft()

    def clear(self) -> None:
        with self._cond:
            self._q.clear()

    def __len__(self) -> int:
        with self._cond:
            return len(self._q)
