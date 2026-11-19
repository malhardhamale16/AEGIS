"""Importable test doubles (conftest modules are not safely importable by name)."""

from collections.abc import Sequence

from aegis.models.llm import ChatMessage, ChatResponse


class FakeLLM:
    """Scripted LLMClient. Each chat() call pops the next response (str or Exception)."""

    def __init__(self, responses: Sequence[str | Exception] = ()) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, model, *, format=None, temperature=None, max_tokens=None):
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "format": format,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResponse(model=model, content=item)

    def last_messages(self) -> list[ChatMessage]:
        return self.calls[-1]["messages"]
