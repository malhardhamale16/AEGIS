"""open_app: launch an application from the configured allowlist."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

from pydantic import Field

from aegis.models.config import OpenAppSettings
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO

Launcher = Callable[[str], None]


def default_launcher(target: str) -> None:
    # ``target`` only ever comes from the skills.yaml allowlist, never from the LLM directly.
    if sys.platform == "win32":
        os.startfile(target)
    else:
        subprocess.Popen([target])


class OpenAppInput(SkillIO):
    app: str = Field(..., min_length=1, description="App alias from skills.yaml, e.g. 'notepad'")


class OpenAppOutput(SkillIO):
    app: str
    target: str
    launched: bool


class OpenAppSkill(Skill):
    name = "open_app"
    description = (
        "Launch an application by its configured alias (see skills.yaml open_app.aliases). "
        "Arbitrary executables are refused."
    )
    risk = RiskLevel.SAFE
    input_model = OpenAppInput
    output_model = OpenAppOutput

    def __init__(
        self, settings: OpenAppSettings | None = None, launcher: Launcher = default_launcher
    ) -> None:
        self._aliases = {k.lower(): v for k, v in (settings or OpenAppSettings()).aliases.items()}
        self._launcher = launcher

    @property
    def aliases(self) -> list[str]:
        return sorted(self._aliases)

    def run(self, data: OpenAppInput, *, dry_run: bool) -> OpenAppOutput:
        key = data.app.strip().lower()
        target = self._aliases.get(key)
        if target is None:
            known = ", ".join(self.aliases) or "(none configured)"
            raise SkillError(f"unknown app {data.app!r}; allowed: {known}")
        if dry_run:
            return OpenAppOutput(app=key, target=target, launched=False)
        try:
            self._launcher(target)
        except OSError as exc:
            raise SkillError(f"failed to launch {target}: {exc}") from exc
        return OpenAppOutput(app=key, target=target, launched=True)
