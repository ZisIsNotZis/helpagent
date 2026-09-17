"""Check pipeline (TEST_PLAN §3.3, DESIGN §4.5, KERNEL_API §3.4 — M3).

Pin the ladder contract: survivor rule (≤2 fix passes), tool-fight FAIL_PATTERN,
rollback on parse survivors, finding-level type-check filtering, config rejection
of unsound scoping, intent tier-1, secret-filtered diffs, and the FP-4 rule family
(cross-file name resolution is harness work, never the model's).
"""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.checks import CheckConfig, CheckFinding, check_write, diagnose_test_output
from harness.runner import ledger_entries, reset_ledger_for_tests


def _run(workdir: Path, path: str, content: str, **kw):
    return asyncio.run(check_write(workdir, path, content, **kw))


def _no_types() -> CheckConfig:
    # trim the ladder to the stages under test — mypy is exercised by its own case
    return CheckConfig(stages=("autofix", "parse", "rules"))


# ---------------------------------------------------------------- fix passes


async def _stuck_fixer(workdir: Path, path: str, pass_no: int):
    # pass 0 = collect-only inventory; the finding is present before and after
    # every fix pass (the fixer cannot fix it) — never oscillates
    return False, [
        CheckFinding(stage="autofix", path=path, line=1, code="E501",
                     message="line too long", fixable=False)
    ]


def test_autofix_stops_after_two_passes(tmp_path: Path):
    (tmp_path / "mod.py").write_text("x = 1\n")
    res = _run(tmp_path, "mod.py", "x = 1  # unchanged\n", config=_no_types(),
               autofix=_stuck_fixer)
    assert res.fix_passes_used == 2
    assert res.verdict == "escalated" and res.ok is True   # write stays; script retries
    assert (tmp_path / "mod.py").read_text() == "x = 1  # unchanged\n"
    assert [f.code for f in res.findings] == ["E501"]


def test_tool_fight_oscillation_records_fail_pattern(tmp_path: Path):
    """Fixer A reintroduces B's finding and vice versa → after 2 passes escalate;
    the ledger records the tool_fight survivor (DESIGN §4.5 FAIL_PATTERN)."""

    flip = {"n": -1}

    async def fighting_fixer(workdir: Path, path: str, pass_no: int):
        # pass 0 reports the ORIGINAL finding (E501); pass 1 "fixes" it into F841;
        # pass 2 reintroduces E501 — the oscillation the FAIL_PATTERN rule exists for
        flip["n"] += 1
        code = "E501" if flip["n"] != 1 else "F841"
        return False, [CheckFinding(stage="autofix", path=path, line=1,
                                    code=code, message="alternating")]

    (tmp_path / "mod.py").write_text("x = 1\n")
    reset_ledger_for_tests()
    res = _run(tmp_path, "mod.py", "x = 2\n", config=_no_types(), autofix=fighting_fixer)
    assert res.fix_passes_used == 2 and res.verdict == "escalated"
    kinds = [e["kind"] for e in ledger_entries()]
    assert "tool_fight_survivor" in kinds


def test_fixer_clean_on_first_pass_runs_one_pass(tmp_path: Path):
    calls = {"n": 0}

    async def clean_fixer(workdir: Path, path: str, pass_no: int):
        calls["n"] += 1
        return True, []

    (tmp_path / "mod.py").write_text("x = 1\n")
    res = _run(tmp_path, "mod.py", "x = 1\n", config=_no_types(), autofix=clean_fixer)
    # the real pin: one pass, no findings, verdict is NOT escalated
    assert res.fix_passes_used == 1
    assert res.verdict == "clean" and res.ok is True


# ---------------------------------------------------------------- rollback


def test_unfixable_write_rolls_back_worktree(tmp_path: Path):
    """Parse survivor ⇒ byte-restore; the work tree never holds a non-parsing file
    (DESIGN §4.5, KERNEL_API §3.4 unfixable ⇒ rollback)."""
    (tmp_path / "mod.py").write_text("x = 1\n")
    broken = "def f(:\n    return 1\n"
    res = _run(tmp_path, "mod.py", broken, config=CheckConfig(stages=("autofix", "parse")))
    assert res.ok is False and res.verdict == "rolled_back" and res.rolled_back is True
    assert (tmp_path / "mod.py").read_text() == "x = 1\n"
    assert any(f.stage == "parse" for f in res.findings)


def test_new_file_parse_survivor_is_removed_entirely(tmp_path: Path):
    res = _run(tmp_path, "new_mod.py", "def g(:\n  pass\n",
               config=CheckConfig(stages=("autofix", "parse")))
    assert res.rolled_back is True
    assert not (tmp_path / "new_mod.py").exists()


def test_path_escape_is_a_shaped_policy_result(tmp_path: Path):
    res = _run(tmp_path, "../outside.py", "x = 1\n", config=_no_types())
    assert res.ok is False and res.verdict == "rolled_back"
    assert not (tmp_path.parent / "outside.py").exists()
    assert any(f.code == "policy-path-escape" for f in res.findings)


# ---------------------------------------------------------------- typecheck


def test_type_check_filters_at_finding_level(tmp_path: Path):
    """A write that breaks a CALLER in an untouched file keeps the finding
    (finding-level, not invocation-level scoping, DESIGN §4.5); pre-existing
    untouched-file noise never blocks."""
    (tmp_path / "mod.py").write_text("def greet(x):\n    return x\n")
    (tmp_path / "caller.py").write_text("from mod import greet\n\n"
                                        "def main() -> int:\n    return greet(3)\n")
    (tmp_path / "other.py").write_text("bad = 1 + 'x'\n")   # pre-existing noise
    res = _run(tmp_path, "mod.py", "def greet(x: str) -> str:\n    return x\n")
    by_file = {f.path for f in res.findings if f.stage == "typecheck"}
    assert "caller.py" in by_file          # the write broke this caller → survives
    assert "mod.py" not in by_file         # the touched file itself is clean
    assert "other.py" not in by_file       # pre-existing noise filtered by baseline


def test_touched_files_only_scoping_is_rejected():
    with pytest.raises(ValidationError):
        CheckConfig(scope_mode="invocation")


# ---------------------------------------------------------------- real ruff


def test_ruff_autofix_real_fixes_lint(tmp_path: Path):
    res = _run(tmp_path, "mod.py", "import os\nx = 1\n",
               config=CheckConfig(stages=("autofix", "parse")))
    assert res.ok is True
    assert "import os" not in (tmp_path / "mod.py").read_text()
    assert res.verdict == "auto_fixed"


def test_clean_write_is_clean(tmp_path: Path):
    (tmp_path / "mod.py").write_text("x = 1\n")
    res = _run(tmp_path, "mod.py", "x = 1\n", config=_no_types())
    assert res.ok is True and res.verdict == "clean" and res.findings == []


# ---------------------------------------------------------------- intent


def test_source_intent_write_into_test_file_is_rolled_back(tmp_path: Path):
    (tmp_path / "test_mod.py").write_text("def test_ok():\n    assert True\n")
    res = _run(tmp_path, "test_mod.py", "def test_ok():\n    assert False\n",
               intent="source", config=_no_types())
    assert res.rolled_back is True and res.ok is False
    assert any(f.code == "intent-test-write" for f in res.findings)
    assert (tmp_path / "test_mod.py").read_text() == "def test_ok():\n    assert True\n"


def test_test_intent_write_is_allowed(tmp_path: Path):
    res = _run(tmp_path, "tests/test_new.py", "def test_new():\n    assert True\n",
               intent="test", config=_no_types())
    assert res.ok is True and res.verdict == "clean"


# ---------------------------------------------------------------- rule library


def test_nameerror_rule_diagnoses_from_repo():
    repo = {"minirepo/errors.py": "class MinirepoError(Exception):\n    pass\n"}
    out = diagnose_test_output(
        ["E       NameError: name 'MinirepoError' is not defined"], repo)
    assert out and out[0].code == "FP-4-nameerror-source"
    assert out[0].path == "minirepo/errors.py"
    assert "add the import" in out[0].message


def test_nameerror_rule_unresolved_reports_misspelling():
    out = diagnose_test_output(
        ["E       NameError: name 'MinirepoError' is not defined"], {"a.py": "x = 1\n"})
    assert out and out[0].code == "FP-4-nameerror-unresolved"


def test_import_rule_local_module():
    repo = {"minirepo/calc.py": "def divide(a, b):\n    return a / b\n"}
    out = diagnose_test_output(
        ["E   ModuleNotFoundError: No module named 'minirepo.calc'"], repo)
    assert out and out[0].code == "FP-4-import-source" and out[0].path == "minirepo/calc.py"


def test_import_rule_external_module():
    out = diagnose_test_output(
        ["E   ModuleNotFoundError: No module named 'requests'"], {"a.py": "x = 1\n"})
    assert out and out[0].code == "FP-4-import-external"


# ---------------------------------------------------------------- secret filter


def test_diff_is_secret_filtered_at_the_boundary(tmp_path: Path):
    res = _run(tmp_path, "cfg.py", "password = 'hunter2'\n", config=_no_types())
    assert res.diff_redactions >= 1
    assert "hunter2" not in res.diff
    assert "[REDACTED]" in res.diff


# ---------------------------------------------------------------- FP-9 pin


def test_lint_stage_pins_correctness_rules_no_style_drift(tmp_path: Path):
    """FP-9: the ladder's rule set is pinned to E9,F — a style-rule magnet file
    (naive datetime, DTZ007 under ruff 0.16 defaults) must NOT escalate, while
    real defects (F821 undefined name) still do. The correct T-17 fix was
    flagged 5x by style rules and the model chased them into breaking logic
    (sweep 20260917T100148Z)."""
    naive = "import datetime\n\n\ndef parse(s):\n    return datetime.datetime.strptime(s, '%H:%M')\n"
    res = _run(tmp_path, "mod.py", naive, config=_no_types())
    assert not any(f.code == "DTZ007" for f in res.findings), res.findings
    undefined = "def f():\n    return undefined_name\n"
    res2 = _run(tmp_path, "mod2.py", undefined, config=_no_types())
    assert any(f.code == "F821" for f in res2.findings)
