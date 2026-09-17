# 03-m3-check-pipeline

**Status:** claimed
**Milestone:** DESIGN §8 M3 — Check pipeline (format/lint/type/parse, auto-fix ≤2 passes, rollback)
**Contract:** KERNEL_API §3.4 `check_write`; DESIGN §4.5 ladder; TEST_PLAN §3.3 test matrix

## Objective

The kernel-owned write path: every work-tree mutation from model output goes through
one primitive that runs the check ladder, auto-fixes the trivial, and rolls back what
cannot stand. Reliability-first per owner decision 2026-09-17 (DESIGN §6): correctness
gates everything; cost only counts after it.

## Scope (v1 slice — each slice boundary recorded, none silent)

- Whole-file writes only (bounded-region stitching stays M9 file-splitting).
- Ladder stages: ruff format → ruff check --fix (**≤2 passes, survivor rule**) →
  tree-sitter parse (located excerpt; failure ⇒ rollback — parse repair belongs to the
  §4.7 generation-time path) → mypy project-wide with **finding-level baseline filter**
  (pre-write vs post-write diff; pre-existing untouched-file noise never blocks, a
  caller broken in an untouched file always survives) → rule library → intent tier-1
  (source-intent write into a test file ⇒ rollback: gate-easing is structurally suspect).
- **Scoped tests stay the script's stage** (golden pytest gate): check_write owns
  format/autofix/parse/type/rules; test policy (which suite is scoped) belongs to the
  script until the M4 session runner. The rule library therefore consumes test output
  via `diagnose_test_output(...)` called by the script after pytest.
- Trajectory snapshots stay caller-side until the M4 kernel loop owns the step loop.
- Rollback = byte-restore + ledger note (per-file restore is exact for whole-file v1;
  harness-git reset stays kernel-internal per KERNEL_API §4.5 DECISION).
- Early stats counters (owner alignment 2026-09-17): `check_verdict`,
  `write_committed`/`write_rolled_back`, `policy_blocked` (exec), `rule_diagnosis`.

## Dependencies (design-mandated, DESIGN §4.5 ladder — same treatment as tree-sitter, ticket 02)

ruff 0.16.8, mypy 2.3.1 via `uv add` (tsinghua index; PyPI direct remains unreliable,
WORKSPACE env-fact 2026-09-15 re-verified 2026-09-17: mirror works).

## Acceptance criteria

1. TEST_PLAN §3.3 matrix green: `autofix_stops_after_two_passes`,
   `tool_fight_oscillation_records_fail_pattern` (scripted fixer injection point),
   `unfixable_write_rolls_back_worktree`, `type_check_filters_at_finding_level`,
   `touched_files_only_scoping_is_rejected` (+ rule/intent/secret-filter cases).
2. Unit gate <10s CPU-only; full suite green.
3. Golden script end-to-end on mini_repo via real model (:8833): gate green, FP-4
   diagnosis now fires from the rule library (ledger shows `rule_diagnosis`).
4. Full-corpus sweep (real model): per-task parity with the N=3 sweep floor — no task
   regresses from PASS to FAIL when run through the check path.
5. Docs current: DESIGN §6 reliability-first line, §4.6 no-free-form-read rationale,
   TEST_PLAN path drift fixed.

## Progress log (append-only)

- 2026-09-17 owner session: ticket opened; doc-sync audit done (DESIGN/KERNEL_API/
  TEST_PLAN vs harness/ implementation); deps added; implementation started.
