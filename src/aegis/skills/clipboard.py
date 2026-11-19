"""clipboard_read: read the current clipboard text. Read-only."""

from __future__ import annotations

from pydantic import Field

from aegis.models.config import ClipboardSettings
from aegis.models.skill import RiskLevel, Skill, SkillIO
from aegis.skills._system import CommandRunner, run_command

CLIPBOARD_COMMAND = (
    "powershell",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    "Get-Clipboard -Raw",
)


class ClipboardReadInput(SkillIO):
    max_chars: int | None = Field(None, gt=0)


class ClipboardReadOutput(SkillIO):
    text: str
    length: int
    truncated: bool


class ClipboardReadSkill(Skill):
    name = "clipboard_read"
    description = "Read the text currently on the clipboard. Read-only."
    risk = RiskLevel.SAFE
    input_model = ClipboardReadInput
    output_model = ClipboardReadOutput

    def __init__(
        self, settings: ClipboardSettings | None = None, runner: CommandRunner = run_command
    ) -> None:
        self._settings = settings or ClipboardSettings()
        self._runner = runner

    def run(self, data: ClipboardReadInput, *, dry_run: bool) -> ClipboardReadOutput:
        raw = self._runner(CLIPBOARD_COMMAND)
        text = raw[:-2] if raw.endswith("\r\n") else raw.removesuffix("\n")
        limit = min(data.max_chars or self._settings.max_chars, self._settings.max_chars)
        return ClipboardReadOutput(text=text[:limit], length=len(text), truncated=len(text) > limit)
