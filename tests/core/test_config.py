from pathlib import Path

import pytest

from aegis.core.config import CONFIG_DIR_ENV, ConfigError, load_config, resolve_config_dir
from aegis.models.config import RiskLevel


def test_repo_configs_load_and_validate(repo_configs):
    settings = load_config(repo_configs)
    assert settings.aegis.safety.dry_run is True
    assert settings.models.ollama.base_url == "http://127.0.0.1:11434"
    assert settings.voice.audio.input_device == 1
    assert settings.voice.audio.host_api == "MME"
    assert settings.voice.audio.mode == "callback"
    assert settings.voice.audio.sample_rate == 16000
    assert settings.voice.audio.channels == 1
    assert settings.voice.audio.frame_ms == 30


def test_empty_files_yield_defaults(config_dir):
    settings = load_config(config_dir)
    assert settings.aegis.safety.dry_run is True
    assert settings.voice.audio.frame_samples == 480


def test_values_are_overridable(write_config):
    cfg = write_config("voice.yaml", {"audio": {"input_device": 3, "host_api": "WASAPI"}})
    settings = load_config(cfg)
    assert settings.voice.audio.input_device == 3
    assert settings.voice.audio.host_api == "WASAPI"


def test_skill_overrides_parse_risk_enum(write_config):
    cfg = write_config("skills.yaml", {"overrides": {"open_app": {"risk": "confirm"}}})
    assert load_config(cfg).skills.overrides["open_app"].risk is RiskLevel.CONFIRM


def test_missing_file_raises(config_dir):
    (config_dir / "models.yaml").unlink()
    with pytest.raises(ConfigError, match="not found"):
        load_config(config_dir)


def test_missing_directory_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope")


def test_invalid_yaml_raises(config_dir):
    (config_dir / "aegis.yaml").write_text("app: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(config_dir)


def test_non_mapping_top_level_raises(config_dir):
    (config_dir / "aegis.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(config_dir)


def test_unknown_key_rejected(write_config):
    cfg = write_config("aegis.yaml", {"safety": {"dry_runn": False}})
    with pytest.raises(ConfigError, match=r"safety\.dry_runn"):
        load_config(cfg)


def test_wrong_type_reports_file_and_path(write_config):
    cfg = write_config("voice.yaml", {"audio": {"input_device": "one"}})
    with pytest.raises(ConfigError) as exc:
        load_config(cfg)
    assert "voice.yaml" in str(exc.value)
    assert "audio.input_device" in str(exc.value)


def test_non_local_ollama_url_rejected(write_config):
    cfg = write_config("models.yaml", {"ollama": {"base_url": "https://api.example.com"}})
    with pytest.raises(ConfigError, match="local"):
        load_config(cfg)


def test_resolve_dir_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    assert resolve_config_dir() == Path("configs")
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    assert resolve_config_dir() == tmp_path
    assert resolve_config_dir("explicit") == Path("explicit")
