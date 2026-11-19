import pytest

from aegis.models.config import WriteFileSettings
from aegis.models.skill import RiskLevel, SkillError
from aegis.skills.write_file import WriteFileInput, WriteFileSkill


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "allowed"
    r.mkdir()
    return r


@pytest.fixture
def skill(root):
    return WriteFileSkill(WriteFileSettings(allowed_roots=[root], max_bytes=100))


def run(skill, dry_run=False, **kw):
    return skill.run(WriteFileInput(**kw), dry_run=dry_run)


def test_is_confirm_level():
    assert WriteFileSkill.risk is RiskLevel.CONFIRM


def test_dry_run_writes_nothing(skill, root):
    out = run(skill, dry_run=True, path="note.txt", content="hi")
    assert out.dry_run and not out.written and out.bytes == 2
    assert not (root / "note.txt").exists()


def test_writes_relative_path_under_first_root(skill, root):
    out = run(skill, path="sub/note.txt", content="héllo")
    assert out.written and not out.existed
    assert (root / "sub" / "note.txt").read_text(encoding="utf-8") == "héllo"


def test_refuses_overwrite_by_default(skill, root):
    (root / "a.txt").write_text("old")
    with pytest.raises(SkillError, match="already exists"):
        run(skill, path="a.txt", content="new")
    assert (root / "a.txt").read_text() == "old"


def test_overwrite_when_asked(skill, root):
    (root / "a.txt").write_text("old")
    out = run(skill, path="a.txt", content="new", overwrite=True)
    assert out.existed and (root / "a.txt").read_text() == "new"


@pytest.mark.parametrize("path", ["../escape.txt", "sub/../../escape.txt"])
def test_traversal_blocked(skill, root, path):
    with pytest.raises(SkillError, match="outside the allowed"):
        run(skill, path=path, content="x")
    assert not (root.parent / "escape.txt").exists()


def test_absolute_path_outside_root_blocked(skill, tmp_path):
    with pytest.raises(SkillError, match="outside the allowed"):
        run(skill, path=str(tmp_path / "other.txt"), content="x")


def test_root_itself_rejected(skill, root):
    with pytest.raises(SkillError, match="not an allowed root"):
        run(skill, path=str(root), content="x")


def test_size_limit(skill):
    with pytest.raises(SkillError, match="limit"):
        run(skill, path="big.txt", content="x" * 101)


def test_directory_target_rejected(skill, root):
    (root / "d").mkdir()
    with pytest.raises(SkillError, match="directory"):
        run(skill, path="d", content="x")


def test_no_roots_configured():
    with pytest.raises(SkillError, match="no allowed_roots"):
        run(WriteFileSkill(WriteFileSettings(allowed_roots=[])), path="a", content="x")
