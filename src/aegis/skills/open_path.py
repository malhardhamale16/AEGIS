"""open_path: open a folder in File Explorer, or a document with its default app.

Programs, scripts and shortcuts are refused: this skill must never run code.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import Field

from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO
from aegis.skills._paths import describe_folders, known_folders, resolve_user_path

Opener = Callable[[Path], None]

# Anything Windows would execute (or hand to an interpreter) when "opened".
BLOCKED_EXTENSIONS = {
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".ps1xml", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".msi", ".msp", ".mst", ".scr", ".pif", ".lnk", ".url",
    ".reg", ".hta", ".cpl", ".jar", ".appref-ms", ".application", ".gadget", ".inf", ".dll",
    ".sys", ".msc", ".py", ".pyw", ".sh", ".appx", ".msix", ".settingcontent-ms",
}  # fmt: skip


def default_opener(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    else:  # pragma: no cover - AEGIS targets Windows
        subprocess.Popen(["xdg-open", str(path)])


class OpenPathInput(SkillIO):
    path: str = Field(
        ...,
        min_length=1,
        description="Folder or document to open: a real path, or a folder name such as "
        "'Downloads', 'Documents', 'Desktop'",
    )


class OpenPathOutput(SkillIO):
    path: str
    is_folder: bool
    opened: bool


class OpenPathSkill(Skill):
    name = "open_path"
    description = (
        "Open a folder in File Explorer, or a document (pdf, docx, image, video...) with its "
        "default app. Programs and scripts are refused."
    )
    risk = RiskLevel.SAFE
    input_model = OpenPathInput
    output_model = OpenPathOutput

    def __init__(
        self, *, opener: Opener = default_opener, folders: Mapping[str, Path] | None = None
    ) -> None:
        self._opener = opener
        self._folders = folders

    @property
    def folders(self) -> Mapping[str, Path]:
        if self._folders is None:
            self._folders = known_folders()
        return self._folders

    def run(self, data: OpenPathInput, *, dry_run: bool) -> OpenPathOutput:
        path = resolve_user_path(data.path, self.folders)
        if not path.exists():
            raise SkillError(
                f"{path} does not exist. Known folders: {describe_folders(self.folders)}"
            )
        is_folder = path.is_dir()
        if not is_folder and path.suffix.lower() in BLOCKED_EXTENSIONS:
            raise SkillError(f"refusing to open {path.name}: {path.suffix} files can run code")
        if dry_run:
            return OpenPathOutput(path=str(path), is_folder=is_folder, opened=False)
        try:
            self._opener(path)
        except OSError as exc:
            raise SkillError(f"could not open {path}: {exc}") from exc
        return OpenPathOutput(path=str(path), is_folder=is_folder, opened=True)
