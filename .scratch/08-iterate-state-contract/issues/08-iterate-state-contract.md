# 08 — Iterate state contract

Status: done
Need-review: yes (fresh scoped self-review completed)
Need-test-cases: yes (three regression tests added)

Issue: The unified iteration claim in DESIGN §2.4 was not implemented at the composer boundary: `step_implement` retained edits on disk, but `current_files` and optional knowledge injection were built from the original corpus `files` dictionary. Also `tiered.run_gear` still passed the removed `accumulate` keyword, causing gear 0/1 to fail and silently escalate. The previous iterate A/B therefore does not establish the claimed effect; withdraw its causal verdict.

Objective: For every attempt, inject the exact current staged file bytes (including earlier accepted edits), restore all touched files on exhausted budget, and run tiered gear 0/1 without an obsolete argument. Add narrow regression tests. Rerun checks and relevant A/B with equal budgets before making any performance claim.

Blockers: none. Do not mutate the tree during benchmark runs.

- 2026-09-20 agent: inspected commit c451c76, reproduced defects by code path. Prior 4/18→6/18 statement is confounded and is not accepted evidence for iteration.
- 2026-09-28 agent: fixed both entry points in b532e96; `uv run pytest -q` 147/147 pass; `git diff --check` clean. Regressions assert the next prompt sees the staged draft, exhausted budget restores bytes, multi-file green retains all edits, and tiered gear 0 calls the current signature.
- 2026-09-28 agent: tiered N=1 smoke at `bench/runs/tiered-20260928T024004`: T-02 and T-33 both close in gear 0. Sequential same-model, same-budget N=3 comparison at old c451c76 (static snapshot) vs b532e96 (staged draft): old 8/12, new 9/12; T-02 2→3, T-16 3→3, T-18 0→0, T-33 3→3. Evidence: `evidence/{old,new}-{summary.json,results.jsonl}` and `evidence/tiered-smoke-summary.json`. A one-run difference with N=3 is noise, not an established success-rate improvement. The user-selected unified semantics is retained for correctness; no performance uplift claimed.
- 2026-09-28 agent: fresh scoped self-review of b532e96: staged snapshot is taken before each call; diagnoses read post-write state; failed strategy restores original bytes; retained edits enter untouched-file gate in both golden and tiered; tests cover boundary and regression. No blocking finding. Residual: broader quality impact remains unmeasured; T-18 still fails 0/3. DESIGN §2.4 causal claim weakened accordingly.
