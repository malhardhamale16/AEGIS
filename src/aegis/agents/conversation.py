"""Conversation agent: keeps chat history, plans, executes, and explains the outcome."""

from __future__ import annotations

import json

from aegis.agents.executor import ExecutorAgent
from aegis.agents.planner import PlannerAgent, PlanningError
from aegis.core.llm import LLMClient, LLMError, LLMUnavailableError
from aegis.core.logging import get_logger
from aegis.models.config import ConversationSettings
from aegis.models.llm import ChatMessage
from aegis.models.plan import AgentReply, PlanResult

log = get_logger("agents.conversation")

SUMMARY_PROMPT = """\
You are AEGIS, a local assistant on the user's Windows PC.
Explain to the user what just happened, in 1-3 short sentences, using only the results below.
- If a step ran as a dry run, say it was only simulated and nothing was changed.
- If a step was denied or failed, say so plainly and give the reason.
- Never invent results.
"""

FALLBACK_NO_ANSWER = "I'm not sure how to help with that."


def describe_result(result: PlanResult) -> str:
    """Plain-text summary that needs no LLM (used as a fallback)."""
    lines = []
    for step, res in zip(result.plan.steps, result.results, strict=False):
        if res.ok:
            mode = " (dry run, nothing changed)" if res.decision and res.decision.dry_run else ""
            lines.append(f"- {step.skill}: done{mode}")
        else:
            lines.append(f"- {step.skill}: {res.error}")
    skipped = len(result.plan.steps) - len(result.results)
    if skipped:
        lines.append(f"- {skipped} remaining step(s) skipped")
    return "\n".join(lines) or "Nothing to do."


class ConversationAgent:
    def __init__(
        self,
        llm: LLMClient,
        planner: PlannerAgent,
        executor: ExecutorAgent,
        model: str,
        settings: ConversationSettings | None = None,
    ) -> None:
        self._llm = llm
        self._planner = planner
        self._executor = executor
        self._model = model
        self._settings = settings or ConversationSettings()
        self._history: list[ChatMessage] = []

    @property
    def history(self) -> list[ChatMessage]:
        return list(self._history)

    def reset(self) -> None:
        self._history.clear()

    def _remember(self, user_text: str, reply: str) -> None:
        self._history += [
            ChatMessage(role="user", content=user_text),
            ChatMessage(role="assistant", content=reply),
        ]
        limit = self._settings.max_history
        self._history = self._history[-limit:] if limit else []

    def handle(self, user_text: str, *, dry_run: bool | None = None) -> AgentReply:
        try:
            plan = self._planner.plan(user_text, self._history)
        except LLMUnavailableError as exc:
            return AgentReply(
                text=f"I can't reach the local model right now ({exc}).", error=str(exc)
            )
        except (PlanningError, LLMError) as exc:
            log.warning("planning failed: %s", exc)
            return AgentReply(text="Sorry, I couldn't work out how to do that.", error=str(exc))

        if plan.is_direct_answer:
            text = plan.response or FALLBACK_NO_ANSWER
            self._remember(user_text, text)
            return AgentReply(text=text, plan=plan)

        result = self._executor.execute(plan, dry_run=dry_run)
        text = self._summarize(user_text, result)
        self._remember(user_text, text)
        return AgentReply(text=text, plan=plan, result=result)

    def _summarize(self, user_text: str, result: PlanResult) -> str:
        payload = [
            {
                "skill": r.skill,
                "ok": r.ok,
                "dry_run": r.decision.dry_run if r.decision else None,
                "output": r.output,
                "error": r.error,
            }
            for r in result.results
        ]
        data = json.dumps(
            {
                "completed": result.completed,
                "stopped_reason": result.stopped_reason,
                "results": payload,
            },
            default=str,
        )[: self._settings.summary_max_chars]
        messages = [
            ChatMessage(role="system", content=SUMMARY_PROMPT),
            ChatMessage(role="user", content=f"Request: {user_text}\nResults: {data}"),
        ]
        try:
            text = self._llm.chat(messages, self._model).content.strip()
        except LLMError as exc:
            log.warning("summary failed, using fallback: %s", exc)
            text = ""
        return text or describe_result(result)
