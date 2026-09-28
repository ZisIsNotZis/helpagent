# 08 — Iterate state contract

Status: claimed
Need-review: yes
Need-test-cases: yes

Issue: The unified iteration claim in DESIGN §2.4 was not implemented at the composer boundary: `step_implement` retained edits on disk, but `current_files` and optional knowledge injection were built from the original corpus `files` dictionary. Also `tiered.run_gear` still passed the removed `accumulate` keyword, causing gear 0/1 to fail and silently escalate. The previous iterate A/B therefore does not establish the claimed effect; withdraw its causal verdict.

Objective: For every attempt, inject the exact current staged file bytes (including earlier accepted edits), restore all touched files on exhausted budget, and run tiered gear 0/1 without an obsolete argument. Add narrow regression tests. Rerun checks and relevant A/B with equal budgets before making any performance claim.

Blockers: none. Do not mutate the tree during benchmark runs.

- 2026-09-20 agent: inspected commit c451c76, reproduced defects by code path; implementation and tests in progress. Prior 4/18→6/18 statement is confounded and is not accepted evidence for iteration.
