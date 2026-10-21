# Every number in the draft, its source, and the command that re-derives it

One row per number. `Source` is a `file:line` in this repository (a cell may cite more than one
line); `Command` is one of four forms, and the choice of form is part of the claim:

1. **A printed key**, `python3 reproduce.py <key>` — the number is printed by the entry point,
   byte for byte.
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
| R1, ours: tasks solved per run | `24.640` | `docs/STATUS.md:44` | `python3 reproduce.py r1_a_mean_tasks` |
| R1, baseline: tasks solved per run | `24.960` | `docs/STATUS.md:44` | `python3 reproduce.py r1_b_mean_tasks` |
| R1, paired delta in tasks | `-0.320` | `docs/STATUS.md:48` | `python3 reproduce.py r1_delta_tasks` |
| R1, task-clustered 95% interval, low | `-3.520` | `docs/STATUS.md:49` | `python3 reproduce.py r1_lo95` |
| R1, task-clustered 95% interval, high | `3.080` | `docs/STATUS.md:49` | `python3 reproduce.py r1_hi95` |
| R1, interval level | `95` | `docs/STATUS.md:49` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, bootstrap resamples | `20000` | `docs/STATUS.md:50` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, bootstrap seed | `20261013` | `docs/STATUS.md:49` | `python3 bench/analysis/wave1/recompute_n25.py` |
| R1, margin of the pre-registered rule, tasks | `M=3` | `docs/STATUS.md:51` | `python3 reproduce.py` |
| R1, shortfall against the margin, tasks | `0.520` | `docs/STATUS.md:52` | `python3 reproduce.py r1_lo95` |
| R1, seeds per arm | `25` | `docs/STATUS.md:38` | `python3 reproduce.py` |
| R1, run rows per arm | `1000` | `docs/STATUS.md:38` | `python3 reproduce.py r1_rows_per_arm` |
| corpus size, tasks | `40` | `docs/STATUS.md:18` | `python3 reproduce.py` |
| R1, ours: runs solved | `616/1000` | `docs/STATUS.md:43` | `python3 reproduce.py` |
| R1, baseline: runs solved | `624/1000` | `docs/STATUS.md:43` | `python3 reproduce.py` |
| R1, ours: false successes | `22/1000` | `docs/STATUS.md:45` | `python3 reproduce.py` |
| R1, baseline: false successes | `61/1000` | `docs/STATUS.md:45` | `python3 reproduce.py` |
| R1, false-success difference, tasks | `-1.56` | `docs/STATUS.md:140` | `python3 reproduce.py` |
| R1, false-success difference, interval | `[-3.16, -0.20]` | `docs/STATUS.md:140` | `python3 reproduce.py` |
| R1 interval width: half-width, tasks | `3.3` | `docs/STATUS.md:57` | `unknown` |
| R1 interval width: full width at the frozen intermediate N | `6.53` | `docs/STATUS.md:58` | `unknown` |
| R1 interval width: full width at the final N | `6.60` | `docs/STATUS.md:58` | `unknown` |
| R1 interval width: seeds spanned by the flat range | `17`, `25` | `docs/STATUS.md:58` | `unknown` |
| R1 interval width: within-seed share of variance, percent | `8.7%` | `docs/STATUS.md:60` | `unknown` |
| R1 interval width: asymptotic projection, tasks | `6.3` | `docs/STATUS.md:60` | `unknown` |
| R1, point estimate needed for ACHIEVED, tasks | `0.3` | `docs/STATUS.md:61` | `unknown` |
| R1, starting position on the earlier revision | `24/40`, `27/40` | `docs/STATUS.md:64` | `unknown` |
| R1, the short-input trap: delta over a starved input | `0.06` | `bench/analysis/wave1/NUMBERS.md:76` | `unknown` |
| R1, the short-input trap: interval over a starved input | `[-3.35, 3.71]` | `bench/analysis/wave1/NUMBERS.md:76` | `unknown` |
| R1, the short-input trap: rows read | `680` | `bench/analysis/wave1/NUMBERS.md:76` | `unknown` |
| R3, leaf: runs solved | `47/70` | `docs/STATUS.md:109` | `python3 reproduce.py r3_leaf` |
| R3, tree-greedy: runs solved | `14/70` | `docs/STATUS.md:110` | `python3 reproduce.py r3_tree_greedy` |
| R3, tree-tournament: runs solved | `15/70` | `docs/STATUS.md:111` | `python3 reproduce.py r3_tree_tournament` |
| R3, claimed runs per arm | `8/70`, `18/70` | `docs/STATUS.md:109`, `docs/STATUS.md:111` | `H=$(pwd)/bench/runs/wave1/final/r3; sed "s\|/tmp/wave1/final/r3\|$H\|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` |
| R3, false successes per arm | `0`, `4`, `3` | `docs/STATUS.md:109`, `docs/STATUS.md:110`, `docs/STATUS.md:111` | `H=$(pwd)/bench/runs/wave1/final/r3; sed "s\|/tmp/wave1/final/r3\|$H\|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` |
| R3, leaf: mean calls per task | `14.4` | `docs/STATUS.md:109` | `python3 reproduce.py r3_leaf_mean_calls` |
| R3, tree-greedy: mean calls per task | `31.6` | `docs/STATUS.md:110` | `python3 reproduce.py r3_tree_greedy_mean_calls` |
| R3, tree-tournament: mean calls per task | `35.2` | `docs/STATUS.md:111` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, mean wall clock per run | `175`, `408`, `498` | `docs/STATUS.md:109`, `docs/STATUS.md:110`, `docs/STATUS.md:111` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, runs per arm | `70` | `docs/STATUS.md:104` | `python3 reproduce.py r3_leaf` |
| R3, design: tasks, arms, seeds, runs | `14`, `3`, `5`, `210` | `docs/STATUS.md:104` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on decomposable tasks: mean delta | `-0.444` | `docs/STATUS.md:117` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on decomposable tasks: interval | `[-0.733, -0.178]` | `docs/STATUS.md:117` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-only and leaf-only fixes, decomposable | `0`, `20` | `docs/STATUS.md:117` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on forced-leaf tasks: mean delta | `-0.520` | `docs/STATUS.md:118` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-greedy vs leaf on forced-leaf tasks: interval | `[-0.920, -0.120]` | `docs/STATUS.md:118` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-only and leaf-only fixes, forced-leaf | `1`, `14` | `docs/STATUS.md:118` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: mean delta | `-0.422` | `docs/STATUS.md:119` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: interval | `[-0.689, -0.178]` | `docs/STATUS.md:119` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on decomposable tasks: tree-only and leaf-only fixes | `2`, `21` | `docs/STATUS.md:119` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, tree-tournament vs leaf on forced-leaf tasks: interval | `[-0.800, -0.240]` | `docs/STATUS.md:120` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, exact McNemar p, four comparisons | `0.000`, `0.001` | `docs/STATUS.md:117`, `docs/STATUS.md:118` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: greedy, runs | `3/70` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: greedy, decomposable tasks | `3/9` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: tournament, runs | `9/70` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, decomposition fired: tournament, decomposable tasks | `4/9` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: call ratio of the tree arms | `2.2`, `2.4` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: wall-clock ratio of the tree arms | `2.3`, `2.9` | `docs/STATUS.md:122` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| R3, cost: token ratio of the tree arms | `1.85` | `docs/STATUS.md:122` | `unknown` |
| R3, unclaimed failures delivered by both tree arms | `52` | `docs/STATUS.md:123` | `unknown` |
| R3, unclaimed runs the leaf passed | `39` | `docs/STATUS.md:123` | `unknown` |
| R2, design: arms, repeats, runs | `5`, `3`, `600` | `docs/STATUS.md:74` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, bootstrap resamples | `10000` | `bench/analysis/wave1/r2/analysis.txt:1` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, A0 development only: runs solved | `70/120` | `docs/STATUS.md:79` | `python3 reproduce.py r2_arm_dev_only` |
| R2, A1 own test: runs solved | `66/120` | `docs/STATUS.md:80` | `python3 reproduce.py r2_arm_own_test` |
| R2, A2 own test + independent test: runs solved | `65/120` | `docs/STATUS.md:81` | `python3 reproduce.py r2_arm_own_iv` |
| R2, A3 own test + review: runs solved | `71/120` | `docs/STATUS.md:82` | `python3 reproduce.py r2_arm_own_review` |
| R2, A4 full: runs solved | `77/120` | `docs/STATUS.md:83` | `python3 reproduce.py r2_arm_full` |
| R2, claimed runs per arm | `0`, `1`, `54`, `28` | `docs/STATUS.md:79`, `docs/STATUS.md:81`, `docs/STATUS.md:82`, `docs/STATUS.md:83` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, false successes per arm | `0`, `10`, `1` | `docs/STATUS.md:79`, `docs/STATUS.md:82`, `docs/STATUS.md:83` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, calls per task per arm | `1.01`, `5.54`, `6.63`, `9.13`, `12.86` | `docs/STATUS.md:79`, `docs/STATUS.md:80`, `docs/STATUS.md:81`, `docs/STATUS.md:82`, `docs/STATUS.md:83` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, tokens per task per arm | `1198`, `8480`, `10570`, `12696`, `18894` | `docs/STATUS.md:79`, `docs/STATUS.md:80`, `docs/STATUS.md:81`, `docs/STATUS.md:82`, `docs/STATUS.md:83` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, own-test contrast: delta, interval, p | `-1.33`, `[-5.67, +3.00]`, `0.549` | `docs/STATUS.md:89` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, review without independent test: false-success delta, interval, p | `+3.33`, `[+1.00, +6.33]`, `0.031` | `docs/STATUS.md:91` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, review with independent test: correctness delta | `+4.00` | `docs/STATUS.md:92` | `python3 reproduce.py r2_full_minus_own_iv_correctness` |
| R2, review with independent test: correctness interval | `[+1.33, +7.00]` | `docs/STATUS.md:92` | `python3 reproduce.py r2_full_minus_own_iv_ci` |
| R2, review with independent test: correctness p | `0.012` | `docs/STATUS.md:92` | `python3 reproduce.py r2_full_minus_own_iv_p` |
| R2, independent test with review present: correctness delta, interval, p | `+2.00`, `[-0.67, +4.67]`, `0.388` | `docs/STATUS.md:93` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, independent test with review present: claim delta | `-8.67` | `docs/STATUS.md:98` | `python3 reproduce.py r2_full_minus_own_review_claimed` |
| R2, independent test with review present: claim p | `0.0009` | `docs/STATUS.md:98` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, independent test with review present: false-success delta and interval | `-3.00`, `[-5.67, -1.00]` | `docs/STATUS.md:98` | `python3 reproduce.py r2_full_minus_own_review_false` |
| R2, independent test withheld approval: runs and grader passes | `92/110`, `57` | `docs/STATUS.md:98` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, full stack minus development only: delta, interval, p | `+2.33`, `[-0.33, +5.33]`, `0.34` | `docs/STATUS.md:100` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| R2, own-test loop cost multiples: tokens, wall | `7`, `6.6` | `docs/STATUS.md:97` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| cost, ours: tokens per task | `18.9k` | `docs/STATUS.md:127` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` |
| cost, baseline: tokens per task | `9k` | `docs/STATUS.md:127` | `unknown` |
| cost, single-lane wall subset: tasks, ours, baseline | `8`, `31.0`, `47.5` | `docs/STATUS.md:133` | `unknown` |
| retracted token headline | `-31.3%` | `docs/STATUS.md:136` | `unknown` |

## The unknowns, and how each gap would be closed

- **R1 interval-width projection** (`3.3`, `6.53`, `6.60`, `8.7%`, `6.3`, `0.3`, `17`..`25`):
  the sentence is generated into the campaign's own renderer
  (`bench/analysis/wave1/n25/assemble.py:55`) at campaign time, and the per-N interval widths
  are not a field of any committed record. To close it, the widths for each N would have to be
  computed from the per-seed totals in `bench/analysis/wave1/n25/analysis-n25-final.json:14` and
  committed as a record beside the analyzer.
- **R1 starting position** (`24/40`, `27/40`): measured on the earlier revision `6b224f5`,
  whose rows are not in the projection. It is a historical fact, cited to the record that
  states it, and not re-derived here.
- **The short-input trap** (`0.06`, `[-3.35, 3.71]`, `680`): the entry point refuses a starved
  input instead of reproducing the wrong experiment (`reproduce.py:116`), so the trap's numbers
  are quoted from the traceability table and are not a reproduced output.
- **R3 token ratio** (`1.85`): the tree arms wrote no trajectory file, so their token counts
  were never captured (`bench/analysis/wave1/r3/supp-r3.txt:48`); the ratio is a lower bound
  recorded in the campaign, not a computed ratio.
- **R3 unclaimed failures** (`52`, `39`): produced by the final-revision audit that
  `docs/STATUS.md:123` cites for its code and byte evidence; that audit's inputs are not in the
  committed projection, so the record of the two counts is the audit and not a command in this
  repository.
- **cost, baseline tokens per task** (`9k`): the baseline's driver carries no token counters
  (`docs/STATUS.md:128`), so the figure comes from the recorded reference and is not
  recomputable from the final rows.
- **cost, single-lane wall subset** (`8` tasks, `31.0`, `47.5` s/task): the arms were not
  measured under the same concurrency (`docs/STATUS.md:131`), so the subset is indicative and
  the clean comparison is outstanding (`docs/STATUS.md:134`).
- **retracted headline** (`-31.3%`): a dead claim. It is kept as a number because the
  retraction is evidence; it did not reproduce (`docs/STATUS.md:136`), and no command produces
  it.

## The nine negative-result rows of §6

The campaign-wave numbers in these rows are measured, recorded, and **not** re-derived from the
committed projection: their rows live in the secured home, whose recompute commands are the
campaign's per-wave drivers, not the three analyzers the entry point runs.

| Number | Value | Source | Command |
| --- | --- | --- | --- |
| a bounded source index: harmful | `13/24`, `18/24` | `docs/STATUS.md:181` | `unknown` |
| a bounded source index: against the pre-change revision | `13/24`, `19/24` | `docs/STATUS.md:181` | `unknown` |
| forcing a deterministic file-change order: harmful | `14/15`, `7/15` | `docs/STATUS.md:178` | `unknown` |
| a knowledge pack per call: no gain | `4/15`, `3/15` | `docs/STATUS.md:176` | `unknown` |
| module importers in the write spec: no gain | `10/15` | `docs/STATUS.md:177` | `unknown` |
| extending the write boundary on rule evidence: no gain | `1/5` | `docs/STATUS.md:179` | `unknown` |
| competitive approach exploration: cost multiple | `2.2`, `2.4` | `docs/STATUS.md:180` | `unknown` |
| competitive approach exploration: runs solved | `15/70`, `47/70` | `docs/STATUS.md:180` | `unknown` |
| asking the baseline to write and run its own tests: worse at small context | `16/40`, `21/40` | `docs/STATUS.md:182` | `unknown` |

## What the check script does with this file

`docs/paper/check_citations.py` re-reads every row of both tables, resolves every `Source` cell,
confirms that each value in the `Value` cell appears on at least one of the cited lines, and
confirms that each `Command` cell is a printed key, the bare entry point, or a command recorded
in the traceability table. It counts `unknown` rows separately and fails only when a row is
malformed or a citation does not resolve.
