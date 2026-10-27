"""The deterministic REGRESSION stage (docs/6_FLOW.md §4 W4, §5 — P1b).

Before this module there was no regression check: a run could break a test that passed
before it started and still claim "requirement satisfied". The stage here is entirely
deterministic and model-free:

* the task's **VISIBLE test suite** — the test files present in the staged source view
  (`harness.staging.is_test_path`; the grader's own suite is withheld by the blind
  protocol) — is run on the **pristine staged source BEFORE the run's first write**, and
  every test id that PASSES is recorded as the baseline;
* the SAME suite is run again on the **final revision**; every id that passed at the
  baseline and does NOT pass now is a **REGRESSION**;
* a regression is a hard input to the single claim gate (:func:`harness.leaf.claim_decision`,
  via its ``regressions`` parameter), recorded with the failing ids and the suite output.

Honesty (docs/6_FLOW.md §11 H6): only the VISIBLE suite can be checked — the grader's own suite never
enters the run — so a "no regression" verdict is PARTIAL and the external grader is the final
word. A suite that could not be OBSERVED (no machine-readable report, a transport error, a
refused run) is recorded as **unobservable**, never as "no regression".

The suite is run through the SAME seam the leaf uses (``run_suite``: ``workdir -> ShapedResult``
with a :class:`~harness.gate_report.GateReport`), so the module reuses the existing pytest
runner and gate-report machinery (``harness/exec.py`` + ``harness/gate_report.py``) instead of
shelling out by hand.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from harness.gate_report import CANARY_PREFIX, GateReport
from harness.staging import is_test_path

__all__ = [
    "RegressionCheck",
    "VisibleSuiteBaseline",
    "capture_baseline",
    "check_regression",
    "visible_test_files",
]

#: A suite runner: the leaf's ``run_tests`` seam (``workdir -> ShapedResult``), sync or async.
SuiteRunner = Callable[[Path], "Any | Awaitable[Any]"]


@dataclass(frozen=True)
class VisibleSuiteBaseline:
    """The visible suite's baseline on the pristine staged source.

    ``passed_ids`` are the test ids that PASSED (canary ids excluded — the per-run canary
    is a harness artifact, not a visible test). ``observable`` is True only when the suite
    really ran and produced a machine-readable report holding at least one testcase.
    """

    passed_ids: tuple[str, ...] = ()
    observable: bool = False
    detail: str = ""
    gate: GateReport | None = None


@dataclass(frozen=True)
class RegressionCheck:
    """The visible suite on the final revision compared with the baseline.

    ``regressions`` are the ids that passed at the baseline and do NOT pass now — an empty
    tuple means NO regression **only when** ``observable`` is True. ``observable`` is False
    for a suite that could not be observed on either run (recorded as unobservable, never
    as "no regression"); ``output`` is the final run's shaped pytest output.
    """

    regressions: tuple[str, ...] = ()
    observable: bool = False
    detail: str = ""
    baseline_ids: tuple[str, ...] = ()
    passed_ids: tuple[str, ...] = ()
    output: tuple[str, ...] = ()
    gate: GateReport | None = None

    @property
    def clean(self) -> bool:
        """True only when the check OBSERVED the suite and found no regression."""
        return self.observable and not self.regressions


def _is_canary(node_id: str) -> bool:
    """True for the per-run gate canary node id (a harness artifact, never a visible test)."""
    file_part = node_id.split("::", 1)[0]
    return CANARY_PREFIX in PurePosixPath(file_part).name


def visible_test_files(workdir: Path | str) -> tuple[str, ...]:
    """The test files present in the staged view (repo-relative, sorted, canary excluded).

    The blind staging withholds every grader-owned test path, so these are exactly the
    tests a run may see and run on its own.
    """
    root = Path(workdir)
    if not root.is_dir():
        return ()
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if is_test_path(rel) and CANARY_PREFIX not in path.name:
            found.append(rel)
    return tuple(found)


def _suite_passed_ids(res: Any) -> tuple[str, ...]:
    """The passing test ids in a suite result, with the per-run canary filtered out."""
    gate = getattr(res, "gate", None)
    if gate is None:
        return ()
    return tuple(nid for nid in gate.passed_ids if not _is_canary(nid))


def _suite_output(res: Any) -> tuple[str, ...]:
    return tuple(getattr(res, "excerpts", []) or ())


def _observed(res: Any) -> tuple[bool, GateReport | None]:
    """True only when a genuine machine-readable report was produced (>=1 testcase)."""
    gate = getattr(res, "gate", None)
    return bool(gate is not None and gate.observed), gate


def _gate_detail(gate: GateReport | None) -> str:
    if gate is None:
        return "no machine-readable pytest report"
    if not gate.observed:
        return f"{gate.anomaly or 'unobserved'}: {gate.detail}"
    if gate.anomaly:
        return f"{gate.anomaly}: {gate.detail}"
    return "the suite ran and reported green"


async def _run(run_suite: SuiteRunner, workdir: Path) -> Any:
    result = run_suite(workdir)
    if inspect.isawaitable(result):
        return await result
    return result


async def capture_baseline(workdir: Path | str, run_suite: SuiteRunner) -> VisibleSuiteBaseline:
    """Run the visible suite on the pristine source and record which ids pass.

    Returns ``observable=False`` (and no ids) when the staged view ships no visible test
    file, or when the run produced no trustworthy report — either way the result says the
    suite could not be observed rather than pretending the baseline was green.
    """
    root = Path(workdir)
    if not visible_test_files(root):
        return VisibleSuiteBaseline(
            observable=False,
            detail="no visible test file is present in the staged source")
    res = await _run(run_suite, root)
    observable, gate = _observed(res)
    passed = _suite_passed_ids(res)
    detail = _gate_detail(gate)
    return VisibleSuiteBaseline(passed_ids=passed, observable=observable, detail=detail,
                                gate=gate)


async def check_regression(baseline: VisibleSuiteBaseline, workdir: Path | str,
                           run_suite: SuiteRunner) -> RegressionCheck:
    """Run the same visible suite on the final revision and compare with the baseline.

    Every baseline-passing id that does not pass now is a regression. An unobservable
    baseline or an unobservable final run makes the whole check unobservable (``observable``
    is False), so an empty ``regressions`` there is never read as "no regression".
    """
    root = Path(workdir)
    if not baseline.observable:
        return RegressionCheck(
            observable=False, baseline_ids=baseline.passed_ids,
            detail=("the baseline suite could not be observed: "
                    f"{baseline.detail or 'no report'}"))
    res = await _run(run_suite, root)
    observable, gate = _observed(res)
    output = _suite_output(res)
    if not observable:
        return RegressionCheck(
            observable=False, baseline_ids=baseline.passed_ids, output=output, gate=gate,
            detail=("the visible suite could not be observed on the final revision: "
                    f"{_gate_detail(gate)}"))
    passed = _suite_passed_ids(res)
    passed_set = set(passed)
    regressions = tuple(nid for nid in baseline.passed_ids if nid not in passed_set)
    if regressions:
        detail = (f"{len(regressions)} regression(s) against the baseline: "
                  + ", ".join(regressions))
    else:
        detail = (f"no regression: all {len(baseline.passed_ids)} baseline test id(s) "
                  "still pass")
    return RegressionCheck(regressions=regressions, observable=True, detail=detail,
                           baseline_ids=baseline.passed_ids, passed_ids=tuple(sorted(passed)),
                           output=output, gate=gate)
