#!/usr/bin/env python3
"""External grader: score a run with the corpus tests, outside the harness.

Owner direction 2026-09-29: the corpus checks are the benchmark's own scoring
instrument, invisible to the harness. This module applies whatever the harness
produced onto a PRISTINE copy of the task repo and runs the task's own
``checks.py verify`` there. It never runs inside the harness process and its
result is never fed back into a run.

Usage (library):
    from bench.external_score import external_score
    outcome = external_score(task_dir, produced_files, work_root)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

__all__ = ["ExternalScore", "external_score"]


@dataclass
class ExternalScore:
    """Grader verdict plus the raw evidence needed to trust or distrust it."""

    passed: bool
    exit: int
    notes: list[str] = field(default_factory=list)
    work_root: str = ""
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _pristine_copy(task_dir: Path, work_root: Path) -> Path:
    """Copy the whole task dir (checks.py + repo/) so the grader runs unmodified."""
    dest = work_root / task_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task_dir, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  ".untouched.baseline.json"))
    return dest


def external_score(task_dir: Path, produced_files: Mapping[str, str],
                   work_root: Path, timeout_s: int = 300) -> ExternalScore:
    """Apply ``produced_files`` to a pristine repo and run the corpus checks.

    Files the harness created that the corpus does not know about are still
    applied (a legitimate fix may add a module); files the corpus freezes are
    applied too and then caught by the grader's untouched contract — the grader,
    not the harness, decides whether that was allowed.
    """
    task_dir = Path(task_dir)
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    copy = _pristine_copy(task_dir, work_root)
    repo = copy / "repo"

    snap = subprocess.run([sys.executable, str(copy / "checks.py"), "snapshot"],
                          cwd=copy, capture_output=True, text=True, timeout=timeout_s)
    if snap.returncode != 0:
        return ExternalScore(False, snap.returncode,
                             [f"snapshot failed: {snap.stderr.strip()[:200]}"],
                             str(work_root))

    applied, skipped = [], []
    for rel, content in sorted(produced_files.items()):
        target = repo / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            applied.append(rel)
        except OSError as exc:                      # pragma: no cover - fs error path
            skipped.append(f"{rel}: {exc}")

    verify = subprocess.run([sys.executable, str(copy / "checks.py"), "verify"],
                            cwd=copy, capture_output=True, text=True, timeout=timeout_s)
    notes = [line for line in (verify.stdout + verify.stderr).splitlines() if line.strip()]
    return ExternalScore(verify.returncode == 0, verify.returncode, notes[-6:],
                         str(work_root), applied, skipped)
