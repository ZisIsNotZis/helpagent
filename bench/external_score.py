#!/usr/bin/env python3
"""External grader: score a run with the corpus tests, outside the harness.

Owner direction 2026-09-29: the corpus checks are the benchmark's own scoring
instrument, invisible to the harness. This module applies whatever the harness
produced onto a PRISTINE copy of the task repo and runs the task's own
``checks.py verify`` there. It never runs inside the harness process and its
result is never fed back into a run.

Round-4 contamination fix (ticket 17): the grader owns a deterministic surface and
must never accept the run's version of it. For every grader-owned path the run
produced — every path :func:`harness.staging.owned_paths` owns (any test path,
``conftest.py`` at any depth, a pytest configuration file, ``sitecustomize.py`` or a
``*.pth`` file) and every path the task's own ``checks.py`` lists in ``UNTOUCHED`` —
the pristine copy is RESTORED (written back, or removed when the run invented it) and
the restore is recorded in :attr:`ExternalScore.restored`. Before this fix a run that
wrote a ``conftest.py`` with a ``pytest_sessionfinish`` hook turned the grader into a
liar: ``claimed=True``, ``actual=True``, nothing fixed.

Round-5 (ticket 17): the run and the grader shared the interpreter path, so a
run-authored top-level module (``json.py`` / ``pytest.py`` / ``_pytest/__init__.py``)
could shadow an import and make the grader exit 0 — a forged TRUE SUCCESS with the
real bug untouched. A produced :func:`harness.staging.shadowing_path` is NEVER applied
(recorded in :attr:`ExternalScore.shadowed`), and the grader's own pytest is launched
with :func:`harness.staging.pytest_isolation_env` so the run's repo root is not on
``sys.path`` (``PYTHONSAFEPATH=1``; the applied env is recorded for audit).

Round-6 (ticket 17 F1): the process exit status stopped being evidence. ``checks.py``
is the corpus's own instrument and is NOT modified; instead this module runs its OWN
report-based verification on the graded copy — pytest with ``--junitxml`` into a
private ``mkdtemp`` outside the repository, plus a per-run randomized canary test —
and ``actual`` is True only when the corpus check exited 0 AND that report is green.
When the corpus check exits 0 but the report gate flags an anomaly (missing or
unparsable report, no testcase, missing corpus test file, missing canary), the grade is
recorded as SUSPECTED CONTAMINATED and ``passed`` is False.

Usage (library):
    from bench.external_score import external_score
    outcome = external_score(task_dir, produced_files, work_root)
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.gate_report import (  # noqa: E402
    JUNIT_FAMILY_ARGS,
    GateReport,
    canary_path,
    canary_source,
    canary_token,
    cleanup_report,
    evaluate_gate,
    private_report_path,
)
from harness.staging import (  # noqa: E402
    PYTEST_ISOLATION_ARGS,
    gate_env,
    owned_paths,
    pytest_isolation_env,
    shadowing_path,
)

__all__ = ["ExternalScore", "external_score", "untouched_paths"]

#: The isolation env entries recorded for audit (the rest of the env is inherited).
_ISOLATION_KEYS = ("PYTHONSAFEPATH", "PYTEST_ADDOPTS")

#: A corpus test file is one pytest collects by default (``test_*.py`` / ``*_test.py``)
#: and that defines at least one ``test_`` function. ``is_test_path`` is the WRITE guard
#: (a tests/ directory component counts there), which is not the same question.
_TEST_FILE_NAME = re.compile(r"^(?:test_.*|.*_test)\.py$", re.IGNORECASE)
_TEST_DEF = re.compile(r"^\s*def\s+test_", re.MULTILINE)


@dataclass
class ExternalScore:
    """Grader verdict plus the raw evidence needed to trust or distrust it."""

    passed: bool
    exit: int
    notes: list[str] = field(default_factory=list)
    work_root: str = ""
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    shadowed: list[str] = field(default_factory=list)   # module-shadow attempts refused
    isolation: dict[str, str] = field(default_factory=dict)  # env applied to the grader
    #: The machine-readable report gate (ticket 17 F1): None when the corpus check
    #: already failed, so no report was needed to deny the green.
    report_gate: GateReport | None = None
    #: True when the corpus check exited 0 but the report gate flagged an anomaly:
    #: the grade cannot be trusted and ``passed`` is False.
    suspected_contaminated_grade: bool = False


def _pristine_copy(task_dir: Path, work_root: Path) -> Path:
    """Copy the whole task dir (checks.py + repo/) so the grader runs unmodified."""
    dest = work_root / task_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task_dir, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  ".untouched.baseline.json"))
    return dest


def _repo_relative_grader_path(rel: str) -> str | None:
    """Map a task-dir-relative ``checks.py`` path onto the repo-relative view we apply.

    ``UNTOUCHED`` entries are relative to the task dir (``"repo/pyproject.toml"``);
    produced files are relative to the staged repo. Only paths under ``repo/`` can
    collide with a produced file, so anything else is ignored.
    """
    parts = PurePosixPath(rel).parts
    if parts and parts[0] == "repo":
        return str(PurePosixPath(*parts[1:]))
    return None


def untouched_paths(task_dir: Path) -> set[str]:
    """The task's own frozen-file list, read from ``checks.py`` without executing it.

    ``checks.py`` is a standalone grader script; parsing its literal ``UNTOUCHED``
    assignment keeps the grader's own definition authoritative and never runs corpus
    code in-process. Returned repo-relative (``"api/__init__.py"``), so both the
    external grader's restore set AND the driver's ``LeafSpec.grader_paths`` use the
    SAME definition of what the run may not touch (ticket 17 F2).
    """
    try:
        tree = ast.parse((Path(task_dir) / "checks.py").read_text())
    except (OSError, SyntaxError):
        return set()
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "UNTOUCHED" for t in node.targets):
            continue
        try:
            values = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return set()
        for value in values:
            if isinstance(value, str):
                mapped = _repo_relative_grader_path(value)
                if mapped is not None:
                    found.add(mapped)
    return found


def _grader_owned(rel: str, untouched: set[str]) -> bool:
    """Deterministic grader-owned surface (ticket 17 round 4/5).

    Every path :func:`harness.staging.owned_paths` owns (test paths and test
    infrastructure) plus any path in the task's ``UNTOUCHED`` list. The single
    staging definition is the source of truth so a new infrastructure path cannot be
    guarded in one consumer and leak in another.
    """
    return owned_paths(rel) or rel in untouched


def _restore_grader_path(task_dir: Path, repo: Path, rel: str) -> str:
    """Restore one grader-owned path from the pristine source; return the record line.

    The pristine copy already holds the grader's bytes, so a path that exists in the
    task repo is written back explicitly (robust to any future ordering) while a path
    the run invented is removed. Either way the harness's version never takes effect.
    """
    src = Path(task_dir) / "repo" / rel
    dst = repo / rel
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return f"{rel}: restored from the pristine copy"
    if dst.exists():
        dst.unlink()
        return f"{rel}: removed (grader-owned; absent from the pristine copy)"
    return f"{rel}: kept pristine (grader-owned; nothing to restore)"


def _corpus_test_files(repo: Path) -> tuple[str, ...]:
    """The corpus task's own test files (repo-relative, sorted).

    Read from the PRISTINE copy before any produced file is applied, so the run can
    never widen or shrink the set. A file counts when pytest would collect it
    (``test_*.py`` / ``*_test.py``, the default patterns — the anchor tasks use
    ``*_test.py``) and it actually defines a ``test_`` function (``tests/__init__.py``
    is a test path but holds no test).
    """
    found: list[str] = []
    for path in sorted(repo.rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if not _TEST_FILE_NAME.match(PurePosixPath(rel).name) or not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:                             # pragma: no cover - fs error path
            continue
        if _TEST_DEF.search(text):
            found.append(rel)
    return tuple(found)


def _report_gate(repo: Path, expected_files: tuple[str, ...], env: Mapping[str, str],
                 timeout_s: int) -> GateReport:
    """The grader's OWN report-based verification of the graded copy (ticket 17 F1).

    ``checks.py`` is untouched; this is a second, independent observation: pytest is
    launched with ``--junitxml`` into a private ``mkdtemp`` OUTSIDE the repository and
    with a tiny per-run canary test written next to the corpus's own tests (the corpus
    repos configure ``testpaths = ["tests"]``). The exit status is ignored as evidence —
    only the report can green this gate.
    """
    token = canary_token()
    canary_dir = str(PurePosixPath(expected_files[0]).parent) if expected_files else "tests"
    canary = canary_path(token, canary_dir)
    target = repo / canary
    report_path = private_report_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canary_source(token))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *PYTEST_ISOLATION_ARGS,
             "--rootdir=.", *JUNIT_FAMILY_ARGS, f"--junitxml={report_path}"],
            cwd=repo, capture_output=True, text=True, timeout=timeout_s,
            env={**gate_env(repo, env), "PYTHONDONTWRITEBYTECODE": "1"})
    except (OSError, subprocess.SubprocessError) as exc:
        target.unlink(missing_ok=True)
        cleanup_report(report_path)
        return GateReport(report_path=str(report_path), process_exit=None, canary=token,
                          expected_files=expected_files, n_tests=0, n_failed=0, n_errors=0,
                          passed_ids=(), failed_ids=(), missing=expected_files,
                          observed=False, anomaly="report-missing",
                          detail=f"the gate pytest could not run: {type(exc).__name__}: {exc}")
    target.unlink(missing_ok=True)
    gate = evaluate_gate(report_path, canary=token, expected_files=expected_files,
                         canary_dir=canary_dir, process_exit=proc.returncode)
    cleanup_report(report_path)
    return gate


def external_score(task_dir: Path, produced_files: Mapping[str, str],
                   work_root: Path, timeout_s: int = 300) -> ExternalScore:
    """Apply ``produced_files`` to a pristine repo and run the corpus checks.

    Files the harness created that the corpus does not know about are still
    applied (a legitimate fix may add a module); the grader-owned surface is
    restored from the pristine copy and recorded — the grader, not the harness,
    owns its tests, configuration, and frozen files.
    """
    task_dir = Path(task_dir)
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    copy = _pristine_copy(task_dir, work_root)
    repo = copy / "repo"
    # The corpus's own test files, read while the copy is still pristine (ticket 17 F1).
    expected_tests = _corpus_test_files(repo)

    # Interpreter isolation: PYTHONSAFEPATH keeps the run-owned repo root off
    # sys.path for the grader's pytest too, and PYTEST_ADDOPTS reaches the pytest
    # subprocess checks.py spawns (whose argv we do not own).
    # Explicit import roots (PYTHONSAFEPATH removed the implicit ones): the task
    # directory for the corpus's own helpers, then the repo root for the package under
    # test. The run's tree stays importable without giving a run-authored module the
    # implicit cwd prepend that made stdlib shadowing possible.
    env = pytest_isolation_env()
    env["PYTHONPATH"] = os.pathsep.join([str(copy), str(repo)])
    isolation = {key: env[key] for key in _ISOLATION_KEYS if key in env}

    snap = subprocess.run([sys.executable, str(copy / "checks.py"), "snapshot"],
                          cwd=copy, capture_output=True, text=True, timeout=timeout_s,
                          env=env)
    if snap.returncode != 0:
        return ExternalScore(False, snap.returncode,
                             [f"snapshot failed: {snap.stderr.strip()[:200]}"],
                             str(work_root), isolation=isolation)

    untouched = untouched_paths(task_dir)
    applied, skipped, restored, shadowed = [], [], [], []
    for rel, content in sorted(produced_files.items()):
        if _grader_owned(rel, untouched):
            # Restore instead of accepting the run's version. The record is explicit
            # so an audit can see exactly which tampering was neutralized.
            restored.append(_restore_grader_path(task_dir, repo, rel))
            skipped.append(f"{rel}: grader-owned, not applied "
                           "(restored from the pristine copy)")
            continue
        if shadowing_path(rel):
            # Never apply a run-authored top-level module: it would shadow an
            # interpreter import and can exit 0 before pytest runs. The pristine
            # copy (which has no such file, or its genuine version) is left in place.
            shadowed.append(rel)
            skipped.append(f"{rel}: module-shadow path, not applied "
                           "(would shadow an interpreter import)")
            continue
        target = repo / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            applied.append(rel)
        except OSError as exc:                      # pragma: no cover - fs error path
            skipped.append(f"{rel}: {exc}")

    verify = subprocess.run([sys.executable, str(copy / "checks.py"), "verify"],
                            cwd=copy, capture_output=True, text=True, timeout=timeout_s,
                            env=env)
    notes = [line for line in (verify.stdout + verify.stderr).splitlines() if line.strip()]
    corpus_ok = verify.returncode == 0
    # F1: the corpus check passing is NOT enough — its exit status is forgeable by the
    # run's own code. The report gate is the second, machine-readable observation.
    gate = None
    suspected = False
    if corpus_ok:
        gate = _report_gate(repo, expected_tests, env, timeout_s)
        if not gate.green:
            suspected = True
            notes.append(f"gate_report_anomaly: {gate.anomaly}: {gate.detail}")
            notes.append("suspected contaminated grade: the corpus check exited 0 but the "
                         "report gate did not; an exit status alone is not evidence")
    passed = corpus_ok and gate is not None and gate.green
    return ExternalScore(passed, verify.returncode, notes[-6:],
                         str(work_root), applied, skipped, restored, shadowed, isolation,
                         report_gate=gate, suspected_contaminated_grade=suspected)
