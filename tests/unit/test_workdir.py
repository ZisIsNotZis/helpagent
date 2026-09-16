"""Workdir boot-reset & single-instance lock (TEST_PLAN §3.5, KERNEL_API §6).
Pure + tmp git repos — no GPU, part of the unit gate."""

import subprocess
from pathlib import Path

import pytest

from harness import ledger_entries, reset_ledger_for_tests
from harness.runner import note
from harness.workdir import WorkdirLocked, boot_recover, is_dirty, lock


def _git(wd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(wd), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    wd = tmp_path / "repo"
    wd.mkdir()
    _git(wd, "init", "-q")
    _git(wd, "config", "user.email", "t@t")
    _git(wd, "config", "user.name", "t")
    (wd / "calc.py").write_text("X = 1\n")
    (wd / ".gitignore").write_text(".ignored-dir/\n")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "baseline")
    return wd


def test_boot_recover_resets_dirty_workdir(repo: Path):
    reset_ledger_for_tests()
    (repo / "calc.py").write_text("X = 999\n")          # tracked modification
    (repo / "stray.py").write_text("untracked\n")        # untracked file
    (repo / ".ignored-dir").mkdir()
    (repo / ".ignored-dir" / "cache.bin").write_text("keep me\n")  # ignored → kept
    assert is_dirty(repo)

    assert boot_recover(repo, note=note) is True

    assert not is_dirty(repo)
    assert (repo / "calc.py").read_text() == "X = 1\n"   # tracked file restored
    assert not (repo / "stray.py").exists()              # untracked removed
    assert (repo / ".ignored-dir" / "cache.bin").exists()  # ignored KEPT (never -x)
    kinds = [(e["kind"], e.get("detail", "")) for e in ledger_entries()]
    assert ("boot", "reset dirty workdir: crash recovery") in kinds


def test_clean_workdir_is_not_touched(repo: Path):
    reset_ledger_for_tests()
    before = sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts)
    assert boot_recover(repo, note=note) is False
    after = sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts)
    assert before == after
    assert (repo / "calc.py").read_text() == "X = 1\n"
    assert not [e for e in ledger_entries() if e["kind"] == "boot"]  # clean ⇒ NO note


def test_stale_lock_is_stealable(repo: Path):
    lockfile = repo / ".helpagent.lock"
    lockfile.write_text("999999999")  # pid that cannot exist
    with lock(repo):
        pass  # stale lock stolen without error


def test_second_process_cannot_lock(repo: Path):
    """The single-instance rule is cross-process: another live harness process gets
    WorkdirLocked (same-process re-entry is legal, see lock docstring)."""
    import os, sys
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from harness.workdir import lock, WorkdirLocked\n"
        "try:\n"
        "    with lock(%r):\n"
        "        pass\n"
        "except WorkdirLocked:\n"
        "    sys.exit(3)\n"
        "sys.exit(0)\n"
    ) % (str(Path(__file__).resolve().parents[2]), str(repo))
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    with lock(repo):  # held by THIS process
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 3, (r.returncode, r.stderr[-300:])


def test_boot_recover_runs_under_same_process_lock(repo: Path):
    reset_ledger_for_tests()
    (repo / "calc.py").write_text("X = 2\n")
    with lock(repo):  # a script may hold the lock and call boot_recover (re-entry)
        assert boot_recover(repo, note=note) is True
    assert (repo / "calc.py").read_text() == "X = 1\n"
