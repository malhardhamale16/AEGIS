from voice_fakes import FakeAgent, FakePlayer, FakeSTT, FakeTTS, ListSource, ScriptedVad, frame

from aegis.models.config import AudioConfig, BargeInConfig, VadConfig
from aegis.ui.voice.capture import VoiceCapture
from aegis.ui.voice.session import VoiceSession
from aegis.ui.voice.turn import TurnDetector

# 30 ms frames: turn opens after 2 speech frames, closes after 2 silent frames.
VAD = VadConfig(start_frames=2, end_silence_ms=60, pre_roll_ms=60, min_utterance_ms=60)


def frames(pattern):
    return [frame(i) if ch == "s" else frame(0) for i, ch in enumerate(pattern, 1)]


def session(pattern, texts, *, speak=True, barge=True, min_speech_ms=90, player=None, **kw):
    source = ListSource(frames(pattern))
    capture = VoiceCapture(source, ScriptedVad(), TurnDetector(VAD, AudioConfig()))
    events = []
    s = VoiceSession(
        capture,
        FakeSTT(texts),
        kw.pop("agent", FakeAgent()),
        barge_in=BargeInConfig(enabled=barge, min_speech_ms=min_speech_ms),
        frame_ms=30,
        tts=FakeTTS() if speak else None,
        player=(player or FakePlayer()) if speak else None,
        on_event=lambda kind, text: events.append((kind, text)),
        **kw,
    )
    return s, events, source


def test_utterance_to_reply_to_speech():
    s, events, source = session("sss..", ["open notepad"], dry_run=True)
    stats = s.run()
    assert events == [("you", "open notepad"), ("aegis", "echo: open notepad")]
    assert s.agent.calls == [("open notepad", True)]
    assert s.tts.texts == ["echo: open notepad"]
    assert (stats.utterances, stats.replies, stats.spoken) == (1, 1, 1)
    assert source.started is False  # stopped at the end


def test_text_only_mode_never_synthesizes():
    s, events, _ = session("sss..", ["hi"], speak=False)
    stats = s.run()
    assert ("aegis", "echo: hi") in events and stats.spoken == 0


def test_reply_is_cleaned_before_speaking():
    s, _, _ = session("sss..", ["x"], agent=FakeAgent(["**Done.**\n- step: ok"]))
    s.run()
    assert s.tts.texts == ["Done. step: ok"]


def test_empty_transcript_is_skipped():
    s, events, _ = session("sss..", ["   "])
    stats = s.run()
    assert events == [] and stats.empty_transcripts == 1 and s.agent.calls == []


def test_stt_error_reported_and_loop_continues():
    s, events, _ = session("sss.." + "sss..", [RuntimeError("decode"), "second"])
    stats = s.run()
    assert events[0] == ("error", "decode") and ("you", "second") in events
    assert stats.errors == 1 and stats.replies == 1


def test_sustained_speech_during_playback_barges_in():
    # first turn -> reply starts playing; then 4 speech frames while "speaking"
    s, events, _ = session("sss.." + "ssss..", ["first", "second"])
    stats = s.run()
    first_playback = s.player.handles[0]
    assert first_playback.cancelled
    assert stats.barge_ins == 1 and ("status", "interrupted") in events
    assert ("you", "second") in events  # the interrupting speech became the next turn


def test_short_blip_during_playback_does_not_barge_in():
    # 2 speech frames < 3 needed (90 ms) -> no interruption; blip still opens a short turn
    s, _, _ = session("sss.." + "ss.", ["first", "blip"], min_speech_ms=90)
    s.run()
    assert s.stats.barge_ins == 0


def test_new_reply_cancels_previous_playback():
    s, _, _ = session("sss.." + "sss..", ["a", "b"], min_speech_ms=10_000)
    s.run()
    assert s.player.handles[0].cancelled and len(s.player.handles) == 2


def test_half_duplex_waits_and_discards_mic_audio():
    s, _, source = session("sss..", ["hi"], barge=False)
    s.run()
    assert s.player.handles[0].waited
    assert source.clears == 1
    assert s.stats.barge_ins == 0


def test_no_barge_in_when_disabled_even_with_long_speech():
    s, _, _ = session("sss.." + "ssssssss..", ["a", "b"], barge=False)
    s.run()
    assert s.stats.barge_ins == 0


def test_playback_cancelled_when_session_ends():
    s, _, _ = session("sss..", ["hi"])
    s.run()
    assert s.player.handles[-1].cancelled


def test_tts_without_player_rejected():
    import pytest

    capture = VoiceCapture(ListSource([]), ScriptedVad(), TurnDetector(VAD, AudioConfig()))
    with pytest.raises(ValueError):
        VoiceSession(
            capture, FakeSTT([]), FakeAgent(), barge_in=BargeInConfig(), frame_ms=30, tts=FakeTTS()
        )
