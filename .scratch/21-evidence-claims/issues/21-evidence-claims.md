# 21 — evidence in both directions, and the single claim gate

Status: done (rounds 1-6, commits b669dbc .. f0dc49a)
Owner direction: 2026-09-30 (evening) — claims must never be a guess in EITHER direction
Depends on: tickets 17-20 (leaf loop, covenant, review angles, greedy Hows)

## Owner's words that define this ticket

"If it says 'not fixed', it must show EVIDENCE of what is not fixed — which requirement,
which check, which counterexample. It must not guess 'done' either." And, on failures:
find out WHY from the recorded trajectory and fix that root cause systemically rather than
patching around it. The How axis is frozen: one approach should solve the vast majority of
tasks, and Hows get no further investment.

## What was built

1. **Per-acceptance-criterion ledger** on every code-writing node: state
   `satisfied | violated | unverifiable`, each row carrying a concrete evidence pointer
   (own-test gate, independent test, declared test case, artifact coverage, review angle)
   computed from what the run actually observed. Persisted in `run.json`.
2. **EVIDENCE GAP**: a non-claimed run that stops (`attempts`/`ladder`/`calls`/`attempt-cap`/
   `deadline`) with no satisfied or violated row is a distinct state, not an honest failure,
   and says so in its reason.
3. **The loop consumes the report**: a violated criterion becomes the next attempt's
   targeted context; an unverifiable one routes to review.
4. **Verify at exhaustion**: the independent per-criterion verification (and, where a test
   cannot carry it, the review path) now runs on the FINAL code when the ladder exhausts —
   previously it only ran after the run's own test went green, which is exactly why a run
   whose own test was wrong gave up silently.
5. **Requirement coverage is a hard block** for claims and for `ok` reviews (the T-31
   false-success route).
6. **One claim gate** (`harness/leaf.py::claim_decision`): the only place a claim may be
   granted; every site routes through it, and an AST test fails the suite if any other path
   can produce a claimed outcome. It refuses a claim when the own test is red, when
   coverage missed a named artifact, with zero criteria, or with an empty ledger; a red own
   test plus a passing review/IV is recorded as a verifier CONFLICT and cannot claim.
7. **Corpus integrity suite** (107 cases): every task's reference solution must not be
   frozen by its own grader, the shipped tree must be red, the UNTOUCHED list must be
   coherent, and the layout must be exactly four entries. It caught T-33, which was
   unwinnable as graded.
8. **Judge input**: the goal, the criteria and the FAILING ASSERTION lines, not just the
   failure excerpt.

## The forensic evidence that drove it (26 recorded runs, read-only, evidence-cited)

- The dominant root cause of the missed-success bucket: **6/26 runs had their own
  verification contradict the hidden grader** — all five missed successes plus the single
  false success. Mechanism: the model's own test asserted the SYMPTOM as the expected value
  (T-02 asserted 3 items where the fix yields 4; T-20 asserted 4.25 where the fix yields
  4.08), so a correct fix could never go green; the judge ratified the bad test; one
  falsifier invented a counterexample; one review approved a partial diff.
- Also found: T-33 unwinnable as graded; one run planned test points inside a withheld
  grader path.

## Residual routes to a wrong green (the honest end state)

| Route | Kind |
| --- | --- |
| Two verifications that share the same misreading agree, so a wrong fix claims | **fundamental** — no in-process rule can catch it without a ground-truth oracle; documented in DESIGN §10.8a |
| In-process forging of the gate's own evidence (a run writing the report, the canary or a fake module) | adversarial; tamper-evident via recorded anomalies, not prevented |
| A weak-but-genuinely-discriminating test (red on pristine, green on the final) | ordinary-model; the grader is the only check |

Everything an ORDINARY model did in the recorded sample is now blocked at one gate.

## Verification

Every round had an independent, shell-capable, adversarial verifier lane. It broke the
design four times in a row (five wrong-green repros, each in a different branch) which is
what forced the single-gate design; all five repros are re-run and refused with the REAL
content-executing runner, and the two legitimate claim routes still claim.
