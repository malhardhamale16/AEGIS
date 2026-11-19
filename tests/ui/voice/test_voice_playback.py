import threading

from voice_fakes import FakeSoundDevice

from aegis.models.config import TtsConfig
from aegis.ui.voice.playback import SoundDevicePlayer
from aegis.ui.voice.tts import AudioChunk

RATE = 24000
BLOCK_BYTES = RATE * 20 // 1000 * 2  # 20 ms blocks = 960 bytes


def chunk(n_blocks, value=1):
    return AudioChunk(pcm=bytes([value, 0]) * (BLOCK_BYTES // 2) * n_blocks, sample_rate=RATE)


def test_plays_all_chunks_in_blocks_and_drains():
    sd = FakeSoundDevice()
    pb = SoundDevicePlayer(TtsConfig(output_device=3), sd=sd).play([chunk(2), chunk(1, 2)])
    assert pb.wait(2) and not pb.playing and not pb.cancelled and pb.error is None
    stream = sd.streams[0]
    assert stream.kwargs == {"samplerate": RATE, "channels": 1, "dtype": "int16", "device": 3}
    assert len(stream.writes) == 3 and all(len(w) == BLOCK_BYTES for w in stream.writes)
    assert stream.events == ["start", "stop", "close"]


def test_cancel_mid_playback_aborts_and_stops_synthesis():
    sd = FakeSoundDevice()
    pulled = []
    holder = {}
    ready = threading.Event()

    def chunks():
        ready.wait(2)  # the handle exists before the worker touches it
        for i in range(100):
            pulled.append(i)
            yield chunk(5)

    original = sd.RawOutputStream

    def stream_factory(**kw):
        stream = original(**kw)
        stream.on_write = lambda n: holder["pb"].cancel() if n == 2 else None
        return stream

    sd.RawOutputStream = stream_factory
    holder["pb"] = SoundDevicePlayer(TtsConfig(), sd=sd).play(chunks())
    ready.set()
    pb = holder["pb"]
    assert pb.wait(2) and pb.cancelled
    stream = sd.streams[0]
    assert len(stream.writes) == 2
    assert "abort" in stream.events and "stop" not in stream.events
    assert len(pulled) == 1  # no further synthesis after cancel


def test_cancel_before_first_chunk_opens_nothing():
    sd = FakeSoundDevice()
    holder = {}
    ready = threading.Event()

    def slow():
        ready.wait(2)
        holder["pb"].cancel()
        yield chunk(1)

    holder["pb"] = SoundDevicePlayer(TtsConfig(), sd=sd).play(slow())
    ready.set()
    assert holder["pb"].wait(2) and sd.streams == []


def test_synthesis_error_recorded():
    def bad():
        yield chunk(1)
        raise RuntimeError("tts died")

    sd = FakeSoundDevice()
    pb = SoundDevicePlayer(TtsConfig(), sd=sd).play(bad())
    assert pb.wait(2)
    assert isinstance(pb.error, RuntimeError)
    assert sd.streams[0].events[-1] == "close"


def test_empty_input():
    pb = SoundDevicePlayer(TtsConfig(), sd=FakeSoundDevice()).play([])
    assert pb.wait(2) and pb.error is None
