import sys
from types import SimpleNamespace

import pytest
from voice_fakes import frame

from aegis.models.config import SttConfig
from aegis.ui.voice.stt import FasterWhisperSTT, SttError, pcm_to_float
from aegis.ui.voice.turn import Utterance


def utt(pcm=None, rate=16000):
    pcm = pcm if pcm is not None else frame(100) * 3
    return Utterance(pcm=pcm, sample_rate=rate, duration_ms=90, end_reason="silence")


class FakeWhisper:
    def __init__(self, texts=(" Hello", " world. "), fail=None):
        self.texts = texts
        self.fail = fail
        self.kwargs = None
        self.audio = None

    def transcribe(self, audio, **kwargs):
        if self.fail:
            raise self.fail
        self.audio, self.kwargs = audio, kwargs
        segs = (SimpleNamespace(text=t) for t in self.texts)  # generator, like the real one
        return segs, SimpleNamespace(language="en")


def test_transcribe_joins_segments_and_passes_config():
    model = FakeWhisper()
    stt = FasterWhisperSTT(SttConfig(language="de", beam_size=3), model=model)
    result = stt.transcribe(utt())
    assert result.text == "Hello world." and result.language == "en"
    assert model.kwargs == {"language": "de", "beam_size": 3, "vad_filter": False}
    assert len(model.audio) == 480 * 3


def test_pcm_to_float_scales_to_unit_range():
    import struct

    samples = list(pcm_to_float(struct.pack("<3h", 0, 16384, -32768)))
    assert samples == [0.0, 0.5, -1.0]


def test_wrong_sample_rate_rejected():
    with pytest.raises(SttError, match="16000"):
        FasterWhisperSTT(SttConfig(), model=FakeWhisper()).transcribe(utt(rate=48000))


def test_model_failure_wrapped():
    stt = FasterWhisperSTT(SttConfig(), model=FakeWhisper(fail=RuntimeError("oom")))
    with pytest.raises(SttError, match="transcription failed: oom"):
        stt.transcribe(utt())


def test_missing_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(SttError, match="not installed"):
        FasterWhisperSTT(SttConfig())


def test_load_uses_local_files_only_and_explains_missing_model(monkeypatch):
    seen = {}

    def whisper_model(name, **kwargs):
        seen.update(kwargs, name=name)
        raise FileNotFoundError("no snapshot")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=whisper_model))
    with pytest.raises(SttError, match="local_files_only is true"):
        FasterWhisperSTT(SttConfig(model="base"))
    assert seen["local_files_only"] is True and seen["name"] == "base"
    assert seen["compute_type"] == "int8" and seen["device"] == "cpu"
