# CONFIRMED

## The three requirements and their verdicts

The campaign set out to settle three claims about process, not about the model. Final verdicts,
all measured on revision `45ebb32` under the fair precondition in
`docs/6_ARCHITECTURE.md#fair-comparison-precondition`:

| requirement | verdict | decisive numbers |
| --- | --- | --- |
| **R1 capability parity** (ours >= `pi` within the error margin) | **INCONCLUSIVE** | N=25/arm: ours `24.640/40` (sd 1.22) vs `pi` `24.960/40` (sd 2.15); delta `−0.320` tasks `= −0.8%`; task-clustered 95% CI `[−3.520, +3.080]`; pre-registered `M=3` rule returns INCONCLUSIVE by `0.52` tasks; the CI width was flat over N=17..25, so further seeds alone are not projected to resolve it at the observed task effects. |
| **R2 verification carries information** | **PARTLY / not as stated** | own-test loop `−1.33` tasks (CI `[−5.67, +3.00]`, p=0.55), net correctness effect unresolved; independent-test correctness effects unresolved, `−8.67` claims (p=0.0009) and `−3.00` false successes (p=0.031) with review present; review `+4.00` correctness (p=0.012) with independent test present, and `+3.33` false successes (p=0.031) without it; interaction not established. |
| **R3 decomposition / multi-approach** | **NEGATIVE** | leaf `47/70 (67.1%, 0 false)` vs tree-greedy `14/70 (20.0%, 4 false)` vs tree-tournament `15/70 (21.4%, 3 false)`; paired delta CI upper bounds below 0, p<0.001; negative for the current tree bundle, not isolated decomposition or field refinement. |

The three requirements map to the acceptance criteria as R1 = C1 + C4 + C5, R2 = C2 and R3 = the
structural-superiority part of C4
(`docs/2_GOAL.md#the-acceptance-criteria-and-their-verdicts`).

## The campaign slices and their verdicts

The product surface of this project is a command and the honest report it prints, so every slice
is something a person can run and look at, and a slice is done when it can be seen rather than
when the code for it exists.

| # | what you can see | final state |
| --- | --- | --- |
| **V1** | *One task, fixed, with its evidence.* Hand the harness a request; it edits the repo, runs its own verification, and prints what it changed, what it verified, and what it could not. | **done** |
| **V2** | *The honest scoreboard.* Run a corpus slice and get a table: what the harness claimed, what an independent grader actually found, and the trajectory behind each. | **done** |
| **V3** | *It does not lie, and it explains itself.* Every task that fails prints a one-line reason you can check against its trajectory, and the false-success column is zero. | **not closed** — the false-success rate was cut to `2.20%` head-to-head (ours) and to `1/120` in the full ablation arm, but not to zero; per-task failure verdicts exist for the campaign revision, and the final fix wave changed which tasks fail |
| **V4** | *It beats the mature CLI on the same model, and costs less.* Run both arms on the same 40 tasks and see one side-by-side table: actual, claimed, tokens, wall-clock. | **not met** — head-to-head is INCONCLUSIVE at the pre-registered margin (`24.640/40` vs `24.960/40`), and tokens are about `2x` the baseline's (`~18.9k` vs `~9k`); the improved-prompt baseline arm is unmeasured |
| **V5** | *It works on a repository it has not seen before.* Point it at a repo that ships its own visible tests plus a hidden grading suite, and it behaves the same as on the corpus. | **open / not attempted** — on today's corpus the regression stage is unobservable |
| **V6** | *The product.* One command you can point at your own repository: `helpagent "<request>"` → it edits, verifies, and prints what it verified and what it could not, with the evidence trail on disk. | **open / does not exist** — this is the thing the research was for; it was never built |

The two runnable slices, V1 and V2, work now:

```sh
# V1 — one task, end to end
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 --calls 24 --out /tmp/slice1

# V2 — the honest scoreboard for a slice of the corpus
curl -fsS --max-time 3 http://127.0.0.1:8834/health     # the model server must answer ok
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 \
  --verify full --server http://127.0.0.1:8834
```

The campaign's three verdicts are recorded and their numerical results were independently
recomputed from the raw rows; that recomputation does not validate the causal interpretations.
Everything else is either not closed (V3, C1–C4) or never attempted (V5, V6). The bounded
final-revision explanations in `.scratch/29-close-audit/report.md` do not close C3: missing
records and ungraded intermediate candidates remain explicitly unknown.

## The acceptance criteria and their verdicts

| # | criterion | verdict | evidence |
| --- | --- | --- | --- |
| C1 | coding >= `pi` on the same model with every knob maxed, and better in wall-clock and tokens | **NOT MET** | parity not established (INCONCLUSIVE at `M=3`, CI `[−3.520, +3.080]`); tokens about `2x` worse; wall-clock not cleanly comparable. |
| C2 | verification carries information (no meaningless test or review; failures traced to their exact deviation point) | **NOT MET as stated** | the own-test loop has no detected net correctness gain (`−1.33 [−5.67, +3.00]`, p=0.55), not proven zero information; review without independent test raises false successes (`+3.33`, p=0.031), while with independent test its correctness contrast is positive (`+4.00`, p=0.012); interaction not established and final failures not fully traced. |
| C3 | no unexplained failures: every remaining failure has an evidenced `our-defect` (with the fix) or `model-ceiling` (with the evidence), zero false successes | **NOT MET** | per-task verdicts exist for the campaign revision (`d24410a`), but the final wave (`45ebb32`) changed which tasks fail; the final false-success rate is `2.20%` at N=25, not zero. |
| C4 | structural superiority: work that prompting alone cannot get out of `pi` but the structure can | **NOT SHOWN** | the current tree bundle is NEGATIVE; splitting and field refinement were not isolated from planning, budget and delivery policy; no aggregate coding difference was detected (parity not established; INCONCLUSIVE at `M=3`); the improved-prompt baseline arm is unmeasured. |
| C5 | efficiency measured, not assumed | **MET (result unfavourable)** | tokens measured for ours (`~18.9k`/task) and partly for `pi` (`~9k`); the honest result is that the harness costs roughly twice as much. |

# INFERRED

## R1 capability parity

Head-to-head, same server, same grader, N=25 seeds/arm (1000 rows/arm), 0 crashes and 0 timeouts
in the recorded driver-level metrics. Revision `45ebb32`; the frozen N=17 result was reused and
seeds 18..25 added. Those metrics do not mean every inference completed: retained final-revision
`pi` samples contain length stops and explicit context-size errors before any code write; the
bounded audit (`.scratch/29-close-audit/report.md`) distinguishes them from driver timeout and
leaves their runtime capacity cause unknown.

| | ours (N=25) | `pi` (N=25, same server) |
| --- | --- | --- |
| **actual** | `616/1000 = 61.6%` | `624/1000 = 62.4%` |
| actual per 40-task run | mean `24.640`, sd `1.221` | mean `24.960`, sd `2.150` |
| **false success** | `22/1000 = 2.20%` | `61/1000 = 6.10%` |
| claimed (not comparable across arms) | `224/1000` | `647/1000` |

- **Delta** = `actual(ours) − actual(pi)` = `−0.320` tasks (`−0.8%`).
- **Task-clustered percentile-bootstrap 95% CI** `[−3.520, +3.080]` (seed `20261013`, B=20000).
- **Pre-registered rule (`M = 3` tasks):** `Lo95 >= −M` means parity within margin, `Hi95 < −M`
  means behind, otherwise inconclusive. `−3.520 >= −3` is false by `0.520` tasks and
  `+3.080 < −3` is false, so the verdict is **INCONCLUSIVE**: the point estimate is a near-tie,
  but the frozen test establishes neither parity within margin nor inferiority.

**Why N=25 did not resolve it (projection from observed task effects).** The CI half-width is
about `3.3` tasks and is flat over N=17..25 (full width `6.53` to `6.60`). It is set by
between-task heterogeneity in the 40-task corpus, not by seed noise: at N=25 the within-seed
variance contributes only about `8.7%` of the per-task-mean variance, leaving a `~6.3`-task
asymptotic width projected from the observed effects. At that width the rule would need the point
estimate to move to about `+0.3` tasks, or a different or larger task set, to return ACHIEVED.
This is not proof that more seeds cannot change the estimate, nor that the capability goal is
impossible.

**Where the starting position came from.** The 2026-10-09 campaign measurement on revision
`6b224f5` was ours `24/40` vs `pi` `27/40`, caused by a discarded grader-passing revision in
**T-07**, the closed T-30 claim hole, and content in **T-14**. The two parity losses on the next
revision (T-17, T-28) were both harness defects of the same kind: a **grader-passing revision
inside the run that the harness threw away** (T-17: 4 of 7 written revisions passed, the delivered
one failed; T-28: a discarded revision passed 4/4, the delivered one failed 4/4). Fixing the
delivery path (the fix wave at `45ebb32`) moved the position to the tie reported above.

## R2 verification information

`600` runs (5 arms x 40 tasks x 3 repeats) on revision `45ebb32`, external grader only. The ladder
is cumulative, one stage added per arm.

| arm (what runs) | actual | claimed | **false success** | calls/task | tokens/task | wall s/task |
| --- | --- | --- | --- | --- | --- | --- |
| A0 development only (no verification, never claims) | `70/120 (58.3%)` | 0 | **0** | 1.01 | 1,198 | 7.5 |
| A1 + the run's own test | `66/120 (55.0%)` | 0 | **0** | 5.54 | 8,480 | 49.8 |
| A2 + own test + independent test | `65/120 (54.2%)` | 1 | **0** | 6.63 | 10,570 | 58.3 |
| A3 + own test + review | `71/120 (59.2%)` | 54 | **10** | 9.13 | 12,696 | 60.7 |
| A4 full (own test + independent test + review + claim gate) | `77/120 (64.2%)` | 28 | **1** | 12.86 | 18,894 | 97.9 |

Paired stage-enable contrasts (net workflow effects, 40 tasks, 95% percentile bootstrap, seed
`20261013`); enabling a stage also changes feedback, iteration, stopping and delivery, so this
does not isolate the information in a test or review:

| contrast | stage enabled | Δactual [95% CI] | p | Δclaimed | Δfalse [95% CI] | p |
| --- | --- | --- | --- | --- | --- | --- |
| A1 − A0 | own test | `−1.33 [−5.67, +3.00]` | 0.549 | +0.00 | `+0.00 [0.00, 0.00]` | 1.000 |
| A2 − A1 | independent test | `−0.33 [−3.00, +2.33]` | 1.000 | +0.33 | `+0.00 [0.00, 0.00]` | 1.000 |
| A3 − A1 | review (independent test absent) | `+1.67 [−1.33, +5.33]` | 1.000 | +18.00 | `+3.33 [+1.00, +6.33]` | 0.031 |
| A4 − A2 | review (independent test present) | `+4.00 [+1.33, +7.00]` | **0.012** | +9.00 | `+0.33 [0.00, +1.00]` | 1.000 |
| A4 − A3 | independent test (review present) | `+2.00 [−0.67, +4.67]` | 0.388 | −8.67 | `−3.00 [−5.67, −1.00]` | 0.031 |

Reading it:

- **No net correctness gain was detected from enabling the own-test loop.** Its CI
  `[−5.67, +3.00]` includes losses and gains; this is not proof of zero information or
  equivalence. Own tests never directly carried a claim, but can change code and block later
  claims. The loop costs about 7x the tokens and 6.6x the wall time of development-only.
- **The independent-test contrasts leave correctness unresolved and reduce false claims with
  review present.** Claims fall (`−8.67`, p=0.0009) and false successes fall
  (`−3.00 [−5.67, −1.00]`, p=0.031). In the full arm it withheld approval in `92/110` runs, `57` of
  which the final grader passed; that join is not an independent diagnostic-accuracy experiment.
- **Review has a positive correctness contrast with independent test present.** `A4−A2` is
  `+4.00 [+1.33, +7.00]`, p=0.012. Without independent test, `A3−A1` has no detected correctness
  effect and increases false successes by `+3.33`. A significant contrast beside a nonsignificant
  one does not establish that their difference (the interaction) is significant.
- **The requirement remains not met as stated.** The net full-stack gain is unresolved
  (`+2.33 [−0.33, +5.33]`, p=0.34), not every final failure has a deviation-point explanation, and
  the final R2 A-05#1 shows independent test and review jointly approving wrong answers. These
  workflow measurements do not measure information content. Small N, unmatched stage costs and
  multiple unadjusted contrasts limit interpretation; see the measurement record and the bounded
  final-revision audit (`.scratch/29-close-audit/report.md`).

## R3 decomposition and multi-approach

`210` runs (14 tasks x 3 arms x N=5) on revision `45ebb32`, paired by `(task, seed)`,
pre-registered rule fixed before any outcome was read.

| arm | actual | claimed | **false success** | mean calls/task | mean wall s/run |
| --- | --- | --- | --- | --- | --- |
| B0 monolithic leaf | `47/70 (67.1%)` | 8/70 | **0** | 14.4 | 175 |
| B1 tree-greedy (`--how-explore 1`) | `14/70 (20.0%)` | 18/70 | **4** | 31.6 | 408 |
| B2 tree-tournament (`--how-explore 3`) | `15/70 (21.4%)` | 18/70 | **3** | 35.2 | 498 |

Paired deltas (tree − leaf), 95% bootstrap CI, seed `20261013`:

| comparison | mean delta | 95% CI | tree-only / leaf-only fixes | McNemar p |
| --- | --- | --- | --- | --- |
| B1 vs leaf, decomposable tasks | `−0.444` | `[−0.733, −0.178]` | 0 / 20 | 0.000 |
| B1 vs leaf, forced-leaf tasks | `−0.520` | `[−0.920, −0.120]` | 1 / 14 | 0.001 |
| B2 vs leaf, decomposable tasks | `−0.422` | `[−0.689, −0.178]` | 2 / 21 | 0.000 |
| B2 vs leaf, forced-leaf tasks | `−0.520` | `[−0.800, −0.240]` | 1 / 14 | 0.001 |

The pre-registered rule returns NEGATIVE for both current tree arms (every decomp-related CI upper
bound is below 0). Decomposition ran in `3/70` runs on `3/9` decomposable tasks (B1) and `9/70`
runs on `4/9` tasks (B2); this establishes that it sometimes fired, not causal isolation. The tree
cost `2.2` to `2.4x` the calls, `2.3` to `2.9x` the wall and at least `1.85x` the tokens, for one
third of the leaf's grader passes.

**The current tree bundle is worse here; decomposition, field refinement and structural
superiority in general are not refuted.** It changes planning, spec rewriting, budget and
delivery as well as splitting: tree merges only closed, claimed candidates, whereas leaf also
delivers unclaimed code. Both tree arms delivered pristine Python source on all 52 unclaimed
failures; leaf passed 39 unclaimed runs. The deleted tree candidates cannot establish how many
were correct. See `.scratch/29-close-audit/report.md` for code and byte evidence and its limits.

## Known limits

What the results cannot carry. Every one is accepted, none is pretended away:

1. **Two verifications that share the same misreading agree**, so a wrong fix can be certified.
   The internal checks share the model's weights; the external grader is the only correctness
   arbiter.
2. **The harness is not an oracle.** Its own claim is evidence, not proof; every number here is
   the grader's verdict, never the harness's.
3. **Adversarial code can forge the gate's own evidence** (it runs in the same process and
   filesystem). This is tamper-*evident* (every anomaly is recorded) but not prevented.
4. **A weak-but-genuinely-discriminating test** (red on the pristine source, green on the final)
   passes the harness's checks even if it does not encode the requirement. This is the class that
   produced the residual false successes.
5. **Missed success is the strongest residual on the quality axis**: runs that fix the task and
   cannot verify it. The ledger names the unverifiable criterion and why.
6. **The review tier is measured, not proven.** Its error rate is the reviewing model's own; a
   consumer that cannot tolerate it should filter on the recorded claim basis.
7. **The regression stage is unobservable on this corpus.** Each task's `repo/tests/` is the
   grader's suite and the blind protocol withholds it, so the staged view usually contains no
   visible test file. On these 40 tasks "no regression" rests on the external grader's own suite.
8. **The remaining false successes are on the plain green path** (own test green, independent
   test green, review approved, grader rejects). The rules that close the review route are not
   fully applied to the green route.
9. **Scope.** Every result is for one model (Spark-X2.5-4B Q4_K_M), one revision (`45ebb32`) and
   one 40-task corpus. No claim is made about other models, corpora or real repositories.
10. **The three verdicts' numbers were recomputed from the raw rows by an independent
    fresh-context worker with no discrepancy.** That validates the arithmetic, not the causal
    reading.
11. **Unfinished and open:** no proof of superiority and no proof of impossibility; the product
    CLI does not exist; the improved-prompt `pi` arm is unmeasured; `pi` token cost is partly
    unmeasured; a clean single-lane wall-clock comparison is outstanding.

## Retractions

Each retraction is kept visible because the reason is part of the method:

| claim withdrawn | why | status |
| --- | --- | --- |
| the token headline "`−31.3%`" | it did not reproduce | retracted |
| "this harness is cheaper than the mature CLI" (the wall-clock reading behind it) | the two arms' wall-clock conditions differ (concurrent against sequential) and are not comparable; the only indicative number is a single 8-task run, `31.0 s/task` against `47.5 s/task` | retracted; neither reading may be claimed as a win |
| the early maturity comparison, which judged `pi` weaker | it clamped the baseline itself (thinking off, 8k context); re-measured under the fair precondition, the result is worse for us | retracted |
