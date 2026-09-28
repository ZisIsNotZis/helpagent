# 09 — Overall quality confirmation

Status: claimed
Need-review: yes
Need-test-cases: no (measurement on existing red→green corpus)

Issue: Ticket 08 corrected the staged-draft contract; a four-task N=3 comparison (8/12 vs 9/12) cannot establish overall quality. Historical tiered 97/120 at `bench/runs/tiered-20260918T080505` predates the corrected implementation and is only a reference, not an equal-condition control.

Objective: Run the frozen current revision on all 40 tasks (35 local + 5 external anchors), N=3, using the reference Spark-X2.5-4B model. Report total, three strata, closing gears, crashes, and material regressions versus the historical run. Validate the result file against actual rows, inspect failure patterns, and distinguish evidence from causal inference. Preserve compact evidence and park or fix any newly discovered system defect before accepting the quality claim.

Blockers: none initially. Freeze the work tree while the model sweep runs. Budget: local inference, one serialized server and sweep, bounded runtime.

- 2026-09-28 agent: starting from clean `64323cb`; baseline historical 97/120 overall, 84/90 local 30. Unit suite 147/147 and ticket 08 targeted comparison passed. No performance uplift was established by that smaller comparison.
