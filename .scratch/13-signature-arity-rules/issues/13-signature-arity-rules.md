# 13 — Signature-arity rule family for threaded parameters

Status: claimed
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: T-31 map-arm failures show repeated `TypeError: send()/fetch()/sync_record() got an unexpected keyword argument 'timeout'` while the model re-emitted the named file without adding the parameter (or added it without threading). The FP-4 rule library covers NameError/ImportError only; signature mismatch produces no deterministic diagnosis, so retries carried failing test ids but no actionable line.

Objective: Extend `diagnose_test_output` with a bounded deterministic rule: for `TypeError: <name>() got an unexpected keyword argument '<kw>'` (and missing-required-argument forms), locate the `def <name>` in repo files and inject "add/accept `<kw>` in <rel>'s <name> signature; callers passing it also need it in their signature" when the caller is a repo function. No model calls added; no boundary widening. Then real-model rerun of T-31 plus T-33/T-02 controls at equal budgets.

Acceptance: unit tests for the rule (kwarg and missing-arg, resolution across files, no false fire on unrelated TypeErrors); frozen N=5 golden A/B on T-31/T-33/T-02; zero-crash requirement; adopt only if T-31 improves without control regressions; otherwise revert rule and record. Preserve compact evidence; restore clean tree.

- 2026-09-28 agent: started from clean `6a82c9b`. Diagnosis above cites evidence in ticket 12 (`evidence/map/T31-*.txt.gz`); shaped excerpts verified to include the E-lines, and the rule library returns `[]` for them.
