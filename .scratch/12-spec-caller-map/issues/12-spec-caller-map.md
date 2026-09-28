# 12 — Caller coverage at spec composition

Status: claimed
Owner: agent
Need-review: yes
Need-test-cases: yes

Issue: In T-31, some model specs name only transport.py, omitting client/service/exporter. Once the spec boundary is narrow, later import/caller injection at implementation cannot safely widen it. Forced write order (ticket 11) regressed and was removed.

Objective: Experimental `--spec-callers` injects a bounded, deterministic direct module-importer map into write_spec only. The map excludes tests and never grants write permission itself; the model's spec still decides files_touched within the existing repo boundary. No extra model calls or attempts. Default flow unchanged.

Acceptance: AST map tests (T-31, T-33, excluded tests, syntax/cycles), spec composition test; frozen same-model N=5 per arm on T-31/T-33/T-02. Record spec coverage, pass rate, crashes, model calls and controls. If quality fails to improve or controls regress, remove variant. Preserve compact evidence and restore clean tree.

- 2026-09-28 agent: started from clean `b2dfe17`; ticket 11 rejected forced order (T-31 4/5→1/5; T-33 5/5→2/5). This experiment moves only information timing, not edit control.
