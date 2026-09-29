# 13 — Signature-arity rule family for threaded parameters

Status: done
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: T-31 map-arm failures show repeated `TypeError: send()/fetch()/sync_record() got an unexpected keyword argument 'timeout'` while the model re-emitted the named file without adding the parameter (or added it without threading). The FP-4 rule library covers NameError/ImportError only; signature mismatch produces no deterministic diagnosis, so retries carried failing test ids but no actionable line.

Objective: Extend `diagnose_test_output` with a bounded deterministic rule: for `TypeError: <name>() got an unexpected keyword argument '<kw>'` (and missing-required-argument forms), locate the `def <name>` in repo files and inject "add/accept `<kw>` in <rel>'s <name> signature; callers passing it also need it in their signature" when the caller is a repo function. No model calls added; no boundary widening. Then real-model rerun of T-31 plus T-33/T-02 controls at equal budgets.

Acceptance: unit tests for the rule (kwarg and missing-arg, resolution across files, no false fire on unrelated TypeErrors); frozen N=5 golden A/B on T-31/T-33/T-02; zero-crash requirement; adopt only if T-31 improves without control regressions; otherwise revert rule and record. Preserve compact evidence; restore clean tree.

- 2026-09-28 agent: started from clean `6a82c9b`. Diagnosis above cites evidence in ticket 12 (`evidence/map/T31-*.txt.gz`); shaped excerpts verified to include the E-lines, and the rule library returned `[]` for them. Rule shipped at `21d25d7`; full unit suite green.
- 2026-09-29 agent: frozen 21d25d7, same reference model. Golden N=5: **12/15** — T-31 **3/5** (prior equal-budget baseline 0/5 and 1/5 across tickets 11/12), T-02 5/5, T-33 4/5 (baseline 5/5; one-run wobble). Tiered N=3: 7/9 — T-31 1/3, controls 3/3 each, zero error rows in both runs. The rule demonstrably FIRES (ledger `rule_diagnosis arity-signature-thread`: 6–17 fires per T-31 run) and turning prior silent TypeErrors into pointed signature+caller instructions is the first intervention with a visible T-31 movement at equal budget. Evidence: `evidence/*-{golden-n5,tiered-n3}*`, compressed run log.
- 2026-09-29 agent: adoption verdict: **KEEP the rule** (kernel rule library is the designed home for such deterministic diagnoses; FP family closed). It does NOT establish solved status: T-31 3/5 still varies with spec coverage (both failures again narrowed files_touched to transport-only), so remaining variance is spec-side. Controls: T-33 4/5 vs 5/5 baseline is one-run sampling; no evidence of rule-caused regression (rule never fired on T-33 files; verified via T-33 ledgers having zero arity fires). Scoped self-review: rule is bounded, deterministic, fires only on typed signature mismatches with a repo `def`, never widens boundary; false-positive risk limited to same-name different-function collisions (none in corpus). Residual: sample sizes remain N=5; spec-side omission is the next diagnosis target if T-31 work continues.
