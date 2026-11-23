"""file_search: find files by name pattern. Read-only."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, field_validator

from aegis.models.config import FileSearchSettings
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO
from aegis.skills._paths import describe_folders, known_folders, resolve_user_path

# Bare words that mean "files of this type" ("find a pdf" -> "*.pdf").
_EXTENSION_WORDS = {
    "pdf", "doc", "docx", "txt", "xls", "xlsx", "csv", "ppt", "pptx", "jpg", "jpeg", "png",
    "gif", "mp3", "wav", "mp4", "mkv", "zip", "rar", "py", "json", "yaml", "md",
}  # fmt: skip


def normalize_pattern(pattern: str) -> str:
    """'pdf' -> '*.pdf', '.pdf' -> '*.pdf', 'resume' -> '*resume*'. Globs are kept."""
    p = pattern.strip().lower()
    if any(ch in p for ch in "*?["):
        return p
    if p.lstrip(".") in _EXTENSION_WORDS and "." not in p.lstrip("."):
        return f"*.{p.lstrip('.')}"
    if p.startswith("."):
        return f"*{p}"
    if "." in p:  # looks like a full file name: match it anywhere in the name
        return f"*{p}*"
    return f"*{p}*"


class FileSearchInput(SkillIO):
    pattern: str = Field(
        ...,
        min_length=1,
        description="File name glob. Put name words in it: '*resume*.pdf', '*.pdf', 'budget*'",
    )
    root: str | None = Field(
        None,
        description="Folder to search: a real path or a folder name such as 'Downloads', "
        "'Documents', 'Desktop'. Omit to search the whole home folder.",
    )
    max_results: int | None = Field(None, gt=0)

    @field_validator("pattern")
    @classmethod
    def _name_only(cls, v: str) -> str:
        if "/" in v or "\\" in v:
            raise ValueError("pattern matches file names only; put the directory in 'root'")
        return v


class FileSearchOutput(SkillIO):
    root: str
    pattern: str
    matches: list[str]
    truncated: bool


class FileSearchSkill(Skill):
    name = "file_search"
    description = (
        "Find files by name under a folder (searches subfolders too). Read-only. "
        "Use a folder name like 'Downloads' or 'Documents' as root."
    )
    risk = RiskLevel.SAFE
    input_model = FileSearchInput
    output_model = FileSearchOutput

    def __init__(
        self,
        settings: FileSearchSettings | None = None,
        *,
        folders: Mapping[str, Path] | None = None,
    ) -> None:
        self._settings = settings or FileSearchSettings()
        self._folders = folders

    @property
    def folders(self) -> Mapping[str, Path]:
        if self._folders is None:
            self._folders = known_folders()
        return self._folders

    def run(self, data: FileSearchInput, *, dry_run: bool) -> FileSearchOutput:
        raw_root = data.root or str(self._settings.default_root)
        root = resolve_user_path(raw_root, self.folders)
        if not root.is_dir():
            raise SkillError(
                f"not a directory: {root}. Known folders: {describe_folders(self.folders)}"
            )
        cap = self._settings.max_results
        limit = min(data.max_results or cap, cap)
        excluded = {d.lower() for d in self._settings.exclude_dirs}
        pattern = normalize_pattern(data.pattern)

        matches: list[str] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d.lower() not in excluded)
            for fname in sorted(filenames):
                if fnmatch.fnmatchcase(fname.lower(), pattern):
                    if len(matches) >= limit:
                        truncated = True
                        break
                    matches.append(str(Path(dirpath) / fname))
            if truncated:
                break
        return FileSearchOutput(
            root=str(root), pattern=pattern, matches=matches, truncated=truncated
        )
