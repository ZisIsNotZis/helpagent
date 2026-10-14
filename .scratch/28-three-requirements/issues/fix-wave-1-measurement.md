# Fix wave 1 — head-to-head measurement (frozen-revision decisive run)

**Revision pin.** `git log -1` = `45ebb32f1be0977b9149057da3a80ee93ce22840` ("Fix wave 1:
verification/review information + deterministic delivery anchor, plus T-35 and canary
closures"); `git status --porcelain` empty (clean tree) at start and at measurement.
**Server.** `http://127.0.0.1:8834`, llama.cpp, Spark-X2.5-4B-Q4_K_M, `-c 32768
--cache-type-k q8_0 --cache-type-v q8_0`, 4 slots; health `{"status":"ok"}` before the run.
**Arbiter.** The corpus's own withheld tests (`bench/external_score.external_score`), never
the harness claim. **Writes:** this file and `/tmp/wave1/final/` only; no harness, bench or
test code was changed and no claim path was added.

## 0. Pre-registration (fixed before any number below was read)

* **Our arm.** Full 40-task corpus (T-01..T-35 in `bench/corpus` + A-01..A-05 in
  `bench/anchor`), `bench/v2_measure.py --ablate none` (`--verify full`), **N=5 seeds**, split
  over **4 disjoint lanes** (one `v2_measure` process per lane; the server has exactly 4
  slots). Lane membership: `/tmp/wave1/final/our_lanes.txt`.
* **Single-lane wall-clock subset.** `--wall-clock`, one lane, no concurrency, 8 tasks
  spanning every band.
* **pi arm.** `bench/pi_baseline.py --reasoning --thinking max` (the maxed reference arm:
  thinking max + 32k window + 8192 output) against the same server. A full 40-task re-run is
  ~5230 s of model-serial work and does not fit the 2-hour budget, so pi's 40-task column is
  the recorded reference `bench/runs/evidence/pi-maxed-20261006` (N=1/task), and a
  **pre-registered 12-task probe** (`/tmp/wave1/final/pi_probe_lanes.txt`) was re-run twice on
  8834 as a same-server validity check and a first pi-variance measurement. Probe tasks,
  chosen before running: T-01, T-04, T-09 (ref pass), T-13 (ref fail), T-14 (ref pass),
  T-24 (ref fail), T-28, T-30 (ref pass), T-32, T-34 (ref fail), A-01, A-02 (ref fail) →
  reference outcome 6 pass / 6 fail.
* **Decision rule** (`impossibility-dossier-design.md` §2.6, adopted from
  `parity-forensics.md` §4): margin **`M = 3` tasks**; with `Δ = actual(ours) − actual(pi)`
  paired by task and averaged over seeds, `Lo95(Δ) ≥ −M` → **PARITY**,
  `Hi95(Δ) < −M` → **INFERIOR**, otherwise **INCONCLUSIVE**. CI = task-clustered bootstrap,
  fixed seed `20261013`, 20000 resamples.

---

## 1. Head-to-head (frozen revision, same model, same 40 tasks, same grader)

| | ours (`45ebb32`, N=5) | pi (reference `pi-maxed-20261006`, N=1/task) |
| --- | --- | --- |
| **actual** | **125/200 = 62.5%** | **27/40 = 67.5%** |
| actual, per 40-task run | mean **25.0/40**, sd **1.58** (seed totals 26, 24, 25, 27, 23) | 27/40 (single run; variance unmeasured) |
| **claimed** | 46/200 = 23.0% | 29/40 = 72.5% (regex read, not a claim gate) |
| **false success** | **4/200 = 2.0%** | 2/40 = 5.0% |
| **tokens/task** | mean **18740**, sd 6533, [6027..33587] (4-lane) | **unmeasured** (pi traces carry no token counters) |
| **wall s/task** | **75.5** sd 30.2 [22.3..148.5] — *4-lane, contended; not the honest cost* | 131 s/task sequential (reference README, all 40 tasks) |
| **wall s/task, single lane** | **27.2** sd 10.9 [11.4..40.7] (8-task subset, n=1) | 131 s/task sequential (reference) |
| turns/task | see per-task table (model calls 12.6 mean on the cost subset) | 8.9 turns/task (reference README) |

Our `claimed` is far below pi's because ours is the one `claim_decision` gate (a delivery is
claimed only when the graded evidence supports it); pi's "claimed" is a regex read of the final
assistant message with no gate (STATUS §8c). Only `actual` and the false-success counts are
comparable, per the pre-registration.

### Paired difference and decision rule

* Per-task mean actual over the same 40 tasks: ours **25.00**, pi **27.00**.
* **Δ = −2.00 tasks** (ours behind by 2 of 40 = 5.0 pp).
* **Task-clustered bootstrap 95% CI: [−4.80, +1.20] tasks.**
* **`M = 3` tasks.**

| condition | check | result |
| --- | --- | --- |
| `Lo95(Δ) ≥ −M` | −4.80 ≥ −3 ? | **no** |
| `Hi95(Δ) < −M` | +1.20 < −3 ? | **no** |
| otherwise | | **INCONCLUSIVE** |

**Verdict: INCONCLUSIVE at the pre-registered rule (margin `M = 3` tasks).** The recorded
−2-task gap is not distinguishable from zero (CI includes +1.20), and parity-within-margin is
**not** established at 95% (the CI reaches −4.80, past the −3 margin). The rule is written so
that neither "parity" nor "inferior" can be declared from this seed count; the answer to
"is our actual ≥ pi within the measured error margin?" is: **not resolvable at N=5 against a
N=1 pi arm** — it needs the pre-registered N ≥ 9 per arm (N ≥ 17 for "beats pi").

Secondary "no-lie" condition (`false_success(ours) ≤ false_success(pi)`): **satisfied** on the
counts, 2.0% vs 5.0%.

pi-only tasks (pi passed, our per-task rate < 1): T-05 (3/5), T-07 (4/5), T-08 (4/5),
T-14 (3/5), T-16 (4/5), T-17 (3/5), T-18 (4/5), T-28 (2/5), T-29 (4/5), T-30 (2/5).
our-only tasks (we passed at least once, pi failed its one recorded run): T-24 (1/5),
T-32 (1/5), T-33 (5/5).

## 2. Per-band

| band | ours runs | ours actual | ours claimed | ours false | pi actual (N=1/task) | pi claimed |
| --- | --- | --- | --- | --- | --- | --- |
| easy (T-01..T-10) | 50 | 46/50 | 10/50 | 0/50 | 10/10 | 10/10 |
| mid1 (T-11..T-20) | 50 | 39/50 | 13/50 | 1/50 | 9/10 | 9/10 |
| mid2 (T-21..T-30) | 50 | 29/50 | 19/50 | 1/50 | 7/10 | 7/10 |
| tail (T-31..T-35) | 25 | 11/25 | 2/25 | 0/25 | 1/5 | 2/5 |
| anchors (A-01..A-05) | 25 | 0/25 | 2/25 | 2/25 | 0/5 | 1/5 |
| **total** | 200 | **125/200** | 46/200 | 4/200 | **27/40** | 29/40 |

Lane totals: lane1 28/50, lane2 35/45, lane3 32/50, lane4 30/55 (lane wall times 4165.9 s,
3425.6 s, 4056.2 s, 3553.2 s; all four lanes started 07:32:24 and the arm finished ~08:45).

## 3. Per-task (ours N=5 · pi reference N=1)

| task | band | ours actual | ours claimed | ours false | ours wall_s (4-lane) | ours tokens | pi actual | pi claimed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A-01-word-count | anchors | 0/5 | 0/5 | 0/5 | 104 | 18030 | 0/1 | 0/1 |
| A-02-protein-translation | anchors | 0/5 | 2/5 | 2/5 | 89 | 22017 | 0/1 | 1/1 |
| A-03-book-store | anchors | 0/5 | 0/5 | 0/5 | 86 | 33587 | 0/1 | 0/1 |
| A-04-connect | anchors | 0/5 | 0/5 | 0/5 | 106 | 22368 | 0/1 | 0/1 |
| A-05-zebra-puzzle | anchors | 0/5 | 0/5 | 0/5 | 120 | 31077 | 0/1 | 0/1 |
| T-01-ttl-seconds-ms | easy | 5/5 | 2/5 | 0/5 | 43 | 15858 | 1/1 | 1/1 |
| T-02-off-by-one | easy | 5/5 | 3/5 | 0/5 | 72 | 17628 | 1/1 | 1/1 |
| T-03-wrong-comparison | easy | 5/5 | 0/5 | 0/5 | 126 | 27253 | 1/1 | 1/1 |
| T-04-missing-default | easy | 5/5 | 5/5 | 0/5 | 52 | 15943 | 1/1 | 1/1 |
| T-05-mutable-default | easy | 3/5 | 0/5 | 0/5 | 83 | 20235 | 1/1 | 1/1 |
| T-06-tz-naive-compare | easy | 5/5 | 0/5 | 0/5 | 103 | 24407 | 1/1 | 1/1 |
| T-07-f-string-sql | easy | 4/5 | 0/5 | 0/5 | 96 | 24048 | 1/1 | 1/1 |
| T-08-add-cache-invalidation | easy | 4/5 | 0/5 | 0/5 | 104 | 29554 | 1/1 | 1/1 |
| T-09-add-rate-limit-hook | easy | 5/5 | 0/5 | 0/5 | 100 | 20391 | 1/1 | 1/1 |
| T-10-port-dict-keys-view | easy | 5/5 | 0/5 | 0/5 | 76 | 20674 | 1/1 | 1/1 |
| T-11-wrong-exception-type | mid1 | 5/5 | 0/5 | 0/5 | 125 | 29998 | 1/1 | 1/1 |
| T-12-str-enum-compare | mid1 | 5/5 | 0/5 | 0/5 | 82 | 19845 | 1/1 | 1/1 |
| T-13-add-retry-backoff | mid1 | 0/5 | 0/5 | 0/5 | 91 | 23658 | 0/1 | 0/1 |
| T-14-add-export-sorting | mid1 | 3/5 | 0/5 | 0/5 | 85 | 21847 | 1/1 | 1/1 |
| T-15-stale-registry-entry | mid1 | 5/5 | 5/5 | 0/5 | 24 | 6896 | 1/1 | 1/1 |
| T-16-class-state-leak | mid1 | 4/5 | 2/5 | 0/5 | 50 | 15172 | 1/1 | 1/1 |
| T-17-log-hour-format | mid1 | 3/5 | 0/5 | 0/5 | 63 | 16187 | 1/1 | 1/1 |
| T-18-env-config-precedence | mid1 | 4/5 | 5/5 | 1/5 | 35 | 9452 | 1/1 | 1/1 |
| T-19-slug-separator | mid1 | 5/5 | 0/5 | 0/5 | 36 | 12202 | 1/1 | 1/1 |
| T-20-average-truncation | mid1 | 5/5 | 1/5 | 0/5 | 40 | 11530 | 1/1 | 1/1 |
| T-21-swallowed-corruption | mid2 | 5/5 | 3/5 | 0/5 | 39 | 9568 | 1/1 | 1/1 |
| T-22-case-sort-order | mid2 | 5/5 | 4/5 | 0/5 | 22 | 6027 | 1/1 | 1/1 |
| T-23-stack-is-empty | mid2 | 5/5 | 2/5 | 0/5 | 39 | 10770 | 1/1 | 1/1 |
| T-24-json-report-flag | mid2 | 1/5 | 0/5 | 0/5 | 53 | 13556 | 0/1 | 0/1 |
| T-25-chunked-helper | mid2 | 5/5 | 5/5 | 0/5 | 58 | 12261 | 1/1 | 1/1 |
| T-26-plan-dataclass-port | mid2 | 0/5 | 0/5 | 0/5 | 68 | 16515 | 0/1 | 0/1 |
| T-27-snakecase-ingest | mid2 | 0/5 | 1/5 | 1/5 | 77 | 16732 | 0/1 | 0/1 |
| T-28-plugin-registry-scaffold | mid2 | 2/5 | 0/5 | 0/5 | 70 | 17310 | 1/1 | 1/1 |
| T-29-prerelease-version-parsing | mid2 | 4/5 | 4/5 | 0/5 | 64 | 15254 | 1/1 | 1/1 |
| T-30-naive-datetime-compare | mid2 | 2/5 | 0/5 | 0/5 | 89 | 21397 | 1/1 | 1/1 |
| T-31-parameter-threading | tail | 5/5 | 0/5 | 0/5 | 57 | 14765 | 1/1 | 1/1 |
| T-32-sliding-window-limiter | tail | 1/5 | 0/5 | 0/5 | 58 | 20686 | 0/1 | 0/1 |
| T-33-serializer-contract | tail | 5/5 | 2/5 | 0/5 | 80 | 17200 | 0/1 | 0/1 |
| T-34-expression-tokenizer | tail | 0/5 | 0/5 | 0/5 | 149 | 25722 | 0/1 | 0/1 |
| T-35-interval-merge-invariants | tail | 0/5 | 0/5 | 0/5 | 107 | 21963 | 0/1 | 1/1 |

### Single-lane wall-clock subset (one lane, no concurrency, n=1, 8 tasks, 220.9 s total)

| task | wall_s | tokens | model calls | actual |
| --- | --- | --- | --- | --- |
| T-01-ttl-seconds-ms | 11.4 | 6935 | 6 | pass |
| T-04-missing-default | 15.0 | 10281 | 8 | pass |
| T-14-add-export-sorting | 37.2 | 21631 | 14 | pass |
| T-24-json-report-flag | 21.3 | 15997 | 12 | fail |
| T-28-plugin-registry-scaffold | 26.8 | 19114 | 16 | pass |
| T-32-sliding-window-limiter | 38.1 | 28108 | 24 | fail |
| T-34-expression-tokenizer | 40.7 | 23287 | 14 | fail |
| A-01-word-count | 27.1 | 14951 | 7 | fail |
| **mean** | **27.2** (sd 10.9) | **17538** (sd 6951) | 12.6 | 4/8 |

Our honest single-lane cost is ~27 s/task and ~17.5k tokens/task on this subset; pi's recorded
cost is 131 s/task sequential over all 40 tasks. The subsets differ, so the cost limb is
indicative, not a like-for-like 40-task total.

## 4. Exact commands

```bash
# 0. state checks
git log -1 --format='%H %s'        # 45ebb32f1be0977b9149057da3a80ee93ce22840
git status --porcelain             # empty
curl -fsS --max-time 3 http://127.0.0.1:8834/health   # {"status":"ok"}

# 1. our arm, N=5, 4 disjoint lanes (one v2_measure process per lane, the server's 4 slots)
/tmp/wave1/final/run_our_arm.sh our-n5 5
#   -> for each lane in /tmp/wave1/final/our_lanes.txt:
#   uv run python bench/v2_measure.py --tasks "<lane tasks>" --n 5 \
#       --server http://127.0.0.1:8834 --out /tmp/wave1/final/our-n5/<lane>

# 2. single-lane wall-clock subset (no concurrency)
uv run python bench/v2_measure.py \
  --tasks T-01-ttl-seconds-ms,T-04-missing-default,T-14-add-export-sorting,T-24-json-report-flag,T-28-plugin-registry-scaffold,T-32-sliding-window-limiter,T-34-expression-tokenizer,A-01-word-count \
  --wall-clock --server http://127.0.0.1:8834 --out /tmp/wave1/final/our-wallclock

# 3. merge the 4 lanes (no run is dropped) and dedupe the pi reference bands
cat /tmp/wave1/final/our-n5/lane*/none/results.jsonl > /tmp/wave1/final/our-n5/merged-results.jsonl
#   pi reference: bench/runs/evidence/pi-maxed-20261006/{easy,mid1,mid2,tail,anchors}/results.jsonl,
#   later band wins -> /tmp/wave1/final/pi-reference.jsonl (same rule as load_pi_reference)

# 4. pi arm: smoke test, then two probe rounds (each N=1, 4 lanes)
uv run python bench/pi_baseline.py --tasks T-04-missing-default --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max --out /tmp/wave1/final/pi-smoke
#   for each lane in /tmp/wave1/final/pi_probe_lanes.txt, once into pi-probe and once into pi-probe-r2:
uv run python bench/pi_baseline.py --tasks "<lane tasks>" --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max \
  --out /tmp/wave1/final/pi-probe/<lane>          # (r2: /tmp/wave1/final/pi-probe-r2/<lane>)

# 5. analysis: paired Delta + task-clustered bootstrap CI
python3 /tmp/wave1/final/analyze.py \
  --ours /tmp/wave1/final/our-n5/merged-results.jsonl \
  --pi   /tmp/wave1/final/pi-reference.jsonl \
  --pi-label "pi-reference (N=1)" --out /tmp/wave1/final/analysis-vs-reference.json
```

Raw run roots (all kept): `/tmp/wave1/final/our-n5/lane{1..4}/none/results.jsonl` (200 rows),
`/tmp/wave1/final/our-wallclock/none/results.jsonl` (8 rows),
`/tmp/wave1/final/pi-smoke/results.jsonl`, `/tmp/wave1/final/pi-probe{-r2}/lane{1..4}/results.jsonl`.

The Δ and its CI are reproducible from the two jsonl files alone (task-clustered percentile
bootstrap; this exact snippet was re-run independently and returns Δ −2.000, Lo95 −4.800,
Hi95 +1.200):

```python
import json, random
ours = [json.loads(l) for l in open('merged-results.jsonl') if l.strip()]
pi   = {json.loads(l)['task']: json.loads(l) for l in open('pi-reference.jsonl') if l.strip()}
g = {}
for r in ours: g.setdefault(r['task'], []).append(1.0 if r['actual'] else 0.0)
ot = {t: sum(v)/len(v) for t, v in g.items()}
tasks = sorted(ot)
diffs = [ot[t] - (1.0 if pi[t]['actual'] else 0.0) for t in tasks]
rng = random.Random(20261013); B = 20000; n = len(tasks)
bs = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(B))
print(sum(diffs), bs[int(.025*B)], bs[int(.975*B)-1])   # -2.0 -4.8 1.2
```

Our per-seed 40-task totals `[26, 24, 25, 27, 23]` give an **empirically measured 40-task
run-to-run SD of 1.58 tasks**, close to the dossier's pre-registered ≈2.0 (`parity-forensics.md`
§4). Under the dossier's §2.6 Phase-0 rule (`M` stays 3 unless `s` differs from 2.0 by more
than 1 task) this measurement therefore also **leaves `M = 3`**, and it is recorded here.

## 5. pi probe on the frozen revision (same server, 12 tasks × 2 seeds)

Re-run of the maxed pi arm on 8834, same model/server config, same blind staging and grader:

| task | ref actual | probe seed 1 | probe seed 2 | probe claimed s1/s2 |
| --- | --- | --- | --- | --- |
| T-01-ttl-seconds-ms | 1/1 | 1/1 | 1/1 | 1/1 / 1/1 |
| T-04-missing-default | 1/1 | 1/1 | 1/1 | 1/1 / 1/1 |
| T-09-add-rate-limit-hook | 1/1 | 1/1 | 0/1 | 0/1 / 0/1 |
| T-13-add-retry-backoff | 0/1 | **1/1** | 1/1 | 1/1 / 1/1 |
| T-14-add-export-sorting | 1/1 | 1/1 | 1/1 | 1/1 / 1/1 |
| T-24-json-report-flag | 0/1 | **1/1** | 0/1 | 1/1 / 1/1 |
| T-28-plugin-registry-scaffold | 1/1 | 1/1 | 0/1 | 1/1 / 1/1 |
| T-30-naive-datetime-compare | 1/1 | 1/1 | 0/1 | 1/1 / 1/1 |
| T-32-sliding-window-limiter | 0/1 | 0/1 | 0/1 | 1/1 / 0/1 |
| T-34-expression-tokenizer | 0/1 | 0/1 | 0/1 | 0/1 / 0/1 |
| A-01-word-count | 0/1 | **1/1** | 0/1 | 1/1 / 0/1 |
| A-02-protein-translation | 0/1 | 0/1 | 0/1 | 0/1 / 1/1 |
| **pass count** | **6/12** | **9/12** | **4/12** | |

* **pi flips 5/12 tasks between its own two seeds** and 3/12 against the recorded reference.
  Across the two probe seeds pi scored 9/12 and 4/12 (mean 6.5/12) against the reference's
  6/12 — a ±2.5-task swing on 12 tasks from the same configuration, server and grader.
* Probe totals over 24 runs: claimed 17/24, actual **13/24 (54.2%)**, false success **5/24
  (20.8%)**, timeouts 0. (pi's claim column is a regex read, so compare only the counts.)
* Probe cost: wall/task mean 96.3 s (sd 52.0) for seed 1 and 117.7 s (sd 50.4) for seed 2 under
  4-lane concurrency; turns/task 9.1 (reference 8.9), consistent with the reference's shape.

**Consequence for the verdict:** the recorded pi column (27/40) is a **single draw from a
process that demonstrably flips ~40% of its tasks between identical runs**. The −2-task point
estimate and its CI are therefore conditional on that draw, and the honest reading of the
campaign is exactly the rule's: **INCONCLUSIVE**. Nothing here supports a "parity achieved"
or "inferior" claim; both remain open.

## 6. Limitations (every one that applies)

1. **pi N=1 in the 40-task comparison.** The pi column is the recorded reference, one run per
   task; the probe shows pi's run-to-run flips are large (5/12 between two seeds), so the
   ±CI above **understates** two-arm uncertainty. The 40-task pi arm was **not** re-run at the
   pre-registered N ≥ 9.
2. **Our arm N=5 < the pre-registered N ≥ 9.** N=5 cannot support a parity-within-margin
   statement (§2.3/§2.6); N ≥ 17 would be needed for "beats pi". The verdict is INCONCLUSIVE
   by construction. Budget arithmetic, disclosed in full: the N=5 arm consumed 73 of the 120
   minutes (200 runs at 4 lanes), the cost subset 5 min and the two pi probe rounds ~19 min,
   leaving ~15 minutes — enough for one more seed (N=6) but not for the pre-registered N ≥ 9
   (≈3× the N=5 arm). One more seed moves the verdict not at all (even N=9 was pre-registered
   as inconclusive at this Δ), so the remaining time was spent on the pi-variance evidence
   and this report. The seed count is disclosed as **N=5, below the pre-registered
   threshold**; no seed-count claim is made.
3. **Concurrency.** Our 40-task arm ran on 4 lanes (the server's 4 slots); the per-task
   `wall_s` column in §3 is contended (mean 75.5 s vs 27.2 s single-lane) and **must not** be
   read as cost. Only the §3 single-lane subset is the honest wall clock. Verdict metrics
   (`actual`/`claimed`/`false`) are per-run outcomes, but a single-lane schedule was not used
   for the accuracy arm.
4. **Cost subsets differ.** Our single-lane cost covers 8 tasks; pi's 131 s/task is the
   40-task sequential mean from the reference README, so the cost limb is indicative.
5. **pi tokens/task unmeasured.** pi's recorded traces carry no prompt/completion counters
   (`turns`, `tool_calls`, `wall_s`, … no token fields), so there is no pi side to the token
   comparison.
6. **pi reference provenance.** The reference ran against port **8833** (now down); this
   campaign's pi probe and our arm ran against **8834**. Same GGUF/Q4_K_M and the README's
   `-c 32768` cache config; the probe (§5) is the reproduction check and it **partially
   fails** — 3/12 reference tasks flipped — so the reference is not a fixed number even on the
   same model.
7. **pi "claimed" is not a claim gate** (regex read of the final message, STATUS §8c); the
   claimed column is not comparable to ours. Only actual and false-success counts are.
8. **A2 (improved-prompt pi) arm not run.** It is recorded as GPU-blocked by an unrelated job.
   During this run **no unrelated GPU job was present** (nvidia-smi 4.6/24.6 GB, ~31% util; the
   only model process is the 8834 llama-server), so that blocker is not reproduced here; A2
   remains **unmeasured** and is not faked.
9. **Host CPU contention.** An unrelated `pytest` suite from another session ran on the host
   during part of the window (12 cores), a minor shared-resource effect on timings.
10. **Cost subset is n=1 per task**, so its only error bar is the 8-task spread; the 4-lane
    tokens/task column carries the N=5 spread.

## 7. Status log

* 2026-10-13T07:31+08:00 — state checks pass (revision `45ebb32`, clean tree, 8834 healthy).
* 2026-10-13T07:32+08:00 — our arm launched (4 lanes, N=5).
* 2026-10-13T07:45+08:00 — pi smoke test T-04 on 8834: claimed/actual true/true (matches
  reference); full 40-task pi re-run confirmed infeasible in the 2-hour budget.
* 2026-10-13T08:45+08:00 — our arm complete, 200/200 runs (73 min).
* 2026-10-13T08:52+08:00 — single-lane wall-clock subset complete (8 tasks, 220.9 s).
* 2026-10-13T09:01+08:00 — pi probe seed 1 complete (12/12 tasks).
* 2026-10-13T09:11+08:00 — pi probe seed 2 complete (12/12 tasks); report written.
