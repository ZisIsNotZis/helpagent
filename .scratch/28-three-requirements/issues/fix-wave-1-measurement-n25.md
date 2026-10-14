# Fix wave 1 — head-to-head extended to N=25 (both arms, revision 45ebb32, server :8834)

**Status: COMPLETE.** Run finished 2026-10-14T17:56+08:00 at N=25/arm (all eight new seeds
done; the rule never returned ACHIEVED or BEHIND, so no early stop). Every bash poll appended a
checkpoint line under *Status log*; the result, tables, commands and limitations are below.

**Objective.** Drive requirement 1 ("our actual ≥ pi within the error margin", M=3 tasks) to a
definitive pre-registered verdict on the frozen revision `45ebb32` by extending BOTH arms from
N=17 to N=25 (or until the rule resolves), reusing all valid existing seeds.

**Revision pin.** `git rev-parse HEAD` = `45ebb32f1be0977b9149057da3a80ee93ce22840`; code is
untouched (measurement only; no claim path added).
**Model server.** `http://127.0.0.1:8834`, llama.cpp, Spark-X2.5-4B-Q4_K_M, `-c 32768
--cache-type-k q8_0 --cache-type-v q8_0`, `n_slots=4`; health `{"status":"ok"}` before the run.
**Writes.** `/tmp/wave1/final/n25/` and this file only.

## Pre-registration (fixed before any seed ≥18 number was read)

* **Reuse.** Seeds 1..17 are the frozen N=17 data (verified intact: re-scoring them here
  reproduces the frozen result exactly — ours 423/680, pi 428/680, Δ=−0.294, CI
  [−3.471,+3.059], INCONCLUSIVE). Seeds 1..5 ours `our-n5/`, 6..9 ours `n9/our-extra/`,
  10..17 ours `n17/our-extra/` + pi `n9/pi-n9/` + `n17/pi-extra/`.
* **New seeds 18..25.** Both arms, 4 disjoint lanes each (`/tmp/wave1/final/our_lanes.txt`,
  `/tmp/wave1/final/pi_lanes.txt`), same drivers: ours `bench/v2_measure.py --n 1
  --server :8834`; pi `bench/pi_baseline.py --n 1 --base-url http://127.0.0.1:8834/v1
  --reasoning --thinking max` (per-run temp agent dir). Round mode = **segregated arms**
  (our 4 lanes, then pi 4 lanes) — the N=17 run's final validated mode, chosen before any
  seed ≥18 result was read because the 8-way-concurrent trial measured ~1.9 rows/min against
  ~2.0+ rows/min segregated on this host. A seed enters the analysis only when both arms
  have exactly 40 rows.
* **Decision rule (frozen, unchanged from the N=17 run).** `M = 3` tasks;
  `Δ = actual(ours) − actual(pi)` paired by task, per-task means over seeds;
  `Lo95(Δ) ≥ −M` → **ACHIEVED**, `Hi95(Δ) < −M` → **BEHIND**, else **INCONCLUSIVE**;
  strict **BEAT** iff `Lo95(Δ) > 0`. CI = task-clustered percentile bootstrap, seed
  `20261013`, B=20000. Stop early once ACHIEVED or BEHIND is established.
* **Arbiter.** The corpus's own withheld tests (`bench/external_score.external_score`), never a
  harness claim. `claimed` is not comparable across arms; only `actual` and false-success are.

## 1. Result — final head-to-head at N=25 (both arms, revision `45ebb32`, server :8834)

**Verdict: INCONCLUSIVE at the pre-registered rule (`M = 3`).** Both arms were extended to the
pre-registered maximum **N=25 seeds/task**; the rule never returned ACHIEVED or BEHIND at any N
from 18 to 25, so the driver ran every seed, and **N=25 is the definitive verdict for this run**.

| | ours (N=25) | pi (N=25, same server) |
| --- | --- | --- |
| **actual** | **616/1000 = 61.6%** | **624/1000 = 62.4%** |
| actual, per 40-task run | mean **24.640/40**, sd **1.221** | mean **24.960/40**, sd **2.150** |
| **claimed** (not comparable across arms) | 224/1000 | 647/1000 |
| **false success** | **22/1000 = 2.20%** | **61/1000 = 6.10%** |
| crashes / timeouts | 0 / 0 | 0 / 0 |

* Per-task mean actual over the same 40 tasks: ours **24.640**, pi **24.960**.
* **Δ = actual(ours) − actual(pi) = −0.320 tasks** (ours behind by 0.32 of 40 = 0.8 pp).
* **Task-clustered percentile-bootstrap 95% CI: [−3.520, +3.080]** (seed `20261013`, B=20000).

| condition | check | result |
| --- | --- | --- |
| `Lo95(Δ) ≥ −M` | −3.520 ≥ −3 ? | **no** (misses by **0.520** tasks) |
| `Hi95(Δ) < −M` | +3.080 < −3 ? | no |
| otherwise | | **INCONCLUSIVE** |
| strict **BEAT** (`Lo95 > 0`) | −3.520 > 0 ? | no |

The point estimate is a **near-tie** (ours 0.32 tasks behind), but the frozen 95%
non-inferiority test **does not establish parity within the 3-task margin** and **does not
establish inferiority** either. Requirement 1 ("our actual ≥ pi within the error margin")
therefore remains **unresolved by the pre-registered test at its maximum N**: neither the
ACHIEVED reading nor the BEHIND reading is supported.

**Why N=25 did not resolve it (structural).** The CI half-width is ~3.3 tasks and is
essentially flat over N=17→25 (full width 6.53 → 6.60). It is limited by **between-task
heterogeneity in the 40-task corpus**, not by seed noise: as seeds accumulate the per-task
means converge and the bootstrap interval settles near the task-level spread. More seeds on
this corpus therefore cannot close the 0.52-task gap to the −3 boundary; the rule would need
the point estimate to move to ≈ **+0.3 tasks** (or a different/larger task set) to return
ACHIEVED. This is a property of the test design, not of one lucky draw.

### Per-seed trajectory (recomputed checkpoint after each completed seed round)

| N | ours /40 | pi /40 | Δ (tasks) | Lo95 | Hi95 | rule |
| --- | --- | --- | --- | --- | --- | --- |
| 17 (frozen, reused) | 24.882 | 25.176 | −0.294 | −3.471 | +3.059 | INCONCLUSIVE |
| 18 | 24.778 | 25.444 | −0.667 | −3.889 | +2.667 | INCONCLUSIVE |
| 19 | 24.789 | 25.211 | −0.421 | −3.632 | +2.947 | INCONCLUSIVE |
| 20 | 24.750 | 25.200 | −0.450 | −3.650 | +2.950 | INCONCLUSIVE |
| 21 | 24.667 | 25.143 | −0.476 | −3.667 | +2.905 | INCONCLUSIVE |
| 22 | 24.727 | 24.955 | −0.227 | −3.364 | +3.136 | INCONCLUSIVE |
| 23 | 24.652 | 24.957 | −0.304 | −3.435 | +3.000 | INCONCLUSIVE |
| 24 | 24.625 | 24.958 | −0.333 | −3.500 | +3.042 | INCONCLUSIVE |
| **25 (final)** | **24.640** | **24.960** | **−0.320** | **−3.520** | **+3.080** | **INCONCLUSIVE** |

**Secondary no-lie limb** (`false_success(ours) ≤ false_success(pi)`): **satisfied** — 2.20% vs
6.10% run-level; task-clustered CI on the false-success difference **Δ_fs = −1.56 tasks,
[−3.16, −0.20]** (ours better; upper bound below the +1-task limit).

**`M` re-check (Phase-0 clause).** Run-to-run SD: ours 1.221, pi 2.150 → independent-arms
difference `s = √(1.221² + 2.150²) = 2.47` tasks, inside [1.0, 3.0] → **`M` stays 3**.

---

## 2. Per-task, per-band and arm tables (both arms, N=25)

### Per-task (ours N=25 · pi N=25)

| task | band | ours act | pi act | ours clm | pi clm | ours false | pi false |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01-word-count | anchors | 1/25 | 4/25 | 1/25 | 4/25 | 1/25 | 1/25 |
| A-02-protein-translation | anchors | 0/25 | 0/25 | 7/25 | 5/25 | 7/25 | 5/25 |
| A-03-book-store | anchors | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| A-04-connect | anchors | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| A-05-zebra-puzzle | anchors | 0/25 | 1/25 | 1/25 | 3/25 | 1/25 | 2/25 |
| T-01-ttl-seconds-ms | easy | 25/25 | 24/25 | 13/25 | 24/25 | 0/25 | 0/25 |
| T-02-off-by-one | easy | 25/25 | 24/25 | 5/25 | 22/25 | 0/25 | 0/25 |
| T-03-wrong-comparison | easy | 23/25 | 23/25 | 0/25 | 22/25 | 0/25 | 0/25 |
| T-04-missing-default | easy | 25/25 | 25/25 | 24/25 | 25/25 | 0/25 | 0/25 |
| T-05-mutable-default | easy | 10/25 | 17/25 | 0/25 | 15/25 | 0/25 | 0/25 |
| T-06-tz-naive-compare | easy | 25/25 | 24/25 | 1/25 | 25/25 | 0/25 | 1/25 |
| T-07-f-string-sql | easy | 23/25 | 25/25 | 0/25 | 24/25 | 0/25 | 0/25 |
| T-08-add-cache-invalidation | easy | 20/25 | 22/25 | 2/25 | 21/25 | 0/25 | 0/25 |
| T-09-add-rate-limit-hook | easy | 24/25 | 17/25 | 5/25 | 12/25 | 0/25 | 1/25 |
| T-10-port-dict-keys-view | easy | 25/25 | 25/25 | 0/25 | 25/25 | 0/25 | 0/25 |
| T-11-wrong-exception-type | mid1 | 25/25 | 25/25 | 0/25 | 23/25 | 0/25 | 0/25 |
| T-12-str-enum-compare | mid1 | 24/25 | 6/25 | 0/25 | 14/25 | 0/25 | 9/25 |
| T-13-add-retry-backoff | mid1 | 1/25 | 6/25 | 0/25 | 3/25 | 0/25 | 0/25 |
| T-14-add-export-sorting | mid1 | 18/25 | 22/25 | 9/25 | 25/25 | 0/25 | 3/25 |
| T-15-stale-registry-entry | mid1 | 24/25 | 23/25 | 24/25 | 22/25 | 0/25 | 0/25 |
| T-16-class-state-leak | mid1 | 17/25 | 25/25 | 9/25 | 24/25 | 0/25 | 0/25 |
| T-17-log-hour-format | mid1 | 22/25 | 20/25 | 3/25 | 15/25 | 0/25 | 0/25 |
| T-18-env-config-precedence | mid1 | 15/25 | 16/25 | 23/25 | 15/25 | 9/25 | 2/25 |
| T-19-slug-separator | mid1 | 25/25 | 25/25 | 6/25 | 24/25 | 0/25 | 0/25 |
| T-20-average-truncation | mid1 | 25/25 | 25/25 | 7/25 | 24/25 | 0/25 | 0/25 |
| T-21-swallowed-corruption | mid2 | 25/25 | 21/25 | 20/25 | 22/25 | 0/25 | 1/25 |
| T-22-case-sort-order | mid2 | 23/25 | 25/25 | 16/25 | 25/25 | 0/25 | 0/25 |
| T-23-stack-is-empty | mid2 | 25/25 | 25/25 | 10/25 | 25/25 | 0/25 | 0/25 |
| T-24-json-report-flag | mid2 | 2/25 | 10/25 | 0/25 | 15/25 | 0/25 | 5/25 |
| T-25-chunked-helper | mid2 | 25/25 | 20/25 | 17/25 | 23/25 | 0/25 | 4/25 |
| T-26-plan-dataclass-port | mid2 | 2/25 | 10/25 | 0/25 | 10/25 | 0/25 | 1/25 |
| T-27-snakecase-ingest | mid2 | 0/25 | 0/25 | 1/25 | 2/25 | 1/25 | 2/25 |
| T-28-plugin-registry-scaffold | mid2 | 7/25 | 10/25 | 0/25 | 23/25 | 0/25 | 14/25 |
| T-29-prerelease-version-parsing | mid2 | 19/25 | 12/25 | 9/25 | 12/25 | 0/25 | 0/25 |
| T-30-naive-datetime-compare | mid2 | 15/25 | 25/25 | 0/25 | 24/25 | 0/25 | 0/25 |
| T-31-parameter-threading | tail | 25/25 | 21/25 | 0/25 | 22/25 | 0/25 | 1/25 |
| T-32-sliding-window-limiter | tail | 2/25 | 0/25 | 2/25 | 5/25 | 2/25 | 5/25 |
| T-33-serializer-contract | tail | 23/25 | 1/25 | 8/25 | 1/25 | 0/25 | 1/25 |
| T-34-expression-tokenizer | tail | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 | 0/25 |
| T-35-interval-merge-invariants | tail | 1/25 | 20/25 | 1/25 | 22/25 | 1/25 | 3/25 |

### Per-band (each cell = mean per-task actual, N=25/task)

| band | ours | pi |
| --- | --- | --- |
| easy (10 tasks) | 9.00/10 | 9.04/10 |
| mid1 (10 tasks) | 7.84/10 | 7.72/10 |
| mid2 (10 tasks) | 5.72/10 | 6.32/10 |
| tail (5 tasks) | 2.04/5 | 1.68/5 |
| anchors (5 tasks) | 0.04/5 | 0.20/5 |
| **total (40 tasks)** | **24.640/40** | **24.960/40** |

### Arm summary

| metric | ours | pi |
| --- | --- | --- |
| actual | 616/1000 = 61.6% | 624/1000 = 62.4% |
| actual per 40-task run | mean 24.640, sd 1.221 | mean 24.960, sd 2.150 |
| claimed (not comparable) | 224/1000 | 647/1000 |
| false success | 22/1000 = 2.20% | 61/1000 = 6.10% |
| wall s/task (4-lane) | 99.8 | 125.4 |
| tokens/task (4-lane) | 18916 | unmeasured (pi carries no token counters) |
| crashes / timeouts | 0 / 0 | 0 / 0 |

Ours seed totals (1..25):
`26, 24, 25, 27, 23, 26, 24, 26, 25, 24, 24, 24, 27, 24, 24, 26, 24, 23, 25, 24, 23, 26, 23, 24, 25`

pi seed totals (1..25):
`24, 24, 23, 23, 24, 28, 23, 26, 27, 27, 27, 26, 25, 22, 27, 26, 26, 30, 21, 25, 24, 21, 25, 25, 25`



---

## 3. Cost — single lane, no concurrency, same 8-task subset, n=1

Fresh for this run (server otherwise idle; our arm one sequential `v2_measure --wall-clock`
process; pi arm one sequential `pi_baseline` process). Single-run, so indicative.

| task | ours wall_s | ours tokens | pi wall_s | ours/pi actual |
| --- | --- | --- | --- | --- |
| T-01-ttl-seconds-ms | 19.7 | 20317 | 70.3 | pass / pass |
| T-04-missing-default | 20.7 | 14108 | 17.6 | pass / pass |
| T-14-add-export-sorting | 23.0 | 18655 | 25.1 | fail / fail |
| T-24-json-report-flag | 21.6 | 13228 | 72.6 | fail / pass |
| T-28-plugin-registry-scaffold | 23.1 | 12134 | 64.8 | fail / fail |
| T-32-sliding-window-limiter | 53.5 | 25860 | 2.0 | fail / fail |
| T-34-expression-tokenizer | 34.5 | 21944 | 64.7 | fail / fail |
| A-01-word-count | 52.0 | 20047 | 62.9 | fail / fail |
| **mean** | **31.0** | **18287** | **47.5** (sd 27.9) | 3/8 · 3/8 |
| **total** | 248.1 s | 146293 | 380.0 s | |

* Our arm is ~1.5× cheaper in single-lane wall on this subset (**31.0 s/task** vs pi **47.5
  s/task**); the 4-lane contended means over all 40 tasks are **99.8 s/task** (ours) vs
  **125.4 s/task** (pi).
* **Our tokens/task: 18916 (4-lane, all 40 tasks)**; single-lane subset 18287. **pi
  tokens/task is unmeasured** — `pi_baseline.py` records no token counters (this is a driver
  limitation carried over from the N=9 run), so the token limb has no pi side.

---

## 4. Exact commands

Revision / precondition (unchanged code):
```sh
git -C /home/z/vibe/helpagent rev-parse HEAD        # 45ebb32f1be0977b9149057da3a80ee93ce22840
```

Server (was DOWN at start; started the documented docs/STATUS.md §7 32k server, stopped after):
```sh
llama-server \
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health                  # {"status":"ok"} before the run
```

Driver (both arms, seeds 18..25, 4 disjoint lanes/arm, segregated arms per round, resume-safe,
stops on ACHIEVED/BEHIND):
```sh
setsid nohup /tmp/wave1/final/n25/run_n25_seg.sh > /tmp/wave1/final/n25/driver-seg.out 2>&1 &
/tmp/wave1/final/n25/poll_n25.sh                        # one poll: checkpoint line appended
```

Per-lane commands the driver issues (lane task lists in `/tmp/wave1/final/{our,pi}_lanes.txt`):
```sh
uv run python bench/v2_measure.py --tasks "<lane tasks>" --n 1 \
  --server http://127.0.0.1:8834 --out /tmp/wave1/final/n25/our-extra/seed<k>/<lane>
uv run python bench/pi_baseline.py --tasks "<lane tasks>" --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
  --out /tmp/wave1/final/n25/pi-extra/seed<k>/<lane>
```

Analysis (frozen rule; reuses seeds 1..17 from the frozen roots):
```sh
python3 /tmp/wave1/final/n25/analyze_n25.py --nmax 25 \
  --out /tmp/wave1/final/n25/analysis-n25-final.json
```

Cost subset (both arms, single lane, server idle):
```sh
/tmp/wave1/final/n25/run_wallclock.sh
```

---

## 5. Limitations

1. **Achieved N = 25/arm** (40 tasks × 25 seeds each = **1000 rows/arm**; our + pi = 2000 rows).
   **0 crashes, 0 timeouts.** All eight new seeds 18..25 completed both arms at exactly 40 rows.
   The rule never resolved to ACHIEVED or BEHIND, so the run consumed the full pre-registered
   extension; the verdict below is therefore the maximum-N verdict for this design.
2. **The result is INCONCLUSIVE, not parity.** The CI still admits a deficit of up to 3.52 tasks
   (margin 3) and a lead of up to 3.08 tasks. The point estimate (ours −0.32 tasks) is a tie
   within noise, but "≥ pi within 3 tasks" is **not established at 95%**.
3. **The test is structurally unable to resolve at this corpus size.** CI width is ~6.6 tasks
   and flat over N=17→25; it is driven by between-task heterogeneity, so **more seeds will not
   close the 0.52-task gap**. Resolution needs Δ ≈ +0.3 tasks or a different/larger task set —
   a design decision above this measurement.
4. **pi tokens/task unmeasured** (`pi_baseline.py` has no token counters). Only our tokens/task
   is reported (18916 4-lane / 18287 single-lane).
5. **Cost subset is 8 tasks, single run, skewed easy-ish** (4-of-8 pass for each arm); it is
   indicative single-lane wall clock, not the full-40 mean.
6. **Round mode was segregated** (our 4 lanes, then pi 4 lanes) — the N=17 run's final mode,
   chosen before any seed ≥18 result was read because an 8-lane-concurrent trial measured
   ~1.9 rows/min vs ~2.0+ rows/min segregated on this host. The concurrent trial's partial
   seed-18 rows were discarded and re-run cleanly.
7. **`claimed` is not comparable across arms** (ours is gated by `claim_decision`; pi's is our
   regex read of its final message). Only `actual` and false-success are comparable.
8. **Server**: down at start; started the documented 32k server and **stopped it** after the
   run; port 8834 closed, no orphan lane processes, GPU back to baseline.
9. **Reused seeds 1..17** were verified intact before reuse (re-scoring reproduces the frozen
   N=17 result exactly). New seeds are all on `45ebb32` / :8834 with the same drivers.

---

## Status log

* 2026-10-14T13:19:19+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:19:18+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours2/40,pi2/40; driver_pid=1784975.
* 2026-10-14T13:22:14+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:22:13+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours4/40,pi4/40; driver_pid=1784975.
* 2026-10-14T13:25:28+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:25:27+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours7/40,pi8/40; driver_pid=1784975.
* 2026-10-14T13:29:17+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:29:15+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours8/40,pi0/40; driver_pid=1789515.
* 2026-10-14T13:32:16+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:32:14+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours18/40,pi0/40; driver_pid=1789515.
* 2026-10-14T13:35:15+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:35:13+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours25/40,pi0/40; driver_pid=1789515.
* 2026-10-14T13:38:13+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:38:12+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours36/40,pi0/40; driver_pid=1789515.
* 2026-10-14T13:41:12+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:41:11+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi0/40; driver_pid=1789515.
* 2026-10-14T13:44:11+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:44:09+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi6/40; driver_pid=1789515.
* 2026-10-14T13:47:10+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:47:09+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi16/40; driver_pid=1789515.
* 2026-10-14T13:50:09+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:50:07+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi25/40; driver_pid=1789515.
* 2026-10-14T13:53:08+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:53:06+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi31/40; driver_pid=1789515.
* 2026-10-14T13:56:07+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:56:05+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi35/40; driver_pid=1789515.
* 2026-10-14T13:59:06+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T13:59:04+08:00 — checkpoint N=17 (analyzer line above); in-flight: seed18:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T14:00:04+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:01:09+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:01:08+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours2/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:04:09+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:04:08+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours11/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:07:08+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:07:06+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours20/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:10:06+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:10:04+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours31/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:13:04+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:13:02+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours38/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:16:03+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:16:01+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi6/40; driver_pid=1789515.
* 2026-10-14T14:19:02+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:19:01+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi16/40; driver_pid=1789515.
* 2026-10-14T14:22:01+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:21:59+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi23/40; driver_pid=1789515.
* 2026-10-14T14:25:00+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:24:58+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi29/40; driver_pid=1789515.
* 2026-10-14T14:27:58+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:27:56+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi36/40; driver_pid=1789515.
* 2026-10-14T14:30:57+0800 — N=18/arm; ours 446/720 (24.778/40); pi 458/720 (25.444/40); Δ=-0.667; task-clustered 95% CI [-3.889, +2.667]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:30:56+08:00 — checkpoint N=18 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T14:31:07+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:33:31+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:33:30+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours4/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:36:32+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:36:30+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours15/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:39:30+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:39:29+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours22/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:42:29+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:42:27+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours32/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:45:27+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:45:25+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours34/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:48:26+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:48:24+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours39/40,pi0/40; driver_pid=1789515.
* 2026-10-14T14:51:25+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:51:23+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi6/40; driver_pid=1789515.
* 2026-10-14T14:54:25+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:54:24+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi13/40; driver_pid=1789515.
* 2026-10-14T14:57:24+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T14:57:23+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi22/40; driver_pid=1789515.
* 2026-10-14T15:00:23+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:00:21+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi31/40; driver_pid=1789515.
* 2026-10-14T15:03:21+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:03:19+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi35/40; driver_pid=1789515.
* 2026-10-14T15:06:20+0800 — N=19/arm; ours 471/760 (24.789/40); pi 479/760 (25.211/40); Δ=-0.421; task-clustered 95% CI [-3.632, +2.947]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:06:18+08:00 — checkpoint N=19 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T15:08:14+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:08:53+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:08:52+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40; driver_pid=1789515.
* 2026-10-14T15:11:55+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:11:54+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours8/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:14:54+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:14:52+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours20/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:17:53+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:17:51+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours31/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:20:51+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:20:50+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours36/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:23:50+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:23:49+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi1/40; driver_pid=1789515.
* 2026-10-14T15:26:50+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:26:48+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi7/40; driver_pid=1789515.
* 2026-10-14T15:29:48+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:29:47+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi16/40; driver_pid=1789515.
* 2026-10-14T15:32:47+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:32:45+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi24/40; driver_pid=1789515.
* 2026-10-14T15:35:45+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:35:43+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi32/40; driver_pid=1789515.
* 2026-10-14T15:38:43+0800 — N=20/arm; ours 495/800 (24.750/40); pi 504/800 (25.200/40); Δ=-0.450; task-clustered 95% CI [-3.650, +2.950]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:38:41+08:00 — checkpoint N=20 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T15:39:49+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:41:17+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:41:15+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours2/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:44:17+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:44:15+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours17/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:47:15+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:47:13+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours23/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:50:13+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:50:12+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours31/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:53:12+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:53:10+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi0/40; driver_pid=1789515.
* 2026-10-14T15:56:10+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:56:08+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi7/40; driver_pid=1789515.
* 2026-10-14T15:59:08+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T15:59:07+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi13/40; driver_pid=1789515.
* 2026-10-14T16:02:06+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:02:05+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi22/40; driver_pid=1789515.
* 2026-10-14T16:05:05+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:05:03+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi30/40; driver_pid=1789515.
* 2026-10-14T16:08:04+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:08:02+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi35/40; driver_pid=1789515.
* 2026-10-14T16:11:02+0800 — N=21/arm; ours 518/840 (24.667/40); pi 528/840 (25.143/40); Δ=-0.476; task-clustered 95% CI [-3.667, +2.905]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:11:00+08:00 — checkpoint N=21 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T16:12:11+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:13:36+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:13:34+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours2/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:16:35+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:16:33+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours12/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:19:33+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:19:32+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours21/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:22:32+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:22:30+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours30/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:25:30+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:25:29+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours38/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:28:28+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:28:27+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi3/40; driver_pid=1789515.
* 2026-10-14T16:31:27+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:31:25+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi9/40; driver_pid=1789515.
* 2026-10-14T16:34:25+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:34:23+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi22/40; driver_pid=1789515.
* 2026-10-14T16:37:24+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:37:22+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi29/40; driver_pid=1789515.
* 2026-10-14T16:40:22+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:40:20+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi34/40; driver_pid=1789515.
* 2026-10-14T16:43:20+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:43:19+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T16:45:54+0800 — N=22/arm; ours 544/880 (24.727/40); pi 549/880 (24.955/40); Δ=-0.227; task-clustered 95% CI [-3.364, +3.136]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:45:52+08:00 — checkpoint N=22 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T16:46:09+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:48:28+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:48:26+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours4/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:51:27+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:51:25+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours16/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:54:25+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:54:23+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours25/40,pi0/40; driver_pid=1789515.
* 2026-10-14T16:57:23+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T16:57:21+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours31/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:00:21+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:00:20+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours38/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:03:20+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:03:18+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:06:19+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:06:17+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi10/40; driver_pid=1789515.
* 2026-10-14T17:09:17+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:09:15+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi17/40; driver_pid=1789515.
* 2026-10-14T17:12:15+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:12:13+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi24/40; driver_pid=1789515.
* 2026-10-14T17:15:14+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:15:12+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi30/40; driver_pid=1789515.
* 2026-10-14T17:18:12+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:18:10+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi33/40; driver_pid=1789515.
* 2026-10-14T17:21:10+0800 — N=23/arm; ours 567/920 (24.652/40); pi 574/920 (24.957/40); Δ=-0.304; task-clustered 95% CI [-3.435, +3.000]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:21:08+08:00 — checkpoint N=23 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T17:22:42+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:23:44+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:23:42+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours1/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:26:43+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:26:41+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours10/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:29:41+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:29:39+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours19/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:32:40+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:32:38+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours26/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:35:38+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:35:37+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours37/40,pi0/40; driver_pid=1789515.
* 2026-10-14T17:38:37+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:38:35+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi2/40; driver_pid=1789515.
* 2026-10-14T17:41:36+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:41:34+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi7/40; driver_pid=1789515.
* 2026-10-14T17:44:34+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:44:32+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi18/40; driver_pid=1789515.
* 2026-10-14T17:47:32+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:47:30+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi24/40; driver_pid=1789515.
* 2026-10-14T17:50:31+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:50:29+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi31/40; driver_pid=1789515.
* 2026-10-14T17:53:29+0800 — N=24/arm; ours 591/960 (24.625/40); pi 599/960 (24.958/40); Δ=-0.333; task-clustered 95% CI [-3.500, +3.042]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:53:28+08:00 — checkpoint N=24 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi39/40; driver_pid=1789515.
* 2026-10-14T17:55:03+0800 — N=25/arm; ours 616/1000 (24.640/40); pi 624/1000 (24.960/40); Δ=-0.320; task-clustered 95% CI [-3.520, +3.080]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:56:03+0800 — N=25/arm; ours 616/1000 (24.640/40); pi 624/1000 (24.960/40); Δ=-0.320; task-clustered 95% CI [-3.520, +3.080]; rule=INCONCLUSIVE (M=3).
* 2026-10-14T17:56:01+08:00 — checkpoint N=25 (analyzer line above); in-flight: seed18:ours40/40,pi40/40 seed19:ours40/40,pi40/40 seed20:ours40/40,pi40/40 seed21:ours40/40,pi40/40 seed22:ours40/40,pi40/40 seed23:ours40/40,pi40/40 seed24:ours40/40,pi40/40 seed25:ours40/40,pi40/40; driver_pid=2077187.
