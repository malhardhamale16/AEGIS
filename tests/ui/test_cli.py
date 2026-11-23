"""CLI tests through Typer's CliRunner. Fake LLM, temp configs, no Ollama."""

import json
import shutil

import pytest
import yaml
from typer.testing import CliRunner

from aegis.models.llm import HealthStatus
from aegis.ui.cli.app import create_app
from aegis_fakes import FakeLLM


def plan(*steps, response=None):
    return json.dumps(
        {"steps": [{"skill": s, "args": a, "reason": ""} for s, a in steps], "response": response}
    )


class FakeOllama(FakeLLM):
    def __init__(self, responses=(), *, healthy=True, models=("llama3.2:3b",)):
        super().__init__(responses)
        self.healthy = healthy
        self.models = list(models)
        self.closed = False

    def health(self):
        if self.healthy:
            return HealthStatus(ok=True, version="0.9.0", latency_ms=1.0)
        return HealthStatus(ok=False, error="unreachable: refused")

    def list_models(self):
        return self.models

    def close(self):
        self.closed = True


@pytest.fixture
def cfg(tmp_path, repo_configs):
    """Copy of the repo configs with logging silenced and writes confined to tmp."""
    d = tmp_path / "configs"
    shutil.copytree(repo_configs, d)
    aegis = yaml.safe_load((d / "aegis.yaml").read_text())
    aegis["logging"] = {"level": "WARNING", "console": False, "file": None}
    (d / "aegis.yaml").write_text(yaml.safe_dump(aegis))
    skills = yaml.safe_load((d / "skills.yaml").read_text())
    skills["write_file"]["allowed_roots"] = [str(tmp_path / "out")]
    (d / "skills.yaml").write_text(yaml.safe_dump(skills))
    return d


@pytest.fixture
def cli(cfg):
    runner = CliRunner()

    def invoke(args, fake=None, input=None):
        fake = fake if fake is not None else FakeOllama()
        app = create_app(llm_factory=lambda settings: fake)
        result = runner.invoke(app, ["--config-dir", str(cfg), *args], input=input)
        return result, fake

    return invoke


# ------------------------------------------------------------------------ basics


def test_no_args_shows_help(cfg):
    result = CliRunner().invoke(create_app(), [])
    assert "chat" in result.output and "doctor" in result.output


def test_bad_config_exits_2(tmp_path):
    result = CliRunner().invoke(create_app(), ["--config-dir", str(tmp_path), "skills", "list"])
    assert result.exit_code == 2
    assert "not found" in result.output


# ------------------------------------------------------------------------ skills


def test_skills_list_table(cli):
    result, _ = cli(["skills", "list"])
    assert result.exit_code == 0
    for name in ("system_info", "file_search", "write_file"):
        assert name in result.output
    assert "confirm" in result.output


def test_skills_list_json(cli):
    result, _ = cli(["skills", "list", "--json"])
    data = json.loads(result.output)
    assert {d["name"]: d["risk"] for d in data}["write_file"] == "confirm"
    assert len(data) == 7


def test_skills_show(cli):
    result, _ = cli(["skills", "show", "web_open"])
    assert result.exit_code == 0
    assert json.loads(result.output)["input_schema"]["required"] == ["url"]


def test_skills_show_unknown(cli):
    result, _ = cli(["skills", "show", "nope"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------- run


def test_run_direct_answer(cli):
    result, fake = cli(["run", "hello"], FakeOllama([plan(response="Hi!")]))
    assert result.exit_code == 0
    assert "aegis> Hi!" in result.output
    assert fake.closed


def test_run_skill_and_summary(cli):
    fake = FakeOllama([plan(("system_info", {})), "Your PC runs Windows."])
    result, _ = cli(["run", "what OS am I on"], fake)
    assert result.exit_code == 0
    assert "system_info" in result.output and "done" in result.output
    assert "Your PC runs Windows." in result.output


def test_run_defaults_to_dry_run(cli, tmp_path):
    fake = FakeOllama([plan(("write_file", {"path": "a.txt", "content": "x"})), "Simulated."])
    result, _ = cli(["run", "write a file"], fake)
    assert result.exit_code == 0
    assert "dry-run" in result.output and "simulated" in result.output
    assert not (tmp_path / "out" / "a.txt").exists()


def test_run_execute_confirmed_writes(cli, tmp_path):
    fake = FakeOllama([plan(("write_file", {"path": "a.txt", "content": "x"})), "Wrote it."])
    result, _ = cli(["run", "write a file", "--execute"], fake, input="y\n")
    assert result.exit_code == 0, result.output
    assert "Confirmation required" in result.output
    assert (tmp_path / "out" / "a.txt").read_text() == "x"


def test_run_execute_declined_does_not_write(cli, tmp_path):
    fake = FakeOllama([plan(("write_file", {"path": "a.txt", "content": "x"})), "Declined."])
    result, _ = cli(["run", "write a file", "--execute"], fake, input="n\n")
    assert result.exit_code == 1
    assert not (tmp_path / "out" / "a.txt").exists()


def test_run_execute_no_input_denies(cli, tmp_path):
    fake = FakeOllama([plan(("write_file", {"path": "a.txt", "content": "x"})), "Denied."])
    result, _ = cli(["run", "write", "--execute"], fake, input="")
    assert result.exit_code == 1
    assert not (tmp_path / "out" / "a.txt").exists()


def test_run_json_output(cli):
    result, _ = cli(["run", "hi", "--json"], FakeOllama([plan(response="Hello")]))
    assert result.exit_code == 0
    assert json.loads(result.stdout)["text"] == "Hello"


def test_run_ollama_down_exits_1(cli):
    from aegis.core.llm import LLMUnavailableError

    result, _ = cli(["run", "hi"], FakeOllama([LLMUnavailableError("refused")]))
    assert result.exit_code == 1
    assert "can't reach the local model" in result.output


def test_run_rich_markup_in_reply_is_not_interpreted(cli):
    result, _ = cli(["run", "x"], FakeOllama([plan(response="[red]literal[/red]")]))
    assert "[red]literal[/red]" in result.output


# -------------------------------------------------------------------------- chat


def test_chat_session_with_commands(cli):
    fake = FakeOllama([plan(response="one"), plan(response="two")])
    result, _ = cli(["chat"], fake, input="first\n/help\n\n/reset\nsecond\n/exit\n")
    assert result.exit_code == 0
    out = result.output
    assert "aegis> one" in out and "aegis> two" in out
    assert "History cleared." in out and "Bye." in out
    # after /reset the second planner call carries no history
    assert [m.content for m in fake.calls[1]["messages"][1:]] == ["second"]


def test_chat_ends_on_eof(cli):
    result, fake = cli(["chat"], FakeOllama([plan(response="ok")]), input="hi\n")
    assert result.exit_code == 0 and "aegis> ok" in result.output and fake.closed


# ------------------------------------------------------------------------ doctor


def test_doctor_all_ok(cli):
    result, _ = cli(["doctor", "--json"])
    assert result.exit_code == 0, result.output
    checks = {c["name"]: c["status"] for c in json.loads(result.output)}
    assert checks["ollama"] == "ok"
    assert checks["model:planner"] == "ok"
    assert checks["skills"] == "ok"


def test_doctor_ollama_down_fails(cli):
    result, _ = cli(["doctor"], FakeOllama(healthy=False))
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_doctor_missing_model_fails(cli):
    result, _ = cli(["doctor", "--json"], FakeOllama(models=[]))
    assert result.exit_code == 1
    checks = {c["name"]: c for c in json.loads(result.output)}
    assert "ollama pull llama3.2:3b" in checks["model:planner"]["detail"]
