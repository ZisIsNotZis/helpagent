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
- **Restructuring.** L6 (a leaf that stopped ``signal == "exhausted"`` re-splits into
  smaller children) and L7 (a leaf that stopped ``needs_parent`` / ``spec-bubble`` sends
  the owning parent back to its own pre-checkpoint) each reset that node's own subtree
  via :meth:`harness.trajectory.Trajectory.reset_to` and re-run ``plan_node`` with the
  failure as evidence. A re-split whose signature is unchanged AND that does not shrink
  the unit is refused as ``wasted`` (:class:`harness.node.SplitHistory`), so the T-31
  "nine identical retries" defect cannot recur here.
- **Shared deadline — the final stop.** The wall-clock deadline is never hard-split per
  child; when it passes, no new node starts and the checkpoints are kept for resume.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from harness.budget import Budget, BudgetError, group_weights
from harness.leaf import (
    LeafOutcome,
    LeafSpec,
    _default_run_tests,  # the tree's default check runner
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
from harness.runner import note
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

#: Bound on L6 (re-split) / L7 (parent spec) rounds per node before the node parks as
#: ``needs-user`` (design §5). Two rounds is enough to try a genuinely different plan.
_MAX_RESTRUCTURE = 2

#: Bound on integration-verdict reopen rounds per node (ticket 18 gap 2): a failing
#: integration check reopens its responsible writers at most this many times before the
#: node parks with ``needs-integration``, so the reopen cannot loop forever.
_MAX_INTEGRATION_REOPEN = 2


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
    reset_to: str | None = None
    resplit_rounds: int = 0
    respec_rounds: int = 0
    evidence: str = ""
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
        review_rounds=spec.review_rounds,
        best_effort=spec.best_effort,
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
            # Ticket 20: the merged child carries the STRONGEST requirement and the most
            # review rounds of its parts, and is best-effort only when every part was.
            verification_required=_strongest_requirement(s.verification_required
                                                         for s in specs),
            review_rounds=max(s.review_rounds for s in specs),
            best_effort=all(s.best_effort for s in specs),
        ))
    return merged


# ---------------------------------------------------------------------------
# Node execution
# ---------------------------------------------------------------------------


def _parked(node_id: str, reason: str, wall_s: float, *, evidence: str = "",
            children: list[NodeOutcome] | None = None,
            leaf: LeafOutcome | None = None, reset_to: str | None = None,
            resplit_rounds: int = 0, respec_rounds: int = 0,
            close_rule: str = "", integration_reopen_rounds: int = 0,
            integration_verdicts: dict[str, str] | None = None) -> NodeOutcome:
    return NodeOutcome(node_id=node_id, claimed=False, stop_reason="parked",
                       leaf=leaf, children=children or [], wall_s=wall_s,
                       reset_to=reset_to, evidence=evidence or reason,
                       resplit_rounds=resplit_rounds, respec_rounds=respec_rounds,
                       close_rule=close_rule,
                       integration_reopen_rounds=integration_reopen_rounds,
                       integration_verdicts=dict(integration_verdicts or {}))


async def run_node(ctx: _TreeContext, node: NodeHandle, budget: Budget) -> NodeOutcome:
    """Run one node: decompose if it can afford to, else execute it as a leaf.

    L6 (its own leaf exhausted) and L7 (a child's spec bubbled) both reset THIS node's
    subtree to its pre-checkpoint and re-run ``plan_node`` with the failure as evidence,
    bounded to :data:`_MAX_RESTRUCTURE` rounds before the node parks.
    """
    nid = node.id
    spec = ctx.specs[nid]
    depth = ctx.depths[nid]
    started = ctx.now()

    if ctx.expired(budget) or budget.calls < 1:
        reason = "deadline" if ctx.expired(budget) else "calls"
        ctx.emit("node_parked", node=nid, reason=reason)
        return _parked(nid, reason, round(ctx.now() - started, 3))

    checkpoint = ctx.trajectory.checkpoint(nid)
    ctx.checkpoints[nid] = checkpoint

    evidence = ""
    l6_rounds = 0
    l7_rounds = 0
    force_plan = False
    reuse_handles: list[NodeHandle] = []

    while True:
        can_plan = (spec.kind == "internal" or force_plan)
        plan = None
        if can_plan and depth < ctx.depth_cap and can_decompose(
                budget, 2, min_leaf_calls=ctx.min_leaf_calls):
            plan = await _plan(ctx, node, spec, budget, evidence)

        if plan is not None:
            decomp = plan
            weights = [c.est_calls for c in decomp.children]
            spendable = int(budget.calls * (1.0 - budget.reserve_fraction))
            groups = group_weights(weights, spendable=spendable, min_each=ctx.min_leaf_calls)
            budgets: list[Budget] | None = None
            merged: list[NodeSpec] = []
            if groups is not None:
                merged = _merge_children(decomp.children, groups)
                # The shrink comparison uses a STABLE pool (the node's first non-reserve
                # pool), so an identical re-split is recognized even though running the
                # children changed the live budget. "Did this decomposition allocate
                # smaller pieces than the last one?" is a fact about the decomposition.
                pool = ctx.split_pool.setdefault(
                    nid, int(budget.calls * (1.0 - budget.reserve_fraction)))
                total_weight = max(1, sum(weights))
                max_child_budget = max(
                    (pool * sum(weights[i] for i in g)) // total_weight for g in groups)
                hist = ctx.split_history.setdefault(nid, SplitHistory())
                if not hist.accept(decomp.signature, n_children=len(merged),
                                   max_child_budget=max_child_budget):
                    ctx.emit("split_wasted", node=nid, signature=decomp.signature,
                             wasted=hist.wasted)
                    return _parked(nid, "wasted-resplit", round(ctx.now() - started, 3),
                                   evidence="identical re-split refused as wasted",
                                   reset_to=checkpoint, resplit_rounds=l6_rounds,
                                   respec_rounds=l7_rounds)
                # Every internal attempt inserts its children plus one dedicated
                # integration leaf (ticket 18 gap 1), so a re-plan reuses that many.
                needed = len(merged) + 1
                if reuse_handles and needed < len(reuse_handles):
                    return _parked(nid, "restructure-too-small",
                                   round(ctx.now() - started, 3),
                                   evidence="the re-plan produced fewer children than the "
                                            "existing subtree; cannot restructure in place",
                                   reset_to=checkpoint, resplit_rounds=l6_rounds,
                                   respec_rounds=l7_rounds)
                try:
                    budgets = split_weighted(budget, weights, min_leaf_calls=ctx.min_leaf_calls)
                except BudgetError:
                    budgets = None  # second line of defense → force a leaf
            if budgets is not None:
                result, handles = await _attempt_internal(
                    ctx, node, spec, merged, budgets, budget, reuse_handles)
                if result.stop_reason == "respec" and l7_rounds < _MAX_RESTRUCTURE:
                    l7_rounds += 1
                    ctx.trajectory.reset_to(checkpoint, reason="L7",
                                            detail=result.evidence)
                    for handle in handles:
                        _reset_handle(ctx, handle)
                    reuse_handles = handles
                    evidence = result.evidence
                    ctx.emit("l7_respec", node=nid, round=l7_rounds, evidence=evidence)
                    continue
                if result.stop_reason == "respec":
                    return _parked(nid, "needs-user", round(ctx.now() - started, 3),
                                   evidence="L7 round bound reached: the parent spec still "
                                            "does not close",
                                   children=result.children, reset_to=checkpoint,
                                   respec_rounds=l7_rounds)
                result.reset_to = result.reset_to or (
                    checkpoint if result.stop_reason == "parked" else None)
                return result

        # Leaf path.
        result = await _run_leaf_node(ctx, node, spec, budget)
        if result.stop_reason == "resplit" and l6_rounds < _MAX_RESTRUCTURE:
            l6_rounds += 1
            ctx.trajectory.reset_to(checkpoint, reason="L6", detail=result.evidence)
            evidence = result.evidence
            force_plan = True
            ctx.emit("l6_resplit", node=nid, round=l6_rounds, evidence=evidence)
            continue
        if result.stop_reason == "resplit":
            return _parked(nid, "needs-user", round(ctx.now() - started, 3),
                           evidence="L6 round bound reached: the node keeps exhausting",
                           leaf=result.leaf, reset_to=checkpoint, resplit_rounds=l6_rounds)
        result.reset_to = checkpoint if result.leaf is not None and not result.claimed else None
        return result


async def _run_leaf_node(ctx: _TreeContext, node: NodeHandle, spec: NodeSpec,
                         budget: Budget) -> NodeOutcome:
    """Execute one node as a leaf through :func:`run_leaf` (the single work primitive).

    The write boundary is AUDITED, not trusted (ticket 18 gap A): the work tree is
    snapshotted before ``run_leaf`` and resnapshotted after, and any path that changed
    outside the allowed set (the leaf's declared boundary plus every test path) is
    restored from the pre-leaf snapshot. A boundary escape invalidates the leaf's claim
    (``stop_reason == "boundary-escape"``) so the node never closes on code that wrote
    outside its boundary.
    """
    leaf_spec = leaf_spec_from(spec, ctx.workdir, root_grader_paths=ctx.root_grader_paths,
                               candidate_files=tuple(sorted(ctx.candidate_files)))
    before_state = snapshot_workdir(ctx.workdir)
    before = budget.spent_calls
    outcome = await run_leaf(
        ctx.model, leaf_spec, ctx.workdir, budget, judge=ctx.judge, iv=ctx.iv,
        review=ctx.review, run_tests=ctx.run_tests, now=ctx.now, on_event=ctx.on_event)
    ctx.total_calls += budget.spent_calls - before
    audit = audit_leaf_boundary(ctx.workdir, before_state,
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
                               budget: Budget) -> list[str]:
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
        await run_node(ctx, integration_handle, child_budget)
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
                outcome = await run_node(ctx, source_handles[i], child_budget)
                budget.release(child_budget)
                released.add(i)
                outcomes[i] = outcome
                if outcome.stop_reason in ("respec", "parked"):
                    return (NodeOutcome(node_id=node.id, claimed=False,
                                        stop_reason=outcome.stop_reason,
                                        children=[o for o in outcomes if o is not None],
                                        wall_s=round(ctx.now() - started, 3),
                                        evidence=outcome.evidence,
                                        reset_to=outcome.reset_to), handles)
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
            keys = await _run_integration_leaf(ctx, integration_handle, budget)
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
        results = await integration_verdicts(ctx.tree, node, ctx.run_tests, ctx.workdir)
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
) -> TreeOutcome:
    """Run the whole tree over an already-built :class:`TaskTree` and root :class:`NodeSpec`.

    ``run_leaf`` is called verbatim for every leaf; ``root_grader_paths`` is the single
    grader set every descendant leaf inherits; the shared ``budget`` deadline is the
    final stop (no new node starts once it passes).
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
        depth_cap=depth_cap, max_children=max_children, min_leaf_calls=min_leaf_calls)
    ctx.specs[tree.root_id] = root
    ctx.depths[tree.root_id] = 0
    started = clock()
    outcome = await run_node(ctx, tree.root, budget)
    return TreeOutcome(
        root=outcome, claimed=outcome.claimed, calls=ctx.total_calls,
        wall_s=round(clock() - started, 3), budget=budget,
        checkpoints=dict(ctx.checkpoints),
        split_history={k: list(v.attempts) for k, v in ctx.split_history.items()})
