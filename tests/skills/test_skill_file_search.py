import pytest
from pydantic import ValidationError

from aegis.models.config import FileSearchSettings
from aegis.models.skill import SkillError
from aegis.skills.file_search import FileSearchInput, FileSearchSkill


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "a.PDF").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.pdf").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.pdf").write_text("x")
    return tmp_path


def run(skill, **kw):
    return skill.run(FileSearchInput(**kw), dry_run=False)


def test_case_insensitive_recursive_match_with_excludes(tree):
    out = run(FileSearchSkill(), pattern="*.pdf", root=str(tree))
    names = sorted(p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in out.matches)
    assert names == ["a.PDF", "c.pdf"]
    assert out.truncated is False


def test_default_root_from_settings(tree):
    out = run(FileSearchSkill(FileSearchSettings(default_root=tree)), pattern="b.txt")
    assert len(out.matches) == 1


def test_result_cap_and_truncation(tree):
    skill = FileSearchSkill(FileSearchSettings(max_results=1, exclude_dirs=[]))
    out = run(skill, pattern="*.pdf", root=str(tree), max_results=50)
    assert len(out.matches) == 1 and out.truncated is True


def test_missing_root_raises(tmp_path):
    with pytest.raises(SkillError, match="not a directory"):
        run(FileSearchSkill(), pattern="*", root=str(tmp_path / "nope"))


def test_pattern_with_path_rejected():
    with pytest.raises(ValidationError):
        FileSearchInput(pattern="sub/*.pdf")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        FileSearchInput(pattern="*", recursive=True)
