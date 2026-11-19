import threading
import time

from voice_fakes import ListSource, ScriptedVad, frame

from aegis.core.events import EventBus
from aegis.models.config import AudioConfig, VadConfig
from aegis.ui.voice.capture import (
    TOPIC_DISCARDED,
    TOPIC_SPEECH_STARTED,
    TOPIC_UTTERANCE,
    VoiceCapture,
)
from aegis.ui.voice.turn import TurnDetector

VAD = VadConfig(start_frames=2, end_silence_ms=60, pre_roll_ms=60, min_utterance_ms=60)


def frames(pattern):
    return [frame(i) if ch == "s" else frame(0) for i, ch in enumerate(pattern, 1)]


def make(pattern, bus=None, vad_cfg=VAD, **src):
    return VoiceCapture(
        ListSource(frames(pattern), **src),
        ScriptedVad(),
        TurnDetector(vad_cfg, AudioConfig()),
        bus=bus,
    )


def test_yields_each_utterance():
    cap = make("..sss..." + "..ssss..")
    utts = list(cap.utterances())
    assert [u.end_reason for u in utts] == ["silence", "silence"]
    assert cap.stats.utterances == 2
    assert cap.stats.frames == 16 and cap.stats.speech_frames == 7


def test_open_turn_flushed_when_source_ends():
    utts = list(make("..sss").utterances())
    assert len(utts) == 1 and utts[0].end_reason == "flush"


def test_events_published_without_audio_payload():
    bus = EventBus()
    seen = []
    bus.subscribe("*", lambda e: seen.append((e.topic, e.payload)))
    list(make("sss..", bus=bus).utterances())
    topics = [t for t, _ in seen]
    assert topics == [TOPIC_SPEECH_STARTED, TOPIC_UTTERANCE]
    assert set(seen[1][1]) == {"duration_ms", "end_reason"}


def test_discarded_turn_counted_and_published():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC_DISCARDED, lambda e: seen.append(e.payload))
    cap = make("ss..", bus=bus, vad_cfg=VAD.model_copy(update={"min_utterance_ms": 300}))
    assert list(cap.utterances()) == []
    assert cap.stats.discarded == 1 and seen == [{"duration_ms": 60}]


def test_stop_event_ends_iteration():
    stop = threading.Event()
    stop.set()
    assert list(make("sss...", stay_active=True).utterances(stop)) == []


def test_deadline_ends_iteration_on_live_source():
    cap = make("", stay_active=True)
    start = time.monotonic()
    assert list(cap.utterances(poll_timeout=0.01, deadline=start + 0.05)) == []
    assert time.monotonic() - start < 1


def test_listen_once_returns_first_utterance():
    utt = make("sss..." + "ssss...").listen_once(timeout_s=5)
    assert utt is not None and utt.pcm.startswith(frame(1))


def test_listen_once_times_out():
    assert make("....", stay_active=True).listen_once(timeout_s=0.05, poll_timeout=0.01) is None
