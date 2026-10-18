# Status — the final measured position

This is the current-state record for the helpagent research project. The project is
**campaign complete and research archived**: the campaign has run to its pre-registered end and reported its verdicts. The goals (match or beat a mature agent CLI on the same model, without lying, with verification that carries information) remain unmet or unresolved, not disproved. The product CLI does not exist.

Every number here was measured on revision `45ebb32`, with the same reference model, the
same server window and a blind external grader. When this document and the run records
disagree, the records win; when it and the code disagree, the code and its tests win. The
narrative and the raw provenance are in the work record
[`.scratch/28-three-requirements/`](../.scratch/28-three-requirements/issues/28-three-requirements.md).

## 1. Fair comparison precondition

Held equal for every arm in the final measurement:

- **model:** Spark-X2.5-4B (`Spark-X2.5-4B-Q4_K_M.gguf`) on llama.cpp;
- **server:** one local server, `-c 32768` with `--cache-type-k q8_0 --cache-type-v q8_0`;
- **corpus:** the same 40 tasks (T-01..T-35 + anchors A-01..A-05);
- **grader:** each task's own withheld suite, applied to a pristine copy after the run
  (blind: the grader never enters a run);
- **baseline configuration:** the `pi` CLI with `--thinking max --reasoning` (the
  baseline's own knobs maxed), not throttled.

## 2. The three requirements — final verdicts

| requirement | verdict | decisive numbers |
| --- | --- | --- |
| **R1 capability parity** (ours >= `pi` within the error margin) | **INCONCLUSIVE** | N=25/arm: ours `24.640/40` (sd 1.22) vs `pi` `24.960/40` (sd 2.15); delta `−0.320` tasks `= −0.8%`; task-clustered 95% CI `[−3.520, +3.080]`; pre-registered `M=3` rule returns INCONCLUSIVE by `0.52` tasks; the CI width was flat over N=17..25, so further seeds alone are not projected to resolve it at the observed task effects. |
| **R2 verification carries information** | **PARTLY / not as stated** | own-test loop `−1.33` tasks (CI `[−5.67, +3.00]`, p=0.55), net correctness effect unresolved; independent-test correctness effects unresolved, `−8.67` claims (p=0.0009) and `−3.00` false successes (p=0.031) with review present; review `+4.00` correctness (p=0.012) with independent test present, and `+3.33` false successes (p=0.031) without it; interaction not established. |
| **R3 decomposition / multi-approach** | **NEGATIVE** | leaf `47/70 (67.1%, 0 false)` vs tree-greedy `14/70 (20.0%, 4 false)` vs tree-tournament `15/70 (21.4%, 3 false)`; paired delta CI upper bounds below 0, p<0.001; negative for the current tree bundle, not isolated decomposition or field refinement. |

The three requirements map to the acceptance criteria as R1 = C1 + C4 + C5, R2 = C2 and
R3 = the structural-superiority part of C4. The criterion-by-criterion verdicts are in
[`ROADMAP.md`](ROADMAP.md).

## 3. R1 — capability parity (INCONCLUSIVE)

Head-to-head, same server, same grader, N=25 seeds/arm (1000 rows/arm), 0 crashes and 0
timeouts in the recorded driver-level metrics. Revision `45ebb32`; the frozen N=17 result was reused and seeds 18..25 added. Those metrics do not mean every inference completed: retained final-revision `pi` samples contain length stops and explicit context-size errors before any code write; the [bounded audit](../.scratch/29-close-audit/report.md) distinguishes them from driver timeout and leaves their runtime capacity cause unknown.

| | ours (N=25) | `pi` (N=25, same server) |
| --- | --- | --- |
| **actual** | `616/1000 = 61.6%` | `624/1000 = 62.4%` |
| actual per 40-task run | mean `24.640`, sd `1.221` | mean `24.960`, sd `2.150` |
| **false success** | `22/1000 = 2.20%` | `61/1000 = 6.10%` |
| claimed (not comparable across arms) | `224/1000` | `647/1000` |

- **Delta** = `actual(ours) − actual(pi)` = `−0.320` tasks (`−0.8%`).
- **Task-clustered percentile-bootstrap 95% CI** `[−3.520, +3.080]` (seed `20261013`,
  B=20000).
- **Pre-registered rule (`M = 3` tasks):** `Lo95 >= −M` means parity within margin,
  `Hi95 < −M` means behind, otherwise inconclusive. `−3.520 >= −3` is false by `0.520`
  tasks and `+3.080 < −3` is false, so the verdict is **INCONCLUSIVE**: the point estimate
  is a near-tie, but the frozen test establishes neither parity within margin nor
  inferiority.

**Why N=25 did not resolve it (projection from observed task effects).** The CI half-width is about
`3.3` tasks and is flat over N=17..25 (full width `6.53` to `6.60`). It is set by
between-task heterogeneity in the 40-task corpus, not by seed noise: at N=25 the
within-seed variance contributes only about `8.7%` of the per-task-mean variance, leaving a
`~6.3`-task asymptotic width projected from the observed effects. At that width the rule would need the point estimate to move to about `+0.3` tasks, or a different or larger task set, to return ACHIEVED. This is not proof that more seeds cannot change the estimate, nor that the capability goal is impossible.

**Where the starting position came from.** The 2026-10-09 campaign measurement on revision
`6b224f5` was ours `24/40` vs `pi` `27/40`, caused by a discarded grader-passing revision in
**T-07**, the closed T-30 claim hole, and content in **T-14**. The two parity losses on the
next revision (T-17, T-28) were both harness defects of the same kind: a **grader-passing
revision inside the run that the harness threw away** (T-17: 4 of 7 written revisions passed,
the delivered one failed; T-28: a discarded revision passed 4/4, the delivered one failed
4/4). Fixing the delivery path (the fix wave at `45ebb32`) moved the position to the tie
reported above.

## 4. R2 — verification information (five-arm ablation)

`600` runs (5 arms x 40 tasks x 3 repeats) on revision `45ebb32`, external grader only. The
ladder is cumulative, one stage added per arm.

| arm (what runs) | actual | claimed | **false success** | calls/task | tokens/task | wall s/task |
| --- | --- | --- | --- | --- | --- | --- |
| A0 development only (no verification, never claims) | `70/120 (58.3%)` | 0 | **0** | 1.01 | 1,198 | 7.5 |
| A1 + the run's own test | `66/120 (55.0%)` | 0 | **0** | 5.54 | 8,480 | 49.8 |
| A2 + own test + independent test | `65/120 (54.2%)` | 1 | **0** | 6.63 | 10,570 | 58.3 |
| A3 + own test + review | `71/120 (59.2%)` | 54 | **10** | 9.13 | 12,696 | 60.7 |
| A4 full (own test + independent test + review + claim gate) | `77/120 (64.2%)` | 28 | **1** | 12.86 | 18,894 | 97.9 |

Paired stage-enable contrasts (net workflow effects, 40 tasks, 95% percentile bootstrap, seed `20261013`); enabling a stage also changes feedback, iteration, stopping and delivery, so this does not isolate the information in a test or review:

| contrast | stage enabled | Δactual [95% CI] | p | Δclaimed | Δfalse [95% CI] | p |
| --- | --- | --- | --- | --- | --- | --- |
| A1 − A0 | own test | `−1.33 [−5.67, +3.00]` | 0.549 | +0.00 | `+0.00 [0.00, 0.00]` | 1.000 |
| A2 − A1 | independent test | `−0.33 [−3.00, +2.33]` | 1.000 | +0.33 | `+0.00 [0.00, 0.00]` | 1.000 |
| A3 − A1 | review (independent test absent) | `+1.67 [−1.33, +5.33]` | 1.000 | +18.00 | `+3.33 [+1.00, +6.33]` | 0.031 |
| A4 − A2 | review (independent test present) | `+4.00 [+1.33, +7.00]` | **0.012** | +9.00 | `+0.33 [0.00, +1.00]` | 1.000 |
| A4 − A3 | independent test (review present) | `+2.00 [−0.67, +4.67]` | 0.388 | −8.67 | `−3.00 [−5.67, −1.00]` | 0.031 |

Reading it:

- **No net correctness gain was detected from enabling the own-test loop.** Its CI `[−5.67, +3.00]` includes losses and gains; this is not proof of zero information or equivalence. Own tests never directly carried a claim, but can change code and block later claims. The loop costs about 7x the tokens and 6.6x the wall time of development-only.
- **The independent-test contrasts leave correctness unresolved and reduce false claims with review present.** Claims fall (`−8.67`, p=0.0009) and false successes fall (`−3.00 [−5.67, −1.00]`, p=0.031). In the full arm it withheld approval in `92/110` runs, `57` of which the final grader passed; that join is not an independent diagnostic-accuracy experiment.
- **Review has a positive correctness contrast with independent test present.** `A4−A2` is `+4.00 [+1.33, +7.00]`, p=0.012. Without independent test, `A3−A1` has no detected correctness effect and increases false successes by `+3.33`. A significant contrast beside a nonsignificant one does not establish that their difference (the interaction) is significant.
- **The requirement remains not met as stated.** The net full-stack gain is unresolved (`+2.33 [−0.33, +5.33]`, p=0.34), not every final failure has a deviation-point explanation, and the final R2 A-05#1 shows independent test and review jointly approving wrong answers. These workflow measurements do not measure information content. Small N, unmatched stage costs and multiple unadjusted contrasts limit interpretation; see the measurement record and [bounded final-revision audit](../.scratch/29-close-audit/report.md).

## 5. R3 — decomposition / multi-approach (NEGATIVE)

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

The pre-registered rule returns NEGATIVE for both current tree arms (every decomp-related CI upper bound is below 0). Decomposition ran in `3/70` runs on `3/9` decomposable tasks (B1) and `9/70` runs on `4/9` tasks (B2); this establishes that it sometimes fired, not causal isolation. The tree cost `2.2` to `2.4x` the calls, `2.3` to `2.9x` the wall and at least `1.85x` the tokens, for one third of the leaf's grader passes.
**The current tree bundle is worse here; decomposition, field refinement and structural superiority in general are not refuted.** It changes planning/spec rewriting, budget and delivery as well as splitting: tree merges only closed, claimed candidates, whereas leaf also delivers unclaimed code. Both tree arms delivered pristine Python source on all 52 unclaimed failures; leaf passed 39 unclaimed runs. The deleted tree candidates cannot establish how many were correct. See [ticket 29](../.scratch/29-close-audit/report.md) for code/byte evidence and limits.

## 6. Cost

- **Tokens: ours about `18.9k`/task (4-lane, 40 tasks) vs `pi` about `9k`.** The harness is
  roughly twice as expensive, not cheaper. (`pi`'s token count is partly unmeasured: the driver carries no
  token counters, so its `~9k` comes from the recorded reference and is not recomputable
  from the final rows.)
- **Wall-clock is not clean or comparable.** Ours was measured under concurrency and `pi`
  sequentially, so the two are not like-for-like. A single-lane subset measured ours at
  `31.0 s/task` vs `pi` at `47.5 s/task` (8 tasks, single run, skewed easy-ish), which is
  indicative only. A clean single-lane 40-task comparison for both arms is outstanding and
  is recorded as open.
- An earlier token headline (`−31.3%`) was retracted; it did not reproduce.

## 7. False successes and honesty

- **Head-to-head (N=25):** ours `22/1000 = 2.20%` vs `pi` `61/1000 = 6.10%`. The
  task-clustered CI on the difference is `−1.56 tasks [−3.16, −0.20]` (ours better).
- **Ablation (600 runs):** false successes `0 / 0 / 0 / 10 / 1` across the five arms; the
  one false success in the full arm (A-05) rested on both the independent test and the
  review approving a solution the grader failed.
- **`pi`'s "claimed" column is not comparable to ours.** `pi` has no claim gate: its
  "claimed" is a regex read of its final assistant message, and its non-claims are mostly
  empty or truncated final messages, not admissions of failure. Only `actual` and
  false-success are comparable across the two arms.
- The claim gate is what makes false successes a measurable quantity, but it does not
  eliminate them: the final rate is about `2.2%` at N=25.

## 8. What the harness does (implementation summary)

- **Blind protocol.** The run never sees the grader's tests; it stages source, works in a
  sandbox, and is scored afterwards on a pristine copy.
- **Self-verification that cannot lie about itself.** The gate is a machine-readable pytest
  report on a private path with a per-run canary and the expected test ids. An exit status
  is never evidence.
- **One claim gate.** A claim is granted in exactly one function
  (`harness/leaf.py::claim_decision`), and a structural test fails the suite if any other
  code path could grant one. It refuses a claim when the run's own test is red, when
  coverage missed a criterion's named artifact, when there are no criteria, or when the
  evidence ledger is empty.
- **Evidence in both directions.** Every acceptance criterion gets a ledger row (satisfied
  / violated / unverifiable) pointing at what was observed. A stop with no row is an
  `EVIDENCE GAP`.
- **Greedy by default.** A node plans ranked approaches (Hows), takes the top one and
  spends its budget there; competitive exploration of several candidates is opt-in
  (`--how-explore`), and measured it costs several times more and fixes fewer tasks.

## 9. What was tried and did not help

| mechanism | result |
| --- | --- |
| current tree / multi-approach bundle | harmful here; splitting and field refinement not isolated (R3 above) |
| injecting a knowledge pack (signatures / callers / constants) | no gain (`4/15` vs `3/15`) |
| putting module importers into the write spec | no gain (`10/15` vs `10/15`) |
| forcing a deterministic file-change order | harmful (`14/15` vs `7/15`) |
| extending the write boundary on rule evidence | no gain (`1/5` vs `1/5`) |
| competitive How exploration (a tournament of candidates) | fires, but costs `2.2` to `2.4x` the calls and fixes far fewer tasks (`15/70` vs `47/70`); greedy is the default |
| the bounded source index (declared files in full, the rest as an index) | harmful (`13/24` vs `18/24`; `13/24` vs `19/24` against the pre-change revision `e190a4f`, commit `25dafaf`) |
| asking the mature CLI to write and run its own tests | worse at 8k (`16/40` vs `21/40`); the 4B could not emit a whole test file as one tool argument. Not re-measured at 32k |

These implementations spent extra calls without a measured net capability gain; this does not show that structure in general cannot help.

## 10. Known limits (accepted, not pretended away)

1. **Two verifications that share the same misreading agree**, so a wrong fix can be
   certified. The internal checks share the model's weights; the external grader is the
   only correctness arbiter.
2. **The harness is not an oracle.** Its own claim is evidence, not proof; every number
   here is the grader's verdict, never the harness's.
3. **Adversarial code can forge the gate's own evidence** (it runs in the same process and
   filesystem). This is tamper-*evident* (every anomaly is recorded) but not prevented.
4. **A weak-but-genuinely-discriminating test** (red on the pristine source, green on the
   final) passes the harness's checks even if it does not encode the requirement. This is
   the class that produced the residual false successes.
5. **Missed success is the strongest residual on the quality axis**: runs that fix the task
   and cannot verify it. The ledger names the unverifiable criterion and why.
6. **The review tier is measured, not proven.** Its error rate is the reviewing model's
   own; a consumer that cannot tolerate it should filter on the recorded claim basis.
7. **The regression stage is unobservable on this corpus.** Each task's `repo/tests/` is
   the grader's suite and the blind protocol withholds it, so the staged view usually
   contains no visible test file. On these 40 tasks "no regression" rests on the external
   grader's own suite.
8. **The remaining false successes are on the plain green path** (own test green,
   independent test green, review approved, grader rejects). The rules that close the
   review route are not fully applied to the green route.
9. **Scope.** Every result is for one model (Spark-X2.5-4B Q4_K_M), one revision
   (`45ebb32`) and one 40-task corpus. No claim is made about other models, corpora or
   real repositories.
10. **Unfinished and open:** no proof of superiority and no proof of impossibility; the
    product CLI does not exist; the improved-prompt `pi` arm is unmeasured; `pi` token cost
    is partly unmeasured; a clean single-lane wall-clock comparison is outstanding.

## 11. Reproducing the numbers

```sh
# unit/contract gate (no model required), including the tamper guard and corpus integrity
uv run pytest

# the model server (final measurement config)
llama-server \
  -m /path/to/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health     # {"status":"ok"}

# R1 our arm, one task (leaf flow, full verification)
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 \
  --calls 24 --deadline-hours 6 --verify full

# R1 pi arm (maxed baseline)
uv run python bench/pi_baseline.py --tasks T-02-off-by-one --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max --out /tmp/pi-run

# R2 five-arm ablation (one arm per invocation; see the measurement record for the four arms)
uv run python bench/v2_measure.py --tasks "<task list>" --n 1 \
  --server http://127.0.0.1:8834 --ablate none --out /tmp/ablation

# R3 decomposition arms
uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading \
  --server http://127.0.0.1:8834 --calls 48 --deadline-hours 1 --how-explore 1 --out /tmp/tree
```

The frozen revision is `45ebb32`. The exact commands, seed lists, analysis scripts and
per-task tables for each requirement are in the work record
[`.scratch/28-three-requirements/issues/`](../.scratch/28-three-requirements/issues/):
`fix-wave-1-measurement-n25.md` (R1), `requirement-2-ablation.md` (R2),
`requirement-3-result.md` (R3), and `final-measurement-independent-verification.md` (a
fresh-context recomputation of all three from the raw rows).

## 12. Evidence and work records

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/28-three-requirements/issues/` for this campaign; earlier tickets
  under `.scratch/17-*` .. `.scratch/27-*`.
- The extraction document (what is reusable, what is not): [`LEARNINGS.md`](LEARNINGS.md).
