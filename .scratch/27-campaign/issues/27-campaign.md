# 27 — the campaign (owner mandate 2026-10-06, full delegation)

Owner: "you are fully delegated; manage and orchestrate; let the workers do the concrete work;
don't stop until the research is finished; I only want the final result."

## Success criteria (from README "Objective")

1. pure coding >= pi with maxed knobs (same model), and better in wall/tokens;
2. tests/reviews carry information (fix the mechanism, the prompt or the injection — trajectory
   first, find the exact deviation point);
3. every unsolved task has a specific evidenced reason; everything else passes (target 100%);
4. structural superiority proven: work that prompting alone cannot get out of pi;
5. efficiency measured (ours vs pi baseline AND prompt-improved).

## Phases

| # | phase | deliverable | state |
| --- | --- | --- | --- |
| P1 | flow v3 core: one runner, no write refusals (allow + record + restore), regression stage, three-state/How terminal semantics, best-of propagation | code + tests + T-01/T-28/T-31 re-runs | TODO |
| P2 | node structure v3 (what/reason/hows + four lists per How + children) + exploration (read) + triage into issues | code + tests + 40-task re-run | TODO |
| P3 | make verification meaningful: trajectory forensics per failure, fix tests/reviews/prompts/injection | per-task deviation reports + fixes | TODO |
| P4 | pi parity: baseline, prompt-improved, thinking on/off for ours; tokens + wall; structural-superiority cases | comparison table + evidence | TODO |
| P5 | drive the residual to zero: every remaining failure carries an evidenced "impossible for this model" | STATUS.md final position | TODO |

Discipline: one writer per work tree; every phase re-measures against the REAL model; numbers are
retracted and re-measured after any flow change; each phase leaves its evidence in this directory.

## P1a + P1b landed (verified by the orchestrator)

- P1a write policy: off-plan writes LAND, are recorded as deviations (`WriteDeviation`,
  `write_deviation` telemetry, `Attempt.deviations`, `LeafOutcome.deviations`), and are restored on
  the produced repo before grading (`bench/blind_run.restore_deviations`, called before
  `external_score`). Only the mechanical shape refusal remains. Verified: the test suite is green
  (exit 0) and the restore call precedes the grader.
- P1b regression stage: `harness/regression.py` captures the visible suite before the first write
  and re-runs it on the final revision; `regressions` blocks the claim on every leaf route and
  drives another iteration. Unobservable is never treated as clean.

### Finding F1 (for P2/P3): on THIS corpus the regression stage is mostly unobservable

Each task's `repo/tests/` IS the grader's suite, and the blind protocol withholds it, so the staged
view usually contains NO visible test file: `capture_baseline` returns `observable=False` and the
regression check is skipped. So on these 40 tasks "no regression" still rests on the external
grader's own suite (which is the real regression oracle) plus our tests/reviews. The regression
stage becomes load-bearing only for a repo that ships its OWN visible tests alongside a hidden
grader suite — i.e. a realism gap in the corpus, to be closed when the corpus grows (a visible
smoke suite per task, plus the hidden grading suite).

### P1c was re-cut

The one-runner lane timed out with NO tracked file changed (it read only). It is split:
- P1c-1 (now): three states + How terminal semantics + best-of propagation, inside the outcomes.
- P1c-2 (into P2): the sweep drives the unified tree runner, because P2 changes the node structure
  the runner consumes anyway.
