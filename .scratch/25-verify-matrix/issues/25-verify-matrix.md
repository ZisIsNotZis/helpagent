# 25 — the development-vs-verification matrix, and the mature-agent comparison

Status: done (commits 4f1c4d4, 961f64a)
Trigger: the owner's question — "can our harness at least reach a normal agent loop's level,
and do our review/test mechanisms help? Quantify it on ALL tasks, not three."

## Method

Two additions made the matrix possible: a `--verify {raw,test,review,full}` selector on the
leaf driver (isolating which mechanism drives the loop) and `--ask-tests` on the pi baseline.
All arms: same 4B model, same llama-server, blind staging (source-only; the grader never
enters), the same external grader, all 40 tasks, N=1.

## Results (clean, commit 124c41d)

| arm | drives the loop | actual | claimed | FALSE | cost |
| --- | --- | --- | --- | --- | --- |
| harness `raw` | development only: no self-test, no independent test, no review, never claims | 21/40 (52%) | 0 | 0 | 1.1 calls, ~6 s |
| harness `test` | own test, red on arrival, iterate to green | 23/40 (58%) | 0 | 0 | 4.9 calls, ~28 s |
| harness `review` | graded review is the only feedback | 22/40 (55%) | 34 | 13 | 5.4 calls, ~18 s |
| harness `full` | default: all of it plus the deterministic gates | 20/33 (61%) | 12 | 2 | 10.2 calls, ~96 s |
| pi CLI | request only | 21/40 (52%) | 21 | 4 | ~8 turns, ~120 s |
| pi CLI + ask-tests | "write test files and run them" | 16/40 (40%) | 22 | 6 | ~8 turns, 90-160 s |
| `bench/v2_agent.py` | minimal loop, no feedback | 0/6 hard | - | - | - |

## Findings

1. **Development capability is a TIE with the mature CLI** (21/40 each) at about 1/20th the
   wall time. The harness's forced structure does not cost development power.
2. **The hard tail defeats every agent equally** (T-31's four-file threading, all five anchors,
   T-27/T-28/T-32/T-34): a model-capability boundary, not a harness defect.
3. **Our mechanisms add 6-9 points** over development-only, and the deterministic gates keep
   false successes at 1-2 where pi (no claim gate) certifies 4-6 wrong fixes.
4. **Asking a small model to write its own tests makes a mature CLI WORSE** (21 -> 16). The 4B
   cannot emit a whole test file as a tool argument (the write hits the output-token limit and
   is dropped), and it exhausts its context on the attempt: 9 of 10 runs in the last band ended
   on a length-truncated thinking block. Measured justification for keeping the harness's
   self-test optional and small-stepped, and for leaning on reviews.
5. **Review alone does not improve fixing** (22/40 vs 21/40 development-only) and its own
   verdicts were wrong 13 times out of 34 claims (38%). Its value is honest claiming, not
   correctness - which is why the deterministic gates sit next to it.

## Defects found and fixed by the measurement lanes

- **Cache leak (retracted the earlier matrix).** 12 of 40 task repos shipped `.pytest_cache`
  containing the grader's own test node ids; staging withheld only owned paths, so the run could
  read them (pi visibly did). Fixed in `harness/staging.py` (`cache_artifact`/`withheld_path`),
  caches deleted from the corpus, and two guards added (`124c41d`).
- **Unreadable produced file aborted the sweep** (a chmod-000 file a run's own test created);
  `produced_files` now skips it.
- **pytest tmp_path retention** (`pytest-of-*/**`) was being handed to the grader as a
  deliverable; now excluded.
