"""Builds the real voice components from settings. Heavy libraries load only here."""

from __future__ import annotations

from dataclasses import dataclass

from aegis.core.events import EventBus
from aegis.models.config import Settings
from aegis.ui.voice.audio import AudioSource, SoundDeviceSource
from aegis.ui.voice.capture import VoiceCapture
from aegis.ui.voice.playback import AudioPlayer, SoundDevicePlayer
from aegis.ui.voice.stt import FasterWhisperSTT, SpeechToText
from aegis.ui.voice.tts import KokoroTTS, TextToSpeech
from aegis.ui.voice.turn import TurnDetector
from aegis.ui.voice.vad import Vad, WebRtcVad


class VoiceSetupError(Exception):
    pass


@dataclass
class VoiceComponents:
    source: AudioSource
    vad: Vad
    stt: SpeechToText
    tts: TextToSpeech | None = None
    player: AudioPlayer | None = None

    def capture(self, settings: Settings, bus: EventBus | None = None) -> VoiceCapture:
        v = settings.voice
        return VoiceCapture(self.source, self.vad, TurnDetector(v.vad, v.audio), bus=bus)


def build_voice(settings: Settings, *, speak: bool) -> VoiceComponents:
    """Real mic/VAD/STT, plus TTS/player only when ``speak`` is true."""
    v = settings.voice
    try:
        vad = WebRtcVad(v.vad, v.audio)
        stt = FasterWhisperSTT(v.stt)
        tts = KokoroTTS(v.tts) if speak else None
    except Exception as exc:
        raise VoiceSetupError(str(exc)) from exc
    player = SoundDevicePlayer(v.tts) if speak else None
    return VoiceComponents(SoundDeviceSource(v.audio), vad, stt, tts, player)
