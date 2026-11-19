"""Skill registry: the only path from agents to skills."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from aegis.core.logging import get_logger
from aegis.models.config import SkillsConfig
from aegis.models.skill import SKILL_NAME_RE, RiskLevel, Skill, SkillInfo

log = get_logger("registry")


class RegistryError(Exception):
    """Invalid skill definition or registry configuration."""


class UnknownSkillError(RegistryError):
    pass


class SkillDisabledError(RegistryError):
    pass


class SkillBlockedError(RegistryError):
    pass


def _validate_skill(skill: Skill) -> None:
    cls = type(skill)
    for attr in ("name", "description", "risk", "input_model", "output_model"):
        if not hasattr(cls, attr):
            raise RegistryError(f"{cls.__name__} is missing required attribute {attr!r}")
    if not isinstance(skill.name, str) or not SKILL_NAME_RE.match(skill.name):
        raise RegistryError(f"Invalid skill name {skill.name!r} (use lower_snake_case)")
    if not isinstance(skill.description, str) or not skill.description.strip():
        raise RegistryError(f"Skill {skill.name!r} needs a description")
    if not isinstance(skill.risk, RiskLevel):
        raise RegistryError(f"Skill {skill.name!r} risk must be a RiskLevel")
    for attr in ("input_model", "output_model"):
        model = getattr(skill, attr)
        if not (inspect.isclass(model) and issubclass(model, BaseModel)):
            raise RegistryError(f"Skill {skill.name!r} {attr} must be a pydantic model class")


class SkillRegistry:
    """Holds skill instances and applies ``skills.yaml`` (enable list and risk overrides).

    Overrides may only *raise* a skill's risk (safe -> confirm -> blocked). Lowering it
    from config is rejected so a YAML edit can't silently remove a confirmation step.
    """

    def __init__(self, config: SkillsConfig | None = None) -> None:
        self._config = config or SkillsConfig()
        self._skills: dict[str, Skill] = {}

    # ------------------------------------------------------------------ registration

    def register(self, skill: Skill) -> Skill:
        _validate_skill(skill)
        if skill.name in self._skills:
            raise RegistryError(f"Skill {skill.name!r} is already registered")
        override = self._config.overrides.get(skill.name)
        if override and override.risk and override.risk.rank < skill.risk.rank:
            raise RegistryError(
                f"skills.yaml cannot lower risk of {skill.name!r} "
                f"from {skill.risk.value} to {override.risk.value}"
            )
        self._skills[skill.name] = skill
        log.debug("Registered skill %s (%s)", skill.name, self.effective_risk(skill.name))
        return skill

    # ----------------------------------------------------------------------- queries

    def is_enabled(self, name: str) -> bool:
        if name not in self._skills:
            return False
        override = self._config.overrides.get(name)
        if override and override.enabled is not None:
            return override.enabled
        return not self._config.enabled or name in self._config.enabled

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise UnknownSkillError(f"Unknown skill {name!r}")
        if not self.is_enabled(name):
            raise SkillDisabledError(f"Skill {name!r} is disabled in skills.yaml")
        return self._skills[name]

    def effective_risk(self, name: str) -> RiskLevel:
        skill = self._skills.get(name)
        if skill is None:
            raise UnknownSkillError(f"Unknown skill {name!r}")
        override = self._config.overrides.get(name)
        return override.risk if override and override.risk else skill.risk

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.is_enabled(name)

    def names(self) -> list[str]:
        return sorted(n for n in self._skills if self.is_enabled(n))

    def info(self, name: str) -> SkillInfo:
        skill = self.get(name)
        return SkillInfo(
            name=skill.name,
            description=skill.description,
            risk=self.effective_risk(name),
            input_schema=skill.input_model.model_json_schema(),
            output_schema=skill.output_model.model_json_schema(),
        )

    def describe(self) -> list[SkillInfo]:
        """Info for every enabled skill, sorted by name (what the planner sees)."""
        return [self.info(n) for n in self.names()]

    # --------------------------------------------------------------------- execution

    def validate_input(self, name: str, args: dict[str, Any]) -> BaseModel:
        """Raise ``pydantic.ValidationError`` if ``args`` don't match the input schema."""
        return self.get(name).input_model.model_validate(args)

    def execute(self, name: str, args: dict[str, Any], *, dry_run: bool) -> BaseModel:
        """Validate input, run the skill, validate output.

        Does not ask for permission: callers go through ``PermissionGate``. Blocked
        skills are refused here too, as a second line of defense.
        """
        skill = self.get(name)
        if self.effective_risk(name) is RiskLevel.BLOCKED:
            raise SkillBlockedError(f"Skill {name!r} is blocked")
        data = skill.input_model.model_validate(args)
        result = skill.run(data, dry_run=dry_run)
        if not isinstance(result, skill.output_model):
            result = skill.output_model.model_validate(
                result.model_dump() if isinstance(result, BaseModel) else result
            )
        return result
