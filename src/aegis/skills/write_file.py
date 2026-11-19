"""write_file: write a UTF-8 text file inside an allowed directory. Changes state -> confirm."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from aegis.models.config import WriteFileSettings
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO


class WriteFileInput(SkillIO):
    path: str = Field(
        ..., min_length=1, description="Target file; relative paths go under the first allowed root"
    )
    content: str
    overwrite: bool = False


class WriteFileOutput(SkillIO):
    path: str
    bytes: int
    existed: bool
    written: bool
    dry_run: bool


class WriteFileSkill(Skill):
    name = "write_file"
    description = (
        "Create or overwrite a UTF-8 text file. Only inside the allowed directories from "
        "skills.yaml. Refuses to overwrite unless overwrite=true."
    )
    risk = RiskLevel.CONFIRM
    input_model = WriteFileInput
    output_model = WriteFileOutput

    def __init__(self, settings: WriteFileSettings | None = None) -> None:
        self._settings = settings or WriteFileSettings()
        self._roots = [Path(r).expanduser().resolve() for r in self._settings.allowed_roots]

    def _resolve(self, raw: str) -> Path:
        if not self._roots:
            raise SkillError("write_file has no allowed_roots configured")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self._roots[0] / path
        path = path.resolve()  # collapses ".." so traversal can't escape a root
        if not any(path.is_relative_to(root) for root in self._roots):
            allowed = ", ".join(str(r) for r in self._roots)
            raise SkillError(f"{path} is outside the allowed directories ({allowed})")
        if path in self._roots:
            raise SkillError("path must be a file, not an allowed root itself")
        return path

    def run(self, data: WriteFileInput, *, dry_run: bool) -> WriteFileOutput:
        path = self._resolve(data.path)
        encoded = data.content.encode("utf-8")
        if len(encoded) > self._settings.max_bytes:
            raise SkillError(
                f"content is {len(encoded)} bytes; limit is {self._settings.max_bytes}"
            )
        if path.is_dir():
            raise SkillError(f"{path} is a directory")
        existed = path.exists()
        if existed and not data.overwrite:
            raise SkillError(f"{path} already exists (set overwrite=true to replace it)")

        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
        return WriteFileOutput(
            path=str(path),
            bytes=len(encoded),
            existed=existed,
            written=not dry_run,
            dry_run=dry_run,
        )
