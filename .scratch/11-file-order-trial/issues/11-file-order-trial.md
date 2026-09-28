# 11 — Dependency-order file trial

Status: claimed
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: T-31 passed once after four distinct edits in dependency order (transport → client → service → exporter), but failed in other runs; the model often repeats one file instead of covering the caller chain. The success is an observation, not proof of an ordering intervention.

Objective: Test an experimental, deterministic import-graph source-file sequence against unchanged golden flow on T-31, with T-33 and T-02 controls. Keep the same reference model, attempt budget, checks and test gate. Explicit `--ordered-files` only; shipped default unchanged. Sequence is derived from repository AST, never from the hidden solution/tests. Do not silently widen the write boundary or edit tests. On structural failure, retain existing free-choice behavior after one ordered pass.

Acceptance: narrow unit tests for graph order and bounded behavior; frozen N=5 per arm on three tasks with row reconciliation, crash count, attempt histograms, model-call cost where available; adopt only if T-31 improves meaningfully without control regressions or material cost. Else remove experiment flag and park with evidence.

- 2026-09-28 agent: clean start at `511da83`; T-31 success evidence in ticket 10. Implementation pending.
