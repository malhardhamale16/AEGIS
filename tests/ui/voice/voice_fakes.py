"""Fakes for voice tests: PCM frames, a scripted source, a scripted VAD, a fake sounddevice."""

import struct

FRAME_SAMPLES = 480  # 16 kHz * 30 ms
FRAME_BYTES = FRAME_SAMPLES * 2


def frame(value: int = 0) -> bytes:
    """One 30 ms int16 frame filled with ``value`` (distinct values = traceable order)."""
    return struct.pack("<h", value) * FRAME_SAMPLES


class ScriptedVad:
    """Speech iff the frame's first sample is non-zero."""

    def __init__(self) -> None:
        self.calls = 0

    def is_speech(self, data: bytes) -> bool:
        self.calls += 1
        return struct.unpack_from("<h", data)[0] != 0


class ListSource:
    """AudioSource over a fixed list of frames; goes inactive once drained."""

    def __init__(self, frames, *, stay_active: bool = False) -> None:
        self.frames = list(frames)
        self.stay_active = stay_active
        self.started = False

    @property
    def active(self) -> bool:
        return self.stay_active or bool(self.frames)

    @property
    def dropped(self) -> int:
        return 0

    @property
    def overflows(self) -> int:
        return 0

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def read(self, timeout=None):
        return self.frames.pop(0) if self.frames else None

    def clear(self) -> None:
        # Scripted frames represent the future, so they are kept; only the call is recorded.
        self.clears = getattr(self, "clears", 0) + 1


class FakeStatus:
    def __init__(self, input_overflow: bool) -> None:
        self.input_overflow = input_overflow

    def __bool__(self) -> bool:
        return self.input_overflow


class FakeStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.active = False
        self.closed = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.closed = True

    def push(self, data: bytes, overflow: bool = False) -> None:
        """Simulate PortAudio invoking the callback."""
        self.kwargs["callback"](data, len(data) // 2, None, FakeStatus(overflow))


class FakeSoundDevice:
    """Minimal stand-in for the ``sounddevice`` module."""

    def __init__(self, hostapi="MME", max_input_channels=1, reject=None, devices=(0, 1)):
        self._hostapi = hostapi
        self._channels = max_input_channels
        self._reject = reject
        self._devices = set(devices)
        self.streams: list[FakeStream] = []

    def query_devices(self, index):
        if index not in self._devices:
            raise ValueError(f"Error querying device {index}")
        return {"name": "Microphone (Fake)", "hostapi": 0, "max_input_channels": self._channels}

    def query_hostapis(self, index):
        return {"name": self._hostapi}

    def check_input_settings(self, **kwargs):
        if self._reject:
            raise ValueError(self._reject)

    def RawInputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice's API
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream

    def RawOutputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice's API
        stream = FakeOutputStream(**kwargs)
        self.streams.append(stream)
        return stream


class FakeOutputStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.writes: list[bytes] = []
        self.events: list[str] = []
        self.on_write = None  # hook: called after each write (e.g. to cancel mid-playback)

    def start(self):
        self.events.append("start")

    def write(self, data):
        self.writes.append(bytes(data))
        if self.on_write:
            self.on_write(len(self.writes))

    def stop(self):
        self.events.append("stop")

    def abort(self):
        self.events.append("abort")

    def close(self):
        self.events.append("close")


# ----------------------------------------------------------------- session fakes


class FakeSTT:
    def __init__(self, texts):
        self.texts = list(texts)
        self.seen = []

    def transcribe(self, utterance):
        from aegis.ui.voice.stt import SttError, Transcript

        self.seen.append(utterance)
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise SttError(str(item))
        return Transcript(text=item, language="en", duration_ms=utterance.duration_ms)


class FakeAgent:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = []

    def handle(self, text, *, dry_run=None):
        from aegis.models.plan import AgentReply

        self.calls.append((text, dry_run))
        reply = self.replies.pop(0) if self.replies else f"echo: {text}"
        return AgentReply(text=reply)


class FakeTTS:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        from aegis.ui.voice.tts import AudioChunk

        self.texts.append(text)
        yield AudioChunk(pcm=b"\x01\x00" * 10, sample_rate=24000)


class FakePlayback:
    """Plays 'forever' until cancelled, unless finish_immediately."""

    def __init__(self, finish_immediately=False, linger_after_cancel=False):
        self._playing = not finish_immediately
        self.linger_after_cancel = linger_after_cancel  # like the real thread winding down
        self.cancelled = False
        self.cancel_calls = 0
        self.error = None
        self.waited = False

    @property
    def playing(self):
        return self._playing

    def cancel(self):
        self.cancel_calls += 1
        self.cancelled = True
        if not self.linger_after_cancel:
            self._playing = False

    def wait(self, timeout=None):
        self.waited = True
        self._playing = False
        return True


class FakePlayer:
    def __init__(self, finish_immediately=False, linger_after_cancel=False):
        self.finish_immediately = finish_immediately
        self.linger_after_cancel = linger_after_cancel
        self.handles = []
        self.chunks = []

    def play(self, chunks):
        self.chunks.append(list(chunks))
        handle = FakePlayback(self.finish_immediately, self.linger_after_cancel)
        self.handles.append(handle)
        return handle
