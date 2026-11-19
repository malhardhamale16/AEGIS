"""Voice pipeline: mic -> VAD -> turn detection -> (Phase 7: STT -> agent -> TTS)."""

from aegis.ui.voice.audio import AudioDeviceError, AudioSource, SoundDeviceSource
from aegis.ui.voice.capture import CaptureStats, VoiceCapture
from aegis.ui.voice.frames import BoundedFrameQueue, Reframer
from aegis.ui.voice.playback import Playback, SoundDevicePlayer
from aegis.ui.voice.session import SessionStats, VoiceSession
from aegis.ui.voice.stt import FasterWhisperSTT, SttError, Transcript
from aegis.ui.voice.tts import AudioChunk, KokoroTTS, TtsError
from aegis.ui.voice.turn import SpeechStarted, TurnDetector, TurnDiscarded, Utterance
from aegis.ui.voice.vad import Vad, WebRtcVad

__all__ = [
    "AudioChunk",
    "AudioDeviceError",
    "AudioSource",
    "BoundedFrameQueue",
    "CaptureStats",
    "FasterWhisperSTT",
    "KokoroTTS",
    "Playback",
    "Reframer",
    "SessionStats",
    "SoundDevicePlayer",
    "SoundDeviceSource",
    "SpeechStarted",
    "SttError",
    "Transcript",
    "TtsError",
    "TurnDetector",
    "TurnDiscarded",
    "Utterance",
    "Vad",
    "VoiceCapture",
    "VoiceSession",
    "WebRtcVad",
]
