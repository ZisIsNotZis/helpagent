"""Workdir conflict rule: an external edit to the
running work tree pauses the leaf (needs-user) — never a silent overwrite —
while the harness's own writes proceed normally."""

import shutil
from pathlib import Path

import pytest

from harness.trajectory import Trajectory, pause_leaf_on_conflict


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    wd = tmp_path / "work"
    wd.mkdir()
    (wd / "a.py").write_text("A = 1\n")
    (wd / "b.py").write_text("B = 1\n")
    tr = Trajectory(workdir=wd)
    tr.ensure_git()
    return wd


def _diverged_after_harness_write(workdir: Path) -> list[str]:
    tr = Trajectory(workdir=workdir)
    baseline = tr.file_hashes()
    # the harness legitimately writes a.py
    (workdir / "a.py").write_text("A = 2\n")
    return tr.detect_external_edits(baseline, changed_by_harness={"a.py"})


def test_user_edit_conflict_pauses_not_overwrites(workdir: Path):
    tree = __import__("harness.tree", fromlist=["TaskTree"]).TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    leaf.status = "in-progress"

    tr = Trajectory(workdir=workdir)
    baseline = tr.file_hashes()                     # BEFORE any mid-run write
    (workdir / "a.py").write_text("A = 2\n")         # the harness legitimately writes a.py
    (workdir / "b.py").write_text("B = user was here\n")  # the user edits b.py mid-run

    diverged = tr.detect_external_edits(baseline, changed_by_harness={"a.py"})
    assert diverged == ["b.py"]                     # exactly the user-touched file
    assert pause_leaf_on_conflict(leaf, diverged) is True
    assert leaf.status == "needs-user"              # paused, not silently overwritten
    assert (workdir / "b.py").read_text() == "B = user was here\n"  # user edit SURVIVES


def test_harness_own_writes_do_not_pause(workdir: Path):
    tr = Trajectory(workdir=workdir)
    baseline = tr.file_hashes()
    (workdir / "a.py").write_text("A = 2\n")
    diverged = tr.detect_external_edits(baseline, changed_by_harness={"a.py"})
    assert diverged == []
    tree = __import__("harness.tree", fromlist=["TaskTree"]).TaskTree(what="root")
    leaf = tree.insert_ticket(tree.root, "leaf")
    assert pause_leaf_on_conflict(leaf, diverged) is False
    assert leaf.status == "pending"


def test_trajectory_records_diff_and_files_changed(workdir: Path):
    tr = Trajectory(workdir=workdir)
    (workdir / "a.py").write_text("A = 2\n")
    rec = tr.record(step_id="s-1", node_id="leaf-1", outcome="written")
    assert "a.py" in rec.files_changed
    assert "-A = 1" in rec.diff and "+A = 2" in rec.diff
    assert tr.diff("leaf-1") == rec.diff
    assert tr.diff("other") == ""
    assert '"step_id": "s-1"' in tr.to_json()
