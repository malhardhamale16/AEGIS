import pytest
from agent_helpers import plan_json

from aegis.agents.planner import PlannerAgent, PlanningError, format_catalog
from aegis.core.llm import LLMUnavailableError
from aegis.models.llm import ChatMessage
from aegis.models.plan import PlanDraft


def test_valid_plan_returned(make_planner):
    planner, llm = make_planner([plan_json(("echo", {"text": "hi"}))])
    plan = planner.plan("say hi")
    assert plan.goal == "say hi"
    assert [(s.skill, s.args) for s in plan.steps] == [("echo", {"text": "hi"})]
    call = llm.calls[0]
    assert call["model"] == "planner-model"
    assert call["temperature"] == 0
    assert call["format"] == PlanDraft.model_json_schema()


def test_system_prompt_lists_skills_with_risk_and_args(make_planner):
    planner, llm = make_planner([plan_json()])
    planner.plan("x")
    system = llm.calls[0]["messages"][0]
    assert system.role == "system"
    assert "- echo [safe]: Return the input text." in system.content
    assert "- fake_write [confirm]" in system.content
    assert '"text": {"type": "string"}' in system.content
    assert "at most 5" in system.content
    assert "Plan only what the user explicitly asked for" in system.content
    assert "Leave optional arguments out" in system.content


def test_disabled_skills_not_in_catalog(registry):
    assert "danger" in format_catalog(registry.describe())
    assert format_catalog([]) == "(no skills available)"


def test_direct_answer(make_planner):
    planner, _ = make_planner([plan_json(response="Hello!")])
    plan = planner.plan("hi")
    assert plan.is_direct_answer and plan.response == "Hello!"


def test_history_is_passed_between_system_and_user(make_planner):
    planner, llm = make_planner([plan_json()])
    history = [ChatMessage(role="user", content="a"), ChatMessage(role="assistant", content="b")]
    planner.plan("c", history)
    roles = [(m.role, m.content) for m in llm.last_messages()[1:]]
    assert roles == [("user", "a"), ("assistant", "b"), ("user", "c")]


def test_code_fenced_json_accepted(make_planner):
    planner, _ = make_planner(["```json\n" + plan_json(("echo", {"text": "x"})) + "\n```"])
    assert planner.plan("x").steps[0].skill == "echo"


@pytest.mark.parametrize(
    "bad, match",
    [
        ("not json at all", "not a valid plan"),
        (plan_json(("ghost", {})), "unknown skill 'ghost'"),
        (plan_json(("echo", {})), "invalid args"),
        (plan_json(("echo", {"text": 1})), "invalid args"),
        ('{"steps": [], "extra": 1}', "not a valid plan"),
    ],
)
def test_invalid_plan_retried_then_fails(make_planner, bad, match):
    planner, llm = make_planner([bad, bad], max_retries=1)
    with pytest.raises(PlanningError, match=match):
        planner.plan("x")
    assert len(llm.calls) == 2


def test_retry_feeds_error_back_and_recovers(make_planner):
    planner, llm = make_planner([plan_json(("ghost", {})), plan_json(("echo", {"text": "ok"}))])
    plan = planner.plan("x")
    assert plan.steps[0].skill == "echo"
    retry_msgs = llm.calls[1]["messages"]
    assert retry_msgs[-2].role == "assistant"
    assert "unknown skill 'ghost'" in retry_msgs[-1].content


def test_zero_retries(make_planner):
    planner, llm = make_planner(["junk"], max_retries=0)
    with pytest.raises(PlanningError):
        planner.plan("x")
    assert len(llm.calls) == 1


def test_too_many_steps_rejected(make_planner):
    steps = [("echo", {"text": str(i)}) for i in range(3)]
    planner, _ = make_planner([plan_json(*steps)], max_steps=2, max_retries=0)
    with pytest.raises(PlanningError, match="exceeds the limit of 2"):
        planner.plan("x")


def test_llm_unavailable_propagates(make_planner):
    planner, _ = make_planner([LLMUnavailableError("down")])
    with pytest.raises(LLMUnavailableError):
        planner.plan("x")


def test_planner_does_not_execute_skills(registry, fake_write, fake_llm_factory):
    llm = fake_llm_factory([plan_json(("fake_write", {"path": "a"}))])
    PlannerAgent(llm, registry, "m").plan("write a")
    assert fake_write.calls == []
