"""list_processes: list running processes via ``tasklist``. Read-only."""

from __future__ import annotations

import csv
import io
import re

from pydantic import Field

from aegis.models.config import ProcessListSettings
from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO
from aegis.skills._system import CommandRunner, run_command

TASKLIST_COMMAND = ("tasklist", "/FO", "CSV", "/NH")


class ProcessInfo(SkillIO):
    name: str
    pid: int
    memory_kb: int | None


class ListProcessesInput(SkillIO):
    name_contains: str | None = Field(None, description="Case-insensitive name filter")
    limit: int | None = Field(None, gt=0)


class ListProcessesOutput(SkillIO):
    processes: list[ProcessInfo]
    total: int
    truncated: bool


def parse_tasklist_csv(text: str) -> list[ProcessInfo]:
    procs: list[ProcessInfo] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        digits = re.sub(r"\D", "", row[4])  # "12,345 K" / "12.345 K" depending on locale
        procs.append(ProcessInfo(name=row[0], pid=pid, memory_kb=int(digits) if digits else None))
    return procs


class ListProcessesSkill(Skill):
    name = "list_processes"
    description = "List running processes (name, PID, memory), optionally filtered by name."
    risk = RiskLevel.SAFE
    input_model = ListProcessesInput
    output_model = ListProcessesOutput

    def __init__(
        self, settings: ProcessListSettings | None = None, runner: CommandRunner = run_command
    ) -> None:
        self._settings = settings or ProcessListSettings()
        self._runner = runner

    def run(self, data: ListProcessesInput, *, dry_run: bool) -> ListProcessesOutput:
        procs = parse_tasklist_csv(self._runner(TASKLIST_COMMAND))
        if not procs:
            raise SkillError("tasklist returned no parseable rows")
        if data.name_contains:
            needle = data.name_contains.lower()
            procs = [p for p in procs if needle in p.name.lower()]
        procs.sort(key=lambda p: (p.name.lower(), p.pid))
        cap = self._settings.max_results
        limit = min(data.limit or cap, cap)
        return ListProcessesOutput(
            processes=procs[:limit], total=len(procs), truncated=len(procs) > limit
        )
