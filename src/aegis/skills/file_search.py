"""file_search: find files by name pattern. Read-only."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from pydantic import Field, field_validator

from aegis.models.config import FileSearchSettings
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO


class FileSearchInput(SkillIO):
    pattern: str = Field(..., min_length=1, description="File name glob, e.g. '*.pdf'")
    root: str | None = Field(None, description="Directory to search; defaults to config")
    max_results: int | None = Field(None, gt=0)

    @field_validator("pattern")
    @classmethod
    def _name_only(cls, v: str) -> str:
        if "/" in v or "\\" in v:
            raise ValueError("pattern matches file names only; put the directory in 'root'")
        return v


class FileSearchOutput(SkillIO):
    root: str
    matches: list[str]
    truncated: bool


class FileSearchSkill(Skill):
    name = "file_search"
    description = "Find files whose name matches a glob pattern under a directory. Read-only."
    risk = RiskLevel.SAFE
    input_model = FileSearchInput
    output_model = FileSearchOutput

    def __init__(self, settings: FileSearchSettings | None = None) -> None:
        self._settings = settings or FileSearchSettings()

    def run(self, data: FileSearchInput, *, dry_run: bool) -> FileSearchOutput:
        root = Path(data.root or self._settings.default_root).expanduser()
        if not root.is_dir():
            raise SkillError(f"not a directory: {root}")
        cap = self._settings.max_results
        limit = min(data.max_results or cap, cap)
        excluded = {d.lower() for d in self._settings.exclude_dirs}
        pattern = data.pattern.lower()

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
        return FileSearchOutput(root=str(root), matches=matches, truncated=truncated)
