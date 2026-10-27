"""Workdir lifecycle: single-instance lock + boot-time recovery (docs/7_INTERFACE.md §6,). "Sudden death means the trajectory may not reflect the last
mutations ... on program boot (single-instance lock per workdir — never two
harness processes in one workdir): reset everything we don't know and that is
not ignored in the workdir." """

from __future__ import annotations

import os
from pathlib import Path
from contextlib import contextmanager

from harness.trajectory import _git

LOCKFILE = ".helpagent.lock"


class WorkdirLocked(Exception):
    """Second harness instance on the same workdir — never allowed (§6)."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _exclude_lockfile(workdir: Path) -> None:
    """Repo-local exclude for the lockfile — a harness artifact must never count as
    work-tree dirt (it would make boot_recover see its own lock as a crash), and
    ``git clean`` must never delete a held lock. Uses .git/info/exclude so user
    files (.gitignore) stay untouched."""
    git_dir = workdir / ".git"
    if not git_dir.exists():
        return  # not a repo (yet) — nothing to exclude from
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    if LOCKFILE not in current:
        exclude.write_text(current + ("\n" if current and not current.endswith("\n") else "") + f"{LOCKFILE}\n")


@contextmanager
def lock(workdir: Path):
    """Pid-stamped lockfile (O_CREAT|O_EXCL — atomic). A second acquisition from a
    DIFFERENT live process raises WorkdirLocked (never two harness processes in one
    workdir, docs/7_INTERFACE.md §6); same-process re-entry is legal (a script may hold the
    lock and call boot_recover). A STALE lock (owner pid dead) is stealable, so a
    crashed run cannot wedge the workdir forever."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    _exclude_lockfile(workdir)
    path = workdir / LOCKFILE
    if path.exists():
        try:
            old_pid = int(path.read_text().strip() or "0")
        except ValueError:
            old_pid = 0
        if old_pid and _pid_alive(old_pid) and old_pid != os.getpid():
            raise WorkdirLocked(
                f"workdir {workdir} is locked by live pid {old_pid} (never two harness "
                "processes in one workdir, docs/7_INTERFACE.md §6)"
            )
        path.unlink()  # stale: owner is gone
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        if path.exists():
            path.unlink()


def is_dirty(workdir: Path) -> bool:
    """Uncommitted/untracked/non-ignored state (git status --porcelain already
    excludes ignored paths)."""
    return bool(_git(Path(workdir), "status", "--porcelain").strip())


def boot_recover(workdir: Path, note=None) -> bool:
    """§6 boot-time recovery: a dirty workdir is reset (git reset --hard + clean -fd,
    keeping ignored files — never -x) with a ledger note; a clean workdir is a no-op
    with NO note. Returns True when a reset happened."""
    workdir = Path(workdir)
    with lock(workdir):
        if not is_dirty(workdir):
            return False
        _git(workdir, "reset", "--hard", "-q")
        _git(workdir, "clean", "-fdq")   # no -x: ignored files are kept
        if note is not None:
            note("boot", detail="reset dirty workdir: crash recovery")
        return True
