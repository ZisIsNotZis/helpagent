# Requirement 2 — five-arm verification ablation (complete N=3)

**Outcome:** the run is **complete** — **600/600 cells** (5 arms × 40 tasks × 3 repeats),
no duplicates, no missing cells. This doc is the requirement-2 measurement deliverable.

- **Revision:** `45ebb32f1be0977b9149057da3a80ee93ce22840` (HEAD unchanged; repo code never
  modified by this run — `git status` clean for tracked files, `git diff --check` clean).
- **Model / server:** Spark-X2.5-4B Q4_K_M (`llama-server`, port 8834, `-c 32768`,
  `--cache-type-k q8_0 --cache-type-v q8_0`), identical config for all 600 cells.
- **Data:** `/tmp/wave1/final/r2/runs/*/*/*/results.jsonl` (600 rows),
  analysis `/tmp/wave1/final/r2/analysis.{json,txt}`, per-poll log
  `/tmp/wave1/final/r2/checkpoints.md`.
- **Provenance:** a prior worker measured **380** cells before its processes died
  (last auto-checkpoint 2026-10-13T21:17:53 = 371, on-disk state at resume = 380).
  This session resumed and measured the remaining **220** cells
  (2026-10-14T09:50:01 → 10:51:45 +08:00, 9 lane jobs, all `rc=0`). 380 + 220 = 600.
- **Measurement only:** no claim path was added; every row comes from
  `bench.v2_leaf.run_once` → `harness.leaf.run_leaf` → the single `claim_decision` gate.

---

## 1. Arms (the cumulative verification ladder)

Derived from `bench/v2_measure.py::ABLATIONS` + `bench/v2_leaf.py::run_once`; the driver
`r2_lane.py` reuses the four `ABLATIONS` entries verbatim and synthesises only the missing
`verify=test` arm. The `ABLATIONS` **keys are subtractive** (e.g. its `"review"` key turns
IV *on*), so the arms below are named by **what runs**.

| arm (what runs) | verify | judge | IV | review | exact invocation |
| --- | --- | --- | --- | --- | --- |
| **A0 dev-only (raw)** | `raw` | off | off | off | `ABLATIONS["own-test"]` (raw drops test/IV/review/claim) |
| **A1 + own test** | `test` | on | off | off | synthesised `verify=test` (self-test loop only) |
| **A2 + own test + IV** | `full` | on | on | off | `ABLATIONS["review"]` |
| **A3 + own test + review** | `full` | on | off | on | `ABLATIONS["independent-test"]` |
| **A4 full** | `full` | on | on | on | `ABLATIONS["none"]` |

All arms run the same 40 tasks, the same `--calls 24` / `--deadline-hours 6` budget, and
N=3 independent repeats per task.

### Arm table (N=3, 120 runs/arm)

| arm | actual | claimed | false success | calls/task | tokens/task | wall s/task |
| --- | --- | --- | --- | --- | --- | --- |
| A0 dev-only (raw) | **70/120 (58.3%)** | 0 (0.0%) | 0 (0.0%) | 1.01 | 1 198 | 7.5 |
| A1 + own test | **66/120 (55.0%)** | 0 (0.0%) | 0 (0.0%) | 5.54 | 8 480 | 49.8 |
| A2 + own test + IV | **65/120 (54.2%)** | 1 (0.8%) | 0 (0.0%) | 6.63 | 10 570 | 58.3 |
| A3 + own test + review | **71/120 (59.2%)** | 54 (45.0%) | **10 (8.3%)** | 9.13 | 12 696 | 60.7 |
| A4 full | **77/120 (64.2%)** | 28 (23.3%) | **1 (0.8%)** | 12.86 | 18 894 | 97.9 |

Quadrants (true-success / honest-failure / missed-success / false-success):

| arm | true | honest-fail | missed | false |
| --- | --- | --- | --- | --- |
| dev-only | 0 | 50 | 70 | 0 |
| + own test | 0 | 54 | 66 | 0 |
| + own test + IV | 1 | 55 | 64 | 0 |
| + own test + review | 44 | 39 | 27 | 10 |
| full | 27 | 42 | 50 | 1 |

## 2. Incremental contribution of each stage

Paired per task (`rate_with(t) − rate_without(t)` over the 40 tasks, reported in **tasks
out of 40**), 95 % percentile bootstrap CI (10 000 resamples, seed **20261013**), and the
exact McNemar (sign) test on the discordant tasks. Each contrast changes **exactly one
stage**, so it isolates that stage. Script: `r2_analyze.py`.

| contrast | stage isolated | Δactual [95% CI] | McNemar p | Δclaimed | Δfalse [95% CI] | p |
| --- | --- | --- | --- | --- | --- | --- |
| A1 − A0 | own test | **−1.33 [−5.67, +3.00]** | 0.549 | +0.00 | +0.00 [0.00, 0.00] | 1.000 |
| A2 − A1 | independent test | **−0.33 [−3.00, +2.33]** | 1.000 | +0.33 | +0.00 [0.00, 0.00] | 1.000 |
| A3 − A1 | review (IV absent) | **+1.67 [−1.33, +5.33]** | 1.000 | +18.00 | **+3.33 [+1.00, +6.33]** | 0.031 |
| A4 − A2 | review (IV present) | **+4.00 [+1.33, +7.00]** | **0.012** | +9.00 | +0.33 [0.00, +1.00] | 1.000 |
| A4 − A3 | independent test (review present) | **+2.00 [−0.67, +4.67]** | 0.388 | −8.67 | **−3.00 [−5.67, −1.00]** | 0.031 |
| A4 − A0 | all three together | **+2.33 [−0.33, +5.33]** | 0.344 | +9.33 | +0.33 [0.00, +1.00] | 1.000 |

**What is actually significant here (be honest about N):**

- The only contrast with a **significant correctness gain** is `A4 − A2` (review added on
  top of own-test+IV): **+4.00 tasks [ +1.33, +7.00 ], p = 0.012**.
- The **independent test shows no significant correctness effect in either direction**
  (`A2−A1` −0.33, `A4−A3` +2.00); its clean effects are on claims (−8.67, p=0.0009) and
  **false successes (−3.00 [−5.67, −1.00], p = 0.031)**.
- **Review added to the own test alone** produces no significant correctness change but
  **significantly increases false successes** (+3.33 [ +1.00, +6.33], p = 0.031) and
  claims (+18.00, p < 0.0001).
- Everything else has a CI spanning 0 — **inconclusive**, not "proven zero" (per the
  protocol's power note: ~±1.5 tasks/40 is the detectable consistent effect at 40 tasks).

### Stage-signal joins (verdict vs the external grader)

| arm | self-test ran | claimed on own-test | IV ran | IV approved (false-approve) | IV blocked (false-block) | review ran | claimed on review (false-approve) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 + own test | 101 | **0** | — | — | — | — | — |
| A2 + own test + IV | 109 | **0** | 40 | 5 (1) | 35 (12) | — | — |
| A3 + own test + review | 108 | **0** | — | — | — | 64 | 54 (10) |
| A4 full | 103 | **0** | 110 | 18 (1) | 92 (**57**) | 72 | 25 (1) |

Two facts worth stating: (i) the self-test **never** carried a claim in any of the 600 runs
(`claimed_basis` is always `review` and/or `independent-test`); (ii) in the full arm the
independent test withheld approval in 92/110 runs, **57 of which the grader passed** — it is
a very conservative filter that rejects many genuinely-correct solutions.

## 3. The four questions, answered

**(a) Does the own test add correctness beyond raw? — No.**
`A1 − A0` = **−1.33 tasks [−5.67, +3.00]**, McNemar p = 0.549. The point estimate is
*negative*, the CI spans 0, the self-test produced **0 claims and 0 false successes**, and
it costs ~7× tokens (1 198 → 8 480/task) and ~6.6× wall time (7.5 → 49.8 s/task). Under the
pre-registered rule this is **zero-information**, and there is no evidence of any
correctness benefit on this revision.

**(b) Is the independent test net-positive / neutral / negative? — Neutral on correctness;
strongly protective of the claim.**
`A2 − A1` = −0.33 [−3.00, +2.33] (p = 1.0); `A4 − A3` = +2.00 [−0.67, +4.67] (p = 0.388).
Neither is significant, so on **actual correctness the IV is indistinguishable from zero**.
Its real, significant effects are to cut claims (`A4−A3` Δclaimed −8.67, p = 0.0009) and to
cut false successes (`A4−A3` Δfalse −3.00 [−5.67, −1.00], p = 0.031). It is also the most
expensive stage to be wrong with: it false-blocks 57 of 92 grader-passing runs in the full
arm. Net: **neutral on correctness, net-positive only as a false-claim suppressor.**

**(c) Does review add correctness or only claims? — Mostly claims; correctness only
alongside the IV (an interaction).**
On its own (`A3 − A1`): +1.67 tasks [−1.33, +5.33], p = 1.0 — **no significant correctness**
— while adding **+18.00 claimed** (p < 0.0001) and **+3.33 false successes [ +1.00, +6.33]**
(p = 0.031). By the protocol's rule 4 (Δfalse CI lower bound > 0) this contrast makes review
**negative information**. But with the IV present (`A4 − A2`): **+4.00 tasks [ +1.33,
+7.00], p = 0.012** — the only significant correctness gain in the whole ladder — with only
+0.33 false successes. So review's correctness value is **conditional on the independent
test**; alone it mostly buys claims and errors.

**(d) False successes per arm (out of 120):**

| arm | false successes | rate |
| --- | --- | --- |
| dev-only | **0** | 0.0 % |
| + own test | **0** | 0.0 % |
| + own test + IV | **0** | 0.0 % |
| + own test + review | **10** (T-18#3, T-24#3, T-26#2, T-26#3, T-34#3, A-02#1, A-02#2, A-05#1, A-05#2, A-05#3) | 8.3 % |
| full | **1** (A-05-zebra-puzzle #1, basis `review+independent-test`) | 0.8 % |

The only claims that can be false are those carried by review and/or IV. The full arm's one
false success is a case where **both** the independent test **and** the review approved a
solution the external grader failed.

### R2 verdict on this data

Under the pre-registered `ablation-protocol.md` §6 rule, the own test and the independent
test are **zero-information** on actual correctness, review is **negative-information** in
the `A3−A1` contrast (it raises false successes), and no stage has a clean
positive-information profile (every "positive" reading carries either a live CI or a
false-success increase). **R2 as stated — every stage carries information — is therefore
NOT supported on revision 45ebb32 with this model and corpus.** The full pipeline does beat
raw overall (**+2.33 tasks [−0.33, +5.33]**, p = 0.34, n.s.) for ~16× the tokens and ~13×
the wall time, but that gain is driven by the review+IV combination, not by the stages
individually.

## 4. Exact commands

```sh
# 0. the measurement server was DOWN at handoff; restarted with the documented config
#    (docs/STATUS.md §8e) so the resumed 220 cells match the 380 already on disk
llama-server \
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health          # {"status":"ok"}

# 1. dry-run: list the missing cells per (chunk, arm) -> 220 missing
uv run python /tmp/wave1/final/r2/r2_resume.py --arm full --tasks <T-11..T-20> \
  --n 3 --out /tmp/wave1/final/r2/runs/c2/full --dry-run

# 2. resume queue: 9 jobs = the 4 partial jobs + all 5 c4 jobs, 4 lanes (-P 4)
nohup bash /tmp/wave1/final/r2/resume_queue.sh > /tmp/wave1/final/r2/resume_queue.out 2>&1 &
#    each job: bash /tmp/wave1/final/r2/job_resume.sh '<chunk>|<arm>|<tasks>'
#    -> uv run python /tmp/wave1/final/r2/r2_resume.py --arm <arm> --tasks <tasks> \
#         --n 3 --server http://127.0.0.1:8834 --out /tmp/wave1/final/r2/runs/<chunk>/<arm>

# 3. per-poll checkpoint (every <=180 s)
python3 /tmp/wave1/final/r2/poll.py auto      # appends to checkpoints.md

# 4. analysis over the COMPLETE data
uv run python /tmp/wave1/final/r2/r2_analyze.py \
  --glob '/tmp/wave1/final/r2/runs/*/*/*/results.jsonl' \
  --out /tmp/wave1/final/r2/analysis.json --text /tmp/wave1/final/r2/analysis.txt
```

`r2_resume.py` is a **resume wrapper**: it imports `r2_lane.LADDER` and
`bench.v2_measure`, and calls the identical `run_once(...)` with the identical per-cell
`out_dir` / row shape as `_run_arm`; its only added behaviour is to **skip (task, seed)
cells already present** in `results.jsonl`. (`bench.v2_measure._run_arm` always re-runs
every cell and appends, so it cannot finish a killed job without duplicating cells.)
No file under `/home/z/vibe/helpagent` was created or modified.

## 5. Limitations

- **Small samples.** N=3 repeats × 40 tasks. The protocol's own power note: ~±1.5 tasks/40
  is the detectable consistent effect; several CIs here span 0 and must be read as
  *inconclusive*, not as proof of no effect. p-values are descriptive — 6 contrasts × 3
  metrics with no multiplicity correction.
- **No RNG seed.** `LlamaServerRunner` fixes temperature = 0.2 and exposes no seed, so a
  "seed" is an independent stochastic repeat. The historical run-to-run spread (STATUS §8e,
  ±3 tasks) is the noise floor against which the ±2–4 task effects above should be read.
- **Server restart during the campaign.** The 8834 server was down at handoff and was
  restarted once with the documented config. The 380 pre-crash cells and the 220 resumed
  cells therefore share one model/config, but any unseen config drift would be undetectable
  in this analysis.
- **Arm ordering / cost confound.** The ladder is cumulative and the per-run budget is
  fixed (24 calls, 6 h), so later arms have the same budget but different stage counts;
  stage effects are not cost-matched.
- **Descriptive signal joins.** `false-block` / `false-approve` counts join stage verdicts
  to the external grader; they are associations, not causal statements.
- **Scope.** This measures one model (Spark-X2.5-4B Q4_K_M) on one revision (`45ebb32`)
  over 40 tasks. No claim is made about other models, revisions or corpora.

## 6. Cleanup

All measurement lanes are stopped; no `r2_resume.py` / `r2_lane.py` / queue processes
remain. The `llama-server` started for this run was also stopped at completion (it was down
at handoff; restart with the command in §4). No orphan processes.
