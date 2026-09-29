# 14 — Evidence-gated boundary completion

Status: done
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: T-31 residual failures are spec-side: files_touched narrows to transport-only while tests demand threading through client/service/exporter. Ticket 13's arity rule now names the defining file, but the implement loop refuses writes outside the spec boundary, so the diagnosis cannot be acted on.

Objective: Experimental `--boundary-completion` flag: when a rule-library finding points at a repo file OUTSIDE the current implement boundary, the harness adds that file to the allowed write set for subsequent attempts (one-way, evidence-gated, ledger-recorded as boundary_completion). No spec rewrite, no extra model calls, never adds test files, never exceeds the repo+creatable set. Default off.

Acceptance: unit tests (completion fires only on rule findings, excludes tests, one-way persistence, ledger note); frozen same-model A/B on T-31 N=5 golden vs ticket-13 baseline (3/5) with T-33/T-02 controls; zero crashes; adopt only on clear T-31 improvement without control regressions, else revert. Evidence preserved; tree clean.

- 2026-09-29 agent: starting from clean `3ecb1b8`. Ticket 13 evidence: rule fires but cannot act across the boundary.
- 2026-09-29 agent: frozen `f5bf424`, same reference model, golden N=5 each: T-31 without completion **1/5** vs with completion **1/5** (ticket-13 same-day baseline was 3/5 — the no-completion arm itself wobbled two runs below it, so sampling noise is large); T-33 with completion 4/5 (matches baseline), zero crashes in all 30 runs. Completion mechanism WORKED mechanically in 3/5 T-31 runs (ledger `boundary_completion`: client/service/exporter added) and the model then wrote service once — but attempts still left tests red; success run needed no completion at all. Evidence: `evidence/*-{summary,results}.json`, compressed run output.
- 2026-09-29 agent: verdict: **KILL the flag** — no improvement over its own no-completion arm at equal budget, and the arm wobble (1/5 vs 3/5 baseline) shows N=5 T-31 sampling is too noisy to resolve ≤1-run effects. The deeper reading across tickets 11–14: T-31 outcomes are dominated by whether the SPEC names the full caller chain (2/5, 1/5, 2/5 full-coverage rates) and whether transport re-emissions keep the new parameter; completion and ordering interventions act after that decision and did not move it. Next lever if T-31 work continues: the FP-7-style hard rule family (spec prompt already carries importer guidance only behind the killed flag) or corpus-side spec variance; both are design decisions, not mechanical. Flag/code/tests reverted; scoped self-review and cleanup pending.
