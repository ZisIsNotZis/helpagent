"""Attempt records, novelty prefilter, and the exhaustion decision.

Owner direction 2026-09-29: "gave up" is not a state the harness has. There are
three honest stops — deadline handover, exhausted node, and success — and a node
is exhausted only when escalation provably stops producing new information.

The mechanism has two parts:

1. The model states what is NEW in this attempt (``claimed_delta``). Claiming
   nothing new is the cheapest possible signal and is treated as truth.
2. A deterministic prefilter compares the attempt with the node's history on
   failure signature and touched files. Only the genuinely ambiguous middle
   ("claims new, looks similar") costs an independent judge call — the judge
   validates the claim, because a small model saying "new idea!" is not evidence.

Every escalation must add information or shrink the unit; a repeat that adds
neither is a wasted call and is recorded as ``same``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Self, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "TargetLayer", "Strategy", "Novelty", "Attempt", "JudgeVerdict",
    "failure_signature", "prefilter", "exhausted", "layers_tried",
    "ATTRIBUTION_ALIASES", "judge_labels", "normalize_judge_labels", "summary_attribution",
]

TargetLayer = Literal["decomposition", "spec", "implementation", "tests", "sampling"]

# The escalation ladder (DESIGN §10.4), ordered by cost. L1-L5 stay inside the
# node; L6-L7 restructure the tree; L8 asks the human without blocking the run.
Strategy = Literal[
    "L1-resample",         # more samples, same strategy
    "L2-guided",           # enumerate the steps first, then emit
    "L3-deeper-explore",   # query more before writing
    "L4-rule-diagnosis",   # deterministic error -> instruction translation
    "L5-review-judge",     # independent attribution of the failure
    "L6-resplit",          # re-decompose into smaller children
    "L7-parent-spec",      # the parent's spec was wrong
    "L8-ask-user",         # a specific question; the run keeps going meanwhile
]

Novelty = Literal["novel", "same", "undecided"]

_FAILED_ID = re.compile(r"FAILED (\S+)")
_ERROR_KIND = re.compile(r"\b(\w*(?:Error|Exception))\b")
_WS = re.compile(r"\s+")


def failure_signature(failing_tests: Sequence[str], excerpts: Sequence[str]) -> str:
    """Stable identity of a failure: which tests, and which error kinds.

    Deliberately coarse. Message text and line numbers move between attempts of
    the same broken idea; the test set plus the error classes do not.
    """
    ids: list[str] = []
    for item in failing_tests:
        ids.extend(m.group(1) for m in _FAILED_ID.finditer(item))
        if "::" in item and not item.startswith("FAILED"):
            ids.append(item.strip())
    kinds: set[str] = set()
    for item in list(excerpts) + list(failing_tests):
        kinds.update(_ERROR_KIND.findall(item))
    ids_s = ",".join(sorted(set(ids)))
    kinds_s = ",".join(sorted(kinds))
    return f"tests[{ids_s}] errors[{kinds_s}]" if (ids_s or kinds_s) else ""


#: Aliases a judge model may use for the four attributions.
ATTRIBUTION_ALIASES: dict[str, str] = {
    "implementation": "implementation", "code": "implementation", "source": "implementation",
    "tests": "tests", "test": "tests",
    "spec": "spec", "specification": "spec", "requirement": "spec",
    "environment": "environment", "env": "environment", "harness": "environment",
}

#: The canonical single-label domain (kept as the compat summary of a multi-label verdict).
ATTRIBUTION_DOMAIN: tuple[str, ...] = ("implementation", "tests", "spec", "environment")

_ATTRIBUTION_TO_LABEL: dict[str, str] = {
    "implementation": "implementation_wrong",
    "tests": "test_wrong",
    "spec": "spec_wrong",
    "environment": "environment_broken",
}
_LABEL_TO_ATTRIBUTION: dict[str, str] = {v: k for k, v in _ATTRIBUTION_TO_LABEL.items()}

#: Dominance order for the ONE summary label: a wrong spec outranks a broken environment,
#: which outranks a wrong test, which outranks a wrong implementation (owner direction A).
_LABEL_PRIORITY: tuple[str, ...] = (
    "spec_wrong", "environment_broken", "test_wrong", "implementation_wrong")


def judge_labels(verdict: "JudgeVerdict") -> tuple[str, ...]:
    """The set labels a verdict asserts, in dominance order."""
    return tuple(name for name in _LABEL_PRIORITY if getattr(verdict, name, False))


def summary_attribution(labels: Sequence[str]) -> str:
    """The single compat ``attribution`` for a set of multi-labels (dominance order)."""
    for name in _LABEL_PRIORITY:
        if name in labels:
            return _LABEL_TO_ATTRIBUTION[name]
    return "implementation"


def normalize_judge_labels(verdict: "JudgeVerdict") -> "JudgeVerdict":
    """Derive the multi-labels from a legacy single ``attribution`` (and back) in place.

    A hand-authored oracle may answer with the older one-of-four ``attribution``; a
    multi-label verdict may answer with booleans only. Both spellings are kept coherent:
    the dominant label becomes the summary ``attribution`` and a single ``attribution``
    becomes its label, so nothing downstream has to know which form the judge used.
    """
    labels = judge_labels(verdict)
    if not labels and verdict.attribution:
        canonical = ATTRIBUTION_ALIASES.get(_norm(verdict.attribution))
        if canonical is not None:
            label = _ATTRIBUTION_TO_LABEL[canonical]
            setattr(verdict, label, True)
            labels = (label,)
    if labels and verdict.attribution != summary_attribution(labels):
        setattr(verdict, "attribution", summary_attribution(labels))
    if verdict.reason and not verdict.defect:
        setattr(verdict, "defect", verdict.reason)
    elif verdict.defect and not verdict.reason:
        setattr(verdict, "reason", verdict.defect)
    return verdict


class JudgeVerdict(BaseModel):
    """An independent judge's MULTI-LABEL attribution of a failure (ticket 19 A).

    The owner direction replaced the one-of-four ``attribution`` with four independent
    booleans: ``implementation_wrong``, ``test_wrong``, ``spec_wrong`` and
    ``environment_broken``, plus the judge's ``reason`` and the concrete ``evidence`` it
    used. Dominance for the decision: ``spec_wrong`` bubbles to the parent (an
    implementation and a test are meaningless against a wrong spec), then
    ``environment_broken`` parks the node, then ``test_wrong`` repairs/replaces the
    test, and ``implementation_wrong`` alone keeps implementing.

    ``attribution`` (implementation | tests | spec | environment) remains the single
    compat SUMMARY of the labels, derived in dominance order, so a legacy one-of-four
    oracle still works and the run record keeps its old field. ``defect`` names the
    CONCRETE defect in one sentence; ``raw`` keeps the judge's unedited verdict;
    ``coerced``/``coercion_reason`` record the deterministic filter overriding a
    ``test_wrong`` label that did not name the failing test or one of its assertions.
    """

    model_config = ConfigDict(extra="forbid")

    implementation_wrong: bool = False
    test_wrong: bool = False
    spec_wrong: bool = False
    environment_broken: bool = False
    reason: str = ""
    evidence: str = ""
    attribution: str = ""               # compat summary, derived in dominance order
    defect: str = ""
    raw: str = ""
    coerced: bool = False
    coercion_reason: str = ""

    @model_validator(mode="after")
    def _labels_from_attribution(self) -> Self:
        return normalize_judge_labels(self)


class Attempt(BaseModel):
    """One escalation attempt on one node. Append-only evidence, never injected."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    layer: TargetLayer
    strategy: Strategy
    claimed_delta: str = ""          # the model's own "what is new here"
    failure_signature: str = ""
    touched_files: list[str] = Field(default_factory=list)
    outcome: Literal["pass", "fail"]
    verdict: Novelty | None = None   # filled by prefilter or judge
    judge: JudgeVerdict | None = None  # the independent attribution, when one was consulted
    calls_used: int = 1
    #: Ticket 26: the write was REFUSED before it reached disk (a frozen/grader path, a
    #: test path, or a bad target shape). Nothing was learned about the code, so the
    #: escalation must not treat this like "the same attempt again" — see
    #: :func:`harness.leaf._mode` / ``_implement_question``.
    refused: bool = False
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def prefilter(history: Sequence[Attempt], candidate: Attempt) -> Novelty:
    """Cheap verdict before spending a judge call.

    ``same`` means: the model claims no change, or it claims a change while
    repeating an earlier failure signature with the same touched files and the
    same stated idea. ``novel`` means a new failure signature or new file set —
    information the last attempts did not have. Anything else needs the judge.
    """
    if not _norm(candidate.claimed_delta):
        return "same"
    if not history:
        return "novel"
    sig = candidate.failure_signature
    files = set(candidate.touched_files)
    for past in history:
        same_sig = bool(sig) and past.failure_signature == sig
        same_files = set(past.touched_files) == files
        same_claim = _norm(past.claimed_delta) == _norm(candidate.claimed_delta)
        if same_sig and same_files and same_claim:
            return "same"
    new_signature = bool(sig) and all(p.failure_signature != sig for p in history)
    new_files = files and all(set(p.touched_files) != files for p in history)
    if new_signature or new_files:
        return "novel"
    return "undecided"


def exhausted(history: Sequence[Attempt], *, consecutive_same: int = 2,
              structural: tuple[str, ...] = ("L6-resplit", "L7-parent-spec"),
              min_layers: int = 3) -> bool:
    """True when escalation can no longer be expected to add information.

    Owner direction: never stop early. A run of ``same`` verdicts alone is not
    enough, because a node whose remaining lever is RESTRUCTURING (re-split the
    work, fix the parent's spec) has not yet tried the lever most likely to
    help. So exhaustion needs the same-verdict tail AND either a structural
    attempt already made or a broadly exercised ladder.
    """
    if not history:
        return False
    tail = [a for a in history if a.verdict is not None][-consecutive_same:]
    if len(tail) < consecutive_same or not all(a.verdict == "same" for a in tail):
        return False
    if any(a.strategy in structural for a in history):
        return True
    return len(layers_tried(history)) >= min_layers


def layers_tried(history: Sequence[Attempt]) -> set[str]:
    return {a.layer for a in history}
