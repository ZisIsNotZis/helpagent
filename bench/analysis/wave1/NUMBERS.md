# Numbers and how to get them back

Every decisive number the paper will quote, the command that recomputes it, and the line that
command must print. All commands run from the repository root; none starts a model and none
opens a network. This file is the one home for the number → command mapping; the paper's
reproduce section and `AGENTS.md` point here rather than restating it.

## One command (the form the paper quotes)

    python3 reproduce.py

It runs the campaign's own analyzers over the committed projection
`bench/projection/wave1/final/` — 472 files, 2 810 rows, 523 499 bytes (57 561 gzipped), cut
from the 62 MiB of inputs the analyzers read out of the home. It needs no `/tmp`, no model
server, no network, and not the untracked 2 GB home; it prints one `key value` line per number
below and exits 0 only when every value equals the record committed beside its analyzer. A
missing record, a zero-row record or a short sample stops it with a named line before any number
is printed (`bench/projection/README.md` says what a projection row is, and what it cannot show).

Rebuilding the projection from the home is a maintainer recipe, not part of the reproduce path:
`python3 bench/projection/build_projection.py --check`. The per-analyzer commands below remain
the deeper form, for reading how one number is computed rather than for checking it.

## Verified from the home

Each row's `reproduce.py` key is the one the paper quotes; the command in the middle column is
the same computation without the entry point.

| number, where it is quoted | `reproduce.py` key | command | expected |
| --- | --- | --- | --- |
| R1 `24.640` vs `24.960`, delta `−0.320`, CI `[−3.520, +3.080]` (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`, `docs/2_GOAL.md#r1-capability-parity`) | `r1_a_mean_tasks`, `r1_b_mean_tasks`, `r1_delta_tasks`, `r1_lo95`, `r1_hi95`, `r1_rows_per_arm` | `python3 bench/analysis/wave1/recompute_n25.py` | `rows per arm from the home: 1000` and five `ok` lines, `a_mean_tasks +24.640`, `b_mean_tasks +24.960`, `delta_tasks -0.320`, `lo95 -3.520`, `hi95 +3.080` |
| R2 arm table, stage contributions, quadrants, cost (`docs/2_GOAL.md#r2-verification-information`) | `r2_arm_*`, `r2_full_minus_own_iv_*`, `r2_full_minus_own_review_*` | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl' --out /tmp/r2.json --text /tmp/r2.txt && diff /tmp/r2.txt bench/analysis/wave1/r2/analysis.txt` | `diff` empty — the recomputed text is byte-identical to the record committed beside it |
| R2 the same in JSON (compared parsed, not byte-wise — see the limitations below) | — | `diff <(python3 -m json.tool /tmp/r2.json) <(python3 -m json.tool bench/analysis/wave1/r2/analysis.json)` | `diff` empty |
| R3 `leaf 47/70` vs `tree-greedy 14/70` vs `tree-tournament 15/70`, McNemar `p ≤ 0.001`, per-corpus-item deltas (`docs/2_GOAL.md#r3-decomposition-and-multi-approach`) | `r3_leaf`, `r3_tree_greedy`, `r3_tree_tournament` | `H=$(pwd)/bench/runs/wave1/final/r3; sed "s|/tmp/wave1/final/r3|$H|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py \| diff - bench/analysis/wave1/r3/supp-r3.txt` | `diff` empty — line 42 reads `leaf runs=70 actual=47/70 claimed=8/70 false_success=0 …` |
| R3 arm calls and wall-clock, decomposition-fired counts, per-item rates (`docs/2_GOAL.md#r3-decomposition-and-multi-approach`) | `r3_leaf_mean_calls`, `r3_tree_greedy_mean_calls` | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py \| diff - bench/analysis/wave1/r3/analysis-r3.txt` | `diff` empty — `leaf runs=70 mean_calls=14.4 mean_wall_s=175`, `tree-greedy … mean_calls=31.6 mean_wall_s=408` |
| the copy itself, all 53 270 files | — | `python3 bench/analysis/wave1/verify_home.py` | `ok 53270  mismatch 0  missing 0  analysis-copies-ok 36  analysis-copies-bad 0`, exit 0 |

`sed` is needed in the R3 `supp.py` line because that script hardcodes `/tmp/wave1/final/r3`;
`reproduce.py` replaces that one literal under an exactly-once assertion, so the deeper form
below still shows the literal.

## Not verified from the home

These are quoted in `docs/2_GOAL.md` and their inputs are in the secured home, but no command
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

## Recorded limitations of the reproduce path

- `analysis.json`'s `stop_reasons` orders ties by set-iteration order, so a fresh run can differ
  from the recorded file under some `PYTHONHASHSEED` values while matching under others. The
  entry point therefore compares R2's text **bytes** and its JSON **parsed**; no printed number
  depends on the ordering. This is a gap in byte-identity, not in the arithmetic, and it is
  recorded rather than smoothed over.
- `r3/supp.py` hardcodes `/tmp/wave1/final/r3` on line 7; the entry point replaces that one
  literal and asserts the replacement matched exactly once, so a future edit stops the run with
  `unreadable input:` instead of silently reading `/tmp`.
- The projection proves the analyzers were fed the campaign's values. It does not carry why a
  row came out as it did — the transcript, ledger and test source of a single run stay in the
  home under `bench/manifests/wave1.sha256`, and a reader following one number back to its
  provenance needs that home.

## The trap this table exists to prevent

`analyze_n25.py` reads four roots (`our-n5`, `n9`, `n17`, `n25`) and `read_jsonl` returns `[]`
for a path that is not there. With `n17` missing it prints `delta +0.06`, `CI [−3.35, +3.71]`
over 680 rows instead of `−0.320` / `[−3.520, +3.080]` over 1000, and raises nothing. So a short
home does not fail loudly, it reports a different experiment — and that difference is the
headline. Any recompute must assert its row count before it asserts anything else.

## The same analyzers over the committed projection (no home needed)

The preprint's appendix points at these, so a reader on a clean clone can re-derive every row
without the 2 GB home. Each is the analyzer above with its input repointed at
`bench/projection/wave1/final/`; each prints or diffs to the same bytes as its home run, because
the projection carries every field the analyzers read (`bench/projection/README.md`). Verified
2026-10-23: `analyze.py` and `supp.py` diff empty against `analysis-r3.txt` / `supp-r3.txt`, and
`r2_analyze.py` diffs empty against `analysis.txt`.

```
R3=bench/projection/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py
H=$(pwd)/bench/projection/wave1/final/r3; sed "s|/tmp/wave1/final/r3|$H|" bench/analysis/wave1/r3/supp.py > /tmp/supp_home.py && python3 /tmp/supp_home.py | diff - bench/analysis/wave1/r3/supp-r3.txt
python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/projection/wave1/final/r2/runs/*/*/*/results.jsonl'
```

`python3 bench/analysis/wave1/recompute_n25.py` stays home-based: it asserts its row counts
before it compares, so a short home stops it instead of reporting another experiment.
