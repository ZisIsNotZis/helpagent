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
   refused/unestablished self-test, an exhausted call budget, or a model envelope that
   stayed malformed past its bounded retries (``malformed-output`` — no model failure
   ever raises out of the leaf).

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
- **A claim needs an INDEPENDENT TEST (ticket 17 round 7, replacing the round-4
  falsifier text opinion).** When an ``iv`` producer is injected (the ``--iv`` driver
  default), ``claimed=True`` additionally requires a DETERMINISTIC two-gate check on a
  fresh-context test the run never saw: the test must FAIL on a private copy of the
  PRE-RUN source (``red on original``; a test that passes there is vacuous and rejected
  with ``independent-test-not-red``) and PASS on a private copy of the FINAL source.
  Both copies live in a ``tempfile`` directory outside the workdir, so the run can never
  see the independent test; the model call sees the goal, the ACs, and the ORIGINAL and
  FINAL source of the changed files, never the run's own test and never a grader path.
  On either failure the test's output becomes the next attempt's failure context and the
  loop CONTINUES; claimed is ``True`` only when both gates hold and the run's own test is
  unmodified (``claimed_basis="own-test+independent-test"``). A test that cannot be
  produced, afforded, or evaluated leaves ``claimed=False`` — never claim unverified.
  Without an ``iv`` producer the basis is the run's own unmodified test
  (``claimed_basis="own-test"``).
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
- **A test may only be REPLACED, never weakened, and only with an independent
  judge.** The model's own "the test is wrong" claim is never enough: without an
  injected independent judge the claim is not credited and the failure is treated
  as an implementation failure (deterministic conservative default). When the judge
  does attribute to the tests, the test is re-derived from scratch and must be RED
  ON ARRIVAL again before the loop continues. A judge attribution of ``tests`` is
  itself put through the deterministic filter (:func:`apply_judge_filter`): it is
  honoured only when the verdict carries a non-empty defect naming the failing test
  function or one of its assertions; otherwise it is coerced to implementation and
  the coercion is recorded for calibration.
- **No model failure crashes the leaf.** Every envelope request (self-test, its
  retry, implement, judge, test rewrite) is retried up to :data:`ENVELOPE_RETRIES`
  times when the model output is malformed/unparseable; a persistent failure stops
  the run as ``malformed-output`` rather than raising :class:`SchemaViolation`.
- **No "give up".** Exhaustion is delegated to :func:`harness.attempts.exhausted`,
  so a same-verdict tail without a structural lever or three exercised layers keeps
  the node alive. The leaf's ``exhausted`` flag is set only by that function; a call
  budget or a deadline is a distinct, honestly-named stop (``stop_reason``).
"""

from __future__ import annotations

import inspect
import json
import re
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any

from harness.attempts import (
    Attempt,
    JudgeVerdict,
    failure_signature,
    layers_tried,
    prefilter,
)
from harness.attempts import exhausted as attempts_exhausted
from harness.budget import Budget
from harness.checks import diagnose_test_output
from harness.exec import ShapedResult
from harness.exec import exec as k_exec
from harness.gate_report import (
    JUNIT_FAMILY_ARGS,
    GateReport,
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
    "Escalation",
    "IndependentTestCandidate",
    "IndependentTestRequest",
    "IndependentTestVerdict",
    "JudgeRequest",
    "JudgeVerdict",
    "LeafOutcome",
    "LeafSpec",
    "WriteShapeRefused",
    "apply_judge_filter",
    "escalate",
    "evaluate_independent_test",
    "run_leaf",
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
#: ``malformed-output`` is the round-3 robustness stop: a model envelope that stayed
#: unparseable after its bounded retries no longer raises — it stops honestly here.
STOP_REASONS: tuple[str, ...] = (
    "calls",            # the call budget is spent
    "deadline",         # the wall-clock window closed (handover)
    "attempts",         # node exhaustion or the bounded-attempt cap
    "ladder",           # no rung is left to advance to
    "spec-bubble",      # the judge attributed the failure to the specification
    "no-red-target",    # the run's own test could not be made to fail on arrival
    "self-test",        # the run's own test could not be written at a safe path / could not run
    "green",            # the run's own tests exited 0 and the independent test approved
    "green-after-test-rewrite",  # a replaced test went green: unverified, never claimed
    "write-shape",      # a write target could not be normalized (NUL/long/dir/file-parent)
    "malformed-output", # a model envelope stayed malformed past its bounded retries
)

#: Bounded retries for a malformed/unparseable model envelope (owner direction: no
#: model failure may crash the leaf). One initial attempt plus this many retries; a
#: persistent failure stops the run as ``malformed-output`` instead of raising.
ENVELOPE_RETRIES = 2

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
class LeafSpec:
    """The blind leaf contract.

    ``files`` is the source-only view the run may see; ``grader_paths`` are owned by
    the grader and must never reach the run (DESIGN §6/§10.6).
    """

    goal: str
    files: dict[str, str]  # blind view: source only
    acs: list[str]
    interfaces: list[str]
    grader_paths: tuple[str, ...] = ()  # owned by the grader: never shown, never writable


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
    # (``independent-test-not-red`` / ``independent-test-unobserved``) triggered. Both
    # land in the persisted run record so the mechanism's price is measurable.
    iv_attempts: int = 0
    iv_repairs: int = 0
    # Every write-guard action (ticket 17 round 5): a refused self-test/source write or
    # a normalized landing spot. Persisted in the run record so a forged-green attempt
    # is visible after the fact.
    refusals: list[str] = field(default_factory=list)
    # Every gate report anomaly seen (ticket 17 F1): a missing/unparsable pytest report,
    # a report without the per-run canary, a report that contradicts the exit status.
    # A gate with an anomaly is RED and the detail lands here and in the run record.
    gate_anomalies: list[str] = field(default_factory=list)


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
    (``final_gate``) with the canary and expected node ids satisfied. ``reason`` names a
    rejection: ``independent-test-not-red`` (it passed on the original — vacuous),
    ``independent-test-unobserved`` (no trustworthy report could be produced), or
    ``independent-test-red-on-final`` (the fix is still wrong). ``content`` and the gate
    reports are kept for the audit trail; ``output`` is the failure context the loop
    feeds into the next attempt.
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


def _escapes_repo(rel: str) -> bool:
    path = Path(rel)
    return path.is_absolute() or ".." in path.parts


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
    if not rel or _escapes_repo(rel):
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


# ---------------------------------------------------------------------------
# independent judge: deterministic filter over the model's attribution
# ---------------------------------------------------------------------------

#: The canonical attribution domain (owner policy: implementation | tests | spec |
#: environment). A judge's label is mapped onto this before anything is credited.
ATTRIBUTIONS: tuple[str, ...] = ("implementation", "tests", "spec", "environment")

#: Aliases a judge model may use for the same four attributions.
_ATTRIBUTION_ALIASES = {
    "implementation": "implementation", "code": "implementation", "source": "implementation",
    "tests": "tests", "test": "tests",
    "spec": "spec", "specification": "spec", "requirement": "spec",
    "environment": "environment", "env": "environment", "harness": "environment",
}

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
    """The DETERMINISTIC FILTER — never trust the model's word alone.

    ``attribution == "tests"`` is honoured ONLY when ``defect`` is non-empty AND names
    the failing test function or an assertion/expectation of the run's own test.
    Anything else is coerced to ``implementation`` and the coercion is recorded
    (``coerced`` + ``coercion_reason``) so the judge can be calibrated later. An
    unknown attribution label is likewise coerced to ``implementation``.
    """
    canonical = _ATTRIBUTION_ALIASES.get(_norm(verdict.attribution))
    if canonical is None:
        return verdict.model_copy(update={
            "attribution": "implementation", "coerced": True,
            "coercion_reason": f"unknown attribution {verdict.attribution!r} coerced to implementation"})
    if canonical == "tests" and not _defect_names_the_test(verdict.defect, request):
        return verdict.model_copy(update={
            "attribution": "implementation", "coerced": True,
            "coercion_reason": ("tests attribution without a defect naming the failing test "
                                "or one of its assertions (deterministic filter)")})
    if canonical != verdict.attribution:
        return verdict.model_copy(update={"attribution": canonical})
    return verdict


def _as_verdict(result: Any) -> JudgeVerdict:
    """Accept a structured verdict, a raw payload dict, or a bare attribution string
    (hand-authored oracles in tests use the string form)."""
    if isinstance(result, JudgeVerdict):
        return result
    if isinstance(result, Mapping):
        return JudgeVerdict(
            attribution=str(result.get("attribution", "implementation")),
            defect=str(result.get("defect", "")),
            raw=str(result.get("raw", "")),
        )
    if isinstance(result, str):
        return JudgeVerdict(attribution=result, raw=result)
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
#: it passed on the original — or it was never collected), not that the fix is wrong.
#: Each earns exactly ONE bounded re-ask of the same fresh-context producer with the
#: verdict as evidence (ticket 17 round 8). ``independent-test-red-on-final`` is a FIX
#: failure and is deliberately NOT repaired: the loop continues with it as context.
_IV_REPAIRABLE: frozenset[str] = frozenset(
    {"independent-test-not-red", "independent-test-unobserved"})


def _iv_repair_request(
    request: IndependentTestRequest, verdict: IndependentTestVerdict
) -> IndependentTestRequest:
    """The ONE bounded repair request: the same fresh-context call re-asked with the
    rejected test and the verdict that rejected it as explicit evidence."""
    return replace(request, previous_test=verdict.content,
                   repair_reason=verdict.reason, repair_detail=verdict.detail)


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


async def _run_iv_gate(
    run_tests: Callable[[Path], Awaitable[ShapedResult] | ShapedResult],
    tree: Mapping[str, str], iv_path: str, iv_content: str,
) -> tuple[ShapedResult, GateReport | None]:
    """Run the existing report gate on a PRIVATE COPY of ``tree`` + the test.

    The copy is a fresh ``tempfile`` directory OUTSIDE the workdir, so the run never sees
    the independent test and the run's own test files are absent (the tree is the
    source-only view). The directory is removed before returning.
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
        res = await _maybe_await(run_tests, root)
    return res, getattr(res, "gate", None)


async def evaluate_independent_test(
    candidate: IndependentTestCandidate,
    original_tree: Mapping[str, str],
    final_tree: Mapping[str, str],
    run_tests: Callable[[Path], Awaitable[ShapedResult] | ShapedResult],
) -> IndependentTestVerdict:
    """The DETERMINISTIC claim condition (ticket 17 round 7): two report gates.

    1. RED ON ORIGINAL: a private copy of the PRE-RUN source plus the test must run and
       FAIL. A test that passes there does not exercise the failure (vacuous) and is
       rejected with ``independent-test-not-red``.
    2. GREEN ON FINAL: a private copy of the FINAL source plus the SAME test must run and
       PASS with the canary and expected node ids satisfied.

    Both snapshots come from the blind source view (``run_tests`` in production is
    :func:`_default_run_tests`, which writes/requires the JUnit report and canary). A test
    the gate cannot observe (no report) is rejected as unobserved.

    The file the model names is a PARAMETER (round 8): it is normalized to a path pytest
    actually collects (:func:`_iv_safe_path`), and the verdict records the requested path
    plus whether a relocation happened.
    """
    requested_path = candidate.path or ""
    iv_path = _iv_safe_path(requested_path)
    relocated = requested_path != iv_path
    common = {"path": iv_path, "requested_path": requested_path, "relocated": relocated,
              "content": candidate.content, "raw": candidate.raw}
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

    final_res, final_gate = await _run_iv_gate(run_tests, final_tree, iv_path, candidate.content)
    if final_gate is None or not final_gate.green:
        detail = (final_gate.detail if final_gate is not None else
                  "the independent test produced no machine-readable report on the final source")
        return IndependentTestVerdict(
            approved=False, reason="independent-test-red-on-final", detail=detail,
            original_gate=orig_gate, final_gate=final_gate,
            node_ids=tuple(final_gate.passed_ids) if final_gate is not None else (),
            output=tuple(getattr(final_res, "excerpts", []) or ()), **common)

    return IndependentTestVerdict(
        approved=True,
        node_ids=(tuple(nid for nid in final_gate.passed_ids
                        if nid.startswith(f"{iv_path}::")) or tuple(final_gate.passed_ids)),
        original_gate=orig_gate, final_gate=final_gate,
        output=tuple(getattr(final_res, "excerpts", []) or ()), **common)


async def _default_run_tests(workdir: Path) -> ShapedResult:
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
    try:
        res = await k_exec(
            ["python3", "-m", "pytest", "-q", *PYTEST_ISOLATION_ARGS,
             "-c", str(neutral_ini), "--rootdir=.", *JUNIT_FAMILY_ARGS,
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
    return {
        "goal": spec.goal,
        "acceptance_criteria": "\n".join(f"- {a}" for a in spec.acs),
        "interfaces": "\n".join(f"- {i}" for i in spec.interfaces),
        "repo_files": json.dumps(_source_view(spec), ensure_ascii=False),
    }


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
    if getattr(env, "status", "unable") != "ok" or not getattr(env, "file_path", ""):
        return None
    kind, problem = _self_test_problem(env, spec, workdir)
    if not problem:
        return env.file_path
    normalized, note = _normalize_test_path(env.file_path, spec, workdir)
    if not note:
        return None
    emit("self_test_relocated", detail=note, requested=env.file_path, used=normalized)
    emit("tolerance_fired", aspect="self_test_path", requested=env.file_path, used=normalized)
    return normalized


def _self_test_problem(env: Any, spec: LeafSpec, workdir: Path) -> tuple[str, str]:
    """Classify a self-test envelope. Returns ``(ledger_kind, problem)``; ``problem``
    is "" when the envelope is a usable new test path."""
    if getattr(env, "status", "unable") != "ok" or not getattr(env, "file_path", ""):
        return "self_test_unavailable", f"status={getattr(env, 'status', 'unknown')}"
    problem = _new_test_problem(env.file_path, spec, workdir)
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
    run_tests: Callable[[Path], Awaitable[ShapedResult] | ShapedResult] | None = None,
    now: Callable[[], float] | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> LeafOutcome:
    clock = now or time.monotonic
    tests = run_tests or _default_run_tests
    # No default judge: a test replacement needs an INDEPENDENT attribution. The
    # model's own word is never enough, so ``judge=None`` means the claim is not
    # credited (deterministic conservative default). A provided judge may return a
    # ``JudgeVerdict`` (or a dict / bare attribution string); its ``tests`` claim is
    # still filtered by :func:`apply_judge_filter` before it is credited.
    attribution = judge
    # ``iv=None`` is the own-test-only basis (``claimed_basis="own-test"``): the green
    # is delivered on the run's own unmodified test. A provided ``iv`` producer adds an
    # INDEPENDENT test whose deterministic two-gate check (red on original, green on
    # final) must approve before any claim (ticket 17 round 7); a missing/malformed/
    # unevaluable independent test never becomes a claim.
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

    async def request_bounded(call: Callable[[], Awaitable[Any]], label: str
                              ) -> tuple[Any | None, str]:
        """Run one envelope request with a bounded malformed-output retry.

        No model failure may crash the leaf: a schema violation, a transport error, or
        any other exception raised by the model/envelope is retried up to
        :data:`ENVELOPE_RETRIES` times. Persistent failure returns reason
        ``"malformed-output"``; an unaffordable retry returns ``"calls"``.
        """
        for attempt in range(ENVELOPE_RETRIES + 1):
            if not spend():
                return None, "calls"
            try:
                return await call(), ""
            except Exception as exc:  # noqa: BLE001 — a model failure is data, not a crash
                emit("envelope_malformed", step=label, attempt=attempt + 1,
                     detail=f"{type(exc).__name__}: {exc}")
        return None, "malformed-output"

    async def iv_verdict_for(
        request: IndependentTestRequest,
        original_tree: Mapping[str, str],
        final_tree: Mapping[str, str],
    ) -> tuple[IndependentTestVerdict | None, str]:
        """Author and evaluate ONE independent test (round 8).

        One bounded authoring call (malformed-output retries apply) plus the two
        deterministic gates. Returns ``(verdict, "")`` or ``(None, failure_reason)``
        where ``failure_reason`` is ``"calls"`` or ``"malformed-output"`` — the caller
        maps it to the same honest stop the other envelope steps use.
        """
        candidate_test, failure = await request_bounded(
            partial(_call_iv, iv, request), "independent-test")
        if failure:
            return None, failure
        verdict = await _maybe_await(
            evaluate_independent_test, candidate_test, original_tree, final_tree, tests)
        return verdict, ""

    def record_iv(verdict: IndependentTestVerdict) -> None:
        """Count, persist, and surface ONE independent-test verdict (round 8).

        The relocation is recorded exactly like the self-test's parameter-layer
        tolerance (``independent_test_relocated`` + ``tolerance_fired`` + a refusal
        note), so a naming slip is visible after the fact instead of silently becoming
        ``independent-test-unobserved``.
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
        emit("independent_test_verdict", approved=verdict.approved,
             reason=verdict.reason, path=verdict.path,
             original_gate=(verdict.original_gate.anomaly
                            if verdict.original_gate is not None else None),
             final_gate=(verdict.final_gate.anomaly
                         if verdict.final_gate is not None else None),
             raw=verdict.raw)

    def stop(sig: str, reason: str, why: str, *, exhausted: bool = False,
             parent: bool = False) -> None:
        nonlocal signal, exhaustion_reason, stop_reason, node_exhausted, needs_parent
        signal, exhaustion_reason, stop_reason = sig, reason, why
        node_exhausted = exhausted
        needs_parent = parent

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

    def write_self_test(rel: str, content: str) -> bool:
        """Write the run's own test; a filesystem refusal stops honestly (F3)."""
        try:
            _write(workdir, rel, content)
        except WriteShapeRefused as exc:
            emit("write_shape_refused", path=exc.path, reason=exc.detail)
            refusals.append(f"{exc.path}: {exc.detail} (self-test)")
            stop("honest-failure", f"unwritable self-test target: {exc.detail}", "write-shape")
            return False
        return True

    def refuse_self_test(env: Any, message: str, reason: str, *, open_question: bool) -> None:
        """Honest stop for a self-test envelope with no usable landing spot.

        A write-SHAPE problem (existing directory, path under a file, embedded NUL
        byte, over-long name) has no safe normalization here, so it takes the
        write-shape stop; anything else is a logic-level self-test refusal.
        """
        path = getattr(env, "file_path", "") or ""
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

    def finish() -> LeafOutcome:
        reason = exhaustion_reason
        if last_iv_reason and not claimed:
            reason = f"{reason}; independent-test {last_iv_reason}" if reason else f"independent-test {last_iv_reason}"
        last = iv_verdicts[-1] if iv_verdicts else None
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
            refusals=list(refusals),
            gate_anomalies=list(gate_anomalies),
        )

    # ---- deadline before the first call (an already-expired budget writes nothing)
    if budget.expired(clock()):
        stop("handover", "deadline", "deadline")
        return finish()

    # ---- step 1: the run's own test, RUN and required to be RED ON ARRIVAL ----
    self_env, failure = await request_bounded(
        partial(_request_write, model, _self_test_artifacts(spec), _SELF_TEST_QUESTION),
        "self-test")
    if failure == "calls":
        stop("honest-failure", "call-budget", "calls")
        return finish()
    if failure:
        stop("honest-failure", "malformed-output after bounded retries", "malformed-output")
        return finish()
    normalized = _relocate_self_test(self_env, spec, workdir, emit)
    if normalized is None:
        refuse_self_test(self_env, "self-test-refused", "self-test", open_question=True)
        return finish()
    if normalized != getattr(self_env, "file_path", ""):
        _, problem = _self_test_problem(self_env, spec, workdir)
        refusals.append(f"{getattr(self_env, 'file_path', '')}: {problem} -> "
                        f"{normalized} (self-test relocated)")
    if not write_self_test(normalized, self_env.content):
        return finish()
    self_test = normalized

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
        retry_env, failure = await request_bounded(
            partial(_request_write, model,
                    _retry_self_test_artifacts(spec, previous_path, previous_content),
                    _RETRY_SELF_TEST_QUESTION),
            "self-test-retry")
        if failure == "calls":
            stop("honest-failure", "call-budget", "calls")
            return finish()
        if failure:
            stop("honest-failure", "malformed-output after bounded retries", "malformed-output")
            return finish()
        normalized = _relocate_self_test(retry_env, spec, workdir, emit)
        if normalized is None:
            refuse_self_test(retry_env, "no-red-target", "no-red-target", open_question=False)
            return finish()
        if normalized != getattr(retry_env, "file_path", ""):
            _, problem = _self_test_problem(retry_env, spec, workdir)
            refusals.append(f"{getattr(retry_env, 'file_path', '')}: {problem} -> "
                            f"{normalized} (self-test relocated)")
        if not write_self_test(normalized, retry_env.content):
            return finish()
        self_test = normalized
        res = await _maybe_await(tests, workdir)
        gate = record_gate(res)
        if _is_green(res):
            emit("self_test_green_on_arrival", path=self_test)
            (workdir / self_test).unlink(missing_ok=True)
            self_test = None
            stop("honest-failure", "no-red-target", "no-red-target")
            return finish()
    if _exit_code(res) is None or (gate is not None and not gate.observed):
        # We could not trust an observation of the run's own tests: a transport error /
        # sandbox block, or a gate report that is missing or holds no testcase. Nothing
        # may be recorded as a red, so no target is kept.
        emit("self_test_unverified", path=self_test, reason="tests did not run")
        (workdir / self_test).unlink(missing_ok=True)
        self_test = None
        stop("honest-failure", "self-test-unverified", "self-test")
        return finish()
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
            stop("honest-failure", "malformed-output after bounded retries", "malformed-output")
            break

        # the model claims its own TEST is wrong -> independent attribution only
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
                # a FRESH-CONTEXT judge call, wrapped like every other envelope request.
                # Conversion/validation errors are malformed output too, so they are
                # raised inside the bounded call and get the same retry/stop treatment.
                jr = _judge_request(spec, workdir, self_test, last_excerpts, env, baseline)
                raw_verdict, failure = await request_bounded(
                    partial(_call_judge, attribution, jr), "judge")
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    break
                if failure:
                    stop("honest-failure", "malformed-output after bounded retries",
                         "malformed-output")
                    break
                verdict = apply_judge_filter(raw_verdict, jr)
                judge_verdicts.append(verdict)
                emit("judge_verdict", attribution=verdict.attribution, defect=verdict.defect,
                     coerced=verdict.coerced, raw=verdict.raw)
                if verdict.coerced:
                    emit("judge_coerced", reason=verdict.coercion_reason)
                pending_verdict = verdict
                attribution_result = verdict.attribution
                if attribution_result == "spec":
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
                    break
                if attribution_result == "tests" and self_test:
                    repaired, failure = await request_bounded(
                        partial(_repair_test, model, spec, workdir, self_test,
                                last_excerpts, env),
                        "test-rewrite")
                    if failure == "calls":
                        stop("honest-failure", "call-budget", "calls")
                        break
                    if failure:
                        stop("honest-failure", "malformed-output after bounded retries",
                             "malformed-output")
                        break
                    if (getattr(repaired, "status", "unable") == "ok"
                            and getattr(repaired, "content", "")):
                        try:
                            _write(workdir, self_test, repaired.content)
                        except WriteShapeRefused as exc:
                            emit("write_shape_refused", path=exc.path, reason=exc.detail)
                            refusals.append(f"{exc.path}: {exc.detail} (test rewrite)")
                            stop("honest-failure",
                                 f"unwritable test rewrite: {exc.detail}", "write-shape")
                            break
                        test_rewrites += 1
                        rres = await _maybe_await(tests, workdir)
                        record_gate(rres)
                        repair_excerpts = excerpts_of(rres)
                        if _is_green(rres):
                            # a rewrite that passes on arrival does not pin the goal:
                            # leave no bogus target behind
                            emit("test_rewrite_green_on_arrival", path=self_test)
                            (workdir / self_test).unlink(missing_ok=True)
                            self_test = None
                            stop("honest-failure", "no-red-target", "no-red-target")
                            break
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
                        continue
                    emit("test_repair_unavailable",
                         status=getattr(repaired, "status", "unknown"))
                # implementation / environment / uncredited: fall through to the red path

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

        signature = failure_signature(last_excerpts, last_excerpts)
        candidate = Attempt(
            node_id="leaf",
            layer=esc.layer,
            strategy=esc.strategy or "L1-resample",
            claimed_delta=getattr(env, "comment", "") or "",
            failure_signature=signature,
            touched_files=[source_rel] if wrote else [],
            outcome="pass" if _is_green(res) else "fail",
            judge=pending_verdict,
        )
        if not wrote:
            candidate.verdict = "same"
        else:
            candidate.verdict = prefilter(attempts, candidate)

        if candidate.outcome == "pass":
            attempts.append(candidate)
            if test_rewrites:
                # A green after the run REPLACED its own test is not a claim: the
                # implementation satisfied a substituted test, so the result is
                # unverified (ticket 17 round 4). Keep the rewrite machinery and the
                # judge filter — they now stop honestly and hand the node a status.
                emit("leaf_green_after_test_rewrite", strategy=esc.strategy)
                stop("green-after-test-rewrite", "", "green-after-test-rewrite")
                break
            if iv is None:
                # Own-test-only basis (conservative baseline): the run's OWN unmodified
                # test went green. With --iv the driver injects the independent test that
                # must pass its two-gate check before any claim (ticket 17 round 7).
                claimed = True
                claimed_basis = "own-test"
                stop("green", "", "green")
                emit("leaf_green", strategy=esc.strategy, after_test_rewrite=False)
                break
            if not can_afford(1):
                stop("honest-failure", "call-budget", "calls")
                break
            iv_request = _iv_request(spec, workdir, baseline)
            original_tree = dict(spec.files)
            final_tree = _repo_view(spec, workdir, tuple(baseline))
            verdict, failure = await iv_verdict_for(iv_request, original_tree, final_tree)
            if failure == "calls":
                stop("honest-failure", "call-budget", "calls")
                break
            if failure:
                # An independent test that could not be produced never becomes a claim.
                stop("honest-failure", "independent-test-unverified", "malformed-output")
                break
            record_iv(verdict)
            # Bounded IV repair (ticket 17 round 8): a defective TEST — vacuous (it
            # passed on the original) or uncollected — gets exactly ONE re-ask of the
            # same fresh-context producer with the verdict as evidence, then the two
            # gates run again. ``independent-test-red-on-final`` is a FIX failure, not a
            # test defect: it is never repaired here and the loop continues with it.
            if not verdict.approved and verdict.reason in _IV_REPAIRABLE and can_afford(1):
                iv_repairs += 1
                emit("independent_test_repair", reason=verdict.reason,
                     detail=verdict.detail, requested=verdict.requested_path)
                repaired, failure = await iv_verdict_for(
                    _iv_repair_request(iv_request, verdict), original_tree, final_tree)
                if failure == "calls":
                    stop("honest-failure", "call-budget", "calls")
                    break
                if failure:
                    stop("honest-failure", "independent-test-unverified", "malformed-output")
                    break
                record_iv(repaired)
                verdict = repaired
            if verdict.approved:
                claimed = True
                claimed_basis = "own-test+independent-test"
                stop("green", "", "green")
                emit("leaf_green", strategy=esc.strategy, after_test_rewrite=False)
                break
            # Rejected: the independent test's output is the next attempt's failure
            # context and the loop CONTINUES (never a claim, never silently dropped).
            last_iv_reason = f"{verdict.reason}: {verdict.detail}"
            last_excerpts = [f"independent test rejected ({verdict.reason}): {verdict.detail}",
                             *(verdict.output or ())]
            attempts.append(Attempt(
                node_id="leaf", layer=esc.layer, strategy=esc.strategy or "L1-resample",
                claimed_delta=f"independent test: {verdict.reason}",
                failure_signature=failure_signature(last_excerpts, last_excerpts),
                touched_files=[source_rel] if wrote else [],
                outcome="fail", verdict="novel"))
            emit("independent_test_rejected", strategy=esc.strategy,
                 reason=verdict.reason, detail=verdict.detail)
            rung += 1
            continue

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
    rel = getattr(env, "file_path", "") or ""
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
    proposed = getattr(env, "file_path", "") or ""
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
