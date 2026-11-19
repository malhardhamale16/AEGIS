"""Built-in skills wired into the registry and permission gate."""

from aegis.core.config import load_config
from aegis.core.permission import PermissionGate
from aegis.core.registry import SkillRegistry
from aegis.models.config import SafetyConfig, SkillsConfig, WriteFileSettings
from aegis.models.permission import Verdict
from aegis.models.skill import RiskLevel
from aegis.skills import builtin_skills, register_builtin_skills

EXPECTED = {
    "clipboard_read": RiskLevel.SAFE,
    "file_search": RiskLevel.SAFE,
    "list_processes": RiskLevel.SAFE,
    "open_app": RiskLevel.SAFE,
    "system_info": RiskLevel.SAFE,
    "web_open": RiskLevel.SAFE,
    "write_file": RiskLevel.CONFIRM,
}


def test_all_builtins_register_with_repo_config(repo_configs):
    settings = load_config(repo_configs)
    reg = register_builtin_skills(SkillRegistry(settings.skills), settings.skills)
    assert {i.name: i.risk for i in reg.describe()} == EXPECTED


def test_every_skill_has_description_and_schemas():
    for skill in builtin_skills(SkillsConfig()):
        assert skill.description.strip()
        assert skill.input_model.model_json_schema()["type"] == "object"
        assert skill.output_model.model_json_schema()["type"] == "object"


def _gate(tmp_path, **safety):
    cfg = SkillsConfig(write_file=WriteFileSettings(allowed_roots=[tmp_path]))
    reg = register_builtin_skills(SkillRegistry(cfg), cfg)
    return PermissionGate(reg, SafetyConfig(**safety), confirm=lambda r: True)


def test_write_file_through_gate_defaults_to_dry_run(tmp_path):
    result = _gate(tmp_path).execute("write_file", {"path": "x.txt", "content": "hi"})
    assert result.ok and result.output["dry_run"] is True
    assert not (tmp_path / "x.txt").exists()


def test_write_file_through_gate_live_after_confirmation(tmp_path):
    result = _gate(tmp_path, dry_run=False).execute(
        "write_file", {"path": "x.txt", "content": "hi"}
    )
    assert result.decision.verdict is Verdict.ALLOWED and result.decision.confirmed
    assert (tmp_path / "x.txt").read_text() == "hi"


def test_skill_error_surfaces_as_result_error(tmp_path):
    result = _gate(tmp_path, dry_run=False).execute(
        "write_file", {"path": "../out.txt", "content": "x"}
    )
    assert not result.ok and "SkillError" in result.error
