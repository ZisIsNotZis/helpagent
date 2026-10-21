# Numbers and how to get them back

Every decisive number the paper will quote, the command that recomputes it from the declared
home `bench/runs/wave1/`, and the line that command must print. All commands run from the
repository root and start no model and no network. This is the seed of the preprint's reproduce
section, not that section: it covers what has been re-derived from the secured bytes, and it
names what has not.

## Verified from the home

| number, where it is quoted | command | expected |
| --- | --- | --- |
| R1 `24.640` vs `24.960`, delta `−0.320`, CI `[−3.520, +3.080]` (`docs/STATUS.md` §2–§3, `docs/paper-plan.md:17`) | `python3 bench/analysis/wave1/recompute_n25.py` | `rows per arm from the home: 1000` and five `ok` lines, `a_mean_tasks +24.640`, `b_mean_tasks +24.960`, `delta_tasks -0.320`, `lo95 -3.520`, `hi95 +3.080` |
| R2 arm table, stage contributions, quadrants, cost (`docs/STATUS.md` §4–§5) | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl' --out /tmp/r2.json --text /tmp/r2.txt && diff /tmp/r2.txt bench/analysis/wave1/r2/analysis.txt` | `diff` empty — the recomputed text is byte-identical to the record committed beside it |
| R2 the same in JSON | `diff <(python3 -m json.tool /tmp/r2.json) <(python3 -m json.tool bench/analysis/wave1/r2/analysis.json)` | `diff` empty |
| R3 `leaf 47/70` vs `tree-greedy 14/70` vs `tree-tournament 15/70`, McNemar `p ≤ 0.001`, per-corpus-item deltas (`docs/STATUS.md` §2, §5) | `H=$(pwd)/bench/runs/wave1/final/r3; sed "s|/tmp/wave1/final/r3|$H|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` | `diff` empty — line 42 reads `leaf runs=70 actual=47/70 claimed=8/70 false_success=0 …` |
| R3 arm calls and wall-clock, decomposition-fired counts, per-item rates (`docs/STATUS.md` §5) | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py \| diff - bench/analysis/wave1/r3/analysis-r3.txt` | `diff` empty — `leaf runs=70 mean_calls=14.4 mean_wall_s=175`, `tree-greedy … mean_calls=31.6 mean_wall_s=408` |
| the copy itself, all 53 270 files | `python3 bench/analysis/wave1/verify_home.py` | `ok 53270  mismatch 0  missing 0  analysis-copies-ok 36  analysis-copies-bad 0`, exit 0 |

`sed` is needed in the R3 `supp.py` line because that script hardcodes `/tmp/wave1/final/r3`
on line 7; rewriting it to take a path is part of the reproduce entry point, not of this table.

## Not verified from the home

These are quoted in `docs/STATUS.md` and their inputs are in the secured home, but no command
has been run this session that re-derives them from it. They are recorded as unknown, not as
fine.

- §6 tokens: `~18.9k` per corpus item for this harness against `~9k` for `pi`. Producer:
  `bench/analysis/wave1/n25/assemble.py` (and `render_tables.py` for the table form); its inputs
  are the per-run `results.jsonl` rows in the home. Not recomputed here.
- §6 wall-clock `2.2`–`2.4x` calls and `2.3`–`2.9x` wall: the arm table above carries those
  means (`14.4` vs `31.6`/`35.2` calls), so the ratio follows from the verified line, but the
  sentence's provenance in §6 has not been traced to it.
- §7 and the external-validity boundary: `pi`'s unmeasured token count, retained samples with
  length stops and context-size errors, unclean wall-clock. The rows exist under
  `bench/runs/wave1/final/{n17,pi-probe,our-wallclock}` and the bounded audit is
  `.scratch/29-close-audit/report.md`; no recompute command is pinned yet.

## The trap this table exists to prevent

`analyze_n25.py` reads four roots (`our-n5`, `n9`, `n17`, `n25`) and `read_jsonl` returns `[]`
for a path that is not there. With `n17` missing it prints `delta +0.06`, `CI [−3.35, +3.71]`
over 680 rows instead of `−0.320` / `[−3.520, +3.080]` over 1000, and raises nothing. So a short
home does not fail loudly, it reports a different experiment — and that difference is the
headline. Any recompute must assert its row count before it asserts anything else.
