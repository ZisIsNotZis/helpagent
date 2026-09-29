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
- 2026-09-29 lane `worker` (round 6, adversarial findings F1-F3): **the process exit status
  stopped being evidence.** Both gates (the leaf's own pytest and the grader's own
  verification) now require a JUnit report — `--junitxml` into a private `mkdtemp` OUTSIDE
  the repository — with at least one testcase, zero failures and zero errors, the EXPECTED
  test file(s) all passed, and a per-run RANDOM canary node id (a generated test the run
  never saw). Any anomaly is RED and recorded as `gate_report_anomaly` with the detail; the
  corpus `checks.py` is NOT modified — `bench/external_score.py` adds its own report gate and
  records `suspected_contaminated_grade` when the corpus check exits 0 but the report does
  not. F2: the driver passes the corpus `UNTOUCHED` set into `LeafSpec.grader_paths` (union
  with the staged-owned paths), so the leaf refuses exactly what the grader restores (T-31
  `api/__init__.py`). F3: an embedded NUL byte and an over-long file name are converted into
  the honest write-shape refusal instead of crashing. `bench/v2_sweep.py` gains
  `--judge/--no-judge` and `--falsify/--no-falsify`, forwarded to the driver. Suite **284
  green**.
- 2026-09-29 lane `worker` (round 7): **the round-4 falsifier was a text opinion — the blind
  8-task measurement showed it never approved once (actual 4/8, claimed 0/8, 69 calls), so
  the harness never claimed even when it succeeded, and its rejections were unreliable
  (invented counterexamples, self-contradiction, "unable: no acceptance criteria were
  injected"). Replaced with a DETERMINISTIC INDEPENDENT TEST. A fresh-context model call
  (`model_independent_test`, §10 `write_test`, `fresh=True`) sees the goal, the extracted
  ACs, and the ORIGINAL and FINAL source of the changed files — never the run's own test
  and never a grader path — and writes its own test. The harness runs it via the existing
  report gate TWICE on private `tempfile` copies (never the workdir): RED ON ORIGINAL
  (vacuous ⇒ `independent-test-not-red`) and GREEN ON FINAL (canary + expected node ids);
  `claimed=True` only when both hold and `own_test_mutated` is False, with
  `claimed_basis="own-test+independent-test"`, the test source, its node ids, and both gate
  reports in the record. A rejection becomes the next attempt's failure context and the
  loop continues; a test that cannot be produced/afforded/evaluated leaves `claimed=False`.
  The falsifier seam, its schema reuse, and `--falsify/--no-falsify` are removed;
  `--iv/--no-iv` (default ON) replaces them in `bench/v2_leaf.py` and `bench/v2_sweep.py`.
  ACs: `build_spec` now extracts acceptance criteria from `request.md` deterministically
  (one per requirement sentence / bullet) and feeds them to the self-test, implement,
  judge, and independent-test calls; the raw text lands in the run record. Suite **296
  green**.
- 2026-09-29 lane `leaf` (rounds 8-10, worker): round 8 made the independent test's FILE
  NAME a harness parameter (relocate to a collectible path, record the relocation) so a
  naming slip can never be `independent-test-unobserved`. Round 9 added acceptance-criteria
  coverage as a deterministic NAME check (every index 1..N must appear in a collected node
  id) with a one-shot repair. An independent adversarial pass proved name-only coverage
  proves only that the criterion was NAMED: one real test plus placeholders
  (`test_ac2_placeholder`/`test_ac3_placeholder` asserting True), one function carrying
  all indices, and a `parametrize(ids=["ac1",...])` all approved while a grader for the
  unexercised criterion still failed. Round 10 **replaces the name rule with
  PER-CRITERION DISCRIMINATION**: for every index the SAME pytest `-k ac<i>` selection
  runs through the report gate on the original and the final tree and must collect an
  independent-test node, FAIL on the original and PASS on the final. A green-on-original
  selection is `independent-test-not-discriminating`, an empty one is
  `independent-test-incomplete-coverage`; both are repairable once with the offending
  indices. Node-id counts are scoped to the independent test's own file (the canary or any
  other file can never satisfy a criterion); the name convention stays a prompt hint (a
  class-based `TestAC1::test_x` passes when it discriminates, a placeholder fails); the
  whole-file red-on-original / green-on-final gates, the harness-owned file name, and the
  private-copy isolation are unchanged. The run record carries, per index, the selection's
  original/final collected counts and failures plus the reason. Suite **315 green**
  (13 new/rewritten cases pin discrimination, the placeholder and combined-name attacks,
  the class-based and parametrize approvals, and the record's per-criterion evidence).
- 2026-09-29 lane `leaf` (round 11, worker): round 10's per-criterion ``-k ac<i>`` gating
  had two deterministic gaps an adversarial pass found. **Finding C**: ``-k`` is a
  case-sensitive SUBSTRING match, so the selection for criterion 1 (``ac1``) also
  selected ``test_ac12_thing``/``test_ac10_...``, letting an index-colliding name
  "cover" the wrong criterion. **Finding A**: one genuinely discriminating test renamed
  to carry every index (``test_ac1_ac2_ac3_goal``) was selected for every criterion and
  approved them all, so "one test per criterion" was not enforced. Round 11 **stops
  selecting by ``-k``**: the index -> node-id map is derived from the FIRST full-file
  report (the whole-file red-on-original gate) with a boundary-aware, case-insensitive
  match on the test NODE NAME (``ac1`` never matches ``ac12``/``ac10``), scoped to the
  independent test file. Each criterion's discrimination check now runs the EXPLICIT
  node ids for that criterion (``pytest path::nodeid ...`` plus the canary node id, no
  ``-k`` term) on the original and final trees, so nothing else can run or satisfy the
  criterion. The per-criterion test sets must be DISJOINT: one node id mapped to more
  than one criterion is the new, REPAIRABLE ``independent-test-shared-coverage`` (the
  detail lists the shared ids); a criterion with no matching node stays
  ``independent-test-incomplete-coverage``. Red-on-original / green-on-final, the
  whole-file gates, the harness-owned file name, the private copies, the report gate,
  the per-criterion record evidence, and unaffordable/malformed keeping ``claimed``
  False are unchanged. Known consequence of the boundary rule: a class-based
  ``TestAC1::test_thing`` has no index in its junit node NAME and is now
  ``independent-test-incomplete-coverage`` (the index must be in the method/parameter
  name; parametrized ``ids=[...]`` still approve). Tests pin the index-colliding name,
  the all-index shared test (rejected + repairable), distinct per-criterion approvals,
  the explicit-node-id command (no ``-k``), and a live-repair path where a shared test is
  re-asked. Suite **318 green**.

## First honest v2 measurement (2026-09-29, reference model, N=1)

`bench/v2_sweep.py` (blind: source-only staging, grader run afterwards on a pristine copy).

| quadrant | n | detail |
| --- | --- | --- |
| true success | 5 | T-02, T-03, T-05, T-14, A-02 |
| missed success | 1 | T-31 — source correct, the run's own test disagreed |
| honest failure | 2 | T-25 (envelope SchemaViolation at call 1), T-33 |
| **false success** | **0** | never claimed a green the grader rejected |

actual 6/8, claimed 5/8, ~30 model calls total (~3.8 per pass). Compare with the v1
pipeline run blind the same day: 0/3 actual (and its contaminated numbers claimed ~93%).
The suite was 211 green at the measuring commit.

Two defects the live runs found, both parameter/logic-layer:

1. **The model names its self-test after the withheld grader file** (T-02 asked for
   `tests/test_pagination.py`, which exists only as the grader's copy), so the node died
   after one call. Fixed by deterministic parameter-layer normalization: a well-formed
   self-test envelope whose only defect is its landing spot is relocated to a free test
   path with `tolerance_fired` + `self_test_relocated` recorded. Refusal now only covers
   logic-level problems (escape, unusable envelope).
2. **A malformed envelope crashed the run** (T-25, `SchemaViolation`) instead of being
   retried or stopped honestly with a reason.

Remaining gap: the driver passes `judge=None`, so the conservative policy holds and the
model's own "the test is wrong" claim is never credited. T-02's second live run is the
textbook case: the source fix was right, the self-test was wrong (it asserted every item
appears on every page), and the leaf honestly reported exhaustion instead of claiming —
a missed success that an independent test-side judgement would have converted.

## Rounds 3-6 (delegated) and the perimeter decision

Six delegated rounds, each a writer lane plus an independent read-only *adversarial*
verifier lane (shell-enabled, explicitly told to try to forge a pass). Attacks found and
closed: the model naming its test after the withheld grader file; envelope crashes; the
judge path letting a weakened test claim success; a run-written `conftest.py` that
turned the grader green; stdlib/pytest module shadowing (`json.py`, `pytest.py`) that
forged a pass; `atexit` + `os._exit(0)` inside a legitimate source file that forged
BOTH gates. Fixes: parameter-layer tolerance, bounded envelope retries, replace-never-
weaken + independent judgement, one owned-path definition used by staging/the leaf/the
grader, module-shadow refusal, interpreter isolation, and report-based gates (junit XML
in a private temp dir + per-run randomized canary + expected node ids) so an exit status
is never evidence.

Perimeter decision (owner charter is "no false success"): in-process evidence is
fundamentally forgeable, because the measured code executes inside the gate's own
process — a run can read `sys.argv`/`/tmp`, unlink the canary, rewrite the report, and
exit 0. Verification demonstrated this end to end (minimal recipe in the round-6 review).
We stop hardening here and record it as a KNOWN LIMITATION with tamper-evidence
(`gate_report_anomaly`, `gate_process_lie`, `shadow-file-present`) plus the recorded
escape hatch: eventual OS-level separation of the gate (the harness already has bwrap
plumbing). Empirically the reference model never produced such code; the exposure is
adversarial, and the accidental case (a stray `sys.exit()` in edited source) is caught.

Live-run findings fixed directly by the supervisor: the gate inherited the repository's
own pytest configuration because the workdir lives under the repo, which changed the
report's file paths and silently broke canary/expected-file matching (T-02 ran 7 calls
and could never green). The leaf gate now runs with a neutral `-c` config and a pinned
`--rootdir=.`; the grader pins `--rootdir=.` too. Import roots are declared explicitly
(`gate_env`), so a legitimate run-written test under `tests/` can import its package
(verification round-6 R3), while a shadow file present in the tree refuses the gate.

## Final leaf measurement (10 tasks x N=2, blind, reference model)

| claim rule | actual | claimed | true | missed | honest | false | calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| plain | 12/20 | 11/20 | 10 | 2 | 7 | 1 | 69 |
| + independent test | 15/20 | 10/20 | 9 | 6 | 4 | 1 | 123 |
| + per-criterion discrimination | 16/20 | 4/20 | 4 | 12 | 4 | 0 | 183 |

Rounds 3-11 delivered: bounded envelope handling; replace-never-weaken with independent
judgement; one owned-path definition (tests, conftest, pytest config, *.pth,
sitecustomize, corpus UNTOUCHED) enforced by staging, the leaf guards and the grader;
module-shadow refusal; interpreter isolation; report-based gates (junit in a private
temp dir + per-run canary + expected node ids) so an exit status is never evidence; an
independent test the run never sees, required RED on the pristine source and GREEN on
the final source; per-criterion discrimination by explicit node ids with disjoint
per-criterion sets; and the harness, not the model, names the test file. Every round had
an independent shell-enabled adversarial verifier; its findings drove the next round.

Stop point: the remaining weakness is the QUALITY of the independently written test (the
same small model writes it), which is what keeps 12 of 20 graded successes unclaimed. That
is a model-quality lever, not a rule we can tighten or loosen safely. The leaf is
declared done; work moves to the node tree (ticket 18).

## Matched comparison: traditional (own test) vs strict (independent test)

Same 9 corpus tasks x N=2, same day, same fixed recognizer, blind, reference model:

| claim rule | actual | claimed | true | missed | honest | false | calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| own test green => claim (traditional) | **14/18** | 10/18 | 9 | 5 | 3 | **1** | **83** |
| own test + judge + independent test | 11/18 | 1/18 | 1 | 10 | 7 | **0** | 168 |

The strict arm is WORSE on what it actually fixes (11 vs 14) and costs twice as much,
because it frequently rejects work that is correct: of its 11 graded successes, 10 were
unclaimed, and the blockers were defective tests rather than bad code —
"independent-test-not-discriminating" 3, "independent-test-red-on-final" 3,
"no independent-test call at all" 3 (the run's own test never went green),
"not-red" 1. The independent test is authored by the same small model, so it is wrong
in both directions, and every rejection burns an attempt.

The 7 actual failures break down as: coordinated multi-site change the model does not
complete (T-31 x2, T-14; T-05 partly), contract/edge semantics the request does not
spell out (T-33 x2, T-05), and ONE harness defect — T-08 stopped after 2 calls with no
attempts at all because its self-test was green on arrival twice (no-red-target), so it
never even tried to implement. That dead end is ours to fix.

Consequence for the design: `claimed` should become a claim WITH its verification
status (verified | rejected-<reason> | unverified), so a consumer that cannot tolerate
lies filters on `verified` while throughput uses all claims. This is an owner decision.
