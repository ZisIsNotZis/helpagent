"""The deterministic REGRESSION stage (FLOW §4 W4, §5 — P1b).

Three facts are pinned here, exactly the ones the stage exists for:

* a test that passed on the pristine source and no longer passes is a REGRESSION;
* a test the run ADDED (absent from the baseline) is never a regression;
* a suite that could NOT run is recorded as UNOBSERVABLE, never as "no regression".

The suite is driven through the leaf's own runner seam, so no pytest process runs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from harness.exec import ShapedResult
from harness.gate_report import CANARY_PREFIX, GateReport
from harness.regression import (
    capture_baseline,
    check_regression,
    visible_test_files,
)

VISIBLE = "tests/test_visible.py::test_ok"
VISIBLE_TWO = "tests/test_visible.py::test_other"
ADDED = "tests/test_added.py::test_new"


def suite(passed=(), failed=(), *, exit: int | None = 0,
          observed: bool = True) -> ShapedResult:
    """A shaped pytest result carrying a machine-readable gate report."""
    green = exit == 0 and not failed
    gate = GateReport(report_path="(fake)", process_exit=exit, canary="fake",
                      expected_files=(), n_tests=len(passed) + len(failed),
                      n_failed=len(failed), n_errors=0, passed_ids=tuple(passed),
                      failed_ids=tuple(failed), missing=(), observed=observed,
                      anomaly="" if green else "tests-failed",
                      detail="" if green else "1 failure(s)")
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=exit,
                        verdict="ok" if green else "failed",
                        excerpts=[] if green else [f"FAILED {nid}" for nid in failed],
                        gate=gate)


def unobservable() -> ShapedResult:
    """A run that produced no trustworthy report (transport error / policy block)."""
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=None,
                        verdict="transport_error", excerpts=["timed out after 120s"])


def runner(*results):
    """A suite seam returning the scripted results in order (last repeats)."""
    queue = list(results)

    def call(workdir, node_ids=None):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return call


def stage(tmp_path: Path, files: dict) -> None:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------- the three facts


def test_baseline_green_then_red_is_a_regression(tmp_path):
    """A baseline-passing test absent from the final report is a REGRESSION."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE,)))))
    assert baseline.observable is True
    assert baseline.passed_ids == (VISIBLE,)

    check = run(check_regression(baseline, tmp_path, runner(suite(passed=()))))
    assert check.observable is True
    assert check.regressions == (VISIBLE,)
    assert check.clean is False
    assert VISIBLE in check.detail


def test_newly_added_own_test_is_not_a_regression(tmp_path):
    """A test the run ADDED is absent from the baseline, so it can never regress."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE,)))))
    check = run(check_regression(
        baseline, tmp_path, runner(suite(passed=(VISIBLE, ADDED)))))
    assert check.observable is True
    assert check.regressions == ()
    assert check.clean is True


def test_unobservable_final_suite_is_recorded_as_unobservable_not_clean(tmp_path):
    """A suite that could not run is UNOBSERVABLE — never "no regression"."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE,)))))
    check = run(check_regression(baseline, tmp_path, runner(unobservable())))
    assert check.observable is False
    assert check.regressions == ()
    assert check.clean is False                 # empty + unobservable != no regression
    assert "could not be observed" in check.detail


def test_unobservable_baseline_makes_the_whole_check_unobservable(tmp_path):
    """With no trustworthy baseline there is nothing to compare against."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})
    baseline = run(capture_baseline(tmp_path, runner(unobservable())))
    assert baseline.observable is False
    check = run(check_regression(baseline, tmp_path, runner(suite(passed=(VISIBLE,)))))
    assert check.observable is False
    assert check.clean is False
    assert "baseline suite could not be observed" in check.detail


def test_no_visible_suite_is_not_applicable(tmp_path):
    """With no visible test file the baseline is empty and NOT observable."""
    stage(tmp_path, {"pkg/calc.py": "def result():\n    return 0\n"})
    assert visible_test_files(tmp_path) == ()
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE,)))))
    assert baseline.observable is False
    assert baseline.passed_ids == ()
    assert "no visible test file" in baseline.detail


def test_canary_ids_are_never_visible_tests(tmp_path):
    """The per-run gate canary is a harness artifact, not a visible test."""
    stage(tmp_path, {
        "tests/test_visible.py": "def test_ok():\n    assert True\n",
        f"tests/{CANARY_PREFIX}deadbeef.py":
            "def test_gate_canary_deadbeef():\n    assert True\n",
    })
    assert visible_test_files(tmp_path) == ("tests/test_visible.py",)
    canary_id = f"tests/{CANARY_PREFIX}deadbeef.py::test_gate_canary_deadbeef"
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE, canary_id)))))
    assert baseline.passed_ids == (VISIBLE,)          # the canary was filtered out
    # A final run whose canary token differs (every run) never fabricates a regression.
    other = f"tests/{CANARY_PREFIX}cafef00d.py::test_gate_canary_cafef00d"
    check = run(check_regression(baseline, tmp_path, runner(suite(passed=(VISIBLE, other)))))
    assert check.regressions == ()
    assert check.clean is True


def test_a_failing_baseline_test_is_not_a_regression(tmp_path):
    """Only baseline-PASSING ids can regress; a test already red at the baseline cannot."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})
    baseline = run(capture_baseline(tmp_path, runner(suite(passed=(VISIBLE,), failed=(VISIBLE_TWO,)))))
    assert baseline.passed_ids == (VISIBLE,)
    check = run(check_regression(baseline, tmp_path,
                                 runner(suite(passed=(VISIBLE,), failed=(VISIBLE_TWO,)))))
    assert check.regressions == ()


def test_async_runner_is_supported(tmp_path):
    """The seam may be async (the leaf's real runner is)."""
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})

    async def arunner(workdir, node_ids=None):
        return suite(passed=(VISIBLE,))

    baseline = run(capture_baseline(tmp_path, arunner))
    assert baseline.passed_ids == (VISIBLE,)
