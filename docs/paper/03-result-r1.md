# 3. R1 — capability parity: INCONCLUSIVE, and why more seeds do not fix it

The question: on the same model, does the harness solve as many of the corpus's tasks as the
mature CLI, within a margin fixed before the data were read?

## The result

At `25` seeds per arm — `1000` run rows per arm, no crashes and no timeouts in the recorded
driver-level metrics (`docs/STATUS.md:38`) — the two arms are:

| | ours | `pi` |
| --- | --- | --- |
| runs solved | `616/1000` | `624/1000` |
| mean per `40`-task run | `24.640` | `24.960` |

The paired, task-clustered difference is `-0.320` tasks with a 95% interval of
`[-3.520, +3.080]` (`docs/STATUS.md:48`, `docs/STATUS.md:49`). Applying the pre-registered rule
(`docs/STATUS.md:51`): `-3.520 >= -3` is false, missing the margin by `0.520` tasks, and
`+3.080 < -3` is false as well. The verdict is therefore **INCONCLUSIVE**
(`docs/STATUS.md:28`).

## What INCONCLUSIVE means here, and what it does not

INCONCLUSIVE is neither parity nor inferiority. The interval admits a deficit of up to `3.520`
tasks — past the margin the campaign was willing to accept — and a lead of up to `3.080`
tasks. The point estimate is small, and the record calls it a near-tie in the same breath as it
denies that a tie was established (`docs/STATUS.md:54`): a small point estimate computed on a
wide interval is not evidence of parity, and this paper does not read it as one. Specifically:

- it is **not** "near parity" and **not** "essentially equivalent", because neither is what the
  test returns;
- it is **not** a failure of the harness, because inferiority is not established either;
- it **is** a statement about the test's resolution at this corpus size, and that statement is
  quantified below rather than asserted.

## Why more seeds do not fix it

The interval's half-width is about `3.3` tasks and is essentially flat from `N=17` to `N=25`
(full width `6.53` to `6.60`) (`docs/STATUS.md:57`). Flatness with sample size is the signature
of a width set by between-task heterogeneity rather than by seed noise: at `N=25` the
within-seed variance contributes only about `8.7%` of the per-task-mean variance, leaving a
`~6.3`-task asymptotic width projected from the observed task effects (`docs/STATUS.md:60`).
Under that projection, the rule would need the point estimate to move to about `+0.3` tasks, or
a different or larger task set, to return ACHIEVED (`docs/STATUS.md:61`).

Three cautions, in the record's own terms. The projection is a projection from observed task
effects, not a proof that more seeds cannot change the estimate, and not a proof that the
capability goal is impossible (`docs/STATUS.md:61`). It is also the reason the next campaign's
design work is a power question — a task set whose between-task heterogeneity is smaller
relative to the effect — rather than a seed-count question (`docs/ROADMAP.md:83`).

The widths and the variance share above are the only decisive numbers in this paper that no
committed command currently re-derives; they are recorded as unknown in the numbers table with
the gap named (`numbers.md`), not filled in.

## The number this result replaced, and the one it could silently become

The campaign's starting position, measured on revision `6b224f5`, was ours `24/40` against
`27/40` (`docs/STATUS.md:64`). That gap was harness-side, not model-side: a revision that
already passed the grader was discarded inside the run and a failing one delivered (T-07 at
that revision, T-17 and T-28 on the next), plus one closed claim hole and one content-side
failure (`docs/STATUS.md:65`). Fixing the delivery path moved the position to the tie reported
above (`docs/STATUS.md:69`).

The same structure is a warning about reproduction. If the analysis is fed a short input, it
does not fail: with one seed directory absent, the campaign's own analyzer returns `+0.06` and
`[-3.35, +3.71]` over `680` rows instead of `-0.320` and `[-3.520, +3.080]` over `1000`, and
raises nothing (`bench/analysis/wave1/NUMBERS.md:75`). A reproduction that reports parity after
reading an empty directory is worse than no reproduction (`AGENTS.md` §Current facts), which is why the
entry point in §8 asserts row counts before it prints anything.

## The reliability result, which is separate

On the same runs, the harness's false-success rate — the run claimed success and the grader
failed the work — was `22/1000` against the mature CLI's `61/1000` (`docs/STATUS.md:45`), a
task-clustered difference of `-1.56` tasks with interval `[-3.16, -0.20]`
(`docs/STATUS.md:140`). This is the one axis where the harness is measurably ahead, and it is
narrower than it looks: the baseline's claimed column is not comparable, because the mature CLI
has no claim gate and its "claimed" is a regular expression over its final message
(`docs/STATUS.md:145`). Only actual correctness and false success are comparable across the
arms (`docs/STATUS.md:147`). The advantage is also not a moat: it is a property of a design
that is straightforward to add to any agent (`docs/LEARNINGS.md:213`).
