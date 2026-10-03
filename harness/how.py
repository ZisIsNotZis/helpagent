"""The How axis, the selection function, immutability, and the failure→manager loop.

Ticket 20 step 2a (owner direction 2026-09-30, the scaling discussion). This module owns
the pieces the tree runner builds on:

- :class:`How` / :class:`HowList` — a node owns an APPEND-ONLY list of ranked approaches
  (``{id, text, rank, reason, prior, status}``). The first planning step produces N Hows;
  each How the budget lets the node explore gets its own per-How decomposition (a
  :class:`harness.envelopes.PlanNode` bound to that ``how_id``). Hows and decompositions
  are IMMUTABLE: a failure never edits a How or its decomposition, it appends a NEW How
  and marks the old one ``failed``/``abandoned``. Therefore no destructive rollback: each
  candidate works in its OWN isolated directory copied under the run's output area (a
  copy, never a git worktree, and never a ``git reset``/``git clean``).
- :func:`prior_for_rank` / :func:`how_viability` — the PRIOR is a SCHEDULER HINT only,
  never evidence. The default table is geometric decay by rank; a How's viability is its
  own prior times the best VIABLE child value, with failed/abandoned children removed.
  Success is decided ONLY by hard evidence (tests / integration verification).
- :class:`TestPoint` / :func:`planned_test_points` / :func:`point_results` — the
  PLAN-TIME TEST LIST is the CONTRACT. The planning step declares each point by NAME,
  FILE, WHAT it verifies, and the acceptance criterion it serves; the candidate is scored
  over the DECLARED points (never over tests it invented). :func:`extra_test_points`
  names the two-way DEVIATION: extra tests beyond the plan do not score, but are reported
  to the node's manager.
- :func:`select_key` — the lexicographic, deterministic selection key
  ``(test score, review score, rank, cost)`` for ONE candidate. Test score = (planned test
  points covered, pass rate over the PLANNED points); no tests ⇒ 0. Review score = the
  predefined weighted angle aggregate with the critical-angle veto; no review ⇒ 0. A
  NEGATIVE review grade is an ACTION ITEM (the node keeps working), never just a lost
  comparison. :func:`pick` is the ONE picker across candidates: maximise (covered, pass
  rate) and review score, then MINIMISE rank, then MINIMISE cost.
- :func:`decide_after_failure` — the manager loop. On a failed/exhausted How the node's
  STRUCTURED RECORD (How list with statuses, each failure's evidence and reason, which
  Hows remain untried) goes to the node's managing call, which returns ONE decision plus a
  reason out of exactly four: ``continue-with-next-how`` / ``author-a-new-how`` /
  ``request-feasibility-review`` / ``escalate-or-park``. Automatic advance is allowed ONLY
  when a feasibility review judged the How infeasible; otherwise the manager decides.
- :class:`NodeRecord` — the model-maintained text record that is REWRITTEN (not appended)
  and whose every update carries a reason. It is separate from the ledger and is NEVER
  evidence.

Scope discipline: the leaf's claim rules, the review angles, and the covenant are
untouched here. The plan-time test list and its two-way deviation reporting are wired in
step 2b-ii (:class:`TestPoint` and the ``deviations`` on the structured record).

WIRED (step 2b): :mod:`harness.tree_run` now plans How-first — ``run_node`` calls
``how_list``, opens one candidate copy per affordable How, binds each decomposition to
its ``how_id``, and chooses the winner with :func:`pick`. The old
``trajectory.reset_to`` (``git reset --hard`` / ``git clean``) path is GONE from the
runner and from :class:`harness.trajectory.Trajectory`; a failed/exhausted approach
appends a new How through the :func:`decide_after_failure` manager loop. The candidate
copies are the only rollback mechanism now.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

from harness.leaf import (
    DEFAULT_REVIEW_LEVEL,
    ReviewVerdict,
    _declared_case_index,
    combine_review_verdicts,
    effective_review_angles,
    reject_node_record_fields,
)
from harness.node import MIN_LEAF_CALLS, NodeSpec

__all__ = [
    "HOW_STATUSES",
    "MANAGER_DECISIONS",
    "PRIOR_DECAY",
    "SELECTION_ORDER",
    "CandidateSet",
    "CandidateWorkspace",
    "How",
    "HowFailure",
    "HowList",
    "HowStatus",
    "ManagerDecision",
    "ManagerDecisionValue",
    "ManagerUnavailable",
    "NodeRecord",
    "NodeRecordView",
    "Selection",
    "TestPoint",
    "abandon_candidate",
    "audit_candidate_boundary",
    "candidate_dir",
    "create_candidate",
    "decide_after_failure",
    "extra_test_points",
    "how_exploration_limit",
    "how_viability",
    "make_how",
    "pick",
    "planned_test_points",
    "planned_test_score",
    "point_results",
    "prior_for_rank",
    "select_key",
    "snapshot_candidate",
]

HowStatus = Literal["untried", "active", "succeeded", "failed", "abandoned"]
HOW_STATUSES: tuple[str, ...] = ("untried", "active", "succeeded", "failed", "abandoned")

ManagerDecisionValue = Literal[
    "continue-with-next-how",
    "author-a-new-how",
    "request-feasibility-review",
    "escalate-or-park",
]
MANAGER_DECISIONS: tuple[str, ...] = (
    "continue-with-next-how",
    "author-a-new-how",
    "request-feasibility-review",
    "escalate-or-park",
)

#: The DEFAULT framework prior table: geometric decay by rank (rank 1 ⇒ 0.5). It is a
#: SCHEDULER HINT — it decides who runs first, never whether a run counts as a success.
PRIOR_DECAY = 0.5


def prior_for_rank(rank: int) -> float:
    """The default framework prior for a rank (geometric decay: 0.5, 0.25, 0.125, …)."""
    if rank < 1:
        raise ValueError("How rank must be >= 1")
    return PRIOR_DECAY ** rank


@dataclass(frozen=True)
class How:
    """One approach for a node: ``{id, text, rank, reason, prior, status}``.

    ``text`` is a short paragraph of how this would be done, ``reason`` why it is worth a
    look, ``rank`` the model's priority order. ``prior`` is NOT a settable field: it is
    DERIVED from ``rank`` by :func:`prior_for_rank`, so neither the model nor a caller can
    inflate the scheduler hint. The CONTENT (id/text/rank/reason/prior) is immutable; only
    ``status`` is a lifecycle marker, and a transition produces a NEW frozen How — the
    original object is never edited.
    """

    id: str
    text: str
    rank: int
    reason: str
    prior: float | None = None  # derived from rank in __post_init__; never settable
    status: HowStatus = "untried"

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("How rank must be >= 1")
        if not self.text.strip():
            raise ValueError("How text must be non-empty")
        if not self.reason.strip():
            raise ValueError("How reason must be non-empty")
        if self.status not in HOW_STATUSES:
            raise ValueError(f"How status {self.status!r} not in {HOW_STATUSES}")
        expected = prior_for_rank(self.rank)
        if self.prior is not None and self.prior != expected:
            raise ValueError(
                f"How prior comes from the rank table only: rank {self.rank} implies "
                f"{expected}, got {self.prior} (a prior is a scheduler hint, never "
                "evidence)")
        object.__setattr__(self, "prior", expected)

    def with_status(self, status: HowStatus) -> "How":
        """A NEW frozen How with only ``status`` changed (content is never edited)."""
        return replace(self, status=status)


def make_how(id: str, text: str, rank: int, reason: str) -> How:
    """Build a How; the prior always comes from the rank table (:func:`prior_for_rank`).

    There is deliberately NO ``prior`` argument: the prior is a scheduling hint that must
    never be settable (by the model or by a caller), so a high rank can never be inflated
    into out-ranking a better one.
    """
    return How(id=id, text=text, rank=rank, reason=reason)


@dataclass(frozen=True)
class HowList:
    """APPEND-ONLY list of Hows for one node (frozen; every transition returns a new one).

    ``append`` adds a NEW How (and, when given, marks the prior How failed/abandoned in
    the same new list) so "a failure appends a new How and marks the old one" can never
    edit the old How's content or its decomposition.
    """

    hows: tuple[How, ...] = ()

    def __iter__(self):
        return iter(self.hows)

    def __len__(self) -> int:
        return len(self.hows)

    def get(self, how_id: str) -> How | None:
        for how in self.hows:
            if how.id == how_id:
                return how
        return None

    def untried(self) -> tuple[How, ...]:
        """The Hows still untried, in rank order (the candidate pool to draw from)."""
        return tuple(sorted((h for h in self.hows if h.status == "untried"),
                            key=lambda h: (h.rank, h.id)))

    def active(self) -> How | None:
        for how in self.hows:
            if how.status == "active":
                return how
        return None

    def with_status(self, how_id: str, status: HowStatus) -> "HowList":
        """A NEW list with one How's status transitioned; the receiver is unchanged."""
        found = self.get(how_id)
        if found is None:
            raise KeyError(f"unknown how_id {how_id!r}")
        return HowList(tuple(h.with_status(status) if h.id == how_id else h
                             for h in self.hows))

    def append(self, how: How, *, mark: tuple[str, HowStatus] | None = None) -> "HowList":
        """Append ``how`` and (optionally) transition ``mark`` — all in a new list.

        Refuses a duplicate id so the list stays a clean identity map.
        """
        if self.get(how.id) is not None:
            raise ValueError(f"duplicate how_id {how.id!r} (Hows are append-only)")
        if mark is not None:
            base = self.with_status(*mark)
        else:
            base = self
        return HowList(base.hows + (how,))


def how_list_from_envelope(env) -> HowList:
    """Translate a validated :class:`harness.envelopes.HowList` into a :class:`HowList`.

    The LIST ORDER is the priority: the harness assigns ``HOW-<i>`` and rank ``i`` (the
    prior follows from the deterministic table). The model never supplies an id or a
    rank.
    """
    return HowList(tuple(
        make_how(f"HOW-{i}", entry.text, i, entry.reason)
        for i, entry in enumerate(env.hows, start=1)))


# ---------------------------------------------------------------------------
# The prior as a scheduler hint (never evidence)
# ---------------------------------------------------------------------------


def how_viability(prior: float, children: Sequence[tuple[str, float]], *,
                  status: HowStatus = "untried") -> float:
    """``own prior × best viable child value``; failed/abandoned nodes are not viable.

    ``status`` is the node's OWN lifecycle marker: a failed or abandoned How is not
    viable (0.0) regardless of its children. ``children`` is ``(status, value)`` per
    child How. Every status is validated against the closed :data:`HOW_STATUSES`, so an
    UNRECOGNISED or misspelled status (e.g. ``"fail"``) is rejected loudly instead of
    silently counting as viable. A How with no children is a leaf and its viability is
    its own prior; a How whose children are ALL failed/abandoned is 0.0. This value only
    ORDERS exploration; it never decides success.
    """
    if status not in HOW_STATUSES:
        raise ValueError(f"How status {status!r} not in {HOW_STATUSES}")
    if status in ("failed", "abandoned"):
        return 0.0
    for child_status, _ in children:
        if child_status not in HOW_STATUSES:
            raise ValueError(
                f"child How status {child_status!r} not in {HOW_STATUSES}")
    viable = [value for child_status, value in children
              if child_status not in ("failed", "abandoned")]
    if not children:
        return prior
    if not viable:
        return 0.0
    return prior * max(viable)


# ---------------------------------------------------------------------------
# The plan-time test list (the contract a candidate is scored against)
# ---------------------------------------------------------------------------


def _normalize_test_node_id(node_id: str) -> str:
    """``file::Class::test`` ⇒ ``file::test`` (the declared point's spelling).

    pytest node ids for a method carry the class in the middle; a declared point names
    only the FILE and the function, so the middle segments are dropped before matching.
    """
    file, _, rest = node_id.partition("::")
    if not rest:
        return node_id
    return f"{file}::{rest.split('::')[-1]}"


@dataclass(frozen=True)
class TestPoint:
    """One PLAN-TIME test point: the declared contract a candidate is scored against.

    ``name`` is the declared test FUNCTION, ``file`` the file it lives in, ``verifies``
    WHAT it checks (the acceptance-criterion statement it serves), and ``ac_id`` which
    acceptance criterion it serves. ``id`` is the ``file::name`` node id the machine-
    readable report uses, so a point can be matched against a candidate's own-test gate.
    """

    #: Not a pytest test class (the ``Test`` prefix is conceptual, not a collectable test).
    __test__ = False

    name: str
    file: str
    verifies: str
    ac_id: str

    @property
    def id(self) -> str:
        return f"{self.file}::{self.name}"

    def to_dict(self) -> dict:
        return {"name": self.name, "file": self.file,
                "verifies": self.verifies, "ac_id": self.ac_id, "id": self.id}


def planned_test_points(spec: NodeSpec) -> tuple[TestPoint, ...]:
    """The node plan's DECLARED test points (its scoring contract), in declared order.

    One point per declared test FUNCTION name. ``verifies`` is the statement of the
    acceptance criterion the case serves (looked up by the case's ``AC-<n>`` index in
    the spec's OWN ``acs``), or the ``ac_id`` itself when the criterion is not
    resolvable. Empty when the plan declared no test cases — then the test component is
    ``(0, 0.0)`` exactly as before the plan was wired in.
    """
    statements = {i: statement for i, statement in enumerate(spec.acs, 1)}
    points: list[TestPoint] = []
    seen: set[str] = set()
    for case in spec.planned_tests:
        index = _declared_case_index(case)
        verifies = statements.get(index, case.ac_id) if index is not None else case.ac_id
        for name in case.names:
            point = TestPoint(name=name, file=case.file, verifies=verifies, ac_id=case.ac_id)
            if point.id in seen:
                continue
            seen.add(point.id)
            points.append(point)
    return tuple(points)


def point_results(points: Sequence[TestPoint], leaves: Sequence[Any]) -> dict[str, bool]:
    """Per declared point, PASS/FAIL from the candidate's own-test gate reports.

    The result is keyed by the point id and holds a key ONLY for a point a report
    OBSERVED: an unobserved declared point is absent, so it counts as UNCOVERED
    (:func:`planned_test_score` never credits a point the candidate did not run). A
    missing declared point is a separate claim blocker, so a claimed candidate covers
    its whole declared list, but a candidate that closed on another basis (e.g. a
    reviewer) legitimately covers fewer points and is scored lower for it.
    """
    passed: set[str] = set()
    failed: set[str] = set()
    for leaf in leaves:
        gate = getattr(leaf, "own_test_gate", None)
        if gate is None:
            continue
        passed.update(_normalize_test_node_id(nid) for nid in gate.passed_ids)
        failed.update(_normalize_test_node_id(nid) for nid in gate.failed_ids)
    return {point.id: True for point in points if point.id in passed} | {
        point.id: False for point in points if point.id in failed}


def extra_test_points(points: Sequence[TestPoint],
                      leaves: Sequence[Any]) -> tuple[str, ...]:
    """The EXTRA tests a candidate collected in a DECLARED file but the plan did not declare.

    These do NOT score (:func:`planned_test_score` has the plan as its denominator); they
    are a two-way DEVIATION reported to the node's manager, which decides whether the
    plan under-specified or the implementation is padding. Only tests in a file the plan
    already declares count: a test in some unrelated file is not part of this node's
    contract at all.
    """
    declared = {point.id for point in points}
    declared_files = {point.file for point in points}
    collected: set[str] = set()
    for leaf in leaves:
        gate = getattr(leaf, "own_test_gate", None)
        if gate is None:
            continue
        collected.update(_normalize_test_node_id(nid) for nid in gate.passed_ids)
        collected.update(_normalize_test_node_id(nid) for nid in gate.failed_ids)
    return tuple(sorted(nid for nid in collected
                        if nid not in declared and nid.partition("::")[0] in declared_files))


# ---------------------------------------------------------------------------
# The selection function (lexicographic, deterministic)
# ---------------------------------------------------------------------------


def planned_test_score(planned: Sequence[str],
                       results: Mapping[str, bool] | None) -> tuple[int, float]:
    """``(points covered, pass rate over the PLANNED points)``; no plan/tests ⇒ (0, 0.0).

    The DENOMINATOR is the plan list, not the candidate's own tests: covering fewer
    planned points is strictly worse, and the pass rate is ``passed / len(planned)``.
    """
    planned = tuple(planned)
    if not planned:
        return (0, 0.0)
    results = results or {}
    covered = sum(1 for point in planned if point in results)
    passed = sum(1 for point in planned if results.get(point) is True)
    return (covered, passed / len(planned))


#: The ONE lexicographic selection ORDER, best-first. ``test_covered`` and
#: ``test_pass_rate`` are MAXIMISED, then ``review_score`` is MAXIMISED, then ``rank``
#: and ``cost`` are MINIMISED. :attr:`Selection.order` is the single tuple encoding it, so
#: the order cannot drift; :func:`pick` is the only picker.
SELECTION_ORDER: tuple[str, ...] = (
    "test_covered", "test_pass_rate", "review_score", "rank", "cost")


@dataclass(frozen=True)
class Selection:
    """The per-candidate key plus the review-action verdict for ONE candidate.

    ``key`` records the raw components for the audit record, in the documented order:
    ``((test_covered, test_pass_rate), review_score, rank, cost)``. ``order`` is the ONE
    comparator tuple :func:`pick` maximises (rank and cost negated). ``repair_reason`` is
    non-empty when a NEGATIVE (or vetoing critical) review grade makes this an ACTION
    ITEM — the node keeps working rather than treating it as a lost comparison.
    """

    test_covered: int
    test_pass_rate: float
    review_score: int
    rank: int
    cost: int
    review_ok: bool
    repair_reason: str = ""

    def __post_init__(self) -> None:
        reject_node_record_fields(self)
        # A NaN or a non-integer rank/cost would make the comparison input-order
        # dependent (NaN compares false against everything) - reject loudly instead.
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError(f"rank must be a positive int, got {self.rank!r}")
        if not isinstance(self.cost, int) or isinstance(self.cost, bool) or self.cost < 0:
            raise ValueError(f"cost must be a non-negative int, got {self.cost!r}")
        if not isinstance(self.test_covered, int) or isinstance(self.test_covered, bool) \
                or self.test_covered < 0:
            raise ValueError(f"test_covered must be a non-negative int, got {self.test_covered!r}")
        for name in ("test_pass_rate", "review_score"):
            value = getattr(self, name)
            if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                raise ValueError(f"{name} must be finite, got {value!r}")

    @property
    def key(self) -> tuple:
        """The ONE comparable tuple, in best-first order.

        Rank and cost are stored NEGATED so that ``max(key=Selection.key)`` IS the
        documented order (maximise test coverage/rate, then review score, then
        minimise rank, then minimise cost). An unsigned tuple was a trap: the audit
        ``key`` and the picker disagreed on rank/cost ties even though both claimed to
        encode the same order. There is now exactly one tuple to compare.
        """
        return ((self.test_covered, self.test_pass_rate), self.review_score,
                -self.rank, -self.cost)

    @property
    def order(self) -> tuple:
        """The ONE comparator tuple: tests/review MAXIMISED, rank/cost MINIMISED.

        Derived from :attr:`key` so the two cannot drift; ``max(candidates,
        key=Selection.order)`` is exactly the documented order and the one comparator
        :func:`pick` uses.
        """
        return self.key

    @property
    def needs_repair(self) -> bool:
        return bool(self.repair_reason)


def select_key(*, planned_test_points: Sequence[str],
               test_results: Mapping[str, bool] | None,
               review_verdicts: Sequence[ReviewVerdict] = (),
               planned_reviews: Sequence[str] = (),
               review_level: str = DEFAULT_REVIEW_LEVEL,
               rank: int,
               cost: int) -> Selection:
    """The ONE pure selection function (lexicographic, deterministic).

    ``(test score, review score, rank, cost)`` where test score is
    :func:`planned_test_score` and review score is the predefined weighted angle aggregate
    (:func:`harness.leaf.combine_review_verdicts`) with the critical-angle veto. No review
    ⇒ 0. Ties fall through to the smaller rank, then to the smaller cost. A negative
    review grade (or a veto) is recorded as ``repair_reason`` (an action item).
    """
    covered, rate = planned_test_score(planned_test_points, test_results)
    if not review_verdicts:
        return Selection(test_covered=covered, test_pass_rate=rate, review_score=0,
                         rank=rank, cost=cost, review_ok=True, repair_reason="")
    angles = effective_review_angles(planned_reviews, review_level)
    ok, score, reason = combine_review_verdicts(review_verdicts, angles, review_level)
    # A non-ok review (a negative grade or a critical-angle veto) is an ACTION ITEM:
    # its review component drops to 0 so it can never outrank a clean candidate before
    # the repair, while ``repair_reason`` carries the detail back to the node.
    return Selection(test_covered=covered, test_pass_rate=rate,
                     review_score=score if ok else 0,
                     rank=rank, cost=cost, review_ok=ok,
                     repair_reason="" if ok else reason)


def pick(candidates: Sequence[Selection]) -> Selection | None:
    """The ONE deterministic picker: the best candidate under the documented order.

    Order (best-first): maximise (``test_covered``, ``test_pass_rate``), then maximise
    ``review_score``, then MINIMISE ``rank``, then MINIMISE ``cost``. An empty pool
    returns ``None``; a full tie keeps the first candidate, so the pick is deterministic.
    """
    pool = list(candidates)
    if not pool:
        return None
    return max(pool, key=lambda candidate: candidate.order)


# ---------------------------------------------------------------------------
# The failure → manager loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HowFailure:
    """One failure's structured evidence and reason (never the model's chat memory)."""

    how_id: str
    evidence: str
    reason: str


@dataclass(frozen=True)
class NodeRecordView:
    """The STRUCTURED RECORD handed to the manager: audit is data, not context.

    Carries the How list with statuses, each failure's evidence and reason, which Hows
    remain untried, and which How the node was working on. It is what the managing call
    sees INSTEAD of the node's conversational memory.
    """

    node_id: str
    hows: tuple[How, ...]
    failures: tuple[HowFailure, ...] = ()
    untried: tuple[str, ...] = ()
    current_how_id: str = ""
    #: Ticket 20 step 2b-ii: the two-way test deviation — extra tests a candidate
    #: collected beyond the plan's declared points. They never score; the manager
    #: decides whether the plan under-specified or the implementation is padding.
    deviations: tuple[str, ...] = ()
    #: Ticket 20 step 2b-ii: each candidate How's selection key ``(how_id, Selection)``,
    #: so the manager sees what the closed candidates scored on before it decides.
    selections: tuple[tuple[str, Selection], ...] = ()

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(h.id for h in self.hows if h.status == "failed")

    @property
    def abandoned(self) -> tuple[str, ...]:
        return tuple(h.id for h in self.hows if h.status == "abandoned")


@dataclass(frozen=True)
class ManagerDecision:
    """ONE decision plus a reason, out of exactly the four :data:`MANAGER_DECISIONS`."""

    decision: ManagerDecisionValue
    reason: str

    def __post_init__(self) -> None:
        if self.decision not in MANAGER_DECISIONS:
            raise ValueError(
                f"manager decision {self.decision!r} not in {MANAGER_DECISIONS}")
        if not self.reason.strip():
            raise ValueError("a manager decision must carry a reason")


class ManagerUnavailable(RuntimeError):
    """The managing call returned NO usable decision (ticket 20 step 2b-iii).

    A model reply whose envelope status is ``blocked``/``unable`` (or an otherwise
    unusable payload) is NOT one of the four decisions: the manager did not decide. The
    runner records it as ``manager_unavailable`` and parks, so a non-decision can never
    read as a decision in the run record.
    """


#: The managing call the node hands its structured record to.
ManagerCall = Callable[[NodeRecordView], ManagerDecision]


def decide_after_failure(record: NodeRecordView, *,
                         feasibility: Literal["infeasible", "feasible", "unknown"] = "unknown",
                         manager: ManagerCall | None = None) -> ManagerDecision:
    """The manager loop decision after a How failed or exhausted.

    AUTOMATIC advance (``continue-with-next-how``) is allowed ONLY when a feasibility
    review (a plan-level angle) judged the How INFEASIBLE. In every other case the node's
    managing call decides, so the manager — not the framework — owns the move. With no
    manager injected the safe default is ``escalate-or-park`` (never an implicit advance).
    """
    if feasibility == "infeasible":
        nxt = record.untried[0] if record.untried else None
        if nxt is not None:
            return ManagerDecision(
                "continue-with-next-how",
                f"feasibility review judged {record.current_how_id or 'the How'} "
                f"infeasible; advancing to {nxt}")
    if manager is None:
        return ManagerDecision(
            "escalate-or-park",
            "no manager injected and no automatic advance applies "
            "(only an infeasible feasibility review advances automatically)")
    decision = manager(record)
    if decision.decision not in MANAGER_DECISIONS:
        raise ValueError(f"manager returned {decision.decision!r}, not one of "
                         f"{MANAGER_DECISIONS}")
    return decision


# ---------------------------------------------------------------------------
# The node record area (model-maintained, rewritten, never evidence)
# ---------------------------------------------------------------------------


@dataclass
class NodeRecord:
    """A node's model-maintained text record: REWRITTEN, not appended.

    Every update must carry a reason; the previous ``(text, reason)`` is returned so the
    caller can write it to the harness LEDGER (harness-written, append-only, never in
    model context). This record is NEVER evidence — it is a scratchpad the model keeps.
    """

    node_id: str
    text: str = ""
    last_reason: str = ""

    #: Explicit, load-bearing: a node record is a scratchpad, never tournament evidence.
    IS_EVIDENCE = False

    #: The STRUCTURAL marker the leaf's input guard keys on: no verification/claim input
    #: may carry a node record (``harness.leaf.reject_node_record_fields``).
    __helpagent_node_record__ = True

    def rewrite(self, text: str, reason: str) -> tuple[str, str]:
        """Rewrite the record, requiring a reason; return the previous (text, reason)."""
        if not reason.strip():
            raise ValueError("every node-record update must carry a reason")
        previous = (self.text, self.last_reason)
        self.text = text
        self.last_reason = reason
        return previous


# ---------------------------------------------------------------------------
# Candidate isolation (a copy, not a git worktree; no destructive reset)
# ---------------------------------------------------------------------------

_COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc")


@dataclass(frozen=True)
class CandidateWorkspace:
    """One How candidate's OWN isolated directory under the run's output area."""

    node_id: str
    how_id: str
    path: Path


def candidate_dir(run_outdir: str | Path, node_id: str, how_id: str) -> Path:
    """``<run_outdir>/candidates/<node_id>/<how_id>`` — the candidate's private tree."""
    return Path(run_outdir) / "candidates" / node_id / how_id


def create_candidate(run_outdir: str | Path, node_id: str, how_id: str,
                     source: str | Path) -> CandidateWorkspace:
    """Copy ``source`` into the candidate's own directory and return its workspace.

    A COPY, never a git worktree. The copy excludes ``.git`` and caches, so the harness's
    git state is untouched and a candidate can never move the main tree's branch.
    """
    dest = candidate_dir(run_outdir, node_id, how_id)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(source), dest, ignore=_COPY_IGNORE)
    return CandidateWorkspace(node_id=node_id, how_id=how_id, path=dest)


def abandon_candidate(workspace: CandidateWorkspace) -> None:
    """Discard a candidate's directory when its How is abandoned (no git involved)."""
    shutil.rmtree(workspace.path, ignore_errors=True)


def snapshot_candidate(workspace: CandidateWorkspace):
    """Snapshot the candidate directory for the per-candidate boundary audit."""
    from harness.tree_run import snapshot_workdir  # local import avoids an import cycle
    return snapshot_workdir(workspace.path)


def audit_candidate_boundary(workspace: CandidateWorkspace, before, boundary: Sequence[str]):
    """The existing boundary audit, now scoped to ONE candidate directory."""
    from harness.tree_run import audit_leaf_boundary  # local import avoids a cycle
    return audit_leaf_boundary(workspace.path, before, boundary)


def how_exploration_limit(budget, n_hows: int | None = None, *,
                          min_leaf_calls: int = MIN_LEAF_CALLS) -> int:
    """The CUMULATIVE number of Hows the budget lets the node EXPLORE (open a candidate).

    One call was already spent on the How list; each explored How then costs its per-How
    decomposition call plus a leaf's worth of work (``min_leaf_calls + 1``). The bound is
    the non-reserve pool divided by that: ``floor(spendable / (min_leaf_calls + 1))``. It
    is a node-level CUMULATIVE cap, so the caller computes it ONCE when exploration
    starts and never recounts it as Hows are appended or the budget is drawn down --- a
    manager that authors more Hows therefore cannot raise the cap.

    ``n_hows`` optionally caps the result by the number of Hows that already exist; pass
    ``None`` (what the runner does) to leave the bound purely budget-derived, because
    Hows authored LATER must not change the node's cap.

    Ticket 20 step 2c: this is the BUDGET-derived ceiling only. The runner additionally
    caps it by the run's ``how_explore`` setting (``1`` = greedy, the default), so with
    greedy a node opens the top-ranked How and nothing else.
    """
    spendable = int(budget.calls * (1.0 - budget.reserve_fraction))
    per_how = min_leaf_calls + 1
    cap = max(0, spendable // per_how)
    if n_hows is None:
        return cap
    if n_hows < 1:
        return 0
    return min(n_hows, cap)


@dataclass
class CandidateSet:
    """Tracks one node's Hows, their candidate directories, and every manager decision.

    The How list is append-only; opening a candidate copies the run's tree into the
    candidate's OWN directory; abandoning discards that directory and appends a NEW How.
    Every manager decision is recorded (``decisions``) for the run record.
    """

    node_id: str
    run_outdir: Path
    source: Path
    hows: HowList = field(default_factory=HowList)
    workspaces: dict[str, CandidateWorkspace] = field(default_factory=dict)
    failures: list[HowFailure] = field(default_factory=list)
    decisions: list[ManagerDecision] = field(default_factory=list)
    #: Ticket 20 step 2b-ii: every test deviation observed across the node's candidates
    #: (extra tests beyond the declared plan), surfaced to the managing call.
    deviations: list[str] = field(default_factory=list)
    #: Ticket 20 step 2b-ii: each closed candidate's selection key, keyed by its How id.
    selections: dict[str, Selection] = field(default_factory=dict)
    #: Ticket 20 step 2b-iii: managing calls that returned NO usable decision (a
    #: blocked/unable envelope). These are NOT decisions, so they are kept OUT of
    #: ``decisions`` and the node parks on them.
    manager_unavailable: list[dict] = field(default_factory=list)

    def add_how(self, how: How, *, mark: tuple[str, HowStatus] | None = None) -> How:
        """Append a How (optionally marking a prior one failed/abandoned)."""
        self.hows = self.hows.append(how, mark=mark)
        return how

    def open(self, how_id: str) -> CandidateWorkspace:
        """Create the candidate's isolated directory and mark its How ``active``."""
        ws = create_candidate(self.run_outdir, self.node_id, how_id, self.source)
        self.workspaces[how_id] = ws
        self.hows = self.hows.with_status(how_id, "active")
        return ws

    def succeed(self, how_id: str) -> None:
        self.hows = self.hows.with_status(how_id, "succeeded")

    def fail(self, how_id: str, *, evidence: str, reason: str) -> HowFailure:
        """Mark a How failed and record its structured evidence/reason."""
        self.hows = self.hows.with_status(how_id, "failed")
        failure = HowFailure(how_id=how_id, evidence=evidence, reason=reason)
        self.failures.append(failure)
        return failure

    def record_deviations(self, deviations: Sequence[str]) -> None:
        """Record test deviations (extra tests beyond the plan), de-duplicated in order."""
        if deviations:
            self.deviations = list(dict.fromkeys([*self.deviations, *deviations]))

    def record_selection(self, how_id: str, selection: Selection) -> None:
        """Record one candidate's selection key so the managing call can see it."""
        self.selections[how_id] = selection

    def abandon(self, how_id: str, *, reason: str) -> None:
        """Discard the candidate directory and mark the How ``abandoned``."""
        ws = self.workspaces.pop(how_id, None)
        if ws is not None:
            abandon_candidate(ws)
        self.hows = self.hows.with_status(how_id, "abandoned")
        self.failures.append(HowFailure(how_id=how_id, evidence="", reason=reason))

    def record(self, decision: ManagerDecision) -> ManagerDecision:
        """Record a manager decision (append-only, for the run record)."""
        self.decisions.append(decision)
        return decision

    def manager_view(self, *, current_how_id: str = "") -> NodeRecordView:
        """The structured record handed to the managing call."""
        return NodeRecordView(
            node_id=self.node_id, hows=self.hows.hows,
            failures=tuple(self.failures), untried=tuple(h.id for h in self.hows.untried()),
            current_how_id=current_how_id, deviations=tuple(self.deviations),
            selections=tuple((h.id, self.selections[h.id]) for h in self.hows.hows
                             if h.id in self.selections))
