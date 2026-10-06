# pi CLI, reasoning + big context (2026-10-06) — the fairness correction

## Why this run exists

The first mature-agent baseline (`docs/STATUS.md` section 8, commit `ef13a14`) ran the real `pi`
CLI against the same 40 corpus tasks with **two hidden ceilings**, discovered when the owner
asked whether the comparison was fair:

1. `--thinking off` — and, worse, **thinking could not have been on**: pi clamps the level to
   the levels the *model* advertises, and the temp model entry declared no reasoning support
   (`docs/rpc-commands.md`, "returns `["off"]` for a model without reasoning support"). The
   recorded runs therefore never used a reasoning budget at all.
2. the llama-server had **`-c 8192`**. In the recorded "pi + write tests" arm, 9 of 10 tail runs
   ended on a length-truncated thinking block, i.e. they stopped because they ran out of tokens.

Both ceilings are ours, not pi's. This directory is the re-measurement with them removed.

## The configuration actually used

| knob | recorded baseline (`ef13a14`) | this arm |
| --- | --- | --- |
| pi flags | `--mode json --no-session --no-approve --no-extensions --no-skills --no-prompt-templates --no-context-files` | identical |
| tools | pi defaults, unrestricted | identical |
| prompt | `PI_PROMPT` + the task's `request.md` verbatim | identical |
| `--thinking` | `off` (clamped; effectively the only level) | **`max`** |
| model entry | `{"id": "localhost"}` | **+ `"reasoning": true`, `contextWindow: 32768`, `maxTokens: 8192`** |
| server | `-c 8192` | **`-c 32768 --cache-type-k q8_0 --cache-type-v q8_0`** |
| model | Spark-X2.5-4B-Q4_K_M.gguf | identical |

Implemented by the `--reasoning` flag in `bench/pi_baseline.py` (default off, so the recorded
arms stay reproducible).

## Measured (all 40 tasks, N=1, same external grader, same blind staging)

| band | recorded, thinking≈off + 8k | this arm |
| --- | --- | --- |
| T-01..T-10 easy | 9/10 | **10/10** |
| T-11..T-20 middle | 7/10 | **9/10** |
| T-21..T-30 hard | 5/10 | **7/10** |
| T-31..T-35 tail | 0/5 | **1/5** (T-31) |
| A-01..A-05 anchors | 0/5 | **0/5** |
| **total** | **21/40 (52%)**, 25 claimed, 4 false | **27/40 (68%)**, 29 claimed, **2 false** |

Mean cost: 131 s and 8.9 turns per task (recorded arm: ~142 s, 7.4 turns).

On the 33 tasks the harness `--verify full` arm also ran: pi here is **22/33 (67%)** versus the
harness's recorded 20/33 (61%). pi-only wins: T-01, T-12, T-28, T-31. Harness-only wins: T-33,
T-35.

Still failing in this arm: T-13, T-24, T-26, T-27, T-32, T-33, T-34, T-35, A-01..A-05.

## What it means (and what it retracts)

- The claim "development capability is a TIE" in section 8 of `docs/STATUS.md` is **retracted**:
  it was measured against a pi that had its reasoning budget clamped off and only 8k of context.
  Configured properly, pi is stronger than that record showed.
- The claim that the hard tail "defeats both equally, therefore it is a model-capability
  boundary" is **partly retracted**: T-31 (four-file parameter threading) is fixed by the same
  4B once the loop has room to iterate (49 s, 9 turns). "Long agent sequences" were throttled by
  our server, not by the model's ceiling.
- The anchor band **is** unaffected (0/5 both ways) and the failure *shape* is informative: A-03
  burned 238 s in a single turn with zero tool calls, A-05 207 s in one turn with zero tool
  calls — the whole budget went into a thinking block that was then truncated. A-02 still
  certified a wrong fix ("The implementation is complete and verified."). Reasoning budget is not
  a substitute for being able to write a correct implementation.

## Evidence layout

- `<band>/results.jsonl` — one row per task as measured (task, claimed, actual, quadrant,
  wall_s, turns, tool_calls, timed_out, wrote_test, ran_pytest, final_text, grader_notes).
- `<band>/summary.json` — the driver's own tally for that band.
- `<band>/<task>-1.rec.json` — the full per-task record (prompt, staging, produced files,
  tool-call summary, final assistant text).
- bands: `easy` (T-01..T-10), `mid1` (T-11..T-20), `mid2` (T-21..T-30), `tail` (T-31..T-35,
  the 1700 s cap ended this band early), `anchors` (A-01..A-05).

**A-01 was measured twice** (the capped `tail` band reached it before the cap, then the
`anchors` band measured it again) and both rows are kept: tail spent 145 s and 10 turns, anchors
88 s and 3 turns, and both failed. The 40-task tally uses the later row; the spread is why a
single N=1 number for one task should not be read as a rate.

`bench/runs/evidence/pi-maxed-20261006/` is tracked; the bulky per-task `events.jsonl`
streams (pi's `--mode json` trace, ~1.2 MB each) were left under `/tmp/pi-max-*` and are
regenerable from the commands below.

## Reproduce

```bash
# big-context server (same weights, 32k window)
llama-server -m <Spark-X2.5-4B-Q4_K_M.gguf> --port 8834 --host 127.0.0.1 \
  -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0

# one band, maxed config
uv run python bench/pi_baseline.py \
  --tasks T-01-ttl-seconds-ms,... \
  --base-url http://127.0.0.1:8834/v1 --thinking max --reasoning --out /tmp/pi-max-easy
```
