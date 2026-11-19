from aegis.agents.executor import (
    TOPIC_PLAN_FINISHED,
    TOPIC_PLAN_STARTED,
    TOPIC_PLAN_STEP,
    ExecutorAgent,
)
from aegis.core.permission import PermissionGate
from aegis.models.config import ExecutorSettings
from aegis.models.plan import Plan, PlanStep


def make_plan(*steps):
    return Plan(goal="g", steps=[PlanStep(skill=s, args=a) for s, a in steps])


def test_runs_all_steps(make_executor):
    result = make_executor().execute(make_plan(("echo", {"text": "a"}), ("echo", {"text": "b"})))
    assert result.ok and result.completed
    assert [r.output["text"] for r in result.results] == ["a", "b"]


def test_confirm_step_is_dry_run_by_default(make_executor, fake_write):
    result = make_executor().execute(make_plan(("fake_write", {"path": "f"})))
    assert result.ok and result.results[0].decision.dry_run
    assert fake_write.calls == [("f", True)]


def test_confirm_step_live_needs_approval(make_executor, fake_write):
    asked = []
    ex = make_executor(confirm=lambda r: asked.append(r.skill) or True, dry_run=False)
    assert ex.execute(make_plan(("fake_write", {"path": "f"}))).ok
    assert asked == ["fake_write"] and fake_write.calls == [("f", False)]


def test_stops_on_denial(make_executor, fake_write):
    ex = make_executor(confirm=lambda r: False, dry_run=False)
    result = ex.execute(make_plan(("fake_write", {"path": "f"}), ("echo", {"text": "after"})))
    assert not result.completed and len(result.results) == 1
    assert "step 1 (fake_write) failed: denied" in result.stopped_reason
    assert fake_write.calls == []


def test_stops_on_blocked_skill(make_executor, danger):
    result = make_executor().execute(make_plan(("danger", {"text": "x"}), ("echo", {"text": "y"})))
    assert not result.ok and len(result.results) == 1 and danger.called is False


def test_continue_on_failure_when_configured(registry):
    ex = ExecutorAgent(PermissionGate(registry), ExecutorSettings(stop_on_failure=False))
    result = ex.execute(make_plan(("crash", {"text": "x"}), ("echo", {"text": "y"})))
    assert result.completed and not result.ok
    assert [r.ok for r in result.results] == [False, True]


def test_per_call_dry_run_override(make_executor, fake_write):
    ex = make_executor(confirm=lambda r: True, dry_run=False)
    ex.execute(make_plan(("fake_write", {"path": "f"})), dry_run=True)
    assert fake_write.calls == [("f", True)]


def test_empty_plan(make_executor):
    result = make_executor().execute(make_plan())
    assert result.ok and result.results == []


def test_events_emitted_in_order(make_executor, bus):
    topics = []
    bus.subscribe("*", lambda e: topics.append(e.topic))
    make_executor().execute(make_plan(("echo", {"text": "a"})))
    plan_topics = [t for t in topics if t.startswith("plan.")]
    assert plan_topics == [TOPIC_PLAN_STARTED, TOPIC_PLAN_STEP, TOPIC_PLAN_FINISHED]
