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
