# Ablation + measurement protocol for R2/R3

READ-ONLY. Companion to `verification-decomposition-forensics.md`; both are the only
outputs of this task. No code was modified.

**R2/R3 (recorded inference).** Not named in-repo; mapped from the objective's structure
and `docs/ROADMAP.md` to **R2 = C2 "verification carries information (no meaningless test
or review)"** and **R3 = C4 "structural superiority"** (see the forensics doc §0). The
protocol is written so either mapping can be re-labelled without changing the runs.

The whole design rests on one rule already in the codebase (STATUS limit 2, FLOW §4 H6):
the **external grader's verdict is the only correctness arbiter**; the harness's own claim
is evidence, never truth. Every metric below joins a run record to `actual`/`grader_passed`
from `bench/v2_leaf.py::run_once`'s `delivery` event.

---

## 1. What already exists (do not rebuild)

`bench/v2_measure.py` (untracked in the working tree) is the measurement driver and
already does most of the plumbing:

* multi-seed repeats with mean + sample sd (`mean`, `stdev`, `rate_summary`,
  `per_task_means`, `arm_summary`);
* stage ablation via `--ablate NAME` with the exact disabled set printed and recorded
  (`ABLATIONS`: `none`, `independent-test`, `review`, `own-test`);
* single-lane wall clock (`--wall-clock`) and token accounting (`read_token_usage`, sums
  `metrics.prompt_tokens`/`completion_tokens` over every `model_call`);
* a pi-reference merge (`load_pi_reference`, `render_merged`);
* every run still routes through `bench.v2_leaf.run_once` → `harness.leaf.run_leaf` →
  the one `claim_decision`, so no claim semantics are re-implemented.

`bench/v2_sweep.py` is the older, simpler sweep (`--verify {raw,test,review,full}`).
`bench/v2_tree.py` runs the tree for ONE task and writes `run.json`.

## 2. Arms

### 2.1 R2 — cumulative verification ladder (additive design)

The objective names the arms as a ladder, which `ABLATIONS` cannot express (each entry
disables exactly one stage of the full pipeline, and `own-test` is coupled to `raw`).
The ladder is expressed with `--verify` + seam flags through `run_once`
(`bench/v2_leaf.py::run_once`, 798; the mode forcing starts at 808):

| arm | what runs | exact invocation |
| --- | --- | --- |
| A0 development-only | implement, no test/IV/review/claim | `--verify raw` |
| A1 + own test | + self-test red→green loop | `--verify test` |
| A2 + independent test | own test + IV, no review | `--verify full --no-review` |
| A3 + review | own test + review, no IV | `--verify full --no-iv` |
| A4 full | all three | `--verify full` |

A0/A1 are exactly `VERIFICATION_MODES`; A2/A3 are `full` with one seam off. The
complementary **subtractive** design is the existing `--ablate {none,independent-test,
review,own-test}`; run both so a stage's effect is measured from either direction.

### 2.2 R3 — monolithic vs decomposed (decomposition design)

| arm | what runs | exact invocation |
| --- | --- | --- |
| B0 monolithic | today's leaf (one write unit) | `bench/v2_sweep.py` / `v2_measure.py --verify full` |
| B1 greedy tree | How list, top How, one candidate | `bench/v2_tree.py --how-explore 1` |
| B2 tournament | parallel candidates, `harness.how.pick` | `bench/v2_tree.py --how-explore 3` |

B1/B2 must be crossed with the R2 ladder on the tail only (see §3), because the tree
currently has no `--verify` forwarding.

### 2.3 Controls held constant

* One model, one server config, one revision. Record the git SHA and server context size
  in the run root; never mix revisions in one comparison (STATUS §8e is one revision).
* Same budget per arm: `--calls` and `--deadline-hours` identical across arms. **Gap:**
  leaf defaults to 24 calls, tree to 48 — set both explicitly.
* One writer per work tree (`.scratch/active-work.md` standing rule); no lane runs while
  code is edited.

## 3. Task set

* **Full set:** 40 tasks (T-01..T-35 + A-01..A-05). Primary R2 arm comparison.
* **Tail set (R3):** the multi-part tasks where the forensics doc §4.4 predicts a
  delta — T-31, T-33, T-28, T-14, T-26, plus T-21, T-22 as inversion controls. B0/B1/B2
  run here only (cost), and B1/B2 also run on a 6-task easy/mid control (T-02, T-05, T-14,
  T-20, T-25, T-31) to show decomposition does not *regress* the bands the leaf passes.
* **Reduced R2 set (cost control):** T-06, T-10, T-12, T-19, T-20, T-21, T-22, T-35 (the
  inversion class) + T-01, T-05, T-16, T-27, T-28, T-30 (the delivery/claim class) — 14
  tasks that carry the whole measured effect, for a fast first pass.

## 4. Seeds (N)

There is no RNG seed: `harness/model.py::LlamaServerRunner` fixes `temperature=0.2` and
exposes no seed/temperature argument, so a "seed" is an independent stochastic repeat
(`--n`). Use:

* **N = 3** on the full 40-task R2 set (the driver default), **N = 5** on the 14-task
  reduced set and on the R3 tail, to tighten the per-task error bars where the effect is.
* The reason for ≥3: `arm_summary` returns `sd=0` for a single sample by design
  (`stdev` guards n<2), so N=1 cannot produce an error bar. The historical deltas are
  small (§1a: 52→61%), so a single run per task is not a measurement.

**Power note (state it in the pre-registration).** With 40 tasks and N seeds, the paired
per-task difference the design can detect at 95% is roughly ±1.5 tasks / 40 for a
consistent effect. The §1a self-test effect (18−17 = 1/33) is *below* that; the protocol
therefore declares the decision rule in terms of the *sign* of the paired difference with a
bootstrap CI, and treats "CI includes 0" as **inconclusive**, not as proof the stage adds
nothing. A stage is only ever called *zero-information* when the CI on both the actual-pass
delta and the false-success delta includes 0.

## 5. Metrics

Per run (already in the record): `actual`, `claimed`, `false_success = claimed && !actual`,
`stop_reason`, `claimed_basis`, `calls`, `run_wall_s`, `tokens_total`, `iv_verdicts`,
`review_verdicts`, `self_test`.

Aggregated per arm by `arm_summary`: rate + `sd` + `task_rate_sd` + per-task rates for
actual/claimed/false-success, and `wall_s_per_task`/`tokens_per_task` spreads.

**Information gain per stage (new — the core R2 metric).** For stage S, using the
cumulative ladder:

* `Δactual(S) = rate(arm with S) − rate(arm without S)`, computed **paired per task**
  (subtract the two arms' per-task means).
* `Δfalse(S)` the same on false-success.
* **Stage signal quality** (from the trajectory events, joined to the grader verdict):
  * IV: of the runs whose claim was blocked by `iv_red_on_final`, how many the grader
    passed (`IV false-block`); of the runs whose basis was `independent-test`, how many the
    grader failed (`IV false-approve`).
  * review: same for `basis=review` and `review_not_approved` blocks.
  * own test: same for `basis=own-test`.
* **Token and wall cost per stage** attributable to S.

**Cost:** tokens/task, model calls/task, and single-lane seconds/task (`--wall-clock`).

## 6. Decision rule (pre-registered, with error bars)

1. **Statistic.** Per arm pair (with-S vs without-S), build the paired per-task difference
   vector `d_t = rate_with(t) − rate_without(t)` over T tasks. Report the mean `d̄` and a
   **95% percentile bootstrap CI** (10 000 resamples of the T tasks, seed recorded). For
   binary claim/false-success counts also report a **McNemar exact** test on the paired
   2×2 (with-S only, without-S only).

2. **Stage carries positive information** iff the false-success CI's upper bound ≤ 0 AND
   (`Δactual` CI lower bound > 0 OR the false-success CI lies strictly below 0).

3. **Stage carries zero information** iff both CIs include 0 and there is no reduction in
   false success.

4. **Stage carries negative information** iff the `Δactual` CI upper bound < 0, OR the
   false-success CI lower bound > 0.

5. **R2 is supported** iff every stage in {own test, IV, review} is positive or
   zero-information with no false-success increase, AND at least one is positive. **R2 is
   refuted** iff any stage is negative.

6. **R3 is supported** iff, on the tail set, `rate(B1 or B2) − rate(B0)` has a 95% CI
   excluding 0 in favour of the tree, with no negative paired delta on the easy/mid
   control. Otherwise R3 is *inconclusive on this corpus* (the honest wording — the corpus
   is mostly single-artifact and the forensics §4.2 predicts a small effect).

7. A false-success rate above 0 on any arm invalidates a "positive information" reading of
   that arm for R2 (a stage that buys claims by lying is not carrying information).

**Interpretation guard.** Because the corpus is small and the model is stochastic, no arm
difference of one task is reported as a result without the CI; the historical ±3-task
run-to-run spread (STATUS §8e) is the reference noise floor.

## 7. Exact commands (after the missing tooling in §8 is added)

```sh
# 0. server health (never measure without it)
curl -fsS --max-time 3 http://127.0.0.1:8834/health     # must answer {"status":"ok"}

# 1. R2 cumulative ladder, full set, 3 seeds (additive)
uv run python bench/v2_measure.py --tasks all --n 3 --ablate none --verify raw  ...
# (per §2.1: A0 raw, A1 test, A2 full --no-review, A3 full --no-iv, A4 full;
#  the driver must accept the cumulative arm names, see §8 item 1)

# 2. R2 subtractive controls
uv run python bench/v2_measure.py --tasks all --n 3 \
   --ablate none,independent-test,review,own-test

# 3. R3 decomposition on the tail, 5 seeds, equal budget
uv run python bench/v2_tree_sweep.py --tasks T-31-...,T-33-...,T-28-...,T-14-...,T-26-...,T-21-...,T-22-... \
   --n 5 --calls 24 --deadline-hours 0.25 --how-explore 1
uv run python bench/v2_tree_sweep.py --tasks <same> --n 5 --calls 24 --how-explore 3

# 4. single-lane wall clock (one pass, no concurrency)
uv run python bench/v2_measure.py --tasks all --wall-clock --ablate none

# 5. analysis (new; joins trajectories to the grader verdict and bootstraps)
uv run python bench/v2_measure.py --analyze bench/runs/measure-<ts>
```

## 8. Exactly what tooling is missing to run it

Each item names the file + function and the concrete gap. Verified against the working
tree on 2026-10-12 (revision `72538ab`; `bench/v2_measure.py` untracked).

1. **No cumulative ladder arms.** `bench/v2_measure.py::ABLATIONS` (line 95) is
   single-drop only, and `ABLATIONS["own-test"]` is coupled to `raw`
   (`("own-test","independent-test","review")`), so A2 ("own test + IV, no review") and
   A3 ("own test + review, no IV") cannot be named. **Add** ladder entries (e.g. `plan`,
   `own-test-only`, `own-iv`, `own-review`, `full`) or a `STAGE_LADDER` table, and a
   `--ladder` selector.
2. **The driver is not green.** `uv run pytest tests/unit/test_v2_measure.py -q
   -p no:warnings` → **3 failures**:
   * `arm_summary` (line 150) does `per_task_means(rows, "tokens_total")` but the crash
     fallback record built in `_run_arm` (the `except Exception` branch) omits
     `tokens_total` → `KeyError: 'tokens_total'` on any crashed task
     (`test_main_runs_every_arm_and_seed_sequentially_and_merges_pi`,
     `test_wall_clock_defaults_to_a_single_lane`);
   * `arm_summary`'s `task_rate_sd` (line 172) computes `stdev([0.5, 1.0]) = 0.3536` but
     `test_arm_summary_reports_rate_and_task_spread_with_hand_computed_values` expects
     `0.5` — the tool and its own test disagree on the metric's definition.
   Fix both before any measurement: **`_run_arm` must set `tokens_total` (and the other
   measured fields) on the crash path**, and `task_rate_sd` must be defined once (test and
   code reconciled).
3. **No tree sweep / no decomposition aggregation.** `bench/v2_tree.py` (`main`, line
   544) runs ONE task, writes `run.json`, and has no `--verify` forwarding; there is no
   `results.jsonl` per task and no summary. **Add** `bench/v2_tree_sweep.py` (or extend
   `v2_measure` to call `bench.v2_tree.run_once` / `harness.tree_run.run_tree`) with the
   same seeds, crash recovery, token reader and `arm_summary`, and a `--verify` forwarded
   into each leaf spec so B-arms can be crossed with the R2 ladder.
4. **No per-stage information-gain analyzer.** `arm_summary` (`bench/v2_measure.py`) sees
   only `actual/claimed/false_success`. **Add** `stage_information(rows, run_root)` that,
   for each run, reads `trajectory.jsonl`, joins the `delivery` event's grader verdict to
   the `harness_event`s `independent_test_verdict`, `independent_test_inverted`,
   `review_verdict`, `review_not_approved`, `leaf_stop`, and computes per-stage
   precision / false-block / false-approve counts and the paired `Δactual`.
5. **No per-stage token attribution.** `read_token_usage` sums the whole trajectory.
   The IV and the own test BOTH emit `step_type="write_test"`, distinguished only by
   `fresh=True` (IV) vs `fresh=False` (own test) — verified in
   `v2sweep-20261011T070710Z/A-02-protein-translation-1/trajectory.jsonl` (`seq 1274`
   fresh=False, `seq 1299` fresh=True). **Add** `tokens_by_stage(trajectory)` keyed on
   `(step_type, fresh)` plus `debug_judge`/`leaf_review`/`implement_write`.
6. **No paired bootstrap / CI helper.** Only `mean`/`stdev` exist. **Add**
   `paired_diff_bootstrap(rows_a, rows_b, field)` and an exact McNemar helper; the
   decision rule in §6 depends on them.
7. **Budget and deadline are not equalised across arm families.** Leaf default
   `--calls 24` (`bench/v2_leaf.py:936`) vs tree default `--calls 48`
   (`bench/v2_tree.py:524`). **Add** an enforced common budget in the sweep wrappers
   (and record it), or the R3 comparison is not like-for-like.
8. **No revision pin in the output.** The measurement root's `summary.json` does not
   record the git SHA / server context size, so a reader cannot tell which revision a
   `measure-<ts>` directory belongs to. **Add** it to `main`'s summary write.
9. **No seed/temperature knob.** `harness/model.py::LlamaServerRunner.__init__` fixes
   `temperature=0.2` with no seed; repeats are the only stochastic control. Acceptable
   (and arguably correct) but a `--temperature`/`--seed` passthrough would let the
   run-to-run variance be separated from the arm effect, and is cheap to add.
10. **No concurrency guard for the single-lane metric.** `bench/v2_measure.py --wall-clock`
    is sequential *inside the driver*, but nothing stops a second lane (e.g. the pi
    baseline) running concurrently and contaminating seconds/task. The standing rule "one
    writer / one lane" is documented, not enforced.

## 9. Prioritized fix order for the measurement itself

1. Fix the 3 red `test_v2_measure.py` failures (item 2) — the instrument must be green
   before it is trusted.
2. Add the cumulative ladder arms (item 1) and the equal-budget pin (item 7).
3. Add `stage_information` + `tokens_by_stage` + bootstrap CI (items 4–6).
4. Add the tree sweep and `--verify` forwarding (item 3); run R3 last, because the
   forensics §4.2/§1a predict the smallest effect there.

Until items 1–3 land, R2 can only be measured by the existing subtractive arms
(`--ablate`) with the existing mean/sd — which is enough to reproduce the §1a direction
but not to give the decision rule in §6 its error bars. That gap is the honest reason R2
is "measured, not proven" today (STATUS limit 6).
