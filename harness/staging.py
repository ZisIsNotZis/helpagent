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

Test-path recognition mirrors the check pipeline's rule exactly; a unit test
pins the parity so the two definitions cannot drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

__all__ = ["is_test_path", "source_only", "stage_blind", "excluded_paths"]

# Same rule as harness.checks._is_test_path (parity pinned by test_staging.py):
# a tests/ directory component anywhere, a test_* file name, or an _test.py suffix.
_TEST_PATH = re.compile(r"(^|/)(tests?/|test_|_test\.py$)")


def is_test_path(rel: str) -> bool:
    """True for a path the grader owns (never harness-visible, never writable)."""
    return bool(_TEST_PATH.search(rel))


def excluded_paths(files: Mapping[str, str]) -> list[str]:
    return sorted(rel for rel in files if is_test_path(rel))


def source_only(files: Mapping[str, str]) -> dict[str, str]:
    """The harness-visible projection: source and configuration only."""
    return {rel: text for rel, text in files.items() if not is_test_path(rel)}


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
