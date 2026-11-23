"""Skills: small, single-purpose, testable units of action."""

from __future__ import annotations

from aegis.core.registry import SkillRegistry
from aegis.models.config import SkillsConfig
from aegis.models.skill import Skill
from aegis.skills._paths import known_folders
from aegis.skills.clipboard import ClipboardReadSkill
from aegis.skills.file_search import FileSearchSkill
from aegis.skills.list_processes import ListProcessesSkill
from aegis.skills.open_app import OpenAppSkill
from aegis.skills.open_path import OpenPathSkill
from aegis.skills.system_info import SystemInfoSkill
from aegis.skills.web_open import WebOpenSkill
from aegis.skills.write_file import WriteFileSkill


def builtin_skills(config: SkillsConfig) -> list[Skill]:
    """Instantiate every built-in skill with its settings from skills.yaml."""
    return [
        SystemInfoSkill(),
        FileSearchSkill(config.file_search),
        ClipboardReadSkill(config.clipboard_read),
        OpenAppSkill(config.open_app),
        OpenPathSkill(),
        WebOpenSkill(),
        ListProcessesSkill(config.list_processes),
        WriteFileSkill(config.write_file),
    ]


def machine_context(config: SkillsConfig) -> list[str]:
    """Facts about this PC that help the planner pick real arguments (no guessing paths)."""
    folders = known_folders()
    lines = [
        f"Home folder: {folders['home']}",
        "Known folders: "
        + ", ".join(f"{k.capitalize()} = {v}" for k, v in folders.items() if k != "home"),
        "For a folder argument use one of these real paths or just its name (e.g. "
        '"Downloads"). Never write placeholders such as [username].',
    ]
    if config.open_app.aliases:
        lines.append("Apps open_app can launch: " + ", ".join(sorted(config.open_app.aliases)))
    return lines


def register_builtin_skills(registry: SkillRegistry, config: SkillsConfig) -> SkillRegistry:
    for skill in builtin_skills(config):
        registry.register(skill)
    return registry


__all__ = [
    "ClipboardReadSkill",
    "FileSearchSkill",
    "ListProcessesSkill",
    "OpenAppSkill",
    "OpenPathSkill",
    "SystemInfoSkill",
    "WebOpenSkill",
    "WriteFileSkill",
    "builtin_skills",
    "machine_context",
    "register_builtin_skills",
]
