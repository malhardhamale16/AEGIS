import pytest
from voice_fakes import FRAME_BYTES, frame

from aegis.models.config import AudioConfig, VadConfig
from aegis.ui.voice.turn import SpeechStarted, TurnDetector, TurnDiscarded, Utterance

# 30 ms frames: start after 3 speech frames, end after 3 silent frames (90 ms),
# cap at 10 frames (300 ms), pre-roll 5 frames (150 ms), minimum 2 frames (60 ms).
VAD = VadConfig(
    start_frames=3,
    end_silence_ms=90,
    max_utterance_seconds=0.3,
    pre_roll_ms=150,
    min_utterance_ms=60,
)


@pytest.fixture
def det():
    return TurnDetector(VAD, AudioConfig())


def feed(det, pattern, start=1):
    """pattern: string of 's' (speech) / '.' (silence). Frame values are unique & non-zero for
    speech, so ordering can be checked. Returns non-None events."""
    events = []
    for i, ch in enumerate(pattern, start):
        speech = ch == "s"
        ev = det.feed(frame(i if speech else 0), speech)
        if ev is not None:
            events.append(ev)
    return events


def test_derived_frame_counts(det):
    assert (det.end_frames, det.max_frames, det.min_frames, det.pre_roll_frames) == (3, 10, 2, 5)


def test_silence_only_never_starts_and_stays_bounded(det):
    assert feed(det, "." * 100) == []
    assert not det.in_turn
    assert det.buffered_frames == 5


def test_isolated_speech_frames_do_not_start(det):
    assert feed(det, "ss.ss.s.") == []
    assert not det.in_turn


def test_start_includes_pre_roll(det):
    events = feed(det, "....sss")
    assert events == [SpeechStarted(pre_roll_ms=60)]  # 2 silent frames kept before speech
    assert det.in_turn and det.buffered_frames == 5


def test_end_on_silence_trims_trailing_silence(det):
    events = feed(det, "....sssss...")
    assert isinstance(events[0], SpeechStarted)
    utt = events[1]
    assert isinstance(utt, Utterance) and utt.end_reason == "silence"
    # 2 pre-roll silence + 5 speech frames; the 3 closing silent frames are trimmed
    assert len(utt.pcm) == 7 * FRAME_BYTES
    assert utt.duration_ms == 210 and utt.sample_rate == 16000
    assert not det.in_turn


def test_pcm_preserves_frame_order(det):
    utt = feed(det, "sss...", start=1)[1]
    assert utt.pcm == frame(1) + frame(2) + frame(3)


def test_short_pause_does_not_end_turn(det):
    events = feed(det, "sss..s..s")  # 9 frames: under the 10-frame cap
    assert [type(e) for e in events] == [SpeechStarted]
    assert det.in_turn


def test_max_length_cuts_turn(det):
    events = feed(det, "s" * 12)
    assert isinstance(events[1], Utterance)
    assert events[1].end_reason == "max_length"
    assert len(events[1].pcm) == 10 * FRAME_BYTES


def test_turn_buffer_is_bounded(det):
    feed(det, "s" * 200)
    assert det.buffered_frames <= det.max_frames


def test_too_short_turn_discarded():
    det = TurnDetector(VAD.model_copy(update={"min_utterance_ms": 300}), AudioConfig())
    events = feed(det, "sss...")
    assert isinstance(events[1], TurnDiscarded) and events[1].duration_ms == 90


def test_flush_ends_open_turn(det):
    feed(det, "ssss")
    utt = det.flush()
    assert isinstance(utt, Utterance) and utt.end_reason == "flush"
    assert det.flush() is None


def test_next_turn_after_end(det):
    events = feed(det, "sss..." + "sss...")
    assert [type(e) for e in events] == [SpeechStarted, Utterance, SpeechStarted, Utterance]


def test_reset(det):
    feed(det, "ssss")
    det.reset()
    assert not det.in_turn and det.buffered_frames == 0


def test_pre_roll_never_smaller_than_start_frames():
    det = TurnDetector(VadConfig(start_frames=4, pre_roll_ms=0), AudioConfig())
    assert det.pre_roll_frames == 4
    assert feed(det, "ssss") == [SpeechStarted(pre_roll_ms=0)]
