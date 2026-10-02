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

Measured 2026-10-02 at commit `4aec0ac`, 9 tasks x 2 runs, `bench/v2_sweep.py`; run records in
`bench/runs/evidence/` and under `bench/runs/v2sweep-*`.

| metric | value |
| --- | --- |
| **actual** (the grader's verdict) | **12/18 (67%)** |
| **claimed** (what the harness said) | 8/18 |
| true success (claimed + grader passed) | **8** |
| missed success (did not claim, grader passed) | 4 |
| honest failure (did not claim, grader failed) | 6 |
| **false success (claimed, grader failed)** | **0** |
| model calls | 186 (10.3 per run) |

**Claims by evidence basis** — this is the table that decides whether a claim is trustworthy,
and it is the reason the run record carries `claimed_basis`:

| tier | claims | true | **false** | false rate |
| --- | --- | --- | --- | --- |
| `review` (graded, grant-calibre review) | 7 | 7 | 0 | 0% |
| `review+independent-test` | 1 | 1 | 0 | 0% |
| `own-test` / `independent-test` alone | 0 | - | - | - |

**Three rules measured on the same nine tasks, same model** (the evolution of the claim rule,
in order):

| claim rule | actual | claimed | true | missed | **false** | calls |
| --- | --- | --- | --- | --- | --- | --- |
| agreement required (a red test could not be overridden) | 14/18 | 4/18 | 4 | 10 | 0 | 156 |
| the graded review outranks a conflicting test | 12/18 | 11/18 | 9 | 3 | **2** (both on T-31) | 174 |
| ... plus grant-calibre review evidence | 12/18 | 8/18 | **8** | 4 | **0** | 186 |

The middle row is what the owner's rule bought on its own: more claims, and a 20% false-success
rate on the review tier. The third row is the same rule with the evidence requirement that a
granting review must name the acceptance criterion AND a specific observation (a value, or a
behavioural verb with a symbol present in a changed file): the two false successes disappeared
(T-31 was refused rather than claimed), the review tier measured 0/8 false, and the harness
still claimed twice as many true successes as the conservative rule. One sweep is one sample;
the review tier's error rate is not proven zero, it is measured zero here - which is why every
claim records its basis.

**Why the remaining successes were not claimed.** Four graded successes were refused: two were
`ladder` runs whose ledger names the unverifiable criterion, and two were T-33 whose criteria
name a file the task freezes (a criterion/corpus mismatch, not a code defect). The evidence is
in each `run.json`.

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
   The external grader is the only correctness arbiter. (DESIGN §10.8a.) Ticket 22 makes
   this sharper: the graded REVIEW now outranks a conflicting test, so a review that
   approves a wrong fix claims directly rather than being backstopped by an agreeing test.
   Ticket 22 round 2 hardens the route: a review that is about to GRANT must name the
   acceptance criterion it serves AND the specific behaviour/observable/value it verified
   (a changed path or a generic "looks correct" no longer grants; the refusal is recorded
   as `review_not_grant_calibre`). The remaining risk is now exactly the reviewing model's
   error rate when it approves on substantive evidence: thin evidence can no longer
   manufacture a review-backed claim, but a specific yet mistaken approval still can.
2. **The harness is not an oracle.** Its own claim is evidence, not proof; every number in
   section 1 is the grader's verdict, never the harness's.
3. **Adversarial code can forge the gate's own evidence** (it runs in the same process and
   filesystem). This is tamper-*evident* (every anomaly is recorded) but not prevented; a
   run would have to write deliberately hostile code, which the reference model never did.
4. **A weak-but-genuinely-discriminating test** (red on the pristine source, green on the
   final) passes the harness's checks even if it does not encode the requirement.
5. **The strongest residual on the quality axis is MISSED success**: runs that fix the task
   and cannot verify it. The ledger now names which criterion was unverifiable and why.
6. **The review tier is measured, not proven.** In the last sweep its review-backed claims
   were 0/8 false, down from 2/10 before the grant-calibre evidence rule; one sweep is one
   sample, and the tier's error rate is the reviewing model's own. A consumer that cannot
   tolerate that filters on `claimed_basis` (accept `own-test`, `own-test+independent-test`,
   `independent-test`, `review+independent-test`; treat `review` alone as reviewed-but-weak).
   `verification.tier` is NOT the filter to use - it can read `test` on a review-decided claim.

## 5. Where the evidence lives

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage, manager decisions, budget accounting) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/NN-*/issues/*.md` (ticket 21 covers the claim model; ticket 20 the
  How axis and its measured verdict; tickets 17–19 the leaf, the tree and the covenant).
- Design: `docs/DESIGN.md` §10 (flow) and §10.10 (implemented vs not built).

## 6. Recommended next steps (ordered)

1. **The claim rule is settled by measurement; do not re-open it without new numbers.**
   Three rules were measured on the same tasks and model (section 1): the owner's
   review-outranks-tests rule, once requiring grant-calibre evidence, claims twice as many
   true successes as the conservative rule at the same measured false-success count (0), and
   the two false successes the unhardened rule produced are refused by the evidence rule.

2. **Attack the remaining missed-success bucket (4 of 18).** Every case's ledger says which
   criterion was unverifiable and which check was attempted; two of the four are T-33, whose
   criteria name a file the task freezes (a criterion/corpus mismatch worth fixing in the
   task, not the harness).

3. **The independent test is still the weakest link** (14 attempts, 3 repairs, and it was the
   blocker in the earlier conservative sweep). A stronger verifier model - even a modest
   remote one - for the test-authoring and review roles is the single change most likely to
   raise true successes; every run records whether its verification was independent or
   reviewed, so the effect would show in the very next sweep.

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

The reference model server used for every number above:

```sh
llama-server \
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8833 --host 127.0.0.1 -ngl 99 -c 8192
```

`curl -fsS http://127.0.0.1:8833/health` must answer `{"status":"ok"}` before a sweep.
