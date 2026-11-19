import pytest
from pydantic import BaseModel, ValidationError

from aegis.core.registry import (
    RegistryError,
    SkillBlockedError,
    SkillDisabledError,
    SkillRegistry,
    UnknownSkillError,
)
from aegis.models.config import SkillOverride, SkillsConfig
from aegis.models.skill import RiskLevel, Skill


def test_register_and_get(echo):
    reg = SkillRegistry()
    reg.register(echo)
    assert reg.get("echo") is echo
    assert "echo" in reg
    assert reg.names() == ["echo"]


def test_duplicate_rejected(echo):
    reg = SkillRegistry()
    reg.register(echo)
    with pytest.raises(RegistryError, match="already"):
        reg.register(type(echo)())


def test_unknown_skill():
    with pytest.raises(UnknownSkillError):
        SkillRegistry().get("nope")


class Empty(BaseModel):
    pass


def _make_skill(**overrides):
    attrs = {
        "name": "ok_name",
        "description": "desc",
        "risk": RiskLevel.SAFE,
        "input_model": Empty,
        "output_model": Empty,
        "run": lambda self, data, *, dry_run: Empty(),
    }
    attrs.update(overrides)
    return type("Dyn", (Skill,), attrs)()


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"name": "Bad-Name"}, "Invalid skill name"),
        ({"description": "  "}, "description"),
        ({"risk": "safe"}, "RiskLevel"),
        ({"input_model": dict}, "input_model"),
    ],
)
def test_invalid_definitions_rejected(overrides, match):
    with pytest.raises(RegistryError, match=match):
        SkillRegistry().register(_make_skill(**overrides))


def test_describe_exposes_schema_and_risk(echo, fake_write):
    reg = SkillRegistry()
    reg.register(fake_write)
    reg.register(echo)
    infos = reg.describe()
    assert [i.name for i in infos] == ["echo", "fake_write"]
    assert infos[0].input_schema["properties"]["text"]["type"] == "string"
    assert infos[1].risk is RiskLevel.CONFIRM


def test_enabled_list_restricts(echo, fake_write):
    reg = SkillRegistry(SkillsConfig(enabled=["echo"]))
    reg.register(echo)
    reg.register(fake_write)
    assert reg.names() == ["echo"]
    with pytest.raises(SkillDisabledError):
        reg.get("fake_write")


def test_override_can_disable(echo):
    reg = SkillRegistry(SkillsConfig(overrides={"echo": SkillOverride(enabled=False)}))
    reg.register(echo)
    assert "echo" not in reg


def test_override_can_raise_risk(echo):
    reg = SkillRegistry(SkillsConfig(overrides={"echo": SkillOverride(risk=RiskLevel.CONFIRM)}))
    reg.register(echo)
    assert reg.effective_risk("echo") is RiskLevel.CONFIRM


def test_override_cannot_lower_risk(fake_write):
    cfg = SkillsConfig(overrides={"fake_write": SkillOverride(risk=RiskLevel.SAFE)})
    with pytest.raises(RegistryError, match="cannot lower"):
        SkillRegistry(cfg).register(fake_write)


def test_execute_validates_input_and_runs(echo):
    reg = SkillRegistry()
    reg.register(echo)
    assert reg.execute("echo", {"text": "hi"}, dry_run=False).text == "hi"
    with pytest.raises(ValidationError):
        reg.execute("echo", {}, dry_run=False)


def test_execute_refuses_blocked(danger):
    reg = SkillRegistry()
    reg.register(danger)
    with pytest.raises(SkillBlockedError):
        reg.execute("danger", {"text": "x"}, dry_run=True)
    assert danger.called is False


def test_execute_validates_output():
    class Out(BaseModel):
        n: int

    skill = _make_skill(output_model=Out, run=lambda self, data, *, dry_run: {"n": "bad"})
    reg = SkillRegistry()
    reg.register(skill)
    with pytest.raises(ValidationError):
        reg.execute("ok_name", {}, dry_run=False)
