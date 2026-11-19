import pytest
from voice_fakes import FRAME_BYTES, FakeSoundDevice, frame

from aegis.models.config import AudioConfig
from aegis.ui.voice.audio import AudioDeviceError, SoundDeviceSource, describe_device, frame_bytes


def test_frame_bytes_for_default_config():
    assert frame_bytes(AudioConfig()) == FRAME_BYTES == 960


def test_describe_device_ok():
    info = describe_device(AudioConfig(), FakeSoundDevice())
    assert info == {"index": 1, "name": "Microphone (Fake)", "hostapi": "MME"}


def test_wrong_host_api_is_an_error_not_a_switch():
    with pytest.raises(AudioDeviceError, match="uses host API 'Windows WASAPI'.*'MME'"):
        describe_device(AudioConfig(), FakeSoundDevice(hostapi="Windows WASAPI"))


def test_wasapi_accepted_when_configured():
    cfg = AudioConfig(host_api="WASAPI")
    assert describe_device(cfg, FakeSoundDevice(hostapi="Windows WASAPI"))["hostapi"]


def test_unknown_device():
    with pytest.raises(AudioDeviceError, match="not found"):
        describe_device(AudioConfig(input_device=7), FakeSoundDevice())


def test_output_only_device():
    with pytest.raises(AudioDeviceError, match="no input"):
        describe_device(AudioConfig(), FakeSoundDevice(max_input_channels=0))


def test_unsupported_format():
    with pytest.raises(AudioDeviceError, match="rejects 16000 Hz"):
        describe_device(AudioConfig(), FakeSoundDevice(reject="Invalid sample rate"))


def test_start_opens_callback_stream_with_config():
    sd = FakeSoundDevice()
    src = SoundDeviceSource(AudioConfig(), sd=sd)
    src.start()
    kw = sd.streams[0].kwargs
    assert kw["device"] == 1 and kw["samplerate"] == 16000 and kw["channels"] == 1
    assert kw["dtype"] == "int16" and kw["blocksize"] == 480 and callable(kw["callback"])
    assert src.active and src.device["hostapi"] == "MME"
    src.start()  # idempotent
    assert len(sd.streams) == 1


def test_start_fails_on_bad_device_without_opening_stream():
    sd = FakeSoundDevice(hostapi="Windows DirectSound")
    with pytest.raises(AudioDeviceError):
        SoundDeviceSource(AudioConfig(), sd=sd).start()
    assert sd.streams == []


def test_callback_enqueues_fixed_frames():
    sd = FakeSoundDevice()
    with SoundDeviceSource(AudioConfig(), sd=sd) as src:
        stream = sd.streams[0]
        stream.push(frame(1))
        stream.push(frame(2) + frame(3)[: FRAME_BYTES // 2])  # 1.5 frames
        stream.push(frame(3)[FRAME_BYTES // 2 :])
        assert [src.read(0) for _ in range(3)] == [frame(1), frame(2), frame(3)]
        assert src.read(0) is None
    assert stream.closed and not src.active


def test_overflow_and_drop_counters():
    sd = FakeSoundDevice()
    src = SoundDeviceSource(AudioConfig(queue_max_frames=2), sd=sd)
    src.start()
    for i in range(5):
        sd.streams[0].push(frame(i), overflow=(i == 0))
    assert src.overflows == 1 and src.dropped == 3
    assert src.read(0) == frame(3)
    src.stop()
    src.stop()  # safe twice
