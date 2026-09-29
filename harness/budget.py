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

from dataclasses import dataclass, field

__all__ = ["Budget", "BudgetError", "GrantRecord"]

DEFAULT_RESERVE = 0.25


class BudgetError(RuntimeError):
    """Illegal budget operation (over-spend, bad split, bad restore)."""


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

    def __post_init__(self) -> None:
        if self.calls < 0:
            raise BudgetError("budget calls must be >= 0")
        if not 0.0 <= self.reserve_fraction < 1.0:
            raise BudgetError("reserve_fraction must be in [0, 1)")

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

    def release(self, child: "Budget") -> int:
        """Return a finished child's unused calls to this pool."""
        if child.deadline_ts != self.deadline_ts:
            raise BudgetError("cannot release a budget from another subtree")
        returned = child.calls
        self.calls += returned
        return returned

    def grant(self, amount: int, reason: str) -> GrantRecord:
        """Add calls to this pool. A grant always records why (audit + stats)."""
        if amount < 0:
            raise BudgetError("grant amount must be >= 0")
        self.calls += amount
        record = GrantRecord(reason=reason, calls=amount, approved=True)
        self.grants.append(record)
        return record

    def deny(self, reason: str) -> GrantRecord:
        """Refuse a request from the child side; recorded so the stats can see it."""
        record = GrantRecord(reason=reason, calls=0, approved=False)
        self.grants.append(record)
        return record

    # -- durability -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "deadline_ts": self.deadline_ts,
            "reserve_fraction": self.reserve_fraction,
            "spent_calls": self.spent_calls,
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
        )


def default_deadline(start_ts: float, seconds: float = 2.5 * 24 * 3600) -> float:
    """Default window: a task started Friday afternoon may run into Monday morning.

    The number is a fallback for runs with no human-window configuration; callers
    that know when the human returns pass that instant instead.
    """
    return start_ts + seconds
