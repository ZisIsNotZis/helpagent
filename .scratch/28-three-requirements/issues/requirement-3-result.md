# Requirement 3 result — decomposition / step-splitting / multi-approach measurement

**Revision `45ebb32`** (`git rev-parse --short HEAD`), `git status --porcelain
--untracked-files=no` empty at start and at end. No code was modified; no claim path was
added. Outputs: `/tmp/wave1/final/r3/` (210 run records) and this file.

**Verdict: NEGATIVE.** At the pre-registered rule both tree arms are significantly *worse*
than the monolithic leaf on the decomposable comparison, significantly worse on the
forced-leaf overhead comparison, and are worse per unit of cost. The node-split mechanism
did fire (on 3 of 9 decomposable tasks in B1, 4 of 9 in B2), so the run is a valid
decomposition test — it is not an "un-fired mechanism" result.

---

## 1. What was run

Design followed as written: `.scratch/28-three-requirements/issues/requirement-3-design.md`
§5. Arms, task set, N, budget, server, analysis script, bootstrap seed, McNemar and
decision rule are exactly §5. Deviations are listed in §7; the only material one is that
wall-clock was bought with four identical 32k servers and 12 lanes instead of one lane,
because §5.7 estimates 15–20 h of serial work and the task budget is 6 h.

| arm | driver | what it is |
| --- | --- | --- |
| **B0 `leaf`** | `bench/v2_leaf.py --verify full` | today's monolithic leaf: one write unit, no planning, no children |
| **B1 `tree-greedy`** | `bench/v2_tree.py --how-explore 1` | `how_list` + top How + 3/3 forced-leaf guard + node-into-children |
| **B2 `tree-tournament`** | `bench/v2_tree.py --how-explore 3` | same tree, up to 3 parallel How candidates picked by `harness/how.py::pick` |

* Equal budget for every run: `--calls 48 --deadline-hours 1`.
* 14 tasks (9 decomposable, 5 forced-leaf) × 3 arms × **N=5** = **210 runs**, all
  completed, all paired by `(task, seed)`: 70 keys present in all three arms, every one of
  the 14 tasks with exactly 5 seeds in every arm.
* Sweep wall-clock `2026-10-14T11:12:43+08:00` → `2026-10-14T13:10:37+08:00` = **1 h 58 m**
  on 12 lanes. No lane exit code other than 0/1 (1 = honest non-`true-success` quadrant,
  required by §5.3); no traceback in any `run.log`; no run reached the 1 h deadline.

## 2. Pre-registration (fixed before any outcome data was read)

* **Primary statistic:** `d_t = rate_tree(t) − rate_leaf(t)` where `rate` is the mean of
  `run.json:actual` — the corpus's own withheld grader
  (`bench.external_score.external_score`) on a pristine copy, never the harness claim.
* 95 % percentile bootstrap CI over tasks (10 000 resamples, seed `20261013`); exact
  McNemar on discordant `(task, seed)` pairs; a separate bootstrap CI for the false-success
  delta.
* **Verdict rule.** positive iff decomposable CI lower bound > 0 **and** false-success CI
  upper bound ≤ 0 **and** the forced-leaf comparison is not significantly negative;
  negative iff decomposable CI upper bound < 0 **or** false-success CI lower bound > 0
  **or** forced-leaf CI upper bound < 0; otherwise zero/inconclusive (CI includes 0).
* **Mechanism gate.** `decomposition_fired_runs == 0` ⇒ report "decomposition never
  executed at these thresholds" and stop; an un-fired mechanism is an uninformative
  comparison, never evidence that decomposition helped.

## 3. Arms table

70 runs per arm (14 tasks × 5 seeds). `actual` = withheld grader; `claimed` =
`run.json:claimed` (an honest gate, not a regex — STATUS §8c).

| arm | actual | claimed | **false success** | mean calls/task | total calls | mean wall s/run (12-lane) | tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **B0 leaf** | **47/70 = 67.1 %** | 8/70 | **0** | 14.4 | 1009 | 175 | **20 856/run measured** (sd 7 978, range 3 719–47 451; `trajectory.jsonl` present in 70/70) |
| **B1 tree-greedy** | **14/70 = 20.0 %** | 18/70 | **4** | 31.6 | 2 214 | 408 | not metered per run (§9.2) |
| **B2 tree-tournament** | **15/70 = 21.4 %** | 18/70 | **3** | 35.2 | 2 465 | 498 | not metered per run (§9.2) |

Quadrant spread: leaf `{missed-success 39, honest-failure 23, true-success 8}`; B1
`{honest-failure 52, true-success 14, false-success 4}`; B2
`{honest-failure 52, true-success 15, false-success 3}`.

By group:

| group | B0 leaf | B1 greedy | B2 tournament |
| --- | --- | --- | --- |
| DECOMPOSABLE (9 tasks, 45 runs) | **29/45 = 64.4 %** | 9/45 = 20.0 % | 10/45 = 22.2 % |
| FORCED-LEAF (5 tasks, 25 runs) | **18/25 = 72.0 %** | 5/25 = 20.0 % | 5/25 = 20.0 % |

Cost ratios against B0: B1 **2.20× the calls, 2.33× the wall**; B2 **2.44× the calls,
2.85× the wall**. Every run that hit the 48-call cap is a tree run (B1 7, B2 17); the leaf
arm never exhausted its budget (maximum 28 calls).

## 4. Paired deltas with CI (the pre-registered primary statistic)

Output of the design's own §5.4 script, `/tmp/wave1/final/r3/analysis-r3.txt`.

### B1 (tree-greedy) vs B0 (leaf)

| comparison | mean d̄ | 95 % CI | tree-only fix | leaf-only fix | McNemar p | false-success d̄ (CI) |
| --- | --- | --- | --- | --- | --- | --- |
| **DECOMPOSABLE (9)** | **−0.444** | **[−0.733, −0.178]** | 0 | 20 | 0.000 | +0.067 ([+0.000, +0.156]) |
| FORCED-LEAF overhead (5) | **−0.520** | **[−0.920, −0.120]** | 1 | 14 | 0.001 | +0.040 ([+0.000, +0.120]) |

Per task (leaf → tree): T-31 1.00→0.00, T-33 1.00→0.00, T-12 1.00→0.00,
T-21 0.80→0.20, T-28 0.20→0.00, T-03 0.80→0.60, T-11 1.00→1.00, T-34 0.00→0.00,
T-32 0.00→0.00; T-02 1.00→0.00, T-06 1.00→0.00, T-20 1.00→0.40, T-14 0.60→0.60,
T-26 0.00→0.00. Not one task improved.

### B2 (tree-tournament) vs B0 (leaf)

| comparison | mean d̄ | 95 % CI | tree-only fix | leaf-only fix | McNemar p | false-success d̄ (CI) |
| --- | --- | --- | --- | --- | --- | --- |
| **DECOMPOSABLE (9)** | **−0.422** | **[−0.689, −0.178]** | 2 | 21 | 0.000 | +0.067 ([+0.000, +0.156]) |
| FORCED-LEAF overhead (5) | **−0.520** | **[−0.800, −0.240]** | 1 | 14 | 0.001 | +0.000 ([+0.000, +0.000]) |

Per task (leaf → tree): T-31 1.00→0.00, T-12 1.00→0.00, T-33 1.00→0.20,
T-21 0.80→0.40, T-03 0.80→0.40, T-28 0.20→0.00, T-11 1.00→1.00, T-34 0.00→0.00,
T-32 0.00→0.00; T-06 1.00→0.00, T-02 1.00→0.20, T-20 1.00→0.60, T-14 0.60→0.20,
T-26 0.00→0.00. Two tree-only singleton fixes ((`T-21`, seed 5) and (`T-03`, seed 5),
neither of them a decomposed run) against 21 leaf-only fixes.

## 5. Did the mechanism actually fire?

Read from `run.json` → `nodes[].candidates[].how_case` and `nodes[].allocation.forced`
(`/tmp/wave1/final/r3/supp-r3.txt`).

| arm | runs with `decomposed-How` | decomposable tasks on which it fired | full `how_case` census (all runs) | `allocation.forced` nodes |
| --- | --- | --- | --- | --- |
| B1 greedy | **3 / 70** | **3 / 9** (T-31 ×1, T-33 ×1, T-32 ×1) | `leaf-How` 137, `fallback-leaf-How` 12, `forced-leaf` 6, `decomposed-How` 3, `failed-How` 1 | 3 |
| B2 tournament | **9 / 70** | **4 / 9** (T-32 ×4, T-31 ×3, T-33 ×1, T-11 ×1) | `leaf-How` 142, `fallback-leaf-How` 22, `decomposed-How` 9, `forced-leaf` 3, `failed-How` 1 | 1 |

**Gate: PASSED** for both arms — §5.6 requires ≥1 `decomposed-How` run on ≥3 of the 9
decomposable tasks (B1: 3 tasks, B2: 4 tasks). The result is therefore a valid
decomposition comparison, not "decomposition never executed at these thresholds".

But the firing is thin and it must bound the reading:

* **On 6 of the 9 decomposable tasks in B1 and 5 of 9 in B2 the planner never emitted
  children at all** — those runs are pure planning overhead, and no decomposition effect
  could have been observed there. The comparison is informative only for T-31, T-32, T-33
  (B1) plus T-11 (B2).
* **Even on the tasks where it fired, the delta is ≤ 0.** Fired subset (mean actual over
  the 5 seeds): T-31 leaf 1.00 vs greedy 0.00 / tournament 0.00; T-33 leaf 1.00 vs
  greedy 0.00 / tournament 0.20; T-32 leaf 0.00 vs greedy 0.00 / tournament 0.00;
  T-11 leaf 1.00 vs tournament 1.00. The only singleton pairs where a tree passed and the
  leaf failed are (`T-21`, seed 5) and (`T-03`, seed 5) in B2 — both on tasks where that
  run did **not** decompose (`fired=False`); they are sampling variance on tasks the leaf
  otherwise wins (T-21 leaf 4/5, T-03 leaf 4/5), not decomposition wins. No task improved
  at the task level in either arm (B1 0 positive / 5 flat / 9 negative; B2 0 / 4 / 10).
* **The 3/3 forced-leaf guard is rarely the binding constraint.** On the five
  forced-leaf tasks the guard's `forced-leaf` path appeared in only 0–3 of 5 runs per task
  (T-14 3/5, T-26 2/5, T-02 1/5, T-20 0/5, T-06 0/5 in B1). In the remaining runs the
  planner returned an empty child list (`leaf-How`) or an unusable plan
  (`fallback-leaf-How`), so the node became a leaf without the guard acting. The 5 forced
  tasks were leaves either way; the guard's *fixed* effect is small on this corpus.

## 6. Pre-registered verdict

### B1 (tree-greedy) vs B0 (leaf) — **NEGATIVE**

* decomposable CI upper bound = **−0.178 < 0** → the "negative information" clause fires;
* forced-leaf CI upper bound = **−0.120 < 0** → the forced-leaf clause fires too;
* false-success CI lower bound = **+0.000**, not > 0, so that clause does not fire (the
  false-success *point* delta is still adverse: 4 vs 0 false successes);
* the "positive information" clause fails on the first of its three conditions.

### B2 (tree-tournament) vs B0 (leaf) — **NEGATIVE**

* decomposable CI upper bound = **−0.178 < 0**; forced-leaf CI upper bound = **−0.240 < 0**;
* false-success CI lower bound = **+0.000** (point delta +0.067: 3 vs 0 false successes).

**Correct R3 wording (design §6): "structural superiority (C4/R3) is refuted on this
corpus: the monolithic leaf matches or beats the tree at a fraction of the cost."** The
tree arms cost 2.2–2.4× the calls, 2.3–2.9× the wall, and ≥1.85× the tokens per run for
1/3 of the grader passes (and 3.7× the aggregate tokens for the same 14×5 task set). The prior measurement (ticket 20, `66e9708`, tree 1/6 at ~38 calls vs leaf
6/12 at ~7 calls) predicted exactly this and is now reproduced on the frozen revision with
N=5 and a paired design.

## 7. Deviations from the design text (recorded, with rationale)

1. **Four identical servers, 12 lanes (instead of one lane).** §5.7 costs the design at
   15–20 h serial; the task budget is 6 h. Ports 8834/8835/8836/8837 run the *same*
   documented command line (§8), each as its own process, so concurrent requests never
   share a KV pool, a batch or a sampling context and cannot perturb each other's
   numerics. 12 lanes, 3 per server. Every `(arm, task, seed)` job is otherwise identical
   to §5.3. Consequence: absolute wall times are not the single-lane numbers.
2. **Job order.** The 210 jobs are 5 waves of 42 (one wave = all 14 tasks × 3 arms,
   shuffled with `random.Random(20261013+wave)`); a lane takes every 12th job. The three
   arms therefore stay interleaved in time, so contention is shared across arms instead of
   loading one arm into an idle machine.
3. **Seed-1 runs** from the timing calibration (identical §5.3 settings) were reused as
   seed 1 rather than re-run: leaf T-03/T-11/T-12/T-21; tree-greedy T-31/T-33/T-03/T-11;
   tree-tournament T-31/T-33/T-03/T-11.
4. **Supplementary reads** (`supp.py`) were added on top of the design's §5.4 script for
   the mechanism breakdown; the primary statistics are the §5.4 script unmodified.

## 8. Exact commands

```sh
cd /home/z/vibe/helpagent
test "$(git rev-parse --short HEAD)" = "45ebb32" || echo FAIL
git status --porcelain --untracked-files=no          # empty
curl -fsS --max-time 3 http://127.0.0.1:8834/health  # FAILED -> server was down

# server (docs/STATUS.md §7), four identical processes, ports 8834-8837:
for p in 8834 8835 8836 8837; do
  nohup llama-server \
    -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
    --port $p --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0 \
    > /tmp/wave1/final/r3/logs/llama-$p.log 2>&1 &
done
curl -fsS http://127.0.0.1:8834/health   # {"status":"ok"}; /props: n_slots=4, n_ctx_slot=32768

# job queue (5 waves x 42 jobs, shuffled per wave)
python3 - <<'EOF'   # writes /tmp/wave1/final/r3/jobs.txt, 210 lines "arm task seed"
...  (DECOMP/FORCED lists from §5.2; arms leaf/tree-greedy/tree-tournament; seed in 1..5)
EOF

# 12 lanes; lane k -> port 8834+(k%4); each job is exactly §5.3's command line
for k in $(seq 0 11); do
  nohup bash /tmp/wave1/final/r3/lane.sh $k 12 $((8834 + (k % 4))) >/dev/null 2>&1 &
done
# lane.sh body == §5.3, per (arm, task, seed):
#   leaf            : uv run python bench/v2_leaf.py --task bench/corpus/$t --server $SRV \
#                       --calls 48 --deadline-hours 1 --verify full  --out $R3/leaf/$t-$i
#   tree-greedy     : uv run python bench/v2_tree.py --task bench/corpus/$t --server $SRV \
#                       --calls 48 --deadline-hours 1 --how-explore 1 --out $R3/tree-greedy/$t-$i
#   tree-tournament : uv run python bench/v2_tree.py --task bench/corpus/$t --server $SRV \
#                       --calls 48 --deadline-hours 1 --how-explore 3 --out $R3/tree-tournament/$t-$i

# analysis: the design's §5.4 heredoc verbatim (extracted to analyze.py, byte-identical)
R3=/tmp/wave1/final/r3 python3 /tmp/wave1/final/r3/analyze.py | tee /tmp/wave1/final/r3/analysis-r3.txt
python3 /tmp/wave1/final/r3/supp.py | tee /tmp/wave1/final/r3/supp-r3.txt

# shutdown (all lanes had already exited)
pkill -f 'llama-server.*883[4-7]'
```

## 9. Limitations (stated, not hidden)

1. **Wall-clock is contended.** 12 lanes on one GPU (≈99 % utilisation) mean the per-run
   wall figures (leaf 175 s, greedy 408 s, tournament 498 s) are throughput-contended, not
   single-lane latency. The arm-to-arm *ratios* are the meaningful part. A 4-concurrent
   calibration on one server measured leaf 67.7 s, greedy 202.0 s, tournament 257.2 s mean
   wall per run — the same ordering and a smaller absolute scale.
2. **Token cost is measured for B0 only.** `bench/v2_tree.py` installs no telemetry sink
   (design §7.2), so no tree run wrote `trajectory.jsonl` (0/70 in both tree arms, 70/70 in
   the leaf arm). A supplementary aggregate is available: the four servers logged
   **6 861 796 tokens over 6 034 requests**; the leaf arm's own meter reads
   **1 459 895 tokens / 1 009 calls** for its 70 runs, so the two tree arms together cost
   **≥ 5.40 M tokens over 140 runs (≈ 38 585/run, ≥ 1.85× leaf's 20 856/run)**. It cannot be split
   between B1 and B2, it includes a small number of transport retries (server requests
   6 034 vs client calls 5 688), and the subtraction is conservative because prompt-cache
   hits make the server's prompt count ≤ the client's. Calls remain the per-run cost unit.
3. **The mechanism fired on a minority of runs** (B1 3/70, B2 9/70). The pre-registered
   gate is met, but for most tasks the comparison measures planning overhead rather than
   decomposition. The negative verdict is therefore strong on "the tree stage does not pay
   for itself" and weaker on "requirement-level splitting can never help" — the latter is
   bounded to the 3–4 tasks where the planner did split.
4. **The forced-leaf thresholds were not swept.** `FORCED_LEAF_MAX_FILES/ACS` have no CLI
   or env override (design §7.3), so a threshold sweep — the only way to test T-14/T-26 —
   remains unrun. Their prediction could not be tested.
5. **Power.** Per the design's own §5.6, 9 decomposable tasks resolve roughly ±0.4 of a
   task-rate. The observed −0.44 sits at that edge; the direction is however consistent
   across both arms, both groups, the per-task bars (0 of 14 tasks positive in either arm:
   B1 5 flat / 9 negative, B2 4 flat / 10 negative) and the discordant-pair counts
   (tree-only 0 in B1 and 2 in B2, both on non-decomposed runs, vs 20/21 leaf-only fixes),
   so the sign is not in doubt.
6. **One inherited spec-level asymmetry**: the leaf root declares review angles
   `ac-correctness` + `contract-compat` and the tree root `end-to-end-behaviour` +
   `interface-alignment` (design §5.3). Any review-carried claim must be read with that in
   mind; the grader (`actual`) is arm-independent.
7. **Four servers instead of one.** Scheduling differs from §5.3 (each lane is one
   in-flight request; each server has 4 slots, so 3 lanes share each slot pool). Per-request
   numerics are unaffected (separate processes); per-run *latency* is (§9.1).
8. Nothing here is human acceptance and nothing here authorises a publication claim.

## 10. Evidence index

* Run records: `/tmp/wave1/final/r3/{leaf,tree-greedy,tree-tournament}/<task>-<seed>/run.json`
  (210), with `run.log` and, for leaf, `trajectory.jsonl`.
* Lane logs: `/tmp/wave1/final/r3/logs/lane0..11.log`; server logs
  `/tmp/wave1/final/r3/logs/llama-883{4,5,6,7}.log`.
* Analysis: `/tmp/wave1/final/r3/analysis-r3.txt` (design §5.4 script),
  `/tmp/wave1/final/r3/supp-r3.txt` + `supp.py` (mechanism/cost breakdown).
* Job queue: `/tmp/wave1/final/r3/jobs.txt`; runner `/tmp/wave1/final/r3/lane.sh`;
  start stamp `/tmp/wave1/final/r3/started_at.txt`.
* Design: `.scratch/28-three-requirements/issues/requirement-3-design.md` §5, §6, §7.
* Prior, for comparison: `.scratch/20-how-scaling/issues/20-how-scaling.md:120-146`;
  `bench/runs/evidence/v2tree-20260930T*/T-*/run.json` (revision `66e9708`).

## 11. Progress log (timestamps checked against the system clock)

* `2026-10-14T10:55:41+08:00` HEAD `45ebb32`, tracked tree clean, `8834` **down**
  (`curl` exit 7) → started the documented 32768-token server; `/props` = 4 slots,
  32768/slot.
* `10:56:57`–`11:05:11` timing calibration (4 concurrent per arm); results in §7.1/§3 of
  (numbers in §9.1) — this fixed the lane count, not the comparison.
* `11:12:43` 12 lanes launched over 210 jobs; started_at recorded.
* `11:28:40` 39/210 · `11:44` 58/210 (first mechanism read: greedy `decomposed-How` 0,
  tournament 3) · `11:58:54` 82/210 · `12:13:56` 114/210 · `12:35:00` 149/210 ·
  `12:59:02` 191/210 (6 lanes finished) · `13:08:04` 209/210 · `13:10:37` 210/210,
  12/12 lanes `ALL DONE`. GPU 99 % throughout; no timeouts.
* `13:10` analysis (design §5.4 script) and mechanism/cost read-out.
* `13:1x` all 4 `llama-server` processes stopped; `ps` shows no `llama-server`, no
  `v2_leaf.py`/`v2_tree.py`, no `lane.sh`; GPU back to 741 MiB. No orphan processes.
* Final re-check: HEAD `45ebb32`, `git status --porcelain --untracked-files=no` empty.
