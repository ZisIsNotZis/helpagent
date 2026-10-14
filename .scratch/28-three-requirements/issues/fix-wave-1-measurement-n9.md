# Fix wave 1 — head-to-head at the pre-registered N=9 (both arms, same server :8834)

**Revision pin.** `git rev-parse HEAD` = `45ebb32f1be0977b9149057da3a80ee93ce22840`
("Fix wave 1: verification/review information + deterministic delivery anchor, plus T-35 and
canary closures"); `git status --porcelain` shows only the untracked issue notes — **no code,
harness, bench or test file was changed and no claim path was added**.
**Model server.** `http://127.0.0.1:8834`, llama.cpp, Spark-X2.5-4B-Q4_K_M, `-c 32768
--cache-type-k q8_0 --cache-type-v q8_0`, `total_slots=4`; health `{"status":"ok"}` before and
after the run.
**Arbiter.** The corpus's own withheld tests (`bench/external_score.external_score`), never the
harness claim. **Writes:** `/tmp/wave1/final/n9/` and this file only.

**Why this run exists.** The prior report (`fix-wave-1-measurement.md`) measured our arm at
**N=5 on :8834** but took the **pi** column from the recorded reference `pi-maxed-20261006`,
which is **N=1/task on the now-down port :8833**; its own probe showed pi flips 5/12 tasks
between two identical runs. This run re-measures **both** arms at the pre-registered **N=9
seeds**, both on the same server :8834, and applies the frozen decision rule.

---

## 0. Pre-registration (fixed before any N=9 number was read)

* **Our arm.** 40-task corpus (T-01..T-35 `bench/corpus` + A-01..A-05 `bench/anchor`),
  `bench/v2_measure.py --ablate none` (`--verify full`), **N=9 seeds**, 4 disjoint lanes
  (`/tmp/wave1/final/our_lanes.txt`). The **prior N=5 was reused** — verified valid on this
  revision/server (40 tasks × 5 seeds, `run_idx` 1..5, **0 crashes**, run start 07:32:24 after
  HEAD's 07:30:08 commit, all four lane processes passed `--server http://127.0.0.1:8834`) —
  and **4 fresh seeds** ran into `/tmp/wave1/final/n9/our-extra/`. Merged seeds 1..5 (prior) +
  6..9 (fresh) = **9 seeds/task**.
* **pi arm.** `bench/pi_baseline.py --reasoning --thinking max` against **:8834**, **N=9
  seeds** over the same 40 tasks, 4 disjoint lanes (`/tmp/wave1/final/pi_lanes.txt`), run as
  **9 rounds `seed1..seed9`**; each round is 4 lane processes, each with its own `--out` root
  (hence its own temp pi agent dir `<root>/agent` and HOME). This is a full re-run, **not** the
  recorded reference.
* **Cost subset (one sequential lane, server otherwise idle, 8 tasks).** Our arm: the prior
  `--wall-clock` 8-task subset (valid on this revision/server, reused). pi arm: the same 8
  tasks, one sequential `pi_baseline` process on :8834.
* **Decision rule** (`impossibility-dossier-design.md` §2.6): margin **`M = 3` tasks**; with
  `Δ = actual(ours) − actual(pi)` paired by task and averaged over seeds,
  `Lo95(Δ) ≥ −M` → **ACHIEVED (parity within margin)**, `Hi95(Δ) < −M` → **BEHIND**, otherwise
  **INCONCLUSIVE**. **BEAT** needs `Lo95(Δ) > 0` at **N ≥ 17** (reported, not claimed, at N=9).
  CI = task-clustered percentile bootstrap, fixed seed `20261013`, 20000 resamples — the
  identical method/snippet as the N=5 report.
* **`M` re-check (Phase-0 clause).** `M` is held at 3 unless the measured 40-task difference SD
  `s` differs from 2.0 by >1 task. Measured here: our arm run-to-run SD 1.27, pi arm 1.87, so
  the independent-arms difference SD `s = √(1.27² + 1.87²) = 2.26` tasks → within [1.0, 3.0],
  **`M` stays 3**.

---

## 1. Head-to-head (N=9 both arms, same server, same 40 tasks, same grader)

| | ours (`45ebb32`, N=9) | pi (N=9, same server :8834) |
| --- | --- | --- |
| **actual** | **226/360 = 62.8%** | **222/360 = 61.7%** |
| actual, per 40-task run | mean **25.111/40**, sd **1.269** | mean **24.667/40**, sd **1.871** |
| seed totals (40-task) | 26, 24, 25, 27, 23, 26, 24, 26, 25 | 24, 24, 23, 23, 24, 28, 23, 26, 27 |
| **claimed** | 78/360 = 21.7% (the one claim gate) | 233/360 = 64.7% (regex read, **not** a claim gate) |
| **false success** | **4/360 = 1.11%** | **23/360 = 6.39%** |
| wall s/task (4-lane, contended) | 78.1 | 118.5 |
| tokens/task (4-lane) | 18967 | unmeasured (pi traces carry no token counters) |
| timeouts / crashes | 0 / 0 | 0 / 0 |

`claimed` is **not** comparable across arms (ours is gated by `claim_decision`; pi's is our
regex read of its final message). Only `actual` and the false-success counts are comparable,
per the pre-registration and STATUS §8c.

**The recorded reference was optimistic.** At N=9 on :8834 the maxed pi arm scores 24.67/40
(61.7%), against the recorded :8833 reference of 27/40 (67.5%). The prior report's −2-task gap
was therefore partly the reference's single lucky draw — exactly what its probe predicted.

### Paired difference and decision rule

* Per-task mean actual over the same 40 tasks: ours **25.111**, pi **24.667**.
* **Δ = +0.444 tasks** (ours **ahead** by 0.44 of 40 = 1.1 pp).
* **Task-clustered bootstrap 95% CI: [−3.111, +4.333] tasks.**
* **`M = 3` tasks.**

| condition | check | result |
| --- | --- | --- |
| `Lo95(Δ) ≥ −M` | −3.111 ≥ −3 ? | **no** (misses by 0.111 tasks) |
| `Hi95(Δ) < −M` | +4.333 < −3 ? | no |
| otherwise | | **INCONCLUSIVE** |

**Verdict: INCONCLUSIVE at the pre-registered rule (`M = 3`).** The point estimate is that our
pure-coding `actual` is **at or above pi** (Δ = +0.44 tasks), and the deficit side is *almost*
ruled out: `Lo95 = −3.111` sits just past the `−3` margin. The rule is therefore explicit —
parity-within-margin is **not established at 95%** (the CI still admits a deficit slightly
larger than 3 tasks), and inferiority is not established either. Strict **BEAT** is not met
(`Lo95 = −3.111 < 0`; also N=9 < the required 17).

**Answer to requirement 1 ("our actual ≥ pi within the error margin")**: the measured
difference is **+0.44 tasks in our favour**, so the *point estimate* says yes and the *no-lie*
limb holds, but the frozen 95% non-inferiority test returns **INCONCLUSIVE** — by 0.11 of a
task. Nothing here supports a "parity achieved" claim, nothing supports "inferior"; both remain
open, and the pre-registered way to resolve it is more seeds (N ≥ 17 for a win).

Secondary **no-lie** condition (`false_success(ours) ≤ false_success(pi)`): **satisfied** —
1.11% vs 6.39% run-level, and the task-clustered CI on the false-success difference is
`Δ_fs = −2.111` tasks, `[−3.444, −1.000]` (ours better; upper bound below the +1 task limit).

## 2. Per-band (each cell = mean per-task actual over the band, 9 seeds/task)

| band | ours | pi |
| --- | --- | --- |
| easy (T-01..T-10) | 9.22/10 | 9.22/10 |
| mid1 (T-11..T-20) | 8.00/10 | 7.67/10 |
| mid2 (T-21..T-30) | 5.89/10 | 6.11/10 |
| tail (T-31..T-35) | 2.00/5 | 1.56/5 |
| anchors (A-01..A-05) | 0.00/5 | 0.11/5 |
| **total** | **25.11/40** | **24.67/40** |

## 3. Per-task (ours N=9 · pi N=9)

| task | band | ours act | pi act | ours clm | pi clm | pi false |
| --- | --- | --- | --- | --- | --- | --- |
| A-01-word-count | anchors | 0/9 | 1/9 | 0/9 | 1/9 | 0/9 |
| A-02-protein-translation | anchors | 0/9 | 0/9 | 2/9 | 3/9 | 3/9 |
| A-03-book-store | anchors | 0/9 | 0/9 | 0/9 | 0/9 | 0/9 |
| A-04-connect | anchors | 0/9 | 0/9 | 0/9 | 0/9 | 0/9 |
| A-05-zebra-puzzle | anchors | 0/9 | 0/9 | 0/9 | 0/9 | 0/9 |
| T-01-ttl-seconds-ms | easy | 9/9 | 8/9 | 5/9 | 8/9 | 0/9 |
| T-02-off-by-one | easy | 9/9 | 8/9 | 3/9 | 8/9 | 0/9 |
| T-03-wrong-comparison | easy | 9/9 | 9/9 | 0/9 | 8/9 | 0/9 |
| T-04-missing-default | easy | 9/9 | 9/9 | 9/9 | 9/9 | 0/9 |
| T-05-mutable-default | easy | 4/9 | 6/9 | 0/9 | 5/9 | 0/9 |
| T-06-tz-naive-compare | easy | 9/9 | 9/9 | 0/9 | 9/9 | 0/9 |
| T-07-f-string-sql | easy | 8/9 | 9/9 | 0/9 | 8/9 | 0/9 |
| T-08-add-cache-invalidation | easy | 8/9 | 7/9 | 1/9 | 7/9 | 0/9 |
| T-09-add-rate-limit-hook | easy | 9/9 | 9/9 | 1/9 | 5/9 | 0/9 |
| T-10-port-dict-keys-view | easy | 9/9 | 9/9 | 0/9 | 9/9 | 0/9 |
| T-11-wrong-exception-type | mid1 | 9/9 | 9/9 | 0/9 | 9/9 | 0/9 |
| T-12-str-enum-compare | mid1 | 9/9 | 1/9 | 0/9 | 4/9 | 3/9 |
| T-13-add-retry-backoff | mid1 | 0/9 | 3/9 | 0/9 | 2/9 | 0/9 |
| T-14-add-export-sorting | mid1 | 6/9 | 8/9 | 2/9 | 9/9 | 1/9 |
| T-15-stale-registry-entry | mid1 | 9/9 | 9/9 | 9/9 | 9/9 | 0/9 |
| T-16-class-state-leak | mid1 | 7/9 | 9/9 | 4/9 | 9/9 | 0/9 |
| T-17-log-hour-format | mid1 | 7/9 | 6/9 | 0/9 | 5/9 | 0/9 |
| T-18-env-config-precedence | mid1 | 7/9 | 6/9 | 8/9 | 7/9 | 1/9 |
| T-19-slug-separator | mid1 | 9/9 | 9/9 | 1/9 | 9/9 | 0/9 |
| T-20-average-truncation | mid1 | 9/9 | 9/9 | 2/9 | 8/9 | 0/9 |
| T-21-swallowed-corruption | mid2 | 9/9 | 8/9 | 6/9 | 8/9 | 0/9 |
| T-22-case-sort-order | mid2 | 9/9 | 9/9 | 5/9 | 9/9 | 0/9 |
| T-23-stack-is-empty | mid2 | 9/9 | 9/9 | 3/9 | 9/9 | 0/9 |
| T-24-json-report-flag | mid2 | 1/9 | 3/9 | 0/9 | 5/9 | 2/9 |
| T-25-chunked-helper | mid2 | 9/9 | 8/9 | 7/9 | 8/9 | 0/9 |
| T-26-plan-dataclass-port | mid2 | 0/9 | 3/9 | 0/9 | 4/9 | 1/9 |
| T-27-snakecase-ingest | mid2 | 0/9 | 0/9 | 1/9 | 2/9 | 2/9 |
| T-28-plugin-registry-scaffold | mid2 | 4/9 | 4/9 | 0/9 | 8/9 | 4/9 |
| T-29-prerelease-version-parsing | mid2 | 8/9 | 2/9 | 5/9 | 2/9 | 0/9 |
| T-30-naive-datetime-compare | mid2 | 4/9 | 9/9 | 0/9 | 8/9 | 0/9 |
| T-31-parameter-threading | tail | 9/9 | 7/9 | 0/9 | 8/9 | 1/9 |
| T-32-sliding-window-limiter | tail | 1/9 | 0/9 | 0/9 | 2/9 | 2/9 |
| T-33-serializer-contract | tail | 8/9 | 0/9 | 4/9 | 1/9 | 1/9 |
| T-34-expression-tokenizer | tail | 0/9 | 0/9 | 0/9 | 0/9 | 0/9 |
| T-35-interval-merge-invariants | tail | 0/9 | 7/9 | 0/9 | 8/9 | 2/9 |

Tasks where ours leads: T-29 (+6/9), T-33 (+8/9), T-12 (+8/9), plus T-01/T-02/T-08/T-17/T-18/
T-21/T-25/T-31/T-32. Tasks where pi leads: T-30 (−5/9), T-35 (−7/9), T-05 (−2/9), T-13
(−3/9), T-16 (−2/9), T-26 (−3/9), T-14 (−2/9), T-24 (−2/9).

## 4. Cost (single lane, no concurrency, 8-task subset n=1)

| task | ours wall_s | ours tokens | pi wall_s | ours/pi actual |
| --- | --- | --- | --- | --- |
| T-01-ttl-seconds-ms | 11.4 | 6935 | 25.4 | pass / pass |
| T-04-missing-default | 15.0 | 10281 | 15.2 | pass / pass |
| T-14-add-export-sorting | 37.2 | 21631 | 21.4 | pass / pass |
| T-24-json-report-flag | 21.3 | 15997 | 166.4 | fail / fail |
| T-28-plugin-registry-scaffold | 26.8 | 19114 | 22.8 | pass / pass |
| T-32-sliding-window-limiter | 38.1 | 28108 | 71.0 | fail / fail |
| T-34-expression-tokenizer | 40.7 | 23287 | 70.5 | fail / fail |
| A-01-word-count | 27.1 | 14951 | 158.0 | fail / fail |
| **mean** | **27.2** (sd 10.9) | **17538** (sd 6951) | **68.8** (sd 61.7) | 4/8 · 4/8 |
| **total** | 217.6 s | 140304 | 550.7 s | |

* **Our arm is ~2.5× cheaper in wall and ~17.5k tokens/task; pi is ~69 s/task on this subset**
  (the reference README's 131 s/task is the all-40-task sequential mean, so the subsets differ
  and the comparison is indicative, not like-for-like).
* **pi tokens/task remain unmeasured** (its traces carry no token counters) — D1's token limb
  has no pi side.

## 5. Per-seed 40-task totals and 95% CI (n=9)

| arm | seed totals | mean | sd | 95% CI (t, df=8) |
| --- | --- | --- | --- | --- |
| ours | 26, 24, 25, 27, 23, 26, 24, 26, 25 | 25.111 | 1.269 | [24.135, 26.087] |
| pi | 24, 24, 23, 23, 24, 28, 23, 26, 27 | 24.667 | 1.871 | [23.229, 26.105] |

The two per-seed 95% intervals overlap heavily; pi's run-to-run spread (sd 1.87) is larger than
ours (sd 1.27).

## 6. Exact commands

```bash
# 0. state checks
git rev-parse HEAD                                   # 45ebb32f1be0977b9149057da3a80ee93ce22840
git status --porcelain                               # only untracked .scratch issue notes
curl -fsS --max-time 3 http://127.0.0.1:8834/health  # {"status":"ok"}
curl -fsS http://127.0.0.1:8834/props | ...          # total_slots=4, n_ctx=32768

# 1. pi smoke test on :8834
uv run python bench/pi_baseline.py --tasks T-04-missing-default --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
  --out /tmp/wave1/final/n9/pi-smoke

# 2. our arm: prior N=5 (reused) + 4 fresh seeds, 4 disjoint lanes
/tmp/wave1/final/n9/run_our_extra.sh
#   per lane: uv run python bench/v2_measure.py --tasks "<lane>" --n 4 \
#       --server http://127.0.0.1:8834 --out /tmp/wave1/final/n9/our-extra/<lane>
#   merge: prior lane run_idx 1..5 + extra lane run_idx+5 -> our-n5 + our-extra = seeds 1..9

# 3. pi arm: N=9, 9 rounds x 4 disjoint lanes (one seed per round)
/tmp/wave1/final/n9/run_pi_n9.sh
#   per seed k, per lane: uv run python bench/pi_baseline.py --tasks "<lane>" --n 1 \
#       --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
#       --out /tmp/wave1/final/n9/pi-n9/seed<k>/<lane>

# 4. pi single-lane cost subset (server idle)
/tmp/wave1/final/n9/run_pi_wallclock.sh

# 5. analysis: paired Delta + task-clustered bootstrap CI (seed 20261013, B=20000)
python3 /tmp/wave1/final/n9/analyze_n9.py    # -> /tmp/wave1/final/n9/analysis-n9.json
```

Raw run roots (all kept): `/tmp/wave1/final/our-n5/lane{1..4}/none/results.jsonl` (200 rows,
prior, reused), `/tmp/wave1/final/n9/our-extra/lane{1..4}/none/results.jsonl` (160 rows),
`/tmp/wave1/final/n9/pi-n9/seed{1..9}/{lane1..4}/results.jsonl` (360 rows),
`/tmp/wave1/final/our-wallclock/none/results.jsonl` (8 rows, prior, reused),
`/tmp/wave1/final/n9/pi-wallclock/results.jsonl` (8 rows).

## 7. Limitations (every one that applies)

1. **Verdict is boundary-limited.** `Lo95 = −3.111` misses `−M = −3` by **0.111 tasks**; the
   rule returns INCONCLUSIVE. A slightly different task-level draw could flip it either way;
   no tuning is applied. The point estimate (ours +0.44) and the no-lie limb are robust; the
   non-inferiority pass is not.
2. **The 4-lane `wall_s` columns are contended** (ours 78.1, pi 118.5 s/task) and must not be
   read as cost. Only §4's single-lane subset is honest wall clock, and its 8 tasks skew easy
   for pi (68.8 s/task here vs 131 s/task on the full 40-task reference), so it is indicative.
3. **pi tokens/task unmeasured** — its traces carry no token counters; the token limb has no pi
   side. Our tokens/task (4-lane) mean 18967.
4. **Cost subsets were not run in the same session-window** for the two arms (ours is the prior
   reuse on the identical revision/server, pi is fresh); the server was idle for each.
5. **Our arm reuses the prior N=5 rows.** They were verified valid on this revision/server
   (`45ebb32`, :8834, 0 crashes, `run_idx` 1..5), and the fresh 4 seeds (26, 24, 26, 25)
   agree with the prior 5 (26, 24, 25, 27, 23), so no drift is visible; a 100% fresh N=9 was
   not run for budget reasons, disclosed.
6. **`M` held at 3 by the Phase-0 clause** using the measured `s = 2.26` (within [1.0, 3.0]);
   no `M` tuning was performed after reading results.
7. **pi "claimed" is not a claim gate** (regex read); only actual and false-success counts are
   comparable across arms.
8. **A2 (improved-prompt pi) arm not run** (out of this task's scope), still unmeasured.
9. **Host shared-resource effects** (unrelated jobs) were not controlled; the server was the
   only model process during the run.

## 8. Status log

* 2026-10-13T09:14+08:00 — state checks pass (HEAD `45ebb32`, clean tree, :8834 healthy, `pi`
  on PATH, `bwrap` present); pi smoke T-04 on :8834 true/true, 12.8 s.
* 2026-10-13T09:14+08:00 — our-arm extra 4 seeds launched (4 lanes, n=4).
* 2026-10-13T10:15:11+08:00 — our-arm extra complete: 160/160 runs, 0 crashes (~61 min).
* 2026-10-13T10:17:18+08:00 — pi arm N=9 launched (9 rounds × 4 disjoint lanes).
* 2026-10-13T13:38:42+08:00 — pi arm complete: 360/360 runs, 0 timeouts/crashes; 9 rounds
  (per-round wall 24.8, 22.3, 18.3, 24.2, 24.8, 22.6, 23.0, 21.5, 20.0 min).
* 2026-10-13T13:40:26+08:00 — pi single-lane cost subset launched (server idle).
* 2026-10-13T13:49:42+08:00 — cost subset complete (8/8, 550.7 s); analysis + this report.

### Checkpoint log

Row counts were appended to this file after each poll (the raw 3-minute cadence is in the
driver logs `/tmp/wave1/final/n9/our-extra-driver.log` and `pi-driver.log`). Summary:
`our-extra` 17→160 over 09:21–10:15; `pi-n9` 5→360 over 10:20–13:38 (seed barriers at
10:42:05, 11:04:24, 11:22:41, 11:46:52, 12:11:40, 12:34:15, 12:57:16, 13:18:44, 13:38:42);
`pi-wallclock` 3→8 over 13:43–13:51.
