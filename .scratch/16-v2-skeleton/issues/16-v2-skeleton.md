# 16 — v2 skeleton: budget, attempts, questions, blind gate

Status: done
Need-review: yes (scoped self-review recorded below)
Need-test-cases: yes (16 cases in tests/unit/test_v2_skeleton.py)
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: The validated v1 flow leaks the corpus tests into the harness gate (the staged workdir carries them and `gate` runs them), so every published number measures a harness that can read the grader. Owner direction 2026-09-29 replaces the single-leaf flow with a budgeted task tree whose verification is self-produced. Its skeleton must exist before any of that can be built or measured.

Objective: (1) Record the v2 flow in `docs/DESIGN.md` and mark leak-affected v1 numbers as contaminated. (2) Implement the v2 data skeleton with unit tests: node budget (wall-clock deadline primary, call units secondary, split with reserve, grant, release, durable), attempt records with model-claimed novelty plus deterministic novelty prefilter and exhaustion decision, question objects with a state machine and withdrawal rules, and a blind staging projection that keeps corpus tests out of the harness view. No behavior change to the shipped loop yet; wiring comes next under its own evidence.

Acceptance: unit tests pin each rule (split/reserve arithmetic, signature construction, prefilter outcomes, exhaustion detection, legal/illegal question transitions, dedupe, auto-withdraw, test-path projection parity with the check pipeline). Full unit gate green. DESIGN records the v2 flow, the budget rule, the escalation ladder, the question lifecycle, the four-quadrant scoring, and the contaminated-result list. Work tree clean; no model calls required for this ticket.

- 2026-09-29 agent: started from clean `f5c969b`. Owner directions recorded this session: fixed flow, code-aware steps, budget-driven decomposition, deadlock-free "never idle" escalation, non-blocking piloting, scoring quadrants.

## Retracted claims (leaked gate: the harness ran the grader's own tests)

Every number below was produced by a flow whose workdir carried the corpus tests
and whose gate ran them. They measure "harness with the exam on its desk", not
autonomous verification, and they are **not citable** until re-measured under the
blind protocol. Retraction is about the *claim*, not about whether the mechanism
works — the same mechanisms are re-tested.

| Retracted | Why | Replacement measurement |
| --- | --- | --- |
| Tiered "97/120 (80.8%)"; "orig 30 = 84/90 (93.3%)"; hard 8/15; anchors 6/15 | Gate = corpus tests | Blind sweep: claimed vs grader, per stratum |
| Bare-model-vs-harness deltas (85.6% vs 93.3%, "beats bare and full pipeline") | Same gate on the harness arm; the bare arm had no such oracle | Re-run both arms blind |
| Closing-gear histogram 91/5/1 (and 92/3/2) | Escalation triggered by the grader's own tests | Re-measure; escalation must now come from self-produced verification |
| Knowledge-pack null result (4/15 vs 3/15) | Spec was blind (no code read), so a relations pack could not be used | Re-test once steps can read code |
| Spec-caller-map null result (10/15 vs 10/15) | Same blindness | Re-test with code-aware spec |
| Forced file ordering "harmful" (14/15 vs 7/15) | Contaminated gate both arms; also downstream of blind spec | Re-test only if the ladder reaches L6 |
| Boundary-completion null result (1/5 vs 1/5) | Same | Fold into the L6/L7 re-decomposition work |
| Arity-rule T-31 gain (0-1/5 → 3/5) | Magnitude contaminated (gate) | Mechanism is deterministic and unit-pinned; re-measure magnitude blind |
| Retry-view tie (8/24 vs 8/24) | Both arms gated by corpus tests | Not worth re-running before v2 exists |

**Still valid (not gate-dependent):** kernel safety nets (check pipeline, sandbox,
untouched contract) — zero model calls, pinned by unit tests; model-behaviour
FAIL_PATTERNS FP-1…FP-10 (properties of the 4B, independent of the gate);
parameter-layer tolerance; ledger/erasure infrastructure; cost-per-call
measurement method; and the ladder mechanisms L2/L4 that were observed to help
inside a node (guide-first, deterministic diagnosis) — their home in the design is
unchanged.

## v2 protocol as implemented

- `harness/staging.py` — `source_only`/`stage_blind`: test paths never reach the workdir,
  the file map, or the grounding scope; withheld paths are recorded so an audit can prove
  the run had no grader access.
- `bench/external_score.py` — applies a run's produced files onto a pristine task copy and
  runs the task's `checks.py verify` there; returns exit code plus the grader's own notes.
- `harness/budget.py` — deadline-primary budget, split with reserve, grant/deny audit,
  durable round-trip.
- `harness/attempts.py` — failure signature, novelty prefilter, exhaustion rule that
  refuses to declare a node dead while a structural lever is untried.
- `harness/questions.py` — non-blocking question lifecycle with dedupe and
  auto-withdrawal when the blocking nodes finish another way.

Pinned by `tests/unit/test_v2_skeleton.py` (16 cases); full unit gate green.

- 2026-09-29 agent: shipped the five modules and the design record. `uv run pytest -q`
  green (170 cases; 16 new). Fresh scoped self-review: budget split cannot produce
  unworkable children and deadlocks nothing (release/grant audited); novelty prefilter
  never trusts the model's own claim (ambiguous cases go to the judge); exhaustion
  refuses while a structural lever is untried; question transitions are terminal and
  withdrawal always carries a reason; the blind projection withholds exactly the test
  paths the check pipeline treats as test paths (parity pinned); the external grader
  runs in a pristine copy and caught a tampered frozen file in test. Residual: the v2
  flow itself is not wired to any runner yet (next ticket), and the retracted numbers
  remain uncitable until the blind sweep runs.
