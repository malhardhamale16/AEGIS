"""Shared fixtures and fakes. Nothing here touches the OS, Ollama, or audio devices."""

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from aegis.models.skill import RiskLevel, Skill
from aegis_fakes import FakeLLM

REPO_CONFIGS = Path(__file__).resolve().parent.parent / "configs"
CONFIG_FILES = ("aegis.yaml", "models.yaml", "skills.yaml", "voice.yaml")


# --------------------------------------------------------------------------- config


@pytest.fixture
def repo_configs() -> Path:
    return REPO_CONFIGS


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A temp config dir where every file is an empty mapping (all defaults)."""
    for name in CONFIG_FILES:
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def write_config(config_dir: Path):
    def _write(name: str, data: dict) -> Path:
        path = config_dir / name
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return config_dir

    return _write


# --------------------------------------------------------------------------- fake LLM


@pytest.fixture
def fake_llm_factory():
    return FakeLLM


# ------------------------------------------------------------------------ fake skills


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    text: str


class EchoSkill(Skill):
    name = "echo"
    description = "Return the input text."
    risk = RiskLevel.SAFE
    input_model = EchoIn
    output_model = EchoOut

    def run(self, data: EchoIn, *, dry_run: bool) -> EchoOut:
        return EchoOut(text=data.text)


class WriteIn(BaseModel):
    path: str


class WriteOut(BaseModel):
    path: str
    written: bool


class FakeWriteSkill(Skill):
    """Records calls instead of writing anything."""

    name = "fake_write"
    description = "Pretend to write a file."
    risk = RiskLevel.CONFIRM
    input_model = WriteIn
    output_model = WriteOut

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def run(self, data: WriteIn, *, dry_run: bool) -> WriteOut:
        self.calls.append((data.path, dry_run))
        return WriteOut(path=data.path, written=not dry_run)


class DangerSkill(Skill):
    name = "danger"
    description = "Never allowed."
    risk = RiskLevel.BLOCKED
    input_model = EchoIn
    output_model = EchoOut

    def __init__(self) -> None:
        self.called = False

    def run(self, data: EchoIn, *, dry_run: bool) -> EchoOut:
        self.called = True
        return EchoOut(text="boom")


class CrashSkill(Skill):
    name = "crash"
    description = "Raises."
    risk = RiskLevel.SAFE
    input_model = EchoIn
    output_model = EchoOut

    def run(self, data: EchoIn, *, dry_run: bool) -> EchoOut:
        raise RuntimeError("kaput")


@pytest.fixture
def echo() -> EchoSkill:
    return EchoSkill()


@pytest.fixture
def fake_write() -> FakeWriteSkill:
    return FakeWriteSkill()


@pytest.fixture
def danger() -> DangerSkill:
    return DangerSkill()


@pytest.fixture
def crash() -> CrashSkill:
    return CrashSkill()
