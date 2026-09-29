"""Non-blocking questions ("piloting") and their lifecycle.

Owner direction 2026-09-29: asking the human must never stall the run. A question
is a notification, not a wait: the harness picks a reversible default, keeps
working, and adopts the human's answer later as a normal tree patch. The other
half of the requirement is hygiene — the human returns to a list that says which
questions are still live, so stale ones are withdrawn with a recorded reason
instead of silently piling up.

States: ``open`` → ``answered`` | ``withdrawn`` | ``superseded`` (all terminal).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["QuestionState", "Question", "QuestionQueue", "QuestionStateError"]

QuestionState = Literal["open", "answered", "withdrawn", "superseded"]
_TERMINAL: tuple[QuestionState, ...] = ("answered", "withdrawn", "superseded")


class QuestionStateError(RuntimeError):
    """Illegal lifecycle move (e.g. answering a withdrawn question)."""


class Question(BaseModel):
    """One decision the human may make. ``default_choice`` is what the run does meanwhile."""

    model_config = ConfigDict(extra="forbid")

    id: str
    key: str                       # stable dedupe key: same fork -> same question
    text: str = Field(min_length=1)
    context: str = ""
    recommendation: str = ""
    default_choice: str = ""
    blocks: list[str] = Field(default_factory=list)   # node ids waiting on the answer
    state: QuestionState = "open"
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolution: str = ""
    superseded_by: str | None = None

    # -- lifecycle --------------------------------------------------------
    def _require_open(self, action: str) -> None:
        if self.state != "open":
            raise QuestionStateError(f"cannot {action} a {self.state} question ({self.id})")

    def answer(self, text: str) -> None:
        self._require_open("answer")
        if not text.strip():
            raise QuestionStateError("answer text must be non-empty")
        self.state, self.resolution = "answered", text.strip()

    def withdraw(self, reason: str) -> None:
        self._require_open("withdraw")
        if not reason.strip():
            raise QuestionStateError("withdrawal needs a reason")
        self.state, self.resolution = "withdrawn", reason.strip()

    def supersede(self, by_id: str) -> None:
        self._require_open("supersede")
        if not by_id.strip() or by_id == self.id:
            raise QuestionStateError("supersede needs a different question id")
        self.state, self.superseded_by = "superseded", by_id
        self.resolution = f"superseded by {by_id}"


class QuestionQueue:
    """Open-question registry with dedupe and automatic withdrawal."""

    def __init__(self) -> None:
        self._questions: dict[str, Question] = {}
        self._counter = 0

    # -- opening ----------------------------------------------------------
    def open(self, key: str, text: str, *, blocks: list[str] | None = None,
             **kw) -> tuple[Question, bool]:
        """Return ``(question, created)``. A live question with the same key is reused."""
        for q in self._questions.values():
            if q.key == key and q.state == "open":
                return q, False
        self._counter += 1
        qid = f"Q-{self._counter}"
        question = Question(id=qid, key=key, text=text,
                            blocks=list(blocks or []), **kw)
        self._questions[qid] = question
        return question, True

    # -- closing ----------------------------------------------------------
    def answer(self, qid: str, text: str) -> Question:
        q = self._require(qid)
        q.answer(text)
        return q

    def withdraw(self, qid: str, reason: str) -> Question:
        q = self._require(qid)
        q.withdraw(reason)
        return q

    def supersede(self, qid: str, by_id: str) -> Question:
        q = self._require(qid)
        q.supersede(by_id)
        return q

    def withdraw_resolved(self, resolved_nodes: set[str]) -> list[Question]:
        """Withdraw open questions whose blocked nodes all finished another way.

        This is what keeps the human's list honest: a question that the run
        answered by itself disappears with a reason, rather than waiting to be
        read after the fact.
        """
        closed: list[Question] = []
        for q in self.active():
            if q.blocks and set(q.blocks) <= resolved_nodes:
                q.withdraw(f"resolved by the run: {', '.join(sorted(q.blocks))} completed")
                closed.append(q)
        return closed

    # -- queries ----------------------------------------------------------
    def active(self) -> list[Question]:
        return [q for q in self._questions.values() if q.state == "open"]

    def all(self) -> list[Question]:
        return list(self._questions.values())

    def get(self, qid: str) -> Question:
        return self._require(qid)

    def _require(self, qid: str) -> Question:
        if qid not in self._questions:
            raise QuestionStateError(f"unknown question id: {qid}")
        return self._questions[qid]
