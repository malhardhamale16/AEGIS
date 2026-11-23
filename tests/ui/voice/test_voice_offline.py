import os
import sys
from types import SimpleNamespace

import pytest

from aegis.models.config import SttConfig
from aegis.ui.voice.offline import force_hf_offline
from aegis.ui.voice.stt import FasterWhisperSTT


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)


def test_sets_env(clean_env):
    force_hf_offline()
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_flips_constant_when_huggingface_hub_already_imported(clean_env, monkeypatch):
    # huggingface_hub reads the env var only at import; a late env change alone is ignored.
    fake_constants = SimpleNamespace(HF_HUB_OFFLINE=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", fake_constants)
    force_hf_offline()
    assert fake_constants.HF_HUB_OFFLINE is True


def test_stt_goes_offline_before_importing_faster_whisper(clean_env, monkeypatch):
    seen = {}

    def whisper_model(name, **kwargs):
        seen["offline_at_load"] = os.environ.get("HF_HUB_OFFLINE")
        return object()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=whisper_model))
    FasterWhisperSTT(SttConfig(local_files_only=True))
    assert seen["offline_at_load"] == "1"
