from aegis.skills.system_info import SystemInfoInput, SystemInfoSkill


def test_reports_memory_from_probe():
    skill = SystemInfoSkill(memory_probe=lambda: (16 * 1024**3, 4 * 1024**3))
    out = skill.run(SystemInfoInput(), dry_run=False)
    assert out.memory_total_mb == 16 * 1024
    assert out.memory_available_mb == 4 * 1024
    assert out.python_version.count(".") == 2
    assert out.os


def test_memory_unknown_is_none():
    out = SystemInfoSkill(memory_probe=lambda: None).run(SystemInfoInput(), dry_run=False)
    assert out.memory_total_mb is None and out.memory_available_mb is None
