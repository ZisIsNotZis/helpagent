# 09 — Overall quality confirmation

Status: done
Need-review: yes (fresh scoped self-review completed)
Need-test-cases: yes (AC-unavailable regression tests and real-model rerun)

Issue: Ticket 08 corrected the staged-draft contract; a four-task N=3 comparison (8/12 vs 9/12) cannot establish overall quality. Historical tiered 97/120 at `bench/runs/tiered-20260918T080505` predates the corrected implementation and is only a reference, not an equal-condition control.

Objective: Run the frozen current revision on all 40 tasks (35 local + 5 external anchors), N=3, using the reference Spark-X2.5-4B model. Report total, three strata, closing gears, crashes, and material regressions versus the historical run. Validate the result file against actual rows, inspect failure patterns, and distinguish evidence from causal inference. Preserve compact evidence and park or fix any newly discovered system defect before accepting the quality claim.

Blockers: none initially. Freeze the work tree while the model sweep runs. Budget: local inference, one serialized server and sweep, bounded runtime.

- 2026-09-28 agent: starting from clean `64323cb`; baseline historical 97/120 overall, 84/90 local 30. Unit suite 147/147 and ticket 08 targeted comparison passed. No performance uplift was established by that smaller comparison.
- 2026-09-28 agent: frozen `936ffaf` full N=3 sweep `bench/runs/tiered-20260928T030215`: 97/120; local 83/90, hard 8/15, anchors 6/15, closing gear 0/1/2 = 91/5/1. Historical = 97/120; 84/90, 6/15, 7/15; 92/3/2. Four run rows contained errors (A-01 once, A-04 three times), so total score alone masked a reliability defect. Raw summary/results and full log copied to `evidence/`.
- 2026-09-28 agent: A-04 `draft_acs` returned a legal `unable` envelope; `step_acs` iterated its sentinel payload and crashed. A-01 had a persistent schema violation after retry. Both now become explicit `ac_map_unavailable` FAIL with persisted summary and ledger, without bypassing mandatory leaf AC map. Narrow regression tests added. A-03 emitted an asyncio event-loop-close warning without a counted crash; track separately if it recurs.
- 2026-09-28 agent: focused real-model rerun on `5d446e3` for A-01/A-04, forced gear 2, N=3: 3/6 PASS (A-01 3/3, A-04 0/3), **zero error rows**; one A-04 run took the shaped AC-unavailable path and persisted a failure summary, the other two failed ordinary tests. Evidence in `evidence/ac-regression-*`. This is failure shaping, not a claim that A-04 is solved.
- 2026-09-28 agent: result rows independently reaggregated (120 distinct full rows, 6 distinct focused rows; summaries match; full errors=4, focused errors=0). `uv run pytest -q` 150/150, `git diff --check` clean. Fresh scoped self-review: status guard precedes sentinel iteration; unrecoverable AC-map failure records ledger+summary and stops before implementation, preserving mandatory leaf map; subsequent valid AC map still proceeds. Historical comparison is descriptive only (different revisions and random draws), not a causal A/B. Residual: full 40-task N=3 run applies to `936ffaf`, focused crash fix to `5d446e3`; Pydantic REQUIRED-sentinel serialization warnings and A-03 asyncio shutdown warning are observed but not shown to change score. Follow-up if they recur: isolate warning-producing envelope/transport path and add narrow tests.
