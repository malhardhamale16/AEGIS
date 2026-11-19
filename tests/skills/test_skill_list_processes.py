import pytest

from aegis.models.config import ProcessListSettings
from aegis.models.skill import SkillError
from aegis.skills.list_processes import (
    TASKLIST_COMMAND,
    ListProcessesInput,
    ListProcessesSkill,
    parse_tasklist_csv,
)

SAMPLE = (
    '"System Idle Process","0","Services","0","8 K"\r\n'
    '"chrome.exe","4120","Console","1","215,432 K"\r\n'
    '"Code.exe","900","Console","1","98.110 K"\r\n'
    '"chrome.exe","88","Console","1","1,024 K"\r\n'
)


def skill(output=SAMPLE, **settings):
    calls = []

    def runner(args):
        calls.append(tuple(args))
        return output

    s = ListProcessesSkill(ProcessListSettings(**settings), runner=runner)
    s.calls = calls
    return s


def test_parse_handles_locale_separators():
    procs = parse_tasklist_csv(SAMPLE)
    assert [(p.name, p.pid, p.memory_kb) for p in procs][1:3] == [
        ("chrome.exe", 4120, 215432),
        ("Code.exe", 900, 98110),
    ]


def test_parse_skips_garbage_rows():
    assert parse_tasklist_csv('INFO: No tasks\r\n"a","x","s","0","1 K"\r\n') == []


def test_lists_sorted_and_calls_tasklist():
    s = skill()
    out = s.run(ListProcessesInput(), dry_run=False)
    assert [p.name for p in out.processes] == [
        "chrome.exe",
        "chrome.exe",
        "Code.exe",
        "System Idle Process",
    ]
    assert [p.pid for p in out.processes[:2]] == [88, 4120]
    assert s.calls == [TASKLIST_COMMAND]


def test_filter_and_limit():
    out = skill(max_results=1).run(ListProcessesInput(name_contains="CHROME"), dry_run=False)
    assert out.total == 2 and len(out.processes) == 1 and out.truncated


def test_empty_output_raises():
    with pytest.raises(SkillError):
        skill(output="").run(ListProcessesInput(), dry_run=False)
