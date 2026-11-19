"""Thin OS adapters. Skills receive these as injectable callables so tests never touch the OS."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence

from aegis.models.skill import SkillError

CommandRunner = Callable[[Sequence[str]], str]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_command(args: Sequence[str], timeout: float = 10.0) -> str:
    """Run a command without a shell and return stdout. Raises ``SkillError`` on failure."""
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except FileNotFoundError as exc:
        raise SkillError(f"command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"command timed out: {args[0]}") from exc
    if proc.returncode != 0:
        raise SkillError(f"{args[0]} exited with {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout
