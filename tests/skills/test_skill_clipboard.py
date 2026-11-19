import pytest

from aegis.models.config import ClipboardSettings
from aegis.models.skill import SkillError
from aegis.skills.clipboard import CLIPBOARD_COMMAND, ClipboardReadInput, ClipboardReadSkill


def fake_runner(output):
    calls = []

    def runner(args):
        calls.append(tuple(args))
        return output

    runner.calls = calls
    return runner


def test_reads_and_strips_trailing_newline():
    runner = fake_runner("hello\r\n")
    out = ClipboardReadSkill(runner=runner).run(ClipboardReadInput(), dry_run=False)
    assert out.text == "hello" and out.length == 5 and not out.truncated
    assert runner.calls == [CLIPBOARD_COMMAND]


def test_truncates_to_config_cap():
    skill = ClipboardReadSkill(ClipboardSettings(max_chars=3), runner=fake_runner("abcdef"))
    out = skill.run(ClipboardReadInput(max_chars=100), dry_run=False)
    assert out.text == "abc" and out.length == 6 and out.truncated


def test_empty_clipboard():
    out = ClipboardReadSkill(runner=fake_runner("")).run(ClipboardReadInput(), dry_run=False)
    assert out.text == "" and out.length == 0


def test_runner_failure_propagates():
    def boom(args):
        raise SkillError("powershell exited with 1")

    with pytest.raises(SkillError):
        ClipboardReadSkill(runner=boom).run(ClipboardReadInput(), dry_run=False)
