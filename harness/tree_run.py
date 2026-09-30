"""Budgeted tree executor over the working leaf (ticket 18, DESIGN §10.1–§10.2).

The leaf loop (:mod:`harness.leaf`) is the unit of work; this module is the tree that
composes it. It calls :func:`harness.leaf.run_leaf` **unchanged** for every leaf — no
branch inside the leaf, no second implementation of red→green, the leaf's claim policy
intact. What the tree adds:

- **Per-node plan.** Every internal node is specified by ONE ``plan_node`` call
  (:mod:`harness.node`); a node with budget 1 never decomposes (it runs as a leaf).
- **Reference-only internal nodes.** An internal node owns no source; it holds only the
  integration AC map. Integration work lives in a DEDICATED integration leaf that goes
  through :func:`run_leaf`, so red-on-arrival, the independent test, and the report gate
  apply to it unchanged. The internal node may not close without a machine-verified
  integration verdict (:func:`integration_verdicts` re-runs every referenced descendant
  check on the frozen tree) — closure is never aggregated from child claims.
- **Structural close rule.** Whether an integration check is even owed is a deterministic
  STRUCTURAL fact, never the authoring call's word: the runner counts the node's WRITING
  descendants (``_writing_descendants``). ≤1 writer closes as ``close_single_writer``
  (nothing to integrate); ≥2 writers REQUIRE a passing report-gated integration verdict,
  and an integration leaf that exposes no test artifact is not a verdict (no keys ⇒ no
  close: the node parks ``needs-integration``).
- **Integration failure reopens its cause.** A failing integration verdict marks its
  responsible writer descendants ``stale`` and re-runs exactly those, then re-integrates,
  bounded per node (:data:`_MAX_INTEGRATION_REOPEN`) before parking ``needs-integration``.
  A node never closes on a stale child.
- **Grader paths from the ROOT only.** :func:`leaf_spec_from` always injects
  ``root_grader_paths``, so no child can widen its withheld set — and it hands each child
  its declared files as BOTH the blind view and the runtime WRITE BOUNDARY, so two
  siblings with disjoint declared boundaries cannot edit each other's files.
- **The write boundary is audited, not trusted (ticket 18 gap A).** The leaf's guard
  inspects the model's DECLARED path, but a run-authored TEST is executed by pytest
  inside the shared workdir, so import-time code in it can write or rename any sibling
  file. Before every leaf this runner snapshots the work tree (``path -> sha256``); after
  the leaf it resnapshots and compares. The only paths allowed to change are (i) the
  leaf's declared write boundary and (ii) test paths (:func:`harness.staging.is_test_path`);
  anything else is a ``boundary-escape``: the run does NOT claim, the escaped paths are
  restored from the pre-leaf snapshot (a sibling's work is never left damaged), and the
  audit is recorded on the outcome and in the run record. The snapshot walks with
  ``lstat`` and never follows a symlink (a link the leaf introduced is itself a violation,
  recorded with its target); ``.git/**`` is IN SCOPE and only interpreter/pytest caches
  are excluded; the byte/count caps record every skip. The restore never follows a link
  (``O_NOFOLLOW``, ``lstat``-verified), refuses a hardlinked target (detected and recorded,
  never written through), records a per-path reason when it cannot restore safely, and
  records a chmod/ownership-only change as a metadata violation it deliberately does not
  repair. All of this is additive: the allowed set stays "boundary plus test paths".
- **The integration leaf reads the code it integrates (ticket 18 gap C).** The dedicated
  integration leaf is given a READ-ONLY view of the parent node's declared files while
  its write boundary stays its own integration test path, so it can test the integrated
  code instead of inventing a test from the goal alone.
- **The integration verdict FAILS CLOSED (ticket 18 gap B).** A verdict is ``pass`` only
  when the machine-readable report gate is green for that check; a missing gate, a
  missing report, or an anomalous report is a failure, and no keys means no close.
- **How-first planning (ticket 20 step 2b).** A node that can decompose is planned
  HOW-first: ONE ``how_list`` call lists the ranked approaches (``HOW-1``…), then each
  How the budget lets the node explore opens its OWN isolated candidate COPY under the
  run output area (``candidate_dir``) and gets its own ``plan_node`` bound to that
  ``how_id``; the How's children run INSIDE its candidate copy. The winner among closed
  candidates is chosen by :func:`harness.how.pick` (tests, then review, then rank, then
  cost) — never a model vote. A candidate whose review is negative is an ACTION ITEM,
  not a lost comparison.
- **NO destructive reset.** The L6 (exhausted leaf) and L7 (spec bubble) cases no longer
  reset a node's subtree with ``git reset --hard`` / ``git clean``. A failed/exhausted
  approach goes through the manager loop (:func:`harness.how.decide_after_failure`) and
  the node appends a NEW How and switches to a fresh candidate copy; with no manager
  injected the safe default is to park. A repeated decomposition that neither differs nor
  shrinks is refused as ``wasted`` (:class:`harness.node.SplitHistory`), so the T-31
  "nine identical retries" defect cannot recur.
- **Shared deadline — the final stop.** The wall-clock deadline is never hard-split per
  child; when it passes, no new node starts and the checkpoints are kept for resume.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from harness.budget import Budget, BudgetError, group_weights
from harness.leaf import (
    DEFAULT_REVIEW_LEVEL,
    LeafOutcome,
    LeafSpec,
    ReviewRequest,
    ReviewVerdict,
    _call_review,  # one reviewer call incl. verdict conversion (shared with the leaf)
    _default_run_tests,  # the tree's default check runner
    combine_review_verdicts,
    review_angles_for_level,
    review_grade_rank,
    run_leaf,
)
from harness.node import (
    MIN_LEAF_CALLS,
    Decomposition,
    NodeSpec,
    SplitAttempt,
    SplitHistory,
    can_decompose,
    canonical_path,
    plan_node,
    split_weighted,
)
from harness.how import (
    CandidateSet,
    How,
    HowList,
    ManagerDecision,
    Selection,
    TestPoint,
    abandon_candidate,
    decide_after_failure,
    extra_test_points,
    how_exploration_limit,
    how_list_from_envelope,
    make_how,
    pick,
    planned_test_points,
    point_results,
    select_key,
)
from harness.runner import llm_step, note
from harness.staging import is_test_path, owned_paths
from harness.trajectory import Trajectory
from harness.tree import ACEntry, CheckResults, NodeHandle, TaskTree

__all__ = [
    "BoundaryAudit",
    "NodeOutcome",
    "TreeOutcome",
    "audit_leaf_boundary",
    "integration_verdicts",
    "leaf_spec_from",
    "run_node",
    "run_tree",
    "snapshot_workdir",
]

#: Bound on integration-verdict reopen rounds per node (ticket 18 gap 2): a failing
#: integration check reopens its responsible writers at most this many times before the
#: node parks with ``needs-integration``, so the reopen cannot loop forever.
_MAX_INTEGRATION_REOPEN = 2


@dataclass
class CandidateRecord:
    """One How candidate's audit record on a node (ticket 20 step 2b).

    Carries the candidate's How id and rank, its lifecycle status, the ISOLATED
    directory it ran in, its :class:`harness.how.Selection` (the pick key + any repair
    action item), the failure evidence, and whether it won the :func:`harness.how.pick`
    comparison. It is what the tree run record persists per candidate.
    """

    how_id: str
    rank: int
    status: str
    directory: str
    selection: Selection | None = None
    evidence: str = ""
    won: bool = False
    #: Ticket 20 step 2b-ii: the DECLARED test points this candidate's plan named
    #: (``{name, file, verifies, ac_id}``) — the run-record copy of the contract the
    #: candidate was scored against — and any EXTRA tests it collected beyond them.
    planned_points: list[dict] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "how_id": self.how_id, "rank": self.rank, "status": self.status,
            "directory": self.directory,
            "selection": (list(self.selection.key) if self.selection is not None else None),
            "test_covered": (self.selection.test_covered
                             if self.selection is not None else 0),
            "test_pass_rate": (self.selection.test_pass_rate
                               if self.selection is not None else 0.0),
            "review_score": (self.selection.review_score
                             if self.selection is not None else 0),
            "needs_repair": bool(self.selection is not None and self.selection.needs_repair),
            "repair_reason": (self.selection.repair_reason
                              if self.selection is not None else ""),
            "evidence": self.evidence, "won": self.won,
            "planned_points": list(self.planned_points),
            "deviations": list(self.deviations),
        }


@dataclass
class NodeOutcome:
    """One node's result: the single stop reason, its own calls/wall, and its children.

    ``stop_reason`` is ``closed`` (leaf claimed green, or internal with all children
    closed and a passing integration verdict), ``resplit`` (a leaf exhausted and may be
    re-split), ``respec`` (a leaf's spec bubbled to the parent), ``parked`` (deadline,
    call budget, or the L6/L7 round bound), ``boundary-escape`` (the leaf changed a path
    outside its write boundary, so its claim is invalid and the path was restored), or a
    leaf's own ``stop_reason``.
    """

    node_id: str
    claimed: bool
    stop_reason: str
    leaf: LeafOutcome | None = None
    children: list[NodeOutcome] = field(default_factory=list)
    calls: int = 0
    wall_s: float = 0.0
    integration_verdicts: dict[str, str] = field(default_factory=dict)
    resplit_rounds: int = 0
    respec_rounds: int = 0
    evidence: str = ""
    #: Ticket 20 step 2b: the Hows the node planned (``{id,text,rank,reason,prior,status}``),
    #: the per-candidate audit records, the manager-loop decisions, and the winning How
    #: id. All empty for a legacy single-plan node (one that could not plan Hows).
    hows: list[dict] = field(default_factory=list)
    candidates: list[CandidateRecord] = field(default_factory=list)
    manager_decisions: list[dict] = field(default_factory=list)
    winner: str = ""
    #: Which close rule the deterministic structural gate applied (ticket 18 gap 1):
    #: ``integration`` (≥2 writing descendants, a passing report-gated integration
    #: verdict), ``close_single_writer`` (≤1 writing descendant — nothing to integrate),
    #: or ``needs-integration`` (a check was required but could not be produced/passed).
    close_rule: str = ""
    #: Bounded rounds the failing integration verdict was allowed to reopen its
    #: responsible writers before the node parked (ticket 18 gap 2).
    integration_reopen_rounds: int = 0
    #: The post-hoc write-boundary audit for this node's leaf execution (ticket 18 gap A):
    #: ``None`` for an internal node that ran no leaf, otherwise the exact changed paths
    #: outside the allowed set and what was restored. Recorded in the run record.
    boundary_audit: BoundaryAudit | None = None


@dataclass
class BoundaryAudit:
    """The post-hoc write-boundary audit of ONE leaf execution (ticket 18 gap A).

    ``violations`` are the exact work-tree paths that changed outside the leaf's allowed
    set — its declared write boundary plus every test path (:func:`harness.staging.is_test_path`)
    — plus every symlink the leaf introduced or retargeted (a symlink is never allowed
    and is never traversed). ``restored`` are the violated paths written back from the
    pre-leaf snapshot and ``removed`` the ones (added by the leaf) deleted, so a sibling's
    work is never left damaged. ``restore_refused`` records, per path, why a restore could
    NOT be performed safely (a symlink in the parent chain, a hardlinked target, ...); a
    refused restore still counts as a violation. ``metadata`` are chmod/ownership-only
    changes — recorded because content comparison cannot see them, deliberately NOT
    repaired. ``links`` maps a link violation to its target. ``skipped`` records snapshot
    entries dropped for the bounded size/count cap. ``clean`` is True when nothing escaped.
    """

    boundary: tuple[str, ...] = ()
    violations: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    restore_refused: list[str] = field(default_factory=list)
    metadata: list[str] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True only when nothing escaped AND the snapshot saw the whole tree.

        A bounded snapshot that had to skip entries cannot certify anything: a
        violation hidden in a skipped or unreadable file would otherwise pass
        unnoticed (found by adversarial verification round 4 — the size/count cap
        was itself an evasion channel). An incomplete audit is therefore never
        clean, and the node cannot claim.
        """
        return not self.violations and not self.skipped

    def to_dict(self) -> dict:
        return {"clean": self.clean, "boundary": list(self.boundary),
                "violations": list(self.violations),
                "restored": list(self.restored), "removed": list(self.removed),
                "restore_refused": list(self.restore_refused),
                "metadata": list(self.metadata), "links": dict(self.links),
                "skipped": list(self.skipped)}


@dataclass
class TreeOutcome:
    """The whole run: the root outcome, the totals, and the audit trail."""

    root: NodeOutcome
    claimed: bool
    calls: int
    wall_s: float
    budget: Budget
    checkpoints: dict[str, str]
    split_history: dict[str, list[SplitAttempt]]


# ---------------------------------------------------------------------------
# Write-boundary audit (ticket 18 gap A)
# ---------------------------------------------------------------------------

#: Directory names and file suffixes that are interpreter/pytest cache artifacts, never
#: work-tree content. ONLY these are excluded: ``.git/**`` is deliberately INCLUDED, so
#: a leaf that tampers the harness's own git state (the per-node checkpoints) is a
#: boundary escape rather than an invisible edit.
_AUDIT_EXCLUDED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache",
                                   ".ruff_cache"})
_AUDIT_EXCLUDED_SUFFIXES = (".pyc", ".pyo")

#: Bounds on the snapshot so a hostile work tree cannot exhaust memory or time: a file
#: larger than this is never read (and never restorable), and at most this many files are
#: recorded. Every skip is returned on the snapshot's ``skipped`` and surfaced on the
#: audit, so the limit is visible rather than silent.
_MAX_AUDIT_FILE_BYTES = 4 * 1024 * 1024
_MAX_AUDIT_FILES = 20_000


@dataclass(frozen=True)
class _FileState:
    """One work-tree REGULAR file at snapshot time: its sha256, bytes, and metadata.

    ``mode``/``uid``/``gid`` are compared as well: a chmod/ownership-only change is
    invisible to content comparison, so it is recorded as a metadata violation instead.
    """

    sha256: str
    data: bytes
    mode: int = 0
    uid: int = 0
    gid: int = 0


@dataclass(frozen=True)
class _TreeState:
    """The work tree at snapshot time: regular files, real dirs, symlinks, and skips.

    ``links`` maps a symlink's repo-relative path to its target; the walk never follows
    a link, so a symlinked directory inside the workdir is recorded as a violation, not
    traversed.
    """

    files: Mapping[str, _FileState]
    dirs: frozenset[str]
    links: Mapping[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()


def _audit_excluded(rel: str) -> bool:
    """True for a path the audit ignores (interpreter/pytest cache artifacts ONLY).

    ``.git/**`` is NOT excluded: the harness's checkpoints live there, so a leaf that
    tampers git state is a boundary escape. ``__pycache__``/``.pytest_cache``/
    ``.mypy_cache``/``.ruff_cache`` and ``*.pyc``/``*.pyo`` are rewritten by the
    interpreter or pytest independently of the run, so they are never work-tree content.
    """
    if any(part in _AUDIT_EXCLUDED_PARTS for part in rel.split("/")):
        return True
    return rel.endswith(_AUDIT_EXCLUDED_SUFFIXES)


def snapshot_workdir(workdir: Path, *, max_file_bytes: int = _MAX_AUDIT_FILE_BYTES,
                     max_files: int = _MAX_AUDIT_FILES) -> _TreeState:
    """Snapshot the work tree with ``lstat`` — a symlink is recorded, never followed.

    Only regular files are read (and only their bytes, so a violated path can be restored
    byte-for-byte). The snapshot is CAPPED: a file larger than ``max_file_bytes`` is
    skipped, and at most ``max_files`` files are recorded; every skip is returned in
    ``skipped`` so a hostile tree cannot exhaust memory or time silently. Cache artifacts
    are excluded (:func:`_audit_excluded`); ``.git/**`` is included.
    """
    workdir = Path(workdir)
    files: dict[str, _FileState] = {}
    dirs: set[str] = set()
    links: dict[str, str] = {}
    skipped: list[str] = []
    capped = False

    def walk(directory: Path, rel_dir: str) -> None:
        nonlocal capped
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            if _audit_excluded(rel):
                continue
            try:
                if entry.is_symlink():
                    # A symlink is itself a violation; record it and DO NOT traverse it.
                    try:
                        links[rel] = os.readlink(entry.path)
                    except OSError:
                        links[rel] = ""
                    continue
                if entry.is_dir(follow_symlinks=False):
                    dirs.add(rel)
                    walk(Path(entry.path), rel)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if len(files) >= max_files:
                capped = True
                continue
            if st.st_size > max_file_bytes:
                skipped.append(
                    f"{rel}: {st.st_size} bytes > snapshot cap {max_file_bytes}")
                continue
            try:
                data = Path(entry.path).read_bytes()
            except OSError:
                continue
            files[rel] = _FileState(
                sha256=hashlib.sha256(data).hexdigest(), data=data,
                mode=stat.S_IMODE(st.st_mode), uid=st.st_uid, gid=st.st_gid)

    walk(workdir, "")
    if capped:
        skipped.append(
            f"file-count cap reached: only the first {max_files} files were snapshotted")
    return _TreeState(files=files, dirs=frozenset(dirs), links=links,
                      skipped=tuple(skipped))


def _boundary_allows(rel: str, boundary: frozenset[str]) -> bool:
    """The audit's ALLOWED SET: the leaf's declared write boundary OR any test path.

    Boundary entries are canonicalized (``./pkg/a.py`` == ``pkg/a.py``) so a path alias
    cannot evade the check; the test-path arm is :func:`harness.staging.is_test_path`, the
    one definition of a test path, which is exactly where the leaf legitimately writes its
    own test file. A test file renamed INTO a source path is therefore NOT allowed: the
    destination is neither a boundary entry nor a test path, so it is caught.
    """
    if is_test_path(rel):
        return True
    canon = canonical_path(rel)
    return canon is not None and canon in boundary


def _parent_chain_problem(workdir: Path, rel: str) -> str:
    """Why ``rel``'s parent chain is not a real directory ("" when it is).

    Every existing parent component must be a REAL directory (``lstat`` says directory,
    never a symlink), so a restore can never write through a link placed in the path.
    """
    current = workdir
    for part in rel.split("/")[:-1]:
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return f"parent component {part!r} is missing"
        except OSError as exc:
            return f"parent component {part!r} is unreadable ({type(exc).__name__})"
        if not stat.S_ISDIR(st.st_mode):
            return f"parent component {part!r} is not a real directory"
    return ""


def _restore_path(workdir: Path, rel: str,
                  original: _FileState | None) -> tuple[str, str]:
    """Restore one violated path safely; returns ``(action, reason)``.

    ``action`` is ``"restored"`` (the original bytes were written back), ``"removed"``
    (an added entry was deleted), or ``"refused"`` (nothing safe could be done; ``reason``
    says why and the path still counts as a violation).

    The write NEVER follows a link: every parent component must be a real directory, the
    final write uses ``os.open`` with ``O_NOFOLLOW`` and is ``lstat``-verified afterwards.
    A hardlinked target (``st_nlink > 1``) is detected and recorded but never written
    through. A symlink at the target is unlinked first (unlink follows nothing) and only
    then is the original file recreated; if that unlink is refused the whole restore is
    refused and recorded.
    """
    problem = _parent_chain_problem(workdir, rel)
    if problem:
        return "refused", problem
    target = workdir / rel
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        st = None
    except OSError as exc:
        return "refused", f"cannot lstat the target ({type(exc).__name__}: {exc})"

    if original is None:
        # An added path: the restore is its deletion (never following a link).
        if st is None:
            return "refused", "the added path is already gone"
        if stat.S_ISDIR(st.st_mode):
            return "refused", "the added path is a directory (left for the empty-dir prune)"
        if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
            return "refused", (f"the added path has {st.st_nlink} hard links "
                               "(refusing to touch it)")
        try:
            os.unlink(target)
        except OSError as exc:
            return "refused", f"unlink failed ({type(exc).__name__}: {exc})"
        return "removed", ""

    # The path held a regular file before: recreate it, but never through a link.
    if st is not None:
        if stat.S_ISLNK(st.st_mode):
            try:
                os.unlink(target)        # removes the LINK, never what it points at
            except OSError as exc:
                return "refused", (f"cannot remove the symlink "
                                   f"({type(exc).__name__}: {exc})")
            st = None
        elif not stat.S_ISREG(st.st_mode):
            return "refused", "the target is not a regular file"
        elif st.st_nlink > 1:
            return "refused", (f"the target has {st.st_nlink} hard links "
                               "(refusing to write through it)")
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW)
    except OSError as exc:
        return "refused", f"open refused ({type(exc).__name__}: {exc})"
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(original.data)
    except OSError as exc:
        return "refused", f"write failed ({type(exc).__name__}: {exc})"
    try:
        after = os.lstat(target)
    except OSError as exc:
        return "refused", (f"post-write verification failed "
                            f"({type(exc).__name__}: {exc})")
    if not stat.S_ISREG(after.st_mode) or after.st_nlink != 1:
        return "refused", "post-write verification failed (not a single-link regular file)"
    return "restored", ""


def audit_leaf_boundary(workdir: Path, before: _TreeState,
                        boundary: Sequence[str]) -> BoundaryAudit:
    """Compare the post-leaf work tree against the pre-leaf snapshot and undo escapes.

    A path is a violation when it changed outside the allowed set (its declared boundary
    plus every test path) OR when it is a symlink the leaf introduced or retargeted — a
    symlink is never allowed and is never traversed. Content, added/removed-file, link,
    and metadata (chmod/ownership-only) changes are all compared. Violated paths are then
    restored from ``before`` as far as that can be done SAFELY: an added path is removed
    and a changed/removed file is rewritten byte-for-byte through ``O_NOFOLLOW``. A restore
    that cannot be performed safely (a link in the parent chain, a hardlinked target, a
    refused unlink) is recorded per path in ``restore_refused`` and still counts as a
    violation. A metadata-only change is recorded in ``metadata`` and deliberately NOT
    repaired. The audit is pure data: it never raises on a filesystem refusal.
    """
    workdir = Path(workdir)
    after = snapshot_workdir(workdir)
    allowed = frozenset(
        canon for canon in (canonical_path(b) for b in boundary) if canon is not None)
    audit = BoundaryAudit(boundary=tuple(boundary),
                          skipped=[*before.skipped, *after.skipped])

    changes: dict[str, str] = {}

    def mark(rel: str, kind: str) -> None:
        changes.setdefault(rel, kind)

    # Symlinks: a link that is new, retargeted, or removed. A link is a violation wherever
    # it sits (it is never work-tree content and must never be traversed).
    for rel in set(after.links) - set(before.links):
        mark(rel, "symlink")
    for rel in set(before.links) & set(after.links):
        if before.links[rel] != after.links[rel]:
            mark(rel, "symlink")
    for rel in set(before.links) - set(after.links):
        mark(rel, "symlink-removed")
    # Regular files: added / removed / content / metadata.
    for rel in set(after.files) - set(before.files):
        mark(rel, "added")
    for rel in set(before.files) - set(after.files):
        mark(rel, "removed")
    for rel in set(before.files) & set(after.files):
        prior, now = before.files[rel], after.files[rel]
        if prior.sha256 != now.sha256:
            mark(rel, "content")
        elif (prior.mode, prior.uid, prior.gid) != (now.mode, now.uid, now.gid):
            mark(rel, "metadata")

    violations = sorted(
        rel for rel, kind in changes.items()
        if kind == "symlink" or not _boundary_allows(rel, allowed))
    audit.violations = violations
    audit.metadata = [rel for rel in violations if changes[rel] == "metadata"]
    audit.links = {
        rel: (after.links.get(rel) if rel in after.links else before.links.get(rel, ""))
        for rel in violations if rel in after.links or rel in before.links}

    for rel in violations:
        kind = changes[rel]
        if kind == "metadata":
            continue    # chmod/ownership-only: recorded above, deliberately NOT repaired
        if kind == "symlink-removed":
            audit.restore_refused.append(
                f"{rel}: the leaf removed a symlink; a symlink cannot be safely recreated")
            continue
        action, reason = _restore_path(workdir, rel, before.files.get(rel))
        if action == "restored":
            audit.restored.append(rel)
        elif action == "removed":
            audit.removed.append(rel)
        else:
            audit.restore_refused.append(f"{rel}: {reason}")
    # Prune directories the leaf created and left empty (deepest first), so a stray
    # path the escape deleted does not survive as a directory either.
    for rel in sorted(after.dirs - before.dirs,
                      key=lambda r: (r.count("/"), r), reverse=True):
        try:
            (workdir / rel).rmdir()
        except OSError:
            pass
    return audit


# ---------------------------------------------------------------------------
# Blind views
# ---------------------------------------------------------------------------


def _source_only_view(workdir: Path) -> dict[str, str]:
    """The source-only projection of the work tree (grader paths withheld).

    :func:`run_leaf`'s ``LeafSpec.files`` is documented as "the source-only view the run
    may see"; the tree reproduces the fix-round projection (``source_only``) by reading
    every non-grader, non-infrastructure file in the workdir. Writes stay boundary-scoped
    by the tree's sibling-disjointness + ``run_leaf``'s own write guard.
    """
    workdir = Path(workdir)
    view: dict[str, str] = {}
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workdir).as_posix()
        if rel.startswith(".git/") or "__pycache__" in path.parts:
            continue
        if owned_paths(rel):
            continue
        try:
            view[rel] = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
    return view


def _leaf_goal(spec: NodeSpec) -> str:
    parts = [spec.goal]
    if spec.behavior:
        parts.append(f"Shared contract: {spec.behavior}")
    if spec.implementation_notes:
        parts.append(f"Implementation notes: {spec.implementation_notes}")
    return "\n".join(parts)


def leaf_spec_from(spec: NodeSpec, workdir: Path, *,
                   root_grader_paths: Sequence[str],
                   candidate_files: Sequence[str] = ()) -> LeafSpec:
    """Build the leaf contract from a node's plan.

    ``grader_paths`` is ALWAYS ``root_grader_paths`` (the root's set), never anything a
    child declared — the single source that keeps a withheld path unreachable from any
    descendant (design §3).

    The declared files are BOTH the file view and the runtime write boundary (ticket 18
    gap 3): a child sees only its own declared files (its existing content, or nothing
    for a not-yet-existing path it is meant to create) and may write only those, so two
    siblings with disjoint declared boundaries cannot reach into each other's files. A
    declared path that does not exist yet is still writable (it is in the boundary).

    ``spec.view_files`` adds READ-ONLY paths to the view only (ticket 18 gap C): the
    integration leaf sets them to the parent's declared files so it can author a test
    against the code under integration, while its write boundary stays its own test path.

    Ticket 19 D/E: the node's DECLARED test cases and the root candidate-file scope ride
    along, so the leaf can verify the declared test-case contract and gate a claim on the
    artifacts a criterion names.
    """
    workdir = Path(workdir)
    boundary = tuple(spec.files)
    view: dict[str, str] = {}
    for rel in dict.fromkeys([*boundary, *spec.view_files]):
        if owned_paths(rel):
            continue
        path = workdir / rel
        if path.is_file():
            try:
                view[rel] = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
    return LeafSpec(
        goal=_leaf_goal(spec),
        files=view,
        acs=list(spec.acs),
        interfaces=list(spec.interfaces),
        grader_paths=tuple(root_grader_paths),
        write_boundary=boundary,
        test_cases=tuple(spec.test_cases),
        candidate_files=tuple(candidate_files),
        verification_required=spec.verification_required,
        review_angles=tuple(spec.review_angles),
        review_level=spec.review_level,
        best_effort=spec.best_effort,
        best_effort_reason=spec.best_effort_reason,
    )


# ---------------------------------------------------------------------------
# Integration verification
# ---------------------------------------------------------------------------


async def _run_check(run_tests: Callable[..., Any] | None, workdir: Path,
                     key: str) -> Any:
    runner = run_tests or _default_run_tests
    result = runner(workdir, node_ids=[key])
    if inspect.isawaitable(result):
        result = await result
    return result


async def integration_verdicts(tree: TaskTree, node: NodeHandle,
                               run_tests: Callable[..., Any] | None,
                               workdir: Path) -> CheckResults:
    """Machine-verify every integration AC by re-running its referenced descendant check.

    The parent's map is a view over descendant checks; each key is re-run on the FROZEN
    final tree through the same report gate the leaf uses. A verdict is ``pass`` ONLY when
    the machine-readable report gate is green for that check (ticket 18 gap B): a missing
    gate, a missing report, or an anomalous report is a ``fail`` — the exit status alone is
    never evidence, and the run fails CLOSED. This is what stops an internal node closing
    on child ``claimed`` flags or on a gate-less seam result; an empty map yields no
    verdicts, so ``no keys => no close`` (enforced by the caller).
    """
    verdicts: dict[str, str] = {}
    tree.commit()  # apply any pending status assignments before verifying the frozen tree
    for entry in node.ac_test_map:
        key = entry.key
        result = await _run_check(run_tests, workdir, key)
        gate = getattr(result, "gate", None)
        # FAIL CLOSED: green only from a machine-readable gate report. A gate-less result
        # (even with exit 0), a missing/anomalous report, and a None gate are all failures.
        verdicts[key] = "pass" if (gate is not None and bool(getattr(gate, "green", False))) \
            else "fail"
    return CheckResults(verdicts=verdicts)


# ---------------------------------------------------------------------------
# Internal run context
# ---------------------------------------------------------------------------


@dataclass
class _TreeContext:
    model: Any
    tree: TaskTree
    workdir: Path
    trajectory: Trajectory
    root_grader_paths: tuple[str, ...]
    candidate_files: set[str]
    judge: Any
    iv: Any
    review: Any
    run_tests: Any
    now: Callable[[], float]
    on_event: Any
    depth_cap: int
    max_children: int
    min_leaf_calls: int
    specs: dict[str, NodeSpec] = field(default_factory=dict)
    depths: dict[str, int] = field(default_factory=dict)
    checkpoints: dict[str, str] = field(default_factory=dict)
    split_history: dict[str, SplitHistory] = field(default_factory=dict)
    split_pool: dict[str, int] = field(default_factory=dict)
    total_calls: int = 0
    #: Ticket 20 step 2b: the manager call the failure loop consults (``None`` => the
    #: safe default ``escalate-or-park``) and the run output area candidate copies live in.
    manager: Any = None
    run_outdir: Path = field(default_factory=lambda: Path("."))

    def emit(self, kind: str, **data: Any) -> None:
        note(kind, **data)
        if self.on_event is not None:
            self.on_event(kind, data)

    def expired(self, budget: Budget) -> bool:
        return budget.expired(self.now())


# ---------------------------------------------------------------------------
# Status helpers (tree edits go through the existing handles)
# ---------------------------------------------------------------------------


def _force_done(ctx: _TreeContext, node: NodeHandle) -> None:
    tree = ctx.tree
    if node.status in ("pending", "blocked", "needs-user"):
        node.status = "in-progress"
        tree.commit()
    if node.status != "done":
        node.status = "done"
        tree.commit()


def _reset_handle(ctx: _TreeContext, node: NodeHandle) -> None:
    """Return a reused child handle to ``pending`` for an L7 re-run."""
    tree = ctx.tree
    if node.status == "done":
        node.status = "stale"
        tree.commit()
    if node.status != "pending":
        node.status = "pending"
        tree.commit()


def _record_leaf_map(node: NodeHandle, spec: NodeSpec, outcome: LeafOutcome) -> None:
    """Record the leaf's AC map as references to the test it wrote."""
    check = outcome.self_test or outcome.independent_test_path or ""
    if not spec.acs or not check:
        return
    node.set_ac_test_map([
        ACEntry(ac_id=f"AC-{i}", statement=statement, check_kind="test", check_hint=check)
        for i, statement in enumerate(spec.acs, 1)
    ])


def _integration_map(acs: Sequence[str], keys: Sequence[str]) -> list[ACEntry]:
    check = keys[0] if keys else None
    return [
        ACEntry(ac_id=f"AC-{i}", statement=statement, check_kind="test", check_hint=check)
        for i, statement in enumerate(acs, 1)
    ]


def _derived_integration_ac(spec: NodeSpec) -> str:
    """A real integration AC derived deterministically from the node's goal/behavior.

    Used when an internal node with ≥2 writing descendants declared no integration AC of
    its own — the check is still owed, so the harness names the cross-child behavior from
    the plan it already holds (one sentence, no extra model call).
    """
    statement = f"the node's changes integrate: {spec.goal}".strip()
    if spec.behavior:
        statement = f"{statement} ({spec.behavior})"
    return statement


def _integration_spec(spec: NodeSpec) -> NodeSpec:
    """The dedicated integration LEAF for an internal node's integration ACs.

    It carries the node's integration ACs (or the one derived from its goal/behavior
    when it declared none) and no source boundary; it goes through :func:`run_leaf`
    like any other leaf, so the fix-round guarantees apply unchanged.

    Ticket 18 gap C: its write boundary stays empty — its ONLY writable artifact is its
    own integration test (a test path) — while ``view_files`` gives it a READ-ONLY view of
    the parent node's declared files, i.e. the code under integration.
    """
    acs = tuple(spec.acs) or (_derived_integration_ac(spec),)
    return NodeSpec(
        goal=f"Integration: {spec.goal}",
        files=(),
        acs=acs,
        interfaces=tuple(spec.interfaces),
        kind="leaf",
        est_calls=1,
        behavior=spec.behavior,
        implementation_notes=spec.implementation_notes,
        view_files=tuple(spec.files),
        # Ticket 20: the integration leaf reviews at the INTEGRATION level (its own
        # closed angle set and its own critical veto), not the implementation level.
        review_level="integration",
    )


def _subtree_wrote_source(outcome: NodeOutcome) -> bool:
    """Whether this outcome's subtree recorded a source write (ticket 18 gap 1/2).

    A leaf wrote source when an attempt touched a file that is not grader-owned (the
    self-test rewrite touches an owned test path, so it never counts). Delegates into
    child outcomes for an internal node.
    """
    if outcome.children:
        return any(_subtree_wrote_source(child) for child in outcome.children)
    leaf = outcome.leaf
    if leaf is None:
        return False
    return any(not owned_paths(rel) for attempt in leaf.attempts
               for rel in attempt.touched_files)


def _writing_descendants(outcomes: Sequence[NodeOutcome]) -> int:
    """Count the writing descendant leaves across a node's child outcomes."""
    total = 0
    for outcome in outcomes:
        if outcome.children:
            total += _writing_descendants(outcome.children)
        elif _subtree_wrote_source(outcome):
            total += 1
    return total


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


async def _plan(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec, budget: Budget,
                evidence: str) -> Decomposition | None:
    """Attempt a decomposition; ``None`` means the node is a leaf (unable/invalid/empty
    children). The integration leaf is built later by :func:`_attempt_internal`, once the
    actual writing descendants are known."""
    before = budget.spent_calls
    decomp = await plan_node(
        ctx.model, goal=spec.goal, evidence=evidence, boundary=set(spec.files),
        candidate_files=ctx.candidate_files, depth=ctx.depths[node.id],
        depth_cap=ctx.depth_cap, max_children=ctx.max_children,
        budget=budget, on_event=ctx.on_event)
    ctx.total_calls += budget.spent_calls - before
    if decomp is None or not decomp.children:
        return None
    return decomp


def _strongest_requirement(values: Sequence[str]) -> str:
    """The strongest declared verification requirement across ``values`` (ticket 20)."""
    ranked = {"any": 0, "review": 1, "test": 2}
    return max(values, key=lambda value: ranked.get(value, 0), default="any")


def _merge_children(children: Sequence[NodeSpec],
                    groups: Sequence[Sequence[int]]) -> list[NodeSpec]:
    """Union the children a merge group covers into one child (design §2)."""
    merged: list[NodeSpec] = []
    for group in groups:
        specs = [children[i] for i in group]
        if len(specs) == 1:
            merged.append(specs[0])
            continue
        merged.append(NodeSpec(
            goal=" + ".join(s.goal for s in specs),
            why=" + ".join(s.why for s in specs if s.why),
            files=tuple(sorted({f for s in specs for f in s.files})),
            acs=tuple(a for s in specs for a in s.acs),
            interfaces=tuple(i for s in specs for i in s.interfaces),
            kind="leaf",
            est_calls=sum(s.est_calls for s in specs),
            # Ticket 20: the merged child carries the STRONGEST requirement and the UNION
            # of its parts' review angles, and is best-effort only when every part was.
            verification_required=_strongest_requirement(s.verification_required
                                                         for s in specs),
            review_angles=tuple(dict.fromkeys(
                angle for s in specs for angle in s.review_angles)),
            review_level=DEFAULT_REVIEW_LEVEL,
            best_effort=all(s.best_effort for s in specs),
            best_effort_reason=(next((s.best_effort_reason for s in specs
                                      if s.best_effort_reason), "")),
        ))
    return merged


# ---------------------------------------------------------------------------
# Node execution
# ---------------------------------------------------------------------------


def _parked(node_id: str, reason: str, wall_s: float, *, evidence: str = "",
            children: list[NodeOutcome] | None = None,
            leaf: LeafOutcome | None = None,
            resplit_rounds: int = 0, respec_rounds: int = 0,
            close_rule: str = "", integration_reopen_rounds: int = 0,
            integration_verdicts: dict[str, str] | None = None) -> NodeOutcome:
    return NodeOutcome(node_id=node_id, claimed=False, stop_reason="parked",
                       leaf=leaf, children=children or [], wall_s=wall_s,
                       evidence=evidence or reason,
                       resplit_rounds=resplit_rounds, respec_rounds=respec_rounds,
                       close_rule=close_rule,
                       integration_reopen_rounds=integration_reopen_rounds,
                       integration_verdicts=dict(integration_verdicts or {}))


def _how_dict(how: How) -> dict:
    return {"how_id": how.id, "text": how.text, "rank": how.rank,
            "reason": how.reason, "prior": how.prior, "status": how.status}


def _leaf_outcomes(outcome: NodeOutcome):
    """Every leaf outcome in a node's subtree (for selection / review verdicts)."""
    if outcome.leaf is not None:
        yield outcome.leaf
    for child in outcome.children:
        yield from _leaf_outcomes(child)


def _candidate_test_points(decomp: Decomposition | None) -> tuple[TestPoint, ...]:
    """The DECLARED test points a candidate's plan names (node spec + its children).

    Ticket 20 step 2b-ii: the plan-time test list is the contract a candidate is scored
    against. A candidate's plan is its How's decomposition, so the points are the node's
    own declared cases plus its children's, de-duplicated by ``file::name``. Empty when
    the plan declared none — the test component stays ``(0, 0.0)`` as before.
    """
    if decomp is None:
        return ()
    points: list[TestPoint] = []
    seen: set[str] = set()
    for candidate_spec in (decomp.spec, *decomp.children):
        for point in planned_test_points(candidate_spec):
            if point.id in seen:
                continue
            seen.add(point.id)
            points.append(point)
    return tuple(points)


def _candidate_selection(outcome: NodeOutcome, how: How, cost: int, *,
                         planned_points: Sequence[TestPoint] = (),
                         test_results: Mapping[str, bool] | None = None) -> Selection:
    """The ONE selection key for a candidate outcome (ticket 20 step 2b-ii).

    The test component is scored over the candidate's DECLARED test points, never the
    tests it invented: ``(points covered, pass rate over the declared points)`` from
    :func:`harness.how.point_results`, which reads the candidate subtree's own-test gate
    reports. The review component is the subtree's review verdicts, and the tie-break
    chain is rank then cost. A negative/vetoed review surfaces as ``needs_repair`` (an
    ACTION ITEM). With no declared points the test component is ``(0, 0.0)`` and the
    comparison falls through to review, exactly as before.
    """
    verdicts = [v for leaf in _leaf_outcomes(outcome)
                for v in (getattr(leaf, "review_verdicts", ()) or ())]
    return select_key(planned_test_points=tuple(p.id for p in planned_points),
                      test_results=test_results,
                      review_verdicts=verdicts, rank=how.rank, cost=cost)


async def _plan_hows(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec,
                     budget: Budget, *, evidence: str = "") -> HowList | None:
    """The FIRST planning step: ONE ``how_list`` call producing the node's ranked Hows.

    Returns ``None`` when the node cannot afford the call, the model is unable, or the
    output is malformed — the caller then falls back to the legacy unbound plan. The
    prior always comes from the rank table (:func:`harness.how.how_list_from_envelope`).
    """
    before = budget.spent_calls
    if budget.calls < 1:
        return None
    budget.take(1)
    artifacts = {
        "node_goal": spec.goal,
        "write_boundary": "\n".join(spec.files) or "(none: this node owns no files)",
        "candidate_files": "\n".join(sorted(ctx.candidate_files)),
        "depth": str(ctx.depths[node.id]),
    }
    question = (
        "List the candidate APPROACHES (Hows) for THIS node in one call: one paragraph "
        "of how it would be done, a unique rank (1 = try first), a reason why it is "
        "worth a look, and a unique HOW-<n> id. Diversity comes from the How, not from "
        "resampling one prompt. Each How the budget lets the node explore gets its own "
        "decomposition and its own isolated candidate directory; a failed How is "
        "abandoned and a NEW one appended, never edited.")
    if evidence:
        question += "\nPRIOR ATTEMPT REJECTED — offer genuinely different Hows:\n" + evidence
    try:
        env = await llm_step(ctx.model, "how_list", artifacts=artifacts,
                             question=question)
    except Exception:  # noqa: BLE001 — a model failure is data, not a crash
        ctx.total_calls += budget.spent_calls - before
        return None
    ctx.total_calls += budget.spent_calls - before
    if env is None or getattr(env, "status", "unable") == "unable":
        return None
    try:
        hows = how_list_from_envelope(env)
    except Exception:  # noqa: BLE001 — malformed output → legacy fallback
        return None
    if len(hows) == 0:
        return None
    ctx.emit("how_list", node=node.id, hows=[h.id for h in hows])
    return hows


async def _plan_how(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec, budget: Budget,
                    how: How) -> Decomposition | None:
    """Plan ONE How's decomposition, bound to ``how.id`` (``PlanNode.how_id``)."""
    before = budget.spent_calls
    evidence = f"How {how.id}: {how.text}\nWhy this approach: {how.reason}"
    decomp = await plan_node(
        ctx.model, goal=spec.goal, evidence=evidence, boundary=set(spec.files),
        candidate_files=ctx.candidate_files, depth=ctx.depths[node.id],
        depth_cap=ctx.depth_cap, max_children=ctx.max_children,
        budget=budget, on_event=ctx.on_event)
    ctx.total_calls += budget.spent_calls - before
    if decomp is None or not decomp.children:
        return None
    return replace(decomp, how_id=how.id, spec=replace(decomp.spec, how_id=how.id))


async def _author_how(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec, budget: Budget,
                      cs: CandidateSet, evidence: str) -> How | None:
    """Author a NEW How after a failure (append-only; the old How is never edited).

    The HARNESS owns the id of a harness-authored How: it scans the ids already present
    and picks the smallest genuinely UNUSED ``HOW-<n>``. A model that named its Hows
    non-sequentially (a lone ``HOW-2``, or ``HOW-1``/``HOW-3``) therefore cannot make the
    synthetic id collide with an existing one. A fresh model How is used only when its id
    is unused as well.
    """
    fresh = await _plan_hows(ctx, node, spec, budget, evidence=evidence)
    if fresh is not None:
        for how in fresh:
            if cs.hows.get(how.id) is None:
                return how
    # No fresh model How: append a synthetic one so the node retries with a genuinely new
    # candidate instead of editing the failed plan.
    rank = len(cs.hows.hows) + 1
    return make_how(
        _unused_how_id({h.id for h in cs.hows}),
        f"new approach after failure: {(evidence or 'prior attempt failed')[:120]}",
        rank,
        "no fresh model How was available; append one so the node can retry")


def _unused_how_id(existing: set[str]) -> str:
    """The smallest ``HOW-<n>`` id not present in ``existing`` (harness-owned ids)."""
    n = 1
    while f"HOW-{n}" in existing:
        n += 1
    return f"HOW-{n}"


async def _apply_decomposition(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec,
                               budget: Budget, decomp: Decomposition,
                               reuse_handles: Sequence[NodeHandle], workdir: Path,
                               ) -> tuple[NodeOutcome, list[NodeHandle]] | None:
    """Split the budget, apply the repeat-refusal rule, and run the children.

    ``None`` means the decomposition cannot be run (too small to fund, an identical
    non-shrinking repeat, or a smaller re-plan than the existing subtree). The children
    run inside ``workdir`` — the candidate's OWN isolated copy in the How path, or the
    run's workdir in the legacy single-plan path.
    """
    nid = node.id
    weights = [c.est_calls for c in decomp.children]
    spendable = int(budget.calls * (1.0 - budget.reserve_fraction))
    groups = group_weights(weights, spendable=spendable, min_each=ctx.min_leaf_calls)
    if groups is None:
        return None  # cannot fund two leaves → force a leaf
    merged = _merge_children(decomp.children, groups)
    # The shrink comparison uses a STABLE pool (the node's first non-reserve pool), so a
    # repeated decomposition is recognized even though running children changed the live
    # budget.
    pool = ctx.split_pool.setdefault(nid, int(budget.calls * (1.0 - budget.reserve_fraction)))
    total_weight = max(1, sum(weights))
    max_child_budget = max(
        (pool * sum(weights[i] for i in g)) // total_weight for g in groups)
    hist = ctx.split_history.setdefault(nid, SplitHistory())
    if not hist.accept(decomp.signature, n_children=len(merged),
                       max_child_budget=max_child_budget):
        ctx.emit("split_wasted", node=nid, signature=decomp.signature, wasted=hist.wasted)
        return None
    needed = len(merged) + 1
    if reuse_handles and needed < len(reuse_handles):
        return None
    try:
        budgets = split_weighted(budget, weights, min_leaf_calls=ctx.min_leaf_calls)
    except BudgetError:
        return None
    return await _attempt_internal(ctx, node, spec, merged, budgets, budget,
                                   reuse_handles, workdir)


async def _run_hows(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec, budget: Budget,
                    workdir: Path, hows: HowList, *,
                    source: Path | None = None) -> NodeOutcome:
    """Explore the node's How candidates, pick the winner, with NO destructive reset.

    Each How gets its OWN isolated candidate copy (never a git worktree / reset) and its
    own decomposition; the How's children run inside that copy. ``source`` is the pristine
    tree every candidate is copied FROM (defaults to ``workdir``); the leaf path passes the
    pre-first-attempt snapshot so a failed attempt's writes can never seed a candidate
    (ticket 20 step 2b D2). Every model call any candidate makes is charged to the node's
    budget: child budgets are split from the node pool per candidate and released exactly
    once, so a candidate that cannot afford its next call does not open and its unused
    budget returns. On failure the structured record goes to the manager loop; a negative
    review is an ACTION ITEM.
    """
    nid = node.id
    started = ctx.now()
    origin = Path(source) if source is not None else workdir
    cs = CandidateSet(node_id=nid, run_outdir=ctx.run_outdir, source=origin)
    for how in hows:
        # A duplicate id inside ONE envelope is refused without crashing: keep the first.
        if cs.hows.get(how.id) is None:
            cs.add_how(how)
    # The exploration cap is CUMULATIVE per node: computed ONCE from the node's non-reserve
    # pool and never recounted, so a manager that authors Hows cannot raise it (D5).
    exploration_limit = how_exploration_limit(budget, None,
                                              min_leaf_calls=ctx.min_leaf_calls)
    records: list[CandidateRecord] = []
    closed: list[tuple[CandidateRecord, NodeOutcome]] = []
    repair_action = ""
    refusal = ""
    reuse_handles: list[NodeHandle] = []
    explored = 0
    stop = False
    reviewed_feasibility: set[str] = set()
    while not stop and not ctx.expired(budget):
        if explored >= exploration_limit:
            break
        untried = list(cs.hows.untried())
        if not untried:
            break
        how = untried[0]
        explored += 1
        ws = cs.open(how.id)
        before = budget.spent_calls
        decomp = await _plan_how(ctx, node, spec, budget, how)
        result: NodeOutcome | None = None
        if decomp is not None and decomp.children:
            applied = await _apply_decomposition(ctx, node, spec, budget, decomp,
                                                 reuse_handles, ws.path)
            if applied is not None:
                result, reuse_handles = applied
        cost = budget.spent_calls - before
        # Ticket 20 step 2b-ii: the candidate's plan-time test list is its contract. Its
        # DEVIATIONS (extra tests beyond the declared points) do not score, but are
        # reported to the managing call; the candidate is scored over the declared points.
        points = _candidate_test_points(decomp)
        plan_dicts = [point.to_dict() for point in points]
        leaves = list(_leaf_outcomes(result)) if result is not None else []
        deviations = extra_test_points(points, leaves)
        if deviations:
            cs.record_deviations(deviations)
            ctx.emit("test_deviation", node=nid, how=how.id, extra=list(deviations))
        if result is not None and result.claimed and result.stop_reason == "closed":
            selection = _candidate_selection(
                result, how, cost, planned_points=points,
                test_results=point_results(points, leaves))
            record = CandidateRecord(how.id, how.rank, "succeeded", str(ws.path), selection,
                                     planned_points=plan_dicts,
                                     deviations=list(deviations))
            records.append(record)
            cs.record_selection(how.id, selection)
            if selection.needs_repair:
                # A negative review is an ACTION ITEM, not a lost comparison: do not
                # accept it; keep working on the remaining Hows.
                repair_action = selection.repair_reason
                record.status = "abandoned"
                cs.hows = cs.hows.with_status(how.id, "abandoned")
                ctx.emit("candidate_repair", node=nid, how=how.id,
                         reason=selection.repair_reason)
            else:
                cs.succeed(how.id)
                closed.append((record, result))
            continue
        # Failure: the structured evidence + reason go to the manager loop.
        evidence = (result.evidence if result is not None
                    else "the How produced no decomposition")
        stop_reason = result.stop_reason if result is not None else "no-decomposition"
        cs.fail(how.id, evidence=evidence, reason=stop_reason)
        records.append(CandidateRecord(how.id, how.rank, "failed", str(ws.path), None,
                                       evidence, planned_points=plan_dicts,
                                       deviations=list(deviations)))
        decision = decide_after_failure(cs.manager_view(current_how_id=how.id),
                                        manager=ctx.manager)
        cs.record(decision)
        ctx.emit("manager_decision", node=nid, how=how.id,
                 decision=decision.decision, reason=decision.reason)
        if decision.decision == "request-feasibility-review" \
                and how.id not in reviewed_feasibility:
            # Wire the dead decision (D4): run the PLAN-level feasibility review and feed
            # its verdict into decide_after_failure. Only an "infeasible" verdict advances
            # automatically; anything else returns to the manager (or parks with none).
            reviewed_feasibility.add(how.id)
            feasibility = await _run_feasibility_review(
                ctx, nid, spec, budget, how, decomp, evidence)
            decision = decide_after_failure(cs.manager_view(current_how_id=how.id),
                                            feasibility=feasibility, manager=ctx.manager)
            cs.record(decision)
            ctx.emit("manager_decision", node=nid, how=how.id,
                     decision=decision.decision, reason=decision.reason,
                     feasibility=feasibility)
        if decision.decision == "author-a-new-how":
            try:
                appended = await _author_how(ctx, node, spec, budget, cs, evidence)
                if appended is not None:
                    cs.add_how(appended)
                    ctx.emit("how_appended", node=nid, how=appended.id)
            except Exception as exc:  # noqa: BLE001 — an unusable How must never crash
                refusal = f"authored How refused: {exc}"
                cs.record(ManagerDecision("escalate-or-park", refusal))
                ctx.emit("how_refused", node=nid, how=how.id, reason=str(exc))
                stop = True
        elif decision.decision == "continue-with-next-how":
            continue
        else:
            stop = True

    if not closed:
        # Nothing qualifies: abandon every remaining candidate directory and park. No
        # git reset is involved — the candidate copies are simply discarded.
        for how in list(cs.hows):
            ws = cs.workspaces.pop(how.id, None)
            if ws is not None:
                abandon_candidate(ws)
        evidence = repair_action or refusal or "no candidate closed"
        parked = _parked(nid, "parked", round(ctx.now() - started, 3),
                         evidence=f"no How candidate closed: {evidence}")
        parked.hows = [_how_dict(h) for h in cs.hows]
        parked.candidates = records
        parked.manager_decisions = [{"decision": d.decision, "reason": d.reason}
                                    for d in cs.decisions]
        return parked

    # SELECTION DRIVES THE OUTCOME: the ONE picker, never a model vote.
    winner_selection = pick([record.selection for record, _ in closed])
    winner_record, winner_outcome = next(
        (record, outcome) for record, outcome in closed
        if record.selection is winner_selection)
    winner_record.won = True
    unsupported = _merge_candidate(Path(winner_record.directory), workdir)
    if unsupported:
        ctx.emit("merge_unsupported", node=nid, how=winner_record.how_id,
                 paths=unsupported)
    for record, _ in closed:
        if record is not winner_record:
            record.status = "abandoned"
            cs.hows = cs.hows.with_status(record.how_id, "abandoned")
    for how in list(cs.hows):
        ws = cs.workspaces.pop(how.id, None)
        if ws is not None and how.id != winner_record.how_id:
            abandon_candidate(ws)
    ctx.emit("node_hows_selected", node=nid, winner=winner_record.how_id,
             candidates=len(records), decisions=len(cs.decisions))
    winner_outcome.hows = [_how_dict(h) for h in cs.hows]
    winner_outcome.candidates = records
    winner_outcome.manager_decisions = [{"decision": d.decision, "reason": d.reason}
                                        for d in cs.decisions]
    winner_outcome.winner = winner_record.how_id
    return winner_outcome


#: Tree-copy exclusions: git state and interpreter/pytest caches are never candidate
#: content (``.git`` must survive in the node tree so the trajectory stays usable).
_TREE_COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache",
                                           "*.pyc", "*.pyo")


def _snapshot_tree(workdir: Path) -> Path:
    """A pristine filesystem COPY of ``workdir`` (no ``.git`` / caches, links kept).

    Ticket 20 step 2b D2: taken BEFORE a node's first attempt so a failed attempt's
    in-boundary writes can never seed a candidate copy; it replaces the removed git
    checkpoint (there is no ``git reset`` anymore).
    """
    root = Path(tempfile.mkdtemp(prefix="helpagent-node-snapshot-"))
    shutil.copytree(Path(workdir), root, ignore=_TREE_COPY_IGNORE, symlinks=True,
                    dirs_exist_ok=True)
    return root


def _excluded(rel: Path) -> bool:
    """True for a relative path that is git state or an interpreter/pytest cache."""
    return (".git" in rel.parts or "__pycache__" in rel.parts
            or ".pytest_cache" in rel.parts or rel.suffix in (".pyc", ".pyo"))


def _prune_empty_dirs(workdir: Path) -> None:
    """Remove directories left empty after a merge (deepest first), caches/.git kept."""
    for path in sorted(workdir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink() or not path.is_dir() or _excluded(path.relative_to(workdir)):
            continue
        try:
            path.rmdir()
        except OSError:
            pass


def _merge_candidate(source: Path, workdir: Path) -> list[str]:
    """Make ``workdir`` EQUAL to the winning candidate tree (no git).

    The candidate was a COPY of the node's (snapshot) tree, so the merge both copies its
    changed/added files back AND removes every non-excluded path the candidate no longer
    has --- its DELETIONS (ticket 20 step 2b D3), plus any stale write left by an earlier
    failed attempt (D2). ``.git`` and interpreter/pytest caches are never touched.

    A symlink is not reproducible by this copy: every symlink in the candidate (or a
    stale one in the node tree) is returned as an UNSUPPORTED entry so the caller records
    it, rather than silently dropping it.
    """
    source = Path(source)
    workdir = Path(workdir)
    unsupported: list[str] = []
    candidate_files: set[str] = set()
    candidate_dirs: set[str] = set()
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        if _excluded(rel):
            continue
        if path.is_symlink():
            unsupported.append(rel.as_posix())
            continue
        if path.is_dir():
            candidate_dirs.add(rel.as_posix())
        elif path.is_file():
            candidate_files.add(rel.as_posix())
    # Remove node-tree paths the candidate does not have (deletions + stale failed writes).
    for path in sorted(workdir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = path.relative_to(workdir)
        if _excluded(rel):
            continue
        if path.is_symlink():
            unsupported.append(rel.as_posix())
            path.unlink(missing_ok=True)
            continue
        if path.is_dir() or rel.as_posix() in candidate_files \
                or rel.as_posix() in candidate_dirs:
            continue
        path.unlink(missing_ok=True)
    # Copy the candidate's directories and files.
    for rel in sorted(candidate_dirs):
        dest = workdir / rel
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            dest.unlink(missing_ok=True)
        dest.mkdir(parents=True, exist_ok=True)
    for rel in sorted(candidate_files):
        src = source / rel
        dest = workdir / rel
        if dest.is_symlink():
            dest.unlink(missing_ok=True)
        elif dest.is_dir():
            shutil.rmtree(dest)          # a directory replaced by this file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    _prune_empty_dirs(workdir)
    return unsupported


def _plan_review_request(spec: NodeSpec, how: How, decomp: Decomposition | None,
                         evidence: str, angle: str) -> ReviewRequest:
    """The PLAN-level review view for ONE angle: the How, its decomposition, and why the
    attempt failed (there is no diff at plan time).  Its ``reason`` carries the plan facts
    the plan angles judge; ``original``/``final`` are empty."""
    if decomp is not None and decomp.children:
        lines = [f"- {c.goal} [{', '.join(c.files) or 'no files'}]"
                 for c in decomp.children]
    else:
        lines = ["(no decomposition was produced)"]
    reason = (
        f"How {how.id}: {how.text}\n"
        f"Why this approach was worth a look: {how.reason}\n"
        "Its decomposition:\n" + "\n".join(lines) + "\n"
        f"Failure evidence: {evidence or 'the How failed with no recorded reason'}")
    return ReviewRequest(goal=spec.goal, acs=list(spec.acs), original={}, final={},
                         reason=reason, angle=angle)


async def _run_feasibility_review(ctx: _TreeContext, nid: str, spec: NodeSpec,
                                  budget: Budget, how: How,
                                  decomp: Decomposition | None, evidence: str) -> str:
    """The PLAN-level feasibility review of a failed How (ticket 20 step 2b D4).

    Runs ONE fresh-context review per PREDEFINED plan angle (the ``"plan"``
    :data:`harness.leaf.REVIEW_ANGLES_BY_LEVEL`), giving the reviewer the How text, its
    decomposition, and the failure evidence, and combines the graded verdicts with the
    plan-level critical-angle veto. Returns ``"infeasible"`` when a plan angle grades the
    approach problematic, ``"feasible"`` when the combined review is clean, and
    ``"unknown"`` when no review could be run (no reviewer, no budget, or a malformed
    result). The verdict is data: only ``"infeasible"`` lets the node advance
    automatically.
    """
    if ctx.review is None or budget.calls < 1:
        return "unknown"
    angles = review_angles_for_level("plan")
    verdicts: list[ReviewVerdict] = []
    for angle in angles:
        if budget.calls < 1:
            break
        budget.take(1)
        request = _plan_review_request(spec, how, decomp, evidence, angle)
        try:
            verdict = await _call_review(ctx.review, request)
        except Exception:  # noqa: BLE001 — a model failure is data, not a crash
            break
        if not verdict.angle:
            verdict = replace(verdict, angle=angle)
        verdicts.append(verdict)
    ctx.emit("feasibility_review", node=nid, how=how.id,
             grades={v.angle: v.grade for v in verdicts})
    if not verdicts:
        return "unknown"
    ok, _score, _why = combine_review_verdicts(verdicts, angles, "plan")
    if ok:
        return "feasible"
    if any(review_grade_rank(v.grade) < 0 for v in verdicts):
        return "infeasible"
    return "unknown"


async def run_node(ctx: _TreeContext, node: NodeHandle, budget: Budget,
                   workdir: Path | None = None) -> NodeOutcome:
    """Run one node: plan Hows first, decompose, else execute it as a leaf.

    Ticket 20 step 2b: planning is HOW-first. A node that can decompose lists its Hows
    (``how_list``) and explores the affordable ones as candidate copies; the winner is
    chosen by :func:`harness.how.pick`. A failed candidate goes through the manager loop
    and the node appends a NEW How — there is NO ``git reset --hard`` / ``git clean``
    anywhere. A node that cannot plan Hows falls back to the legacy unbound plan; on
    exhaustion or a spec bubble it parks instead of resetting.
    """
    nid = node.id
    spec = ctx.specs[nid]
    depth = ctx.depths[nid]
    workdir = Path(workdir) if workdir is not None else ctx.workdir
    started = ctx.now()

    if ctx.expired(budget) or budget.calls < 1:
        reason = "deadline" if ctx.expired(budget) else "calls"
        ctx.emit("node_parked", node=nid, reason=reason)
        return _parked(nid, reason, round(ctx.now() - started, 3))

    if workdir == ctx.workdir:
        # A resume marker only; nothing resets it (ticket 20 step 2b).
        ctx.checkpoints[nid] = ctx.trajectory.checkpoint(nid)

    if spec.kind == "internal" and depth < ctx.depth_cap and can_decompose(
            budget, 2, min_leaf_calls=ctx.min_leaf_calls):
        hows = await _plan_hows(ctx, node, spec, budget)
        if hows:
            return await _run_hows(ctx, node, spec, budget, workdir, hows)
        # Legacy fallback: no Hows available → the single unbound plan.
        plan = await _plan(ctx, node, spec, budget, "")
        if plan is not None:
            applied = await _apply_decomposition(ctx, node, spec, budget, plan, (),
                                                 workdir)
            if applied is not None:
                result, _handles = applied
                if result.stop_reason == "respec":
                    return _parked(nid, "needs-user", round(ctx.now() - started, 3),
                                   evidence="spec bubble: no reset; append a How via the "
                                            "How path to try a new approach",
                                   children=result.children)
                return result

    # Leaf path (a declared leaf, or a node that could not afford to decompose).
    # D2: snapshot the node tree BEFORE the first attempt, so an in-boundary write the
    # attempt leaves behind can never seed a candidate copy or the merged tree. This
    # replaces the removed L6 git reset without git.
    snapshot = _snapshot_tree(workdir)
    try:
        result = await _run_leaf_node(ctx, node, spec, budget, workdir)
        if result.stop_reason == "resplit":
            # L6 replacement: append a How and switch candidate instead of resetting git.
            hows = await _plan_hows(ctx, node, spec, budget, evidence=result.evidence)
            if hows:
                outcome = await _run_hows(ctx, node, spec, budget, workdir, hows,
                                          source=snapshot)
                if not outcome.claimed:
                    # No candidate won: drop the failed attempt's writes too.
                    _merge_candidate(snapshot, workdir)
                return outcome
            _merge_candidate(snapshot, workdir)
            return _parked(nid, "needs-user", round(ctx.now() - started, 3),
                           evidence="node exhausted; no new How available (no destructive "
                                    "reset)", leaf=result.leaf)
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)
    # A spec bubble ("respec") is NOT handled here: it propagates UP to the owning node,
    # whose candidate loop consults the manager and appends a new How (no reset).
    return result


async def _run_leaf_node(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec,
                         budget: Budget, workdir: Path) -> NodeOutcome:
    """Execute one node as a leaf through :func:`run_leaf` (the single work primitive).

    The write boundary is AUDITED, not trusted (ticket 18 gap A): the work tree is
    snapshotted before ``run_leaf`` and resnapshotted after, and any path that changed
    outside the allowed set (the leaf's declared boundary plus every test path) is
    restored from the pre-leaf snapshot. A boundary escape invalidates the leaf's claim
    (``stop_reason == "boundary-escape"``) so the node never closes on code that wrote
    outside its boundary.
    """
    leaf_spec = leaf_spec_from(spec, workdir, root_grader_paths=ctx.root_grader_paths,
                               candidate_files=tuple(sorted(ctx.candidate_files)))
    before_state = snapshot_workdir(workdir)
    before = budget.spent_calls
    outcome = await run_leaf(
        ctx.model, leaf_spec, workdir, budget, judge=ctx.judge, iv=ctx.iv,
        review=ctx.review, run_tests=ctx.run_tests, now=ctx.now, on_event=ctx.on_event)
    ctx.total_calls += budget.spent_calls - before
    audit = audit_leaf_boundary(workdir, before_state,
                                leaf_spec.write_boundary or ())
    if not audit.clean:
        ctx.emit("boundary_escape", node=node.id, violations=list(audit.violations),
                 restored=list(audit.restored), removed=list(audit.removed),
                 links=dict(audit.links), metadata=list(audit.metadata),
                 restore_refused=list(audit.restore_refused),
                 skipped=list(audit.skipped))
    if not audit.clean and outcome.claimed:
        # The leaf's claim rested on evidence the audit cannot certify: code that
        # escaped the write boundary, or a snapshot that had to skip entries. The run
        # must NOT claim. Record the exact paths, keep the leaf's evidence, and let the
        # ordinary flow run (a non-claimed node never closes).
        if audit.violations:
            reason = "boundary-escape"
            detail = ("write-boundary escape: changed paths outside the declared "
                      "boundary and the test paths: " + ", ".join(audit.violations))
        else:
            reason = "audit-incomplete"
            detail = ("the pre/post snapshot could not cover the work tree, so the leaf "
                      "cannot be certified: " + ", ".join(audit.skipped))
        outcome = replace(
            outcome, claimed=False, signal="honest-failure",
            stop_reason=reason, exhausted=False, needs_parent=False,
            exhaustion_reason=detail)
    _record_leaf_map(node, spec, outcome)

    if outcome.claimed:
        _force_done(ctx, node)
        ctx.emit("leaf_closed", node=node.id, stop_reason=outcome.stop_reason)
        return NodeOutcome(node_id=node.id, claimed=True, stop_reason="closed",
                           leaf=outcome, calls=outcome.calls, wall_s=outcome.wall_s,
                           boundary_audit=audit)
    if outcome.signal == "exhausted":
        return NodeOutcome(node_id=node.id, claimed=False, stop_reason="resplit",
                           leaf=outcome, calls=outcome.calls, wall_s=outcome.wall_s,
                           evidence=outcome.exhaustion_reason or "node exhausted",
                           boundary_audit=audit)
    if outcome.needs_parent and outcome.stop_reason == "spec-bubble":
        return NodeOutcome(node_id=node.id, claimed=False, stop_reason="respec",
                           leaf=outcome, calls=outcome.calls, wall_s=outcome.wall_s,
                           evidence=f"spec bubble: {outcome.exhaustion_reason}",
                           boundary_audit=audit)
    if outcome.stop_reason in ("deadline", "calls"):
        parked = _parked(node.id, outcome.stop_reason, outcome.wall_s, leaf=outcome)
        parked.boundary_audit = audit
        return parked
    return NodeOutcome(node_id=node.id, claimed=False,
                       stop_reason=outcome.stop_reason or outcome.signal or "honest-failure",
                       leaf=outcome, calls=outcome.calls, wall_s=outcome.wall_s,
                       boundary_audit=audit)


async def _run_integration_leaf(ctx: _TreeContext, integration_handle: NodeHandle,
                               budget: Budget, workdir: Path) -> list[str]:
    """Run the dedicated integration leaf on the parent's reserve; return its check keys.

    Integration work draws on the parent's reserve (DESIGN §10.2), not the children's
    split, so a merge can never fold the integration leaf into a source child. Returns
    ``[]`` when no reserve is left OR the leaf exposed no test artifact — and an
    integration leaf with no keys is NOT an integration verdict (ticket 18 gap 1).
    """
    if budget.calls < 1:
        return []
    calls = budget.calls
    budget.take(calls)
    child_budget = Budget(calls=calls, deadline_ts=budget.deadline_ts,
                          reserve_fraction=budget.reserve_fraction)
    try:
        await run_node(ctx, integration_handle, child_budget, workdir)
    finally:
        budget.release(child_budget)
    return [e.key for e in integration_handle.ac_test_map]


def _reopen_budgets(ctx: _TreeContext, budget: Budget, n: int) -> list[Budget] | None:
    """Fresh budgets to re-run ``n`` responsible writers after a failed integration.

    ``None`` when the parent pool can no longer fund one ``min_leaf_calls`` writer each
    (the caller then parks ``needs-integration`` rather than re-run unaffordably).
    """
    if n < 1:
        return None
    try:
        fresh = budget.split_weighted([1] * n, min_each=ctx.min_leaf_calls)
    except BudgetError:
        return None
    return fresh if len(fresh) == n else None


def _finish_internal(ctx: _TreeContext, node: NodeHandle,
                     outcomes: Sequence[NodeOutcome | None], *, results: CheckResults | None,
                     rule: str, writers: int, started: float,
                     handles: list[NodeHandle],
                     integration_reopen_rounds: int = 0) -> tuple[NodeOutcome, list[NodeHandle]]:
    """Close the parent and shape its outcome, recording which close rule applied."""
    done = [o for o in outcomes if o is not None]
    if results is not None:
        closed = node.close(results=results)
        verdicts = dict(results.verdicts)
    else:
        closed = node.close()
        verdicts = {}
    claimed = (bool(closed) and len(done) == len(outcomes)
               and all(o.stop_reason == "closed" for o in done))
    if closed:
        _force_done(ctx, node)
    ctx.emit("internal_close" if claimed else "internal_open", node=node.id, rule=rule,
             writers=writers, verdicts=verdicts,
             reasons=list(getattr(closed, "reasons", []) or []))
    return (NodeOutcome(node_id=node.id, claimed=claimed,
                        stop_reason="closed" if claimed else "open",
                        children=done, wall_s=round(ctx.now() - started, 3),
                        integration_verdicts=verdicts, close_rule=rule,
                        integration_reopen_rounds=integration_reopen_rounds,
                        calls=sum(o.calls for o in done)), handles)


async def _attempt_internal(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec,
                            children: Sequence[NodeSpec], budgets: Sequence[Budget],
                            budget: Budget,
                            reuse_handles: Sequence[NodeHandle],
                            workdir: Path,
                            ) -> tuple[NodeOutcome, list[NodeHandle]]:
    """Insert children plus one dedicated integration leaf, run them, apply the close rule.

    The integration leaf is inserted UP FRONT (before any source child runs) even when
    the node may not need it: a later insert would run the tree-edit cascade and mark
    the already ``done`` source children ``stale``. It is RUN only when the node owes an
    integration check (≥2 writing descendants, or integration ACs of its own); otherwise
    it is force-closed unrun — the ``close_single_writer`` rule, since there is nothing
    to integrate (ticket 18 gap 1). A failing integration verdict reopens its responsible
    writers and re-integrates, bounded to :data:`_MAX_INTEGRATION_REOPEN` rounds before
    the node parks ``needs-integration`` (ticket 18 gap 2).
    """
    started = ctx.now()
    integration_spec = _integration_spec(spec)
    all_specs = list(children) + [integration_spec]
    integration_index = len(children)

    handles: list[NodeHandle] = []
    for i, child in enumerate(all_specs):
        if i < len(reuse_handles):
            handle = reuse_handles[i]
            _reset_handle(ctx, handle)
        else:
            handle = ctx.tree.insert_ticket(node, child.goal, why=child.why,
                                            files=list(child.files))
        ctx.specs[handle.id] = child
        ctx.depths[handle.id] = ctx.depths[node.id] + 1
        handles.append(handle)

    source_handles = handles[:integration_index]
    integration_handle = handles[integration_index]

    # One budget per source handle (aligned by index); re-assigned on a reopen round.
    source_budgets: list[Budget | None] = list(budgets)
    outcomes: list[NodeOutcome | None] = [None] * len(source_handles)
    active = list(range(len(source_handles)))
    reopen_rounds = 0
    keys: list[str] = []

    while True:
        released: set[int] = set()
        try:
            for i in active:
                child_budget = source_budgets[i]
                assert child_budget is not None
                outcome = await run_node(ctx, source_handles[i], child_budget, workdir)
                budget.release(child_budget)
                released.add(i)
                outcomes[i] = outcome
                if outcome.stop_reason in ("respec", "parked"):
                    return (NodeOutcome(node_id=node.id, claimed=False,
                                        stop_reason=outcome.stop_reason,
                                        children=[o for o in outcomes if o is not None],
                                        wall_s=round(ctx.now() - started, 3),
                                        evidence=outcome.evidence), handles)
        finally:
            # A short-circuit (a bubbling/parked child) must still return the unspent
            # pool of the children that never ran, or the parent leaks budget across
            # the reset.
            for i in active:
                child_budget = source_budgets[i]
                if child_budget is not None and i not in released:
                    budget.release(child_budget)

        done = [o for o in outcomes if o is not None]
        writers = _writing_descendants(done)

        if reopen_rounds == 0 and not (bool(spec.acs) or writers >= 2):
            # ≤1 writing descendant and no integration AC of its own: nothing to integrate.
            # Once a reopen round has begun the node already owes a verdict, so this rule
            # is first-round only — a later round re-verifies rather than closing on claims.
            _force_done(ctx, integration_handle)
            ctx.emit("internal_close_rule", node=node.id, rule="close_single_writer",
                     writers=writers)
            return _finish_internal(ctx, node, outcomes, results=None,
                                    rule="close_single_writer", writers=writers,
                                    started=started, handles=handles,
                                    integration_reopen_rounds=reopen_rounds)

        if reopen_rounds == 0:
            keys = await _run_integration_leaf(ctx, integration_handle, budget, workdir)
            if keys:
                # The integration leaf's job is to EXPOSE the check; the verdict is the
                # parent's report-gated re-run of it, so the leaf is done once it produced
                # a test (a red test that the responsible writers then turn green is the
                # normal path). Its own claim is not the gate; an empty artifact is.
                _force_done(ctx, integration_handle)
        if not keys:
            ctx.emit("integration_missing_artifact", node=node.id, writers=writers)
            return _parked(
                node.id, "needs-integration", round(ctx.now() - started, 3),
                evidence="needs-integration: the dedicated integration leaf exposed no "
                         "test artifact (no keys -> no close)",
                children=done, close_rule="needs-integration",
                integration_reopen_rounds=reopen_rounds), handles

        node.set_ac_test_map(_integration_map(integration_spec.acs, keys))
        results = await integration_verdicts(ctx.tree, node, ctx.run_tests, workdir)
        failed = [k for k, v in results.verdicts.items() if v != "pass"]
        if not failed:
            return _finish_internal(ctx, node, outcomes, results=results, rule="integration",
                                    writers=writers, started=started, handles=handles,
                                    integration_reopen_rounds=reopen_rounds)

        # A failing integration verdict reopens its cause: the descendants whose source
        # the check covers. Per-file coverage is not derivable from a check key, so ALL
        # writing descendants are the responsible set (design §10.4 step 6).
        responsible = [i for i in range(len(source_handles))
                       if outcomes[i] is not None and _subtree_wrote_source(outcomes[i])]
        if not responsible:
            # No identifiable writer to reopen: leave the node OPEN (never a false close).
            reasons = list(node.close(results=results).reasons or [])
            ctx.emit("internal_open", node=node.id, verdicts=dict(results.verdicts),
                     reasons=reasons)
            return (NodeOutcome(node_id=node.id, claimed=False, stop_reason="open",
                                children=done, wall_s=round(ctx.now() - started, 3),
                                integration_verdicts=dict(results.verdicts),
                                close_rule="needs-integration",
                                calls=sum(o.calls for o in done)), handles)
        if reopen_rounds >= _MAX_INTEGRATION_REOPEN:
            return _parked(
                node.id, "needs-integration", round(ctx.now() - started, 3),
                evidence="needs-integration: the integration verdict kept failing after "
                         f"{reopen_rounds} reopen round(s)",
                children=done, close_rule="needs-integration",
                integration_reopen_rounds=reopen_rounds,
                integration_verdicts=dict(results.verdicts)), handles
        fresh = _reopen_budgets(ctx, budget, len(responsible))
        if fresh is None:
            return _parked(
                node.id, "needs-integration", round(ctx.now() - started, 3),
                evidence="needs-integration: no call budget left to re-run the responsible "
                         "writers after a failing integration verdict",
                children=done, close_rule="needs-integration",
                integration_reopen_rounds=reopen_rounds,
                integration_verdicts=dict(results.verdicts)), handles
        reopen_rounds += 1
        for j, i in enumerate(responsible):
            _reset_handle(ctx, source_handles[i])   # mark the responsible writers stale
            source_budgets[i] = fresh[j]
        active = responsible
        ctx.emit("integration_reopen", node=node.id, round=reopen_rounds,
                 writers=len(responsible), verdicts=dict(results.verdicts))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_tree(
    model: Any,
    root: NodeSpec,
    tree: TaskTree,
    workdir: Path,
    budget: Budget,
    *,
    root_grader_paths: Sequence[str],
    judge: Any = None,
    iv: Any = None,
    review: Any = None,
    run_tests: Any = None,
    now: Callable[[], float] | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    depth_cap: int = 4,
    max_children: int = 15,
    min_leaf_calls: int = MIN_LEAF_CALLS,
    trajectory: Trajectory | None = None,
    run_outdir: Path | None = None,
    manager: Any = None,
) -> TreeOutcome:
    """Run the whole tree over an already-built :class:`TaskTree` and root :class:`NodeSpec`.

    ``run_leaf`` is called verbatim for every leaf; ``root_grader_paths`` is the single
    grader set every descendant leaf inherits; the shared ``budget`` deadline is the
    final stop (no new node starts once it passes). ``run_outdir`` is the run output area
    How candidate copies live under (ticket 20 step 2b); ``manager`` is the node's
    managing call the failure loop consults (``None`` ⇒ the safe default
    ``escalate-or-park``).
    """
    workdir = Path(workdir)
    trajectory = trajectory or Trajectory(workdir)
    trajectory.ensure_git()
    clock = now or time.monotonic
    ctx = _TreeContext(
        model=model, tree=tree, workdir=workdir, trajectory=trajectory,
        root_grader_paths=tuple(root_grader_paths),
        candidate_files=set(_source_only_view(workdir)),
        judge=judge, iv=iv, review=review, run_tests=run_tests, now=clock, on_event=on_event,
        depth_cap=depth_cap, max_children=max_children, min_leaf_calls=min_leaf_calls,
        run_outdir=Path(run_outdir) if run_outdir is not None else workdir.parent,
        manager=manager)
    ctx.specs[tree.root_id] = root
    ctx.depths[tree.root_id] = 0
    started = clock()
    outcome = await run_node(ctx, tree.root, budget)
    return TreeOutcome(
        root=outcome, claimed=outcome.claimed, calls=ctx.total_calls,
        wall_s=round(clock() - started, 3), budget=budget,
        checkpoints=dict(ctx.checkpoints),
        split_history={k: list(v.attempts) for k, v in ctx.split_history.items()})
