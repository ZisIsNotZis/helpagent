# Final measurement — independent verification (fresh context, read-only)

**Scope.** Independent, fresh-context recomputation of the three definitive measurement
verdicts for the helpagent requirement campaign, **from the raw per-run rows**, not from the
summary docs. Frozen revision checked; no code or existing doc modified; no model calls made
(server down). This file is the only artefact created.

**Revision / tree state.**
`git rev-parse HEAD` = `45ebb32f1be0977b9149057da3a80ee93ce22840` (matches the pin).
`git status --short` shows only untracked `.scratch/28-three-requirements/issues/*.md`
measurement docs; no tracked file modified, nothing staged (`git diff --cached` empty).

**Method.** I re-read every raw row and recomputed each statistic with an independently
written script (same pre-registered rule/method as the runs: task-clustered percentile
bootstrap, seed `20261013`; B=20000 for R1, B=10000 for R2/R3). Where the stored analyser
JSON exists I compared my numbers to it as a methodology cross-check, not as the source.

---

## Verdict summary

| # | Measurement | Verdict under test | Independent result |
| --- | --- | --- | --- |
| R1 | head-to-head ours vs pi, N=25 | **INCONCLUSIVE** at M=3 | **PASS** — confirmed from raw |
| R2 | five-arm verification ablation, N=3 (600/600) | stage contributions table | **PASS** — confirmed from raw |
| R3 | decomposition / step-splitting, 210 runs | **NEGATIVE** | **PASS** — confirmed from raw |
| — | `uv run pytest -q -p no:warnings` at HEAD | passes; single-claim-gate structural test passes | **PASS** |

**No discrepancy, rounding issue, or untraceable number was found in any of the three
verdicts.** Every decisive figure below was recomputed from raw rows and matches the docs.

---

## 1. Requirement 1 — N=25 head-to-head (verdict INCONCLUSIVE) — PASS

Raw data (2000 rows = 1000/arm, 40 tasks × 25 seeds, 4 lanes/seed):
`/tmp/wave1/final/{our-n5,n9/our-extra,n17/our-extra,n25/our-extra}` (ours) and
`/tmp/wave1/final/{n9/pi-n9,n17/pi-extra,n25/pi-extra}` (pi).

### 1.1 Per-seed 40-task totals (raw recomputation) — matches doc exactly

* **ours (seeds 1..25):** `26,24,25,27,23,26,24,26,25,24,24,24,27,24,24,26,24,23,25,24,23,26,23,24,25`
* **pi (seeds 1..25):** `24,24,23,23,24,28,23,26,27,27,27,26,25,22,27,26,26,30,21,25,24,21,25,25,25`

Both lists are byte-identical to the doc. Row integrity: every seed has exactly 40 rows/arm,
0 duplicate tasks, 0 missing cells. Totals: **ours 616/1000, pi 624/1000** (doc 616/624).

### 1.2 Means, sd, delta, CI, rule

| quantity | recomputed | doc | agree |
| --- | --- | --- | --- |
| ours mean /40 | 24.640 | 24.640 | ✓ |
| ours sd (sample) | 1.2207 | 1.221 | ✓ |
| pi mean /40 | 24.960 | 24.960 | ✓ |
| pi sd (sample) | 2.1502 | 2.150 | ✓ |
| Δ = actual(ours) − actual(pi) | **−0.320 tasks** | −0.320 | ✓ |
| task-clustered 95% CI (seed 20261013, B=20000) | **[−3.520, +3.080]** | [−3.520, +3.080] | ✓ |
| `Lo95 ≥ −3`? | −3.520 ≥ −3 → no (misses by 0.520) | no | ✓ |
| `Hi95 < −3`? | +3.080 < −3 → no | no | ✓ |
| strict BEAT `Lo95 > 0`? | no | no | ✓ |
| **verdict** | **INCONCLUSIVE** | INCONCLUSIVE | ✓ |
| claimed | ours 224, pi 647 | 224 / 647 | ✓ |
| false success (claimed ∧ ¬actual) | ours 22/1000 = 2.20%; pi 61/1000 = 6.10% | same | ✓ |
| Δ_false (task-clustered) | **−1.56 tasks, [−3.16, −0.20]** | −1.56, [−3.16, −0.20] | ✓ |

Cross-check: my numbers are identical to the stored analyser
`/tmp/wave1/final/n25/analysis-n25-final.json` (Δ=−0.3200, CI=[−3.5200,+3.0800],
verdict=INCONCLUSIVE) and to `n25/traj-17.json` / `n17/analysis-n17.json` for the reused
N=17 frozen result (ours 423/680, pi 428/680, Δ=−0.2941, CI=[−3.4706,+3.0588]).

### 1.3 "CI width is structural (flat N=17→N=25)" — CONFIRMED

Independently recomputed full CI at each N (same seed/B):

| N | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Δ | −0.294 | −0.667 | −0.421 | −0.450 | −0.476 | −0.227 | −0.304 | −0.333 | −0.320 |
| lo95 | −3.471 | −3.889 | −3.632 | −3.650 | −3.667 | −3.364 | −3.435 | −3.500 | −3.520 |
| hi95 | +3.059 | +2.667 | +2.947 | +2.950 | +2.905 | +3.136 | +3.000 | +3.042 | +3.080 |
| **width** | **6.53** | 6.56 | 6.58 | 6.60 | 6.57 | 6.50 | 6.44 | 6.54 | **6.60** |

Width is flat (range 6.44–6.60) over N=17→25; the Δ trajectory is likewise flat around
−0.3. Robustness: re-running the N=25 bootstrap with unrelated seeds gives
CI [−3.520,+3.040] (seed 1), [−3.520,+3.040] (42), [−3.520,+3.120] (999) — the bound is not
a seed artefact.

### 1.4 "More seeds cannot resolve it" — CONFIRMED (quantified)

Decomposition of the per-task Δ variance at N=25: total across-task variance of the 40
per-task Δ = 0.0717; mean within-task seed-variance of the per-task Δ = 0.1562, whose
contribution to each per-task mean is `0.1562/25 = 0.00625` = **8.7 %** of the per-task
variance. The remaining **structural (task-heterogeneity) floor = 0.0655**, which does not
shrink with more seeds. Projecting the CI width onto `sqrt(structural + within/N)`:

| projected N | 25 (now) | 50 | 100 | 400 | ∞ |
| --- | --- | --- | --- | --- | --- |
| CI width | 6.60 | 6.45 | 6.38 | 6.32 | **6.31** |

Even at infinite seeds the CI stays ~6.3 tasks wide, while the point estimate is only
−0.32. With half-width ≈3.2, `Lo95 ≥ −3` needs Δ ≈ **+0.3 tasks**, i.e. the point estimate
must move ~0.6 tasks — which seed accumulation of a near-tie cannot manufacture. The doc's
structural explanation is correct.

### 1.5 Sample check of the per-task table

Parsed all **40 table rows × 6 columns** (ours act/pi act/ours claimed/pi claimed/ours false/
pi false) from `fix-wave1-measurement-n25.md` and compared each against raw counts:
**240/240 cells match, 0 mismatches.** (Concrete raw rows also spot-read; e.g. seed 25,
T-01 ours actual/claimed = True/True, T-11 = True/False.)

---

## 2. Requirement 2 — five-arm ablation, 600/600 — PASS

Raw data: `/tmp/wave1/final/r2/runs/*/*/*/results.jsonl` (20 files, **600 rows**; 5 arms ×
40 tasks × 3 repeats; 0 duplicates, 0 missing cells per arm).

### 2.1 Arm totals (recomputed)

| arm | actual | claimed | false success | tokens/task | calls/task | wall s/task |
| --- | --- | --- | --- | --- | --- | --- |
| dev-only (raw) | **70/120 (58.3 %)** | 0 | 0 | 1198 | 1.0 | 7.5 |
| + own test | **66/120 (55.0 %)** | 0 | 0 | 8480 | 5.5 | 49.8 |
| + own test + IV | **65/120 (54.2 %)** | 1 | 0 | 10570 | 6.6 | 58.3 |
| + own test + review | **71/120 (59.2 %)** | 54 | **10** | 12696 | 9.1 | 60.7 |
| full | **77/120 (64.2 %)** | 28 | **1** | 18894 | 12.9 | 97.9 |

Identical to the doc's arm table; quadrant counts
(`true/honest-fail/missed/false`) also match exactly: dev-only 0/50/70/0, own-test 0/54/66/0,
own-iv 1/55/64/0, own-review 44/39/27/10, full 27/42/50/1.

### 2.2 Paired incremental contributions (recomputed, 40 tasks, B=10000, seed 20261013)

| contrast | stage | Δactual [95 % CI] | McNemar p | Δfalse [95 % CI] | Δfalse p |
| --- | --- | --- | --- | --- | --- |
| A1 − A0 | own test | **−1.33 [−5.67, +3.00]** | 0.549 | +0.00 [0.00, 0.00] | 1.000 |
| A2 − A1 | independent test | **−0.33 [−3.00, +2.33]** | 1.000 | +0.00 [0.00, 0.00] | 1.000 |
| A3 − A1 | review (IV absent) | **+1.67 [−1.33, +5.33]** | 1.000 | **+3.33 [+1.00, +6.33]** | 0.031 |
| A4 − A2 | review (IV present) | **+4.00 [+1.33, +7.00]** | **0.012** | +0.33 [0.00, +1.00] | 1.000 |
| A4 − A3 | independent test | **+2.00 [−0.67, +4.67]** | 0.388 | **−3.00 [−5.67, −1.00]** | 0.031 |
| A4 − A0 | all three | **+2.33 [−0.33, +5.33]** | 0.344 | +0.33 [0.00, +1.00] | 1.000 |

Every Δactual, CI and McNemar p matches the doc; the two Δfalse p=0.031 values are
reproduced by the per-task sign test (own-review−own-test: 6 up / 0 down; full−own-review:
0 up / 6 down). My values are identical to the stored `/tmp/wave1/final/r2/analysis.json`
pairs block.

### 2.3 False-success counts and identities — match

* dev-only 0, own-test 0, own-iv 0, own-review **10**, full **1** (out of 120 each).
* own-review's 10 false successes from raw:
  `T-18#3, T-24#3, T-26#2, T-26#3, T-34#3, A-02#1, A-02#2, A-05#1, A-05#2, A-05#3` — all
  `claimed_basis="review"`; exactly the doc's list.
* full's 1: `A-05-zebra-puzzle #1`, basis `review+independent-test` — matches.
* Stage-signal joins reproduced: own-test never carries a claim (0/…); A2 IV ran 40,
  approved 5 (1 false-approve), blocked 35 (12 false-block); A3 review ran 64, claimed on
  review 54 (10 false); A4 IV ran 110, approved 18 (1), blocked 92 (**57** false-block),
  review ran 72, claimed on review 25 (1). Matches the doc's join table.

**R2 = PASS.** No discrepancy.

---

## 3. Requirement 3 — decomposition / step-splitting, 210 runs (verdict NEGATIVE) — PASS

Raw data: `/tmp/wave1/final/r3/{leaf,tree-greedy,tree-tournament}/<task>-<seed>/run.json`
(70/arm; 70 common paired keys = 14 tasks × 5 seeds).

### 3.1 Arm totals (recomputed)

| arm | actual | claimed | false success | mean calls | total calls | mean wall s |
| --- | --- | --- | --- | --- | --- | --- |
| B0 leaf | **47/70 = 67.1 %** | 8 | **0** | 14.4 | 1009 | 175 |
| B1 tree-greedy | **14/70 = 20.0 %** | 18 | **4** | 31.6 | 2214 | 408 |
| B2 tree-tournament | **15/70 = 21.4 %** | 18 | **3** | 35.2 | 2465 | 498 |

Group rates (recomputed): DECOMPOSABLE (9 tasks/45 runs) leaf 29/45 = 64.4 %, greedy
9/45 = 20.0 %, tournament 10/45 = 22.2 %; FORCED-LEAF (5 tasks/25 runs) 18/25 = 72.0 %,
5/25 = 20.0 %, 5/25 = 20.0 %. All match the doc.

### 3.2 Paired deltas and CIs (recomputed, B=10000, seed 20261013)

| arm vs leaf | group | mean d̄ | 95 % CI | tree-only / leaf-only | McNemar p | Δfalse (CI) |
| --- | --- | --- | --- | --- | --- | --- |
| B1 greedy | DECOMPOSABLE (9) | **−0.444** | **[−0.733, −0.178]** | 0 / 20 | 0.000 | +0.067 [+0.000, +0.156] |
| B1 greedy | FORCED-LEAF (5) | **−0.520** | **[−0.920, −0.120]** | 1 / 14 | 0.001 | +0.040 [+0.000, +0.120] |
| B2 tournament | DECOMPOSABLE (9) | **−0.422** | **[−0.689, −0.178]** | 2 / 21 | 0.000 | +0.067 [+0.000, +0.156] |
| B2 tournament | FORCED-LEAF (5) | **−0.520** | **[−0.800, −0.240]** | 1 / 14 | 0.001 | +0.000 [+0.000, +0.000] |

All values match the doc and the stored `/tmp/wave1/final/r3/analysis-r3.txt`. The
pre-registered rule fires NEGATIVE for both tree arms (decomposable CI upper bound
−0.178 < 0, forced-leaf CI upper bound < 0, false CI lower bound = 0.000 not > 0).

### 3.3 "Mechanism actually fired" evidence (decomposed-How) — CONFIRMED

From `run.json` → recursive `nodes[].candidates[].how_case` (census over all runs):

* **B1 greedy:** `decomposed-How` appeared in **3 / 70 runs**, on **3 / 9** decomposable
  tasks — T-31 ×1, T-32 ×1, T-33 ×1. Full census `leaf-How` 137, `fallback-leaf-How` 12,
  `decomposed-How` 3, `forced-leaf` 6, `failed-How` 1; `allocation.forced` nodes = 3.
* **B2 tournament:** `decomposed-How` in **9 / 70 runs**, **4 / 9** tasks — T-32 ×4,
  T-31 ×3, T-33 ×1, T-11 ×1. Census `leaf-How` 142, `fallback-leaf-How` 22,
  `decomposed-How` 9, `forced-leaf` 3, `failed-How` 1; forced nodes = 1.

Identical to the doc §5 table and to `supp-r3.txt`. The gate (≥1 decomposed-How run on ≥3
of 9 decomposable tasks) is met, so the NEGATIVE verdict is a valid decomposition test, not
an un-fired-mechanism result.

**R3 = PASS.** No discrepancy.

---

## 4. Raw-row sample checks (traceability)

* **R1:** all 40 per-task table rows × 6 fields verified against raw row counts (240 cells,
  0 mismatches); both per-seed-total lists (50 numbers) verified; arm totals, claimed and
  false-success verified; concrete rows spot-read at seed 25 for both arms.
* **R2:** all 5 arm rows × (actual/claimed/false) verified; all 5 quadrant rows verified;
  the 11 false-success rows enumerated from raw and matched to the doc's cell list; the
  stage-join counters reproduced.
* **R3:** all 3 arm rows verified (actual/claimed/false/calls/totals); group table verified;
  the 4 contrast rows verified; per-task `decomposed-How` counts and `allocation.forced`
  census verified against §5.

This exceeds the requested ≥10 raw rows per measurement. **Reported discrepancies: none.**

Two traceability notes (not discrepancies):

1. R1's `pi` `results.jsonl` rows carry **no** `false_success` field; the 61/1000 figure is
   only reproducible as `claimed ∧ ¬actual` (the analyser does exactly this via
   `setdefault`). Verified: pi claimed = 647, pi false = 61. Our arm's stored field and the
   recomputed `claimed ∧ ¬actual` both give 22.
2. R2's Δfalse significance p=0.031 is the per-task sign test; the analyser's printed
   McNemar column is for `actual` only. The doc's Δfalse p values are consistent with the
   per-task sign computation (reproduced above).

---

## 5. Test gate at HEAD

```
$ uv run pytest -q -p no:warnings        # addopts already contains -q
EXIT=0
```
Result: **827 passed** (0 failed/errored, 0 skips reported) on the frozen revision.
The single-claim-gate structural test
`tests/unit/test_v2_leaf.py::test_claim_gate_enforces_every_rule_directly`
("the ONE gate's rule list, pinned directly on `claim_decision`") passes; running
`tests/unit/test_v2_leaf.py -k claim_gate` gives 4 passed.

---

## 6. Overall statement — which verdicts are independently confirmed

Recomputed from the raw per-run rows, with fresh scripts and no reliance on the summary
numbers:

1. **R1 — INCONCLUSIVE at M=3 is independently confirmed.** Ours 616/1000 (mean 24.640,
   sd 1.2207) vs pi 624/1000 (mean 24.960, sd 2.1502); Δ = −0.320; task-clustered 95 % CI
   [−3.520, +3.080]; the rule returns INCONCLUSIVE. The CI width is structural (flat
   6.44–6.60 over N=17→25; seed-noise accounts for only ~8.7 % of the per-task-mean
   variance, leaving a ~6.3-task floor at infinite seeds), so more seeds cannot resolve the
   0.52-task gap to the −3 boundary.
2. **R2 — the five-arm ablation result is independently confirmed.** All five arm totals
   (70/66/65/71/77 of 120), the six paired incremental contributions with their CIs and
   significance (A4−A2 +4.00 [+1.33,+7.00], p=0.012 is the only significant correctness
   gain; A3−A1 and A4−A3 give the Δfalse ±3.00 effects), and the false-success counts
   (0/0/0/10/1) all trace exactly to raw rows. The doc's verdict that R2-as-stated is NOT
   supported follows from these numbers.
3. **R3 — the NEGATIVE verdict is independently confirmed.** Leaf 47/70 (67.1 %) vs greedy
   14/70 (20.0 %) and tournament 15/70 (21.4 %); decomposable CI [−0.733,−0.178] (B1) and
   [−0.689,−0.178] (B2), forced-leaf CIs also entirely below 0; the pre-registered rule
   returns NEGATIVE. The mechanism did fire (B1 3/70 on 3/9 tasks; B2 9/70 on 4/9 tasks),
   so the comparison is valid.

No fabrication survived: every decisive number has a raw-data trace, and the one
unverifiable side-claim (pi token counts) is already declared unmeasured in the source doc.

**Residual gaps / risks.** `pi` token/task remains unmeasured in the raw data (driver has no
token counters) — this is a declared gap in the R1 doc, not a discrepancy here; it does not
touch the R1 verdict. R1's CI method is reproduced with the documented seed; alternative
bootstrap seeds shift the bound by ≤0.04, so the INCONCLUSIVE verdict is not a seed
artefact.
