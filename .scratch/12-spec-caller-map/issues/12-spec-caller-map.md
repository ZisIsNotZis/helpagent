# 12 — Caller coverage at spec composition

Status: done
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: In T-31, some model specs name only transport.py, omitting client/service/exporter. Once the spec boundary is narrow, later import/caller injection at implementation cannot safely widen it. Forced write order (ticket 11) regressed and was removed.

Objective: Experimental `--spec-callers` injects a bounded, deterministic direct module-importer map into write_spec only. The map excludes tests and never grants write permission itself; the model's spec still decides files_touched within the existing repo boundary. No extra model calls or attempts. Default flow unchanged.

Acceptance: AST map tests (T-31, T-33, excluded tests, syntax/cycles), spec composition test; frozen same-model N=5 per arm on T-31/T-33/T-02. Record spec coverage, pass rate, crashes, model calls and controls. If quality fails to improve or controls regress, remove variant. Preserve compact evidence and restore clean tree.

- 2026-09-28 agent: started from clean `b2dfe17`; ticket 11 rejected forced order (T-31 4/5→1/5; T-33 5/5→2/5). This experiment moves only information timing, not edit control.
- 2026-09-28 agent: frozen `f9d4242`, N=5 each on T-02/T-31/T-33. Baseline 10/15 (5/5,0/5,5/5); import-map 10/15 (4/5,1/5,5/5), one map-arm T-02 CRASH before spec. T-31 spec named all four required source files only 1/5 baseline vs 2/5 map; not a reliable coverage uplift. Model calls 173 baseline vs 141 map, but early failure and variable budgets confound any cost interpretation. Evidence: `evidence/{baseline,map}-{summary,results}.json`, per-run T31 summaries/logs, `t02-crash.txt`, compressed sweep output. KILLED: one extra T-31 pass cannot justify a default injection; experimental flag/code/tests reverted.
- 2026-09-28 agent: the T-02 crash is unrelated to spec map (occurred in expand before write_spec). A nested `ChildFill` omitted required `why` but Pydantic allowed the REQUIRED sentinel, then `TaskTree.insert_ticket` raised ValidationError. Fixed earliest at ChildFill validation and guarded top-level unable task_card/expand statuses with shaped failure persistence. Regression tests added.
- 2026-09-28 agent: first post-strict smoke on T-02 N=3 was 0/3 (two shaped `expand failed`, one persistent `SchemaViolation`) because the model routinely omits `seam_id` despite only one harness candidate. Diagnosed from ledger. Added parameter-layer normalization ONLY for the single-candidate case with a `tolerance_fired` counter; ambiguous multiple candidates still reject. Second real-model T-02 smoke: 2/3 PASS, zero crashes; both PASS runs recorded the seam_id tolerance event. Third failure was a legal `task_card.status=failed` shaped failure before expand, not a crash. Evidence: `strict-*`, `tolerant-*` files. Full unit suite and `git diff --check` pass. Residual: this is not a restored 3/3 reliability claim; rerun a broader tiered sample before asserting no regression. Default caller-map code has been byte-restored to pre-experiment behavior; only safety/normalization fixes remain.
