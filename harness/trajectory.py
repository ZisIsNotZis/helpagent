"""Trajectory: harness-owned git snapshots (DESIGN §4.5, KERNEL_API §4.5).

The MODEL never calls git. After every action that mutated the work tree the
harness records ``{step_id, node_id, files_changed, diff, outcome}``. The
recorded baseline also powers the user-edit conflict rule (DESIGN §4.8
"work-tree exclusivity"): a divergence the harness cannot attribute to its own
writes pauses the leaf (``needs-user``) — never a silent overwrite.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from harness.runner import note

ANSI_RE = None  # placeholder to keep imports minimal; ANSI stripping lives in exec.py


def _git(workdir: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(workdir), *args],
        capture_output=True, text=True,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:200]}")
    return r.stdout


@dataclass
class SnapshotRecord:
    step_id: str
    node_id: str
    files_changed: list[str]
    diff: str
    outcome: str


@dataclass
class DiscardedCommit:
    """One commit thrown away by a subtree reset (DESIGN §10.1 step 7). Recorded
    BEFORE ``reset --hard`` so the discarded work is auditable after the fact."""

    sha: str
    reason: str
    note: str = ""


@dataclass
class Trajectory:
    """Append-only per-step snapshot record over one workdir (git-init'd on first use)."""

    workdir: Path
    records: list[SnapshotRecord] = field(default_factory=list)
    discarded: list[DiscardedCommit] = field(default_factory=list)

    # -- git plumbing -----------------------------------------------------------

    def ensure_git(self) -> None:
        """git init + a pristine baseline commit when the workdir is not a repo yet,
        so later ``git diff`` snapshots are meaningful. Repo-local identity keeps the
        harness self-contained (the model never sees or runs git)."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        if (self.workdir / ".git").exists():
            return
        _git(self.workdir, "init", "-q")
        _git(self.workdir, "config", "user.email", "harness@helpagent.local")
        _git(self.workdir, "config", "user.name", "helpagent-harness")
        _git(self.workdir, "add", "-A")
        _git(self.workdir, "commit", "-qm", "baseline: pristine work tree (harness)")

    # -- capture ----------------------------------------------------------------

    def file_hashes(self) -> dict[str, str]:
        """sha256 of every tracked, non-ignored file (relative paths)."""
        out = _git(self.workdir, "ls-files")
        hashes: dict[str, str] = {}
        for rel in out.splitlines():
            p = self.workdir / rel
            if p.is_file():
                hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return hashes

    def changed_files(self) -> list[str]:
        """Tracked files whose working-tree content differs from HEAD."""
        out = _git(self.workdir, "diff", "--name-only", "HEAD")
        return [l for l in out.splitlines() if l.strip()]

    def diff(self, node_id: str | None = None) -> str:
        """The recorded snapshot diff for one node (KERNEL_API §4.5 trajectory.diff),
        or the whole work-tree diff when no node is given."""
        if node_id is None:
            return _git(self.workdir, "diff", "HEAD")
        for rec in reversed(self.records):
            if rec.node_id == node_id:
                return rec.diff
        return ""

    def record(self, step_id: str, node_id: str, outcome: str) -> SnapshotRecord:
        rec = SnapshotRecord(
            step_id=step_id,
            node_id=node_id,
            files_changed=self.changed_files(),
            diff=_git(self.workdir, "diff", "HEAD"),
            outcome=outcome,
        )
        self.records.append(rec)
        return rec

    def to_json(self) -> str:
        return json.dumps(
            [r.__dict__ for r in self.records], indent=1, ensure_ascii=False
        )

    # -- per-node checkpoints (ticket 18, DESIGN §10.1 step 7) -------------------

    def checkpoint(self, node_id: str) -> str:
        """Commit the current work tree and return the checkpoint SHA.

        One commit per node, taken BEFORE the node's first mutation, so an L6/L7
        subtree reset can return to exactly this node's starting point. ``--allow-empty``
        keeps the checkpoint well-defined when nothing changed. Inside the
        harness-owned throwaway workdir only (the user's repo is never touched).
        """
        self.ensure_git()
        _git(self.workdir, "add", "-A")
        _git(self.workdir, "commit", "-q", "--allow-empty", "-m", f"checkpoint:{node_id}")
        sha = _git(self.workdir, "rev-parse", "HEAD").strip()
        note("node_checkpoint", node=node_id, sha=sha)
        return sha

    def reset_to(self, sha: str, *, reason: str, detail: str = "") -> list[str]:
        """Discard every commit after ``sha`` and hard-reset the work tree to it.

        The discarded SHAs are ledger-recorded FIRST (append-only — the work is
        auditable after the reset), then ``git reset --hard <sha>`` and ``git clean -fdq``
        remove the node's own uncommitted/untracked output. ``-x`` is deliberately
        omitted so ignored files are kept. Returns the discarded SHAs, newest first.
        """
        self.ensure_git()
        head = _git(self.workdir, "rev-parse", "HEAD").strip()
        if head != sha:
            out = _git(self.workdir, "rev-list", f"{sha}..HEAD").split()
            for discarded in out:  # newest first (rev-list order) — ledger first
                self.discarded.append(
                    DiscardedCommit(sha=discarded, reason=reason, note=detail))
                note("checkpoint_discarded", sha=discarded, reason=reason, detail=detail)
        else:
            out = []
        _git(self.workdir, "reset", "--hard", sha)
        _git(self.workdir, "clean", "-fdq")
        note("subtree_reset", sha=sha, reason=reason, discarded=len(out))
        return out

    # -- user-edit conflict rule --------------------------------------------------

    def detect_external_edits(
        self, baseline: dict[str, str], changed_by_harness: set[str]
    ) -> list[str]:
        """Files that diverged from the baseline but were NOT written by the harness
        — i.e. the user (or anything else) touched the running work tree. DESIGN
        §4.8: detected via the per-step git snapshot → conflict → pause +
        needs-user, never silent overwrite."""
        now = self.file_hashes()
        diverged = []
        for rel, sha in baseline.items():
            if rel in changed_by_harness:
                continue
            if now.get(rel) != sha:
                diverged.append(rel)
        # files the user ADDED mid-run (tracked in neither baseline nor harness set)
        for rel in now:
            if rel not in baseline and rel not in changed_by_harness:
                diverged.append(rel)
        return sorted(set(diverged))


def pause_leaf_on_conflict(leaf, diverged: list[str]) -> bool:
    """Kernel rule: external edits mid-run pause the leaf — status ``needs-user`` —
    and the harness never writes over them. Returns True when paused."""
    if not diverged:
        return False
    leaf.status = "needs-user"
    return True
