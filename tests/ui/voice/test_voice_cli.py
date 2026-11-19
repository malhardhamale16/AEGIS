"""`aegis voice` through CliRunner with fake mic/VAD/STT/TTS and a fake LLM."""

import json
import shutil

import yaml
from typer.testing import CliRunner
from voice_fakes import FakePlayer, FakeSTT, FakeTTS, ListSource, ScriptedVad, frame

from aegis.apps.doctor import Status, check_voice_packages
from aegis.ui.cli.app import create_app
from aegis.ui.voice.factory import VoiceComponents, VoiceSetupError
from aegis_fakes import FakeLLM


def plan(response):
    return json.dumps({"steps": [], "response": response})


def make_cfg(tmp_path, repo_configs):
    d = tmp_path / "configs"
    shutil.copytree(repo_configs, d)
    aegis = yaml.safe_load((d / "aegis.yaml").read_text())
    aegis["logging"] = {"level": "WARNING", "console": False, "file": None}
    (d / "aegis.yaml").write_text(yaml.safe_dump(aegis))
    voice = yaml.safe_load((d / "voice.yaml").read_text())
    voice["vad"].update(start_frames=2, end_silence_ms=60, pre_roll_ms=60, min_utterance_ms=60)
    (d / "voice.yaml").write_text(yaml.safe_dump(voice))
    return d


def run_voice(tmp_path, repo_configs, args, *, texts, replies, factory_error=None):
    seen = {}
    parts = None

    def voice_factory(settings, speak):
        nonlocal parts
        seen["speak"] = speak
        if factory_error:
            raise factory_error
        pattern = "sss.." * len(texts)
        src = [frame(i) if c == "s" else frame(0) for i, c in enumerate(pattern, 1)]
        parts = VoiceComponents(
            ListSource(src),
            ScriptedVad(),
            FakeSTT(texts),
            FakeTTS() if speak else None,
            FakePlayer(finish_immediately=True) if speak else None,
        )
        return parts

    llm = FakeLLM([plan(r) for r in replies])
    app = create_app(llm_factory=lambda s: llm, voice_factory=voice_factory)
    cfg = make_cfg(tmp_path, repo_configs)
    result = CliRunner().invoke(app, ["--config-dir", str(cfg), "voice", *args])
    return result, seen, parts


def test_voice_text_only_by_default(tmp_path, repo_configs):
    result, seen, parts = run_voice(
        tmp_path, repo_configs, [], texts=["what time is it"], replies=["It is noon."]
    )
    assert result.exit_code == 0, result.output
    assert seen["speak"] is False and parts.tts is None
    assert "you> what time is it" in result.output
    assert "aegis> It is noon." in result.output
    assert "text replies only" in result.output and "dry-run" in result.output
    assert "utterances=1 replies=1 spoken=0" in result.output


def test_voice_speak_flag_enables_tts(tmp_path, repo_configs):
    result, seen, parts = run_voice(
        tmp_path, repo_configs, ["--speak"], texts=["hello"], replies=["Hi there."]
    )
    assert result.exit_code == 0, result.output
    assert seen["speak"] is True
    assert parts.tts.texts == ["Hi there."]
    assert "spoken=1" in result.output


def test_voice_setup_error_exits_1(tmp_path, repo_configs):
    result, _, _ = run_voice(
        tmp_path,
        repo_configs,
        [],
        texts=[],
        replies=[],
        factory_error=VoiceSetupError("faster-whisper is not installed"),
    )
    assert result.exit_code == 1
    assert "Voice setup failed: faster-whisper is not installed" in result.output


def test_doctor_voice_packages_warns_when_missing():
    check = check_voice_packages(find_spec=lambda name: None if name == "kokoro" else object())
    assert check.status is Status.WARN and "kokoro" in check.detail
    assert check_voice_packages(find_spec=lambda name: object()).status is Status.OK
