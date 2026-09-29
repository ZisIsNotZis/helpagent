"""Blind staging: what the harness may see, and what only the grader may see.

Owner direction 2026-09-29 (methodology fix): the corpus tests are the GRADER.
They must never enter the harness's view — not in the workdir, not in the file
map a step receives, not in the grounding scope. v1 staged the whole repo and
gated on the grader's own pytest run, so every published number measured a
harness that could read the exam. This module makes the split explicit:

* ``source_only`` projects the task files to the harness-visible set;
* ``stage_blind`` writes that projection into a workdir;
* the grader side is ``bench/external_score.py`` — it runs the corpus checks
  against the harness's output in a pristine copy, after the run.

Round-5 (ticket 17): the run and the measuring instrument shared the interpreter
path, so a run-authored top-level module (``json.py`` / ``pytest.py`` /
``_pytest/__init__.py``) could shadow an import and make either pytest exit 0.
This module is now the ONE definition of what a run may not touch:

* :func:`owned_paths` — tests plus test infrastructure (``conftest.py``, pytest
  configuration, ``sitecustomize.py``, ``*.pth``); withheld, unwritable, restored;
* :func:`shadowing_path` — a top-level name that can shadow an interpreter import;
* :func:`pytest_isolation_env` — the environment that keeps the run's repo root
  off ``sys.path`` for every pytest the benchmark launches.

Test-path recognition mirrors the check pipeline's rule exactly; a unit test
pins the parity so the two definitions cannot drift apart.
"""

from __future__ import annotations

import os
import pkgutil
import re
import sys
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Mapping

__all__ = [
    "PYTEST_ISOLATION_ARGS",
    "PYTEST_ISOLATION_ENV",
    "gate_env",
    "shadowing_paths",
    "excluded_paths",
    "is_test_infrastructure",
    "is_test_path",
    "owned_paths",
    "pytest_isolation_env",
    "shadowing_path",
    "source_only",
    "stage_blind",
]

# Same rule as harness.checks._is_test_path (parity pinned by test_staging.py):
# a tests/ directory component anywhere, a test_* file name, or an _test.py suffix.
_TEST_PATH = re.compile(r"(^|/)(tests?/|test_|_test\.py$)")

#: pytest reads its configuration from any of these names; a run must never own one
#: (a hostile config can add plugins, redirect testpaths, or silence collection).
_PYTEST_CONFIG_NAMES = frozenset({"pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"})

#: Files that execute at interpreter start-up (``sitecustomize``/``.pth``) can run
#: arbitrary code before pytest even loads — grader-owned by construction.
_PYTHON_STARTUP_NAME = "sitecustomize.py"

#: Interpreter isolation applied to EVERY pytest the benchmark launches (ticket 17
#: round 5). ``PYTHONSAFEPATH`` (Python 3.11+) keeps the run-owned repo root off
#: ``sys.path`` so a run-authored top-level module cannot shadow an interpreter
#: import; the cache provider is disabled so nothing is written into the run's tree.
PYTEST_ISOLATION_ENV: dict[str, str] = {"PYTHONSAFEPATH": "1"}
PYTEST_ISOLATION_ARGS: tuple[str, ...] = ("-p", "no:cacheprovider")
_PYTEST_ADDOPTS = "-p no:cacheprovider"


def is_test_path(rel: str) -> bool:
    """True for a path the grader owns (never harness-visible, never writable)."""
    return bool(_TEST_PATH.search(rel))


def is_test_infrastructure(rel: str) -> bool:
    """True for a path that configures or hooks the test interpreter (any depth).

    ``conftest.py`` is auto-loaded by pytest and can force a session green; a pytest
    configuration file can add plugins or redirect collection; ``sitecustomize.py``
    and ``*.pth`` files run before pytest starts. None of these is a source file, so
    a run must neither see nor write them.
    """
    name = PurePosixPath(rel).name
    return (name == "conftest.py"
            or name in _PYTEST_CONFIG_NAMES
            or name == _PYTHON_STARTUP_NAME
            or name.endswith(".pth"))


def owned_paths(rel: str) -> bool:
    """ONE definition of what a run may never touch (DESIGN §6/§10.3).

    Every consumer — :func:`source_only`/:func:`stage_blind`, the leaf's self-test and
    source-write guards, and the external grader's restore set — classifies with this
    function, so a new infrastructure path cannot be guarded in one place and leak in
    another.
    """
    return is_test_path(rel) or is_test_infrastructure(rel)


def excluded_paths(files: Mapping[str, str]) -> list[str]:
    return sorted(rel for rel in files if owned_paths(rel))


def source_only(files: Mapping[str, str]) -> dict[str, str]:
    """The harness-visible projection: source and configuration only."""
    return {rel: text for rel, text in files.items() if not owned_paths(rel)}


def stage_blind(workdir: Path, files: Mapping[str, str]) -> list[str]:
    """Write the blind projection into ``workdir``; return the paths withheld.

    The withheld list is recorded in the run ledger so an audit can prove the
    harness never had grader access on that run.
    """
    withheld = excluded_paths(files)
    for rel, text in source_only(files).items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return withheld


# ---------------------------------------------------------------------------
# module-shadow protection (ticket 17 round 5)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _shadow_names() -> frozenset[str]:
    """Names a repo-root path may not take (computed once per process).

    Any stdlib module name, any importable top-level package in this interpreter's
    environment (``pkgutil.iter_modules`` over ``sys.path``), and pytest's own
    top-level modules. A run-authored top-level module with one of these names
    shadows the interpreter's import and can exit 0 before the grader runs.
    """
    names = set(sys.stdlib_module_names)
    names.update({"pytest", "_pytest"})
    for entry in sys.path:
        directory = entry or os.getcwd()
        try:
            names.update(info.name for info in pkgutil.iter_modules([directory]))
        except OSError:                                     # unreadable path entry
            continue
    return frozenset(names)


def _shadow_module_name(component: str) -> str:
    path = PurePosixPath(component)
    return path.stem if path.suffix in {".py", ".pth"} else path.name


def shadowing_path(rel: str) -> bool:
    """True when ``rel``'s FIRST component could shadow an interpreter import.

    Only a top-level name matters: ``api/json.py`` cannot shadow the stdlib ``json``,
    but ``json.py`` at the repo root can (and ``_pytest/__init__.py`` shadows pytest's
    own package). This is NOT grader-owned — it is a produced file the run may not
    land, so the grader refuses it and the leaf refuses the write.
    """
    parts = PurePosixPath(rel).parts
    if not parts:
        return False
    return _shadow_module_name(parts[0]) in _shadow_names()


def gate_env(root: Path | str, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Isolation env for a gate pytest run whose import root is ``root``.

    ``PYTHONSAFEPATH=1`` removes the IMPLICIT prepend of cwd/script-dir, which is what
    let a run-authored ``json.py`` shadow the stdlib. It also removed the repo root,
    so a legitimate run-written test under ``tests/`` could no longer import the
    package it was testing (found by verification round 6). The root is therefore
    declared EXPLICITLY on ``PYTHONPATH``: the run's own tree stays importable, while
    the shadowing names are refused at write time (``shadowing_path``) and restored by
    the grader.
    """
    env = pytest_isolation_env(base)
    env["PYTHONPATH"] = str(Path(root).absolute())
    return env


def shadowing_paths(root: Path | str) -> list[str]:
    """Top-level entries of ``root`` whose name could shadow an import.

    A gate may run with ``root`` on ``PYTHONPATH`` so that a legitimate run-written
    test can import the package under test; the price is that an import shadow placed
    there WOULD take effect. The write guard refuses declared shadow writes, and this
    gate-time scan covers a shadow that run code created at runtime (the class of file
    that would otherwise attack the NEXT gate run).
    """
    base = Path(root)
    if not base.is_dir():
        return []
    found = []
    for entry in sorted(base.iterdir()):
        if entry.name in ("__pycache__",) or entry.name.startswith("."):
            continue
        name = entry.name
        if entry.is_dir():
            if _shadow_module_name(name) in _shadow_names() and (entry / "__init__.py").exists():
                found.append(name + "/__init__.py")
        elif shadowing_path(name):
            found.append(name)
    return found


def pytest_isolation_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return ``base`` (default ``os.environ``) plus the isolation overrides.

    Directly-spawned pytest processes get :data:`PYTEST_ISOLATION_ARGS` on the command
    line; a subprocess whose argv we do not own (the corpus ``checks.py``) receives the
    cache flag through ``PYTEST_ADDOPTS``. ``PYTHONSAFEPATH`` is environment-only.
    """
    env = dict(os.environ if base is None else base)
    env.update(PYTEST_ISOLATION_ENV)
    addopts = env.get("PYTEST_ADDOPTS", "").strip()
    if _PYTEST_ADDOPTS not in addopts:
        env["PYTEST_ADDOPTS"] = f"{addopts} {_PYTEST_ADDOPTS}".strip()
    return env
