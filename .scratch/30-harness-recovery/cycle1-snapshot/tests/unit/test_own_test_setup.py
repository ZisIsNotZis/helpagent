"""Own-test setup failures must not drive source edits or establish discrimination.

Use the actual pytest/JUnit gate with a scripted model, never a model server. These
checks distinguish missing imports, syntax and fixture setup from assertion/source red.
"""

import asyncio
from pathlib import Path

import pytest

from harness.budget import Budget
from harness.exec import ShapedResult
from harness.fake_model import FakeModelRunner
from harness.leaf import (
    DeclaredTestCase,
    JudgeVerdict,
    LeafSpec,
    _default_run_tests,
    _own_test_setup_problem,
    run_leaf,
)
from harness.runner import reset_ledger_for_tests


TEST_PATH = "tests/test_generated.py"
SOURCE_PATH = "pkg/calc.py"
BROKEN_SOURCE = "def result():\n    return 0\n"
FIXED_SOURCE = "def result():\n    return 42\n"
VALID_TEST = "from pkg.calc import result\n\ndef test_ac1_result():\n    assert result() == 42\n"
MISSING_IMPORT_TEST = "def test_ac1_result():\n    assert result() == 42\n"
SYNTAX_TEST = "def test_ac1_result(:\n    assert True\n"
MISSING_FIXTURE_TEST = "def test_ac1_result(unknown_fixture):\n    assert unknown_fixture == 42\n"


def _write(path: str, content: str) -> dict:
    return {"status": "ok", "comment": "write the declared artifact",
            "file_path": path, "content": content}


def _stage(workdir: Path, source: str, test: str | None = None) -> None:
    source_path = workdir / SOURCE_PATH
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source)
    if test is not None:
        test_path = workdir / TEST_PATH
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test)


def _spec(source: str) -> LeafSpec:
    return LeafSpec(
        goal="make result() return 42", files={SOURCE_PATH: source},
        acs=["result() returns 42"], interfaces=["pkg.calc.result() -> int"],
        planned_tests=(DeclaredTestCase("AC-1", TEST_PATH, ("test_ac1_result",)),),
        verification_reason="a returned-value assertion pins the goal",
    )


def _run(workdir, source, responses, **kwargs):
    reset_ledger_for_tests()
    _stage(workdir, source)
    model = FakeModelRunner({"write_test": responses})
    events = []
    outcome = asyncio.run(run_leaf(
        model, _spec(source), workdir, Budget(calls=8, deadline_ts=2_000_000_000),
        on_event=lambda kind, body: events.append((kind, body)),
        verification_mode="test", **kwargs))
    test_calls = [c for c in model.calls("write_test") if c.step_type == "write_test"]
    return outcome, model, test_calls, events


@pytest.mark.parametrize(("test", "layer"), [
    (MISSING_IMPORT_TEST, "name"), (SYNTAX_TEST, "syntax"),
    (MISSING_FIXTURE_TEST, "fixture"),
])
def test_own_test_setup_problem_uses_real_gate_output(tmp_path, test, layer):
    _stage(tmp_path, BROKEN_SOURCE, test)
    result = asyncio.run(_default_run_tests(tmp_path))
    assert result.gate.observed and not result.gate.green
    actual, detail = _own_test_setup_problem(TEST_PATH, test, result, (SOURCE_PATH,))
    assert actual == layer
    assert detail


@pytest.mark.parametrize("test", [MISSING_IMPORT_TEST, SYNTAX_TEST, MISSING_FIXTURE_TEST])
def test_run_leaf_repairs_setup_before_implementation_and_reproves_red(tmp_path, test):
    outcome, model, test_calls, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, test), _write(TEST_PATH, VALID_TEST),
         _write(SOURCE_PATH, FIXED_SOURCE)])
    assert len(test_calls) == 2
    assert len(model.calls("implement_write")) == 1
    assert "not behavior evidence" in test_calls[1].artifacts["failure_output"]
    assert SOURCE_PATH in test_calls[1].artifacts["repo_files"]
    assert (tmp_path / SOURCE_PATH).read_text() == FIXED_SOURCE
    kinds = [kind for kind, _ in events]
    assert kinds.index("self_test_setup_invalid") < kinds.index("self_test_written")
    assert "self_test_setup_rechecked" in kinds
    assert outcome.own_test_discriminating == [f"{TEST_PATH}::test_ac1_result"]
    assert outcome.test_rewrites == 0  # no valid red target existed before setup repair
    assert outcome.claimed is True


@pytest.mark.parametrize("repair", [MISSING_IMPORT_TEST, SYNTAX_TEST])
def test_run_leaf_unrepaired_setup_stops_without_source_churn(tmp_path, repair):
    outcome, model, _, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, repair)])
    assert not model.calls("implement_write")
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE
    assert not outcome.claimed
    assert outcome.stop_reason == "self-test-invalid"
    assert outcome.state == "uncertain"
    assert outcome.attempts == []
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert any(kind == "self_test_invalid" for kind, _ in events)
    assert (tmp_path / TEST_PATH).is_file()  # invalid artifact remains inspectable


@pytest.mark.parametrize("source", [
    BROKEN_SOURCE,
    "def result():\n    return unknown_source_name\n",
], ids=["assertion", "source-name"])
def test_run_leaf_assertion_and_source_name_error_remain_implementation_feedback(tmp_path, source):
    outcome, model, test_calls, events = _run(
        tmp_path, source, [_write(TEST_PATH, VALID_TEST), _write(SOURCE_PATH, FIXED_SOURCE)],
        judge=lambda request: JudgeVerdict(
            implementation_wrong=True, reason="result returns the wrong value",
            defect="result must return 42"))
    assert len(test_calls) == 1
    assert not any(kind == "self_test_setup_invalid" for kind, _ in events)
    assert len(model.calls("implement_write")) == 1
    assert outcome.claimed


@pytest.mark.parametrize("source", [
    "def result(:\n    return 42\n",
    "def different_api():\n    return 42\n",
], ids=["source-syntax", "missing-source-api"])
def test_source_import_collection_errors_are_not_automatic_test_setup_blame(tmp_path, source):
    # Ownership of a missing imported API needs goal/visible-interface evidence, not
    # an automatic rewrite of the importing test. Its controller route remains P1b.
    _stage(tmp_path, source, VALID_TEST)
    result = asyncio.run(_default_run_tests(tmp_path))
    assert result.gate.observed and not result.gate.green
    assert _own_test_setup_problem(TEST_PATH, VALID_TEST, result, (SOURCE_PATH,)) == ("", "")


def test_run_leaf_setup_repair_with_missing_report_cannot_reuse_invalid_red(tmp_path):
    calls = 0

    async def lose_repair_report(workdir):
        nonlocal calls
        calls += 1
        if calls == 1:
            return await _default_run_tests(workdir)
        return ShapedResult(command=["pytest"], exit=1, verdict="failed")

    outcome, model, _, _ = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, VALID_TEST)],
        run_tests=lose_repair_report)
    assert not outcome.claimed
    assert not model.calls("implement_write")
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)


def test_run_leaf_repaired_test_green_on_pristine_cannot_claim(tmp_path):
    green_test = VALID_TEST.replace("== 42", "== 0")
    outcome, model, _, _ = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, green_test),
         _write(TEST_PATH, green_test)])
    assert not outcome.claimed
    assert not model.calls("implement_write")
    assert outcome.own_test_discriminating == []
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE
