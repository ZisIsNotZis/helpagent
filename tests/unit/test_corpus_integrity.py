"""Bench-integrity checks over the WHOLE corpus (ticket 21 round 2, fix 4).

The corpus is the instrument every benchmark number rests on, and nothing verified that a
task is internally consistent. T-33 proved the gap: its ``checks.py`` listed
``repo/serialize/pickle_ser.py`` in ``UNTOUCHED`` while its own ``solution.md`` says a
correct fix must change that file, so the task was UNWINNABLE as graded. This file is the
bench-integrity guard.

``solution.md`` is prose (it NAMES the changed ``repo/*.py`` files but 19/35 carry no code
at all), so the deterministic, offline check is:

1. every task directory holds the four mandated entries (``request.md``, ``repo/``,
   ``checks.py``, ``solution.md``) and nothing else but runtime artifacts;
2. the files a task's ``solution.md`` declares as changed are NOT in that task's
   ``checks.py`` ``UNTOUCHED`` list (this is what fails on the pre-fix T-33);
3. the pristine tree really is broken: ``checks.py snapshot`` succeeds (every UNTOUCHED
   path exists) and ``checks.py verify`` fails (its repo tests fail), with the UNTOUCHED
   contract itself reporting OK.

HONESTY BOUNDARY: this is a TEST-SUITE check only. Neither the corpus ``solution.md`` nor
any grader test content may ever reach an in-run decision; this file is never imported by
``run_leaf`` / ``run_tree``.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "bench" / "corpus"
MANDATED = {"request.md", "repo", "checks.py", "solution.md"}
#: Runtime state a task directory may carry without violating the four-entry layout
#: (``__pycache__``/``.pytest_cache`` are interpreter artifacts, ``.untouched.baseline.json``
#: is written by ``checks.py snapshot`` and is gitignored).
RUNTIME_OK = {"__pycache__", ".pytest_cache", ".untouched.baseline.json"}
#: A declared changed file is a ``repo/*.py`` path named in ``solution.md``.
_REPO_PY = re.compile(r"repo/[A-Za-z0-9_./-]+\.py")

TASKS = sorted(p for p in CORPUS.glob("T-*") if p.is_dir())


def _load_checks(task_dir: Path):
    spec = importlib.util.spec_from_file_location(
        f"_corpus_checks_{task_dir.name}", task_dir / "checks.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _declared_changed(task_dir: Path) -> set[str]:
    """The ``repo/*.py`` files a task's ``solution.md`` says a correct fix changes."""
    return set(_REPO_PY.findall((task_dir / "solution.md").read_text()))


def _run_checks(task_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "checks.py", *args], cwd=task_dir,
                          capture_output=True, text=True, check=False)


def test_corpus_is_non_empty():
    assert TASKS, f"no corpus tasks found under {CORPUS}"


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.name)
def test_task_has_the_mandated_layout(task: Path):
    """A task dir holds exactly the four mandated entries (runtime artifacts aside)."""
    entries = {p.name for p in task.iterdir()}
    assert MANDATED <= entries, f"{task.name} is missing {sorted(MANDATED - entries)}"
    extra = entries - MANDATED - RUNTIME_OK
    assert not extra, (
        f"{task.name} holds unexpected entr(ies) {sorted(extra)}; the corpus layout is "
        f"{sorted(MANDATED)} plus runtime artifacts")
    assert (task / "repo").is_dir()
    assert (task / "checks.py").is_file() and (task / "solution.md").is_file()


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.name)
def test_solution_changed_files_are_not_untouched(task: Path):
    """The core guard: a file the solution MUST change may not be a frozen UNTOUCHED
    path. T-33 fails this before its ``UNTOUCHED`` list is fixed."""
    declared = _declared_changed(task)
    if not declared:
        pytest.skip(f"{task.name}: solution.md declares no parseable changed file")
    untouched = set(_load_checks(task).UNTOUCHED)
    clash = sorted(declared & untouched)
    assert not clash, (
        f"{task.name}: solution.md changes {clash} but checks.py freezes them as "
        "UNTOUCHED — the task is unwinnable as graded")


def test_corpus_integrity_coverage_is_visible():
    """No SILENT SKIPS: report exactly how many tasks the file-vs-UNTOUCHED guard
    covers. A task whose solution.md becomes unparseable must not quietly drop out."""
    covered = [t.name for t in TASKS if _declared_changed(t)]
    uncovered = [t.name for t in TASKS if not _declared_changed(t)]
    print(f"corpus integrity: {len(covered)}/{len(TASKS)} task(s) covered by the "
          f"file-vs-UNTOUCHED guard; uncovered: {uncovered}")
    assert not uncovered, (
        "these task(s) declared no parseable changed file, so the file-vs-UNTOUCHED "
        f"guard does NOT cover them: {uncovered}")


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.name)
def test_pristine_task_is_broken_but_internally_coherent(task: Path, tmp_path: Path):
    """The shipped-broken invariant + UNTOUCHED coherence, on a pristine COPY.

    ``snapshot`` succeeds (every UNTOUCHED path exists) and ``verify`` fails (the repo
    tests fail) while the UNTOUCHED contract itself reports OK. This catches a task whose
    tests already pass before any fix, and one whose UNTOUCHED list names a missing path.
    """
    copy = tmp_path / task.name
    shutil.copytree(task, copy)

    snap = _run_checks(copy, "snapshot")
    assert snap.returncode == 0, (
        f"{task.name}: checks.py snapshot failed (exit {snap.returncode}); an UNTOUCHED "
        f"path is missing:\n{snap.stdout}\n{snap.stderr}")

    verify = _run_checks(copy, "verify")
    out = verify.stdout + verify.stderr
    assert verify.returncode == 1, (
        f"{task.name}: expected a broken shipped state (verify exit 1), got "
        f"{verify.returncode}:\n{out}")
    assert "[contract] OK" in out and "[tests]" in out and "FAIL" in out, (
        f"{task.name}: expected the UNTOUCHED contract OK and the repo tests FAIL:\n{out}")
