# INFERRED

The measured detail this project produced: what the harness cost, the false successes it did not
eliminate, the designs that lost when they were tried, and the internals of the reproduction that
keep the archived numbers honest. Every statement here was measured or derived from a measurement.
The verdicts those measurements support are in `docs/2_GOAL.md`; the commands that re-derive them
are in `docs/9_IMPLEMENTATION.md`.

All of it was measured on revision `45ebb32`, with one model (Spark-X2.5-4B Q4_K_M) and one 40-task
corpus. Where a run record and a sentence here disagree, the record wins.

## Cost

- **Tokens: ours about `18.9k`/task (4-lane, 40 tasks) against `pi` about `9k`.** The harness is
  roughly twice as expensive, not cheaper. `pi`'s token count is partly unmeasured: its driver
  carries no token counters, so the `~9k` comes from the recorded reference and is not recomputable
  from the final rows.
- **Wall-clock is not clean or comparable.** Ours was measured under concurrency and `pi`
  sequentially, so the two are not like-for-like. A single-lane subset measured ours at
  `31.0 s/task` against `pi` at `47.5 s/task` — 8 tasks, one run, skewed easy — which is indicative
  only. A clean single-lane 40-task comparison for both arms is outstanding.
- An earlier token headline (`−31.3%`) was retracted; it did not reproduce
  (`docs/2_GOAL.md#retractions`).

## False successes and honesty

- **Head-to-head (N=25):** ours `22/1000 = 2.20%` against `pi` `61/1000 = 6.10%`. The
  task-clustered CI on the difference is `−1.56 tasks [−3.16, −0.20]` (ours better).
- **Ablation (600 runs):** false successes `0 / 0 / 0 / 10 / 1` across the five arms; the one false
  success in the full arm (A-05) rested on both the independent test and the review approving a
  solution the grader failed.
- **`pi`'s "claimed" column is not comparable to ours.** `pi` has no claim gate: its "claimed" is a
  regex read of its final assistant message, and its non-claims are mostly empty or truncated final
  messages, not admissions of failure. Only `actual` and false success are comparable across arms.
- The claim gate is what makes false successes a measurable quantity, but it does not eliminate
  them: the final rate is about `2.2%` at N=25, and the remaining ones sit on the plain green path
  (`docs/2_GOAL.md#known-limits`).

## Negative results

Each row is one mechanism that looked plausible, was implemented, was measured, and lost. They are
the most reusable single contribution of the project, and `docs/0_ROADMAP.md` treats an idea that
appears here as needing a different design rather than a repeat.

| idea | result | record |
| --- | --- | --- |
| current tree / multi-approach bundle (a tree of children; a tournament of Hows) | **harmful here.** Monolithic leaf `47/70 (67.1%, 0 false)` against tree-greedy `14/70 (20.0%, 4 false)` and tree-tournament `15/70 (21.4%, 3 false)`; every paired delta CI has an upper bound below 0, p<0.001; the tree costs `2.2` to `2.4x` the calls, `2.3` to `2.9x` the wall and at least `1.85x` the tokens. Decomposition fired on 3 of 9 decomposable tasks in one arm, 4 of 9 in the other; planning and spec rewriting, budget and closed-only delivery differ too, so this is not an isolated test of splitting or field refinement. | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` |
| a bounded source index (declared files in full, the rest as a compact index) | **harmful.** `13/24` against `18/24` on the same 12 tasks x2, and `13/24` against `19/24` against the pre-change revision `e190a4f` (commit `25dafaf`). Source is never hidden from the model now. | holds |
| forcing a deterministic file-change order | **harmful.** `14/15` against `7/15`. | holds |
| a knowledge pack (signatures, callers, constants) injected per call | no gain (`4/15` against `3/15`); off by default. | holds |
| putting module importers into the write spec | no gain (`10/15` against `10/15`). | holds |
| extending the write boundary on rule evidence | no gain (`1/5` against `1/5`). | holds |
| competitive How exploration (a tournament of candidates) | fires, but costs `2.2` to `2.4x` the calls and fixes far fewer tasks (`15/70` against `47/70`); greedy is the default. | holds |
| asking a weak model to write and run its own tests (applied to the mature CLI) | **worse.** The 4B could not emit a whole test file as a tool argument — the write hit the output-token limit and was dropped or re-issued — and 9 of 10 runs in the last band ended on a length-truncated block. `16/40` against `21/40`, measured at 8k context and never re-measured at 32k. | partial: 8k only |
| the harness discarding a revision that already passed the grader | **a harness defect, not a model ceiling.** The 3-task gap of the earlier starting position (`24/40` against `27/40`) was T-07's delivery discard, the closed T-30 claim hole and T-14's content; then T-17, where 4 of 7 written revisions passed and the delivered one failed, and T-28, where a discarded revision passed 4/4. | `docs/2_GOAL.md#r1-capability-parity` |
| the cost conclusion | **against the harness.** About `18.9k` tokens/task against `9k`, with `pi`'s count partly unmeasured and wall-clock not comparable. | `docs/8_DETAIL.md#cost` |

These implementations added calls without a measured net capability gain; that does not show that
structure in general cannot help. The delivery and attribution defects above show the opposite
direction as well — control flow can throw away capability the model already had — so the honest
statement is that each mechanism has to earn its place by measurement.

## The home, and why it is wider than the contract

The analyzers read more than the three directories the campaign contract named:
`bench/analysis/wave1/n25/analyze_n25.py` opens `our-n5`, `n9` and `n17` as well, because seeds
1..17 of the R1 head-to-head predate the `n25` wave. That is the difference between an interval and
a silent wrong answer: `read_jsonl` returns `[]` for a missing root, so with `n17` absent the same
script prints `delta +0.06` and `CI [−3.35, +3.71]` over 680 rows instead of `−0.320` /
`[−3.520, +3.080]` over 1000, and raises nothing. So the declared home is the whole `/tmp/wave1`
root, and the observable that catches a short home is the row count — 1000 per arm for R1 — which
`bench/analysis/wave1/recompute_n25.py` checks before it compares anything.

## How the home was proven equal to its source

The copy: `rsync -a --numeric-ids /tmp/wave1/ bench/runs/wave1/`, `total size is 1 996 009 173`,
exit 0, run twice — the first run carried only `n25`, `r2`, `r3`, the second the rest of the root,
and rsync skips what is already equal.

Equality with the source was measured rather than assumed: `sha256sum` over both trees, sorted, and
`diff` of the two lists — empty, 53 270 lines each. The source-side list is kept at
`bench/runs/wave1-src-manifest.sha256`, untracked, so the equality stays re-checkable while `/tmp`
survives and is deletable when it does not.

Durability: `sha256sum -c` from the home returned 53 270 `OK` and 0 `FAILED`, exit 0. Usability,
which is the part a hash cannot promise: all three verdicts recompute from the home
(`docs/9_IMPLEMENTATION.md#evidence-pointers`).

## The projection

`python3 reproduce.py` feeds the campaign's own analyzers from `bench/projection/wave1/final/` —
472 files, 2 810 rows, 523 499 bytes raw, 57 561 gzipped, cut from the 62 MiB of inputs the
analyzers read — and compares every value against the record committed beside its analyzer before
it prints one line. Fidelity of the projection to the home it was cut from, and the command that
re-checks it, are in `docs/9_IMPLEMENTATION.md#evidence-pointers`. What a projection row is, which fields it
keeps and what it cannot show is `bench/projection/README.md`.

The projection is cut from a deliberate subset, so it inherits one hazard the home does not have:
a record deleted from it starves an arm. The acceptance checker's three starvation cases leave
their victims under `bench/projection/wave1/final/` as records, and
`docs/7_INTERFACE.md#entry-point-contract` states what a starved run must print.

## A short input stops the run

Loud failure, three ways, each exiting 1 with zero stdout lines: a deleted record
(`missing input: … file not found`), a zero-row record (`empty input: … 0 rows read`), and a short
sample (`short sample: R1 arm a (ours) seed 20 — 35 rows, wanted 40 … arm a then has 995 of
1000`). Each is the short-home trap of
`docs/8_DETAIL.md#the-home-and-why-it-is-wider-than-the-contract` arriving at the projection: a
starved input stops the run with a named line instead of printing a number over a smaller sample.

## Two limits recorded rather than smoothed

R2's `analysis.json` is compared parsed rather than byte-wise, because its `stop_reasons` ties
depend on set-iteration order; and `r3/supp.py`'s one `/tmp` literal is replaced under an
exactly-once assertion, so a future edit stops the run instead of silently reading a temporary
path.
