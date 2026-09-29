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
   refused/unestablished self-test, or an exhausted call budget.

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
- **No false success, ever.** ``exit == 0`` is the ONLY green condition; a
  ``None`` exit (transport error) and a policy-blocked shaped result are red. The
  run's own ``run_tests`` is the only thing that can set ``claimed=True``. A model
  ``comment`` claiming green is irrelevant.
- **A test may only be REPLACED, never weakened, and only with an independent
  judge.** The model's own "the test is wrong" claim is never enough: without an
  injected independent judge the claim is not credited and the failure is treated
  as an implementation failure (deterministic conservative default). When the judge
  does attribute to the tests, the test is re-derived from scratch and must be RED
  ON ARRIVAL again before the loop continues.
- **No "give up".** Exhaustion is delegated to :func:`harness.attempts.exhausted`,
  so a same-verdict tail without a structural lever or three exercised layers keeps
  the node alive. The leaf's ``exhausted`` flag is set only by that function; a call
  budget or a deadline is a distinct, honestly-named stop (``stop_reason``).
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.attempts import Attempt, failure_signature, layers_tried, prefilter
from harness.attempts import exhausted as attempts_exhausted
from harness.budget import Budget
from harness.checks import diagnose_test_output
from harness.exec import ShapedResult
from harness.exec import exec as k_exec
from harness.questions import Question, QuestionQueue
from harness.runner import llm_step, note
from harness.staging import is_test_path

__all__ = [
    "LADDER",
    "STRATEGY_LAYER",
    "Escalation",
    "JudgeRequest",
    "LeafOutcome",
    "LeafSpec",
    "escalate",
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
STOP_REASONS: tuple[str, ...] = (
    "calls",         # the call budget is spent
    "deadline",      # the wall-clock window closed (handover)
    "attempts",      # node exhaustion or the bounded-attempt cap
    "ladder",        # no rung is left to advance to
    "spec-bubble",   # the judge attributed the failure to the specification
    "no-red-target", # the run's own test could not be made to fail on arrival
    "self-test",     # the run's own test could not be written at a safe path
    "green",         # the run's own tests exited 0
)

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

    ``claimed`` is True only if the run's own tests exited 0. ``stop_reason`` is the
    single explicit stop (:data:`STOP_REASONS`); ``exhaustion_reason`` keeps the
    human-readable detail. ``wasted_escalations`` surfaces refusals that were only
    visible in the process-global ledger before. ``test_rewrites`` /
    ``own_test_mutated`` record a judge-authorized replacement of the run's own test.
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


@dataclass(frozen=True)
class JudgeRequest:
    """Everything an independent attribution judge may see (never grader paths)."""

    goal: str
    failure: str
    test_path: str
    test_content: str
    files: dict[str, str]


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


def _new_test_problem(rel: str, spec: LeafSpec, workdir: Path) -> str:
    """Why ``rel`` may not be the run's own test path ("" when it may)."""
    if _escapes_repo(rel):
        return "escapes the repository"
    if rel in set(spec.grader_paths):
        return "grader-owned path"
    if not is_test_path(rel):
        return "not a test path"
    if rel in spec.files or (workdir / rel).exists():
        return "already exists — never overwrite shipped files"
    return ""


def _source_write_problem(rel: str, spec: LeafSpec, self_test: str | None) -> str:
    if _escapes_repo(rel):
        return "escapes the repository"
    if rel in set(spec.grader_paths):
        return "grader-owned path"
    if self_test is not None and rel == self_test:
        return "the run's own test file (outside the implementation seam)"
    if is_test_path(rel):
        return "a test path (outside the implementation seam)"
    return ""


def _write(workdir: Path, rel: str, content: str) -> Path:
    target = workdir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
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
    """``exit == 0`` is the ONLY green condition (owner policy).

    A ``None`` exit (transport error), a policy-blocked result, and a non-int exit
    (a bare ``False`` is not an exit code) are all red. This mirrors
    ``ShapedResult.ok`` (``harness/exec.py``); ignoring ``policy_blocked`` here
    contradicted this docstring and was the one crack an independent verification
    pass found by crafting ``policy_blocked=True, exit=0``.
    """
    code = _exit_code(res)
    if not isinstance(code, int) or isinstance(code, bool) or code != 0:
        return False
    return not getattr(res, "policy_blocked", False)


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


async def _maybe_await(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def _default_run_tests(workdir: Path) -> ShapedResult:
    return await k_exec(["python3", "-m", "pytest", "-q"], workdir, provenance="kernel")


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
    judge: Callable[[JudgeRequest], Awaitable[str] | str] | None = None,
    run_tests: Callable[[Path], Awaitable[ShapedResult] | ShapedResult] | None = None,
    now: Callable[[], float] | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> LeafOutcome:
    clock = now or time.monotonic
    tests = run_tests or _default_run_tests
    # No default judge: a test replacement needs an INDEPENDENT attribution. The
    # model's own word is never enough, so ``judge=None`` means the claim is not
    # credited (deterministic conservative default).
    attribution = judge
    workdir = Path(workdir)
    started = clock()

    calls = 0
    attempts: list[Attempt] = []
    queue = QuestionQueue()
    rung = 0
    claimed = False
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

    def stop(sig: str, reason: str, why: str, *, exhausted: bool = False,
             parent: bool = False) -> None:
        nonlocal signal, exhaustion_reason, stop_reason, node_exhausted, needs_parent
        signal, exhaustion_reason, stop_reason = sig, reason, why
        node_exhausted = exhausted
        needs_parent = parent

    def finish() -> LeafOutcome:
        return LeafOutcome(
            claimed=claimed,
            signal=signal,
            attempts=list(attempts),
            calls=calls,
            wall_s=round(clock() - started, 3),
            self_test=self_test,
            questions=queue.all(),
            exhausted=node_exhausted,
            exhaustion_reason=exhaustion_reason,
            layers_used=list(dict.fromkeys(a.layer for a in attempts)),
            stop_reason=stop_reason,
            wasted_escalations=list(wasted_escalations),
            test_rewrites=test_rewrites,
            own_test_mutated=test_rewrites > 0,
            needs_parent=needs_parent,
        )

    # ---- deadline before the first call (an already-expired budget writes nothing)
    if budget.expired(clock()):
        stop("handover", "deadline", "deadline")
        return finish()

    # ---- step 1: the run's own test, RUN and required to be RED ON ARRIVAL ----
    if not spend():
        stop("honest-failure", "call-budget", "calls")
        return finish()
    self_env = await _request_write(model, _self_test_artifacts(spec), _SELF_TEST_QUESTION)
    kind, problem = _self_test_problem(self_env, spec, workdir)
    if problem:
        emit(kind, path=getattr(self_env, "file_path", ""), reason=problem)
        queue.open(
            f"self-test:{spec.goal[:40]}",
            "the run could not write its own test at a safe path",
            default_choice="park until a writable test path is available",
        )
        stop("honest-failure", f"self-test-refused: {problem}", "self-test")
        return finish()
    _write(workdir, self_env.file_path, self_env.content)
    self_test = self_env.file_path

    res = await _maybe_await(tests, workdir)
    if _is_green(res):
        # A test that passes on arrival does not exercise the failure. Re-ask ONCE
        # with that evidence; never emit red=True without having observed a red.
        emit("self_test_green_on_arrival", path=self_test)
        previous_path = self_test
        previous_content = _read(workdir, self_test)
        (workdir / self_test).unlink(missing_ok=True)
        self_test = None
        if not spend():
            stop("honest-failure", "call-budget", "calls")
            return finish()
        retry_env = await _request_write(
            model,
            _retry_self_test_artifacts(spec, previous_path, previous_content),
            _RETRY_SELF_TEST_QUESTION,
        )
        kind, problem = _self_test_problem(retry_env, spec, workdir)
        if problem:
            emit(kind, path=getattr(retry_env, "file_path", ""), reason=problem)
            stop("honest-failure", f"no-red-target: {problem}", "no-red-target")
            return finish()
        _write(workdir, retry_env.file_path, retry_env.content)
        self_test = retry_env.file_path
        res = await _maybe_await(tests, workdir)
        if _is_green(res):
            emit("self_test_green_on_arrival", path=self_test)
            (workdir / self_test).unlink(missing_ok=True)
            self_test = None
            stop("honest-failure", "no-red-target", "no-red-target")
            return finish()
    if _exit_code(res) is None:
        # We could not run the run's own tests at all (transport error / sandbox
        # block): nothing was observed, so nothing may be recorded as a red.
        emit("self_test_unverified", path=self_test, reason="tests did not run")
        (workdir / self_test).unlink(missing_ok=True)
        self_test = None
        stop("honest-failure", "self-test-unverified", "self-test")
        return finish()
    last_excerpts = list(getattr(res, "excerpts", []) or [])
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
        emit("leaf_attempt", n=len(attempts) + 1, strategy=esc.strategy, layer=esc.layer,
             mode=mode)
        if mode == "M1":
            _erase_draft(workdir, baseline)
        if not spend():
            stop("honest-failure", "call-budget", "calls")
            break
        env = await _request_write(
            model,
            _implement_artifacts(spec, workdir, esc, attempts, last_excerpts, self_test,
                                 mode, baseline),
            _implement_question(mode, esc),
        )

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
                if not spend():
                    stop("honest-failure", "call-budget", "calls")
                    break
                attribution_result = await _attribute(
                    attribution, spec, workdir, self_test, last_excerpts, env, emit)
                if attribution_result == "spec":
                    attempts.append(Attempt(
                        node_id="leaf", layer="spec", strategy=esc.strategy,
                        claimed_delta="judge attributed the failure to the spec",
                        outcome="fail", verdict="novel"))
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
                    if not spend():
                        stop("honest-failure", "call-budget", "calls")
                        break
                    repaired = await _repair_test(
                        model, spec, workdir, self_test, last_excerpts, env)
                    if (getattr(repaired, "status", "unable") == "ok"
                            and getattr(repaired, "content", "")):
                        _write(workdir, self_test, repaired.content)
                        test_rewrites += 1
                        rres = await _maybe_await(tests, workdir)
                        repair_excerpts = list(getattr(rres, "excerpts", []) or [])
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
                            outcome="fail")
                        repair_attempt.verdict = prefilter(attempts, repair_attempt)
                        attempts.append(repair_attempt)
                        emit("test_rewritten", path=self_test, verdict=repair_attempt.verdict)
                        continue
                    emit("test_repair_unavailable",
                         status=getattr(repaired, "status", "unknown"))
                # implementation / environment / uncredited: fall through to the red path

        # normal path: write the source candidate (guarded) and run the tests
        wrote, source_rel, refusal = _write_candidate(env, spec, workdir, self_test, baseline)
        if refusal:
            last_excerpts = [f"implement refused: {refusal}"]
        res = await _maybe_await(tests, workdir) if wrote else None
        if res is not None:
            last_excerpts = list(getattr(res, "excerpts", []) or [])

        signature = failure_signature(last_excerpts, last_excerpts)
        candidate = Attempt(
            node_id="leaf",
            layer=esc.layer,
            strategy=esc.strategy or "L1-resample",
            claimed_delta=getattr(env, "comment", "") or "",
            failure_signature=signature,
            touched_files=[source_rel] if wrote else [],
            outcome="pass" if _is_green(res) else "fail",
        )
        if not wrote:
            candidate.verdict = "same"
        else:
            candidate.verdict = prefilter(attempts, candidate)

        if candidate.outcome == "pass":
            attempts.append(candidate)
            claimed = True
            stop("green-after-test-rewrite" if test_rewrites else "green", "", "green")
            emit("leaf_green", strategy=esc.strategy, after_test_rewrite=bool(test_rewrites))
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
) -> tuple[bool, str, str]:
    """Apply an implementation envelope through the blind write guard.

    Returns ``(wrote, rel, refusal)``. A refusal does not touch the tree; the loop
    records it as a red attempt and lets the ladder advance.
    """
    if getattr(env, "status", "unable") != "ok":
        return False, "", f"status={getattr(env, 'status', 'unknown')}"
    rel = getattr(env, "file_path", "") or ""
    if not rel:
        return False, "", "no file_path"
    problem = _source_write_problem(rel, spec, self_test)
    if problem:
        return False, "", problem
    if rel not in baseline:
        target = workdir / rel
        baseline[rel] = target.read_text() if target.exists() else None
    _write(workdir, rel, env.content)
    return True, rel, ""


async def _attribute(
    attribution: Callable[[JudgeRequest], Awaitable[str] | str],
    spec: LeafSpec,
    workdir: Path,
    self_test: str | None,
    last_excerpts: Sequence[str],
    env: Any,
    emit: Callable[..., None],
) -> str:
    request = JudgeRequest(
        goal=spec.goal,
        failure="\n".join(last_excerpts) or (getattr(env, "comment", "") or ""),
        test_path=self_test or "",
        test_content=_read(workdir, self_test),
        files=_repo_view(spec, workdir),
    )
    result = await _maybe_await(attribution, request)
    emit("judge_attribution", attribution=result)
    return result if result in ("implementation", "tests", "spec", "environment") else "implementation"
