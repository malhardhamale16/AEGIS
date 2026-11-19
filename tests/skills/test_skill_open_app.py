import pytest

from aegis.models.config import OpenAppSettings
from aegis.models.skill import SkillError
from aegis.skills.open_app import OpenAppInput, OpenAppSkill

SETTINGS = OpenAppSettings(aliases={"Notepad": "notepad.exe", "calculator": "calc.exe"})


@pytest.fixture
def launched():
    return []


@pytest.fixture
def skill(launched):
    return OpenAppSkill(SETTINGS, launcher=launched.append)


def test_launches_alias_case_insensitive(skill, launched):
    out = skill.run(OpenAppInput(app=" NOTEPAD "), dry_run=False)
    assert out.launched and out.target == "notepad.exe"
    assert launched == ["notepad.exe"]


def test_unknown_app_refused_with_allowed_list(skill, launched):
    with pytest.raises(SkillError, match="allowed: calculator, notepad"):
        skill.run(OpenAppInput(app="cmd.exe"), dry_run=False)
    assert launched == []


def test_dry_run_does_not_launch(skill, launched):
    out = skill.run(OpenAppInput(app="calculator"), dry_run=True)
    assert out.launched is False and launched == []


def test_launch_oserror_becomes_skill_error():
    def bad(target):
        raise OSError("not found")

    with pytest.raises(SkillError, match="failed to launch"):
        OpenAppSkill(SETTINGS, launcher=bad).run(OpenAppInput(app="notepad"), dry_run=False)


def test_no_aliases_configured():
    with pytest.raises(SkillError, match="none configured"):
        OpenAppSkill(launcher=print).run(OpenAppInput(app="x"), dry_run=False)
