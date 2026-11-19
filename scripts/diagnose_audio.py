"""Opt-in microphone diagnostic. Not part of the test suite. Audio is never saved.

  python scripts/diagnose_audio.py --list        list input devices only (no recording)
  python scripts/diagnose_audio.py               record from the voice.yaml device (5 s)
  python scripts/diagnose_audio.py --seconds 10

Uses the exact device / host API / rate / frame size from voice.yaml. It never switches
to another host API; if the configured one doesn't work, it says so and exits 1.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.core.config import load_config  # noqa: E402
from aegis.ui.voice.audio import (  # noqa: E402
    HOST_API_NAMES,
    AudioDeviceError,
    SoundDeviceSource,
    describe_device,
    load_sounddevice,
)
from aegis.ui.voice.capture import VoiceCapture  # noqa: E402
from aegis.ui.voice.turn import TurnDetector  # noqa: E402
from aegis.ui.voice.vad import WebRtcVad  # noqa: E402


def dbfs(frame: bytes) -> float:
    samples = array("h", frame)
    if not samples:
        return -120.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return 20 * math.log10(rms / 32768) if rms > 0 else -120.0


def list_devices(sd, audio) -> None:
    print(f"sounddevice {sd.__version__}, {sd.get_portaudio_version()[1]}")
    hostapis = sd.query_hostapis()
    wanted = HOST_API_NAMES[audio.host_api]
    print(
        f"\nConfigured: input_device={audio.input_device}, host_api={audio.host_api} ({wanted})\n"
    )
    print(f"{'idx':>4}  {'host API':<20} {'in':>3} {'default Hz':>10}  name")
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] < 1:
            continue
        api = hostapis[dev["hostapi"]]["name"]
        mark = " <== configured" if idx == audio.input_device else ""
        print(
            f"{idx:>4}  {api:<20} {dev['max_input_channels']:>3} "
            f"{int(dev['default_samplerate']):>10}  {dev['name']}{mark}"
        )
    try:
        info = describe_device(audio, sd)
        print(
            f"\nOK    device {info['index']} accepts {audio.sample_rate} Hz mono int16 via "
            f"{info['hostapi']}"
        )
    except AudioDeviceError as exc:
        print(f"\nFAIL  {exc}")


def record(settings, seconds: float) -> int:
    audio, vad_cfg = settings.voice.audio, settings.voice.vad
    source = SoundDeviceSource(audio)
    vad = WebRtcVad(vad_cfg, audio)
    capture = VoiceCapture(source, vad, TurnDetector(vad_cfg, audio))
    expected = int(seconds * 1000 / audio.frame_ms)
    print(
        f"Recording {seconds:g} s from device {audio.input_device} via {audio.host_api}. "
        "Speak a few sentences with pauses...\n"
    )
    print(f"{'sec':>4} {'frames':>7} {'peak dBFS':>10} {'speech %':>9}  turn")

    utterances = []
    try:
        source.start()
    except AudioDeviceError as exc:
        print(f"FAIL  {exc}")
        return 1
    try:
        end = time.monotonic() + seconds
        second, n, speech, peak = 1, 0, 0, -120.0
        next_tick = time.monotonic() + 1
        while time.monotonic() < end:
            frame = source.read(0.1)
            if frame is not None:
                n += 1
                peak = max(peak, dbfs(frame))
                before = capture.stats.speech_frames
                utt = capture.process(frame)
                speech += capture.stats.speech_frames - before
                if utt is not None:
                    utterances.append(utt)
            if time.monotonic() >= next_tick:
                pct = 100 * speech / max(n, 1)
                turn = "speaking" if capture.detector.in_turn else ""
                print(f"{second:>4} {n:>7} {peak:>10.1f} {pct:>8.0f}%  {turn}")
                second, n, speech, peak = second + 1, 0, 0, -120.0
                next_tick += 1
        tail = capture.detector.flush()
        if tail is not None and hasattr(tail, "pcm"):
            utterances.append(tail)
    finally:
        source.stop()

    got = capture.stats.frames
    print(
        f"\nframes: {got}/{expected} expected, dropped: {source.dropped}, "
        f"overflows: {source.overflows}"
    )
    for i, u in enumerate(utterances, 1):
        print(f"utterance {i}: {u.duration_ms} ms ({u.end_reason})")
    if not utterances:
        print("no utterances detected (check mic level / vad.aggressiveness)")

    ok = got >= 0.9 * expected and source.dropped == 0
    print("\nOK    capture looks healthy" if ok else "\nFAIL  frames missing or dropped")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--list", action="store_true", help="list devices, don't record")
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()

    settings = load_config(args.config_dir)
    try:
        sd = load_sounddevice()
    except AudioDeviceError as exc:
        print(f"FAIL  {exc}")
        return 1
    if args.list:
        list_devices(sd, settings.voice.audio)
        return 0
    return record(settings, args.seconds)


if __name__ == "__main__":
    raise SystemExit(main())
