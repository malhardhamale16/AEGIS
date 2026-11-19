"""Microphone input via sounddevice (PortAudio), callback mode, fixed 16-bit PCM frames.

Device and host API come from voice.yaml and are validated, never switched automatically.
``sounddevice`` is imported lazily so the rest of AEGIS (and the tests) work without it.
"""

from __future__ import annotations

from typing import Any, Protocol

from aegis.core.logging import get_logger
from aegis.models.config import AudioConfig
from aegis.ui.voice.frames import BoundedFrameQueue, Reframer

log = get_logger("voice.audio")

SAMPLE_WIDTH = 2  # int16
DTYPE = "int16"

# voice.yaml name -> PortAudio host API name
HOST_API_NAMES = {
    "MME": "MME",
    "WASAPI": "Windows WASAPI",
    "DirectSound": "Windows DirectSound",
    "WDM-KS": "Windows WDM-KS",
}


class AudioDeviceError(Exception):
    """The configured device can't be used as configured."""


class AudioSource(Protocol):
    @property
    def active(self) -> bool: ...
    @property
    def dropped(self) -> int: ...
    @property
    def overflows(self) -> int: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self, timeout: float | None = None) -> bytes | None: ...
    def clear(self) -> None: ...


def frame_bytes(config: AudioConfig) -> int:
    return config.frame_samples * config.channels * SAMPLE_WIDTH


def load_sounddevice() -> Any:
    try:
        import sounddevice
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise AudioDeviceError('sounddevice is not installed (pip install -e ".[voice]")') from exc
    return sounddevice


def describe_device(config: AudioConfig, sd: Any) -> dict[str, Any]:
    """Validate the configured device/host API/format and return its info. No auto-switching."""
    try:
        info = sd.query_devices(config.input_device)
    except Exception as exc:
        raise AudioDeviceError(f"input device {config.input_device} not found: {exc}") from exc
    hostapi = sd.query_hostapis(info["hostapi"])["name"]
    expected = HOST_API_NAMES[config.host_api]
    if hostapi != expected:
        raise AudioDeviceError(
            f"device {config.input_device} ({info['name']}) uses host API {hostapi!r}, but "
            f"voice.yaml asks for {expected!r}. Pick a device index that belongs to {expected} "
            "(scripts/diagnose_audio.py --list) or change audio.host_api."
        )
    if info["max_input_channels"] < config.channels:
        raise AudioDeviceError(f"device {config.input_device} ({info['name']}) has no input")
    try:
        sd.check_input_settings(
            device=config.input_device,
            channels=config.channels,
            dtype=DTYPE,
            samplerate=config.sample_rate,
        )
    except Exception as exc:
        raise AudioDeviceError(
            f"device {config.input_device} rejects {config.sample_rate} Hz / "
            f"{config.channels} ch / {DTYPE}: {exc}"
        ) from exc
    return {"index": config.input_device, "name": info["name"], "hostapi": hostapi}


class SoundDeviceSource:
    """Callback-mode input stream feeding a bounded frame queue."""

    def __init__(self, config: AudioConfig, *, sd: Any = None) -> None:
        if config.mode != "callback":  # schema allows only callback today; keep the guard
            raise AudioDeviceError(f"unsupported audio mode {config.mode!r}")
        self._config = config
        self._sd = sd
        self._stream: Any = None
        self.queue = BoundedFrameQueue(config.queue_max_frames)
        self._reframer = Reframer(frame_bytes(config))
        self._overflows = 0
        self.device: dict[str, Any] | None = None

    # -------------------------------------------------------------- properties

    @property
    def active(self) -> bool:
        return bool(self._stream is not None and self._stream.active)

    @property
    def dropped(self) -> int:
        return self.queue.dropped

    @property
    def overflows(self) -> int:
        return self._overflows

    # -------------------------------------------------------------- callback

    def _callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        # Runs on PortAudio's thread: copy, slice, enqueue. Nothing slow here.
        if status and getattr(status, "input_overflow", False):
            self._overflows += 1
        for frame in self._reframer.push(bytes(indata)):
            self.queue.put(frame)

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = self._sd or load_sounddevice()
        self._sd = sd
        self.device = describe_device(self._config, sd)
        cfg = self._config
        self._stream = sd.RawInputStream(
            device=cfg.input_device,
            samplerate=cfg.sample_rate,
            channels=cfg.channels,
            dtype=DTYPE,
            blocksize=cfg.frame_samples,
            callback=self._callback,
        )
        self._stream.start()
        log.info(
            "audio input started: device %s (%s, %s) %d Hz %d ms frames",
            cfg.input_device,
            self.device["name"],
            self.device["hostapi"],
            cfg.sample_rate,
            cfg.frame_ms,
        )

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        self._reframer.clear()

    def read(self, timeout: float | None = None) -> bytes | None:
        return self.queue.get(timeout)

    def clear(self) -> None:
        """Discard queued frames (e.g. audio captured while AEGIS was speaking)."""
        self.queue.clear()

    def __enter__(self) -> SoundDeviceSource:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
