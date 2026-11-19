import struct
import sys
from types import SimpleNamespace

import pytest

from aegis.models.config import TtsConfig
from aegis.ui.voice.tts import (
    KOKORO_SAMPLE_RATE,
    KokoroTTS,
    TtsError,
    float_to_int16,
    speakable,
)


class FakePipeline:
    def __init__(self, chunks, fail=None):
        self.chunks = chunks
        self.fail = fail
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        for c in self.chunks:
            if self.fail:
                raise self.fail
            yield c


def test_float_to_int16_clips_and_scales():
    pcm = float_to_int16([0.0, 0.5, -1.0, 2.0, -3.0])
    assert struct.unpack("<5h", pcm) == (0, 16383, -32767, 32767, -32767)


def test_synthesize_streams_chunks_with_config():
    pipe = FakePipeline([("a", "a", [0.0, 1.0]), SimpleNamespace(audio=[0.5]), ("b", "b", None)])
    tts = KokoroTTS(TtsConfig(voice="bf_emma", speed=1.2), pipeline=pipe)
    chunks = list(tts.synthesize("Hello."))
    assert [len(c.pcm) for c in chunks] == [4, 2]
    assert all(c.sample_rate == KOKORO_SAMPLE_RATE for c in chunks)
    assert pipe.calls == [("Hello.", "bf_emma", 1.2)]


def test_synthesis_is_lazy():
    pipe = FakePipeline([("a", "a", [0.0])])
    KokoroTTS(TtsConfig(), pipeline=pipe).synthesize("x")
    assert pipe.calls == []


def test_pipeline_error_wrapped():
    tts = KokoroTTS(TtsConfig(), pipeline=FakePipeline([1], fail=RuntimeError("bad voice")))
    with pytest.raises(TtsError, match="bad voice"):
        list(tts.synthesize("x"))


def test_missing_package_and_offline_env(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setitem(sys.modules, "kokoro", None)
    with pytest.raises(TtsError, match="not installed"):
        KokoroTTS(TtsConfig(offline=True))
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"


@pytest.mark.parametrize(
    "raw, spoken",
    [
        ("**Done.** Wrote `a.txt`.", "Done. Wrote a.txt."),
        ("- system_info: done\n- echo: done", "system_info: done echo: done"),
        ("1. first\n2. second", "first second"),
        ("  ", ""),
    ],
)
def test_speakable(raw, spoken):
    assert speakable(raw) == spoken
