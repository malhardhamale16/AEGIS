import pytest
from voice_fakes import frame

from aegis.models.config import AudioConfig, VadConfig
from aegis.ui.voice.vad import WebRtcVad


class FakeWebRtcModule:
    def __init__(self):
        self.calls = []
        self.mode = None
        module = self

        class Vad:
            def __init__(self, mode):
                module.mode = mode

            def is_speech(self, data, rate):
                module.calls.append((len(data), rate))
                return 1

        self.Vad = Vad


def test_passes_frame_and_rate_and_aggressiveness():
    mod = FakeWebRtcModule()
    vad = WebRtcVad(VadConfig(aggressiveness=3), AudioConfig(), module=mod)
    assert vad.is_speech(frame()) is True
    assert mod.mode == 3 and mod.calls == [(960, 16000)]


def test_wrong_frame_length_rejected():
    vad = WebRtcVad(VadConfig(), AudioConfig(), module=FakeWebRtcModule())
    with pytest.raises(ValueError, match="960 bytes"):
        vad.is_speech(b"\x00" * 10)


def test_real_webrtcvad_says_silence_is_not_speech():
    pytest.importorskip("webrtcvad")
    vad = WebRtcVad(VadConfig(), AudioConfig())
    assert vad.is_speech(frame(0)) is False
