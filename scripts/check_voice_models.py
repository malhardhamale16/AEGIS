"""Opt-in offline check of the voice models. No microphone; speakers only with --play.

Loads Whisper and Kokoro exactly as AEGIS does (offline, local files only), synthesizes a
sentence with Kokoro, then transcribes that audio with Whisper and compares the text.

  python scripts/check_voice_models.py
  python scripts/check_voice_models.py --play     # also play the sentence out loud
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.core.config import load_config  # noqa: E402
from aegis.ui.voice.playback import SoundDevicePlayer  # noqa: E402
from aegis.ui.voice.stt import FasterWhisperSTT, SttError  # noqa: E402
from aegis.ui.voice.tts import KOKORO_SAMPLE_RATE, AudioChunk, KokoroTTS, TtsError  # noqa: E402
from aegis.ui.voice.turn import Utterance  # noqa: E402

SENTENCE = "Hello, I am Aegis. Please open the notepad application."


def resample_to_16k(pcm: bytes, rate: int) -> bytes:
    import numpy as np

    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    n = int(len(x) * 16000 / rate)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return y.astype("<i2").tobytes()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--text", default=SENTENCE)
    args = parser.parse_args()
    v = load_config(args.config_dir).voice

    try:
        t = time.perf_counter()
        tts = KokoroTTS(v.tts)
        print(f"OK    Kokoro loaded offline ({time.perf_counter() - t:.1f} s)")
        t = time.perf_counter()
        chunks = list(tts.synthesize(args.text))
        pcm = b"".join(c.pcm for c in chunks)
        secs = len(pcm) / 2 / KOKORO_SAMPLE_RATE
        print(f"OK    synthesized {secs:.1f} s of audio in {time.perf_counter() - t:.1f} s")
    except TtsError as exc:
        print(f"FAIL  TTS: {exc}")
        return 1

    if args.play:
        SoundDevicePlayer(v.tts).play([AudioChunk(pcm, KOKORO_SAMPLE_RATE)]).wait()
        print("OK    played")

    try:
        t = time.perf_counter()
        stt = FasterWhisperSTT(v.stt)
        print(f"OK    Whisper {v.stt.model} loaded offline ({time.perf_counter() - t:.1f} s)")
        audio = resample_to_16k(pcm, KOKORO_SAMPLE_RATE)
        utt = Utterance(audio, 16000, int(secs * 1000), "flush")
        t = time.perf_counter()
        text = stt.transcribe(utt).text
        print(f"OK    transcribed in {time.perf_counter() - t:.1f} s: {text!r}")
    except SttError as exc:
        print(f"FAIL  STT: {exc}")
        return 1

    expected, got = set(words(args.text)), set(words(text))
    overlap = len(expected & got) / len(expected)
    print(f"{'OK  ' if overlap >= 0.7 else 'FAIL'}  word overlap {overlap:.0%}")
    return 0 if overlap >= 0.7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
