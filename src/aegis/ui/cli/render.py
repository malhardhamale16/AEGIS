"""Rich rendering for CLI output. All dynamic text goes through ``Text`` (no markup injection)."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aegis.apps.doctor import Check, Status
from aegis.models.permission import ConfirmRequest
from aegis.models.plan import AgentReply
from aegis.models.skill import RiskLevel, SkillInfo

RISK_STYLE = {RiskLevel.SAFE: "green", RiskLevel.CONFIRM: "yellow", RiskLevel.BLOCKED: "red"}
STATUS_STYLE = {Status.OK: "green", Status.WARN: "yellow", Status.FAIL: "bold red"}


def _risk(risk: RiskLevel) -> Text:
    return Text(risk.value, style=RISK_STYLE[risk])


def skills_table(infos: Sequence[SkillInfo]) -> Table:
    table = Table(title="Skills", show_lines=False)
    table.add_column("name", style="bold")
    table.add_column("risk")
    table.add_column("description")
    for info in infos:
        table.add_row(Text(info.name), _risk(info.risk), Text(info.description))
    return table


def doctor_table(checks: Sequence[Check]) -> Table:
    table = Table(title="AEGIS doctor")
    table.add_column("check", style="bold")
    table.add_column("status")
    table.add_column("detail")
    for c in checks:
        table.add_row(
            Text(c.name), Text(c.status.value.upper(), style=STATUS_STYLE[c.status]), Text(c.detail)
        )
    return table


def dry_run_banner(console: Console) -> None:
    console.print(
        Text(
            "[dry-run] state-changing skills are only simulated. Use --execute to act.",
            style="yellow",
        )
    )


def render_reply(console: Console, reply: AgentReply) -> None:
    result = reply.result
    if result and result.plan.steps:
        table = Table(title="Plan", title_justify="left")
        table.add_column("#", justify="right")
        table.add_column("skill", style="bold")
        table.add_column("args")
        table.add_column("result")
        for i, step in enumerate(result.plan.steps, 1):
            res = result.results[i - 1] if i <= len(result.results) else None
            if res is None:
                status = Text("skipped", style="dim")
            elif res.ok:
                dry = res.decision is not None and res.decision.dry_run
                status = Text("simulated" if dry else "done", style="cyan" if dry else "green")
            else:
                status = Text(res.error or "failed", style="red")
            table.add_row(str(i), Text(step.skill), Text(json.dumps(step.args)), status)
        console.print(table)
    style = "red" if reply.error else None
    console.print(Text("aegis> ", style="bold magenta") + Text(reply.text, style=style))


def confirm_panel(request: ConfirmRequest) -> Panel:
    body = Text()
    body.append(f"{request.skill}", style="bold")
    body.append(f"  [{request.risk.value}]\n", style=RISK_STYLE[request.risk])
    body.append(request.description + "\n\n")
    body.append(json.dumps(request.args, indent=2, ensure_ascii=False))
    return Panel(body, title="Confirmation required", border_style="yellow")
