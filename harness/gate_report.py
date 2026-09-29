"""Machine-readable pytest gate — the exit status is no longer evidence (ticket 17 F1).

Run-authored code executes INSIDE the gate process: the run's own test imports the
run's source, so a run can make pytest exit 0 before any test runs. An adversarial
pass demonstrated it with ``import atexit, os`` plus
``atexit.register(lambda: os._exit(0))``: both pytest runs exited 0 with no test
summary and the run reached ``claimed=True`` AND ``actual=True`` with the real bug
untouched. This module is the ONE definition of the replacement for both gates (the
leaf's own gate and :mod:`bench.external_score`):

the ONLY green signal is a machine-readable JUnit report that

* exists and parses,
* holds at least one testcase,
* reports zero failures and zero errors,
* contains every EXPECTED test file, with all of its tests passed, and
* contains this run's randomized CANARY node id — a tiny generated test the harness
  writes into the copy it is about to run, named with a per-run random token. A
  fabricated report cannot contain a token it never saw.

Anything else is RED and the consumer records it loudly as ``gate_report_anomaly``
with the detail. The report itself is written to a private ``mkdtemp`` directory
OUTSIDE the repository, so the run's tree never holds the harness's evidence.

A report that exists and parses but says the tests FAILED is a *trustworthy* RED
(``observed=True``), not an anomaly — the self-test step needs exactly that fact to
keep its red target. A missing/unparsable report is an *unobserved* gate: nothing may
be inferred from it, and no gate may call it green.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = [
    "ANOMALIES",
    "CANARY_PREFIX",
    "JUNIT_FAMILY_ARGS",
    "GateReport",
    "JunitCase",
    "canary_node_id",
    "canary_path",
    "canary_source",
    "canary_token",
    "cleanup_report",
    "evaluate_gate",
    "parse_junit",
    "private_report_path",
]

#: pytest's default xunit2 family carries only ``classname``/``name`` per testcase;
#: the legacy xunit1 family also carries the repo-relative ``file`` attribute, which is
#: what the EXPECTED-test-file check matches. Requested explicitly on the command line
#: so a run-owned configuration cannot change it for the grader.
JUNIT_FAMILY_ARGS: tuple[str, ...] = ("-o", "junit_family=xunit1")

#: Every anomaly code means the gate is RED. ``tests-failed`` is the one code that is
#: also a trustworthy observation (a real report that says the tests failed), so a
#: self-test arrival can still use it as its red target.
ANOMALIES: tuple[str, ...] = (
    "report-missing",           # exit status with no report: the forgery shape
    "report-unparsable",
    "report-too-large",
    "no-tests",                 # a report with zero testcases: nothing ran
    "canary-missing",           # the report cannot be this run's evidence
    "canary-failed",
    "no-expected-tests",        # the harness named nothing to require
    "expected-tests-missing",   # an expected test file is absent from the report
    "tests-failed",             # trustworthy RED (also the self-test target)
    "expected-test-not-passed", # an expected test was skipped
    "process-exit",             # a green report contradicted by a nonzero exit
)

#: The generated canary test file name prefix (random token appended).
CANARY_PREFIX = "test_gate_canary_"

#: A single pytest report is a few kB; a hostile one is refused before parsing.
_MAX_REPORT_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class JunitCase:
    """One ``<testcase>`` from a JUnit report."""

    node_id: str
    file: str
    name: str
    outcome: str    # "passed" | "failed" | "error" | "skipped"


@dataclass(frozen=True)
class GateReport:
    """The gate verdict: GREEN iff ``anomaly == ""``.

    ``observed`` is True only when a genuine report was produced (it exists, parses,
    and holds at least one testcase) — a failure in such a report is a trustworthy RED.
    ``missing`` lists the expected test files absent from the report. The exit status is
    kept for the audit trail and is never the green signal.
    """

    report_path: str
    process_exit: int | None
    canary: str
    expected_files: tuple[str, ...]
    n_tests: int
    n_failed: int
    n_errors: int
    passed_ids: tuple[str, ...]
    failed_ids: tuple[str, ...]
    missing: tuple[str, ...]
    observed: bool
    anomaly: str = ""
    detail: str = ""

    @property
    def green(self) -> bool:
        return self.anomaly == ""

    @property
    def structural_anomaly(self) -> bool:
        """True when the anomaly is about the REPORT's trustworthiness.

        ``tests-failed`` is deliberately excluded: a report that exists, parses and
        contains the expected tests and the canary, and says the tests FAILED, is a
        trustworthy RED (the self-test's target) — not a reason to distrust the gate.
        """
        return self.anomaly not in ("", "tests-failed")


# ------------------------------------------------------------------------- canary


def canary_token() -> str:
    """A fresh random token per gate run — a fabricated report cannot guess it."""
    return secrets.token_hex(16)


def _canary_dir(directory: str) -> str:
    """``"."``/``""`` means the repo root; otherwise a normalized relative directory."""
    normalized = str(PurePosixPath(directory))
    return "" if normalized in ("", ".") else normalized


def canary_path(token: str, directory: str = "tests") -> str:
    """The generated canary test's repo-relative path."""
    name = f"{CANARY_PREFIX}{token}.py"
    parent = _canary_dir(directory)
    return f"{parent}/{name}" if parent else name


def canary_node_id(token: str, directory: str = "tests") -> str:
    """The canary's node id — the token must appear in the report for a green."""
    return f"{canary_path(token, directory)}::test_gate_canary_{token}"


def canary_source(token: str) -> str:
    """The canary's source: a trivially passing test whose NAME carries the token."""
    return f"def test_gate_canary_{token}():\n    assert True\n"


# ------------------------------------------------------------------ report paths


def private_report_path(prefix: str = "helpagent-gate-report-") -> Path:
    """A report path in a private ``mkdtemp`` directory OUTSIDE the repository.

    The run never writes here and the run's tree never holds the harness's evidence
    (finding F1).
    """
    return Path(tempfile.mkdtemp(prefix=prefix)) / "report.xml"


def cleanup_report(report_path: Path | str) -> None:
    """Remove the private report directory once it has been parsed."""
    shutil.rmtree(Path(report_path).parent, ignore_errors=True)


# ---------------------------------------------------------------------- parsing


def parse_junit(report_path: Path | str) -> tuple[tuple[JunitCase, ...], str]:
    """Parse a JUnit report. Returns ``(testcases, error)``; ``error`` is ``""`` when
    the XML parsed. A missing/unreadable file is an error too — callers turn that into
    a ``report-missing`` (or ``report-unparsable``) anomaly."""
    path = Path(report_path)
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError, ValueError) as exc:
        return (), f"{type(exc).__name__}: {exc}"
    cases: list[JunitCase] = []
    for node in root.iter("testcase"):
        name = node.get("name", "") or ""
        raw_file = node.get("file", "") or ""
        file = str(PurePosixPath(raw_file)) if raw_file else ""
        node_id = f"{file}::{name}" if file else name
        if node.find("failure") is not None:
            outcome = "failed"
        elif node.find("error") is not None:
            outcome = "error"
        elif node.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        cases.append(JunitCase(node_id=node_id, file=file, name=name, outcome=outcome))
    return tuple(cases), ""


def evaluate_gate(
    report_path: Path | str,
    *,
    canary: str,
    expected_files: tuple[str, ...] | list[str],
    canary_dir: str = "tests",
    process_exit: int | None = None,
) -> GateReport:
    """Turn a pytest report into the gate verdict (GREEN iff ``anomaly == ""``).

    The exit code is carried for the record, never used on its own: a run that exits 0
    without a report is ``report-missing``, and a report missing the expected tests or
    the per-run canary can never be green.
    """
    path = Path(report_path)
    expected = tuple(str(PurePosixPath(rel)) for rel in expected_files)
    base = {"report_path": str(path), "process_exit": process_exit, "canary": canary,
            "expected_files": expected}

    if not path.is_file():
        return GateReport(
            **base, n_tests=0, n_failed=0, n_errors=0, passed_ids=(), failed_ids=(),
            missing=expected, observed=False, anomaly="report-missing",
            detail=(f"no machine-readable pytest report at {path} (process exit "
                    f"{process_exit}); an exit status alone is never a green"))

    try:
        size = path.stat().st_size
    except OSError as exc:
        return GateReport(
            **base, n_tests=0, n_failed=0, n_errors=0, passed_ids=(), failed_ids=(),
            missing=expected, observed=False, anomaly="report-unparsable",
            detail=f"cannot stat the report: {type(exc).__name__}: {exc}")
    if size > _MAX_REPORT_BYTES:
        return GateReport(
            **base, n_tests=0, n_failed=0, n_errors=0, passed_ids=(), failed_ids=(),
            missing=expected, observed=False, anomaly="report-too-large",
            detail=f"report is {size} bytes (> {_MAX_REPORT_BYTES}); refused before parsing")

    cases, error = parse_junit(path)
    if error:
        return GateReport(
            **base, n_tests=0, n_failed=0, n_errors=0, passed_ids=(), failed_ids=(),
            missing=expected, observed=False, anomaly="report-unparsable", detail=error)
    if not cases:
        return GateReport(
            **base, n_tests=0, n_failed=0, n_errors=0, passed_ids=(), failed_ids=(),
            missing=expected, observed=False, anomaly="no-tests",
            detail="the pytest report holds no testcase; nothing was observed")

    passed_ids = tuple(c.node_id for c in cases if c.outcome == "passed")
    failed_ids = tuple(c.node_id for c in cases if c.outcome in ("failed", "error"))
    tested_ids = set(passed_ids) | set(failed_ids)
    n_failed = sum(1 for c in cases if c.outcome == "failed")
    n_errors = sum(1 for c in cases if c.outcome == "error")
    present_files = {c.file for c in cases if c.file}
    missing = tuple(rel for rel in expected if rel not in present_files)
    not_passed = tuple(c.node_id for c in cases
                       if c.file in expected and c.outcome == "skipped")
    # R4 (verification round 6): "present and not failed" is too weak — an expected
    # file with no PASSED case (empty, all-skipped, or a truncated forged report)
    # would otherwise pass. Every expected file must contribute at least one green.
    unverified = tuple(rel for rel in expected
                       if not any(c.file == rel and c.outcome == "passed" for c in cases))
    verdict = dict(base, n_tests=len(cases), n_failed=n_failed, n_errors=n_errors,
                   passed_ids=passed_ids, failed_ids=failed_ids, missing=missing,
                   observed=True)

    canary_id = canary_node_id(canary, canary_dir)
    if canary_id not in {c.node_id for c in cases}:
        return GateReport(
            **verdict, anomaly="canary-missing",
            detail=(f"the per-run canary {canary_id} is absent from the report; the "
                    "report cannot be this run's evidence"))
    if not expected:
        return GateReport(**verdict, anomaly="no-expected-tests",
                          detail="no expected test file was required; refusing to gate")
    if failed_ids:
        return GateReport(
            **verdict, anomaly="tests-failed",
            detail=(f"{n_failed} failure(s), {n_errors} error(s): "
                    + ", ".join(failed_ids[:5])))
    if missing:
        return GateReport(
            **verdict, anomaly="expected-tests-missing",
            detail="expected test file(s) absent from the report: " + ", ".join(missing))
    if canary_id not in tested_ids:
        return GateReport(**verdict, anomaly="canary-failed",
                          detail=f"the canary {canary_id} did not run")
    if not_passed or unverified:
        detail = []
        if not_passed:
            detail.append("skipped: " + ", ".join(not_passed))
        if unverified:
            detail.append("no passing case: " + ", ".join(unverified))
        return GateReport(**verdict, anomaly="expected-test-not-passed",
                          detail="expected test(s) did not pass: " + "; ".join(detail))
    if process_exit != 0:
        return GateReport(
            **verdict, anomaly="process-exit",
            detail=f"the report is green but the pytest process exited {process_exit}")
    return GateReport(**verdict)
