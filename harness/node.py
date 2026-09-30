"""Node plan — the fused per-node decompose+specify call and its deterministic gate.

Ticket 18 (DESIGN §10.1–§10.2). The tree layer turns one working leaf into a budgeted
tree: requirement triage → per-node decompose+specify → leaves → integration. This
module owns the *plan* half of that layer:

- :class:`PlanNode` — ONE ``llm_step`` envelope per node that both DECOMPOSES (the
  ``children`` list) and SPECIFIES (the node's own goal/behavior/files/ACs), so the
  per-node cost is a single call (owner requirement). ``children == []`` declares the
  node a LEAF. Registered in :data:`harness.envelopes.SCHEMAS` as ``plan_node``
  (ENVELOPE_SCHEMAS §23; the registry went 23 → 24 — an additive contract extension,
  deliberate and documented, never a silent drift).
- :class:`NodeSpec` / :class:`Decomposition` — the frozen, validated plan data the
  runner consumes.
- :func:`validate_decomposition` — the deterministic gate (never raises, mirrors
  ``harness.tree``): path canonicalization, child ⊆ parent narrowing, pairwise SIBLING
  DISJOINTNESS, leaf/internal shape, ``est_calls >= 1``, ``what`` dedupe, depth and
  child-count caps, and free-text file-token grounding.
- :func:`can_decompose` / :func:`group_weights` / :meth:`Budget.split_weighted` — the
  budget gate: a node with budget 1 cannot split (DESIGN §10.2), and a child whose
  weighted share falls below :data:`MIN_LEAF_CALLS` is merged (union boundary) or the
  node is forced to a leaf rather than emitting an unworkable child.
- :func:`plan_node` — the ONE call, its bounded one-shot re-ask, and the force-leaf
  fallback (invalid output never crashes and never silently produces a child).
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from harness.budget import Budget, group_weights
from harness.envelopes import ChildPlan, PlanNode, file_tokens
from harness.leaf import (
    COVENANT_DILUTION_SHARE,
    DEFAULT_REVIEW_LEVEL,
    VERIFICATION_REQUIREMENTS,
    DeclaredTestCase,
    review_angles_for_level,
)
from harness.runner import llm_step
from harness.tree import Finding, ValidationFindings

__all__ = [
    "MIN_LEAF_CALLS",
    "MIN_LEAF_CALLS_WITH_JUDGE",
    "ChildPlan",
    "Decomposition",
    "NodeKind",
    "NodeSpec",
    "PlanNode",
    "SplitAttempt",
    "SplitHistory",
    "can_decompose",
    "canonical_path",
    "decomposition_from_envelope",
    "decomposition_signature",
    "group_weights",
    "plan_node",
    "split_weighted",
    "validate_decomposition",
]

#: Minimum calls a single leaf can be handed and still do the work (self-test +
#: >=1 implement + headroom). ``run_tree`` passes the higher value when judge+iv are on.
MIN_LEAF_CALLS = 3
MIN_LEAF_CALLS_WITH_JUDGE = 5

NodeKind = Literal["internal", "leaf"]

#: Grounding exempts abbreviations and version-like numerics that match the
#: file-token shape but are prose/values, not paths (mirrors ChildFill §4).
_GROUNDING_EXEMPT = frozenset({"e.g", "i.e", "etc", "vs", "fig", "no", "cf"})
_NUMERIC = re.compile(r"\d+(?:\.\d+)+")
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Path canonicalization (validation step 1)
# ---------------------------------------------------------------------------


def canonical_path(raw: str) -> str | None:
    """Canonical repo-relative path, or ``None`` for one that may not be declared.

    POSIX ``normpath`` collapses ``./`` and internal ``.``/``..``; an absolute path, a
    path that escapes the repository (``..`` above the root), the empty path, and the
    repository root itself are refused. One spelling per file, so the sibling
    disjointness check cannot be evaded with a path alias.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text.startswith(("~", "/")):
        return None
    norm = posixpath.normpath(text)
    if norm in ("", ".", "..") or norm.startswith(("../", "/")):
        return None
    return norm


def _normalized_what(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _grounded_tokens(*texts: str) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        tokens |= file_tokens(text or "")
    out: set[str] = set()
    for tok in tokens:
        if tok.lower().rstrip(".") in _GROUNDING_EXEMPT or _NUMERIC.fullmatch(tok):
            continue
        canonical = canonical_path(tok)
        out.add(canonical if canonical is not None else tok)
    return out


# ---------------------------------------------------------------------------
# Plan data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeSpec:
    """The frozen plan for one node. ``kind`` is the declared intent; the runner may
    still re-split a declared leaf on L6 (an exhausted leaf is re-planned)."""

    goal: str
    files: tuple[str, ...] = ()
    acs: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    kind: NodeKind = "leaf"
    est_calls: int = 1
    why: str = ""
    behavior: str = ""
    implementation_notes: str = ""
    #: READ-ONLY paths this node's leaf may SEE but not write (ticket 18 gap C). The
    #: integration leaf sets this to the parent's declared files so it can author a test
    #: against the code under integration while its write boundary stays its own test.
    view_files: tuple[str, ...] = ()
    #: Ticket 19 D: the DECLARED per-criterion test cases (file + function names) the
    #: node's leaf must expose and pass. Empty when the plan declared none.
    test_cases: tuple[DeclaredTestCase, ...] = ()
    #: Ticket 20 planning-time covenant: the verification the plan requires of this node's
    #: leaf (``test`` | ``review`` | ``any``), the REVIEW ANGLES the review tier runs (a
    #: closed per-level set; empty = the level's critical angles), the review level, and
    #: whether a weaker tier is an accepted fallback with a PLAN-LEVEL reason.
    verification_required: str = "any"
    review_angles: tuple[str, ...] = ()
    review_level: str = DEFAULT_REVIEW_LEVEL
    best_effort: bool = False
    best_effort_reason: str = ""


@dataclass(frozen=True)
class Decomposition:
    """One node's plan: its own :class:`NodeSpec`, its children, and the split signature."""

    spec: NodeSpec
    children: tuple[NodeSpec, ...]
    signature: str


def decomposition_signature(children: Sequence[NodeSpec]) -> str:
    """Stable identity of a decomposition for the repeat-refusal rule.

    ``hash(sorted(normalized child goals) + sorted(sorted child files))`` — so an
    identical re-split (same goals, same boundaries) is recognized no matter the child
    order or the exact prose casing.
    """
    goals = sorted(_normalized_what(c.goal) for c in children)
    files = sorted(",".join(sorted(canonical_path(f) or f for f in c.files)) for c in children)
    return hashlib.sha1(repr((goals, files)).encode("utf-8")).hexdigest()


def _child_spec_from(child: ChildPlan) -> NodeSpec:
    return NodeSpec(
        goal=child.what,
        why=child.why,
        files=tuple(child.files),
        acs=tuple(a.statement for a in child.acs),
        interfaces=tuple(i.name for i in child.interfaces),
        kind=child.kind,
        est_calls=child.est_calls,
        test_cases=tuple(DeclaredTestCase(t.ac_id, t.file, tuple(t.names))
                         for t in child.test_cases),
        verification_required=child.verification_required,
        review_angles=tuple(child.review_angles),
        best_effort=child.best_effort,
        best_effort_reason=child.best_effort_reason,
    )


def decomposition_from_envelope(env: PlanNode) -> Decomposition:
    """Translate a validated :class:`PlanNode` into a :class:`Decomposition`."""
    children = tuple(_child_spec_from(c) for c in env.children)
    spec = NodeSpec(
        goal=env.goal,
        files=tuple(env.files),
        acs=tuple(a.statement for a in env.acs),
        interfaces=tuple(i.name for i in env.interfaces),
        kind="internal" if children else "leaf",
        behavior=env.behavior,
        implementation_notes=env.implementation_notes,
        test_cases=tuple(DeclaredTestCase(t.ac_id, t.file, tuple(t.names))
                         for t in env.test_cases),
        verification_required=env.verification_required,
        review_angles=tuple(env.review_angles),
        best_effort=env.best_effort,
        best_effort_reason=env.best_effort_reason,
    )
    return Decomposition(spec=spec, children=children,
                         signature=decomposition_signature(children))


# ---------------------------------------------------------------------------
# Deterministic validation
# ---------------------------------------------------------------------------


def _canon_set(paths: Sequence[str], add, label: str) -> set[str]:
    out: set[str] = set()
    for raw in paths:
        canonical = canonical_path(raw)
        if canonical is None:
            add("bad-path", f"{label} declares an unusable path {raw!r}")
        else:
            out.add(canonical)
    return out


def _verification_findings(label: str, files: Sequence[str], required: str,
                            review_angles: Sequence[str], level: str, best_effort: bool,
                            best_effort_reason: str, kind: NodeKind, has_code: bool, add,
                            *, leaf_kind: str = "leaf-empty-files") -> None:
    """Ticket 20 STRUCTURAL hard checks, applied at plan construction (never later).

    A LEAF node MUST have a non-empty file list (a leaf writes code). A NON-LEAF node MAY
    omit a file list only when it owns no work of its own; if it declares code (its own
    acceptance criteria / declared test cases), the file list is mandatory --- a writer
    that does not declare what it writes is invalid (ticket 19 round 1 gap 4). The declared
    verification requirement, the review ANGLES (against the node's closed per-level set),
    and the best-effort declaration (a plan-level reason is mandatory) are validated here
    so an out-of-domain or unjustified declaration invalidates the node at construction.
    """
    if kind == "leaf" and not files:
        add(leaf_kind,
            f"{label} is a leaf with an empty file list (a leaf must write code)")
    if kind != "leaf" and has_code and not files:
        add("non-leaf-code-without-files",
            f"{label} declares its own work but no file list (a writer must declare its "
            "files)")
    if required not in VERIFICATION_REQUIREMENTS:
        add("bad-verification-required",
            f"{label} verification_required={required!r} not in {VERIFICATION_REQUIREMENTS}")
    domain = review_angles_for_level(level)
    for angle in review_angles:
        if angle not in domain:
            add("bad-review-angle",
                f"{label} review_angle={angle!r} not in the {level} set {domain}")
    if best_effort and not (best_effort_reason or "").strip():
        add("best-effort-without-reason",
            f"{label} declares best_effort without a plan-level best_effort_reason")


def validate_decomposition(
    d: Decomposition,
    *,
    parent_files: set[str],
    candidate_files: set[str],
    depth: int,
    depth_cap: int,
    max_children: int,
) -> ValidationFindings:
    """The deterministic plan gate — structured findings, never an exception.

    Steps (design §1, relaxed by ticket 19 F): canonicalize; child ⊆ parent; leaf ⇒ no
    children + non-empty ACs; internal ⇒ children; ``est_calls >= 1``; normalized-``what``
    dedupe; depth and child-count caps; free-text file-token grounding. Sibling file sets
    may OVERLAP (the tree serializes overlapping writers); A non-empty result routes the
    caller to re-ask once, then force a leaf.
    """
    findings: list[Finding] = []

    def add(kind: str, detail: str) -> None:
        findings.append(Finding(kind=kind, detail=detail))

    node = d.spec
    parent_canon = {p for p in (canonical_path(f) for f in parent_files) if p is not None}

    if depth > depth_cap:
        add("depth-cap", f"depth {depth} exceeds depth_cap {depth_cap}")
    if len(d.children) > max_children:
        add("child-count", f"{len(d.children)} children exceeds max_children {max_children}")

    _canon_set(node.files, add, "node")
    _verification_findings("node", node.files, node.verification_required,
                           node.review_angles, node.review_level, node.best_effort,
                           node.best_effort_reason, node.kind,
                           bool(node.acs or node.test_cases), add)

    if node.kind == "leaf":
        if d.children:
            add("leaf-with-children", "a leaf node may not declare children")
        if not node.acs:
            add("leaf-empty-acs", "a leaf node requires a non-empty AC map")
    elif not d.children:
        add("internal-without-children", "an internal node must declare at least one child")

    if node.est_calls < 1:
        add("bad-est-calls", f"node est_calls={node.est_calls} must be >= 1")

    for i, child in enumerate(d.children):
        cset = _canon_set(child.files, add, f"child {i}")
        _verification_findings(f"child {i}", child.files, child.verification_required,
                               child.review_angles, child.review_level, child.best_effort,
                               child.best_effort_reason, child.kind,
                               bool(child.acs or child.test_cases), add,
                               leaf_kind="leaf-child-empty-files")
        outside = sorted(cset - parent_canon)
        if outside:
            add("child-outside-boundary",
                f"child {i} files outside the parent boundary: {outside}")
        if child.kind == "leaf" and not child.acs:
            add("leaf-child-empty-acs", f"child {i} is a leaf with an empty AC map")
        if child.est_calls < 1:
            add("bad-est-calls", f"child {i} est_calls={child.est_calls} must be >= 1")
        for tok in _grounded_tokens(child.goal, child.why):
            if tok not in candidate_files and tok not in parent_canon:
                add("ungrounded-reference",
                    f"child {i} names {tok!r} not in the injected candidate scope")

    # Ticket 20 item 5: a plan may not weaken the covenant on every child. If more than
    # the predefined small share of children declares best_effort, the decomposition is
    # rejected at construction (re-ask once, then force a leaf) instead of silently
    # converting the declared floor into an audit log.
    if d.children:
        declared = sum(1 for child in d.children if child.best_effort)
        share = declared / len(d.children)
        if share > COVENANT_DILUTION_SHARE:
            add("best-effort-dilution",
                f"{declared}/{len(d.children)} children declare best_effort "
                f"({share:.0%} > {COVENANT_DILUTION_SHARE:.0%}); the covenant floor must "
                "not be weakened on every child")

    # Ticket 19 F: overlapping declared file sets between siblings are ALLOWED — two
    # requirements may legitimately change the same file. The tree SERIALIZES overlapping
    # writers (:func:`harness.tree.ready_leaves` overlap grouping; ``run_tree`` runs
    # children sequentially) and keeps the per-node write-boundary audit, so a shared file
    # never has two simultaneous writers and no node can change a path it did not declare.

    seen: dict[str, int] = {}
    for i, child in enumerate(d.children):
        key = _normalized_what(child.goal)
        if key in seen:
            add("duplicate-child", f"children {seen[key]} and {i} share the goal {child.goal!r}")
        else:
            seen[key] = i

    return ValidationFindings(items=findings)


# ---------------------------------------------------------------------------
# Budget gate
# ---------------------------------------------------------------------------


def can_decompose(budget: Budget, n_children: int = 2, *,
                  min_leaf_calls: int = MIN_LEAF_CALLS) -> bool:
    """DESIGN §10.2: a node whose non-reserve pool cannot fund ``n_children`` leaves of
    ``min_leaf_calls`` each must not even call the decomposer — it runs as a leaf."""
    if n_children < 1:
        return False
    spendable = int(budget.calls * (1.0 - budget.reserve_fraction))
    return spendable // n_children >= min_leaf_calls


def split_weighted(budget: Budget, weights: Sequence[int], *,
                   min_leaf_calls: int = MIN_LEAF_CALLS) -> list[Budget]:
    """``Budget.split_weighted`` — weighted split with the merge rule.

    Delegates to :meth:`Budget.split_weighted`; exposed here so the plan module owns one
    spelling of the budget gate. Raises :class:`BudgetError` when the split must be
    refused (force a leaf) — the caller converts that to a leaf, never a crash.
    """
    return budget.split_weighted(list(weights), min_each=min_leaf_calls)


# ---------------------------------------------------------------------------
# Repeat refusal
# ---------------------------------------------------------------------------


@dataclass
class SplitAttempt:
    """Append-only record of one accepted-or-refused decomposition."""

    signature: str
    n_children: int
    max_child_budget: int
    verdict: Literal["novel", "wasted"]


@dataclass
class SplitHistory:
    """Per-node split history enforcing the "shrink or differ" rule (design §5; mirrors
    :func:`harness.attempts.prefilter`).

    A signature never seen before is ``novel``. A REPEATED signature is accepted only if
    it SHRINKS the unit — a smaller max child budget, or more children (each therefore
    smaller). Otherwise it is recorded ``wasted`` and refused, so the T-31 "nine identical
    retries" defect cannot recur at the tree layer.
    """

    attempts: list[SplitAttempt] = field(default_factory=list)

    def accept(self, signature: str, *, n_children: int, max_child_budget: int) -> bool:
        for prior in self.attempts:
            if prior.signature != signature:
                continue
            shrinks = (max_child_budget < prior.max_child_budget
                       or n_children > prior.n_children)
            self.attempts.append(SplitAttempt(
                signature=signature, n_children=n_children,
                max_child_budget=max_child_budget,
                verdict="novel" if shrinks else "wasted"))
            return shrinks
        self.attempts.append(SplitAttempt(
            signature=signature, n_children=n_children,
            max_child_budget=max_child_budget, verdict="novel"))
        return True

    @property
    def wasted(self) -> int:
        return sum(1 for a in self.attempts if a.verdict == "wasted")


# ---------------------------------------------------------------------------
# The ONE call
# ---------------------------------------------------------------------------


def _plan_node_artifacts(goal: str, boundary: set[str], candidate_files: set[str],
                         depth: int) -> dict[str, str]:
    return {
        "node_goal": goal,
        "write_boundary": "\n".join(sorted(boundary)) or "(none: this node owns no files)",
        "candidate_files": "\n".join(sorted(candidate_files)),
        "depth": str(depth),
    }


def _plan_node_question(evidence: str, depth: int) -> str:
    lines = [
        ("Decompose and specify THIS node in one call. Return the node's own goal, "
         "behavior, implementation_notes, files, acs, interfaces and test_cases, plus "
         "its children. Return children=[] to declare this node a LEAF (then its acs "
         "MUST be non-empty)."),
        f"DEPTH: {depth} (a child must be at depth {depth + 1}).",
        ("Split by REQUIREMENT / acceptance criterion, NOT by file: give each child "
         "one requirement (or one coherent requirement group). Two children MAY declare "
         "the same file — the harness serializes overlapping writers — but a child must "
         "not declare a path outside this node's write boundary, and every node must "
         "stay within its own declared boundary."),
        ("For each acceptance criterion DECLARE its expected test cases in test_cases: "
         "the ac_id, the test FILE, and the test FUNCTION NAMES that must exist and "
         "pass. The harness verifies these mechanically from the report, so name them "
         "concretely (e.g. ac_id AC-1, file tests/test_x.py, names [test_ac1_goal])."),
        ("DECLARE the verification each node must carry: verification_required is "
         "'test' when a discriminating test MUST carry the claim, 'review' when an "
         "independent review is enough, or 'any' for either. review_angles lists the "
         "review ANGLES to run, from the closed implementation set "
         "['ac-correctness', 'contract-compat', 'edge-and-error', 'regression-risk', "
         "'input-safety', 'maintainability'] --- each angle is one independent review "
         "call, and a repeated angle is a recorded deviation, not extra evidence; leave "
         "it empty to run the critical angles. best_effort=true is an EXPLICIT PLAN-LEVEL "
         "opt-in to a weaker tier, needs a best_effort_reason explaining why, lowers the "
         "floor at most ONE tier, and MUST NOT be declared on every child."),
    ]
    if evidence:
        lines.append("PRIOR ATTEMPT WAS REJECTED — use this as evidence and differ:\n"
                     + evidence)
    return "\n".join(lines)


async def plan_node(
    model: Any,
    *,
    goal: str,
    evidence: str = "",
    boundary: set[str],
    candidate_files: set[str],
    depth: int,
    depth_cap: int = 4,
    max_children: int = 15,
    budget: Budget | None = None,
    on_event: Any = None,
) -> Decomposition | None:
    """ONE ``llm_step("plan_node")`` for one node — with a bounded one-shot re-ask.

    Returns the validated :class:`Decomposition`, or ``None`` to force the node to a
    leaf (an ``unable`` envelope, malformed output, or findings that survive the one
    re-ask). Each call spends one call from ``budget`` when one is injected. Never
    raises out: invalid output becomes a force-leaf.
    """
    boundary = set(boundary)
    candidate_files = set(candidate_files)
    artifacts = _plan_node_artifacts(goal, boundary, candidate_files, depth)
    feedback = evidence
    for attempt in range(2):
        if budget is not None:
            if budget.calls < 1:
                return None
            budget.take(1)
        question = _plan_node_question(feedback, depth)
        try:
            env = await llm_step(model, "plan_node", artifacts=artifacts, question=question)
        except Exception as exc:  # noqa: BLE001 — a model failure is data, not a crash
            if on_event is not None:
                on_event("plan_node_malformed",
                         {"attempt": attempt + 1, "detail": f"{type(exc).__name__}: {exc}"})
            return None
        if getattr(env, "status", "unable") == "unable":
            feedback = f"the decomposer returned unable: {env.unable_reason}"
            continue
        decomp = decomposition_from_envelope(env)
        findings = validate_decomposition(
            decomp, parent_files=boundary, candidate_files=candidate_files,
            depth=depth, depth_cap=depth_cap, max_children=max_children)
        if findings.ok:
            return decomp
        feedback = "plan_node findings: " + "; ".join(
            f"{f.kind}: {f.detail}" for f in findings.items)
    return None
