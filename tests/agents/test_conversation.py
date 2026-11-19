import pytest
from agent_helpers import plan_json

from aegis.agents.conversation import FALLBACK_NO_ANSWER, ConversationAgent, describe_result
from aegis.agents.executor import ExecutorAgent
from aegis.agents.planner import PlannerAgent
from aegis.core.llm import LLMResponseError, LLMUnavailableError
from aegis.core.permission import PermissionGate
from aegis.models.config import ConversationSettings, SafetyConfig


@pytest.fixture
def make_agent(registry, fake_llm_factory):
    def _make(responses, confirm=None, history=20, **safety):
        llm = fake_llm_factory(responses)
        planner = PlannerAgent(llm, registry, "planner-model")
        gate = PermissionGate(registry, SafetyConfig(**safety), confirm=confirm)
        agent = ConversationAgent(
            llm,
            planner,
            ExecutorAgent(gate),
            "chat-model",
            ConversationSettings(max_history=history),
        )
        return agent, llm

    return _make


def test_direct_answer_uses_one_llm_call(make_agent):
    agent, llm = make_agent([plan_json(response="Hi there")])
    reply = agent.handle("hello")
    assert reply.text == "Hi there" and reply.result is None
    assert len(llm.calls) == 1


def test_direct_answer_without_text_falls_back(make_agent):
    agent, _ = make_agent([plan_json()])
    assert agent.handle("??").text == FALLBACK_NO_ANSWER


def test_plan_executes_and_is_summarized(make_agent):
    agent, llm = make_agent([plan_json(("echo", {"text": "yo"})), "I echoed 'yo'."])
    reply = agent.handle("echo yo")
    assert reply.text == "I echoed 'yo'."
    assert reply.result.ok
    summary_call = llm.calls[1]
    assert summary_call["model"] == "chat-model"
    assert '"output": {"text": "yo"}' in summary_call["messages"][1].content


def test_summary_mentions_dry_run_in_payload(make_agent, fake_write):
    agent, llm = make_agent([plan_json(("fake_write", {"path": "a"})), "Simulated."])
    agent.handle("write a")
    assert '"dry_run": true' in llm.calls[1]["messages"][1].content
    assert fake_write.calls == [("a", True)]


def test_summary_failure_uses_deterministic_fallback(make_agent):
    agent, _ = make_agent([plan_json(("echo", {"text": "x"})), LLMResponseError("boom")])
    assert agent.handle("echo").text == "- echo: done"


def test_empty_summary_uses_fallback(make_agent):
    agent, _ = make_agent([plan_json(("fake_write", {"path": "a"})), "   "])
    assert agent.handle("w").text == "- fake_write: done (dry run, nothing changed)"


def test_ollama_down_gives_friendly_error(make_agent):
    agent, _ = make_agent([LLMUnavailableError("connection refused")])
    reply = agent.handle("hi")
    assert "can't reach the local model" in reply.text and reply.error
    assert agent.history == []


def test_planning_failure_gives_friendly_error(make_agent):
    agent, _ = make_agent(["junk", "junk"])
    reply = agent.handle("do it")
    assert "couldn't work out" in reply.text and reply.error


def test_history_grows_and_is_sent_to_planner(make_agent):
    agent, llm = make_agent([plan_json(response="one"), plan_json(response="two")])
    agent.handle("first")
    agent.handle("second")
    assert [m.content for m in agent.history] == ["first", "one", "second", "two"]
    contents = [m.content for m in llm.calls[1]["messages"][1:]]
    assert contents == ["first", "one", "second"]


def test_history_trimmed(make_agent):
    agent, _ = make_agent([plan_json(response=str(i)) for i in range(3)], history=2)
    for i in range(3):
        agent.handle(f"q{i}")
    assert [m.content for m in agent.history] == ["q2", "2"]


def test_history_disabled(make_agent):
    agent, _ = make_agent([plan_json(response="x")], history=0)
    agent.handle("q")
    assert agent.history == []


def test_reset_clears_history(make_agent):
    agent, _ = make_agent([plan_json(response="x")])
    agent.handle("q")
    agent.reset()
    assert agent.history == []


def test_describe_result_reports_failure_and_skips(make_agent):
    agent, _ = make_agent(
        [plan_json(("danger", {"text": "x"}), ("echo", {"text": "y"})), LLMResponseError("x")]
    )
    reply = agent.handle("do danger")
    text = describe_result(reply.result)
    assert "danger: denied: skill is blocked" in text
    assert "1 remaining step(s) skipped" in text
