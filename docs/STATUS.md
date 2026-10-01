# Status — what works, what was measured, what is not solved

Written 2026-10-01 while the owner was away. Everything below is either measured (with the
command to reproduce it) or explicitly marked as not built. When this document and the code
disagree, the code and its tests win; when this document and the run records disagree, the
records win.

## 1. The measured position

Reference model: Spark-X2.5-4B (Q4_K_M) on llama.cpp, one local server. Method: **blind** —
the corpus's own test suite is the grader and never enters the run; the run's produced files
are applied to a pristine copy afterwards and scored there. Nine corpus tasks, two runs
each, driver `bench/v2_leaf.py` (the leaf flow: own test, independent verification, review,
the claim gate).

Measured 2026-10-01 at commit `f0dc49a` (one claim gate), 9 tasks x 2 runs, `bench/v2_sweep.py`,
run directory `bench/runs/v2sweep-20261001T035026Z`.

| metric | value |
| --- | --- |
| **actual** (the grader's verdict) | **14/18 (78%)** |
| **claimed** (what the harness said) | 4/18 |
| true success (claimed + grader passed) | 4 |
| missed success (did not claim, grader passed) | 10 |
| honest failure (did not claim, grader failed) | 4 |
| **false success (claimed, grader failed)** | **0** |
| model calls | 156 (8.7 per run) |

Every claim was **review-based** (a graded, multi-angle review with the critical-angle veto);
no run claimed on its own test alone. There is no false success to attribute, test-based or
review-based.

**Why 10 graded-successes were not claimed** — the stop reasons of those runs, and what the
ledger says:

| blocker | runs | what the record shows |
| --- | --- | --- |
| the INDEPENDENT test was red on the final (correct) code | 5 | the ledger rows were **satisfied via `review:ac-correctness`** — the review judged the fix correct and the grader agreed; the blocker was the independent test's own expectation, not the fix |
| the INDEPENDENT test asserted and failed against a passing fix | 2 | all criteria `violated` by `independent-test` while the grader passed (T-20: the same "wrong expected value" failure the forensics found in the run's own test, now in the independently authored one) |
| verifier conflict (own test red, independent test green) | 1 | both criteria `satisfied` by the independent test; the gate refused because the run's own test disagreed on the same revision |
| ladder exhausted with every criterion `unverifiable` | 2 of them are EVIDENCE GAPs | the ledger names exactly what was attempted and why no discriminating check existed |
| artifact coverage blocked a criterion naming a frozen file | 1 | T-33: the criterion names `base.py`, which the task freezes — a criterion/corpus mismatch, not a code defect |

The honest summary of this table: the harness **fixes** most of these tasks and the gate
still refuses to claim, almost always because a *verification* (the independently authored
test) is wrong, not because the code is. That is the current bottleneck, and it is a data
problem, not a rule problem.

How to read this: **actual** is what the grader decided; **claimed** is what the harness
said; a *false success* is a claim the grader rejected (the number that must stay at zero);
a *missed success* is a task the harness actually fixed but refused to claim, and the run
record now names the criterion and the evidence that stopped it.

## 2. What the harness does (one paragraph each)

**Blind protocol.** The run never sees the grader's tests. It stages only source, works in a
sandbox, and is scored afterwards on a pristine copy. A run that "fixes" its own tests, adds
a `conftest.py` hook, shadows `json.py`/`pytest.py`, or forces a zero exit status is refused
or restored, and the attempt is recorded.

**Self-verification that cannot lie about itself.** The gate is a machine-readable pytest
report written to a private path, containing a per-run random canary and the expected test
ids. An exit status is never evidence; a missing report, a missing canary or a mismatched id
is red.

**One claim gate.** A claim is granted in exactly one place. It requires: at least one
acceptance criterion, a non-empty evidence ledger, no missed coverage of a criterion's named
artifact, and — for anything more than the run's own green test — agreement between two
independently produced verifications. A red own test plus a passing review or independent
test is recorded as a verifier CONFLICT and cannot claim. A structural test fails the suite
if any other code path could grant a claim.

**Evidence in both directions.** Every acceptance criterion gets a ledger row (satisfied /
violated / unverifiable) pointing at what was observed. A run that stops without any
satisfied or violated row is an EVIDENCE GAP and says so, rather than reporting a vague
"attempts exhausted".

**Decomposition is budgeted and greedy.** A request becomes a root node; a node plans ranked
approaches (Hows), takes the top one, and spends its budget there; failed approaches are
abandoned and a new one may be appended (bounded), or the node re-plans into children when
its own boundary is genuinely multi-part. Wall-clock deadline is the primary budget.

## 3. What was tried and did NOT help (measured, not guessed)

| Mechanism | Result |
| --- | --- |
| injecting a knowledge pack (signatures/callers/constants) | no gain (4/15 vs 3/15) |
| putting module importers into the write spec | no gain (10/15 vs 10/15) |
| forcing a deterministic file-change order | harmful (14/15 vs 7/15) |
| extending the write boundary on rule evidence | no gain (1/5 vs 1/5) |
| competitive How exploration (tournament of candidates) | works, but ~5× the calls and wall time for fewer fixes; greedy is now the default |
| a "bare" agent loop as a baseline | 0/6 — it wrote no test and ran no command; the harness's forced verification is what makes the model move at all |

The pattern across all of them: structure that costs calls without adding **information**
loses. What moved the numbers was giving the model more signal (the forced red-then-green
loop, deterministic diagnosis rules, the report gate, coverage and discrimination checks).

## 4. Known limits (accepted, not pretended away)

1. **Two verifications that share the same misreading agree**, so a wrong fix can be
   certified. No deterministic in-process rule can catch this without a ground-truth oracle.
   The external grader is the only correctness arbiter. (DESIGN §10.8a.)
2. **The harness is not an oracle.** Its own claim is evidence, not proof; every number in
   section 1 is the grader's verdict, never the harness's.
3. **Adversarial code can forge the gate's own evidence** (it runs in the same process and
   filesystem). This is tamper-*evident* (every anomaly is recorded) but not prevented; a
   run would have to write deliberately hostile code, which the reference model never did.
4. **A weak-but-genuinely-discriminating test** (red on the pristine source, green on the
   final) passes the harness's checks even if it does not encode the requirement.
5. **The strongest residual on the quality axis is MISSED success**: runs that fix the task
   and cannot verify it. The ledger now names which criterion was unverifiable and why.

## 5. Where the evidence lives

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage, manager decisions, budget accounting) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/NN-*/issues/*.md` (ticket 21 covers the claim model; ticket 20 the
  How axis and its measured verdict; tickets 17–19 the leaf, the tree and the covenant).
- Design: `docs/DESIGN.md` §10 (flow) and §10.10 (implemented vs not built).

## 6. Recommended next steps (ordered)

1. **Attack the missed-success bucket with the data we now have.** Ten of the eighteen runs
   fixed the task and could not claim it; the ledger says exactly which verification was
   wrong. The measured bottleneck is the QUALITY of the independently authored test (the
   same small model writes it): in five runs its expectation was wrong while the graded
   review — and the grader — agreed with the fix.

2. **The next experiment (decided, not yet built): a labelled weaker claim tier.** When the
   run's own test is red and the independent test is red-on-final, but the multi-angle review
   (critical veto included) approves and coverage is clean, the run would claim with
   `verification_basis=review` and an explicit **weak** strength label — so a consumer can
   filter it. Expected yield on this sample: **about six more claims out of eighteen** (five
   independent-test-red-on-final runs plus the verifier conflict), all of which the grader
   accepted. Risk: the graded review can itself be wrong (one earlier round produced a
   review-approved false success); with the label in place that risk becomes a *measured*
   quantity per tier rather than an argument, which is why the tier is labelled rather than
   silently accepted. DECISION while writing this document: the default stays conservative
   (no claim) until that tier is implemented, verified and measured — the numbers above are
   the honest conservative baseline and can be re-derived by re-running the sweep.

3. **A stronger verifier model** (even a modest remote one) for the test-authoring and review
   roles is the single change most likely to raise true successes; every run already records
   whether its verification was independent or reviewed, so the effect would be visible in the
   very next sweep.

4. Build the designed-but-unbuilt layers only if a task needs them: requirement triage,
   model-side context curation, worktrees/parallel trees, a human-facing piloting surface
   (DESIGN §10.10).

## 7. Reproducing the numbers

```sh
# unit gate (no model required) — includes the repo tamper guard and corpus integrity
uv run pytest

# one task, leaf flow, with the ledger and claim record
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --calls 24 --deadline-hours 0.25

# the headline sweep (claimed vs grader), nine tasks, two runs each
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-03-wrong-comparison,T-05-mutable-default,T-08-add-cache-invalidation,T-14-add-export-sorting,T-20-average-truncation,T-25-chunked-helper,T-31-parameter-threading,T-33-serializer-contract --n 2 --calls 24
```
