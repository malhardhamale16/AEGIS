import pytest

from aegis.core.events import EventBus
from aegis.core.permission import TOPIC_DECIDED, TOPIC_FINISHED, PermissionGate
from aegis.core.registry import SkillRegistry, UnknownSkillError
from aegis.models.config import SafetyConfig
from aegis.models.permission import Verdict


@pytest.fixture
def registry(echo, fake_write, danger, crash):
    reg = SkillRegistry()
    for s in (echo, fake_write, danger, crash):
        reg.register(s)
    return reg


def live(**kw) -> SafetyConfig:
    return SafetyConfig(dry_run=False, **kw)


def test_safe_skill_runs_without_prompt(registry):
    prompts = []
    gate = PermissionGate(registry, live(), confirm=lambda r: prompts.append(r) or True)
    result = gate.execute("echo", {"text": "hi"})
    assert result.ok and result.output == {"text": "hi"}
    assert prompts == []


def test_blocked_skill_denied_and_never_runs(registry, danger):
    gate = PermissionGate(registry, live(), confirm=lambda r: True)
    result = gate.execute("danger", {"text": "x"})
    assert not result.ok
    assert result.decision.verdict is Verdict.DENIED
    assert danger.called is False


def test_default_config_is_dry_run_without_prompt(registry, fake_write):
    prompts = []
    gate = PermissionGate(registry, confirm=lambda r: prompts.append(r) or True)
    result = gate.execute("fake_write", {"path": "a.txt"})
    assert result.ok
    assert result.decision.dry_run is True
    assert result.output == {"path": "a.txt", "written": False}
    assert fake_write.calls == [("a.txt", True)]
    assert prompts == []


def test_confirm_skill_approved(registry, fake_write):
    seen = []
    gate = PermissionGate(registry, live(), confirm=lambda r: seen.append(r) or True)
    result = gate.execute("fake_write", {"path": "a.txt"})
    assert result.ok and result.decision.confirmed
    assert fake_write.calls == [("a.txt", False)]
    assert seen[0].skill == "fake_write" and seen[0].args == {"path": "a.txt"}


def test_confirm_skill_declined(registry, fake_write):
    gate = PermissionGate(registry, live(), confirm=lambda r: False)
    result = gate.execute("fake_write", {"path": "a.txt"})
    assert not result.ok and "declined" in result.error
    assert fake_write.calls == []


def test_confirm_skill_without_prompt_is_denied(registry, fake_write):
    result = PermissionGate(registry, live()).execute("fake_write", {"path": "a.txt"})
    assert result.decision.verdict is Verdict.DENIED
    assert fake_write.calls == []


def test_crashing_confirm_callback_denies(registry, fake_write):
    def boom(_):
        raise RuntimeError

    result = PermissionGate(registry, live(), confirm=boom).execute("fake_write", {"path": "a"})
    assert result.decision.verdict is Verdict.DENIED
    assert fake_write.calls == []


def test_require_confirmation_false_skips_prompt(registry, fake_write):
    gate = PermissionGate(registry, live(require_confirmation=False))
    assert gate.execute("fake_write", {"path": "a"}).ok
    assert fake_write.calls == [("a", False)]


def test_per_call_dry_run_overrides_config(registry, fake_write):
    gate = PermissionGate(registry, live(), confirm=lambda r: True)
    gate.execute("fake_write", {"path": "a"}, dry_run=True)
    assert fake_write.calls == [("a", True)]


def test_invalid_input_fails_before_prompt(registry):
    prompts = []
    gate = PermissionGate(registry, live(), confirm=lambda r: prompts.append(r) or True)
    result = gate.execute("fake_write", {"wrong": 1})
    assert "invalid input" in result.error
    assert result.decision is None and prompts == []


def test_unknown_skill_returns_error(registry):
    result = PermissionGate(registry).execute("nope", {})
    assert not result.ok and "Unknown skill" in result.error


def test_authorize_unknown_raises(registry):
    with pytest.raises(UnknownSkillError):
        PermissionGate(registry).authorize("nope", {})


def test_skill_exception_is_captured(registry):
    result = PermissionGate(registry).execute("crash", {"text": "x"})
    assert not result.ok and "RuntimeError: kaput" in result.error


def test_events_published(registry):
    bus = EventBus()
    topics = []
    bus.subscribe("*", lambda e: topics.append((e.topic, e.payload.get("skill"))))
    PermissionGate(registry, bus=bus).execute("echo", {"text": "x"})
    assert topics == [(TOPIC_DECIDED, "echo"), (TOPIC_FINISHED, "echo")]
