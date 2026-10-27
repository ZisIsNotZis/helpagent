# CONFIRMED

## A comparison is fair before it is measured

Same model, same quantisation, same server window, same corpus, same grader, and the
baseline's own knobs maxed rather than throttled. The precondition is not a courtesy: the
project's first maturity comparison was wrong precisely because it clamped the baseline
(thinking off, an 8k window), and the corrected measurement was worse for us
(`docs/8_DETAIL.md#negative-results`).

## The decision rule is fixed before the data is read

A non-inferiority margin, the meaning of the interval's two ends, the bootstrap method, the
seed and the repeat count are written down before any outcome exists. Here the rule is `M = 3`
tasks: `Lo95 >= −M` is parity within margin, `Hi95 < −M` is behind, anything else is
INCONCLUSIVE. Pre-registration is what makes INCONCLUSIVE a result rather than an invitation
to keep sampling until it looks better (`docs/2_GOAL.md#r1-capability-parity`).

## The scoring instrument never enters the run

The task's own withheld suite grades it: the run sees source, the produced files are applied to
a pristine copy afterwards, and every reported number is the grader's verdict rather than the
harness's claim. Everything a run could do to its own scoreboard is refused or restored and the
attempt recorded — rewriting the grader's tests, `conftest.py` hooks, module shadowing, a
forged exit status.

## Evidence is a report, not an exit status

A claim rests on a machine-readable pytest report on a private path, with a per-run canary and
the expected test ids. An exit status is never evidence.

## One claim gate, structurally enforced

Exactly one function can grant a pass claim (`harness/leaf.py::claim_decision`) and every path
routes through it; a structural test fails the suite if any other path could set one. This is
the invariant that makes "the number of lies" measurable rather than aspirational, and it
survives refactoring because the test reads the call graph
(`docs/6_ARCHITECTURE.md#what-the-harness-does`).

## A claim is only as strong as the check that carried it

The basis is recorded with the claim, so a consumer can filter — accept only deterministically
anchored claims, treat a review-only claim as weak. A single claim boolean would hide the
distinction that matters.

## Every decisive number re-derives, or is named as a gap

- The deliverable's numbers recompute from committed rows with one command, with no model
  server, no network and no campaign archive (`docs/7_INTERFACE.md#entry-point-contract`).
- A starvation of the input fails loudly: a missing record, a zero-row record and a short
  sample each stop the run with a line naming the input and the count it wanted, before any
  number is printed. A reproduction that reports parity after reading an empty directory is
  worse than no reproduction.
- A number no committed command re-derives is recorded as `unknown` with the gap named, never
  as re-derived (`docs/paper/numbers.md`).

## Retract in the same breath

A number a later measurement contradicts is retracted in the commit that contradicts it, and
the retraction stays visible (`docs/2_GOAL.md#retractions`).

## A behaviour change needs a measurement

Unit tests alone have let dead paths ship here. A flow change is not done until it has run once
against the real model, and a corpus task is not done until it is winnable
(`docs/9_IMPLEMENTATION.md#run-the-gate`).

## Publication is the person's act

The repository is public and the preprint is readable in it. A DOI deposit, an arXiv submission
or any further public surface is a `cost` act above this node and is not taken here
(`docs/5_PRODUCT.md#published-and-what-is-owed-to-the-person`).

# INFERRED

## The measurement rules these requirements come from

Each requirement above prevents a failure this campaign actually committed, which is why they
are stated as rules rather than as advice:

| failure | rule that now prevents it |
| --- | --- |
| a comparison that made the baseline look weaker than it is | the fair precondition |
| an interval quoted from one run, or widened by adding seeds that cannot resolve the question | pre-registration, the paired task-clustered interval, and a stated resolvable effect size |
| a run that destroyed a revision the grader had already passed | compare the delivered bytes against every revision the run wrote |
| a claim no independent check could carry | the one claim gate and the recorded basis |
| a number that only a reader of the repository could re-derive | the entry point, its loud failure, and the `unknown` rows |
| a headline retracted later and quietly dropped | retraction in the same breath |

## A verification pipeline that can be reused

The findings behind the rules above, as they were extracted at the end of the campaign. The arm
table they rest on is `docs/2_GOAL.md#r2-verification-information`.

1. **Fresh context does not remove shared-model error.** No net correctness gain was detected from
the own-test loop (`−1.33 [−5.67, +3.00]`, p=0.55); independent-test correctness contrasts are also
unresolved. Neither establishes zero information. A shared wrong reading can survive code, own
test, independent test and review; final R2 A-05#1 is a direct example. Agreement is not proof of
correctness; the external grader remains this experiment's arbiter.

2. **Measure the workflow effect without assigning universal stage roles.** With review present,
enabling independent test reduced false successes (`−3.00 [−5.67, −1.00]`, p=0.031). In the full arm
it withheld approval in `92/110` runs, `57` of which the final grader passed; this is a
stage/final-outcome join, not independent diagnostic accuracy. Review's correctness contrast is
positive with independent test present (`+4.00`, p=0.012); without it, false successes rise
(`+3.33`) and correctness is unresolved. This does not establish an interaction or that review
works only when backstopped. Own tests can change code and block claims without directly carrying
a claim. Stage costs are unmatched and contrasts unadjusted for multiplicity; do not equate net
outcome with signal information.

3. **One claim gate, structurally enforced, is reusable and cheap.** There is exactly one function
that can grant a pass claim, every path routes through it, and a structural test fails the suite
if any other code path could set `claimed=True`. That single invariant is what makes "the number
of lies" a measurable quantity rather than an aspiration, and it survives refactoring because the
test checks the call graph.

4. **A claim is only as strong as its basis, and the basis must be recorded.** Distinguishing
"claimed" from "grader passed", and recording *which* check carried the claim, is what lets a
consumer filter ("accept only deterministically anchored claims", "treat a review-only claim as
weak"). A single `claimed` boolean hides the distinction that matters.

5. **An evidence ledger in both directions.** Every acceptance criterion gets a row: satisfied,
violated, unverifiable, pointing at what was observed. A run that stops with no row at all is an
`EVIDENCE GAP`, not an honest failure. This is what makes "no unexplained failures" checkable.

Checklist for a verification pipeline, reusable as-is:

- [ ] The scoring instrument never enters the run; stage source only, grade on a pristine copy
      afterwards.
- [ ] Refuse or restore every attempt to touch the scoring instrument (rewrite tests,
      `conftest.py` hooks, module shadowing, forged exit status), and record the attempt.
- [ ] Evidence is a machine-readable report on a private path with a per-run canary and the
      expected test ids. A process exit status is never evidence.
- [ ] Gate the claim in exactly one function, and test structurally that no other path can grant
      one.
- [ ] Record the basis of every claim, and refuse a claim from a non-discriminating check (a check
      that passes on the unmodified source is not evidence that the change is correct).
- [ ] The independent verifier must not share the author's context or reading; in practice with one
      model this still shares its weights, so treat the external grader as the real arbiter and
      the internal checks as honesty filters.
- [ ] Ledger row per acceptance criterion, plus an explicit `EVIDENCE GAP` state.

## Measuring a harness honestly

The measurement discipline is separate from the design, and arguably the more transferable output.

- **Blind external grading.** The task's own withheld suite is the grader. The run sees source
  only; the produced files are applied to a pristine copy and scored there. Every number reported
  is the grader's verdict, never the harness's claim.
- **Tamper guard.** The repository runs a test that verifies the harness cannot be silently
  reconfigured to self-certify.
- **Trajectory-level forensics.** When a task fails, read the trajectory for the exact deviation
  point rather than labelling the failure. This is how the project found that its own machinery,
  not the model, was causing losses.
- **Run-to-run variance and pre-registered decision rules.** A decision rule is fixed before data
  is read (here: a non-inferiority margin `M = 3` tasks, `Lo95 >= −M` means parity within margin,
  `Hi95 < −M` means behind, else inconclusive), with a task-clustered bootstrap CI and a fixed
  seed. Pre-registration is what makes INCONCLUSIVE a real, publishable result instead of an
  invitation to keep sampling until it looks good.
- **Separate a statistical projection from impossibility.** At N=25 the CI width was flat (range
  `6.44`–`6.60`; `6.53` at N=17, `6.60` at N=25), dominated by between-task heterogeneity. At the
  observed task effects, more seeds alone are not projected to close the 0.52-task gap; future
  estimates can still move. Compute the resolvable effect size before promising a decisive answer,
  and distinguish the campaign's inconclusive stopping result from the capability goal's
  feasibility.
- **Compare delivered bytes against every revision the run wrote**, not just the ones it claimed.
  This is the single most valuable forensic in the project: it revealed that the harness *discarded
  or overwrote revisions that already passed the grader* (T-17: 4 of 7 written revisions passed,
  the delivered one failed; T-28: a discarded revision passed 4/4). The 3-task gap at the
  2026-10-09 starting point (`24/40` vs `27/40`) was harness-side, not model capability: the
  delivery discard (T-07 at that revision; T-17 and T-28 on the next revision) plus the T-30 claim
  hole, with T-14 content-side; fixing the delivery path moved the position to the near-tie reported
  above. **A harness can silently destroy capability it already had.**
- **Separate a throttle from a ceiling.** The original maturity comparison was wrong because our
  own configuration clamped the baseline (thinking off, 8k context). The corrected measurement was
  worse for us. Fair-comparison precondition: same model, same server window, same corpus, same
  grader, and the baseline's own knobs maxed.

Checklist for evaluating a coding harness, reusable:

- [ ] Fix the comparison conditions and state them: model, quantisation, context window, corpus,
      grader, and the baseline's configuration.
- [ ] Grade blind, on a pristine copy, outside the run.
- [ ] Pre-register the decision rule, the margin, the seed count and the analysis method.
- [ ] Report both the arm totals and the paired, task-clustered interval; never a single run.
- [ ] Record run-to-run variance and state the resolvable effect size for the corpus.
- [ ] On every failure, compare the delivered revision to every revision written; a
      grader-passing discarded revision is a harness defect, not a model ceiling.
- [ ] Bind every number to a revision and keep the raw rows so an independent worker can recompute
      it. (This project's three verdicts were recomputed from raw rows by a fresh-context worker
      with no discrepancy.)

## What a decisive result would still need

The 40-task corpus projects an asymptotic interval width of about `6.3` tasks from the
observed task effects, so a decisive parity or superiority test needs a corpus whose
between-task heterogeneity is smaller relative to the effect, or a design built on paired
within-task effect sizes with a power analysis done first. That is a requirement on any future
measurement, not a finding of this one (`docs/0_ROADMAP.md#not-on-this-roadmap`).
