"""v2 leaf loop — one node that owns its test, iterates red→green, and never lies.

Owner direction 2026-09-29 (DESIGN §10.1–§10.7, ticket 17), tightened by the fix
round policy: **the loop must be unable to manufacture a false success.** The v1
golden pipeline was carried by the corpus tests it could read; the blind protocol
then exposed that its self-test step was dead and that a red self-test was DROPPED
instead of kept as the target. This module is the replacement: a single leaf that

1. writes its OWN test at a new test path, RUNS it, and requires it to be RED ON
   ARRIVAL (a green test does not exercise the failure — re-ask once, then stop
   honestly with ``no-red-target``; the file is KEPT as the target),
2. iterates implementation against that test under a :class:`~harness.budget.Budget`
   and the bounded-attempt rule (3 × files, cap 9; DESIGN §4.8),
3. escalates along L1–L5, refusing an escalation that neither adds information nor
   shrinks the unit (recorded ``wasted``; the ladder still advances), and
4. stops only on green, node exhaustion, a spec bubble, a deadline handover, a
   refused/unestablished self-test, an empty acceptance-criteria list, an exhausted call
   budget, or the ladder running out — a MODEL ENVELOPE THAT STAYED MALFORMED NO LONGER
   ENDS THE NODE (ticket 19 round 2, F5): it consumes its calls, is recorded, and the loop
   continues (no model failure ever raises out of the leaf).

Fixed contract points, each deliberate:

- **Blind view.** ``LeafSpec.files`` is the source-only projection; ``grader_paths``
  are owned by the grader and never enter a prompt, an artifact, or the workdir.
  Writes to a grader path, an existing path, a non-test path, or beyond the repo are
  refused (DESIGN §6/§10.6).
- **D-transport (golden_bugfix precedent).** ``Implement`` carries no file content,
  so implementation edits ride the ``write_test`` envelope — the only content-carrying
  schema (ENVELOPE_SCHEMAS §10/§11). No new schema was added: ``SCHEMAS`` stays at 23
  entries (pinned by test_envelopes_schema), and the leaf reuses the documented
  transport rather than widening the library.
- **No false success, ever.** Green is a MACHINE-READABLE pytest report, never the
  process exit status (ticket 17 F1): run-authored code executes inside the gate
  process, so ``import atexit, os`` + ``os._exit(0)`` could make both pytest runs exit
  0 with no test summary. The gate now runs pytest with ``--junitxml`` into a private
  ``mkdtemp`` outside the repository and requires the report to exist, parse, hold at
  least one testcase, report zero failures/errors, contain the run's own expected test
  file(s) with everything passed, and contain this run's random canary node id; any
  anomaly is RED and recorded as ``gate_report_anomaly``. A ``None`` exit (transport
  error), a policy-blocked shaped result, and a gate result with no report are all red.
  The run's own ``run_tests`` green is the precondition for ANY claim; a model
  ``comment`` claiming green is irrelevant. A green that follows a judge-authorized
  test REWRITE never claims: it stops as ``green-after-test-rewrite`` (the
  implementation satisfied a replaced test — unverified).
- **A GREEN CLAIM IS VALIDATED REGARDLESS OF CAUSE (ticket 19 C, superseding the
  independent-test-as-VETO).** A claim is allowed only when (1) the run's own test is a
  real DISCRIMINATOR — it failed on the pristine source (observed red on arrival) and is
  now green and unmodified since that red — OR (2) the test path was declared unwritable
  and a review verdict with concrete evidence passed. The independent test (``iv``) stays
  available as an EXTRA LABEL: its verdict is recorded but it is no longer the only thing
  standing between the run and a claim (it is authored by the same weak model and was
  wrong in both directions — the strict arm measured better fixes but far fewer claims).
  A test that cannot be produced, afforded, or evaluated no longer blocks a claim
  authorised by the run's own discriminating test; ``claimed_basis`` is ``own-test`` or
  ``own-test+independent-test`` (or ``review`` in review mode).
- **PROACTIVE MULTI-LABEL ATTRIBUTION (ticket 19 A).** The judge is consulted when the
  run's own test REPORTS RED — after K=2 consecutive red attempts that materially changed
  the code, or immediately when the own test cannot be made red on arrival — not only when
  the model volunteers a blame. Its verdict is MULTI-LABEL
  (``implementation_wrong``/``test_wrong``/``spec_wrong``/``environment_broken`` + reason +
  evidence), and dominance decides the move: ``spec_wrong`` bubbles to the parent
  (``spec-bubble``), ``environment_broken`` parks the node ``needs-user``
  (``stop_reason="environment"``, without burning budget), ``test_wrong`` repair/replaces
  the own test (bounded), and ``implementation_wrong`` alone keeps implementing. A
  ``test_wrong`` label is still put through the deterministic filter
  (:func:`apply_judge_filter`): it is honoured only with a defect naming the failing test
  or one of its assertions, else it is coerced and recorded.
- **REVIEW-BASED VERIFICATION WHEN NO TEST CAN CARRY IT (ticket 19 B).** If the own test
  cannot be made red on arrival (after the bounded re-ask), or the judge's ``test_wrong``
  label survives a bounded repair that still cannot discriminate, or the test path is
  unwritable, the node switches to a fresh-context REVIEWER of the final diff
  (:class:`ReviewRequest`/``ReviewVerdict``, :func:`apply_review_filter`). Round 2 (F1)
  tightened the evidence filter: a pass counts only when its evidence names a path that
  REALLY changed in the original-vs-final diff, or a symbol that occurs in a changed
  file's final text; a bare line reference is no longer enough, so an UNCHANGED tree can
  never claim by any route. Until then the node may NOT claim (``verification_basis
  ="review"``, ``claimed_basis="review"``). With no reviewer injected the leaf keeps its
  conservative honest stop.
- **DECLARED TEST CASES AND PER-REQUIREMENT ARTIFACT COVERAGE (ticket 19 D/E).** A plan
  may DECLARE, per acceptance criterion, the test file and function names that must exist
  and pass (:class:`DeclaredTestCase`); the harness verifies them mechanically from the
  report and a missing name/file is a distinct, repairable failure (``stop_reason
  ="test-cases"``). Independently, every criterion's named artifacts (file paths and
  symbols that exist in the injected view) must appear in the node's final diff — an
  untouched named artifact means the requirement was not implemented and the node may NOT
  claim — the design answer to the T-31 false success (the loop keeps working; the
  coverage evidence rides the outcome as ``coverage_missing``). Round 2 tightens this in
  three ways: (F3) the diff is compared with comments and whitespace stripped, so a
  comment-only edit is not a change; (F2/F4) a criterion that names NO resolvable
  artifact is NOT skipped — on the test basis it must be carried by a DECLARED test that
  DISCRIMINATES (red on the pristine source, green on final; a placeholder cannot), else
  the claim is blocked with ``coverage_unresolved``; and (F2) an EMPTY acceptance-criteria
  list cannot claim on the test basis at all — review is mandatory.
- **The independent test's file name is a PARAMETER (ticket 17 round 8).** The harness,
  not the model, decides the collected file name: the candidate is written at a path
  pytest actually collects (:func:`_iv_safe_path`), and a relocation is recorded
  (``independent_test_relocated`` + ``tolerance_fired``), so a naming slip can never
  become ``independent-test-unobserved`` — that verdict is reserved for a test the gate
  genuinely could not observe. A DEFECTIVE verdict — ``independent-test-not-red`` (the
  test also passes on the pristine source) or ``independent-test-unobserved`` — earns
  exactly ONE bounded re-ask of the same fresh-context producer with the verdict as
  evidence and the gates run again (``iv_attempts``/``iv_repairs`` count the cost). If
  the repair also fails, the verdict stands and the loop continues as before.
- **Coverage is PER-CRITERION DISCRIMINATION on a DETERMINISTIC node map (ticket 17
  rounds 10-11).** The round-9 rule only proved a criterion was NAMED: one real test
  plus a ``test_ac2_placeholder`` that asserts ``True`` (or a single function carrying
  every index) approved while the criterion was never exercised. Round 10 required each
  criterion's ``-k ac<i>`` selection to be RED ON ORIGINAL and GREEN ON FINAL, but two
  deterministic gaps remained: ``-k`` is a case-sensitive SUBSTRING match (``ac1`` also
  selects ``test_ac12_thing``), and one test carrying every index was selected for every
  criterion and approved them all. Round 11 replaces the ``-k`` term with a deterministic
  node map: the index -> node-id mapping is derived from the FIRST full-file report (the
  whole-file red-on-original gate) with a BOUNDARY-AWARE index match on the test node
  NAME (``ac1`` never matches ``ac12``/``ac10``; case-insensitive), scoped to the
  independent test file's own node ids. Each criterion's discrimination is then checked
  by running the EXPLICIT node ids for that criterion (``pytest path::nodeid ...``, plus
  the per-run canary node id explicitly) on the original and final trees, so nothing
  else can run or satisfy the criterion. A criterion with no matching node is
  ``independent-test-incomplete-coverage``; a node id selected for more than one
  criterion is ``independent-test-shared-coverage`` (the per-criterion sets must be
  DISJOINT). Both are REPAIRABLE on the existing one-shot path, whose evidence lists the
  offending indices. A criterion that is green on the original is
  ``independent-test-not-discriminating``. Every per-criterion count is scoped to the
  independent test file's own node ids, so the canary or any other collected file can
  never satisfy a criterion. The name convention stays a HINT in the prompt. The criteria
  count and, for each index, the explicit node ids plus the original/final collected
  counts, failures, and reason land in the persisted run record. An empty criteria list
  skips the requirement and records ``no_acceptance_criteria``. This makes an
  index-colliding name unmappable for the wrong criterion and makes a single all-index
  test a REPAIRABLE defect rather than a free pass.
- **A test may only be REPLACED, never weakened, and only with an independent
  judge.** The model's own "the test is wrong" claim is never enough: without an
  injected independent judge the claim is not credited and the failure is treated
  as an implementation failure (deterministic conservative default). When the judge
  does label the test wrong, the test is re-derived from scratch and must be RED
  ON ARRIVAL again before the loop continues. A ``test_wrong`` label is
  itself put through the deterministic filter (:func:`apply_judge_filter`): it is
  honoured only when the verdict carries a non-empty defect naming the failing test
  function or one of its assertions; otherwise it is coerced to implementation and
  the coercion is recorded for calibration.
- **No model failure crashes the leaf.** Every envelope request (self-test, its
  retry, implement, judge, test rewrite, review, test-case repair) is retried up to
  :data:`ENVELOPE_RETRIES` times when the model output is malformed/unparseable; a
  persistent failure NEVER raises :class:`SchemaViolation` and NEVER ends the node
  (ticket 19 round 2, F5): it consumes its calls, records the step, and the loop
  continues, bounded by the existing call-budget / attempt-cap / ladder stops.
- **No "give up".** Exhaustion is delegated to :func:`harness.attempts.exhausted`,
  so a same-verdict tail without a structural lever or three exercised layers keeps
  the node alive. The leaf's ``exhausted`` flag is set only by that function; a call
  budget or a deadline is a distinct, honestly-named stop (``stop_reason``).
"""

from __future__ import annotations

import inspect
import json
import posixpath
import re
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any

from harness.attempts import (
    ATTRIBUTION_ALIASES,
    Attempt,
    JudgeVerdict,
    failure_signature,
    judge_labels,
    layers_tried,
    normalize_judge_labels,
    prefilter,
    summary_attribution,
)
from harness.attempts import exhausted as attempts_exhausted
from harness.budget import Budget
from harness.checks import diagnose_test_output
from harness.exec import ShapedResult
from harness.exec import exec as k_exec
from harness.gate_report import (
    JUNIT_FAMILY_ARGS,
    GateReport,
    canary_node_id,
    canary_path,
    canary_source,
    canary_token,
    cleanup_report,
    evaluate_gate,
    private_report_path,
)
from harness.questions import Question, QuestionQueue
from harness.runner import llm_step, note
from harness.staging import (
    PYTEST_ISOLATION_ARGS,
    gate_env,
    shadowing_paths,
    PYTEST_ISOLATION_ENV,
    is_test_infrastructure,
    is_test_path,
    owned_paths,
    shadowing_path,
)

__all__ = [
    "LADDER",
    "STRATEGY_LAYER",
    "CriterionEvidence",
    "Escalation",
    "IndependentTestCandidate",
    "IndependentTestRequest",
    "IndependentTestVerdict",
    "JudgeRequest",
    "JudgeVerdict",
    "LeafOutcome",
    "LeafSpec",
    "VerificationRecord",
    "WriteShapeRefused",
    "apply_judge_filter",
    "escalate",
    "evaluate_independent_test",
    "run_leaf",
    "verification_reason_problem",
]

#: The in-node escalation ladder (DESIGN §10.4 L1–L5). L6–L8 restructure the tree
#: or ask the human; those belong to the parent, so the leaf stops and bubbles
#: instead of pretending to execute them.
LADDER: tuple[str, ...] = (
    "L1-resample",
    "L2-guided",
    "L3-deeper-explore",
    "L4-rule-diagnosis",
    "L5-review-judge",
)

#: Which :data:`harness.attempts.TargetLayer` each rung interrogates. L1 adds
#: samples (the sampling layer); L2–L4 decompose/explore/diagnose the implementation;
#: L5 is the independent review that reads the failure against the SPEC as the
#: highest contract (DESIGN §10.1 step 5). Three distinct layers are reachable over
#: the ladder, which is what lets :func:`attempts.exhausted` ever return True here.
STRATEGY_LAYER: dict[str, str] = {
    "L1-resample": "sampling",
    "L2-guided": "implementation",
    "L3-deeper-explore": "implementation",
    "L4-rule-diagnosis": "implementation",
    "L5-review-judge": "spec",
}

#: The leaf's stop vocabulary (ticket policy). Exactly one is set on every return.
#: A model envelope that stayed unparseable after its bounded retries no longer raises
#: AND no longer stops the node (ticket 19 round 2, F5) — the node continues bounded by the
#: call-budget / attempt-cap / ladder stops.
#: Ticket 19 adds ``environment`` (a judge-attributed broken environment — park needs-user,
#: do not burn budget) and ``test-cases`` (a declared test case is still missing/unpassed
#: after the bounded repair, owner direction D). A per-requirement artifact-coverage failure
#: (owner direction E) is a CLAIM BLOCKER that keeps the loop working, recorded as
#: ``coverage_missing``/``requirement_uncovered`` — not a stop of its own. Round 2 adds
#: ``no-acceptance-criteria`` (an empty criteria list cannot be carried by the test basis
#: alone) and REMOVES ``malformed-output``: a malformed envelope no longer ends the node
#: (ticket 19 round 2, F5). Round 3 adds ``criterion-unresolved``: an unresolvable
#: criterion with no declared discriminating test AND no reviewer is an honest stop (a
#: reviewer would have carried the claim on the review basis — FIX 1).
STOP_REASONS: tuple[str, ...] = (
    "calls",            # the call budget is spent
    "deadline",         # the wall-clock window closed (handover)
    "attempts",         # node exhaustion or the bounded-attempt cap
    "ladder",           # no rung is left to advance to
    "spec-bubble",      # the judge attributed the failure to the specification
    "environment",      # the judge attributed the failure to a broken environment
    "test-cases",       # a declared test case is still missing/unpassed (no claim)
    "criterion-unresolved",  # an unresolvable criterion with no reviewer (no claim)
    "no-acceptance-criteria",  # an empty criteria list cannot claim on the test basis
    "no-red-target",    # the run's own test could not be made to fail on arrival
    "self-test",        # the run's own test could not be written at a safe path / could not run
    "green",            # the run's own tests exited 0 and the claim held
    "green-after-test-rewrite",  # a replaced test went green: unverified, never claimed
    "write-shape",      # a write target could not be normalized (NUL/long/dir/file-parent)
    "verification-required",  # the plan's verification tier was not met and no best_effort
    "unverified",       # the run claimed at the none+reason tier (best_effort)
)

#: The ORDERED verification-strength tiers (ticket 20): the strongest evidence a node
#: that WROTE CODE can carry is a real discriminating TEST, next one or more independent
#: REVIEWS, and last NO test and NO review with a REQUIRED written reason. The strength
#: is a total order (``test`` > ``review`` > ``none``); a claim's tier is enforced
#: against the plan's declared requirement.
VERIFICATION_TIERS: tuple[str, ...] = ("test", "review", "none")

#: The declared requirement domain a plan may set per node (ticket 20).
VERIFICATION_REQUIREMENTS: tuple[str, ...] = ("test", "review", "any")

_TIER_RANK: dict[str, int] = {"test": 2, "review": 1, "none": 0}
#: The floor each declared requirement imposes on a claim. ``any`` imposes no verified
#: floor, but the ``none+reason`` tier is NEVER a normal claim: it always needs the
#: ``best_effort`` opt-in plus a valid written reason (see :func:`verification_reason_problem`).
_REQUIRED_FLOOR: dict[str, int] = {"test": 2, "review": 1, "any": 0}

# ---------------------------------------------------------------------------
# Review ANGLES, weights, and the five ORDINAL grades (ticket 20, item 1-3)
# ---------------------------------------------------------------------------

#: The CLOSED review-angle registry, one tuple per REVIEW LEVEL. A review is NOT a count
#: of identical calls (the round-1 verification gap 3): it is one fresh-context call per
#: DECLARED ANGLE, each with its own fixed prompt template (:data:`REVIEW_ANGLE_PROMPTS`),
#: drawn from this closed set so a small model cannot wander.
REVIEW_ANGLES_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "plan": ("constraint-conflict", "dependency-availability",
             "architecture-consistency", "cost"),
    "implementation": ("ac-correctness", "contract-compat", "edge-and-error",
                       "regression-risk", "input-safety", "maintainability"),
    "integration": ("end-to-end-behaviour", "interface-alignment", "regression"),
}

#: The review level an ordinary (implementation) leaf belongs to; the integration leaf
#: overrides it with ``review_level="integration"``. The plan (How) level is defined for
#: the How axis (the NEXT round) and is not wired here.
DEFAULT_REVIEW_LEVEL = "implementation"

#: Every angle in the closed set, flattened over the levels (the plan-envelope domain).
ALL_REVIEW_ANGLES: tuple[str, ...] = tuple(
    angle for level in ("plan", "implementation", "integration")
    for angle in REVIEW_ANGLES_BY_LEVEL[level])

#: The PREDEFINED per-angle weights --- the accuracy-style angles (does the diff satisfy
#: the acceptance criteria / the contract) weigh most, edge/regression/input next, and the
#: maintainability-style angles least. The weighted score ranks candidates; the critical
#: angles below are the veto. One table, the single place the weights live.
REVIEW_ANGLE_WEIGHTS: dict[str, int] = {
    "constraint-conflict": 3, "dependency-availability": 3,
    "architecture-consistency": 2, "cost": 1,
    "ac-correctness": 3, "contract-compat": 3,
    "edge-and-error": 2, "regression-risk": 2, "input-safety": 2,
    "maintainability": 1,
    "end-to-end-behaviour": 3, "interface-alignment": 2, "regression": 2,
}

#: The PREDEFINED CRITICAL angles per level (ticket 20, item 3). A ``definitely-problematic``
#: verdict on one of these VETOES the candidate regardless of the weighted average, so a
#: real defect found by a high-weight angle cannot be averaged away. A critical angle that
#: did not run at all also blocks a review-tier claim (the veto would be vacuous otherwise).
CRITICAL_REVIEW_ANGLES: dict[str, tuple[str, ...]] = {
    "plan": ("constraint-conflict",),
    "implementation": ("ac-correctness", "contract-compat"),
    "integration": ("end-to-end-behaviour",),
}

#: The five ORDINAL grades (worst → best) and their integer ranks (ticket 20, item 2).
REVIEW_GRADES: tuple[str, ...] = (
    "definitely-problematic", "probably-problematic", "uncertain",
    "probably-ok", "definitely-ok")
REVIEW_GRADE_RANK: dict[str, int] = {
    "definitely-problematic": -2, "probably-problematic": -1, "uncertain": 0,
    "probably-ok": 1, "definitely-ok": 2}
#: The grades that carry a POSITIVE verdict (only these may be grounded into a claim).
POSITIVE_REVIEW_GRADES: frozenset[str] = frozenset({"probably-ok", "definitely-ok"})

#: The fixed prompt template per angle. The prompt REQUIRES either a concrete
#: counterexample or the explicit statement that the angle found none, and the grade is
#: one of the five ordinal values --- so the reviewer cannot answer with a vague approval.
REVIEW_ANGLE_PROMPTS: dict[str, str] = {
    "constraint-conflict": (
        "Check whether the plan conflicts with a constraint stated in the goal or the "
        "acceptance criteria (an invariant, a required behaviour, a forbidden change)."),
    "dependency-availability": (
        "Check whether every dependency the plan relies on (a module, symbol, file, "
        "tool, or already-landed behaviour) actually exists and is available."),
    "architecture-consistency": (
        "Check whether the plan is consistent with the existing architecture and "
        "conventions of the code it touches."),
    "cost": (
        "Check whether the plan's cost (calls, time, amount of change) is proportionate "
        "to the requirement."),
    "ac-correctness": (
        "Check whether the final diff makes EACH acceptance criterion true, reading the "
        "actual changed code, not the summary."),
    "contract-compat": (
        "Check whether the final diff keeps every interface, signature, and documented "
        "contract it must not break."),
    "edge-and-error": (
        "Check whether the final diff handles the edge cases and error paths the "
        "acceptance criteria imply."),
    "regression-risk": (
        "Check whether the final diff can break behaviour that worked before but is not "
        "covered by the goal."),
    "input-safety": (
        "Check whether the final diff is safe against malformed, empty, or hostile "
        "inputs at the boundary it touches."),
    "maintainability": (
        "Check whether the final diff is readable, minimal, and consistent with the "
        "surrounding code."),
    "end-to-end-behaviour": (
        "Check whether the child changes together produce the end-to-end behaviour the "
        "node's acceptance criteria require."),
    "interface-alignment": (
        "Check whether the child changes agree on the interfaces between them (names, "
        "signatures, data shapes)."),
    "regression": (
        "Check whether integrating the child changes breaks behaviour that was working "
        "before."),
}


#: The minimum length of a ``none+reason`` written reason (ticket 20).
MIN_VERIFICATION_REASON = 24
#: The reason must NAME the activity it is about ...
_REASON_ACTIVITY: tuple[str, ...] = (
    "test", "tests", "testing", "review", "reviews", "reviewing", "verif")
#: ... and state WHY testing or reviewing was not possible or not warranted.
_REASON_WHY: tuple[str, ...] = (
    "cannot", "can not", "can't", "unable", "not able", "impossible",
    "not possible", "not feasible", "infeasible", "not warranted",
    "not applicable", "no test", "no review", "without", "not worth", "no way",
    "unsafe", "not sensible", "not meaningful", "not amenable")
#: Words that carry NO artifact and NO observation of their own. A reason made ONLY of
#: these (plus the activity/why vocabulary) is boilerplate, however long it is --- this is
#: the deterministic answer to round-1 gap 1 (a keyword substring test is not enough).
_REASON_GENERIC: frozenset[str] = frozenset({
    "test", "tests", "testing", "review", "reviews", "reviewing", "reviewer",
    "reviewers", "verification", "verify", "verified", "check", "checks",
    "checking", "checked", "change", "changes", "changed", "code", "function",
    "functions", "method", "methods", "helper", "helpers", "behaviour",
    "behavioural", "behavior", "feature", "features", "thing", "things", "part",
    "parts", "reason", "reasons", "reasoning", "possible", "impossible",
    "available", "unavailable", "warranted", "applicable", "reviewable",
    "testable", "sensible", "meaningful", "amenable", "feasible", "infeasible",
    "worth", "safe", "unsafe", "manual", "manually", "automatic", "automatically",
    "cannot", "unable", "way", "able", "need", "needed", "needs", "still",
    "without", "note", "noted", "here", "node", "goal", "criteria",
    "criterion", "acceptance", "requirement", "requirements", "current", "given",
    "this", "that", "these", "those", "because", "since", "and", "the", "for",
    "with", "from", "into", "only", "just", "very", "much", "more", "most",
    "not", "are", "is", "was", "were", "be", "been", "being", "has", "have",
    "had", "do", "does", "did", "would", "could", "should", "may", "might",
    "must", "will", "can", "or", "but", "if", "then", "than", "there", "their",
    "its", "it", "as", "at", "by", "on", "in", "of", "to", "a", "an", "over",
    "under", "between", "any", "all", "some", "each", "every", "no", "nor", "so",
    "such", "too", "also", "while", "when", "where", "which", "who", "what", "why",
    "how", "they", "them", "we", "you",
})
#: Fixed boilerplate/template sentences; a reason that IS one of these (or opens with one)
#: is rejected by name, independent of the specificity heuristic above.
_REASON_BOILERPLATE: tuple[str, ...] = (
    "no test can carry verification for this node",
    "no test can carry verification for this change",
    "testing or reviewing was not possible or not warranted",
    "no test and no reviewer could carry verification",
    "testing is not possible and no review is available",
    "there is nothing to test or review here",
)
_REASON_WORD = re.compile(r"[a-z0-9][a-z0-9_./-]*")


def _reason_tokens(text: str) -> set[str]:
    """Lower-cased word tokens of ``text`` (dotted/underscored identifiers kept whole)."""
    return {word for word in _REASON_WORD.findall((text or "").lower())}


def verification_reason_problem(reason: str, *, goal: str = "",
                                acs: Sequence[str] = ()) -> str:
    """DETERMINISTICALLY check a ``none+reason`` justification (ticket 20, item 4).

    Returns "" when the reason is acceptable, else a short problem describing the first
    failure. Beyond the original length/activity/why checks, the reason must NOT be
    boilerplate or a fixed template sentence, must NOT merely restate the goal or the
    acceptance criteria (a token-overlap test), and must name a concrete artifact or
    observation (at least one content token outside the generic vocabulary) --- so the
    round-1 hole (any 24+ character sentence mentioning testing and a why word passed)
    is closed.
    """
    text = " ".join((reason or "").split())
    if not text:
        return "empty reason"
    if len(text) < MIN_VERIFICATION_REASON:
        return f"reason shorter than {MIN_VERIFICATION_REASON} characters"
    lowered = text.lower()
    if not any(term in lowered for term in _REASON_ACTIVITY):
        return "reason does not mention testing or reviewing"
    if not any(term in lowered for term in _REASON_WHY):
        return ("reason does not say why testing or reviewing was not possible or "
                "not warranted")
    normalized = lowered.strip(" .")
    if any(normalized == phrase or normalized.startswith(phrase)
           for phrase in _REASON_BOILERPLATE):
        return "reason is a boilerplate/template sentence"
    tokens = _reason_tokens(lowered)
    specific = tokens - _REASON_GENERIC
    if not specific:
        return "reason names no concrete artifact or observation"
    goal_tokens = _reason_tokens(" ".join([goal, *acs])) - _REASON_GENERIC
    if goal_tokens:
        overlap = len(specific & goal_tokens) / len(specific)
        if overlap >= 0.8:
            return "reason merely restates the goal or acceptance criteria"
    return ""


def review_angles_for_level(level: str) -> tuple[str, ...]:
    """The closed angle set for ``level`` (defaulting to the implementation level)."""
    return REVIEW_ANGLES_BY_LEVEL.get(level, REVIEW_ANGLES_BY_LEVEL[DEFAULT_REVIEW_LEVEL])


def critical_review_angles(level: str) -> tuple[str, ...]:
    """The PREDEFINED veto angles for ``level``."""
    return CRITICAL_REVIEW_ANGLES.get(level, CRITICAL_REVIEW_ANGLES[DEFAULT_REVIEW_LEVEL])


def review_grade_rank(grade: str) -> int:
    """The ordinal rank of a grade (unknown grades are the neutral ``uncertain`` = 0)."""
    return REVIEW_GRADE_RANK.get(grade, 0)


def effective_review_angles(declared: Sequence[str], level: str) -> tuple[str, ...]:
    """The angles a review actually runs: the declared in-domain angles in order, deduped
    (a repeated angle is a recorded deviation, never extra evidence), or --- when the plan
    declared none --- the level's CRITICAL angles (the minimum a claim must check)."""
    domain = review_angles_for_level(level)
    out: list[str] = []
    for angle in declared:
        if angle in domain and angle not in out:
            out.append(angle)
    return tuple(out) or critical_review_angles(level)


def weighted_review_score(verdicts: Sequence["ReviewVerdict"]) -> int:
    """The PREDEFINED-weight weighted sum of per-angle grades. An angle with no review
    contributes 0, so no review at all scores 0."""
    return sum(REVIEW_ANGLE_WEIGHTS.get(v.angle, 0) * review_grade_rank(v.grade)
               for v in verdicts)


def critical_review_veto(verdicts: Sequence["ReviewVerdict"], level: str) -> str:
    """The VETO reason when a critical angle of ``level`` graded ``definitely-problematic``
    (``-2``), else "". The veto is not diluted by the weighted average."""
    critical = set(critical_review_angles(level))
    for verdict in verdicts:
        if verdict.angle in critical and review_grade_rank(verdict.grade) <= -2:
            return (f"critical angle {verdict.angle} graded {verdict.grade}: "
                    f"{verdict.detail or verdict.evidence or 'definitely problematic'}")
    return ""


def combine_review_verdicts(verdicts: Sequence["ReviewVerdict"], angles: Sequence[str],
                            level: str) -> tuple[bool, int, str]:
    """Combine per-angle graded reviews into ``(ok, weighted_score, reason)``.

    A review carries a claim ONLY when every critical angle of the level produced a
    graded verdict, no angle is negative (any ``probably-problematic``/worse grade is an
    ACTION ITEM: the node keeps working), and the weighted score is positive. A missing
    critical angle scores 0 (the veto would be vacuous otherwise).
    """
    # A COERCED verdict (an ungrounded positive, or a malformed review) carries no grade
    # for aggregation: it is as if that angle did not run, so a missing critical angle
    # still blocks the claim.
    by_angle = {v.angle: v for v in verdicts
                if v.angle in set(angles) and not v.coerced}
    missing = [a for a in critical_review_angles(level) if a not in by_angle]
    if missing:
        return False, 0, f"critical review angle(s) not run: {', '.join(missing)}"
    veto = critical_review_veto(by_angle.values(), level)
    if veto:
        return False, weighted_review_score(by_angle.values()), veto
    negative = [v for v in by_angle.values() if review_grade_rank(v.grade) < 0]
    if negative:
        worst = min(negative, key=lambda v: review_grade_rank(v.grade))
        return False, weighted_review_score(by_angle.values()), (
            f"angle {worst.angle} graded {worst.grade}: "
            f"{worst.detail or worst.evidence or 'problematic'}")
    score = weighted_review_score(by_angle.values())
    if score <= 0:
        return False, score, "the weighted review score is not positive"
    return True, score, ""


#: The predefined small share of a run's code-writing nodes that may claim at the
#: ``none`` tier or declare ``best_effort`` before the run is flagged ``covenant-diluted``
#: (ticket 20, items 4-5).
COVENANT_DILUTION_SHARE = 0.25


def covenant_weakening_share(weakened: int, nodes: int) -> float:
    """The share of code-writing nodes recorded as covenant-weakened (0.0 when no nodes)."""
    return (weakened / nodes) if nodes > 0 else 0.0


def covenant_diluted(weakened: int, nodes: int,
                     share: float = COVENANT_DILUTION_SHARE) -> bool:
    """True when the covenant-weakened share EXCEEDS the predefined small share."""
    return nodes > 0 and covenant_weakening_share(weakened, nodes) > share


#: Bounded retries for a malformed/unparseable model envelope (owner direction: no
#: model failure may crash the leaf). One initial attempt plus this many retries; a
#: persistent failure is RECORDED and the node continues (ticket 19 round 2, F5) — it
#: never raises, and it never ends the node.
ENVELOPE_RETRIES = 2

#: Bounded retries for the JUDGE specifically (ticket 19 round 3, FIX 2). The judge is
#: consulted on a red report and a malformed judge used to burn the generic
#: :data:`ENVELOPE_RETRIES` (three calls) before the node moved on, and the same
#: iteration could consult it twice. One retry (two calls) is enough to ride out a
#: transient format slip; the driver's own two-shape fallback covers the systematic
#: ones, and the leaf then records the deterministic "attribution unavailable"
#: fallback instead of retrying forever.
JUDGE_RETRIES = 1

_SELF_TEST_QUESTION = (
    "Write the run's OWN test file that pins the goal. Reply with a NEW file path "
    "(one that does not exist yet) and its complete content. This test is your target: "
    "a failing red run is expected now and the file is KEPT — never deleted. "
    "Do not name or touch any path outside the injected repository view."
)

_RETRY_SELF_TEST_QUESTION = (
    "Your previous test PASSED on arrival (exit 0), so it does not pin the goal — a "
    "valid target must FAIL now. Write a NEW test at a NEW path that fails against the "
    "current source. Reply with the file path and its complete content."
)

#: Ticket 19 D: the bounded repair for a green run whose test does not expose the DECLARED
#: test cases (missing file/function names). The declared contract is the harness's, so
#: the missing names are handed back as evidence.
_MISSING_TEST_CASES_QUESTION = (
    "Your current test does not expose the DECLARED test cases for this node. Rewrite "
    "the complete test file so the declared test functions exist at the declared path and "
    "pass. Keep the test discriminating. Reply with the file path and complete content."
)

#: Ticket 20: the bounded envelope that asks for the WRITTEN ``none+reason``
#: justification when neither a discriminating test nor an independent review can carry a
#: node's claim. The reason is checked deterministically (length, why testing/reviewing was
#: not possible or not warranted, NOT boilerplate, NOT a restatement of the goal, and a
#: NAMED concrete artifact or observation), so a terse, generic, or goal-restating answer
#: cannot carry a claim.
_VERIFICATION_REASON_QUESTION = (
    "No test can carry verification for this node and no independent review is available "
    "(or a review is not warranted). In one or two sentences, explain IN WRITING why "
    "testing or reviewing was not possible or not warranted for THIS change. You MUST name "
    "a concrete artifact or observation (a file, a symbol, a test name, or a specific "
    "behaviour); do NOT restate the goal and do NOT reply with a generic phrase. Reply "
    "with reason=<your explanation>."
)

_TEST_BLAME_PHRASES = (
    "test is wrong",
    "wrong test",
    "bad test",
    "test-side",
    "test is incorrect",
    "test is broken",
    "fix the test",
)


@dataclass(frozen=True)
class DeclaredTestCase:
    """One DECLARED test case: the file and function names a plan expects for a criterion
    (ticket 19 D). The harness verifies mechanically from the machine-readable report that
    the file exists and every declared name is a collected, passing node id; a missing
    name/file is a distinct, repairable failure. The name check is boundary-aware (a
    declared ``test_ac1_goal`` never matches ``test_ac1_goal_extra``)."""

    ac_id: str                       # e.g. "AC-1" — must be one of the node's ACs
    file: str                        # the test file that must exist and collect
    names: tuple[str, ...] = ()      # test function names that must exist and pass


#: Marker attribute set on :class:`harness.how.NodeRecord`. The node record is the
#: model's rewritten scratchpad and is NEVER evidence; the guard below makes that
#: STRUCTURAL rather than a flag. A plain class attribute keeps leaf.py independent of
#: how.py (which imports leaf), so the check is not defeated by an import cycle.
NODE_RECORD_MARKER = "__helpagent_node_record__"


def _is_node_record(value: Any) -> bool:
    return getattr(type(value), NODE_RECORD_MARKER, False) is True


def _contains_node_record(value: Any, _depth: int = 0) -> bool:
    if _depth > 4:
        return False
    if _is_node_record(value):
        return True
    if isinstance(value, Mapping):
        return any(_contains_node_record(k, _depth + 1)
                   or _contains_node_record(v, _depth + 1) for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_node_record(item, _depth + 1) for item in value)
    return False


def reject_node_record(value: Any, *, owner: str) -> None:
    """Raise when a node record reaches an evidence input it may never enter.

    "The node record is never evidence" is STRUCTURAL, not a flag a caller can ignore:
    it is a model-maintained scratchpad, so no verification/claim input (LeafSpec,
    VerificationRecord, ReviewRequest, JudgeRequest, the selection key) may carry one.
    """
    if _contains_node_record(value):
        raise ValueError(
            f"{owner} may not carry a NodeRecord: a node record is never evidence")


def reject_node_record_fields(instance: Any) -> None:
    """Reject a node record in ANY field of a dataclass instance (the input guard)."""
    for f in fields(instance):
        reject_node_record(getattr(instance, f.name), owner=type(instance).__name__)


@dataclass(frozen=True)
class LeafSpec:
    """The blind leaf contract.

    ``files`` is the source-only view the run may see; ``grader_paths`` are owned by
    the grader and must never reach the run (DESIGN §6/§10.6).

    ``write_boundary`` is the declared write scope the leaf may modify (a node's plan
    boundary). It is ``None`` for the single-leaf driver, whose boundary is the whole
    source view — so its behaviour is unchanged; a tree child sets it to its declared
    files, and any write outside it is refused at the parameter layer (never a crash).

    ``test_cases`` is the DECLARED test-case contract (ticket 19 D): the test file +
    function names the node expects per acceptance criterion. Empty means the node
    declared none and the check is skipped.
    """

    goal: str
    files: dict[str, str]  # blind view: source only
    acs: list[str]
    interfaces: list[str]
    grader_paths: tuple[str, ...] = ()  # owned by the grader: never shown, never writable
    write_boundary: tuple[str, ...] | None = None  # None ⇒ unguarded (single-leaf driver)
    test_cases: tuple[DeclaredTestCase, ...] = ()
    #: The files this node's acceptance criteria may name as artifacts (ticket 19 E). The
    #: projection of the whole repo the requirement text can reference; defaults to the
    #: blind view's keys when empty.
    candidate_files: tuple[str, ...] = ()
    #: Ticket 20 planning-time covenant: the verification the plan requires of this node
    #: (``test`` | ``review`` | ``any``), the REVIEW ANGLES the review tier must run (a
    #: closed per-level set; empty means the level's critical angles), the review level
    #: (``implementation`` | ``integration``; the plan level is not wired here), and
    #: whether a weaker tier is an accepted best-effort fallback with a plan-level reason.
    #: Defaults preserve the pre-ticket-20 policy (any tier, critical angles, no fallback).
    verification_required: str = "any"
    review_angles: tuple[str, ...] = ()
    review_level: str = DEFAULT_REVIEW_LEVEL
    best_effort: bool = False
    best_effort_reason: str = ""

    def __post_init__(self) -> None:
        reject_node_record_fields(self)


@dataclass(frozen=True)
class CriterionEvidence:
    """Per-criterion discrimination evidence (ticket 17 rounds 10-11).

    For criterion ``index`` the harness ran the EXPLICIT node ids it derived for that
    criterion (``selection`` is their space-joined form) on the original and the final
    tree and counted the INDEPENDENT test's own node ids (never the canary or another
    file). ``reason`` is "" when the node ids collected, FAILED on the original and
    PASSED on the final; otherwise it names the defect (``not-discriminating`` /
    ``incomplete-coverage`` / ``shared-coverage`` / ``red-on-final`` / ``unobserved``)
    and ``detail`` is the human-readable evidence for the run record.
    """

    index: int
    selection: str
    original_collected: int
    original_failures: int
    final_collected: int
    final_failures: int
    reason: str = ""
    detail: str = ""


@dataclass(frozen=True)
class RequirementCoverage:
    """Per-criterion ARTIFACT coverage of the node's final diff (ticket 19 E).

    For criterion ``index`` the harness deterministically extracted the artifacts its
    text names — file paths and symbols that actually exist in the injected repo view —
    and checked whether each appears in the node's final diff (with comments and
    whitespace stripped, F3). ``missing`` lists the artifacts that do NOT: a criterion
    whose named artifact is untouched means the requirement was not implemented and the
    node may not claim. An empty ``files``/``symbols`` means the criterion named no
    resolvable artifact (F2): it is NOT skipped — it must be carried by a declared test
    that discriminates, or the claim is blocked (:func:`_criterion_unresolved`).
    """

    index: int
    statement: str
    files: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass
class LeafOutcome:
    """The two facts that matter — what the run CLAIMED and how it stopped — plus the
    evidence needed to audit the loop's honesty.

    ``claimed`` is True only if the run's own tests exited 0 AND (when an ``iv``
    producer was injected) a fresh independent test FAILED on the pre-run source and
    PASSED on the final source. ``stop_reason`` is the single explicit stop
    (:data:`STOP_REASONS`); ``exhaustion_reason`` keeps the human-readable detail.
    ``wasted_escalations`` surfaces refusals that were only visible in the
    process-global ledger before. ``test_rewrites`` / ``own_test_mutated`` record a
    judge-authorized replacement of the run's own test; a green that follows one is
    ``green-after-test-rewrite`` and never claimed. ``claimed_basis`` records whether
    the claim rested on the run's own test alone or on the own test plus the
    independent test; ``iv_verdicts`` carries every independent-test evaluation and
    the last verdict's source, node ids, and both gate reports for audit.
    ``iv_attempts``/``iv_repairs`` count the independent-test mechanism's cost (every
    evaluated test, and every bounded one-shot repair of a defective verdict).
    """

    claimed: bool  # True ONLY if the run's own pytest exited 0
    signal: str  # green | green-after-test-rewrite | honest-failure | exhausted | handover | bubble
    attempts: list[Attempt]
    calls: int
    wall_s: float
    self_test: str | None
    questions: list[Question]
    exhausted: bool
    exhaustion_reason: str
    layers_used: list[str]
    stop_reason: str = ""
    wasted_escalations: list[Escalation] = field(default_factory=list)
    test_rewrites: int = 0
    own_test_mutated: bool = False
    needs_parent: bool = False  # a spec bubble: the parent owns the next move
    judge_verdicts: list[JudgeVerdict] = field(default_factory=list)  # every attribution,
    # raw + coerced, for calibrating the judge itself (also attached to its Attempt)
    claimed_basis: str = "own-test"  # "own-test" | "own-test+independent-test"
    # The independent test the last IV evaluation produced, its node ids, both gate
    # reports, and every verdict (for audit). ``independent_test_reason`` names why the
    # last independent test stopped a claim ("" once one approved).
    independent_test: str = ""
    independent_test_path: str = ""
    independent_test_node_ids: list[str] = field(default_factory=list)
    iv_original_gate: GateReport | None = None
    iv_final_gate: GateReport | None = None
    iv_verdicts: list[IndependentTestVerdict] = field(default_factory=list)
    independent_test_reason: str = ""
    # Ticket 17 round 8: the cost of the independent-test mechanism. ``iv_attempts``
    # counts every independent test that reached the two gates (first evaluations +
    # bounded repairs); ``iv_repairs`` counts the one-shot re-asks a defective verdict
    # (``independent-test-not-red`` / ``independent-test-not-discriminating`` /
    # ``independent-test-incomplete-coverage`` / ``independent-test-unobserved``)
    # triggered. Both land in the persisted run record so the mechanism's price is
    # measurable.
    iv_attempts: int = 0
    iv_repairs: int = 0
    # Ticket 17 rounds 10-11: the acceptance-criteria discrimination evidence from the
    # LAST independent-test verdict. ``iv_criteria_count`` is the extracted criteria
    # count (0 = none extracted); ``iv_criteria`` carries, for every index, the explicit
    # node ids plus the selection's original/final collected count and failures and the
    # reason it failed; ``iv_covered_indices`` are the indices whose selection
    # discriminated, ``iv_uncovered_indices`` the ones with no matching node, and
    # ``iv_shared_node_ids`` the node ids selected for more than one criterion.
    iv_criteria_count: int = 0
    iv_criteria: list[CriterionEvidence] = field(default_factory=list)
    iv_covered_indices: list[int] = field(default_factory=list)
    iv_uncovered_indices: list[int] = field(default_factory=list)
    iv_shared_node_ids: list[str] = field(default_factory=list)
    # Every write-guard action (ticket 17 round 5): a refused self-test/source write or
    # a normalized landing spot. Persisted in the run record so a forged-green attempt
    # is visible after the fact.
    refusals: list[str] = field(default_factory=list)
    # Every gate report anomaly seen (ticket 17 F1): a missing/unparsable pytest report,
    # a report without the per-run canary, a report that contradicts the exit status.
    # A gate with an anomaly is RED and the detail lands here and in the run record.
    gate_anomalies: list[str] = field(default_factory=list)
    # Ticket 19 round 2 (F5): every envelope step that stayed malformed past its bounded
    # retries. A malformed step no longer ends the node — it consumes its calls, is
    # recorded here, and the loop continues (bounded by the call budget / attempt cap /
    # ladder stops).
    malformed_steps: list[str] = field(default_factory=list)
    # Ticket 19 round 3 (FIX 2): how many judge consultations ended in the deterministic
    # "attribution unavailable" fallback (a judge that stayed malformed past
    # :data:`JUDGE_RETRIES`). The node then continues on the existing red path and makes
    # no further judge call for the same attempt.
    judge_unavailable: int = 0
    # Ticket 19 B/C: REVIEW-BASED verification. ``verification_basis`` is "test" when the
    # claim could rest on the run's own discriminating test, or "review" when no test could
    # carry verification (the test was green on arrival past the bounded re-ask, the judge's
    # test_wrong label survived a bounded repair that could not discriminate, or the test
    # path was unwritable) so a fresh-context reviewer of the final diff is mandatory.
    # ``review_verdicts`` keeps every verdict; ``review_verdict`` is the last (or None).
    verification_basis: str = "test"
    review_verdicts: list["ReviewVerdict"] = field(default_factory=list)
    review_verdict: "ReviewVerdict | None" = None
    # Ticket 19 E: per-criterion artifact coverage of the final diff. ``coverage`` is one
    # record per acceptance criterion; ``coverage_missing`` flattens the artifacts that
    # are named by a criterion but untouched by the run (a claim blocker). Ticket 19
    # round 2 (F2): ``coverage_unresolved`` records the criteria that named no artifact
    # and had no declared discriminating test to carry them (a distinct claim blocker).
    coverage: list[RequirementCoverage] = field(default_factory=list)
    coverage_missing: list[str] = field(default_factory=list)
    coverage_unresolved: list[str] = field(default_factory=list)
    # Ticket 19 D: the declared test-case contract failures (missing/unpassed file or
    # node names) after the bounded repair; a claim blocker.
    test_case_problems: list[str] = field(default_factory=list)
    # Ticket 19 A: an environment_broken judge verdict parks the node needs-user without
    # burning the remaining budget (distinct from a spec bubble, which needs the parent).
    needs_user: bool = False
    # Ticket 20: the explicit verification record EVERY node that wrote code carries, with
    # an ORDERED strength tier (test > review > none+reason), the plan's declaration, and
    # any recorded best-effort downgrade. ``None`` when the node wrote no code.
    verification: VerificationRecord | None = None
    #: Ticket 20: True when the terminal evidence is a VERIFIED tier (``test`` or
    #: ``review``). A ``none+reason`` claim is UNVERIFIED and never mixed into verified
    #: claims by the scoring layer.
    verified: bool = False
    #: Ticket 20: the four-way separation the scoring layer reads — ``verified-success``,
    #: ``unverified-success``, ``verified-failure``, or ``unverified-failure``.
    claim_status: str = ""


@dataclass(frozen=True)
class JudgeRequest:
    """Everything an independent attribution judge may see (never grader paths).

    The blind view: the goal, the acceptance criteria, the run's OWN test file, the
    failing test output, and the current source (source-only, never a grader path).
    """

    goal: str
    failure: str
    test_path: str
    test_content: str
    files: dict[str, str]
    acs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        reject_node_record_fields(self)


@dataclass(frozen=True)
class IndependentTestRequest:
    """Everything the independent test author may see — never a grader path, never the
    run's own test.

    Only the files the run changed: their pre-run (``original``) and post-run
    (``final``) source. The author writes a test that must FAIL on the original and PASS
    on the final; it never learns what the run's own test asserts.
    """

    goal: str
    acs: list[str]
    original: dict[str, str]
    final: dict[str, str]
    # Bounded-repair evidence (ticket 17 round 8): a rejected test's source and the
    # verdict that rejected it. Set only on the ONE re-ask; empty on a first call, so
    # the producer can tell a first attempt from its bounded repair.
    previous_test: str = ""
    repair_reason: str = ""
    repair_detail: str = ""
    # Ticket 17 round 10: on a discrimination repair, the criterion indices the rejected
    # test got wrong (uncovered or not discriminating). Empty on a first call and on the
    # other repair reasons.
    offending_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class IndependentTestCandidate:
    """The independent test the model wrote: a path and its complete source."""

    path: str
    content: str
    raw: str = ""


@dataclass(frozen=True)
class IndependentTestVerdict:
    """The DETERMINISTIC two-gate verdict on one independent test.

    ``approved`` is True only when the test FAILED on a private copy of the pre-run
    source (``original_gate``) and PASSED on a private copy of the final source
    (``final_gate``) with the canary and expected node ids satisfied, AND every
    acceptance criterion's own explicit node-id selection discriminated (rounds 10-11).
    ``reason`` names a rejection: ``independent-test-not-red`` (the whole file passed on
    the original — vacuous), ``independent-test-unobserved`` (no trustworthy report could
    be produced), ``independent-test-not-discriminating`` (a criterion's selection still
    passed on the original), ``independent-test-incomplete-coverage`` (a criterion has no
    matching node), ``independent-test-shared-coverage`` (one node id is selected for
    more than one criterion), or ``independent-test-red-on-final`` (the fix is still
    wrong). ``content`` and the gate reports are kept for the audit trail; ``output`` is
    the failure context the loop feeds into the next attempt.

    Ticket 17 rounds 10-11 record the discrimination evidence on every verdict:
    ``criteria_count`` is the number of extracted acceptance criteria (0 means the list
    was empty and the requirement was skipped — :attr:`coverage_skipped`); ``criteria``
    carries one :class:`CriterionEvidence` per index; ``covered_indices`` are the indices
    whose selection discriminated, ``uncovered_indices`` the ones with no matching node,
    and ``shared_node_ids`` the node ids selected for more than one criterion;
    ``offending_indices`` is the flattened set the repair must fix.
    """

    approved: bool
    reason: str = ""
    detail: str = ""
    path: str = ""
    # The path the model asked for and whether the harness had to relocate it to a
    # path pytest actually collects (round 8, parameter-layer normalization).
    requested_path: str = ""
    relocated: bool = False
    content: str = ""
    node_ids: tuple[str, ...] = ()
    original_gate: GateReport | None = None
    final_gate: GateReport | None = None
    output: tuple[str, ...] = ()
    raw: str = ""
    # Ticket 17 round 10: the acceptance-criteria discrimination evidence.
    # ``criteria_count`` is the extracted AC count (0 ⇒ the requirement is skipped);
    # ``criteria`` is one deterministic per-index discrimination record.
    criteria_count: int = 0
    criteria: tuple[CriterionEvidence, ...] = ()
    covered_indices: tuple[int, ...] = ()
    uncovered_indices: tuple[int, ...] = ()
    offending_indices: tuple[int, ...] = ()
    shared_node_ids: tuple[str, ...] = ()

    @property
    def coverage_skipped(self) -> bool:
        """True when there were no extracted acceptance criteria to cover."""
        return self.criteria_count == 0


@dataclass(frozen=True)
class ReviewRequest:
    """Everything the mandatory REVIEW-BASED verifier may see (ticket 19 B): the goal,
    the acceptance criteria, and the final diff of the files the run changed — never a
    grader path and never the run's own test source. ``reason`` records WHY review
    replaced the test (no red target / a non-discriminating repaired test / an
    unwritable test path)."""

    goal: str
    acs: list[str]
    original: dict[str, str]
    final: dict[str, str]
    reason: str = ""
    #: Ticket 20 (item 1): the review ANGLE this call asks about (one fresh call per
    #: angle, its own fixed prompt); the driver builds the angle-specific question from it.
    angle: str = ""

    def __post_init__(self) -> None:
        reject_node_record_fields(self)


@dataclass(frozen=True)
class ReviewVerdict:
    """A fresh-context reviewer's verdict on ONE review angle (tickets 19 B / 20).

    ``grade`` is one of the five ORDINAL :data:`REVIEW_GRADES` (``definitely-ok`` +2 …
    ``definitely-problematic`` -2); ``angle`` says which angle it answers. A POSITIVE
    grade is honoured ONLY when ``evidence`` names a concrete changed artifact (the
    deterministic filter, :func:`apply_review_filter}), so a bare "looks good" cannot
    carry a claim. ``approved`` is the derived boolean (``grade`` is positive). ``detail``
    is the human-readable detail (the reviewer's own comment/counterexample) and ``raw``
    the unedited verdict.
    """

    angle: str = ""
    grade: str = "uncertain"
    evidence: str = ""
    detail: str = ""
    raw: str = ""
    coerced: bool = False
    coercion_reason: str = ""

    @property
    def approved(self) -> bool:
        """True only for a POSITIVE grade (``probably-ok`` or ``definitely-ok``)."""
        return self.grade in POSITIVE_REVIEW_GRADES


@dataclass(frozen=True)
class VerificationRecord:
    """The explicit verification a node that WROTE CODE carries (ticket 20).

    ``tier`` is one of the ORDERED :data:`VERIFICATION_TIERS` (``test`` > ``review`` >
    ``none``): a real discriminating test, one or more independent fresh-context reviews,
    or neither with a REQUIRED written reason. ``reason`` is the written justification
    for the ``none`` tier and ``reason_problem`` is the deterministic check's verdict on
    it (empty when the reason is acceptable). ``required``/``review_angles``/
    ``review_level``/``best_effort`` echo the plan's declaration; ``downgraded``/
    ``downgrade_reason`` record a best-effort claim at a weaker tier than the plan
    required. ``reviews`` keeps every per-angle review verdict (with its grade and
    evidence) and ``review_score`` is their weighted sum.
    """

    wrote_code: bool
    tier: str
    reason: str = ""
    reason_problem: str = ""
    reviews: tuple[ReviewVerdict, ...] = ()
    review_angles: tuple[str, ...] = ()
    review_level: str = DEFAULT_REVIEW_LEVEL
    review_score: int = 0
    required: str = "any"
    best_effort: bool = False
    downgraded: bool = False
    downgrade_reason: str = ""

    def __post_init__(self) -> None:
        reject_node_record_fields(self)

    @property
    def verified(self) -> bool:
        """True only for a VERIFIED tier (``test`` or ``review``)."""
        return self.tier in ("test", "review")

    @property
    def reason_ok(self) -> bool:
        """True only when the ``none`` tier's written reason passed the check."""
        return self.reason_problem == ""


@dataclass(frozen=True)
class Escalation:
    """One ladder decision: which rung, which layer, and whether it is wasted."""

    strategy: str | None
    layer: str
    wasted: bool
    reason: str
    detail: str = ""


# ---------------------------------------------------------------------------
# escalation (fixed step 3)
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _same_attempt(a: Attempt, b: Attempt) -> bool:
    return (
        a.failure_signature == b.failure_signature
        and sorted(a.touched_files) == sorted(b.touched_files)
        and _norm(a.claimed_delta) == _norm(b.claimed_delta)
    )


def _is_repeat(history: Sequence[Attempt], strategy: str) -> bool:
    """A re-run of ``strategy`` that adds nothing new.

    Only a ``novel`` verdict (a genuinely new failure signature or file set) earns
    another run of the same rung. A ``same`` verdict claimed no new idea, and an
    ``undecided`` verdict is an UNVERIFIED novelty claim — the model's own word is
    never trusted alone (DESIGN §10.4) — so both refuse the repeat (the T-31 defect:
    nine identical retries). A judge-authorized test rewrite is recorded as a real
    attempt, so an identical repeated rewrite is refused here too.
    """
    if not history:
        return False
    last = history[-1]
    if last.strategy != strategy or last.verdict == "novel":
        return False
    if last.verdict == "undecided":
        return True
    if len(history) < 2:
        return True
    return _same_attempt(last, history[-2])


def escalate(
    history: Sequence[Attempt],
    rung: int,
    *,
    excerpts: Sequence[str] = (),
    repo_files: Mapping[str, str] | None = None,
) -> Escalation:
    """Decide the next rung. An escalation that neither adds information nor shrinks
    the unit is NOT executed — it is returned as ``wasted`` and the ladder advances.

    L1–L5 all purport to ADD information (samples, guided decomposition, deeper
    exploration, deterministic diagnosis, independent review). The two ways that
    promise can fail: a verbatim repeat of the previous attempt (refused), or an L4
    diagnosis that surfaces nothing the attempt did not already carry.
    """
    if rung >= len(LADDER):
        return Escalation(None, "", True, "ladder exhausted: no rung left")
    strategy = LADDER[rung]
    layer = STRATEGY_LAYER[strategy]
    if _is_repeat(history, strategy):
        return Escalation(strategy, layer, True,
                          "identical attempt refused: same signature/files/claim")
    if strategy == "L4-rule-diagnosis":
        findings = diagnose_test_output(list(excerpts), dict(repo_files or {}))
        if not findings:
            return Escalation(strategy, layer, True, "L4 diagnosis surfaced nothing new")
        return Escalation(strategy, layer, False, f"L4 diagnosis: {len(findings)} finding(s)",
                          detail="; ".join(f"{f.code}: {f.message}" for f in findings[:3]))
    return Escalation(strategy, layer, False, f"{strategy} adds information")


# ---------------------------------------------------------------------------
# deterministic path / write guards (blind gate)
# ---------------------------------------------------------------------------


def _env_path(env: Any) -> str:
    """The envelope's ``file_path`` as a real string, or "" when it is absent.

    Ticket 18 P0: a bare ``unable`` self-test envelope leaves the payload field at the
    ``REQUIRED`` (:class:`harness.envelopes._Missing`) sentinel, and that non-string
    sentinel used to reach a ``Path(...)`` probe and crash the loop. A non-string path
    is never a usable path, so it is reported as absent here and takes the ordinary
    honest self-test refusal instead of raising.
    """
    value = getattr(env, "file_path", "")
    return value if isinstance(value, str) else ""


def _escapes_repo(rel: Any) -> bool:
    if not isinstance(rel, str):
        return True                     # a non-string path is never a usable in-repo path
    path = Path(rel)
    return path.is_absolute() or ".." in path.parts


def _canonical_write_path(rel: str) -> str | None:
    """Canonical repo-relative spelling of ``rel`` for the write-boundary check.

    POSIX ``normpath`` collapses ``./`` and internal ``.``/``..`` so a declared
    boundary cannot be evaded with a path alias; an absolute/escaping/empty path is
    ``None`` (already refused elsewhere as a logic escape).
    """
    text = (rel or "").strip()
    if not text or text.startswith(("~", "/")):
        return None
    norm = posixpath.normpath(text)
    if norm in ("", ".", "..") or norm.startswith(("../", "/")):
        return None
    return norm


def _write_shape_problem(rel: str, workdir: Path) -> str:
    """Why ``rel`` cannot be written as a file in ``workdir`` ("" when it can).

    A write target is a PARAMETER: a schema-valid envelope naming an existing
    directory (``"pkg"``, ``"pkg/"``, ``"."``) or a path under an existing file
    (``"pkg/calc.py/x.py"``) would otherwise raise ``IsADirectoryError`` /
    ``FileExistsError`` from ``Path.write_text``/``mkdir`` — outside the bounded
    request wrapper, which crashed a real driver run.

    Ticket 17 F3: the same schema-valid envelope can carry a path the FILESYSTEM
    itself refuses — an embedded NUL byte (``ValueError``) or an over-long file name
    (``OSError`` ENAMETOOLONG) is raised from the very ``Path.is_dir`` probe below.
    Both are caught here and reported as the honest write-shape problem, so neither
    the self-test nor the implementation path can crash.
    """
    if not rel or not isinstance(rel, str) or _escapes_repo(rel):
        return ""                       # path-escape is a logic refusal, handled elsewhere
    target = workdir / rel
    try:
        if target.is_dir():
            return "target is an existing directory"
        parent = target.parent
        while parent != workdir and parent != parent.parent:
            if parent.is_file():
                return "a path component is an existing file"
            parent = parent.parent
    except (ValueError, OSError) as exc:
        # ValueError: embedded NUL byte. OSError: ENAMETOOLONG / EACCES / ... — the
        # filesystem refuses the name itself, which no amount of mkdir can fix.
        return f"unwritable path ({type(exc).__name__}: {exc})"
    return ""


def _new_test_problem(rel: str, spec: LeafSpec, workdir: Path) -> str:
    """Why ``rel`` may not be the run's own test path ("" when it may).

    The run's OWN test must be a NEW test path: a non-test path, test infrastructure
    (``tests/conftest.py``, pytest config, ``sitecustomize``), a module-shadow path
    (``json.py``), an existing file, or a path of the wrong shape are all refused here;
    the caller normalizes such a landing spot to a free test path.
    """
    if _escapes_repo(rel):
        return "escapes the repository"
    if rel in set(spec.grader_paths):
        return "grader-owned path"
    if is_test_infrastructure(rel):
        return "test infrastructure (grader-owned)"
    if not is_test_path(rel):
        return "not a test path"
    if shadowing_path(rel):
        return "a module-shadow path"
    shape = _write_shape_problem(rel, workdir)
    if shape:
        return shape
    if rel in spec.files or (workdir / rel).exists():
        return "already exists — never overwrite shipped files"
    return ""


def _source_write_problem(rel: str, spec: LeafSpec, self_test: str | None) -> str:
    """Why ``rel`` may not be written as an implementation file ("" when it may).

    The implementation seam excludes every :func:`harness.staging.owned_paths` path —
    a run may never write a test path, ``conftest.py``/pytest config/``sitecustomize``,
    or a module-shadow path that would subvert the interpreter's own imports.
    """
    if _escapes_repo(rel):
        return "escapes the repository"
    if rel in set(spec.grader_paths):
        return "grader-owned path"
    if self_test is not None and rel == self_test:
        return "the run's own test file (outside the implementation seam)"
    if owned_paths(rel):
        if is_test_infrastructure(rel):
            return "test infrastructure (grader-owned)"
        return "a test path (outside the implementation seam)"
    if shadowing_path(rel):
        return "a module-shadow path (would shadow an interpreter import)"
    if spec.write_boundary is not None:
        canon = _canonical_write_path(rel)
        boundary = {_canonical_write_path(b) for b in spec.write_boundary}
        if canon is None or canon not in boundary:
            return "outside the node's declared write boundary"
    return ""


class WriteShapeRefused(RuntimeError):
    """A write target the filesystem refuses (embedded NUL, ENAMETOOLONG, ...).

    Raised by :func:`_write` instead of leaking ``ValueError``/``OSError`` out of the
    loop; every caller routes it to the honest write-shape refusal / stop.
    """

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"{path}: {detail}")
        self.path = path
        self.detail = detail


def _write(workdir: Path, rel: str, content: str) -> Path:
    """Write ``rel`` under ``workdir``; the filesystem's own refusal is data.

    The callers already probe the shape with :func:`_write_shape_problem`; this catch
    is the second half of F3 (and covers anything that probe does not anticipate): a
    ``ValueError`` (embedded NUL byte) or ``OSError`` (over-long name, permissions)
    becomes :class:`WriteShapeRefused` instead of crashing the loop.
    """
    target = workdir / rel
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    except (ValueError, OSError) as exc:
        raise WriteShapeRefused(rel, f"unwritable path ({type(exc).__name__}: {exc})") from exc
    return target


def _read(workdir: Path, rel: str | None) -> str:
    if not rel:
        return ""
    path = workdir / rel
    return path.read_text() if path.is_file() else ""


def _repo_view(spec: LeafSpec, workdir: Path, extra: Sequence[str] = ()) -> dict[str, str]:
    view: dict[str, str] = {}
    for rel in sorted(set(spec.files) | set(extra)):
        path = workdir / rel
        if path.is_file() and not is_test_path(rel):
            view[rel] = path.read_text()
    return view


# ---------------------------------------------------------------------------
# ticket 19 E: per-requirement artifact coverage of the diff
# ---------------------------------------------------------------------------

#: Symbols a criterion may name: a backticked span, a dotted identifier
#: (``pkg.calc.result``), or a call (``result(...)``).
_SPAN = re.compile(r"`([^`]+)`")
_DOTTED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b")
_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")


def _symbol_candidates(text: str) -> set[str]:
    """Deterministic symbol tokens named by a criterion's text."""
    out: set[str] = set()
    for span in _SPAN.findall(text or ""):
        for token in re.split(r"[\s,]+", span.strip()):
            token = token.strip().strip("()")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", token or ""):
                out.add(token)
    out |= set(_DOTTED.findall(text or ""))
    out |= set(_CALL.findall(text or ""))
    return {token for token in out if len(token) >= 3}


def _word_present(symbol: str, text: str) -> bool:
    """Boundary-aware presence of a symbol's FINAL segment in ``text``."""
    segment = symbol.split(".")[-1]
    return bool(re.search(rf"(?<![0-9A-Za-z_]){re.escape(segment)}(?![0-9A-Za-z_])", text or ""))


#: Ticket 19 round 2 (F3): a cheap, DETERMINISTIC comment/whitespace stripper for
#: artifact coverage. It is deliberately not a parser — a line comment (``#`` to the end
#: of the line, throughout even inside a literal) and ALL whitespace are removed, so a
#: comment-only edit is not a change. Accepted residual: an unrelated-but-real edit (an
#: added import, a moved blank line that also changes code) still counts as a change.
_LINE_COMMENT = re.compile(r"#[^\n]*")


def _stripped(text: str | None) -> str:
    """``text`` with line comments and all whitespace removed (F3)."""
    return "".join(_LINE_COMMENT.sub("", text or "").split())


def _changed_files(workdir: Path,
                   baseline: Mapping[str, str | None]) -> dict[str, tuple[str | None, str]]:
    """The node's final diff: changed (or created) source files, original -> final.

    Ticket 19 round 2 (F3): two versions are the SAME file when their comment- and
    whitespace-stripped contents are equal, so a comment-only edit (which used to satisfy
    a criterion naming the file, and to make an already-present symbol look "covered") is
    not a change.
    """
    changed: dict[str, tuple[str | None, str]] = {}
    for rel, original in baseline.items():
        if is_test_path(rel):
            continue
        path = workdir / rel
        current = path.read_text() if path.is_file() else None
        if current is not None and _stripped(current) != _stripped(original):
            changed[rel] = (original, current)
    return changed


def _requirement_coverage(
    spec: LeafSpec,
    workdir: Path,
    baseline: Mapping[str, str | None],
) -> list[RequirementCoverage]:
    """Per-criterion ARTIFACT coverage of the final diff (ticket 19 E).

    For every acceptance criterion the artifacts its text names — file paths and symbols
    that actually exist in the injected view — are checked against the node's final diff.
    A named file that is untouched, or a named symbol absent from every added line, is
    ``missing``: the requirement was not implemented and the node may not claim. A
    criterion that names no resolvable artifact is recorded with an empty missing set
    (nothing could be checked).
    """
    from harness.envelopes import file_tokens

    available = set(spec.files) | set(spec.candidate_files) | set(spec.write_boundary or ())
    source_text = {rel: text for rel, text in spec.files.items()}
    changed = _changed_files(workdir, baseline)
    records: list[RequirementCoverage] = []
    for index, statement in enumerate(spec.acs, 1):
        files: list[str] = []
        for token in file_tokens(statement):
            canon = _canonical_write_path(token)
            if canon and canon in available and canon not in files and not is_test_path(canon):
                files.append(canon)
        symbols: list[str] = []
        for symbol in sorted(_symbol_candidates(statement)):
            # resolvable only when the symbol actually occurs in the injected source view
            if any(_word_present(symbol, text) for text in source_text.values()):
                if symbol not in symbols:
                    symbols.append(symbol)
        missing: list[str] = []
        for rel in files:
            if rel not in changed:
                missing.append(rel)
        # A symbol is covered when it appears in a CHANGED file's final content (F3: the
        # file must pass the comment/whitespace-stripped diff, so a symbol that already
        # existed in a file touched only by a comment is NOT covered). Checking only
        # ADDED lines would fail a criterion whose symbol was already declared but whose
        # behavior changed.
        changed_text = "\n".join(after for _, after in changed.values())
        for symbol in symbols:
            if not _word_present(symbol, changed_text):
                missing.append(symbol)
        records.append(RequirementCoverage(
            index=index, statement=statement, files=tuple(files),
            symbols=tuple(symbols), missing=tuple(missing)))
    return records


def _criterion_unresolved(c: RequirementCoverage) -> bool:
    """True when a criterion named no artifact the coverage rule can check.

    Ticket 19 round 2 (F2): such a criterion is NOT skipped. The claim path must carry it
    with a declared discriminating test (or review); nothing else can resolve it.
    """
    return not c.files and not c.symbols


def _declared_test_case_problems(
    report: GateReport | None,
    declared: Sequence[DeclaredTestCase],
) -> list[str]:
    """The declared test-case contract failures (ticket 19 D).

    Mechanically, from the machine-readable report: each declared file must collect, and
    every declared function name must be present as a collected node id AND pass. A
    missing file, a missing name, and a failing name are all distinct problems (the loop
    may repair them). The name match is exact on the node's final ``::`` segment, so
    ``test_ac1_goal`` never matches ``test_ac1_goal_extra``.
    """
    problems: list[str] = []
    if report is None or not report.observed:
        return ["no machine-readable report to verify the declared test cases"]
    passed, failed = list(report.passed_ids), list(report.failed_ids)
    for case in declared:
        prefix = f"{case.file}::"
        file_ids = [nid for nid in (*passed, *failed) if nid.startswith(prefix)]
        if not file_ids:
            problems.append(f"{case.ac_id}: declared test file {case.file} did not collect")
            continue
        for name in case.names:
            passed_name = any(nid[len(prefix):].split("::")[-1] == name for nid in passed)
            failed_name = any(nid[len(prefix):].split("::")[-1] == name for nid in failed)
            if failed_name:
                problems.append(f"{case.ac_id}: declared test {case.file}::{name} did not pass")
            elif not passed_name:
                problems.append(f"{case.ac_id}: declared test {case.file}::{name} was not collected")
    return problems


#: Ticket 19 round 2 (F2/F4): the AC index a declared case carries in its ``ac_id``
#: (``AC-1`` / ``ac1`` / ``AC_1`` ⇒ 1). Boundary-aware, so ``ac12`` never means 1.
_AC_ID_INDEX = re.compile(r"(?i)(?<![0-9A-Za-z])ac[-_ ]?(\d+)(?![0-9A-Za-z])")


def _declared_case_index(case: DeclaredTestCase) -> int | None:
    """The acceptance-criterion index a declared test case is attached to, or None."""
    match = _AC_ID_INDEX.search(case.ac_id or "")
    return int(match.group(1)) if match else None


async def _declared_case_discriminates(
    run_tests: Callable[..., Any], spec: LeafSpec, workdir: Path, case: DeclaredTestCase,
) -> bool:
    """True when a declared test DISCRIMINATES: RED on the pristine pre-run source.

    Ticket 19 round 2 (F2/F4): a criterion that names no artifact must be carried by a
    declared test that is RED on the pristine source (in a private copy) — a placeholder
    that only asserts ``True`` is green there and cannot carry it. The declared names are
    run through the existing report gate with those EXPLICIT node ids.
    """
    content = _read(workdir, case.file)
    if not content:
        return False
    node_ids = tuple(f"{case.file}::{name}" for name in case.names) or (case.file,)
    _, gate = await _run_iv_gate(run_tests, dict(spec.files), case.file, content,
                                 node_ids=node_ids)
    return gate is not None and gate.observed and not gate.green


def _erase_draft(workdir: Path, baseline: Mapping[str, str | None]) -> None:
    """M1: restore every draft the run wrote to its pre-implement state."""
    for rel, original in baseline.items():
        path = workdir / rel
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(original)


def _exit_code(res: ShapedResult | Any) -> int | None:
    return getattr(res, "exit", None)


def _is_green(res: ShapedResult | Any) -> bool:
    """Green requires a MACHINE-READABLE report, not an exit status (ticket 17 F1).

    A ``None`` exit (transport error), a policy-blocked result, and a non-int exit
    (a bare ``False`` is not an exit code) are all red; this mirrors
    ``ShapedResult.ok`` (``harness/exec.py``) and closed the ``policy_blocked=True,
    exit=0`` crack an independent verification pass found.

    The exit status alone is never enough: run-authored code executes inside the gate
    process and can force it to 0 before any test runs, so a gate result must carry a
    :class:`~harness.gate_report.GateReport` and that report must be green. A result
    with no report at all is red.
    """
    code = _exit_code(res)
    if not isinstance(code, int) or isinstance(code, bool) or code != 0:
        return False
    if getattr(res, "policy_blocked", False):
        return False
    gate = getattr(res, "gate", None)
    return gate is not None and gate.green


def _history_text(attempts: Sequence[Attempt]) -> str:
    lines = [
        f"- [{a.strategy}/{a.layer}] claim={a.claimed_delta!r} "
        f"sig={a.failure_signature} verdict={a.verdict}"
        for a in attempts[-6:]
    ]
    return "\n".join(lines)


def _mode(attempts: Sequence[Attempt]) -> str:
    """M2 first (keep the draft, ask "do you have a new idea?"); M1 once a ``same``
    or ``undecided`` verdict says the draft is stuck (erase and regenerate)."""
    if not attempts:
        return "M2"
    return "M2" if attempts[-1].verdict == "novel" else "M1"


def _claims_test_wrong(env: Any) -> bool:
    """The model's claim that its own TEST is wrong (trigger for the judge). A
    ``blocked`` implementation envelope means exactly that; the comment phrases are
    the fallback for models that answer with text instead of the status branch."""
    if getattr(env, "status", "") == "blocked":
        return True
    comment = (getattr(env, "comment", "") or "").lower()
    return any(phrase in comment for phrase in _TEST_BLAME_PHRASES)


#: Ticket 19 A: consecutive RED attempts in which the run materially changed the code
#: before the judge is consulted proactively (owner direction: K=2).
ATTRIBUTION_RED_K = 2


def _file_materially_changed(workdir: Path, baseline: Mapping[str, str | None], rel: str) -> bool:
    """True when the attempt changed ``rel`` relative to its pre-run content."""
    path = workdir / rel
    current = path.read_text() if path.is_file() else None
    if current is None:
        return False
    if rel not in baseline:
        return True
    return current != baseline[rel]


def _declared_case_artifacts(
    spec: LeafSpec, self_test: str, problems: Sequence[str]
) -> dict[str, str]:
    """The repair artifacts for a missing DECLARED test case (ticket 19 D)."""
    declared = "\n".join(
        f"{c.ac_id}: {c.file} :: {', '.join(c.names)}" for c in spec.test_cases)
    return {
        "goal": spec.goal,
        "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
        "declared_test_cases": declared,
        "current_test_path": self_test,
        "missing": "\n".join(problems),
    }


# ---------------------------------------------------------------------------
# independent judge: deterministic filter over the model's attribution
# ---------------------------------------------------------------------------

#: The canonical attribution domain (owner policy: implementation | tests | spec |
#: environment). A judge's label is mapped onto this before anything is credited.
ATTRIBUTIONS: tuple[str, ...] = ("implementation", "tests", "spec", "environment")

_TEST_FN = re.compile(r"\bdef\s+(test_[A-Za-z0-9_]+)")
_ASSERT = re.compile(r"\bassert\b\s+(.+)$")
_STRING_LITERAL = re.compile(r"(['\"])(.+?)\1")
_FAILED_TEST_ID = re.compile(r"::\s*([A-Za-z_][A-Za-z0-9_]*)")


def _test_anchors(request: JudgeRequest) -> set[str]:
    """Deterministic anchors that make a defect *about the test* rather than a vibe:
    the test function names, each assertion expression and its string-literal
    expectations, and the failing test ids named in the run's failing output. A bare
    numeric literal is deliberately NOT an anchor — the expected value also appears in
    a defect that blames the implementation, so it would let a mis-attribution through."""
    anchors: set[str] = set()
    content = request.test_content or ""
    for name in _TEST_FN.findall(content):
        anchors.add(_norm(name))
    for line in content.splitlines():
        match = _ASSERT.search(line)
        if not match:
            continue
        expr = match.group(1).split("#", 1)[0].strip().rstrip(":")
        if len(expr) >= 3:
            anchors.add(_norm(expr))
        for _, literal in _STRING_LITERAL.findall(expr):
            if len(literal) >= 3:
                anchors.add(_norm(literal))
    for name in _FAILED_TEST_ID.findall(request.failure or ""):
        anchors.add(_norm(name))
    return {a for a in anchors if a}


def _defect_names_the_test(defect: str, request: JudgeRequest) -> bool:
    normalized = _norm(defect)
    if not normalized:
        return False
    return any(anchor in normalized for anchor in _test_anchors(request))


def apply_judge_filter(verdict: JudgeVerdict, request: JudgeRequest) -> JudgeVerdict:
    """The DETERMINISTIC FILTER — never trust the model's word alone (ticket 19 A).

    A ``test_wrong`` label is honoured ONLY when the defect/reason is non-empty AND
    names the failing test function or an assertion/expectation of the run's own test;
    otherwise the label is dropped (coerced to ``implementation_wrong``) and the
    coercion is recorded (``coerced`` + ``coercion_reason``). An unknown attribution
    label is likewise coerced to ``implementation``. ``spec_wrong`` and
    ``environment_broken`` pass through: the loop's decision is dominant-first, and a
    bogus spec/environment claim only parks or bubbles, never claims.
    """
    verdict = normalize_judge_labels(verdict)
    labels = judge_labels(verdict)
    updates: dict[str, Any] = {}
    if not labels and verdict.attribution and (
            ATTRIBUTION_ALIASES.get(_norm(verdict.attribution)) is None):
        updates.update(implementation_wrong=True, coerced=True,
                       coercion_reason=(f"unknown attribution {verdict.attribution!r} "
                                        "coerced to implementation"))
    if verdict.test_wrong and not _defect_names_the_test(
            verdict.defect or verdict.reason, request):
        updates.update(test_wrong=False, coerced=True,
                       coercion_reason=("test_wrong without a defect naming the failing "
                                        "test or one of its assertions (deterministic filter)"))
    if updates:
        merged = verdict.model_copy(update=updates)
        remaining = judge_labels(merged)
        if not remaining:
            merged = merged.model_copy(update={"implementation_wrong": True})
            remaining = ("implementation_wrong",)
        merged = merged.model_copy(update={"attribution": summary_attribution(remaining)})
        return merged
    return verdict


def _plain_attribution(text: str) -> str:
    """Ticket 19 round 3 (FIX 2): the deterministic plain-text fallback parse.

    A judge that answers with prose instead of an envelope (or an oracle that returns a
    bare string) is mapped onto the canonical attribution domain by the FIRST canonical
    attribution word it names, word-boundary aware so ``latest`` never means ``test``.
    Returns "" when no attribution word is present, so the caller can keep the raw text
    and let :func:`apply_judge_filter` apply the conservative implementation default.
    """
    normalized = _norm(text)
    best: tuple[int, str] | None = None
    for token, canonical in ATTRIBUTION_ALIASES.items():
        match = re.search(rf"(?<![0-9a-z_]){re.escape(token)}(?![0-9a-z_])", normalized)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), canonical)
    return best[1] if best else ""


def _as_verdict(result: Any) -> JudgeVerdict:
    """Accept a structured verdict, a raw payload dict (single-label or multi-label), or
    a bare attribution string (hand-authored oracles in tests use the string form).

    Ticket 19 round 3 (FIX 2): a plain-text verdict — prose a judge produced instead of
    a parseable envelope — is parsed deterministically for its attribution word and
    carried as ``reason``/``defect`` so the existing :func:`apply_judge_filter` still
    decides whether the label is earned."""
    if isinstance(result, JudgeVerdict):
        return result
    if isinstance(result, Mapping):
        return JudgeVerdict(
            implementation_wrong=bool(result.get("implementation_wrong", False)),
            test_wrong=bool(result.get("test_wrong", False)),
            spec_wrong=bool(result.get("spec_wrong", False)),
            environment_broken=bool(result.get("environment_broken", False)),
            reason=str(result.get("reason", "")),
            evidence=str(result.get("evidence", "")),
            attribution=str(result.get("attribution", "")),
            defect=str(result.get("defect", "")),
            raw=str(result.get("raw", "")),
        )
    if isinstance(result, str):
        attribution = _plain_attribution(result) or result
        return JudgeVerdict(attribution=attribution, reason=result, defect=result,
                            raw=result)
    raise TypeError(
        f"judge returned {type(result).__name__}; expected a verdict, dict, or attribution")


async def _call_judge(attribution: Any, request: JudgeRequest) -> JudgeVerdict:
    """One judge call including verdict conversion — a module-level helper so it can be
    bound with :func:`functools.partial` (no loop-variable capture)."""
    return _as_verdict(await _maybe_await(attribution, request))


async def _maybe_await(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _review_request(
    spec: LeafSpec,
    workdir: Path,
    baseline: Mapping[str, str | None],
    reason: str,
    angle: str = "",
) -> ReviewRequest:
    """The blind review view for ONE angle: the goal, the ACs, and the ORIGINAL/FINAL
    source of exactly the files the run changed (never the run's own test, never a grader
    path). ``angle`` is the predefined angle the fresh-context call answers.

    Ticket 19 round 2 (F3, composed with F1): "changed" is judged on the comment- and
    whitespace-stripped contents, so a comment-only edit is not a changed file and cannot
    be cited as review evidence.
    """
    original = dict(spec.files)
    final = _repo_view(spec, workdir, tuple(baseline))
    changed = sorted(rel for rel in set(original) | set(final)
                     if _stripped(original.get(rel)) != _stripped(final.get(rel)))
    return ReviewRequest(
        goal=spec.goal, acs=list(spec.acs),
        original={rel: original.get(rel, "") for rel in changed},
        final={rel: final.get(rel, "") for rel in changed},
        reason=reason, angle=angle,
    )


def _evidence_names_an_artifact(evidence: str, request: ReviewRequest) -> bool:
    """True when the evidence names an artifact that REALLY appears in the diff.

    The deterministic filter for review (ticket 19 B). Round 2 (F1) closed the no-op
    bypass: a pass must name either a path that CHANGED in the node's original-vs-final
    diff, or a symbol that occurs in a changed file's final text. A bare line reference
    is no longer enough on its own — a line number can always be cited for a file that
    never moved — so an UNCHANGED tree can never carry a claim by any route. A line
    reference (``file.py:12`` / ``line 12``) is only ever honoured TOGETHER with a
    changed path, since that path is what the rest of this function accepts."""
    normalized = (evidence or "").lower()
    if not normalized.strip() or not request.final:
        return False
    for rel in request.final:
        for token in (rel.lower(), PurePosixPath(rel).name.lower()):
            if token and re.search(rf"(?<![0-9a-z_]){re.escape(token)}(?![0-9a-z_])", normalized):
                return True
    for symbol in _symbol_candidates(evidence):
        if any(_word_present(symbol, text) for text in request.final.values()):
            return True
    return False


def apply_review_filter(verdict: ReviewVerdict, request: ReviewRequest) -> ReviewVerdict:
    """The DETERMINISTIC review filter (ticket 19 B, extended to grades): evidence or no
    claim.

    A POSITIVE grade (``probably-ok``/``definitely-ok``) is honoured ONLY when its evidence
    names a concrete artifact that changed in the diff; otherwise the grade is coerced down
    to ``uncertain`` (0) and the coercion recorded, so the reviewer (the same weak model)
    can never carry a claim on its word alone and a no-op tree can never claim. A
    non-positive grade is left as it is (a negative grade is an action item; uncertain
    scores 0)."""
    if verdict.grade in POSITIVE_REVIEW_GRADES \
            and not _evidence_names_an_artifact(verdict.evidence, request):
        return replace(verdict, grade="uncertain", coerced=True,
                       coercion_reason=("positive review grade without evidence naming a "
                                        "changed artifact (deterministic filter)"))
    return verdict


def _coerce_review_grade(value: Any) -> str:
    """Map a model's grade word (or a legacy pass/fail) to one of the five ordinal grades."""
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
        if normalized in REVIEW_GRADE_RANK:
            return normalized
        if normalized in ("pass", "approved", "ok", "true", "yes"):
            return "probably-ok"
        if normalized in ("fail", "failed", "false", "no", "reject", "rejected"):
            return "probably-problematic"
    if isinstance(value, bool):
        return "probably-ok" if value else "probably-problematic"
    return "uncertain"


def _as_review_verdict(result: Any) -> ReviewVerdict:
    """Accept a structured verdict, a payload dict, or a bare pass/fail string.

    The grade is read from ``grade`` when present, else from a legacy ``verdict``/``approved``
    field, else from a bare pass/fail string; anything unrecognized is ``uncertain`` (0),
    never a positive claim."""
    if isinstance(result, ReviewVerdict):
        return result
    if isinstance(result, Mapping):
        if "grade" in result:
            grade = _coerce_review_grade(result.get("grade"))
        elif "verdict" in result:
            grade = _coerce_review_grade(result.get("verdict"))
        else:
            grade = _coerce_review_grade(result.get("approved", False))
        return ReviewVerdict(
            angle=str(result.get("angle", "")),
            grade=grade,
            evidence=str(result.get("evidence", "")),
            detail=str(result.get("detail", "")),
            raw=str(result.get("raw", "")),
        )
    if isinstance(result, str):
        return ReviewVerdict(grade=_coerce_review_grade(result), evidence=result,
                             raw=result)
    raise TypeError(
        f"review returned {type(result).__name__}; expected a verdict, dict, or grade")


async def _call_review(review: Any, request: ReviewRequest) -> ReviewVerdict:
    """One reviewer call including verdict conversion — a module-level helper so it can
    be bound with :func:`functools.partial`."""
    return _as_review_verdict(await _maybe_await(review, request))


def _as_iv_candidate(result: Any) -> IndependentTestCandidate:
    """Accept a structured candidate, a payload dict (``path``/``file_path`` +
    ``content``), or a model envelope carrying ``file_path``/``content``. Anything
    without usable content is malformed — never a claim (never claim unverified)."""
    if isinstance(result, IndependentTestCandidate):
        if not result.content:
            raise ValueError("independent test candidate carries no content")
        return result
    if isinstance(result, Mapping):
        content = str(result.get("content") or "")
        if not content:
            raise ValueError("independent test candidate carries no content")
        return IndependentTestCandidate(
            path=str(result.get("path") or result.get("file_path") or ""),
            content=content, raw=str(result.get("raw", "")))
    if getattr(result, "status", "ok") not in ("", "ok"):
        raise ValueError(
            f"independent test envelope status={getattr(result, 'status', 'unknown')!r}")
    content = getattr(result, "content", "")
    if isinstance(content, str) and content:
        return IndependentTestCandidate(path=getattr(result, "file_path", "") or "",
                                        content=content)
    raise ValueError(
        f"independent test returned {type(result).__name__}; expected a test file "
        "with non-empty content")


async def _call_iv(iv: Any, request: IndependentTestRequest) -> IndependentTestCandidate:
    """One independent-test authoring call including candidate conversion — a
    module-level helper so it can be bound with :func:`functools.partial`."""
    return _as_iv_candidate(await _maybe_await(iv, request))


def _iv_request(spec: LeafSpec, workdir: Path,
                baseline: Mapping[str, str | None]) -> IndependentTestRequest:
    """The blind independent-test view: the goal, the ACs, and the ORIGINAL and FINAL
    source of exactly the files the run changed. The run's own test and every grader
    path are filtered out by construction (``spec.files`` is source-only; ``_repo_view``
    drops test paths)."""
    original = dict(spec.files)
    final = _repo_view(spec, workdir, tuple(baseline))
    changed = sorted(rel for rel in set(original) | set(final)
                     if original.get(rel) != final.get(rel))
    return IndependentTestRequest(
        goal=spec.goal,
        acs=list(spec.acs),
        original={rel: original.get(rel, "") for rel in changed},
        final={rel: final.get(rel, "") for rel in changed},
    )


#: Verdicts that mean the independent TEST itself is defective (it cannot discriminate —
#: it passed on the original — it has no node for a criterion, it reuses one node for
#: several criteria, or it was never collected), not that the fix is wrong. Each earns
#: exactly ONE bounded re-ask of the same fresh-context producer with the verdict as
#: evidence (ticket 17 round 8). ``independent-test-not-discriminating``,
#: ``independent-test-incomplete-coverage`` and ``independent-test-shared-coverage``
#: (rounds 10-11) are TEST defects, so the test is re-asked with the offending indices
#: as evidence. ``independent-test-red-on-final`` is a FIX failure and is deliberately
#: NOT repaired: the loop continues with it as context.
_IV_REPAIRABLE: frozenset[str] = frozenset(
    {"independent-test-not-red", "independent-test-unobserved",
     "independent-test-not-discriminating", "independent-test-incomplete-coverage",
     "independent-test-shared-coverage"})


def _iv_repair_request(
    request: IndependentTestRequest, verdict: IndependentTestVerdict
) -> IndependentTestRequest:
    """The ONE bounded repair request: the same fresh-context call re-asked with the
    rejected test and the verdict that rejected it as explicit evidence.

    On a discrimination repair the offending criterion indices ride the request
    (``offending_indices``) so the re-ask names them, not just a prose detail."""
    return replace(request, previous_test=verdict.content,
                   repair_reason=verdict.reason, repair_detail=verdict.detail,
                   offending_indices=verdict.offending_indices)


#: pytest's default ``python_files``: collect ``test_*.py`` and ``*_test.py`` only.
_COLLECTIBLE_TEST_FILE = re.compile(r"^(?:test_.+|.+_test)\.py$")


def _iv_collectible(rel: str) -> bool:
    """True when pytest's DEFAULT collection rule would run ``rel`` as a test module.

    pytest's ``python_files`` default collects only ``test_*.py`` and ``*_test.py``; a
    file merely living under ``tests/`` (``tests/verify_pagination.py``) is never
    collected. The staging rule :func:`harness.staging.is_test_path` is broader (it owns
    everything under ``tests/``), so it must not be used as the collectability test.
    """
    return bool(_COLLECTIBLE_TEST_FILE.match(PurePosixPath(rel).name))


def _iv_safe_path(rel: str) -> str:
    """Normalize a candidate path into a COLLECTIBLE test file (parameter-layer
    tolerance): the harness, not the model, decides the collected file name.

    A model that names its test ``tests/verify_pagination.py`` (a valid ``tests/`` path
    by the staging rule, but NOT collectible by pytest's ``test_*.py``/``*_test.py``
    rule) used to be punished with ``independent-test-unobserved`` for the harness's own
    naming rule (ticket 17 round 8 defect). Any landing spot pytest would not collect —
    and any escaping or non-test path — is relocated to ``tests/test_independent.py``.
    The private copy is fully harness-controlled, so intent is unambiguous. Returns the
    path actually written; the caller compares it against the requested path to record
    the relocation.
    """
    rel = (rel or "").strip().lstrip("/")
    if rel and not _escapes_repo(rel) and is_test_path(rel) and _iv_collectible(rel):
        return rel
    return "tests/test_independent.py"


#: The boundary-aware index token (ticket 17 round 11). The discipline is the round-9
#: one: the token is ``ac<digits>`` and it only counts when the ``ac`` is not preceded
#: and the digits are not followed by another alphanumeric character, so ``ac1`` never
#: matches ``ac12``/``ac10``. Case-insensitive: ``AC1`` matches.
_INDEX_TOKEN = re.compile(r"(?<![0-9A-Za-z])ac(\d+)(?![0-9A-Za-z])", re.IGNORECASE)


def _node_criterion_indices(node_id: str, iv_path: str) -> tuple[int, ...]:
    """The criterion indices a node NAME carries, scoped to the independent test file.

    Only the part after ``<iv_path>::`` is matched (the node name) and only a
    boundary-aware index token counts, so a node belonging to another file, or one named
    ``test_ac12_thing`` for criterion 1, can never satisfy a criterion.
    """
    prefix = f"{iv_path}::"
    if not node_id.startswith(prefix):
        return ()
    name = node_id[len(prefix):]
    return tuple(sorted({int(match) for match in _INDEX_TOKEN.findall(name)}))


def _criterion_node_map(
    gate: GateReport, iv_path: str, criteria_count: int
) -> dict[int, tuple[str, ...]]:
    """The DETERMINISTIC index -> node-id map for criteria ``1..N`` (round 11).

    Derived from the FIRST full-file report (the whole-file red-on-original run): every
    independent-test node id — passed or failed — is bucketed by the boundary-aware
    indices its NAME carries. A node may land in several buckets, which is exactly the
    shared-coverage defect the caller detects; a criterion with no node keeps an empty
    tuple. ``criteria_count == 0`` yields an empty map (the requirement is skipped).
    """
    mapping: dict[int, list[str]] = {index: [] for index in range(1, criteria_count + 1)}
    passed, failed = _iv_scoped_ids(gate, iv_path)
    for node_id in (*passed, *failed):
        for index in _node_criterion_indices(node_id, iv_path):
            if index in mapping and node_id not in mapping[index]:
                mapping[index].append(node_id)
    return {index: tuple(ids) for index, ids in mapping.items()}


def _shared_node_ids(
    mapping: Mapping[int, Sequence[str]]
) -> dict[str, tuple[int, ...]]:
    """The node ids selected for MORE than one criterion (round 11).

    The per-criterion test sets must be DISJOINT: a node that serves several criteria
    ("one test per criterion") is a defect, not free coverage. Returns ``node id ->
    sorted indices`` for every shared node.
    """
    by_node: dict[str, list[int]] = {}
    for index, ids in mapping.items():
        for node_id in ids:
            by_node.setdefault(node_id, []).append(index)
    return {node_id: tuple(sorted(indices))
            for node_id, indices in by_node.items() if len(indices) > 1}


def _shared_coverage_detail(shared: Mapping[str, Sequence[int]]) -> str:
    """The readable shared-coverage evidence, listing every shared node id."""
    parts = [f"{node_id} serves {', '.join(f'AC{i}' for i in indices)}"
             for node_id, indices in sorted(shared.items())]
    return ("the independent test reuses one test node for several acceptance criteria "
            "(each criterion needs its own distinct node): " + "; ".join(parts))


def _mark_shared(
    criteria: Sequence[CriterionEvidence], shared: Mapping[str, Sequence[int]]
) -> list[CriterionEvidence]:
    """Mark every criterion served by a shared node with the shared-coverage reason.

    A criterion's set is disjoint or it is not: if ANY node id it was mapped to also
    serves another criterion, the whole criterion is offending (the caller then rejects
    the verdict with ``independent-test-shared-coverage`` and can repair it once).
    """
    shared_indices = {index for indices in shared.values() for index in indices}
    marked: list[CriterionEvidence] = []
    for criterion in criteria:
        if criterion.index not in shared_indices:
            marked.append(criterion)
            continue
        ids = sorted(node_id for node_id, indices in shared.items()
                     if criterion.index in indices)
        marked.append(replace(
            criterion, reason="shared-coverage",
            detail=f"AC{criterion.index} shares {', '.join(ids)} with another criterion"))
    return marked


def _iv_scoped_ids(
    gate: GateReport, iv_path: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A gate report's passed/failed node ids belonging to the INDEPENDENT test only.

    Ticket 17 round 10 (point 3): every per-criterion count is scoped to the file the
    harness wrote (``<iv_path>::``), so the per-run canary or any other collected file
    can never satisfy a criterion.
    """
    prefix = f"{iv_path}::"
    passed = tuple(nid for nid in gate.passed_ids if nid.startswith(prefix))
    failed = tuple(nid for nid in gate.failed_ids if nid.startswith(prefix))
    return passed, failed


def _criterion_evidence(
    index: int, node_ids: Sequence[str], original: GateReport | None,
    final: GateReport | None, iv_path: str,
) -> CriterionEvidence:
    """The deterministic per-criterion discrimination evidence (rounds 10-11).

    Both runs use the SAME EXPLICIT node ids derived for this criterion from the first
    full-file report. A criterion with no matching node is ``incomplete-coverage``; a
    node set that collects but PASSES on the original is ``not-discriminating`` (a
    placeholder that asserts ``True`` is green there and is therefore rejected); the set
    must be RED ON ORIGINAL and GREEN ON FINAL. A trustworthy report that was never
    produced is ``unobserved``. Counts are scoped to the requested node ids within the
    independent test's own file, so nothing else can satisfy the criterion.
    """
    selection = " ".join(node_ids)
    if not node_ids:
        return CriterionEvidence(
            index, selection, 0, 0, 0, 0, reason="incomplete-coverage",
            detail=f"no independent-test node carries the AC{index} index")
    if original is None or not original.observed or final is None or not final.observed:
        return CriterionEvidence(
            index, selection, 0, 0, 0, 0, reason="unobserved",
            detail=f"the AC{index} node selection produced no machine-readable report")
    requested = set(node_ids)
    o_passed, o_failed = _iv_scoped_ids(original, iv_path)
    f_passed, f_failed = _iv_scoped_ids(final, iv_path)
    o_passed = tuple(nid for nid in o_passed if nid in requested)
    o_failed = tuple(nid for nid in o_failed if nid in requested)
    f_passed = tuple(nid for nid in f_passed if nid in requested)
    f_failed = tuple(nid for nid in f_failed if nid in requested)
    o_collected, f_collected = len(o_passed) + len(o_failed), len(f_passed) + len(f_failed)
    if o_collected == 0:
        reason, detail = "incomplete-coverage", f"no independent-test node is selected for AC{index}"
    elif not o_failed:
        reason, detail = "not-discriminating", f"the AC{index} node selection still PASSES on the pre-run source"
    elif f_collected == 0:
        reason, detail = "incomplete-coverage", f"no independent-test node is selected for AC{index}"
    elif f_failed:
        reason, detail = "red-on-final", f"the AC{index} node selection still FAILS on the final source"
    else:
        reason, detail = "", ""
    return CriterionEvidence(index, selection, o_collected, len(o_failed),
                             f_collected, len(f_failed), reason, detail)


#: The per-criterion reasons in verdict PRIORITY order: a missing observation first,
#: then the structural SHARED-coverage defect, then the two repairable TEST defects (a
#: placeholder / a missing test), and finally the FIX failure, which is not repaired.
_CRITERION_REASON_ORDER: tuple[str, ...] = (
    "unobserved", "shared-coverage", "not-discriminating", "incomplete-coverage",
    "red-on-final")

_CRITERION_VERDICT_REASON: dict[str, str] = {
    "unobserved": "independent-test-unobserved",
    "shared-coverage": "independent-test-shared-coverage",
    "not-discriminating": "independent-test-not-discriminating",
    "incomplete-coverage": "independent-test-incomplete-coverage",
    "red-on-final": "independent-test-red-on-final",
}


def _classify_criteria(
    criteria: Sequence[CriterionEvidence],
) -> tuple[str, tuple[int, ...]]:
    """Pick the verdict reason from the per-criterion evidence (rounds 10-11).

    Returns ``(verdict_reason, offending_indices)``; ``("", ())`` means every criterion
    discriminated. A single verdict can only carry one reason, so the highest-priority
    defect wins (see :data:`_CRITERION_REASON_ORDER`) and its offending indices are the
    evidence the ONE repair is asked to fix.
    """
    for criterion_reason in _CRITERION_REASON_ORDER:
        offending = tuple(c.index for c in criteria if c.reason == criterion_reason)
        if offending:
            return _CRITERION_VERDICT_REASON[criterion_reason], offending
    return "", ()


def _criterion_detail(reason: str, offending: Sequence[int]) -> str:
    """The human-readable evidence for a per-criterion rejection (rounds 10-11)."""
    indices = ", ".join(f"AC{i}" for i in offending)
    if reason == "independent-test-not-discriminating":
        return ("the independent test does not pin the goal for every acceptance "
                f"criterion: the node selection for {indices} still PASSES on the pre-run source")
    if reason == "independent-test-incomplete-coverage":
        return ("the independent test does not exercise every acceptance criterion: "
                f"no independent-test node carries the index for {indices}")
    if reason == "independent-test-unobserved":
        return ("the independent test node selection for "
                f"{indices} produced no machine-readable report")
    return f"the independent test still FAILS on the final source for {indices}"


async def _run_iv_gate(
    run_tests: Callable[..., Awaitable[ShapedResult] | ShapedResult],
    tree: Mapping[str, str], iv_path: str, iv_content: str, *,
    node_ids: Sequence[str] | None = None,
) -> tuple[ShapedResult, GateReport | None]:
    """Run the existing report gate on a PRIVATE COPY of ``tree`` + the test.

    The copy is a fresh ``tempfile`` directory OUTSIDE the workdir, so the run never sees
    the independent test and the run's own test files are absent (the tree is the
    source-only view). The directory is removed before returning.

    Ticket 17 round 11: ``node_ids`` are the EXPLICIT pytest node ids restricting the run
    to one criterion's tests; the gate forces the per-run canary node id into the same
    argument list. The SAME node ids are used on the original and the final tree.
    """
    with tempfile.TemporaryDirectory(prefix="helpagent-iv-") as tmp:
        root = Path(tmp)
        for rel, text in tree.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        target = root / iv_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(iv_content)
        if node_ids is None:
            res = await _maybe_await(run_tests, root)
        else:
            res = await _maybe_await(run_tests, root, node_ids=node_ids)
    return res, getattr(res, "gate", None)


async def _repaired_test_is_red_on_pristine(
    run_tests: Callable[..., Any], spec: LeafSpec, test_path: str, test_content: str,
) -> bool:
    """Ticket 19 D: a repaired own test must still DISCRIMINATE — RED on the pristine
    pre-run source in a private copy. A test that passes there does not pin the goal, so a
    declared-case repair cannot smuggle a weakened test into a claim."""
    _, gate = await _run_iv_gate(run_tests, dict(spec.files), test_path, test_content)
    return gate is not None and gate.observed and not gate.green


async def evaluate_independent_test(
    candidate: IndependentTestCandidate,
    original_tree: Mapping[str, str],
    final_tree: Mapping[str, str],
    run_tests: Callable[..., Awaitable[ShapedResult] | ShapedResult],
    *,
    criteria_count: int = 0,
) -> IndependentTestVerdict:
    """The DETERMINISTIC claim condition (ticket 17 rounds 7-11): report gates.

    1. RED ON ORIGINAL (whole file): a private copy of the PRE-RUN source plus the test
       must run and FAIL. A test that passes there does not exercise the failure
       (vacuous) and is rejected with ``independent-test-not-red``.
    2. THE NODE MAP (round 11): the index -> node-id mapping for criteria ``1..N`` is
       derived from that FIRST full-file report with a boundary-aware, case-insensitive
       match on the test node NAME (``ac1`` never matches ``ac12``/``ac10``), scoped to
       the independent test file. A node id that serves more than one criterion is the
       ``independent-test-shared-coverage`` defect (the per-criterion sets must be
       DISJOINT).
    3. GREEN ON FINAL (whole file): a private copy of the FINAL source plus the SAME test
       must run and PASS with the canary and expected node ids satisfied.
    4. PER-CRITERION DISCRIMINATION (rounds 10-11): every criterion index
       ``1..criteria_count`` runs the EXPLICIT node ids derived for it in step 2 (plus
       the canary) through the SAME report gate on both trees. The node set must be RED
       ON ORIGINAL and GREEN ON FINAL; a set that stays green on the original is
       ``independent-test-not-discriminating``. A criterion with no matching node is
       ``independent-test-incomplete-coverage``. The test defects (incomplete / shared /
       not-discriminating) are repairable once.

    Both snapshots come from the blind source view (``run_tests`` in production is
    :func:`_default_run_tests`, which writes/requires the JUnit report and canary). A test
    the gate cannot observe (no report) is rejected as unobserved.

    The file the model names is a PARAMETER (round 8): it is normalized to a path pytest
    actually collects (:func:`_iv_safe_path`), and the verdict records the requested path
    plus whether a relocation happened. ``criteria_count=0`` (no extracted acceptance
    criteria) skips the per-criterion requirement.
    """
    requested_path = candidate.path or ""
    iv_path = _iv_safe_path(requested_path)
    relocated = requested_path != iv_path
    common = {"path": iv_path, "requested_path": requested_path, "relocated": relocated,
              "content": candidate.content, "raw": candidate.raw,
              "criteria_count": criteria_count}
    # 1. Whole-file RED ON ORIGINAL.
    orig_res, orig_gate = await _run_iv_gate(run_tests, original_tree, iv_path, candidate.content)
    orig_red = (orig_gate is not None and orig_gate.observed and not orig_gate.green
                and orig_gate.anomaly == "tests-failed")
    if not orig_red:
        if orig_gate is not None and orig_gate.observed and orig_gate.green:
            reason = "independent-test-not-red"
            detail = "the independent test PASSED on the pre-run source: it does not pin the goal"
        else:
            reason = "independent-test-unobserved"
            detail = (orig_gate.detail if orig_gate is not None else
                      "the independent test produced no machine-readable report on the pre-run source")
        return IndependentTestVerdict(
            approved=False, reason=reason, detail=detail, original_gate=orig_gate,
            output=tuple(getattr(orig_res, "excerpts", []) or ()), **common)

    # 2. THE NODE MAP: derive index -> explicit node ids from THIS first full-file report
    # (boundary-aware node-NAME match, scoped to the independent test file).
    mapping = _criterion_node_map(orig_gate, iv_path, criteria_count)
    shared = _shared_node_ids(mapping)

    # 3. Per-criterion RED ON ORIGINAL with the EXPLICIT node ids for that criterion (a
    # criterion with no matching node has nothing to run and stays incomplete-coverage).
    original_criteria: dict[int, GateReport | None] = {}
    for index in range(1, criteria_count + 1):
        node_ids = mapping[index]
        if not node_ids:
            original_criteria[index] = None
            continue
        _, gate = await _run_iv_gate(run_tests, original_tree, iv_path, candidate.content,
                                     node_ids=node_ids)
        original_criteria[index] = gate

    # 4. Whole-file GREEN ON FINAL.
    final_res, final_gate = await _run_iv_gate(run_tests, final_tree, iv_path, candidate.content)
    if final_gate is None:
        return IndependentTestVerdict(
            approved=False, reason="independent-test-red-on-final",
            detail="the independent test produced no machine-readable report on the final source",
            original_gate=orig_gate, final_gate=None,
            output=tuple(getattr(final_res, "excerpts", []) or ()), **common)
    if not final_gate.green:
        return IndependentTestVerdict(
            approved=False, reason="independent-test-red-on-final", detail=final_gate.detail,
            original_gate=orig_gate, final_gate=final_gate,
            node_ids=tuple(nid for nid in final_gate.passed_ids
                           if nid.startswith(f"{iv_path}::")),
            output=tuple(getattr(final_res, "excerpts", []) or ()), **common)

    # 5. Per-criterion GREEN ON FINAL with the IDENTICAL explicit node ids per index.
    evidence: list[CriterionEvidence] = []
    for index in range(1, criteria_count + 1):
        node_ids = mapping[index]
        if not node_ids:
            evidence.append(_criterion_evidence(index, (), None, None, iv_path))
            continue
        _, final_sel_gate = await _run_iv_gate(
            run_tests, final_tree, iv_path, candidate.content, node_ids=node_ids)
        evidence.append(_criterion_evidence(index, node_ids, original_criteria[index],
                                            final_sel_gate, iv_path))
    criteria = tuple(_mark_shared(evidence, shared))
    covered = tuple(c.index for c in criteria if not c.reason)
    uncovered = tuple(c.index for c in criteria if c.reason == "incomplete-coverage")
    shared_ids = tuple(sorted(shared))
    node_ids = tuple(nid for nid in final_gate.passed_ids if nid.startswith(f"{iv_path}::"))
    reason, offending = _classify_criteria(criteria)
    if reason:
        detail = (_shared_coverage_detail(shared)
                  if reason == "independent-test-shared-coverage"
                  else _criterion_detail(reason, offending))
        return IndependentTestVerdict(
            approved=False, reason=reason, detail=detail,
            original_gate=orig_gate, final_gate=final_gate, node_ids=node_ids,
            criteria=criteria, covered_indices=covered, uncovered_indices=uncovered,
            offending_indices=offending, shared_node_ids=shared_ids,
            output=tuple(getattr(final_res, "excerpts", []) or ()), **common)

    return IndependentTestVerdict(
        approved=True, node_ids=node_ids,
        original_gate=orig_gate, final_gate=final_gate,
        criteria=criteria, covered_indices=covered, uncovered_indices=(),
        output=tuple(getattr(final_res, "excerpts", []) or ()), **common)


async def _default_run_tests(workdir: Path, node_ids: Sequence[str] | None = None) -> ShapedResult:
    """The run's own gate: interpreter isolation + a machine-readable report.

    ``PYTHONSAFEPATH=1`` keeps the run-owned workdir off ``sys.path`` so a
    run-authored top-level module (``json.py`` / ``pytest.py`` / ``_pytest/``) cannot
    shadow an interpreter import and exit 0 before pytest runs; ``-p
    no:cacheprovider`` keeps pytest from writing a cache into the run's tree.

    Ticket 17 F1: the process exit status is not evidence. pytest is launched with
    ``--junitxml=<path in a private mkdtemp OUTSIDE the repository>`` and a small
    generated CANARY test (random token in its node id) next to the run's own tests;
    the gate is green only when the report exists, parses, holds the expected test
    file(s) and the canary all passed, and reports no failure or error. The exit code
    exposed to the loop is DERIVED from the report — 0 only on a green report.

    Ticket 17 round 11: ``node_ids`` are the EXPLICIT pytest node ids restricting the run
    to one acceptance criterion's tests (used for per-criterion discrimination). The
    per-run canary node id is forced into the same argument list so the report still
    carries this run's evidence; nothing else runs.
    """
    workdir = Path(workdir)
    shadows = shadowing_paths(workdir)
    if shadows:
        # The workdir is on PYTHONPATH so a legitimate test can import its package;
        # that makes a shadow file decisive, so the gate refuses to run at all.
        from harness.gate_report import GateReport
        detail = "workdir holds an import shadow: " + ", ".join(shadows)
        return ShapedResult(
            command=["python3", "-m", "pytest", "-q"], exit=1, verdict="gate_refused",
            excerpts=[detail],
            gate=GateReport(report_path="", process_exit=None, canary="",
                            expected_files=(), n_tests=0, n_failed=0, n_errors=0,
                            passed_ids=(), failed_ids=(), missing=(), observed=False,
                            anomaly="shadow-file-present", detail=detail))
    # Expected test files: the run's own (staging withheld every grader test, so the
    # only test files in the workdir are the ones the run wrote).
    expected = _workdir_test_files(workdir)
    token = canary_token()
    canary_dir = "tests"
    canary_file = workdir / canary_path(token, canary_dir)
    report_path = private_report_path()
    # A neutral config + pinned rootdir: a workdir nested under the repository would
    # otherwise inherit the repository's own pytest configuration, which changes the
    # report's file paths (rootdir-relative) and silently breaks expected-file and
    # canary matching — a real false-negative found by a live run (T-02, 2026-09-29).
    neutral_ini = report_path.parent / "gate.ini"
    neutral_ini.write_text("[pytest]\n")
    canary_file.parent.mkdir(parents=True, exist_ok=True)
    canary_file.write_text(canary_source(token))
    target_args: list[str] = []
    if node_ids is not None:
        # EXPLICIT node ids only: pytest runs exactly the criterion's tests plus the
        # canary (whose node id is named explicitly), so nothing else can run or satisfy
        # a criterion. The harness still scopes its counts to the independent test file.
        target_args = [*node_ids, canary_node_id(token, canary_dir)]
    try:
        res = await k_exec(
            ["python3", "-m", "pytest", "-q", *PYTEST_ISOLATION_ARGS,
             "-c", str(neutral_ini), "--rootdir=.", *target_args, *JUNIT_FAMILY_ARGS,
             f"--junitxml={report_path}"],
            workdir, provenance="kernel", extra_env=gate_env(workdir))
    finally:
        canary_file.unlink(missing_ok=True)
    gate = evaluate_gate(report_path, canary=token, expected_files=expected,
                         canary_dir=canary_dir, process_exit=res.exit)
    cleanup_report(report_path)
    res.gate = gate
    res.exit = 0 if gate.green else _nonzero_exit(res.exit)
    return res


def _nonzero_exit(code: Any) -> int:
    """A non-zero exit code for a red gate result (keeps a real code for the record)."""
    return code if isinstance(code, int) and not isinstance(code, bool) and code != 0 else 1


def _workdir_test_files(workdir: Path) -> tuple[str, ...]:
    """The run's own test files in ``workdir`` (repo-relative, sorted).

    Staging withholds every grader-owned test path, so a test file found here was
    written by the run: those are exactly the tests its own gate must have run.
    """
    return tuple(
        path.relative_to(workdir).as_posix()
        for path in sorted(workdir.rglob("*.py"))
        if path.is_file() and is_test_path(path.relative_to(workdir).as_posix())
    )


def _reason(history: Sequence[Attempt]) -> str:
    layers = ",".join(sorted(layers_tried(history)))
    return f"same-verdict tail across layers [{layers}]"


def _implement_artifacts(
    spec: LeafSpec,
    workdir: Path,
    esc: Escalation,
    attempts: Sequence[Attempt],
    last_excerpts: Sequence[str],
    self_test: str | None,
    mode: str,
    baseline: Mapping[str, str | None],
) -> dict[str, str]:
    return {
        "goal": spec.goal,
        "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
        "interfaces": "\n".join(f"- {i}" for i in spec.interfaces),
        "current_files": json.dumps(_repo_view(spec, workdir, tuple(baseline)),
                                    ensure_ascii=False),
        "self_test": _read(workdir, self_test),
        "failure_output": "\n".join(last_excerpts),
        "failure_history": _history_text(attempts),
        "escalation": esc.strategy or "",
        "escalation_detail": esc.detail,
        "retry_mode": mode,
    }


def _implement_question(mode: str, esc: Escalation) -> str:
    if mode == "M2":
        lead = ("You still hold your current draft. Do you have a new idea? Keep what "
                "works and change only what the failure requires. ")
    else:
        lead = ("Your previous draft was erased. Regenerate the target file from the "
                "failure history as your only intelligence. ")
    if esc.strategy == "L2-guided":
        lead += "First enumerate the ordered fix steps, then emit the complete file. "
    elif esc.strategy == "L3-deeper-explore":
        lead += "Explore the repository view more deeply before writing. "
    elif esc.strategy == "L4-rule-diagnosis":
        lead += f"Apply this deterministic diagnosis: {esc.detail}. "
    elif esc.strategy == "L5-review-judge":
        lead += "An independent review is watching; justify the change against the goal. "
    return (
        lead
        + "Emit the complete new content of ONE implementation file (file_path + content). "
        "Never edit a test file or a grader path — fix the source."
    )


def _self_test_artifacts(spec: LeafSpec) -> dict[str, str]:
    artifacts = {
        "goal": spec.goal,
        "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
        "interfaces": "\n".join(f"- {i}" for i in spec.interfaces),
        "repo_files": json.dumps(_source_view(spec), ensure_ascii=False),
    }
    if spec.test_cases:
        # Ticket 19 D: the plan DECLARES the test cases; the self-test must expose them.
        artifacts["declared_test_cases"] = "\n".join(
            f"{c.ac_id}: {c.file} :: {', '.join(c.names)}" for c in spec.test_cases)
    return artifacts


def _retry_self_test_artifacts(
    spec: LeafSpec, previous_path: str, previous_content: str
) -> dict[str, str]:
    artifacts = _self_test_artifacts(spec)
    artifacts["previous_test_path"] = previous_path
    artifacts["previous_test_content"] = previous_content
    artifacts["previous_test_result"] = "PASSED on arrival (exit 0): it does not pin the goal"
    return artifacts


def _source_view(spec: LeafSpec) -> dict[str, str]:
    return {rel: text for rel, text in spec.files.items()}


async def _request_write(model: Any, artifacts: dict[str, str], question: str) -> Any:
    return await llm_step(model, "write_test", artifacts=artifacts, question=question)


def _normalize_test_path(rel: str, spec: LeafSpec, workdir: Path) -> tuple[str, str]:
    """Parameter-layer tolerance (owner policy): a well-formed self-test envelope whose
    ONLY defect is where it lands is normalized deterministically, never refused.

    The grader's test files are withheld, so the model naturally reuses exactly those
    names (first live run: it asked for the grader's own ``tests/test_pagination.py``
    and the node died after one call). Intent is unambiguous — the step asks for a
    test — so the path is a parameter: relocate to a free test path. Returns
    ``(path, note)``; ``note`` is "" when nothing had to change.
    """
    if _escapes_repo(rel):
        return rel, ""                       # logic-level: never silently relocate out
    problem = _new_test_problem(rel, spec, workdir)
    if not problem:
        return rel, ""
    if problem == "escapes the repository":
        return rel, ""
    stem = Path(rel).stem or "self"
    suffix = Path(rel).suffix or ".py"
    parent = Path(rel).parent
    if not is_test_path(rel):
        parent = Path("tests")
    for n in range(0, 50):
        candidate = str(parent / (f"{stem}_leaf{suffix}" if n == 0 else f"{stem}_leaf{n}{suffix}"))
        if not _new_test_problem(candidate, spec, workdir):
            return candidate, f"{rel} -> {candidate} ({problem})"
    return rel, ""


def _relocate_self_test(env: Any, spec: LeafSpec, workdir: Path, emit: Any) -> str | None:
    """Return a usable self-test path for ``env``, normalizing a bad landing spot.

    Returns None when the envelope is unusable at the logic level (not ok, no path,
    or a path that escapes the repository).
    """
    path = _env_path(env)
    if getattr(env, "status", "unable") != "ok" or not path:
        return None
    kind, problem = _self_test_problem(env, spec, workdir)
    if not problem:
        return path
    normalized, note = _normalize_test_path(path, spec, workdir)
    if not note:
        return None
    emit("self_test_relocated", detail=note, requested=path, used=normalized)
    emit("tolerance_fired", aspect="self_test_path", requested=path, used=normalized)
    return normalized


def _self_test_problem(env: Any, spec: LeafSpec, workdir: Path) -> tuple[str, str]:
    """Classify a self-test envelope. Returns ``(ledger_kind, problem)``; ``problem``
    is "" when the envelope is a usable new test path."""
    path = _env_path(env)
    if getattr(env, "status", "unable") != "ok" or not path:
        return "self_test_unavailable", f"status={getattr(env, 'status', 'unknown')}"
    problem = _new_test_problem(path, spec, workdir)
    if problem:
        return "self_test_refused", problem
    return "", ""


async def _repair_test(
    model: Any, spec: LeafSpec, workdir: Path, self_test: str,
    last_excerpts: Sequence[str], previous: Any,
) -> Any:
    repair_request = (
        "Your own test is red; the failure was attributed to the TEST. Rewrite the "
        "complete test file from scratch so it correctly pins the goal. Reply with the "
        "new content. It must still FAIL on arrival against the current source."
    )
    return await _request_write(
        model,
        {
            "goal": spec.goal,
            "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
            "current_test": _read(workdir, self_test),
            "failure_output": "\n".join(last_excerpts),
            "prior_claim": getattr(previous, "comment", ""),
        },
        repair_request,
    )


# ---------------------------------------------------------------------------
# the leaf loop
# ---------------------------------------------------------------------------


async def run_leaf(
    model: Any,
    spec: LeafSpec,
    workdir: Path,
    budget: Budget,
    *,
    judge: Callable[[JudgeRequest], Awaitable[JudgeVerdict | dict | str] | JudgeVerdict | dict | str]
    | None = None,
    iv: Callable[[IndependentTestRequest], Any] | None = None,
    review: Callable[[ReviewRequest], Awaitable[ReviewVerdict | dict | str] | ReviewVerdict | dict | str]
    | None = None,
    run_tests: Callable[[Path], Awaitable[ShapedResult] | ShapedResult] | None = None,
    now: Callable[[], float] | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> LeafOutcome:
    clock = now or time.monotonic
    tests = run_tests or _default_run_tests
    # The judge is PROACTIVE (ticket 19 A): it is consulted when the run's own test
    # REPORTS RED, not only when the model volunteers a blame. ``attribution`` keeps the
    # old name for the seam; ``judge=None`` means no attribution and the conservative
    # default (the model's own "the test is wrong" claim is never credited).
    attribution = judge
    # ``review=None`` keeps the own-test-only path: when no test can carry verification
    # the node stops honestly instead of reviewing. A provided ``review`` producer makes
    # the REVIEW-BASED verification mandatory in that case (ticket 19 B).
    # ``iv`` stays available as an EXTRA LABEL (ticket 19 C): its verdict is recorded but
    # no longer the veto between the run and a claim.
    workdir = Path(workdir)
    started = clock()

    calls = 0
    attempts: list[Attempt] = []
    queue = QuestionQueue()
    rung = 0
    claimed = False
    claimed_basis = "own-test"
    signal = "honest-failure"
    exhaustion_reason = ""
    stop_reason = ""
    node_exhausted = False
    needs_parent = False
    needs_user = False
    self_test: str | None = None
    last_excerpts: list[str] = []
    baseline: dict[str, str | None] = {}
    wasted_escalations: list[Escalation] = []
    test_rewrites = 0
    judge_verdicts: list[JudgeVerdict] = []
    iv_verdicts: list[IndependentTestVerdict] = []
    last_iv_reason = ""
    iv_attempts = 0
    iv_repairs = 0
    refusals: list[str] = []
    gate_anomalies: list[str] = []
    # Ticket 19 round 2 (F5): every envelope step that stayed malformed past its retries.
    malformed_steps: list[str] = []
    # Ticket 19 round 3 (FIX 2): the judge is consulted at most ONCE per attempt and its
    # malformed fallback is counted here so the cost is auditable.
    judge_attempted = False
    judge_unavailable = 0
    # Ticket 19 A: consecutive RED attempts in which the run materially changed the code.
    # At K=2 the judge is consulted proactively (with the run's own test, the failing
    # output, and the diff as evidence).
    red_code_changes = 0
    # Ticket 19 B/C: REVIEW-BASED verification state. Ticket 20 adds ``reason`` mode (a
    # best-effort node with no test and no reviewer) and tracks the terminal tier.
    verification_basis = "test"
    review_verdicts: list[ReviewVerdict] = []
    review_reason = ""
    review_approved = False
    # Ticket 20: the claim tier the loop actually reached, the written ``none+reason``
    # justification and its deterministic check, and any best-effort downgrade.
    verification_tier = ""
    verification_reason = ""
    verification_reason_problem_text = ""
    verification_downgraded = False
    verification_downgrade_reason = ""
    verification_review_score = 0
    # Ticket 19 D/E coverage evidence from the LAST claim evaluation.
    coverage: list[RequirementCoverage] = []
    coverage_missing: list[str] = []
    coverage_unresolved: list[str] = []
    test_case_problems: list[str] = []
    test_case_repairs = 0
    attempt_cap = min(9, 3 * max(1, len(spec.files)))

    def emit(kind: str, **data: Any) -> None:
        note(kind, **data)
        if on_event is not None:
            on_event(kind, data)

    def spend() -> bool:
        nonlocal calls
        if budget.calls < 1:
            return False
        budget.take(1)
        calls += 1
        return True

    def can_afford(n: int) -> bool:
        """A multi-call escalation must check before it starts: a BudgetError must
        never escape mid-run (owner policy)."""
        return budget.calls >= n

    async def request_bounded(call: Callable[[], Awaitable[Any]], label: str,
                              retries: int = ENVELOPE_RETRIES
                              ) -> tuple[Any | None, str]:
        """Run one envelope request with a bounded malformed-output retry.

        No model failure may crash the leaf: a schema violation, a transport error, or
        any other exception raised by the model/envelope is retried up to ``retries``
        times (the JUDGE passes :data:`JUDGE_RETRIES`, ticket 19 round 3 FIX 2, so a
        malformed judge does not consume the generic envelope budget). Persistent
        failure returns reason ``"malformed-output"`` and RECORDS the step (ticket 19
        round 2, F5); an unaffordable retry returns ``"calls"``. The caller decides
        how to continue — this helper never stops the node.
        """
        for attempt in range(retries + 1):
            if not spend():
                return None, "calls"
            try:
                return await call(), ""
            except Exception as exc:  # noqa: BLE001 — a model failure is data, not a crash
                emit("envelope_malformed", step=label, attempt=attempt + 1,
                     detail=f"{type(exc).__name__}: {exc}")
        malformed_steps.append(label)
        return None, "malformed-output"

    async def request_envelope(call: Callable[[], Awaitable[Any]], label: str
                              ) -> tuple[Any | None, str]:
        """A bounded retry that NEVER ends the node (ticket 19 round 2, F5).

        Used where a run that cannot obtain the envelope has nothing safe to fall back
        on — the self-test: a test-less gate could green on its canary alone. It re-asks
        while ``request_bounded`` returns ``"malformed-output"``; because every try and
        every retry spends a call, the loop is bounded by the CALL BUDGET and the
        DEADLINE (both existing stops), so it cannot spin forever. Every malformed round
        is recorded (the ledger events from ``request_bounded`` plus one
        ``envelope_malformed_step``).
        """
        while True:
            if budget.expired(clock()):
                return None, "deadline"
            result, failure = await request_bounded(call, label)
            if not failure:
                return result, ""
            if failure == "calls":
                return None, "calls"
            emit("envelope_malformed_step", step=label)

    async def iv_verdict_for(
        request: IndependentTestRequest,
        original_tree: Mapping[str, str],
        final_tree: Mapping[str, str],
    ) -> tuple[IndependentTestVerdict | None, str]:
        """Author and evaluate ONE independent test (rounds 8-10).

        One bounded authoring call (malformed-output retries apply) plus the two
        deterministic gates and the deterministic per-criterion discrimination check.
        Returns ``(verdict, "")`` or ``(None, failure_reason)`` where ``failure_reason``
        is ``"calls"`` or ``"malformed-output"``. The independent test is an extra label
        (ticket 19 C), so either way it never stops the node: ``"calls"`` is left for the
        caller to surface and a malformed label is recorded.
        """
        candidate_test, failure = await request_bounded(
            partial(_call_iv, iv, request), "independent-test")
        if failure:
            return None, failure
        verdict = await _maybe_await(
            evaluate_independent_test, candidate_test, original_tree, final_tree, tests,
            criteria_count=len(request.acs))
        return verdict, ""

    def record_iv(verdict: IndependentTestVerdict) -> None:
        """Count, persist, and surface ONE independent-test verdict (rounds 8-10).

        The relocation is recorded exactly like the self-test's parameter-layer
        tolerance (``independent_test_relocated`` + ``tolerance_fired`` + a refusal
        note), so a naming slip is visible after the fact instead of silently becoming
        ``independent-test-unobserved``. An empty acceptance-criteria list is recorded
        as ``no_acceptance_criteria`` (round 9): the per-criterion requirement is not
        applied there. The per-criterion discrimination evidence rides the emitted
        event (round 10).
        """
        nonlocal iv_attempts
        iv_attempts += 1
        iv_verdicts.append(verdict)
        if verdict.relocated:
            emit("independent_test_relocated", requested=verdict.requested_path,
                 used=verdict.path)
            emit("tolerance_fired", aspect="independent_test_path",
                 requested=verdict.requested_path, used=verdict.path)
            refusals.append(f"{verdict.requested_path}: not collectible -> {verdict.path} "
                            "(independent test relocated)")
        if verdict.coverage_skipped:
            emit("no_acceptance_criteria", path=verdict.path,
                 detail="the extracted acceptance-criteria list is empty; "
                        "per-criterion discrimination is not required")
        emit("independent_test_verdict", approved=verdict.approved,
             reason=verdict.reason, path=verdict.path,
             criteria_count=verdict.criteria_count,
             covered_indices=list(verdict.covered_indices),
             uncovered_indices=list(verdict.uncovered_indices),
             offending_indices=list(verdict.offending_indices),
             shared_node_ids=list(verdict.shared_node_ids),
             criteria=[{"index": c.index, "selection": c.selection,
                        "original_collected": c.original_collected,
                        "original_failures": c.original_failures,
                        "final_collected": c.final_collected,
                        "final_failures": c.final_failures,
                        "reason": c.reason, "detail": c.detail}
                       for c in verdict.criteria],
             original_gate=(verdict.original_gate.anomaly
                            if verdict.original_gate is not None else None),
             final_gate=(verdict.final_gate.anomaly
                         if verdict.final_gate is not None else None),
             raw=verdict.raw)

    async def run_review(angle: str, reason: str
                         ) -> tuple[ReviewVerdict | None, str]:
        """Author and FILTER one fresh-context review of ONE angle (tickets 19 B / 20).

        The reviewer sees the goal, the ACs, and the changed files' original and final
        source — never a grader path and never the run's own test — and the fixed
        angle-specific prompt template (ticket 20, item 1). Each call is a SEPARATE
        fresh-context review (no shared history) for exactly one angle. The graded verdict
        is put through :func:`apply_review_filter`, so only a POSITIVE grade WITH concrete
        evidence naming a changed artifact can contribute to a claim. Returns
        ``(verdict, "")`` or ``(None, failure_reason)`` where ``failure_reason`` is
        ``"calls"`` or ``"malformed-output"``.
        """
        request = _review_request(spec, workdir, baseline, reason or review_reason, angle)
        raw, failure = await request_bounded(
            partial(_call_review, review, request), "review")
        if failure:
            return None, failure
        verdict = apply_review_filter(raw, request)
        if not verdict.angle:
            verdict = replace(verdict, angle=angle)
        review_verdicts.append(verdict)
        emit("review_verdict", angle=verdict.angle, grade=verdict.grade,
             approved=verdict.approved, evidence=verdict.evidence,
             detail=verdict.detail, coerced=verdict.coerced)
        if verdict.coerced:
            emit("review_coerced", reason=verdict.coercion_reason)
        return verdict, ""

    def _declared_review_angles() -> tuple[str, ...]:
        """The angles this node's review runs (ticket 20, item 1).

        The declared angles are filtered to the node's closed per-level set and deduped;
        a REPEATED angle is recorded as a deviation (``review_angle_repeated``) and never
        buys extra evidence. An empty declaration falls back to the level's CRITICAL
        angles, the minimum a review-tier claim must check.
        """
        level = spec.review_level if spec.review_level in REVIEW_ANGLES_BY_LEVEL \
            else DEFAULT_REVIEW_LEVEL
        domain = review_angles_for_level(level)
        angles: list[str] = []
        repeats: list[str] = []
        rejected: list[str] = []
        for angle in spec.review_angles:
            if angle not in domain:
                rejected.append(angle)
            elif angle in angles:
                repeats.append(angle)
            else:
                angles.append(angle)
        if repeats:
            emit("review_angle_repeated", angles=repeats)
        if rejected:
            emit("review_angle_rejected", angles=rejected)
        return tuple(angles) or critical_review_angles(level)

    async def run_reviews(reason: str) -> tuple[bool | None, str]:
        """Ticket 20 (items 1-3): run ONE fresh-context review per declared ANGLE and
        combine the graded verdicts by the PREDEFINED weights + the critical-angle veto.

        Every angle is a separate fresh call with its own fixed prompt. A malformed round
        records ``uncertain`` for that angle (it cannot contribute a positive score). The
        claim may proceed ONLY when :func:`combine_review_verdicts` says so — no negative
        grade, every critical angle run, and a positive weighted score. ``(None, "calls")``
        means the call budget ran out; ``(False, why)`` keeps the loop working.
        """
        nonlocal verification_review_score
        level = spec.review_level if spec.review_level in REVIEW_ANGLES_BY_LEVEL \
            else DEFAULT_REVIEW_LEVEL
        angles = _declared_review_angles()
        for angle in angles:
            verdict, failure = await run_review(angle, reason)
            if failure == "calls":
                return None, "calls"
            if failure:
                review_verdicts.append(ReviewVerdict(
                    angle=angle, grade="uncertain", coerced=True,
                    coercion_reason="review envelope stayed malformed after bounded retries",
                    detail="review unavailable"))
                emit("review_angle_unavailable", angle=angle)
        ok, score, why = combine_review_verdicts(review_verdicts, angles, level)
        verification_review_score = score
        if not ok:
            return False, why or "the weighted review did not carry the claim"
        return True, ""

    async def obtain_verification_reason() -> tuple[str, str]:
        """Ask the model for the WRITTEN ``none+reason`` justification (ticket 20).

        Returns ``(reason, "")`` on a returned envelope (the reason may still fail the
        deterministic check) or ``(\"\", failure)`` where ``failure`` is ``"calls"``
        or ``"malformed-output"``.
        """
        async def call() -> Any:
            return await llm_step(model, "verify", artifacts={
                "goal": spec.goal,
                "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
            }, question=_VERIFICATION_REASON_QUESTION)
        raw, failure = await request_bounded(call, "verification-reason")
        if failure:
            return "", failure
        reason = getattr(raw, "reason", "") if getattr(raw, "status", "") == "ok" else ""
        return (reason if isinstance(reason, str) else ""), ""

    def _required_tier() -> str:
        required = spec.verification_required
        return required if required in VERIFICATION_REQUIREMENTS else "any"

    async def enforce_verification(tier: str) -> tuple[bool, str]:
        """Enforce the plan's verification covenant for a claim at ``tier`` (ticket 20).

        The declaration is enforced, not advisory: a VERIFIED tier at or above the
        declared floor is a normal claim. A weaker VERIFIED tier (e.g. ``review`` when
        ``test`` was required) is allowed ONLY with ``best_effort``, and the downgrade is
        recorded. The ``none`` tier needs a valid written reason AND ``best_effort``; a
        reason that fails :func:`verification_reason_problem` blocks the claim. Returns
        ``(True, "")`` when the claim may proceed, ``(False, "calls")`` when the call
        budget ran out, and ``(False, "blocked")`` otherwise.
        """
        nonlocal verification_tier, verification_reason
        nonlocal verification_reason_problem_text, verification_downgraded
        nonlocal verification_downgrade_reason
        verification_tier = tier
        required = _required_tier()
        floor = _REQUIRED_FLOOR[required]
        if tier == "none":
            if not spec.best_effort or not (spec.best_effort_reason or "").strip():
                return False, "blocked"
            if floor - _TIER_RANK["none"] > 1:
                # Ticket 20 item 5: best_effort lowers the floor AT MOST one tier, so a
                # ``test`` requirement can never be satisfied by a ``none`` claim.
                emit("verification_claim_blocked", tier=tier, required=required,
                     reason="best_effort may lower the floor at most one tier")
                return False, "blocked"
            reason, failure = await obtain_verification_reason()
            if failure:
                return False, failure
            verification_reason = reason
            verification_reason_problem_text = verification_reason_problem(
                reason, goal=spec.goal, acs=spec.acs)
            if verification_reason_problem_text:
                return False, "blocked"
            verification_downgraded = True
            verification_downgrade_reason = (
                f"best_effort: no test and no review could carry verification; claimed "
                f"at the none+reason tier instead of the required {required!r} tier")
            emit("verification_unverified", required=required, reason=reason)
            return True, ""
        if _TIER_RANK[tier] >= floor:
            return True, ""
        if not spec.best_effort or not (spec.best_effort_reason or "").strip():
            # Ticket 20 item 5: best_effort is a PLAN-TIME opt-in that must carry a
            # plan-level reason; without one it is not a valid downgrade.
            return False, "blocked"
        if floor - _TIER_RANK[tier] > 1:
            # Ticket 20 item 5: best_effort may lower the floor AT MOST ONE tier
            # (test -> review, review -> none). A two-tier drop is never allowed, however
            # it was reached.
            emit("verification_claim_blocked", tier=tier, required=required,
                 reason="best_effort may lower the floor at most one tier")
            return False, "blocked"
        verification_downgraded = True
        verification_downgrade_reason = (
            f"best_effort: the required verification tier {required!r} could not be met; "
            f"claimed at the weaker {tier!r} tier")
        emit("verification_downgraded", required=required, attained=tier)
        return True, ""

    async def review_blocker(reason: str, unavailable_reason: str) -> bool:
        """Ticket 19 round 3 (FIX 1): route a claim blocker that more implementation
        cannot clear — an unresolvable criterion, or a missing/non-discriminating declared
        test case — into the owner's REVIEW path ("a test cannot carry the verification").

        Returns True ONLY when the claim may proceed (a grounded review pass, or — ticket
        20 — a best-effort ``reason`` mode where the written reason is checked at the
        claim gate). False means this attempt may not claim: no reviewer was injected and
        no ``best_effort`` opt-in (an honest stop, recorded with ``unavailable_reason`` —
        never a ladder burn), the review was unaffordable (a ``calls`` stop), it stayed
        malformed, or it rejected the diff (the review becomes the next attempt's
        context). A blocker may spend at most the declared review ANGLES: once review is
        entered, ``verification_basis == "review"`` and the ordinary per-attempt review
        loop owns every later evaluation.
        """
        nonlocal last_excerpts, review_approved
        if not enter_review(reason):
            stop("honest-failure", unavailable_reason, unavailable_reason)
            return False
        if verification_basis == "reason":
            # best_effort with no reviewer: the written-reason claim is decided at the
            # claim gate (enforce_verification).
            return True
        status, why = await run_reviews(reason)
        if status is None:
            stop("honest-failure", "call-budget", "calls")
            return False
        if not status:
            last_excerpts = [f"review did not approve: {why}"]
            return False
        review_approved = True
        return True

    async def consult_judge(jr: JudgeRequest) -> tuple[JudgeVerdict | None, str]:
        """One bounded judge consultation, AT MOST ONE per attempt (ticket 19 round 3,
        FIX 2).

        A malformed judge used to burn the generic envelope retries and the same iteration
        could consult the judge twice (the volunteer-blame site and the proactive site).
        Both are cut here: the judge is attempted once per attempt with
        :data:`JUDGE_RETRIES` retries. Returns ``(verdict, failure)`` with ``failure`` ""
        on a credited verdict, ``"calls"`` when the call budget ran out, and
        ``"unavailable"`` when the judge stayed malformed. On ``"unavailable"`` the
        deterministic "attribution unavailable" fallback is recorded and NO further judge
        call is made for this attempt; the node continues on the existing red path.
        """
        nonlocal judge_attempted, judge_unavailable
        if judge_attempted:
            return None, "unavailable"
        judge_attempted = True
        raw, failure = await request_bounded(
            partial(_call_judge, attribution, jr), "judge", retries=JUDGE_RETRIES)
        if failure == "calls":
            return None, "calls"
        if failure:
            judge_unavailable += 1
            emit("judge_unavailable", reason="attribution unavailable")
            return None, "unavailable"
        return apply_judge_filter(raw, jr), ""

    async def handle_verdict(verdict: JudgeVerdict, esc: Escalation, env: Any) -> str:
        """Apply the judge's MULTI-LABEL decision (ticket 19 A). Returns the action:

        - ``"stop"`` — a stop was set (always required for spec_wrong / environment_broken)
        - ``"repair"`` — the own test was rewritten (a bounded replacement); continue the loop
        - ``"implementation"`` — implementation_wrong alone (or an uncredited verdict): keep
          implementing with the failure as context.

        Dominance: spec_wrong (bubble: an implementation and a test are meaningless against
        a wrong spec) → environment_broken (park needs-user; nothing in-process can fix it)
        → test_wrong (repair/replace the own test, bounded) → implementation_wrong.
        """
        nonlocal test_rewrites, self_test, last_excerpts, verification_basis, review_reason
        judge_verdicts.append(verdict)
        emit("judge_verdict", implementation_wrong=verdict.implementation_wrong,
             test_wrong=verdict.test_wrong, spec_wrong=verdict.spec_wrong,
             environment_broken=verdict.environment_broken,
             attribution=verdict.attribution, reason=verdict.reason,
             evidence=verdict.evidence, coerced=verdict.coerced, raw=verdict.raw)
        if verdict.coerced:
            emit("judge_coerced", reason=verdict.coercion_reason)
        if verdict.spec_wrong:
            attempts.append(Attempt(
                node_id="leaf", layer="spec", strategy=esc.strategy,
                claimed_delta="judge attributed the failure to the spec",
                outcome="fail", verdict="novel", judge=verdict))
            queue.open(
                f"spec:{spec.goal[:40]}",
                "the leaf's failure was attributed to the specification; the "
                "parent owns the spec",
                default_choice="park the node and bubble the spec up",
            )
            emit("spec_bubbled_up", reason="judge attributed the failure to the spec")
            stop("bubble", "spec-bubble", "spec-bubble", parent=True)
            return "stop"
        if verdict.environment_broken:
            queue.open(
                f"environment:{spec.goal[:40]}",
                "the leaf's failure was attributed to a broken environment",
                default_choice="park the node; the environment cannot be fixed in-process",
            )
            emit("environment_broken", reason=verdict.reason or verdict.defect)
            stop("honest-failure", "environment", "environment", user=True)
            return "stop"
        if verdict.test_wrong and self_test:
            repaired, failure = await request_bounded(
                partial(_repair_test, model, spec, workdir, self_test,
                        last_excerpts, env),
                "test-rewrite")
            if failure == "calls":
                stop("honest-failure", "call-budget", "calls")
                return "stop"
            if failure:
                # Ticket 19 round 2 (F5): a malformed rewrite consumes its calls and is
                # recorded; the node keeps implementing against the existing test rather
                # than ending on malformed output.
                emit("test_repair_unavailable", reason="malformed-output")
                return "implementation"
            if (getattr(repaired, "status", "unable") == "ok"
                    and getattr(repaired, "content", "")):
                try:
                    _write(workdir, self_test, repaired.content)
                except WriteShapeRefused as exc:
                    emit("write_shape_refused", path=exc.path, reason=exc.detail)
                    refusals.append(f"{exc.path}: {exc.detail} (test rewrite)")
                    stop("honest-failure",
                         f"unwritable test rewrite: {exc.detail}", "write-shape")
                    return "stop"
                test_rewrites += 1
                rres = await _maybe_await(tests, workdir)
                record_gate(rres)
                repair_excerpts = excerpts_of(rres)
                if _is_green(rres):
                    # A rewrite that passes on arrival does not pin the goal, and a
                    # repaired test that cannot be made to discriminate can never carry
                    # the claim (ticket 19 B): switch to mandatory REVIEW verification.
                    emit("test_rewrite_green_on_arrival", path=self_test)
                    (workdir / self_test).unlink(missing_ok=True)
                    self_test = None
                    if review is not None:
                        verification_basis = "review"
                        review_reason = "the repaired test could not be made to discriminate"
                        emit("review_verification", reason=review_reason)
                        return "repair"
                    stop("honest-failure", "no-red-target", "no-red-target")
                    return "stop"
                last_excerpts = repair_excerpts
                signature = failure_signature(repair_excerpts, repair_excerpts)
                repair_attempt = Attempt(
                    node_id="leaf", layer="tests", strategy=esc.strategy,
                    claimed_delta=(getattr(repaired, "comment", "")
                                   or "rewrote the run's own test"),
                    failure_signature=signature, touched_files=[self_test],
                    outcome="fail", judge=verdict)
                repair_attempt.verdict = prefilter(attempts, repair_attempt)
                attempts.append(repair_attempt)
                emit("test_rewritten", path=self_test, verdict=repair_attempt.verdict)
                return "repair"
            emit("test_repair_unavailable",
                 status=getattr(repaired, "status", "unknown"))
        # implementation_wrong alone (or an uncredited/ambiguous verdict): keep implementing
        return "implementation"

    def stop(sig: str, reason: str, why: str, *, exhausted: bool = False,
             parent: bool = False, user: bool = False) -> None:
        nonlocal signal, exhaustion_reason, stop_reason, node_exhausted, needs_parent, needs_user
        signal, exhaustion_reason, stop_reason = sig, reason, why
        node_exhausted = exhausted
        needs_parent = parent
        needs_user = user

    def record_gate(res: ShapedResult | Any) -> GateReport | None:
        """Surface the machine-readable gate verdict; record an anomaly LOUDLY (F1).

        The process exit status is not evidence, so every anomaly (a missing or
        unparsable report, a report without the per-run canary, a report that
        contradicts the exit) lands in the ledger and on the outcome. A gate result
        with no report at all is the injected seam's, not the run's.
        """
        gate = getattr(res, "gate", None)
        if gate is None:
            return None
        if gate.structural_anomaly:
            emit("gate_report_anomaly", anomaly=gate.anomaly, detail=gate.detail,
                 report=gate.report_path, process_exit=gate.process_exit)
            gate_anomalies.append(f"{gate.anomaly}: {gate.detail}")
        elif gate.observed and gate.process_exit == 0 and not gate.green:
            # R2 (verification round 6): the process claimed success while its own
            # report said otherwise (e.g. run code forcing exit 0 from atexit). It is a
            # trustworthy RED, but the lie itself is evidence and must be recorded.
            emit("gate_process_lie", anomaly=gate.anomaly, detail=gate.detail,
                 report=gate.report_path, process_exit=gate.process_exit)
            gate_anomalies.append(f"process-exit-lie: {gate.anomaly}: {gate.detail}")
        return gate

    def excerpts_of(res: ShapedResult | Any) -> list[str]:
        """Shaped pytest output, quoting the gate anomaly when nothing was observed.

        A missing report leaves no failure excerpt at all, so the next attempt would
        otherwise start blind; the anomaly is the only honest failure context there.
        """
        excerpts = list(getattr(res, "excerpts", []) or [])
        gate = getattr(res, "gate", None)
        if gate is not None and not gate.green and not gate.observed:
            return [f"gate_report_anomaly {gate.anomaly}: {gate.detail}", *excerpts]
        return excerpts

    def write_self_test(rel: str, content: str) -> str:
        """Write the run's own test; returns "" on success, else the write-shape detail.

        The caller decides the stop (or the switch to review-based verification when the
        test path itself is unwritable, ticket 19 C2).
        """
        try:
            _write(workdir, rel, content)
        except WriteShapeRefused as exc:
            emit("write_shape_refused", path=exc.path, reason=exc.detail)
            refusals.append(f"{exc.path}: {exc.detail} (self-test)")
            return exc.detail
        return ""

    def refuse_self_test(env: Any, message: str, reason: str, *, open_question: bool) -> None:
        """Honest stop for a self-test envelope with no usable landing spot.

        A write-SHAPE problem (existing directory, path under a file, embedded NUL
        byte, over-long name) has no safe normalization here, so it takes the
        write-shape stop; anything else is a logic-level self-test refusal.
        """
        path = _env_path(env)
        kind, problem = _self_test_problem(env, spec, workdir)
        emit(kind, path=path, reason=problem)
        refusals.append(f"{path}: {problem} (self-test)")
        if _write_shape_problem(path, workdir):
            emit("write_shape_refused", path=path, reason=problem)
            stop("honest-failure", f"{message}: {problem}", "write-shape")
            return
        if open_question:
            queue.open(
                f"self-test:{spec.goal[:40]}",
                "the run could not write its own test at a safe path",
                default_choice="park until a writable test path is available",
            )
        stop("honest-failure", f"{message}: {problem}", reason)

    def _wrote_code() -> bool:
        """True when the run wrote source (a non-owned path) in any attempt."""
        return any(not owned_paths(rel) for attempt in attempts
                   for rel in attempt.touched_files)

    def _terminal_tier() -> str:
        """The strongest VERIFIED evidence the terminal state actually rested on.

        A claim's tier is set by :func:`enforce_verification`. For a non-claim the
        terminal evidence is the run's own discriminating test (``test``) when one was
        observed red, else a performed review (``review``), else ``none``.
        """
        if self_test is not None and test_rewrites == 0:
            return "test"
        if review_verdicts:
            return "review"
        return "none"

    def finish() -> LeafOutcome:
        reason = exhaustion_reason
        if last_iv_reason and not claimed:
            reason = f"{reason}; independent-test {last_iv_reason}" if reason else f"independent-test {last_iv_reason}"
        last = iv_verdicts[-1] if iv_verdicts else None
        tier = verification_tier or (_terminal_tier() if not claimed else "none")
        wrote = _wrote_code()
        record = None
        if wrote:
            record = VerificationRecord(
                wrote_code=True, tier=tier, reason=verification_reason,
                reason_problem=verification_reason_problem_text,
                reviews=tuple(review_verdicts),
                review_angles=_declared_review_angles(),
                review_level=(spec.review_level
                              if spec.review_level in REVIEW_ANGLES_BY_LEVEL
                              else DEFAULT_REVIEW_LEVEL),
                review_score=verification_review_score,
                required=_required_tier(), best_effort=bool(spec.best_effort),
                downgraded=verification_downgraded,
                downgrade_reason=verification_downgrade_reason)
        verified = tier in ("test", "review")
        if claimed and verified:
            claim_status = "verified-success"
        elif claimed:
            claim_status = "unverified-success"
        elif verified:
            claim_status = "verified-failure"
        else:
            claim_status = "unverified-failure"
        return LeafOutcome(
            claimed=claimed,
            signal=signal,
            attempts=list(attempts),
            calls=calls,
            wall_s=round(clock() - started, 3),
            self_test=self_test,
            questions=queue.all(),
            exhausted=node_exhausted,
            exhaustion_reason=reason,
            layers_used=list(dict.fromkeys(a.layer for a in attempts)),
            stop_reason=stop_reason,
            wasted_escalations=list(wasted_escalations),
            test_rewrites=test_rewrites,
            own_test_mutated=test_rewrites > 0,
            needs_parent=needs_parent,
            judge_verdicts=list(judge_verdicts),
            claimed_basis=claimed_basis,
            independent_test=(last.content if last is not None else ""),
            independent_test_path=(last.path if last is not None else ""),
            independent_test_node_ids=list(last.node_ids) if last is not None else [],
            iv_original_gate=(last.original_gate if last is not None else None),
            iv_final_gate=(last.final_gate if last is not None else None),
            iv_verdicts=list(iv_verdicts),
            independent_test_reason=last_iv_reason,
            iv_attempts=iv_attempts,
            iv_repairs=iv_repairs,
            iv_criteria_count=(last.criteria_count if last is not None else 0),
            iv_criteria=list(last.criteria) if last is not None else [],
            iv_covered_indices=list(last.covered_indices) if last is not None else [],
            iv_uncovered_indices=list(last.uncovered_indices) if last is not None else [],
            iv_shared_node_ids=list(last.shared_node_ids) if last is not None else [],
            refusals=list(refusals),
            gate_anomalies=list(gate_anomalies),
            verification_basis=verification_basis,
            review_verdicts=list(review_verdicts),
            review_verdict=(review_verdicts[-1] if review_verdicts else None),
            coverage=list(coverage),
            coverage_missing=list(coverage_missing),
            coverage_unresolved=list(coverage_unresolved),
            test_case_problems=list(test_case_problems),
            malformed_steps=list(malformed_steps),
            judge_unavailable=judge_unavailable,
            needs_user=needs_user,
            verification=record,
            verified=verified,
            claim_status=claim_status,
        )

    def enter_review(why: str) -> bool:
        """Switch to mandatory REVIEW-BASED verification (ticket 19 B), or — ticket 20 —
        to best-effort ``reason`` mode when no reviewer was injected.

        Returns False when no ``review`` producer was injected AND the plan did not opt
        into ``best_effort`` (the leaf then keeps its conservative honest stop, since
        nothing can verify the diff). With ``best_effort`` set, ``reason`` mode lets the
        loop proceed and the written-reason claim gate decide; the claim is recorded as
        UNVERIFIED.
        """
        nonlocal verification_basis, review_reason
        if review is None:
            if not spec.best_effort:
                return False
            verification_basis = "reason"
            review_reason = why
            emit("verification_reason_mode", reason=why)
            return True
        verification_basis = "review"
        review_reason = why
        emit("review_verification", reason=why)
        return True

    # ---- deadline before the first call (an already-expired budget writes nothing)
    if budget.expired(clock()):
        stop("handover", "deadline", "deadline")
        return finish()

    # ---- step 1: the run's own test, RUN and required to be RED ON ARRIVAL ----
    self_env, failure = await request_envelope(
        partial(_request_write, model, _self_test_artifacts(spec), _SELF_TEST_QUESTION),
        "self-test")
    if failure == "calls":
        stop("honest-failure", "call-budget", "calls")
        return finish()
    if failure == "deadline":
        stop("handover", "deadline", "deadline")
        return finish()
    normalized = _relocate_self_test(self_env, spec, workdir, emit)
    if normalized is None:
        # No usable test path. Ticket 19 C2: an unwritable test path means review is the
        # mandatory verification (a review verdict with evidence may carry the claim);
        # otherwise the honest self-test refusal stands.
        if not enter_review("the run's own test could not be written at a safe path"):
            refuse_self_test(self_env, "self-test-refused", "self-test", open_question=True)
            return finish()
    else:
        if normalized != getattr(self_env, "file_path", ""):
            _, problem = _self_test_problem(self_env, spec, workdir)
            refusals.append(f"{getattr(self_env, 'file_path', '')}: {problem} -> "
                            f"{normalized} (self-test relocated)")
        problem = write_self_test(normalized, self_env.content)
        if problem:
            if not enter_review(f"the run's own test path was unwritable: {problem}"):
                stop("honest-failure", f"unwritable self-test target: {problem}", "write-shape")
                return finish()
        else:
            self_test = normalized

    if verification_basis == "test":
        res = await _maybe_await(tests, workdir)
        gate = record_gate(res)
        if _is_green(res):
            # A test that passes on arrival does not exercise the failure. Re-ask ONCE
            # with that evidence; never emit red=True without having observed a red.
            emit("self_test_green_on_arrival", path=self_test)
            previous_path = self_test
            previous_content = _read(workdir, self_test)
            (workdir / self_test).unlink(missing_ok=True)
            self_test = None
            retry_env, failure = await request_envelope(
                partial(_request_write, model,
                        _retry_self_test_artifacts(spec, previous_path, previous_content),
                        _RETRY_SELF_TEST_QUESTION),
                "self-test-retry")
            if failure == "calls":
                stop("honest-failure", "call-budget", "calls")
                return finish()
            if failure == "deadline":
                stop("handover", "deadline", "deadline")
                return finish()
            normalized = _relocate_self_test(retry_env, spec, workdir, emit)
            if normalized is None:
                if not enter_review("the run's own test could not be written at a safe path"):
                    refuse_self_test(retry_env, "no-red-target", "no-red-target",
                                     open_question=False)
                    return finish()
            else:
                if normalized != getattr(retry_env, "file_path", ""):
                    _, problem = _self_test_problem(retry_env, spec, workdir)
                    refusals.append(f"{getattr(retry_env, 'file_path', '')}: {problem} -> "
                                    f"{normalized} (self-test relocated)")
                problem = write_self_test(normalized, retry_env.content)
                if problem:
                    if not enter_review(f"the run's own test path was unwritable: {problem}"):
                        stop("honest-failure",
                             f"unwritable self-test target: {problem}", "write-shape")
                        return finish()
                else:
                    self_test = normalized
                    res = await _maybe_await(tests, workdir)
                    gate = record_gate(res)
        if verification_basis == "test" and (
                _exit_code(res) is None or (gate is not None and not gate.observed)):
            # We could not trust an observation of the run's own tests: a transport error /
            # sandbox block, or a gate report that is missing or holds no testcase. Nothing
            # may be recorded as a red, so no target is kept.
            emit("self_test_unverified", path=self_test, reason="tests did not run")
            (workdir / self_test).unlink(missing_ok=True)
            self_test = None
            stop("honest-failure", "self-test-unverified", "self-test")
            return finish()
        if verification_basis == "test" and _is_green(res):
            # The one re-ask was green too: no red target. Ticket 19 A: consult the judge
            # IMMEDIATELY (spec / environment are actionable here); ticket 19 B: otherwise
            # switch to mandatory review verification when a reviewer is injected.
            emit("self_test_green_on_arrival", path=self_test)
            previous_path = self_test
            previous_content = _read(workdir, self_test)
            (workdir / self_test).unlink(missing_ok=True)
            self_test = None
            if attribution is not None and can_afford(2):
                jr = _no_red_judge_request(spec, workdir, previous_path, previous_content,
                                           baseline)
                verdict, failure = await consult_judge(jr)
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    return finish()
                if verdict is not None:
                    action = await handle_verdict(
                        verdict, Escalation("L1-resample", "sampling", False, "no red target"),
                        None)
                    if action == "stop":
                        return finish()
            if not enter_review("the run's own test could not be made to fail on arrival"):
                stop("honest-failure", "no-red-target", "no-red-target")
                return finish()
        if verification_basis == "test":
            last_excerpts = excerpts_of(res)
            emit("self_test_written", path=self_test, red=True)

    # ---- step 2: attempt loop (bounded by Budget and 3 × files, cap 9) ----
    while True:
        if budget.expired(clock()):
            stop("handover", "deadline", "deadline")
            break
        if budget.calls < 1:
            stop("honest-failure", "call-budget", "calls")
            break
        if attempts and attempts_exhausted(attempts):
            stop("exhausted", _reason(attempts), "attempts", exhausted=True)
            break
        if len(attempts) >= attempt_cap:
            stop("honest-failure", "attempt-cap", "attempts")
            break

        esc = escalate(attempts, rung, excerpts=last_excerpts,
                       repo_files=_repo_view(spec, workdir, tuple(baseline)))
        if esc.wasted:
            wasted_escalations.append(esc)
            emit("escalation_wasted", strategy=esc.strategy or "none", reason=esc.reason)
            if esc.strategy is None:
                # no rung is left to advance to; stop honestly instead of spinning.
                if attempts and attempts_exhausted(attempts):
                    stop("exhausted", _reason(attempts), "attempts", exhausted=True)
                else:
                    stop("honest-failure", "ladder-exhausted", "ladder")
                break
            rung += 1
            continue

        mode = _mode(attempts)
        pending_verdict: JudgeVerdict | None = None
        judge_attempted = False   # FIX 2: at most one judge consultation per attempt
        review_approved = False   # ticket 20: recomputed each attempt (review angles)
        emit("leaf_attempt", n=len(attempts) + 1, strategy=esc.strategy, layer=esc.layer,
             mode=mode)
        if mode == "M1":
            _erase_draft(workdir, baseline)
        env, failure = await request_bounded(
            partial(_request_write, model,
                    _implement_artifacts(spec, workdir, esc, attempts, last_excerpts,
                                         self_test, mode, baseline),
                    _implement_question(mode, esc)),
            "implement")
        if failure == "calls":
            stop("honest-failure", "call-budget", "calls")
            break
        if failure:
            # Ticket 19 round 2 (F5): a malformed implement envelope consumes its calls
            # and is recorded; the loop continues (bounded by the existing call-budget,
            # attempt-cap, and ladder stops) instead of ending the node.
            last_excerpts = ["implement envelope stayed malformed after bounded retries"]
            rung += 1
            continue

        # The model claims its own TEST is wrong: an INDEPENDENT judge is the only way
        # that claim is credited (ticket 17 policy, kept by ticket 19). The PROACTIVE
        # trigger below is the ticket-19 addition: the judge is consulted on a red REPORTS
        # signal even when the model volunteers nothing.
        if _claims_test_wrong(env):
            if attribution is None:
                # No independent judge: the model's own word is never enough. Treat
                # the claim as an implementation failure and let the ladder advance.
                emit("test_blame_uncredited", reason="no independent judge")
            elif not can_afford(2):
                # judge + a possible test rewrite is a multi-call escalation; without
                # the calls for it, stop cleanly instead of half-spending.
                stop("honest-failure", "call-budget", "calls")
                break
            else:
                jr = _judge_request(spec, workdir, self_test, last_excerpts, env, baseline)
                verdict, failure = await consult_judge(jr)
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    break
                if verdict is not None:
                    pending_verdict = verdict
                    action = await handle_verdict(verdict, esc, env)
                    if action == "stop":
                        break
                    if action == "repair":
                        continue
                # A malformed judge (FIX 2) leaves the model's own test-blaming word
                # uncredited and the run keeps implementing.

        # normal path: write the source candidate (guarded) and run the tests
        wrote, source_rel, refusal, shape = _write_candidate(env, spec, workdir, self_test, baseline)
        if shape:
            # A bad target SHAPE on a source write has no safe normalization (we cannot
            # guess which file the model meant), so stop honestly instead of raising.
            refusals.append(f"{source_rel}: {refusal} (un-normalizable target shape)")
            emit("write_shape_refused", path=source_rel, reason=refusal)
            stop("honest-failure", f"un-normalizable write target: {refusal}", "write-shape")
            break
        if refusal:
            # A refused source write (a test path, test infrastructure, a grader path,
            # or a module-shadow path) never touches the tree and never runs the gate;
            # the attempt is recorded and the ladder continues.
            refusals.append(f"{source_rel}: {refusal}")
            emit("implement_refused", path=source_rel, reason=refusal)
            last_excerpts = [f"implement refused: {refusal}"]
        res = await _maybe_await(tests, workdir) if wrote else None
        if res is not None:
            record_gate(res)
            last_excerpts = excerpts_of(res)

        # Ticket 19 A: PROACTIVE attribution. After K consecutive RED attempts in which
        # the run materially changed the code, consult the judge even though the model
        # volunteered nothing. The judge sees the goal, the ACs, the run's own test, the
        # failing output, and the current diff; its labels decide the next move.
        if res is not None and not _is_green(res) and wrote and source_rel:
            red_code_changes = (red_code_changes + 1
                                if _file_materially_changed(workdir, baseline, source_rel)
                                else 0)
            if (attribution is not None and pending_verdict is None
                    and red_code_changes == ATTRIBUTION_RED_K and can_afford(2)):
                emit("judge_triggered", reason="red-code-changes", count=red_code_changes)
                jr = _judge_request(spec, workdir, self_test, last_excerpts, env, baseline)
                verdict, failure = await consult_judge(jr)
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    break
                if verdict is not None:
                    pending_verdict = verdict
                    action = await handle_verdict(pending_verdict, esc, env)
                    if action == "stop":
                        break
                    if action == "repair":
                        red_code_changes = 0
                        continue
                # FIX 2: a malformed judge leaves the attempt on the existing red path
                # (no credited verdict, no repeat consultation this attempt).
        else:
            red_code_changes = 0

        # Ticket 19 round 2 (F2): an EMPTY acceptance-criteria list cannot be carried by
        # the run's own test alone; review (with the grounded evidence of F1) is mandatory.
        if not spec.acs and verification_basis == "test" and wrote and source_rel:
            enter_review("the acceptance-criteria list is empty: a test basis alone "
                         "cannot carry the claim")
        # Ticket 19 B / ticket 20: when no test can carry verification, the declared review
        # ANGLES are the gate (weighted, critical-angle veto, no negative grade).
        if verification_basis == "review" and wrote and source_rel:
            status, why = await run_reviews(review_reason)
            if status is None:
                stop("honest-failure", "call-budget", "calls")
                break
            review_approved = bool(status)
            if not review_approved:
                last_excerpts = [f"review did not approve: {why}"]

        signature = failure_signature(last_excerpts, last_excerpts)
        if verification_basis == "review":
            approved = review_approved
        elif verification_basis == "reason":
            # best_effort with no test and no reviewer: the model's completed write is the
            # only completion signal; the written-reason claim gate below decides the tier.
            approved = bool(wrote and source_rel)
        else:
            approved = _is_green(res)
        candidate = Attempt(
            node_id="leaf",
            layer=esc.layer,
            strategy=esc.strategy or "L1-resample",
            claimed_delta=getattr(env, "comment", "") or "",
            failure_signature=signature,
            touched_files=[source_rel] if wrote else [],
            outcome="pass" if approved else "fail",
            judge=pending_verdict,
        )
        if not wrote:
            candidate.verdict = "same"
        else:
            candidate.verdict = prefilter(attempts, candidate)

        if candidate.outcome == "pass":
            if not spec.acs and verification_basis == "test":
                # Ticket 19 round 2 (F2): with no acceptance criteria a test basis alone
                # can never carry the claim. A reviewer would have switched the run to
                # review above; without one there is no claim route, so stop honestly
                # (the distinct reason is recorded on the outcome).
                attempts.append(candidate)
                emit("no_acceptance_criteria_claim_blocked")
                stop("honest-failure", "no-acceptance-criteria", "no-acceptance-criteria")
                break
            report = getattr(res, "gate", None)
            if test_rewrites and verification_basis == "test":
                # A green after the run REPLACED its own test is not a claim: the
                # implementation satisfied a substituted test, so the result is
                # unverified (ticket 17 round 4).
                attempts.append(candidate)
                emit("leaf_green_after_test_rewrite", strategy=esc.strategy)
                stop("green-after-test-rewrite", "", "green-after-test-rewrite")
                break
            # Ticket 19 E: per-requirement ARTIFACT coverage of the final diff. A
            # criterion whose named file/symbol is untouched was not implemented; the
            # node may NOT claim (the design answer to T-31's one-of-two call sites).
            new_coverage = _requirement_coverage(spec, workdir, baseline)
            new_missing = [f"{c.statement!r} names {m}, untouched by the diff"
                           for c in new_coverage for m in c.missing]
            if new_missing:
                coverage, coverage_missing = new_coverage, new_missing
                candidate.outcome = "fail"
                candidate.verdict = prefilter(attempts, candidate)
                attempts.append(candidate)
                emit("requirement_uncovered", missing=new_missing)
                last_excerpts = [f"requirement artifact untouched: {m}" for m in new_missing]
                rung += 1
                continue
            coverage, coverage_missing = new_coverage, []
            # Ticket 19 round 2 (F2/F4): a criterion that names NO resolvable artifact is
            # NOT skipped. On the test basis it must be carried by a DECLARED test that
            # DISCRIMINATES (red on the pristine source, green on final); a placeholder
            # that only asserts ``True`` is green there and cannot carry it. Without one
            # the node may not claim (a distinct, recorded reason).
            unresolved: list[str] = []
            if verification_basis == "test":
                declared_by_index: dict[int, list[DeclaredTestCase]] = {}
                for case in spec.test_cases:
                    case_index = _declared_case_index(case)
                    if case_index is not None:
                        declared_by_index.setdefault(case_index, []).append(case)
                for criterion in new_coverage:
                    if not _criterion_unresolved(criterion):
                        continue
                    discriminating = False
                    for case in declared_by_index.get(criterion.index, []):
                        if await _declared_case_discriminates(tests, spec, workdir, case):
                            discriminating = True
                            break
                    if not discriminating:
                        unresolved.append(
                            f"AC{criterion.index}: criterion names no artifact and no "
                            "declared test discriminates for it")
            if unresolved:
                coverage_unresolved = unresolved
                emit("criterion_unresolved", problems=unresolved)
                # FIX 1: an unresolvable criterion cannot be cleared by more code, so the
                # node enters the owner's REVIEW path ("a test cannot carry the
                # verification"). A grounded review pass then claims on
                # verification_basis="review"; with no reviewer this is an honest stop,
                # never a ladder burn.
                if not await review_blocker(
                        "a criterion names no artifact and no declared test discriminates "
                        "for it", "criterion-unresolved"):
                    candidate.outcome = "fail"
                    candidate.verdict = prefilter(attempts, candidate)
                    attempts.append(candidate)
                    if stop_reason:
                        break
                    last_excerpts = [f"criterion not carried: {p}" for p in unresolved]
                    rung += 1
                    continue
            else:
                coverage_unresolved = []
            # Ticket 19 D: the DECLARED test-case contract, verified mechanically from
            # the report. A missing file/name is a distinct, repairable failure.
            tc_problems = ([] if verification_basis != "test"
                           else _declared_test_case_problems(report, spec.test_cases))
            if tc_problems and test_case_repairs < 1 and self_test and can_afford(1):
                emit("test_case_repair", problems=tc_problems)
                repaired_env, failure = await request_bounded(
                    partial(_request_write, model,
                            _declared_case_artifacts(spec, self_test, tc_problems),
                            _MISSING_TEST_CASES_QUESTION),
                    "test-cases")
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    break
                if failure:
                    # F5: a malformed repair consumes its calls and is recorded; the node
                    # keeps working and the repair stays available on the next attempt.
                    last_excerpts = ["test-case repair envelope stayed malformed"]
                    rung += 1
                    continue
                test_case_repairs += 1
                if (getattr(repaired_env, "status", "unable") == "ok"
                        and getattr(repaired_env, "content", "")):
                    try:
                        _write(workdir, self_test, repaired_env.content)
                    except WriteShapeRefused as exc:
                        refusals.append(f"{exc.path}: {exc.detail} (test cases)")
                        stop("honest-failure",
                             f"unwritable test repair: {exc.detail}", "write-shape")
                        break
                    rres = await _maybe_await(tests, workdir)
                    record_gate(rres)
                    res = rres
                    report = getattr(rres, "gate", None)
                    tc_problems = _declared_test_case_problems(report, spec.test_cases)
                    if _is_green(rres) and not tc_problems:
                        # The repair replaced the run's own test AFTER the red observation,
                        # so it must re-prove it is a real discriminator: RED on the
                        # PRISTINE source (in a private copy, never the workdir).
                        if not await _repaired_test_is_red_on_pristine(
                                tests, spec, self_test, repaired_env.content):
                            tc_problems = ["the repaired test still PASSES on the pristine "
                                           "source (it does not discriminate)"]
                    if not _is_green(rres):
                        # the repair broke the target: record a red attempt and continue
                        candidate.outcome = "fail"
                        candidate.verdict = prefilter(attempts, candidate)
                        attempts.append(candidate)
                        last_excerpts = excerpts_of(rres)
                        rung += 1
                        continue
            if tc_problems:
                test_case_problems = tc_problems
                emit("test_cases_missing", problems=tc_problems)
                # FIX 1: the declared test-case defect survived the bounded repair, and
                # more implementation cannot clear it; enter the owner's REVIEW path.
                # No reviewer is the honest ``test-cases`` stop (never a ladder burn).
                if not await review_blocker(
                        "a declared test case is missing or does not discriminate",
                        "test-cases"):
                    candidate.outcome = "fail"
                    candidate.verdict = prefilter(attempts, candidate)
                    attempts.append(candidate)
                    if stop_reason:
                        break
                    last_excerpts = [f"declared test case unresolved: {p}"
                                     for p in tc_problems]
                    rung += 1
                    continue
            else:
                test_case_problems = []
            attempts.append(candidate)
            # Ticket 19 C: the independent test is an EXTRA LABEL, never the veto. Its
            # verdict is recorded (with its one bounded repair) but never stands between the
            # run and a claim authorised by the run's own discriminating test. Ticket 20
            # (item 7): where it is injected it is the STRONG-evidence route — an approved
            # independent discriminator upgrades the claim to the ``test`` tier, including
            # when review was the basis (it never overrides a REJECTED review).
            iv_approved = False
            if iv is not None and can_afford(1):
                iv_request = _iv_request(spec, workdir, baseline)
                original_tree = dict(spec.files)
                final_tree = _repo_view(spec, workdir, tuple(baseline))
                label, failure = await iv_verdict_for(iv_request, original_tree, final_tree)
                if failure:
                    last_iv_reason = f"{failure}: independent label not collected"
                    emit("independent_test_uncollected", reason=failure)
                else:
                    record_iv(label)
                    if (not label.approved and label.reason in _IV_REPAIRABLE
                            and can_afford(1)):
                        iv_repairs += 1
                        emit("independent_test_repair", reason=label.reason,
                             detail=label.detail, requested=label.requested_path)
                        repaired, failure = await iv_verdict_for(
                            _iv_repair_request(iv_request, label), original_tree, final_tree)
                        if not failure:
                            record_iv(repaired)
                            label = repaired
                    iv_approved = label.approved
                    if not label.approved:
                        last_iv_reason = f"{label.reason}: {label.detail}"
            # --- ticket 20: the ORDERED verification tier + covenant enforcement ---
            if iv_approved:
                # An independently authored, red-on-pristine/green-on-final test is the
                # top (``test``) tier wherever it is available.
                tier = "test"
            elif verification_basis == "review":
                tier = "review" if review_approved else "none"
            elif verification_basis == "reason":
                tier = "none"
            elif self_test is not None and test_rewrites == 0:
                tier = "test"
            else:
                tier = "none"
            allowed, tier_failure = await enforce_verification(tier)
            if not allowed:
                if tier_failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                else:
                    emit("verification_claim_blocked", tier=tier,
                         required=_required_tier(),
                         reason=verification_reason_problem_text)
                    stop("honest-failure", "verification-required",
                         "verification-required")
                break
            claimed = True
            if verification_basis == "review":
                claimed_basis = "review+independent-test" if iv_approved else "review"
            elif tier == "none":
                claimed_basis = "reason"
            elif iv_approved and verification_basis == "reason":
                claimed_basis = "independent-test"
            elif iv_approved:
                claimed_basis = "own-test+independent-test"
            else:
                claimed_basis = "own-test"
            if tier == "none":
                stop("unverified", "", "unverified")
                emit("leaf_unverified_claim", tier=tier, required=_required_tier(),
                     reason=verification_reason)
            else:
                stop("green", "", "green")
                emit("leaf_green", strategy=esc.strategy, after_test_rewrite=False)
            break

        attempts.append(candidate)
        emit("attempt_recorded", strategy=esc.strategy, layer=esc.layer,
             verdict=candidate.verdict, signature=signature)

    emit("leaf_stop", signal=signal, claimed=claimed, calls=calls,
         reason=exhaustion_reason, stop_reason=stop_reason)
    return finish()


def _write_candidate(
    env: Any, spec: LeafSpec, workdir: Path, self_test: str | None,
    baseline: dict[str, str | None],
) -> tuple[bool, str, str, bool]:
    """Apply an implementation envelope through the blind write guard.

    Returns ``(wrote, rel, refusal, shape)``. ``shape`` is True when the ONLY problem
    is an un-normalizable target shape (an existing directory at the target, or a path
    component that is an existing file): the caller stops honestly instead of raising
    ``IsADirectoryError``/``FileExistsError``. Any other refusal does not touch the
    tree; the loop records it as a red attempt and lets the ladder advance.
    """
    if getattr(env, "status", "unable") != "ok":
        return False, "", f"status={getattr(env, 'status', 'unknown')}", False
    rel = _env_path(env)
    if not rel:
        return False, "", "no file_path", False
    problem = _source_write_problem(rel, spec, self_test)
    if problem:
        return False, rel, problem, False
    shape = _write_shape_problem(rel, workdir)
    if shape:
        return False, rel, shape, True
    if rel not in baseline:
        target = workdir / rel
        baseline[rel] = target.read_text() if target.exists() else None
    try:
        if rel not in baseline:
            target = workdir / rel
            baseline[rel] = target.read_text() if target.exists() else None
        _write(workdir, rel, env.content)
    except WriteShapeRefused as exc:
        # The shape probe above did not anticipate this one; it is still a write-shape
        # refusal (F3), never a crash.
        return False, rel, exc.detail, True
    except (ValueError, OSError) as exc:      # embedded NUL / ENAMETOOLONG on the probe-free path
        return False, rel, f"unwritable path ({type(exc).__name__}: {exc})", True
    return True, rel, "", False


def _no_red_judge_request(
    spec: LeafSpec, workdir: Path, test_path: str, test_content: str,
    baseline: Mapping[str, str | None],
) -> JudgeRequest:
    """The judge view for the ticket-19 A no-red-target trigger: the run's own test PASSED
    on arrival, so there is no red report but there is still a failure to attribute."""
    return JudgeRequest(
        goal=spec.goal,
        acs=list(spec.acs),
        failure=("the run's own test PASSED on arrival (exit 0): it does not exercise the "
                 "failure"),
        test_path=test_path,
        test_content=test_content,
        files=_repo_view(spec, workdir, tuple(baseline)),
    )


def _judge_request(
    spec: LeafSpec,
    workdir: Path,
    self_test: str | None,
    last_excerpts: Sequence[str],
    env: Any,
    baseline: Mapping[str, str | None],
) -> JudgeRequest:
    """Build the blind judge view (never a grader path).

    The judge sees the goal, the ACs, the run's own test file, the failing output,
    and the source: the blind view (``spec.files``) plus any draft the run wrote, with
    the current attempt's proposed content overlaid. No test path but the run's OWN
    test enters this request.
    """
    files = _repo_view(spec, workdir, tuple(baseline))
    proposed = _env_path(env)
    content = getattr(env, "content", "") or ""
    if (getattr(env, "status", "") == "ok" and proposed and content
            and not is_test_path(proposed) and proposed not in set(spec.grader_paths)):
        files[proposed] = content
    return JudgeRequest(
        goal=spec.goal,
        acs=list(spec.acs),
        failure="\n".join(last_excerpts) or (getattr(env, "comment", "") or ""),
        test_path=self_test or "",
        test_content=_read(workdir, self_test),
        files=files,
    )
