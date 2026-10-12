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
