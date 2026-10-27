# bench/projection — the campaign rows a reader can carry

Kind: authored document, owner: the M1 node. It describes `bench/projection/wave1/`, the
committed projection that lets `python3 reproduce.py` recompute every decisive number of the
preprint from the repository alone. The 2 GB campaign home `bench/runs/wave1/` (untracked,
`/tmp/wave1` before it) is not needed by that command and is not read by it.

## What a projection row is

A row is the campaign's own row with every field no analyzer reads removed, one JSON object per
line, at the path the analyzer resolves it to. So `bench/projection/wave1/final/` mirrors the
home's layout and the campaign's scripts run unmodified: R1 has its four roots repointed, R2
takes a `--glob`, R3 takes `R3=`, and `supp.py`'s one hardcoded root line is replaced — nothing
else in any analyzer changes.

| rows | files | rows in the home | rows here | fields kept |
| --- | --- | --- | --- | --- |
| R1 `our-n5`, `n9`, `n17`, `n25`, `pi-n9`, `pi-extra` | 172 | 2000 | 2000 | `task`, `run_idx`, `actual`, `claimed`, `total_tokens`, `run_wall_s`, `wall_s` |
| R2 `r2/runs/c{1..4}/<arm>/<arm>`, 5 arms | 20 | 600 | 600 | `task`, `arm`, `run_idx`, `actual`, `claimed`, `false_success`, `quadrant`, `total_tokens`, `model_calls`, `run_wall_s`, `claimed_basis`, `self_test`, `stop_reason`, `independent_test_reason`, `iv_verdicts` (reduced to `approved`), `review_verdicts` (reduced to truthiness) |
| R3 `r3/<arm>/<task>-<seed>/run.json`, 3 arms | 210 | 210 | 210 | `task`, `actual`, `claimed`, `calls`, `run_wall_s`, `nodes` (reduced to `candidates[].how_case`, `allocation.forced`, `children`) |
| R3 `trajectory.jsonl` presence markers | 70 | 70 | 70 | none — empty files, see below |

`run_idx` is kept though only R1's readers filter on it: it is the row's identity, and without
it the row count per seed is the only thing tying a projection file to the home file it came
from.

## Dropped, and why that is safe

The home is 2 GB because each row also carries `verification`, `ledger`, `coverage`,
`request_coverage`, `attempts`, `judge_verdicts`, `iv_verdicts` at full length, the embedded
test sources (`independent_test`, `own_test_*`), `goal`, `acs`, `withheld_grader_paths`,
`grader_*`, `produced`/`applied`/`skipped` and the 200 KB `trajectory.jsonl` transcript per
run. No analyzer in `bench/analysis/wave1/` reads any of them; each one is a record of *why* a
row came out the way it did, and each stays in the home, under the manifest, for a reader who
follows a single run back to its provenance.

Two reductions deserve their own line because they are not deletions:

- `iv_verdicts` keeps one boolean per verdict (`approved`). `r2_analyze.py` reads the list for
  truthiness and then for `all(v.get("approved"))`; the reasons and details are not read.
- `review_verdicts` becomes a boolean. It is read only for truthiness, by the same function.

A `trajectory.jsonl` is committed as a **zero-byte presence marker** where the campaign wrote
one (all 70 `leaf` runs, no tree run). `r3/analyze.py` counts `(ROOT/arm).glob("*/trajectory.jsonl")`
and never opens the file, so an empty file carries the whole fact that line needs. It is not a
transcript and must not be read as one.

## Size

`du -sb bench/projection/wave1` and `tar czf - bench/projection/wave1 | wc -c` are the two
numbers to quote; they are measured in the M1 handover rather than stored here, so they cannot
drift from the tree.

## Rebuild and check

Both commands need the untracked home, so they are maintainer recipes, not part of `reproduce`:

    python3 bench/projection/build_projection.py           # rewrite bench/projection/wave1/
    python3 bench/projection/build_projection.py --check   # rebuild into a temp dir, diff every file

`reproduce.py` does not verify this tree against the home; it verifies the tree's *output*
against the records the campaign committed (`bench/analysis/wave1/{n25,r2,r3}/`), which is the
stronger claim and the one a reader without the home can check.

## What this projection cannot show

The rows are evidence that the analyzers were fed the campaign's values; they are not the
campaign's trace of how each value was produced. A reader who wants to know why
`T-31-parameter-threading` fell from `1.00` under `leaf` to `0.00` under `tree-greedy` needs the
home (or `bench/analysis/wave1/r3/supp-r3.txt` and `docs/2_GOAL.md`). That boundary is
the paper's own boundary section, not a gap in the projection.
