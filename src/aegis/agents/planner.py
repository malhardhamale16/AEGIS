"""Planner agent: natural language -> validated plan of skill calls (structured JSON)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import ValidationError

from aegis.core.llm import LLMClient
from aegis.core.logging import get_logger
from aegis.core.registry import RegistryError, SkillRegistry
from aegis.models.config import PlannerSettings
from aegis.models.llm import ChatMessage
from aegis.models.plan import Plan, PlanDraft
from aegis.models.skill import SkillInfo

log = get_logger("agents.planner")

SYSTEM_PROMPT = """\
You are the planner for AEGIS, a local assistant that controls a Windows PC.
Turn the user's request into a plan of skill calls.

Rules:
- Use only the skills listed below, with arguments that match their schema exactly.
- Use as few steps as possible, at most {max_steps}.
- Steps run in order. A step cannot use the output of an earlier step.
- If the request needs no skill (a question, small talk), return an empty "steps" list and
  answer in "response".
- If the request cannot be done with these skills, return an empty "steps" list and explain
  why in "response".
- Never invent skills or arguments.

Reply with JSON only, in this shape:
{{"steps": [{{"skill": "<name>", "args": {{...}}, "reason": "<why>"}}], "response": null}}

Skills:
{catalog}
"""

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class PlanningError(Exception):
    """The LLM did not produce a valid plan within the retry budget."""


def format_catalog(skills: Sequence[SkillInfo]) -> str:
    lines = []
    for s in skills:
        schema = s.input_schema
        args = {
            name: {k: v for k, v in spec.items() if k != "title"}
            for name, spec in schema.get("properties", {}).items()
        }
        required = schema.get("required", [])
        lines.append(f"- {s.name} [{s.risk.value}]: {s.description}")
        lines.append(f"  args: {json.dumps(args)}  required: {json.dumps(required)}")
    return "\n".join(lines) if lines else "(no skills available)"


class PlannerAgent:
    def __init__(
        self,
        llm: LLMClient,
        registry: SkillRegistry,
        model: str,
        settings: PlannerSettings | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._model = model
        self._settings = settings or PlannerSettings()

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(
            max_steps=self._settings.max_steps,
            catalog=format_catalog(self._registry.describe()),
        )

    def plan(self, instruction: str, history: Sequence[ChatMessage] = ()) -> Plan:
        """Ask the LLM for a plan and validate it. LLM transport errors propagate."""
        messages = [
            ChatMessage(role="system", content=self.system_prompt()),
            *history,
            ChatMessage(role="user", content=instruction),
        ]
        last_error = "no attempt made"
        for attempt in range(self._settings.max_retries + 1):
            reply = self._llm.chat(
                messages,
                self._model,
                format=PlanDraft.model_json_schema(),
                temperature=0,
            )
            try:
                draft = self._parse(reply.content)
            except PlanningError as exc:
                last_error = str(exc)
                log.warning("invalid plan (attempt %d): %s", attempt + 1, last_error)
                messages += [
                    ChatMessage(role="assistant", content=reply.content),
                    ChatMessage(
                        role="user",
                        content=f"That plan was invalid: {last_error}. "
                        "Reply again with corrected JSON only.",
                    ),
                ]
                continue
            return Plan(goal=instruction, steps=draft.steps, response=draft.response)
        raise PlanningError(f"could not produce a valid plan: {last_error}")

    def _parse(self, content: str) -> PlanDraft:
        text = content.strip()
        if fenced := _FENCE_RE.match(text):
            text = fenced.group(1)
        try:
            draft = PlanDraft.model_validate_json(text)
        except ValidationError as exc:
            raise PlanningError(f"not a valid plan object: {exc.errors()[0]['msg']}") from exc

        if len(draft.steps) > self._settings.max_steps:
            raise PlanningError(
                f"{len(draft.steps)} steps exceeds the limit of {self._settings.max_steps}"
            )
        for i, step in enumerate(draft.steps, 1):
            if step.skill not in self._registry:
                raise PlanningError(f"step {i} uses unknown skill {step.skill!r}")
            try:
                self._registry.validate_input(step.skill, step.args)
            except (ValidationError, RegistryError) as exc:
                raise PlanningError(f"step {i} ({step.skill}) has invalid args: {exc}") from exc
        return draft
