"""Node budget (DESIGN §10.2, owner direction 2026-09-29).

The scarce resource for a local-model run is not money — it is the wall clock
until the human next looks at the run. So the PRIMARY budget is a deadline, and
model-call units are secondary accounting (they order the escalation ladder and
feed cost stats; they never by themselves stop a run that has until Monday).

Decomposition spends budget: a parent splits a share to its children and keeps a
reserve for integration, verification, and grants. A child's unused calls return
to the parent, so an efficient child does not starve its siblings.

Durable: ``to_dict``/``from_dict`` round-trip, because a run may be parked and
resumed after a human answers (DESIGN §10.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = ["Budget", "BudgetError", "GrantRecord", "group_weights"]

DEFAULT_RESERVE = 0.25


class BudgetError(RuntimeError):
    """Illegal budget operation (over-spend, bad split, bad restore)."""


def group_weights(weights: Sequence[int], *, spendable: int,
                  min_each: int) -> list[tuple[int, ...]] | None:
    """Deterministic child indexing after the weighted-merge rule (DESIGN §10.2).

    Returns groups of ``weights`` indices (each ascending) such that every group's
    proportional share of ``spendable`` is ``>= min_each``. The two smallest groups are
    merged (their boundary is the UNION) until the rule holds. ``None`` means the split
    must be refused: even one group cannot be afforded (force a leaf). One
    implementation, shared by :meth:`Budget.split_weighted` and the tree runner, so the
    grouping a caller merges children by is exactly the grouping the budgets cover.
    """
    if not weights:
        return []
    if min_each < 1:
        raise ValueError("min_each must be >= 1")
    total = sum(weights)
    if total <= 0:
        return None
    groups: list[list[int]] = [[i] for i in range(len(weights))]

    def group_weight(group: Sequence[int]) -> int:
        return sum(weights[i] for i in group)

    while True:
        below = [g for g in groups if (spendable * group_weight(g)) // total < min_each]
        if not below:
            return [tuple(sorted(g)) for g in sorted(groups, key=lambda g: g[0])]
        if len(groups) == 1:
            return None
        order = sorted(range(len(groups)),
                       key=lambda k: (group_weight(groups[k]), groups[k][0]))
        a, b = order[0], order[1]
        groups[a] = sorted(groups[a] + groups[b])
        del groups[b]


@dataclass
class GrantRecord:
    """Append-only ledger entry for a budget change (never injected into prompts)."""

    reason: str
    calls: int
    approved: bool


@dataclass
class Budget:
    """Remaining call units + a wall-clock deadline.

    ``calls`` is this node's whole pool (its own work plus what it will hand to
    children). ``deadline_ts`` is shared by the subtree: the run stops at the
    human's window, not at a per-node timer.
    """

    calls: int
    deadline_ts: float
    reserve_fraction: float = DEFAULT_RESERVE
    spent_calls: int = 0
    grants: list[GrantRecord] = field(default_factory=list)
    #: The pool this budget was CREATED with (before any spend or transfer). It is what
    #: makes conservation checkable at a glance: at rest ``initial_calls == calls +
    #: spent_calls`` for every pool, because :meth:`release` folds a child's spend back
    #: and :meth:`grant` extends the pool. A leak or a double release shows as ``ok``
    #: false in :meth:`accounting` (ticket 20 step 2e). ``None`` means "derive it now".
    initial_calls: int | None = None

    def __post_init__(self) -> None:
        if self.calls < 0:
            raise BudgetError("budget calls must be >= 0")
        if not 0.0 <= self.reserve_fraction < 1.0:
            raise BudgetError("reserve_fraction must be in [0, 1)")
        if self.initial_calls is None:
            self.initial_calls = self.calls + self.spent_calls
        elif self.initial_calls < 0:
            raise BudgetError("budget initial_calls must be >= 0")

    # -- state ------------------------------------------------------------
    def expired(self, now: float) -> bool:
        return now >= self.deadline_ts

    def exhausted(self, now: float) -> bool:
        """No new call may start. The deadline ends the run; call units end a node."""
        return self.calls <= 0 or self.expired(now)

    def take(self, n: int = 1) -> None:
        if n < 1:
            raise BudgetError("take() needs n >= 1")
        if n > self.calls:
            raise BudgetError(f"budget over-spend: wanted {n}, have {self.calls}")
        self.calls -= n
        self.spent_calls += n

    # -- allocation -------------------------------------------------------
    def split(self, n_children: int) -> list["Budget"]:
        """Hand each child an equal share of the non-reserve pool.

        The parent keeps the reserve plus the integer remainder as its own pool,
        which is what pays for integration work and later grants.
        """
        if n_children < 1:
            raise BudgetError("split() needs at least one child")
        spendable = int(self.calls * (1.0 - self.reserve_fraction))
        share = spendable // n_children
        if share < 1:
            # Budget too small to decompose further: the node must do the work
            # itself instead of splitting into unworkable children (DESIGN §10.2).
            raise BudgetError("budget too small to decompose: each child would get < 1 call")
        total = share * n_children
        self.calls -= total
        return [Budget(calls=share, deadline_ts=self.deadline_ts,
                       reserve_fraction=self.reserve_fraction) for _ in range(n_children)]

    def split_total(self) -> Budget:
        """Hand this pool's ENTIRE remaining calls to ONE child (reserve included).

        Unlike :meth:`split`, nothing is marked spent on the way out: the calls MOVE to
        the child and :meth:`release` folds the child's spend back, so ``calls +
        spent_calls`` is conserved. The integration leaf draws on the parent's whole
        remaining pool (reserve included), which is exactly this handoff.
        """
        child = Budget(calls=self.calls, deadline_ts=self.deadline_ts,
                       reserve_fraction=self.reserve_fraction)
        self.calls = 0
        return child

    def split_weighted(self, weights: Sequence[int], *, min_each: int) -> list["Budget"]:
        """Hand each child a share of the non-reserve pool proportional to its weight.

        Design §2 (ticket 18): if a child's proportional share falls below ``min_each``
        the SMALLEST children are merged (union boundary) or, when even a single group
        cannot be afforded, the split is refused with :class:`BudgetError` so the caller
        forces the node to a leaf. One budget is returned per surviving group, in
        increasing index order (see :func:`group_weights`). The reserve plus the integer
        remainder stay with the parent, exactly as in :meth:`split`.
        """
        weights = list(weights)
        if not weights:
            raise BudgetError("split_weighted() needs at least one child")
        if min_each < 1:
            raise BudgetError("split_weighted() needs min_each >= 1")
        spendable = int(self.calls * (1.0 - self.reserve_fraction))
        groups = group_weights(weights, spendable=spendable, min_each=min_each)
        if groups is None:
            raise BudgetError(
                "budget too small to decompose: no child share reaches min_each")
        total = sum(weights)
        budgets = [Budget(calls=max(min_each, spendable * sum(weights[i] for i in group)
                                    // total),
                          deadline_ts=self.deadline_ts,
                          reserve_fraction=self.reserve_fraction)
                   for group in groups]
        total_alloc = sum(b.calls for b in budgets)
        if total_alloc > spendable:
            raise BudgetError("weighted split exceeds the non-reserve pool")
        self.calls -= total_alloc
        return budgets

    def release(self, child: "Budget") -> int:
        """Return a finished child's pool to this one: its unused calls AND its spend.

        The child's ``spent_calls`` belongs to THIS pool's subtree, so folding it back is
        what keeps ``initial_calls == calls + spent_calls`` exact across a split/release
        cycle: counting only the parent's own takes silently drops every call a child
        (or a reserved slice) spent. A child is released exactly once, so nothing is
        double counted.
        """
        if child.deadline_ts != self.deadline_ts:
            raise BudgetError("cannot release a budget from another subtree")
        returned = child.calls
        self.calls += returned
        self.spent_calls += child.spent_calls
        return returned

    def grant(self, amount: int, reason: str) -> GrantRecord:
        """Add calls to this pool. A grant always records why (audit + stats)."""
        if amount < 0:
            raise BudgetError("grant amount must be >= 0")
        self.calls += amount
        # A grant EXTENDS the pool, so the conservation total moves with it (ticket 20
        # step 2e): otherwise ``accounting`` would read False after any legitimate grant.
        self.initial_calls = (self.initial_calls or 0) + amount
        record = GrantRecord(reason=reason, calls=amount, approved=True)
        self.grants.append(record)
        return record

    def deny(self, reason: str) -> GrantRecord:
        """Refuse a request from the child side; recorded so the stats can see it."""
        record = GrantRecord(reason=reason, calls=0, approved=False)
        self.grants.append(record)
        return record

    # -- conservation -----------------------------------------------------
    def accounting(self) -> dict:
        """The pool's conservation invariant, COMPUTED from the live numbers.

        ``ok`` is true iff the pool's creation total still equals what is left plus what
        was spent. It is derived, never asserted, so a reservation that is not returned
        (or returned twice) reads as false rather than passing silently.
        """
        return {
            "initial": self.initial_calls,
            "remaining": self.calls,
            "spent": self.spent_calls,
            "ok": self.initial_calls == self.calls + self.spent_calls,
        }

    # -- durability -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "deadline_ts": self.deadline_ts,
            "reserve_fraction": self.reserve_fraction,
            "spent_calls": self.spent_calls,
            "initial_calls": self.initial_calls,
            "accounting": self.accounting(),
            "grants": [{"reason": g.reason, "calls": g.calls, "approved": g.approved}
                       for g in self.grants],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Budget":
        return cls(
            calls=data["calls"],
            deadline_ts=data["deadline_ts"],
            reserve_fraction=data.get("reserve_fraction", DEFAULT_RESERVE),
            spent_calls=data.get("spent_calls", 0),
            grants=[GrantRecord(**g) for g in data.get("grants", [])],
            initial_calls=data.get("initial_calls"),
        )


def default_deadline(start_ts: float, seconds: float = 2.5 * 24 * 3600) -> float:
    """Default window: a task started Friday afternoon may run into Monday morning.

    The number is a fallback for runs with no human-window configuration; callers
    that know when the human returns pass that instant instead.
    """
    return start_ts + seconds
