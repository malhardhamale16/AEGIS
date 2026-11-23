"""Path resolution for spoken / LLM-written folder names (no real user folders touched)."""

import pytest

from aegis.models.skill import SkillError
from aegis.skills._paths import known_folders, resolve_user_path
from aegis.skills.file_search import FileSearchInput, FileSearchSkill, normalize_pattern


@pytest.fixture
def folders(tmp_path):
    names = ["desktop", "documents", "downloads", "pictures", "music", "videos"]
    result = {"home": tmp_path}
    for name in names:
        (tmp_path / name.capitalize()).mkdir()
        result[name] = tmp_path / name.capitalize()
    return result


@pytest.mark.parametrize(
    "spoken, folder",
    [
        ("downloads", "downloads"),
        ("Downloads", "downloads"),
        ("my downloads", "downloads"),
        ("the Downloads folder", "downloads"),
        ("download", "downloads"),
        ("my documents", "documents"),
        ("docs", "documents"),
        ("photos", "pictures"),
        ("Desktop\\", "desktop"),
        ("home", "home"),
    ],
)
def test_folder_names(folders, spoken, folder):
    assert resolve_user_path(spoken, folders) == folders[folder]


@pytest.mark.parametrize(
    "hallucinated",
    [
        "C:\\Users\\[username]\\Downloads",
        "C:\\Users\\YourName\\Downloads",
        "C:/Users/<user>/Downloads",
    ],
)
def test_placeholder_user_paths_map_to_real_home(folders, hallucinated):
    assert resolve_user_path(hallucinated, folders) == folders["downloads"]


def test_placeholder_user_path_with_subfolder(folders):
    got = resolve_user_path("C:\\Users\\[username]\\Documents\\taxes", folders)
    assert got == folders["documents"] / "taxes"


def test_relative_paths_go_under_home_or_known_folder(folders):
    assert resolve_user_path("Downloads\\cv", folders) == folders["downloads"] / "cv"
    assert resolve_user_path("projects\\x", folders) == folders["home"] / "projects" / "x"


def test_absolute_existing_path_unchanged(folders, tmp_path):
    target = tmp_path / "Documents"
    assert resolve_user_path(str(target), folders) == target


def test_known_folders_has_home_and_standard_folders():
    folders = known_folders()
    assert {"home", "desktop", "documents", "downloads"} <= set(folders)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("*.pdf", "*.pdf"),
        ("pdf", "*.pdf"),
        (".PDF", "*.pdf"),
        ("resume", "*resume*"),
        ("Resume*.pdf", "resume*.pdf"),
        ("notes.txt", "*notes.txt*"),
    ],
)
def test_normalize_pattern(raw, expected):
    assert normalize_pattern(raw) == expected


def test_file_search_accepts_folder_name_and_bare_word(folders):
    (folders["downloads"] / "Malhar Resume.pdf").write_text("x")
    (folders["downloads"] / "other.txt").write_text("x")
    skill = FileSearchSkill(folders=folders)
    out = skill.run(FileSearchInput(pattern="resume", root="my downloads"), dry_run=False)
    assert [m.rsplit("\\", 1)[-1] for m in out.matches] == ["Malhar Resume.pdf"]
    out = skill.run(
        FileSearchInput(pattern="pdf", root="C:\\Users\\[username]\\Downloads"), dry_run=False
    )
    assert len(out.matches) == 1 and out.pattern == "*.pdf"


def test_file_search_error_lists_known_folders(folders):
    skill = FileSearchSkill(folders=folders)
    with pytest.raises(SkillError, match="Known folders: Home ="):
        skill.run(FileSearchInput(pattern="*", root="Z:\\nope"), dry_run=False)
