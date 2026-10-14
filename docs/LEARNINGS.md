# Learnings and reusable patterns

This is the extraction document for the helpagent research project. It records what the
project teaches, what is reusable outside it, what is not, and what remains open. The
measured numbers it quotes live in [`STATUS.md`](STATUS.md); the narrative and provenance
live in the work record [`.scratch/28-three-requirements/`](../.scratch/28-three-requirements/issues/28-three-requirements.md).

The whole project is one experiment: wrap a weak local model (Spark-X2.5-4B Q4_K_M, a 4B
quantised model) in a conventional software-engineering process, and measure honestly
whether the result is better than the same model driving a mature free-form agent CLI
(`pi`) on the same 40 tasks with every knob maxed, using a blind external grader.

The short answer: **no detected capability difference — parity not established
(INCONCLUSIVE at `M=3`), a real but shallow reliability advantage, and no cost
advantage.** The value of the project is the design principle it validated, the
methodology it demonstrated, and the negative results it recorded with error bars.

## 1. The design principle: harness-as-program, model-as-fallback-node

The central idea is that the model is never a free-form engineer. The harness is a
deterministic program, and every place a general-purpose language model is used is a
single step with a written contract:

- it has a fixed input (named artifacts), a fixed output (a typed envelope, a
  grammar-constrained shape), and a declared purpose;
- the surrounding control flow is ordinary code (branches, loops, budgets) that never
  asks the model to decide the flow;
- deterministic checks own every fact that can be computed (does the test pass, does the
  file exist, is the untouched contract intact), and the model only fills the gaps where
  no deterministic program exists (write a candidate revision, read a failure and propose
  a cause).

A useful one-line statement: **the harness is a program, and the model is a fallback node
invoked with a function-like contract wherever deterministic code cannot be written.**
The mechanism, its purpose and its use are: (what) a step wrapper that fixes input, output
and question for one model call; (purpose) keep the model out of control flow and out of
any decision a shell command, parser or lookup could make; (use) the harness calls it at a
declared seam and validates the returned envelope before acting on it.

**What the measurements say about this design** (revision `45ebb32`, 40-task corpus):

- It works: the full harness fixes `77/120 = 64.2%` on a five-arm ablation, and the
  head-to-head at N=25 is statistically indistinguishable from the mature CLI
  (`24.640/40` vs `24.960/40`, task-clustered 95% CI `[-3.520, +3.080]`).
- It is statistically indistinguishable from a free-form agent loop, but it is not better
  on capability: the pre-registered test returned INCONCLUSIVE, so neither parity within
  margin nor inferiority is established. The development-only arm (a plain loop with no
  verification, `58.3%`) and the full stack (`64.2%`) differ by `+2.33 tasks [−0.33, +5.33]`,
  which is not significant at this sample size; and the head-to-head against `pi` (a
  free-form loop) is a near-tie.
- What the structure buys is not raw fixes. It buys **checkable claims**: the same model
  under the harness produced false-success rates of `2.2%` against `pi`'s `6.1%` at N=25,
  and the ablation shows where that comes from (section 2).

The design is worth copying when the model is weak and the task class is narrow. It is
not shown to beat a good free-form loop on capability, and a stronger model would likely
erase most of the reliability gap (section 7).

## 2. Verification methodology: deterministic gates, one claim gate, evidence ledger

The project's verification pipeline and what each part measured. The five-arm ablation is
`600` runs (5 arms x 40 tasks x 3 repeats) on revision `45ebb32`, external grader only:

| arm (what runs) | actual | false success |
| --- | --- | --- |
| A0 development only (no verification, never claims) | 70/120 (58.3%) | 0 |
| A1 + the run's own test (red first, iterate to green) | 66/120 (55.0%) | 0 |
| A2 + an independently authored test | 65/120 (54.2%) | 0 |
| A3 + the run's own test + a graded review | 71/120 (59.2%) | 10 |
| A4 full (own test + independent test + review + one claim gate) | 77/120 (64.2%) | 1 |

Paired incremental contributions (one stage isolated per contrast, 40 tasks):

| stage | effect on actual correctness | effect on claims / false successes |
| --- | --- | --- |
| the run's own test | `−1.33 tasks [−5.67, +3.00]`, p=0.55 | none; it never carried a claim in any of the 600 runs |
| the independent test | no significant correctness effect (`−0.33`, `+2.00`, p≥0.39) | cuts claims `−8.67`, p=0.0009; cuts false successes `−3.00 [−5.67, −1.00]`, p=0.031 |
| the graded review | the only significant correctness gain, and only **on top of** own test + independent test: `+4.00 [ +1.33, +7.00]`, p=0.012 | added to the own test alone, review produces `+3.33 false successes [+1.00, +6.33]`, p=0.031 |

The reusable findings:

1. **A check that shares the generator of the thing it checks is not independent
   evidence.** The own test is written by the same model that writes the code; measured,
   it is zero-information on correctness (`−1.33`, p=0.55). The independent test is
   written by the same model in a fresh context; on correctness it is also
   indistinguishable from zero. When the model keeps a wrong reading, its code, its own
   test, its independent test and its reviewer all inherit that reading, so agreement
   between them proves nothing. The external grader is the only correctness arbiter.

2. **Each verification stage has a different, measurable job, and they are not
   interchangeable.** The independent test is a **false-claim suppressor** (it buys
   honesty, not fixes), and it is a conservative one: in the full arm it withheld approval
   in `92/110` runs, `57` of which the grader passed. The review is a **correctness** lever
   only when it is backstopped by an independent test; alone it mostly produces confident
   wrong claims (`+3.33` false successes). The own test is a cost centre with no measured
   correctness benefit here. A pipeline should assign these roles deliberately instead of
   treating "more verification" as strictly better.

3. **One claim gate, structurally enforced, is reusable and cheap.** There is exactly one
   function that can grant a pass claim, every path routes through it, and a structural
   test fails the suite if any other code path could set `claimed=True`. That single
   invariant is what makes "the number of lies" a measurable quantity rather than an
   aspiration, and it survives refactoring because the test checks the call graph.

4. **A claim is only as strong as its basis, and the basis must be recorded.**
   Distinguishing "claimed" from "grader passed", and recording *which* check carried the
   claim, is what lets a consumer filter ("accept only deterministically anchored claims",
   "treat a review-only claim as weak"). A single `claimed` boolean hides the distinction
   that matters.

5. **An evidence ledger in both directions.** Every acceptance criterion gets a row:
   satisfied / violated / unverifiable, pointing at what was observed. A run that stops
   with no row at all is an `EVIDENCE GAP`, not an honest failure. This is what makes
   "no unexplained failures" checkable.

**Checklist for a verification pipeline (reusable as-is):**

- [ ] The scoring instrument never enters the run; stage source only, grade on a pristine
      copy afterwards.
- [ ] Refuse or restore every attempt to touch the scoring instrument (rewrite tests,
      `conftest.py` hooks, module shadowing, forged exit status), and record the attempt.
- [ ] Evidence is a machine-readable report on a private path with a per-run canary and
      the expected test ids. A process exit status is never evidence.
- [ ] Gate the claim in exactly one function, and test structurally that no other path can
      grant one.
- [ ] Record the basis of every claim, and refuse a claim from a non-discriminating check
      (a check that passes on the unmodified source is not evidence that the change is
      correct).
- [ ] The independent verifier must not share the author's context or reading; in practice
      with one model this still shares its weights, so treat the external grader as the
      real arbiter and the internal checks as honesty filters.
- [ ] Ledger row per acceptance criterion, plus an explicit `EVIDENCE GAP` state.

## 3. Evaluation methodology: how to measure a harness honestly

The project's measurement discipline is separate from its design, and arguably the more
transferable output.

- **Blind external grading.** The task's own withheld suite is the grader. The run sees
  source only; the produced files are applied to a pristine copy and scored there. Every
  number reported is the grader's verdict, never the harness's claim.
- **Tamper guard.** The repository runs a test that verifies the harness cannot be
  silently reconfigured to self-certify.
- **Trajectory-level forensics.** When a task fails, read the trajectory for the exact
  deviation point rather than labelling the failure. This is how the project found that
  its own machinery, not the model, was causing losses.
- **Run-to-run variance and pre-registered decision rules.** A decision rule is fixed
  before data is read (here: a non-inferiority margin `M = 3` tasks, `Lo95 >= −M` means
  parity within margin, `Hi95 < −M` means behind, else inconclusive), with a task-clustered
  bootstrap CI and a fixed seed. Pre-registration is what makes "INCONCLUSIVE" a real,
  publishable result instead of an invitation to keep sampling until it looks good.
- **The decision rule can be structurally unable to resolve.** At N=25 the CI width was
  flat (range `6.44`–`6.60`; `6.53` at N=17, `6.60` at N=25) because it is set by between-task
  heterogeneity in the 40-task corpus, not by seed noise; more seeds cannot close the
  0.52-task gap to the margin. The lesson is to compute the resolvable effect size from
  the corpus before promising a decisive answer, and to say "the test cannot resolve this"
  rather than "more data needed".
- **Compare delivered bytes against every revision the run wrote**, not just the ones it
  claimed. This is the single most valuable forensic in the project: it revealed that the
  harness *discarded or overwrote revisions that already passed the grader* (T-17: 4 of 7
  written revisions passed, the delivered one failed; T-28: a discarded revision passed
  4/4). The 3-task gap at the 2026-10-09 starting point (`24/40` vs `27/40`) was
  harness-side, not model capability: the delivery discard (T-07 at that revision; T-17 and
  T-28 on the next revision) plus the T-30 claim hole, with T-14 content-side; fixing the
  delivery path moved the position to the near-tie reported above. **A harness can silently
  destroy capability it already had.**
- **Separate a throttle from a ceiling.** The original maturity comparison was wrong
  because our own configuration clamped the baseline (thinking off, 8k context). The
  corrected measurement was worse for us. Fair-comparison precondition: same model, same
  server window, same corpus, same grader, and the baseline's own knobs maxed.

**Checklist for evaluating a coding harness (reusable):**

- [ ] Fix the comparison conditions and state them: model, quantisation, context window,
      corpus, grader, and the baseline's configuration.
- [ ] Grade blind, on a pristine copy, outside the run.
- [ ] Pre-register the decision rule, the margin, the seed count and the analysis method.
- [ ] Report both the arm totals and the paired, task-clustered interval; never a single
      run.
- [ ] Record run-to-run variance and state the resolvable effect size for the corpus.
- [ ] On every failure, compare the delivered revision to every revision written; a
      grader-passing discarded revision is a harness defect, not a model ceiling.
- [ ] Bind every number to a revision and keep the raw rows so an independent worker can
      recompute it. (This project's three verdicts were recomputed from raw rows by a
      fresh-context worker with no discrepancy.)

## 4. It codifies a conventional software-engineering process around a weak model

The harness is, deliberately, a small team's process written as code: implement, test,
review, keep evidence. The interesting result is not that this is novel; it is that it
transfers down to a 4B model when every step is bounded and checked, and that the process
stages have *different* measured value in this setting (section 2). The conventional
wisdom "write tests, review the change" is not uniformly true here: the model's own test
is worthless, and review without an independent test manufactures confident errors. The
process is worth codifying, but each stage must earn its place by measurement, not by
analogy to a human team.

## 5. Negative results worth recording

These are measured, not guessed, and each is a place a plausible design idea lost. They
are the most reusable single contribution of the project.

| idea | result |
| --- | --- |
| decomposition / step-splitting / multi-approach (tree of children; a tournament of Hows) | **harmful.** Monolithic leaf `47/70 (67.1%, 0 false)` vs tree-greedy `14/70 (20.0%, 4 false)` vs tree-tournament `15/70 (21.4%, 3 false)`; every paired delta CI has an upper bound below 0, p<0.001; the tree costs 2.2 to 2.4x the calls, 2.3 to 2.9x the wall and at least 1.85x the tokens. The mechanism verifiably fired (decomposition on 3 of 9 decomposable tasks in one arm, 4 of 9 in the other), so this is a valid negative, not an unfired mechanism. |
| injecting a context index (declared files in full, the rest as a compact index) | **harmful.** `13/24` vs `18/24` on the same 12 tasks x2, and `13/24` vs `19/24` against the pre-change revision `e190a4f` (commit `25dafaf`). Source is never hidden from the model now. |
| forcing a deterministic file-change order | **harmful.** `14/15` vs `7/15`. |
| a knowledge pack (signatures / callers / constants) injected per call | no gain (`4/15` vs `3/15`); off by default. |
| putting module importers into the write spec | no gain (`10/15` vs `10/15`). |
| extending the write boundary on rule evidence | no gain (`1/5` vs `1/5`). |
| competitive How exploration (a tournament of candidates) | fires, but costs `2.2` to `2.4x` the calls and fixes far fewer tasks (`15/70` vs `47/70`); greedy is the default. |
| asking a weak model to write and run its own tests (applied to the mature CLI) | **worse.** The 4B could not emit a whole test file as a tool argument (the write hit the output-token limit and was dropped or re-issued), and 9 of 10 runs in the last band ended on a length-truncated block. Measured at 8k context; not re-measured at 32k. |

The pattern across all of them: **structure that costs calls without adding information
loses.** What moved the numbers was giving the model more signal (a forced red-then-green
loop, deterministic diagnosis rules, coverage and discrimination checks), not more
elaborate control flow.

Caveat on the mature-CLI test-writing result: it was measured on the throttled 8k
baseline and is not re-measured at 32k, so it is recorded as known-at-8k only.

## 6. What is reusable, in one list

- The **design principle** (section 1): harness as program, model as a contract-bound
  fallback node, deterministic code owning every decidable fact.
- The **blind grading protocol** and the tamper guard (section 3).
- The **one-claim-gate invariant** with its structural test (section 2).
- The **evidence ledger** and the `EVIDENCE GAP` state (section 2).
- The **claim-basis distinction** (a claim is only as strong as the check that carried it).
- The **per-stage verification roles** and the finding that they are not interchangeable
  (section 2).
- The **evaluation checklists** (sections 2 and 3), including "compare delivered bytes to
  every written revision".
- The **negative results** (section 5), which save a future project from repeating them.
- The **generalisation**: a process works on a weak model only when each step is small,
  bounded, checked, and derived from a human team's real practice.

## 7. What is not reusable / does not transfer

- **The reliability advantage is not a moat.** The lower false-success rate (`2.2%` vs
  `6.1%`) comes from a claim gate that is straightforward to add to any agent; it is a
  property of a design, not a durable capability. Do not treat it as a competitive
  advantage.
- **The cost result is unfavourable.** The harness spent roughly twice the tokens of the
  mature CLI (`~18.9k` vs `~9k` per task) for no measured capability gain. Wall-clock
  evidence is not clean or comparable across arms (ours was measured on a concurrent
  server, `pi` sequentially), so do not quote it as a win either way. An earlier token
  headline (`−31.3%`) was retracted; it did not reproduce.
- **Nothing here generalises past its scope.** All results are for one 4B model, one
  40-task corpus and one baseline. There is no claim about stronger models, other
  corpora, other languages, or real repositories.
- **The decomposition result is corpus- and model-scoped.** The negative is strong on "the
  tree stage does not pay for itself here"; it bounds, but does not prove, "requirement-
  level splitting can never help" (the planner only split on a minority of tasks). The
  forced-leaf thresholds were never swept.
- **The internal verifiers share the model's weights.** Fresh context helps but does not
  make them independent; the external grader is the arbiter.

## 8. Future research directions

1. **A larger or differently shaped corpus.** The 40-task corpus structurally caps the
   resolvable difference at about 6.3 tasks even at infinite seeds. A decisive
   non-inferiority or superiority test needs a task set whose between-task heterogeneity
   is smaller relative to the effect, or a different design (paired within-task effect
   sizes with a pre-computed power analysis).
2. **The product CLI.** The command form the project was for (`helpagent "<request>"`,
   run against an arbitrary repository) was never built. Until it is run on an unseen
   repository that ships its own visible tests beside a hidden grading suite, the
   regression stage stays unobservable and real-world transfer is untested.
3. **Cheap fixes to the known harness defects.** The forensics named concrete ones:
   redirect on a refusal instead of a six-attempt loop; accumulate multi-file changes
   instead of erasing a partial fix; rank the delivered revision by how much of the
   required surface it covers, not only by evidence tier; apply the "non-discriminating
   check cannot carry a claim" rule to the plain green path as well as the review path;
   persist the per-attempt model output so forensics can read it directly.
4. **A stronger prompt for the baseline, measured.** The `pi` arm with an improved prompt
   was never measured (environment blocker), so "structure beats a better prompt" remains
   untested.
5. **The decomposition question done differently.** Sweep the forced-leaf thresholds and
   test requirement-level splitting only on tasks that genuinely need it, with a design
   that isolates splitting from planning overhead.
6. **Cost.** Cut tokens without hiding source, and measure a clean single-lane wall clock
   for both arms.

## 9. Where the evidence is

- Measured position and reproduction commands: [`STATUS.md`](STATUS.md).
- Slices and acceptance-criteria verdicts: [`ROADMAP.md`](ROADMAP.md).
- Measurement records, raw-row recomputation and provenance:
  [`.scratch/28-three-requirements/issues/`](../.scratch/28-three-requirements/issues/)
  (`fix-wave-1-measurement-n25.md`, `requirement-2-ablation.md`,
  `requirement-3-result.md`, `final-measurement-independent-verification.md`).
- Design and flow: [`DESIGN.md`](DESIGN.md), [`FLOW.md`](FLOW.md).
- Curated baseline evidence: [`bench/runs/evidence/`](../bench/runs/evidence/).
