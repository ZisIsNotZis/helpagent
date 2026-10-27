# 2. Protocol: an external grader, a pre-registered rule, and a corpus that cannot see its own answer

The protocol exists to remove three sources of self-flattery at once: the instrument must not
be inside the run, the conditions must be equal for both arms, and the decision rule must be
fixed before the outcome is read. Each is a section below.

## Who grades

The scoring instrument is each task's own withheld test suite, applied to a pristine copy of
the task's repository *after* the run has finished. It is a separate program, and it says so on
its face: "It never runs inside the harness process and its result is never fed back into a
run" (`bench/external_score.py:2`). Three contamination routes were closed by measurement
before the final campaign, and each closure is a documented round in the same file:

- the grader owns a deterministic surface and restores the run's version of every
  grader-owned path (test paths, `conftest.py`, pytest configuration) before scoring, so a run
  that rewrites the tests cannot turn the grader into a liar (`bench/external_score.py:10`);
- a run-authored module that shadows `json` or `pytest` is never applied, and the grader's own
  pytest runs with the run's repository root off `sys.path` (`bench/external_score.py:20`);
- the process exit status stopped being evidence: the grader runs its own report-based
  verification and reads a machine-readable report (`bench/external_score.py:26`).

The consequences for the numbers in this paper: every number below is the grader's verdict,
never the harness's claim (`docs/2_GOAL.md#known-limits`). The harness's claim is recorded separately
and the two are compared, which is what makes "false success" a measurable quantity rather than
an aspiration (`docs/3_REQUIREMENT.md#a-verification-pipeline-that-can-be-reused`).

## Who is compared, under what conditions

Held equal for every arm (`docs/6_ARCHITECTURE.md#fair-comparison-precondition`): one model, Spark-X2.5-4B Q4_K_M on llama.cpp
(`docs/6_ARCHITECTURE.md#fair-comparison-precondition`); one server window with a quantised KV cache
(`docs/6_ARCHITECTURE.md#fair-comparison-precondition`); one corpus of `40` tasks (`docs/6_ARCHITECTURE.md#fair-comparison-precondition`); the same blind grader
(`docs/6_ARCHITECTURE.md#fair-comparison-precondition`); and the baseline configured with its own knobs maxed rather than
throttled — the `pi` CLI with `--thinking max --reasoning` (`docs/6_ARCHITECTURE.md#fair-comparison-precondition`).

The last condition is the one that reverses naive results. An earlier maturity comparison had
clamped the baseline (thinking off, a small context window) and therefore judged the mature CLI
the weaker; measured again under the fair precondition, the comparison was *worse for the
harness* (`docs/3_REQUIREMENT.md#measuring-a-harness-honestly`). That earlier reading is retracted (§6).

## The corpus

`40` tasks: the project's own tasks T-01..T-35 plus anchors A-01..A-05 drawn from Exercism
exercises (`docs/9_IMPLEMENTATION.md#where-the-evidence-is`). Every task directory has the same shape and nothing else
(`bench/corpus/README.md:3`):

- `request.md` — the user's raw request, verbatim, the only input a run is given
  (`bench/corpus/README.md:8`);
- `repo/` — the work tree, which ships broken (`bench/corpus/README.md:9`);
- `checks.py` — deterministic checks, standard library only, with an explicit `UNTOUCHED` list
  of paths a correct solution must not modify (`bench/corpus/README.md:47`);
- `solution.md` — the minimal fix, outside `repo/`, never shown to a run
  (`bench/corpus/README.md:11`).

Red-to-green is verified by hand before a task enters the corpus, and the repository is then
restored to its exact broken bytes, checked by hash (`bench/corpus/README.md:19`). Without
that step the corpus is an opinion about what is broken; with it, a task is a falsifiable pair
of states.

The anchor tasks matter for the same reason a negative control matters: they were not written
by the harness's author against the harness's weaknesses, and they are the part of the corpus a
reader can obtain independently.

## Pre-registration and the stopping rule

The decision rule for R1 was fixed before the data were read: a non-inferiority margin of `M=3`
tasks on the `40`-task scale, with a task-clustered percentile bootstrap interval at `20000`
resamples and a fixed seed `20261013` (`docs/2_GOAL.md#r1-capability-parity`, `docs/2_GOAL.md#r1-capability-parity`). The rule is
three lines, and it is the whole test:

- `Lo95 >= -M` — parity within the margin;
- `Hi95 < -M` — behind;
- otherwise — INCONCLUSIVE.

Two features of this shape are deliberate. First, the unit is *tasks solved*, not runs or
sessions, so an interval is computed over the corpus's `40` tasks and its width is set by
between-task heterogeneity rather than by how long the campaign was run (§3). Second,
INCONCLUSIVE is a verdict the rule can return and the campaign can publish; it is not the
absence of a verdict. Pre-registration is what makes that true: without it, an inconclusive
result is an invitation to keep sampling until it looks good (`docs/3_REQUIREMENT.md#measuring-a-harness-honestly`).

**Why `M=3`.** The record fixes the margin and the rule but does not preserve a derivation of
the number three beyond its role as the smallest difference the campaign would have acted on
(`docs/3_REQUIREMENT.md#measuring-a-harness-honestly`). This paper names that gap instead of filling it: what is fixed is
the *test*, not the justification of its margin, and a reader who thinks three tasks on forty
is too loose or too tight can apply the same interval with their own margin, because the
interval is reported.

**The stopping rule.** The campaign had a frozen intermediate result at `N=17` seeds per arm
and extended it to the seeds beyond it (`docs/2_GOAL.md#r1-capability-parity`); the rule never returned ACHIEVED
or BEHIND, so the run consumed the full pre-registered extension and the reported verdict is
the maximum-N verdict for this design (`bench/analysis/wave1/n25/assemble.py:165`). The arm
therefore carries `25` seeds, which is `1000` run rows per arm (`docs/2_GOAL.md#r1-capability-parity`).

The other two requirements were pre-registered the same way. R3's rule was fixed before any
outcome was read, and its comparisons are paired by `(task, seed)` (`docs/2_GOAL.md#r3-decomposition-and-multi-approach`). R2's
ladder is cumulative — one verification stage added per arm — over `5` arms and `3` repeats of
the `40` tasks, `600` runs in total (`docs/2_GOAL.md#r2-verification-information`), with its own bootstrap at `10000`
resamples and the same seed (`bench/analysis/wave1/r2/analysis.txt:1`). R3 ran `210` runs:
`14` tasks, `3` arms, `5` seeds, `70` runs per arm (`docs/2_GOAL.md#r3-decomposition-and-multi-approach`).

## What the protocol does not solve

The internal verifiers share the model's weights, so fresh context helps but does not make them
independent (`docs/5_PRODUCT.md#what-does-not-transfer`). The regression stage is unobservable on this corpus,
because each task's `repo/tests/` is the grader's suite and the blind protocol withholds it, so
"no regression" rests on the external grader's own suite (`docs/2_GOAL.md#known-limits`). And the
protocol measures workflows, not information content: enabling a stage changes feedback,
iteration, stopping and delivery together, so a stage contrast is a net workflow effect rather
than an isolated measurement of signal (`docs/2_GOAL.md#r2-verification-information`).
