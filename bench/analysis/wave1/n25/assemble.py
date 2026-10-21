#!/usr/bin/env python3
"""Assemble the final N=25 report: keep the pre-registration + append-only status log,
insert the result tables, verdict, commands and limitations at the top."""
from pathlib import Path

F = Path("/home/z/vibe/helpagent/.scratch/28-three-requirements/issues/fix-wave-1-measurement-n25.md")
cur = F.read_text(encoding="utf-8")
pre, _, log = cur.partition("## Status log")
log = "## Status log" + log

# update the status banner
pre = pre.replace(
    "**Status: RUN IN PROGRESS.** This file is the authorized measurement output. Checkpoint "
    "lines\n(N, per-arm means, Δ, CI, rule) are appended under *Status log* after every poll, "
    "so a timeout\ncannot lose the result. The full tables, verdict, exact commands and "
    "limitations are written at\nthe top when the run stops.",
    "**Status: COMPLETE.** Run finished 2026-10-14T17:56+08:00 at N=25/arm (all eight new "
    "seeds\ndone; the rule never returned ACHIEVED or BEHIND, so no early stop). Every bash "
    "poll appended a\ncheckpoint line under *Status log*; the result, tables, commands and "
    "limitations are below.")

tables = Path("/tmp/wave1/final/n25/tables-n25.md").read_text(encoding="utf-8")

results = """## 1. Result — final head-to-head at N=25 (both arms, revision `45ebb32`, server :8834)

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

""" + tables + """

---

## 4. Cost — single lane, no concurrency, same 8-task subset, n=1

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

## 5. Exact commands

Revision / precondition (unchanged code):
```sh
git -C /home/z/vibe/helpagent rev-parse HEAD        # 45ebb32f1be0977b9149057da3a80ee93ce22840
```

Server (was DOWN at start; started the documented docs/STATUS.md §7 32k server, stopped after):
```sh
llama-server \\
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \\
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
uv run python bench/v2_measure.py --tasks "<lane tasks>" --n 1 \\
  --server http://127.0.0.1:8834 --out /tmp/wave1/final/n25/our-extra/seed<k>/<lane>
uv run python bench/pi_baseline.py --tasks "<lane tasks>" --n 1 \\
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \\
  --out /tmp/wave1/final/n25/pi-extra/seed<k>/<lane>
```

Analysis (frozen rule; reuses seeds 1..17 from the frozen roots):
```sh
python3 /tmp/wave1/final/n25/analyze_n25.py --nmax 25 \\
  --out /tmp/wave1/final/n25/analysis-n25-final.json
```

Cost subset (both arms, single lane, server idle):
```sh
/tmp/wave1/final/n25/run_wallclock.sh
```

---

## 6. Limitations

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

"""

F.write_text(pre + results + log, encoding="utf-8")
print("wrote", F, len(F.read_text(encoding='utf-8')), "bytes")
