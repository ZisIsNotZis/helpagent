# 17 — v2 leaf loop: a node that owns its test, iterates red→green, and never lies

Status: in-progress (delegated to the worker lane)
Need-review: yes (independent reviewer lane, fresh context)
Need-test-cases: yes (mechanics pinned with the scripted fake model, no live server)

## Why

The first honest (blind) measurement scored 0/3 while the contaminated v1 numbers
claimed ~93%: the old flow was carried by the grader's own tests, which the harness
could read. The blind protocol then exposed that the self-test step had been dead
code and that the router DROPPED a red self-test instead of using it as the target.
This ticket builds the replacement: one leaf node that owns its own verification.

## Deliverables (one writer lane)

- `harness/leaf.py` — the leaf loop.
- `bench/v2_leaf.py` — blind CLI driver: stage source-only, run the leaf, then score
  externally with `bench/external_score.py`; report claimed-vs-actual quadrant.
- `tests/unit/test_v2_leaf.py` — mechanics pinned with `harness/fake_model.py`.
- Must not regress: `uv run pytest -q` fully green (171 cases before this ticket).

## Contract

```python
@dataclass(frozen=True)
class LeafSpec:
    goal: str
    files: dict[str, str]        # blind view: source only
    acs: list[str]
    interfaces: list[str]
    grader_paths: tuple[str, ...] = ()   # owned by the grader: never shown, never writable

@dataclass
class LeafOutcome:
    claimed: bool                # True ONLY if the run's own pytest exited 0
    signal: str                  # "green" | "green-after-test-rewrite" | "honest-failure"
                                 # | "exhausted" | "handover" | "bubble"
    attempts: list[Attempt]
    calls: int
    wall_s: float
    self_test: str | None
    questions: list[Question]
    exhausted: bool
    exhaustion_reason: str       # human-readable detail of the stop
    layers_used: list[str]
    stop_reason: str             # "calls" | "deadline" | "attempts" | "ladder"
                                 # | "spec-bubble" | "no-red-target" | "self-test" | "green"
    wasted_escalations: list[Escalation]   # surfaced, not just in the ledger
    test_rewrites: int           # judge-authorized rewrites of the run's own test
    own_test_mutated: bool       # True iff test_rewrites > 0
    needs_parent: bool           # a spec bubble: the parent owns the next move

async def run_leaf(model, spec, workdir: Path, budget: Budget, *,
                   judge=None, run_tests=..., now=..., on_event=None) -> LeafOutcome
```

Fix-round policy (owner decision — the loop must be unable to manufacture a false
success):

- **RED ON ARRIVAL is required.** After the self-test is written it is RUN before
  implementing. If it exits 0 it does not exercise the failure: re-ask ONCE with that
  evidence; if the replacement is green too, stop (signal `honest-failure`,
  `stop_reason="no-red-target"`, `claimed=False`). `red=True` is never emitted
  without having observed a red (no blind assertion).
- **A test may only be REPLACED, never weakened, and only with an independent judge.**
  `judge=None`, or a judge that does not independently attribute to the tests, does
  NOT credit the model's own "the test is wrong" claim: the failure is treated as an
  implementation failure and the ladder advances. When the judge does attribute to
  tests, the test is re-derived from scratch and must be red on arrival again.
- **Wasted escalations are first-class.** Refusals appear on `LeafOutcome` and in the
  persisted run record (`bench/v2_leaf.py` run.json).
- **`exit == 0` is the ONLY green.** `exit=None` (transport error) and a
  policy-blocked shaped result are both red.
- **No `BudgetError` mid-run.** A multi-call escalation (judge + rewrite) checks the
  remaining calls before spending; without them it stops with `stop_reason="calls"`.

Fixed steps (DESIGN §10.1 — no step fuses, no step picks its own depth):

1. **self-test** — the model writes ITS OWN test at a new TEST path
   (`harness.staging.is_test_path`; grader-owned, escaping, existing, and non-test
   paths are refused). A fresh red is EXPECTED, VERIFIED by running the test, and the
   file is KEPT as the target (the v1 defect: it was dropped). A green-on-arrival test
   is re-asked once, then the run stops with `no-red-target`.
2. **attempt loop**, bounded by `Budget` and the bounded-attempt rule (3 x files,
   cap 9; DESIGN §4.8):
   a. implement (mode M2 first: keep the draft, ask "do you have a new idea?";
      then M1: erase the draft, regenerate with the failure history as intelligence);
   b. run the run's own tests (deterministic; only `exit == 0` is green);
   c. green -> stop, `claimed=True`, `signal="green"` (or
      `green-after-test-rewrite` once a judge-authorized rewrite happened);
   d. red -> build an `Attempt` (failure signature from failing test ids + excerpt
      shapes, claimed delta, files touched, layer) and run `harness.attempts.prefilter`;
   e. if the model claims the TEST is wrong, ask the judge for attribution
      (implementation / tests / spec / environment) ONLY when an independent `judge`
      was injected. "tests" -> re-derive the test from scratch, require it red on
      arrival, and record it as a real (`layer="tests"`) attempt with a genuine
      prefilter verdict — an identical repeat is refused as `wasted`. "spec" -> stop,
      `signal="bubble"`, `needs_parent=True`, and bubble to the parent. No credit
      without the judge: treat the claim as an implementation failure.
3. **escalation ladder L1-L5** (`escalate`): L1 more samples -> L2 guided
   decomposition -> L3 deeper exploration -> L4 deterministic diagnosis
   (`harness.checks.diagnose_test_output`) -> L5 independent judge/review.
   INVARIANT: an escalation that neither adds information nor shrinks the unit is
   NOT executed — it is recorded as `wasted` and the ladder advances. Never repeat
   an identical attempt (T-31 burned 9 identical retries in v1).
4. **stops** (`stop_reason`): green | node `exhausted` (via
   `harness.attempts.exhausted`) | deadline handover (`budget.expired()` at entry OR
   in-loop -> `signal="handover"`, tree kept, nothing written before the first call) |
   `calls` | `ladder` | `no-red-target` | `self-test`.
   There is no "give up": exhaustion needs the same-verdict tail AND a structural
   lever tried or >=3 layers exercised.
5. non-blocking questions via `harness/questions.py`; a question never blocks, and
   the run proceeds on a recorded reversible default.

Invariants to pin as tests (>= 12 cases):

- a red self-test is RUN on arrival, kept, and never emitted `red=True` without an
  observed red (regression pin for the dead-step/dropped-test defect);
- a green-on-arrival self-test is re-asked ONCE and then stops `no-red-target`
  (never `claimed`);
- grader paths never appear in the prompt/artifacts/grounding and cannot be written;
- a non-test self-test path is refused (`is_test_path`);
- `claimed=True` only when the run's own test exits 0 (no false success, ever), and
  `exit=None` (transport) and policy-blocked are both red;
- judge `None` + a "test is wrong" claim never credits a test replacement;
- judge attribution "tests" re-derives the test, requires red-on-arrival, and a later
  green is `green-after-test-rewrite` with `own_test_mutated=True`;
- judge attribution "spec" yields `signal="bubble"` + `needs_parent=True` and does not
  burn remaining budget;
- a repeat escalation with an identical signature + files + no new claim is refused
  and recorded as `wasted`, and the ladder still advances — including an identical
  repeated test rewrite;
- an escalation that cannot afford its calls stops cleanly with `stop_reason="calls"`
  (no `BudgetError` mid-run);
- an already-expired deadline before step 1 writes nothing (`handover`);
- wasted escalations surface on `LeafOutcome` and in the persisted run record;
- exhaustion refuses while a structural lever is untried;
- budget exhaustion and deadline expiry both stop the loop and are distinguishable;
- the whole mechanics run against `harness/fake_model.py` with no live server.

## Non-goals

- No tree/decomposition, no parallelism, no rewriting of the legacy `golden_bugfix`
  pipeline (it stays as the v1 reference), no corpus-test access of any kind.

## Round log

- 2026-09-29 lane `leaf` (worker): first implementation, 18 tests, suite 198 green.
- 2026-09-29 lane `risks` (Designer, read-only) + lane `code-review` (reviewer, read-only):
  found the dominant false-success vector (a run could repair its own test to green —
  self-grading, i.e. the worst quadrant) plus one P1 invariant bypass.
- 2026-09-29 supervisor decision (recorded in DESIGN §10.3/§10.4): red-on-arrival required;
  tests may be replaced but never weakened and only by an independent judge; `exit == 0` is
  the only green; six explicit stop reasons; wasted escalations in the record.
- 2026-09-29 lane `fixes` (worker) + lane `verify` (Designer with shell, adversarial):
  10/10 policies verified by running the suite and by actively trying to forge a green
  (green-on-arrival, weakened test, exit=None, policy_blocked) — none succeeded. One real
  crack remained: `_is_green` ignored `policy_blocked`/non-int exits.
- 2026-09-29 supervisor: closed that crack, made `red=True` conditional on an observed red
  (transport error now stops as `self-test-unverified` and leaves no file), removed the
  bogus target left by a vacuous rewrite, pinned all three with tests. Suite **211 green**
  (`tests/unit/test_v2_leaf.py` = 31 cases).
