# 28 — three requirements: parity, honesty, verification that carries information

Owner mandate (ticket 28): make the harness's pure-coding outcome **match or beat** the mature CLI
`pi` on the SAME 4B model over the 40-task corpus, **without lying** and with verification that
**adds information**, then prove it. The campaign is cut into five milestones (Q1–Q5). Each one
states what can be seen, the check to run, and what counts as done.

Read with: [`docs/ROADMAP.md`](../../../docs/ROADMAP.md) (the user-visible slices V1–V6 and the
criteria C1–C5), [`docs/STATUS.md`](../../../docs/STATUS.md) §8e–§8h (the numbers), and this
ticket's Q1 output
[`parity-forensics.md`](parity-forensics.md) (the diagnosis, the defect list D1–D6).

Companion outputs written for the same ticket (independent workers, same directory):
[`verification-decomposition-forensics.md`](verification-decomposition-forensics.md) and
[`ablation-protocol.md`](ablation-protocol.md), plus the measurement tool
`bench/v2_measure.py` with [`measurement-tooling.md`](measurement-tooling.md). Where those use
`R1`/`R2`/`R3` labels, each states its own mapping; the milestone axis here is **Q1–Q5** and is the
one the mandate fixed.

The three requirements map to the acceptance criteria like this: **R1 parity** = C1 (coding ≥ pi
on the same model, every knob maxed) with C4 (structure beats prompting) and C5 (efficiency
measured); **R2 honesty** = C3 (no unexplained failures, zero false successes); **R3 verification
carries information** = C2 (no meaningless test or review, and every failure traced to its exact
deviation point).

## Milestones

| # | what can be seen | the check | state |
| --- | --- | --- | --- |
| **Q1** | *Why we lose, task by task.* Every divergence with pi carries a quoted deviation point, a named harness mechanism, a named fix, and a `our-defect` / `model-ceiling` verdict; the N=1 error margin is numeric. | `parity-forensics.md` — §2 quotes the trajectory, §4 gives the margin, §5 the prioritized list | **done** (this ticket) |
| **Q2** | *The parity fixes, proven.* D1–D5 landed one at a time, each with a before/after on the tasks it names, then the whole corpus re-measured on ≥9 seeds per arm on ONE revision. | `bench/runs/v2sweep-*` at the frozen revision + this ticket's Q2 table; the two arms' 40-task totals with a 95% interval | **open** |
| **Q3** | *Verification earns its keep.* An ablation on the same tasks and revision shows what each stage adds (`raw` → `+own-test` → `+independent` → `+review` → `+gates`), measured on **actual** (grader) and not only on claims. | the ablation sweeps + the per-arm claim/false table; a stage that adds no actual-pass information is named and removed or re-aimed | **open** |
| **Q4** | *Multi-part work moves.* A decomposition / multi-approach path shows a positive delta (actual) on the multi-part tasks (T-31-style multi-file and anchor-band tasks), not a wash. | the same 40 tasks with and without the decomposition path; the delta on the multi-part subset, with the failed paths recorded | **open** |
| **Q5** | *The final head-to-head, on a frozen revision.* Ours vs pi (A1 maxed and A2 prompt-improved) on 40 tasks: actual, claimed, false, tokens, and wall-clock on a **single lane**. | one table, one revision, both arms, the same seed count; retractions recorded in `STATUS.md` in the same commit | **open** |

Q2–Q5 are sequential: Q2 must not be measured until the revision is frozen, Q3/Q4 change behaviour
and therefore re-open Q2's numbers, Q5 is the last measurement on the final freeze. Every
milestone's numbers land in `docs/STATUS.md` (one home per fact); this ticket keeps the narrative,
the contracts and the provenance.

## Q1 result (done)

**State at `d24410a`:** ours 26/40 actual (10 claimed, 1 false: A-02), pi 27/40 (29 claimed, 2
false). pi-only wins: **T-17, T-28**. Our-only win: T-33. Both arms fail the same 12
(`A-01..A-05, T-13, T-24, T-26, T-27, T-32, T-34, T-35`).

**At `6b224f5` (the campaign measurement):** ours 24/40, pi 27/40; pi-only wins T-07, T-14, T-28,
T-30.

**The diagnosis, in one line:** both current parity losses have a **grader-passing revision inside
the run that the harness threw away** (T-17: 4 of the 7 written revisions pass, the delivered one
fails; T-28: the discarded revision passes 4/4, the delivered one fails 4/4). Of the `6b224f5`
losses, T-07, T-28 and T-30 are defect-led (T-30's false-success claim is closed by P8b) and only
T-14 is content-side (`6b224f5`: six revisions written, none passing). No parity loss needs a
better model.

**Numbers the next milestones must use.** N=1, 40-task noise: SD ≈ 1.4 tasks (2.0 on the
difference), up to 2.4/3.4 on the hard tail, from 4 task flips per 40 between identical repeats.
Parity-within-margin needs **≥9 seeds per arm** (≈330 task-runs); claiming a win needs **≥17 seeds
per arm**. pi's variance is unmeasured (N=1) and must be measured with the same seed count.
Cost today: 18,250 / 19,365 tokens per task (mean 18,808; pi 9,045) and a wall-clock that is
still not single-lane (26-34 s/task measured 4-way concurrent vs pi's sequential 131 s).

**Open items handed to Q2** (from `parity-forensics.md` §5): D1 deterministic-anchored delivery,
D2 deterministic test-attribution, D3 `spec_wrong` coherence, D4 one-sided documented-API check,
D5 independent-verification admissibility, D6 the measurement protocol (seeds, single lane, A2).

## Discipline for this ticket

- One writer per work tree; never edit code while a measurement lane runs.
- Every flow change is exercised once against the REAL model before it counts, and its before/after
  is recorded here.
- A number that a later measurement contradicts is retracted in the same commit that contradicts
  it (the rule the P2 token headline was retracted under).
- The test gate is the authority: `uv run pytest -q -p no:warnings` (includes the tamper guard and
  the corpus-integrity suite); check the exit code, never pipe it.
- One claim gate: nothing outside `harness/leaf.py::claim_decision` may set `claimed=True`.
- Model-ceiling may only be recorded with the recurring failure quoted per task, and never from a
  `stop_reason` label alone.

## Provenance

- Campaign root for the earlier phases: [`.scratch/27-campaign/`](../../27-campaign/issues/27-campaign.md).
- Q1 evidence: every quote in `parity-forensics.md` §2 comes from
  `bench/runs/v2sweep-20261011T065821Z/`, `bench/runs/v2sweep-20261011T070710Z/` and
  `bench/runs/v2sweep-20261009T{114753,114754,120918}Z/`; the pi quotes from
  `bench/runs/evidence/pi-maxed-20261006/`. Every "would have passed" claim is a re-run of the
  withheld suite on that revision in a pristine copy.

## Closeout — final verdicts (2026-10-14, revision `45ebb32`)

**Status: CLOSED.** The user asked for the closeout. The final measurement revision is
`45ebb32f1be0977b9149057da3a80ee93ce22840` ("Fix wave 1: verification/review information +
deterministic delivery anchor, plus T-35 and canary closures"). The current facts were
rewritten in place into `docs/STATUS.md`, `docs/ROADMAP.md` and `README.md`; the extraction
is the new `docs/LEARNINGS.md` and the working rules are `CONTRIBUTING.md`. This section is
the narrative record and the home for the dated narrative that was removed from
`docs/STATUS.md`.

### Final verdicts

| milestone | verdict | decisive numbers (revision `45ebb32`, 40 tasks, blind grader) |
| --- | --- | --- |
| Q1 (why we lose) | **done** | both parity losses had a grader-passing revision the harness threw away (T-17: 4/7 written revisions passed, delivered failed; T-28: discarded revision 4/4, delivered 0/4). Diagnosed at `d24410a`/`6b224f5`. |
| Q2 (R1 parity) | **INCONCLUSIVE** | N=25/arm: ours `24.640/40` (sd 1.22) vs pi `24.960/40` (sd 2.15), delta `-0.320` tasks `= -0.8%`, task-clustered 95% CI `[-3.520, +3.080]`, `M=3` rule misses by `0.520` tasks. CI width structural (flat `6.53..6.60` from N=17..25), so more seeds cannot resolve. Evidence: `fix-wave-1-measurement-n25.md`, `fix-wave-1-measurement-final.md`. |
| Q3 (R2 verification information) | **PARTLY / not as stated** | own test `-1.33` tasks (p=0.55); IV neutral on correctness, `-8.67` claims (p=0.0009) and `-3.00` false (p=0.031); review `+4.00` correctness (p=0.012) only atop own test + IV, and `+3.33` false (p=0.031) alone. False successes `0/0/0/10/1`. Evidence: `requirement-2-ablation.md`. |
| Q4 (R3 decomposition) | **NEGATIVE** | leaf `47/70 (67.1%, 0 false)` vs tree-greedy `14/70 (20.0%, 4 false)` vs tree-tournament `15/70 (21.4%, 3 false)`; paired CI upper bounds below 0, p<0.001; mechanism fired (3/70 on 3/9 tasks; 9/70 on 4/9). Evidence: `requirement-3-result.md`. |
| Q5 (final head-to-head) | **Q2 result; A2 arm unmeasured** | false successes ours `2.20%` vs pi `6.10%`; cost ours `~17.5k` tokens/task vs pi `~9k`. The improved-prompt pi arm (A2) was never run (environment blocker, then out of scope for the closeout). |

Independent recomputation of all three requirement verdicts from the raw rows, with no
discrepancy: `final-measurement-independent-verification.md`.

### Open / unfinished (recorded as openly not closed)

- **No proof of superiority and no proof of impossibility.** The pre-registered test
  returns INCONCLUSIVE; the point estimate is a near-tie.
- **The product CLI does not exist** (slice V6).
- **The improved-prompt pi arm is unmeasured** (slice C4's "structure beats a better prompt").
- **pi token cost is partly unmeasured** (`pi_baseline.py` carries no token counters; its
  `~9k`/task comes from the recorded reference).
- **Wall-clock is not cleanly comparable** (ours measured under concurrency, pi
  sequentially); a clean single-lane 40-task run is outstanding.
- **Results are corpus/model-scoped**: one model (Spark-X2.5-4B Q4_K_M), one 40-task
  corpus, one baseline.
- **Named harness defects remain unfixed**: redirect on a refusal; accumulate multi-file
  changes instead of erasing; rank the delivered revision by required-surface coverage;
  apply the non-discriminating-check rule to the plain green path; persist per-attempt
  model output.

### Closeout deliverables (same pass, no commit; a later integration worker commits)

- `docs/LEARNINGS.md` (new): the extraction document.
- `README.md` (rewritten).
- `docs/STATUS.md` (rewritten to the final measured position).
- `docs/ROADMAP.md` (rewritten to the final slice and criteria verdicts).
- `CONTRIBUTING.md` (new).
- `.gitignore` (small standard additions; proposed).
- This closeout section (and the moved narrative below).

### Superseded `STATUS.md` narrative (moved here; not current facts)

The dated sections of the old `docs/STATUS.md` (`§1`, `§1a`, `§8b`..`§8h`) were folded
into current facts. Their still-valuable history, kept for audit and not as the current
position:

- **2026-10-01/03 — the 9-task, 8192-token measurement** (`416f1bf`): `15/18` actual, `0`
  false. **Retracted as a leaked-exam measurement:** the task repos shipped a stale
  `.pytest_cache` holding the grader's own test node ids and the mature-agent baseline
  visibly read it. `harness/staging.py` now withholds cache artifacts and the corpus caches
  are gone.
- **The claim-rule iteration on those 9 tasks** (`416f1bf`): agreement-required `14/18`
  actual, 0 false; review-outranks-test `12/18`, 2 false; review + grant-calibre evidence
  `12/18`, 0 false; plus best-evidence delivery `14/18`, 3 false; plus request-level
  coverage and a red independent verification blocking a review `15/18`, 0 false.
- **2026-10-03 development-vs-verification matrix** (`124c41d`, clean re-measurement, 33
  common tasks): raw `17/33 (52%)`, test `18/33`, review `18/33` with 11 false, full
  `20/33 (61%)` with 2 false.
- **The retracted token headline:** the byte-stable-context change was reported as
  `-31.3%` tokens; re-measurement did not reproduce it (mean `16,006` pre-change,
  `16,132`/`16,872` after). Retracted at `25dafaf`.
- **The throttled pi baseline and its correction:** the first pi measurement (`21/40`)
  ran with `--thinking off` (the only level the temp model declaration allowed) on an 8k
  server; re-measured with `--thinking max --reasoning` on 32k, pi fixes `27/40`, and the
  anchors stay `0/5`. This is the fairness correction that turned a claimed tie into a
  3-task deficit at `6b224f5`.
- **Our 32k full arm** (`6b224f5`): `22/40`, with the missed wins dominated by our own
  independently authored verification turning red on a correct fix
  (`independent-test-red-on-final`, 8 tasks).
- **Per-task failure verdicts** (`8f`, `d24410a`): all 16 failures given a quoted grader
  failure and an `our-defect` / `model-ceiling` verdict; two harness defects remained open
  (T-28 delivered nothing, T-14 shipped a known-partial revision).
- **The strict claim rule (P8c, owner decision A)** at `24d801e`: only a behaviour-level
  deterministic fact may carry a claim; a 5-task probe returned 0 false successes.
- **The confirming 40-task run after P8b** (`8g`, `d24410a`): `26/40`, 1 false (A-02).
- **Fix wave 1** (`45ebb32`): the delivery-anchor, review-attribution and IV-inversion fixes,
  plus the T-35 false-success class closed by the self-contradicting-check rule; reviewed
  and independently verified (`fix-wave-1-independent-review.md`,
  `final-measurement-independent-verification.md`). The head-to-head to N=25 followed on
  this revision.

Full run records and raw rows are in this directory and in git history; the commits that
bracket the story are `416f1bf`, `25dafaf`, `124c41d`, `6b224f5`, `24d801e` and `45ebb32`.
