# 24 — the mature-agent baseline (what does a real agent CLI do with the same small model?)

Status: done (commit 1b600e5)
Owner question (asked twice): "did you run this under pi / a mature agent bare, and what
was the result?"

## Method

`bench/pi_baseline.py` runs the REAL `pi` CLI headless (`--mode json`, `--no-session`,
`--thinking off`, `--provider local` pointed at the same llama-server) against a corpus
task, with:

- the same blind staging as the harness (source-only; the corpus tests and `checks.py`
  never enter the run);
- a TEMP pi agent directory (`PI_CODING_AGENT_DIR`) holding only the `local` provider in
  `models.json`, so the owner's real pi configuration is never read or written;
- the same external grader (`bench/external_score.py`) and the same quadrant function, so
  the numbers are comparable;
- a behavioural trace: turns, tool calls by name, every shell command, files touched,
  whether it wrote a test or ran pytest, and its final message.

A bwrap sandbox confines the run (host read-only, only the run root writable) when bwrap is
available.

## Result (same 4B model, three tasks)

| agent | T-02 | T-05 | T-31 | actual | claimed |
| --- | --- | --- | --- | --- | --- |
| our harness (newest sweep, N=2) | 2/2 | 1/2 | 0/2 | 3/6 | 0/6 |
| pi CLI (2 passes, 1 run each) | 1/2 | 1/2 | 2/2 | 4/6 | 4/6 |
| our minimal agent loop (bench/v2_agent.py) | - | - | - | 0/6 | n/a |

Behaviourally: pi drives a real tool loop AND runs shell commands every run - what our
minimal loop could not do. It wrote NO test, because the 4B could not emit a whole test file
as a tool argument (output-token limit; the write failed). Its dominant failure mode is
structural: pi ends the run when the model returns an assistant message with no tool call,
which the 4B does prematurely (turn 4 / turn 8); a one-shot headless run has no user turn to
say "continue", so an unfinished task simply ends. That explains the run-to-run variance
(3/3 versus 1/3).

## What it does and does not show

Shows: on a small model, a mature agent CLI's loop is at least as good as our harness on the
grader's verdict for these tasks, and it claims far more (it has no claim gate; its "claims"
are our reading of its prose). Our harness's contribution is therefore NOT "it fixes more
easy tasks" - it is the blind scoring protocol, the deterministic gates, the auditable
evidence trail, and the structural layers (trees, budgets, escalation) that a one-shot CLI
run does not attempt.

Does not show: a general rate (three tasks, one or two passes each), and the comparison is
not apples-to-apples (pi has no call budget, no honesty gates, no evidence ledger; the
harness caps calls and refuses unverified claims).

## Follow-up worth doing (not done)

The same-model comparison suggests the harness's 24-call budget and its red-independent-test
gate are conservative relative to what the model can do under a free-running loop. A
controlled experiment (same tasks, harness with a much larger budget and/or the red-IV gate
relaxed to a label) would separate "the gate costs fixes" from "the gate costs only claims".
