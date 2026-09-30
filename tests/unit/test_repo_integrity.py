"""The repository's own gate against silent test-result tampering.

Incident 2026-09-30: an untracked repo-root ``conftest.py`` (a probe written to a
relative path by a verification lane) rewrote every failing pytest report to
``passed``. Nothing in the repo would have failed because of it — the suite simply
would have gone green for anyone running pytest from the repo root, including us.
The sandboxed runs already refuse test-infrastructure files (``owned_paths``); this
file applies the same rule to OUR OWN repository, so a stray hook cannot hide.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Interpreter/pytest start-up files that must never sit loose in this repository.
FORBIDDEN = ("conftest.py", "sitecustomize.py", "usercustomize.py", "pytest.ini", "tox.ini")


def test_no_stray_test_hook_or_interpreter_startup_file_at_the_repo_root():
    found = [name for name in FORBIDDEN if (ROOT / name).exists()]
    found += [p.name for p in ROOT.glob("*.pth")]
    assert found == [], (
        f"stray test-hook / interpreter-startup file(s) in the repository root: {found}. "
        "Such a file silently changes every pytest run in this repo; remove it and keep "
        "probe fixtures inside the sandbox or a tmp directory.")


def test_no_untracked_conftest_anywhere_in_the_repo():
    """A conftest outside the test tree is an unexplained hook. Tracked ones are fine."""
    out = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    untracked = [p for p in out.stdout.split("\0") if p]
    strays = [p for p in untracked
              if os.path.basename(p) == "conftest.py" or Path(p).name.endswith(".pth")]
    assert strays == [], f"untracked conftest/.pth file(s) present: {strays}"


def test_tracked_conftest_files_live_under_the_test_tree():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    tracked = [p for p in out.stdout.split("\0") if p]
    bad = [p for p in tracked if os.path.basename(p) == "conftest.py"
           and not p.startswith("tests/")]
    assert bad == [], f"conftest.py outside tests/: {bad}"
