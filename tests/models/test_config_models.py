import pytest
from pydantic import ValidationError

from aegis.models.config import (
    AudioConfig,
    LoggingConfig,
    ModelsConfig,
    OllamaConfig,
    RiskLevel,
    Settings,
    VadConfig,
)


def test_defaults_match_windows_audio_policy():
    audio = AudioConfig()
    assert (audio.input_device, audio.host_api, audio.mode) == (1, "MME", "callback")
    assert (audio.sample_rate, audio.channels, audio.frame_ms) == (16000, 1, 30)


@pytest.mark.parametrize("frame_ms", [5, 25, 40])
def test_invalid_frame_ms_rejected(frame_ms):
    with pytest.raises(ValidationError):
        AudioConfig(frame_ms=frame_ms)


def test_stereo_rejected():
    with pytest.raises(ValidationError):
        AudioConfig(channels=2)


def test_queue_must_be_bounded_positive():
    with pytest.raises(ValidationError):
        AudioConfig(queue_max_frames=0)


def test_vad_aggressiveness_range():
    assert VadConfig(aggressiveness=3).aggressiveness == 3
    with pytest.raises(ValidationError):
        VadConfig(aggressiveness=4)


def test_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        ModelsConfig(unknown=1)


def test_ollama_accepts_localhost_variants_and_strips_slash():
    assert OllamaConfig(base_url="http://localhost:11434/").base_url == "http://localhost:11434"
    assert OllamaConfig(base_url="http://127.0.0.1:11434").base_url == "http://127.0.0.1:11434"


def test_ollama_rejects_remote_host():
    with pytest.raises(ValidationError):
        OllamaConfig(base_url="http://10.0.0.5:11434")


def test_logging_level_validated():
    with pytest.raises(ValidationError):
        LoggingConfig(level="LOUD")


def test_risk_levels():
    assert {r.value for r in RiskLevel} == {"safe", "confirm", "blocked"}


def test_settings_defaults_are_dry_run():
    assert Settings().aegis.safety.dry_run is True
