# Every number in the draft, its source, and the command that re-derives it

One row per number. `Source` is a reference in this repository — `path#anchor`, naming a heading
rather than a line, so that editing a document cannot rot the citation; a line reference
`path:line` is still accepted where the target is code. A cell may cite more than one place.
`Command` is one of four forms, and the choice of form is part of the claim:

1. **A printed key**, `python3 reproduce.py <key>` — the number is printed by the entry point,
   which refuses a key it does not print. Where the entry point formats the same quantity
differently from this table (a signed delta, a bracketed interval, a rounded share), the row's
   value is that quantity written the way the paper writes it, and the key still names it.
2. **The bare entry point**, `python3 reproduce.py` — the number is a field of a record the entry
   point compares in full, so a mismatch stops the run, but it is not one of the printed keys.
3. **An analyzer command from the traceability table** `bench/analysis/wave1/NUMBERS.md` — the
   campaign's own analyzer, run over the secured home, whose output carries the number.
4. **`unknown`** — no committed command re-derives it yet. The gap is named below the table and
   the paper states the number as recorded, never as re-derived.

The provenance rule for `unknown` is the traceability table's own: a number whose inputs are
secured but whose recompute command has never been run is "recorded as unknown, not as fine"
(`bench/analysis/wave1/NUMBERS.md:43`).

| Number | Value | Source | Command |
| --- | --- | --- | --- |
| R1, ours: tasks solved per run | `24.640` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_a_mean_tasks` |
| R1, baseline: tasks solved per run | `24.960` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_b_mean_tasks` |
| R1, paired delta in tasks | `-0.320` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_delta_tasks` |
| R1, task-clustered 95% interval, low | `-3.520` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_lo95` |
| R1, task-clustered 95% interval, high | `3.080` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_hi95` |
| R1, interval level | `95` | `docs/2_GOAL.md#r1-capability-parity` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, bootstrap resamples | `20000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, bootstrap seed | `20261013` | `docs/2_GOAL.md#r1-capability-parity` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, margin of the pre-registered rule, tasks | `M=3` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, shortfall against the margin, tasks | `0.520` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_shortfall_tasks` |
| R1, seeds per arm | `25` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, run rows per arm | `1000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_rows_per_arm` |
| corpus size, tasks | `40` | `docs/6_ARCHITECTURE.md#fair-comparison-precondition` | `python3 reproduce.py` |
| R1, ours: runs solved | `616/1000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, baseline: runs solved | `624/1000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, ours: false successes | `22/1000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, baseline: false successes | `61/1000` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py` |
| R1, false-success difference, tasks | `-1.56` | `docs/8_DETAIL.md#false-successes-and-honesty` | `python3 reproduce.py` |
| R1, false-success difference, interval | `[-3.16, -0.20]` | `docs/8_DETAIL.md#false-successes-and-honesty` | `python3 reproduce.py` |
| R1 interval width: half-width, tasks | `3.3` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_half_width` |
| R1 interval width: full width at the frozen intermediate N | `6.53` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_width_n17` |
| R1 interval width: full width at the final N | `6.60` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_width_n25` |
| R1 interval width: smallest full width over the N=17..25 sweep | `6.43` | `bench/analysis/wave1/n25/interval-widths.json:77` | `python3 reproduce.py r1_width_min` |
| R1 interval width: seeds spanned by the flat range | `17`, `25` | `docs/2_GOAL.md#r1-capability-parity`, `docs/2_GOAL.md#r1-capability-parity` | `unknown` |
| R1 interval width: within-seed share of variance, percent | `8.7%` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_within_share_pct` |
| R1 interval width: asymptotic projection, tasks | `6.3` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_asymptotic_width` |
| R1, point estimate needed for ACHIEVED, tasks | `0.3` | `docs/2_GOAL.md#r1-capability-parity` | `python3 reproduce.py r1_needed_estimate` |
| R1, starting position on the earlier revision | `24/40`, `27/40` | `docs/2_GOAL.md#r1-capability-parity` | `unknown` |
| R1, the short-input trap: delta over a starved input | `0.06` | `bench/analysis/wave1/NUMBERS.md:77` | `unknown` |
| R1, the short-input trap: interval over a starved input | `[-3.35, 3.71]` | `bench/analysis/wave1/NUMBERS.md:77` | `unknown` |
| R1, the short-input trap: rows read | `680` | `bench/analysis/wave1/NUMBERS.md:78` | `unknown` |
| R3, leaf: runs solved | `47/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_leaf` |
| R3, tree-greedy: runs solved | `14/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_tree_greedy` |
| R3, tree-tournament: runs solved | `15/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_tree_tournament` |
| R3, claimed runs per arm | `8/70`, `18/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `H=$(pwd)/bench/projection/wave1/final/r3; sed "s\|/tmp/wave1/final/r3\|$H\|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` |
| R3, false successes per arm | `0`, `4`, `3` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `H=$(pwd)/bench/projection/wave1/final/r3; sed "s\|/tmp/wave1/final/r3\|$H\|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` |
| R3, leaf: mean calls per task | `14.4` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_leaf_mean_calls` |
| R3, tree-greedy: mean calls per task | `31.6` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_tree_greedy_mean_calls` |
| R3, tree-tournament: mean calls per task | `35.2` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, mean wall clock per run | `175`, `408`, `498` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, runs per arm | `70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `python3 reproduce.py r3_leaf` |
| R3, design: tasks, arms, seeds, runs | `14`, `3`, `5`, `210` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on decomposable tasks: mean delta | `-0.444` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on decomposable tasks: interval | `[-0.733, -0.178]` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-only and leaf-only fixes, decomposable | `0`, `20` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on forced-leaf tasks: mean delta | `-0.520` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on forced-leaf tasks: interval | `[-0.920, -0.120]` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-only and leaf-only fixes, forced-leaf | `1`, `14` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: mean delta | `-0.422` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: interval | `[-0.689, -0.178]` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: tree-only and leaf-only fixes | `2`, `21` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on forced-leaf tasks: mean delta | `-0.520` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on forced-leaf tasks: tree-only and leaf-only fixes | `1`, `14` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on forced-leaf tasks: interval | `[-0.800, -0.240]` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, exact McNemar p, four comparisons | `0.000`, `0.001` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach`, `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: greedy, runs | `3/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: greedy, decomposable tasks | `3/9` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: tournament, runs | `9/70` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: tournament, decomposable tasks | `4/9` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: call ratio of the tree arms | `2.2`, `2.4` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: wall-clock ratio of the tree arms | `2.3`, `2.9` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: token ratio of the tree arms | `1.85` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `unknown` |
| R3, unclaimed failures delivered by both tree arms | `52` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `unknown` |
| R3, unclaimed runs the leaf passed | `39` | `docs/2_GOAL.md#r3-decomposition-and-multi-approach` | `unknown` |
| R2, design: arms, repeats, runs | `5`, `3`, `600` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, bootstrap resamples | `10000` | `bench/analysis/wave1/r2/analysis.txt:1` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, A0 development only: runs solved | `70/120` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_arm_dev_only` |
| R2, A1 own test: runs solved | `66/120` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_arm_own_test` |
| R2, A2 own test + independent test: runs solved | `65/120` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_arm_own_iv` |
| R2, A3 own test + review: runs solved | `71/120` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_arm_own_review` |
| R2, A4 full: runs solved | `77/120` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_arm_full` |
| R2, claimed runs per arm | `0`, `1`, `54`, `28` | `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, false successes per arm | `0`, `10`, `1` | `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, calls per task per arm | `1.01`, `5.54`, `6.63`, `9.13`, `12.86` | `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, tokens per task per arm | `1198`, `8480`, `10570`, `12696`, `18894` | `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, own-test contrast: delta, interval, p | `-1.33`, `[-5.67, +3.00]`, `0.549` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, review without independent test: false-success delta, interval, p | `+3.33`, `[+1.00, +6.33]`, `0.031` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, review with independent test: correctness delta | `+4.00` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_full_minus_own_iv_correctness` |
| R2, review with independent test: correctness interval | `[+1.33, +7.00]` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_full_minus_own_iv_ci` |
| R2, review with independent test: correctness p | `0.012` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_full_minus_own_iv_p` |
| R2, independent test with review present: correctness delta, interval, p | `+2.00`, `[-0.67, +4.67]`, `0.388` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, independent test with review present: claim delta | `-8.67` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_full_minus_own_review_claimed` |
| R2, independent test with review present: claim p | `0.0009` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, independent test with review present: false-success delta, interval and p | `-3.00`, `[-5.67, -1.00]`, `0.031` | `docs/2_GOAL.md#r2-verification-information` | `python3 reproduce.py r2_full_minus_own_review_false` |
| R2, independent test withheld approval: runs and grader passes | `92/110`, `57` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, full stack minus development only: delta, interval, p | `+2.33`, `[-0.33, +5.33]`, `0.34` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, own-test loop cost multiples: tokens, wall | `7`, `6.6` | `docs/2_GOAL.md#r2-verification-information` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| cost, ours: tokens per task | `18.9k` | `docs/8_DETAIL.md#cost` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| cost, baseline: tokens per task | `9k` | `docs/8_DETAIL.md#cost` | `unknown` |
| the baseline's per-turn output cap, tokens | `8192` | `bench/pi_baseline.py:71` | `unknown` |
| cost, single-lane wall subset: tasks, ours, baseline | `8`, `31.0`, `47.5` | `docs/8_DETAIL.md#cost` | `unknown` |
| retracted token headline | `-31.3%` | `docs/8_DETAIL.md#cost` | `unknown` |

## The unknowns, and how each gap would be closed

- **R1 starting position** (`24/40`, `27/40`): measured on the earlier revision `6b224f5`,
  whose rows are not in the projection. It is a historical fact, cited to the record that
  states it, and not re-derived here.
- **The interval-width quantities are no longer in this list**: `r1_half_width`,
  `r1_width_n17`, `r1_width_n25`, `r1_width_min`, `r1_within_share_pct`,
  `r1_asymptotic_width` and `r1_needed_estimate` are printed by `python3 reproduce.py`, derived
  by `bench/analysis/wave1/n25/interval_widths.py` from the projection, recorded in
  `bench/analysis/wave1/n25/interval-widths.json`, and checked digit for digit against the
  sentence that states them (`docs/2_GOAL.md#r1-capability-parity`) on every run.
- **The short-input trap** (`0.06`, `[-3.35, 3.71]`, `680`): the entry point refuses a starved
  input instead of reproducing the wrong experiment (`reproduce.py:116`), so the trap's numbers
  are quoted from the traceability table and are not a reproduced output.
- **R3 token ratio** (`1.85`): the tree arms wrote no trajectory file, so their token counts
  were never captured (`bench/analysis/wave1/r3/supp-r3.txt:48`); the ratio is a lower bound
  recorded in the campaign, not a computed ratio.
- **R3 unclaimed failures** (`52`, `39`): produced by the final-revision audit that
  `docs/2_GOAL.md#r3-decomposition-and-multi-approach` cites for its code and byte evidence; that audit's inputs are not in the
  committed projection, so the record of the two counts is the audit and not a command in this
  repository.
- **cost, baseline tokens per task** (`9k`): the baseline's driver carries no token counters
  (`docs/8_DETAIL.md#cost`), so the figure comes from the recorded reference and is not
  recomputable from the final rows.
- **the baseline's per-turn output cap** (`8192`): a configuration constant in the driver that
  produced the baseline rows, not a measurement. The code is its own evidence
  (`bench/pi_baseline.py:71`); no command derives it, and no record counts how many baseline runs
  ended on it.
- **cost, single-lane wall subset** (`8` tasks, `31.0`, `47.5` s/task): the arms were not
  measured under the same concurrency (`docs/8_DETAIL.md#cost`), so the subset is indicative and
  the clean comparison is outstanding (`docs/8_DETAIL.md#cost`).
- **retracted headline** (`-31.3%`): a dead claim. It is kept as a number because the
  retraction is evidence; it did not reproduce (`docs/8_DETAIL.md#cost`), and no command produces
  it.

## The nine negative-result rows of §6

The campaign-wave numbers in these rows are measured, recorded, and **not** re-derived from the
committed projection: their rows live in the secured home, whose recompute commands are the
campaign's per-wave drivers, not the three analyzers the entry point runs.

| Number | Value | Source | Command |
| --- | --- | --- | --- |
| a bounded source index: harmful | `13/24`, `18/24` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| a bounded source index: against the pre-change revision | `13/24`, `19/24` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| forcing a deterministic file-change order: harmful | `14/15`, `7/15` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| a knowledge pack per call: no gain | `4/15`, `3/15` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| module importers in the write spec: no gain | `10/15` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| extending the write boundary on rule evidence: no gain | `1/5` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| competitive approach exploration: cost multiple | `2.2`, `2.4` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| competitive approach exploration: runs solved | `15/70`, `47/70` | `docs/8_DETAIL.md#negative-results` | `unknown` |
| asking the baseline to write and run its own tests: worse at small context | `16/40`, `21/40` | `docs/8_DETAIL.md#negative-results` | `unknown` |

## What the check script does with this file

`docs/paper/check_citations.py` re-reads every row of both tables, resolves every `Source` cell,
confirms that each value in the `Value` cell appears on at least one of the cited lines, and
confirms that each `Command` cell is a printed key, the bare entry point, or a command recorded
in the traceability table. It counts `unknown` rows separately and fails only when a row is
malformed or a citation does not resolve.
