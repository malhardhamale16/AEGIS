"""system_info: basic, read-only facts about this machine."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from collections.abc import Callable

from aegis.models.skill import RiskLevel, Skill, SkillIO

MemoryProbe = Callable[[], tuple[int, int] | None]


def windows_memory() -> tuple[int, int] | None:
    """(total_bytes, available_bytes) via GlobalMemoryStatusEx, or None off Windows."""
    if sys.platform != "win32":
        return None

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return None
    return int(stat.ullTotalPhys), int(stat.ullAvailPhys)


class SystemInfoInput(SkillIO):
    pass


class SystemInfoOutput(SkillIO):
    os: str
    os_version: str
    hostname: str
    machine: str
    cpu_count: int | None
    python_version: str
    memory_total_mb: int | None
    memory_available_mb: int | None


class SystemInfoSkill(Skill):
    name = "system_info"
    description = "Report OS, hostname, CPU count, memory and Python version. Read-only."
    risk = RiskLevel.SAFE
    input_model = SystemInfoInput
    output_model = SystemInfoOutput

    def __init__(self, memory_probe: MemoryProbe = windows_memory) -> None:
        self._memory_probe = memory_probe

    def run(self, data: SystemInfoInput, *, dry_run: bool) -> SystemInfoOutput:
        mem = self._memory_probe()
        mb = 1024 * 1024
        return SystemInfoOutput(
            os=platform.system(),
            os_version=platform.version(),
            hostname=platform.node(),
            machine=platform.machine(),
            cpu_count=os.cpu_count(),
            python_version=platform.python_version(),
            memory_total_mb=mem[0] // mb if mem else None,
            memory_available_mb=mem[1] // mb if mem else None,
        )
