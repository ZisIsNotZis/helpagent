# Measurement tooling (bench/v2_measure.py)

`bench/v2_measure.py` measures the v2 leaf arm and prints it beside the pi reference on
the same tasks. It adds measurement only: every run goes through
`bench.v2_leaf.run_once`, and claims still come from the one `claim_decision` gate.

## Commands

Multi-seed arm (mean + spread; `--n 3` repeats each task, default `--n` is 3):

```bash
uv run python bench/v2_measure.py \
  --tasks T-01-ttl-seconds-ms,T-02-off-by-one --n 3 \
  --server http://127.0.0.1:8834
```

Stage ablation (`--ablate` takes a comma-separated list of arms), single-lane wall-clock
cost, and the full 40-task ablation switch:

```bash
uv run python bench/v2_measure.py --tasks T-01-ttl-seconds-ms --ablate review
uv run python bench/v2_measure.py --tasks T-01-ttl-seconds-ms --wall-clock
uv run python bench/v2_measure.py --tasks all --ablate none,own-test,independent-test,review --n 3
```

Outputs land in `bench/runs/measure-<utc>/`: per-arm `results.jsonl` + `summary.json`,
plus `summary.json`, `merged.json`, `merged.md`. The merged table is also printed.

## What each switch disables

`--verify` (values come from `harness.leaf.VERIFICATION_MODES`; the mode table is in the
module docstring and mirrored by `VERIFY_MODE_STAGES`):

| `--verify` | own-test | independent-test | review |
| --- | --- | --- | --- |
| `full` | on | on | on |
| `test` | on | OFF | OFF |
| `review` | OFF | OFF | on |
| `raw` | OFF | OFF | OFF |

`--ablate` names ONE stage and leaves the rest of the full pipeline intact:

| `--ablate` | verify | judge | independent-test | review | disabled stages |
| --- | --- | --- | --- | --- | --- |
| `none` | full | on | on | on | — |
| `independent-test` | full | on | OFF | on | independent-test only |
| `review` | full | on | on | OFF | review only |
| `own-test` | raw | off | OFF | OFF | own-test, independent-test, review |

`independent-test` and `review` are clean single-stage ablations. `own-test` is coupled:
the leaf derives its self-test loop from `verification_mode`
(`run_self_test = mode in ("full", "test")`), so the only selector that skips the own
test is `raw`, which also drops the independent test, the review and the claim gate.
A single-stage own-test ablation would need a new mode in `harness/leaf.py`, which is
outside this task's authorized edit set (`bench/` and `tests/unit/` only). If you want
own-test off while the graded-review loop keeps running, use `--verify review` (it also
drops the independent test). The driver prints and records the disabled set per arm
(`summary["arm"]["disabled"]`) so the coupling is never implicit.

## Cost and variance

- `seconds/task` is the whole-run wall time (`run_wall_s`), and `tokens/task` sums the
  server's `prompt_tokens` + `completion_tokens` over every `model_call` in the run's
  `trajectory.jsonl` (cached prefixes included, as the server counted them).
- `--wall-clock` runs ONE sequential pass per task (`n=1`; this driver never uses
  concurrency) for the honest single-lane cost.
- Each arm reports a per-run rate plus sample spread (`sd`) and the spread of per-task
  rates (`task_rate_sd`) for actual / claimed / false-success; a one-seed arm reports
  `sd=0.0` rather than a fabricated error bar.
- pi reference: `bench/runs/evidence/pi-maxed-20261006/<band>/results.jsonl`, N=1 per
  task; a task measured in two bands keeps the later band (A-01), matching
  `tests/unit/test_pi_maxed_evidence.py`.

## Evidence from the initial run

- Server `http://127.0.0.1:8834` healthy (`{"status":"ok"}`).
- `--tasks T-04-missing-default,T-07-f-string-sql --wall-clock`: 2 tasks, 1 seed, one
  lane, `lane_wall_s=48.5`; merged table printed with the pi rows.
- `--tasks T-04-missing-default --n 3 --ablate none,independent-test`: 6 runs; `none`
  claimed 3/3 (sd 0.000), `independent-test` claimed 2/3 (sd 0.577) with iv off,
  actual 3/3 both arms.
- `uv run pytest -q -p no:warnings` green, including 15 new cases in
  `tests/unit/test_v2_measure.py`.
