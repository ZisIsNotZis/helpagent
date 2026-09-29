# 14 — Evidence-gated boundary completion

Status: claimed
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: T-31 residual failures are spec-side: files_touched narrows to transport-only while tests demand threading through client/service/exporter. Ticket 13's arity rule now names the defining file, but the implement loop refuses writes outside the spec boundary, so the diagnosis cannot be acted on.

Objective: Experimental `--boundary-completion` flag: when a rule-library finding points at a repo file OUTSIDE the current implement boundary, the harness adds that file to the allowed write set for subsequent attempts (one-way, evidence-gated, ledger-recorded as boundary_completion). No spec rewrite, no extra model calls, never adds test files, never exceeds the repo+creatable set. Default off.

Acceptance: unit tests (completion fires only on rule findings, excludes tests, one-way persistence, ledger note); frozen same-model A/B on T-31 N=5 golden vs ticket-13 baseline (3/5) with T-33/T-02 controls; zero crashes; adopt only on clear T-31 improvement without control regressions, else revert. Evidence preserved; tree clean.

- 2026-09-29 agent: starting from clean `3ecb1b8`. Ticket 13 evidence: rule fires but cannot act across the boundary.
