import pytest

from aegis.models.skill import RiskLevel, SkillError
from aegis.skills.open_path import OpenPathInput, OpenPathSkill


@pytest.fixture
def folders(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    return {"home": tmp_path, "downloads": downloads}


@pytest.fixture
def opened():
    return []


@pytest.fixture
def skill(folders, opened):
    return OpenPathSkill(opener=opened.append, folders=folders)


def run(skill, path, dry_run=False):
    return skill.run(OpenPathInput(path=path), dry_run=dry_run)


def test_is_safe_level():
    assert OpenPathSkill.risk is RiskLevel.SAFE


def test_opens_known_folder_by_name(skill, folders, opened):
    out = run(skill, "my downloads folder")
    assert out.is_folder and out.opened
    assert opened == [folders["downloads"]]


def test_opens_document(skill, folders, opened):
    doc = folders["downloads"] / "Resume.pdf"
    doc.write_text("x")
    out = run(skill, str(doc))
    assert not out.is_folder and opened == [doc]


@pytest.mark.parametrize("name", ["setup.exe", "run.BAT", "x.ps1", "link.lnk", "a.vbs", "s.py"])
def test_refuses_anything_that_can_run_code(skill, folders, opened, name):
    target = folders["downloads"] / name
    target.write_text("x")
    with pytest.raises(SkillError, match="can run code"):
        run(skill, str(target))
    assert opened == []


def test_missing_path(skill, opened):
    with pytest.raises(SkillError, match="does not exist"):
        run(skill, "Z:\\nowhere\\file.pdf")
    assert opened == []


def test_dry_run_does_not_open(skill, opened):
    out = run(skill, "downloads", dry_run=True)
    assert out.opened is False and opened == []


def test_open_failure_becomes_skill_error(folders):
    def boom(path):
        raise OSError("no association")

    with pytest.raises(SkillError, match="could not open"):
        OpenPathSkill(opener=boom, folders=folders).run(
            OpenPathInput(path="downloads"), dry_run=False
        )
