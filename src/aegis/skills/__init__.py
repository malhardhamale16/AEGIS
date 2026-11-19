"""Skills: small, single-purpose, testable units of action."""

from __future__ import annotations

from aegis.core.registry import SkillRegistry
from aegis.models.config import SkillsConfig
from aegis.models.skill import Skill
from aegis.skills.clipboard import ClipboardReadSkill
from aegis.skills.file_search import FileSearchSkill
from aegis.skills.list_processes import ListProcessesSkill
from aegis.skills.open_app import OpenAppSkill
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
        WebOpenSkill(),
        ListProcessesSkill(config.list_processes),
        WriteFileSkill(config.write_file),
    ]


def register_builtin_skills(registry: SkillRegistry, config: SkillsConfig) -> SkillRegistry:
    for skill in builtin_skills(config):
        registry.register(skill)
    return registry


__all__ = [
    "ClipboardReadSkill",
    "FileSearchSkill",
    "ListProcessesSkill",
    "OpenAppSkill",
    "SystemInfoSkill",
    "WebOpenSkill",
    "WriteFileSkill",
    "builtin_skills",
    "register_builtin_skills",
]
