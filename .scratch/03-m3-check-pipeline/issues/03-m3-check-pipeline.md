# 03-m3-check-pipeline

**Status:** done
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

- 2026-09-17 owner session (cont.): M3 implemented + wired + committed (396e816).
  - `harness/checks.py`: check_write ladder, survivor rule (pass-0 inventory +
    re-appearance detector ⇒ tool_fight FAIL_PATTERN note), byte-restore rollback,
    intent tier-1, secret-filtered diff; mypy baseline filter = finding-level
    (pre-write project run diffed against post-write; 2× mypy cost accepted as the
    price of sound scoping — DECISION recorded in module docstring).
  - Tests: 17 new (tests/unit/test_checks.py) — TEST_PLAN §3.3 matrix + rules +
    intent + secret filter. Full suite 108/108 green.
  - `harness/exec.py`: policy_blocked ledger counter (early stats counters per
    2026-09-17 owner alignment).
  - Golden wired: implement + write_test writes ride check_write (intent
    source/test); inline FP-4 NameError grep REPLACED by kernel rule library
    (diagnose_test_output → note rule_diagnosis).
  - Real-model smoke mini_repo: PASS; ledger shows `check_verdict escalated
    (2 fix passes)` → `rule_diagnosis FP-4-nameerror-source → minirepo/errors.py`
    → retry `clean` → gate green. Rule library is now the FP-4 fix layer.
  - Full-corpus N=1 sweep launched (bg task b78987ff1) — parity evidence pending.

- 2026-09-17 owner session (closure): full-corpus N=1 sweep THROUGH the M3 pipeline:
  **15/16** (bench/runs/n-sweep-20260917T061549Z). Sole failure T-01 = pre-existing
  flake, model-side (all 3 attempts `write_committed`, pytest red — no ladder
  interference; resample 20260917T063255 confirms; class diagnosed → FP-7, ticket 04).
  T-07 (the other baseline flake) passed 1/1. Walls 39–102 s/task incl. 2× mypy.
  ACs: (1) §3.3 matrix green ✓ (2) unit gate 108/108 ✓ (3) mini_repo real-model gate
  green + rule_diagnosis ledger evidence ✓ (4) corpus parity ✓ (T-01 variance
  unchanged, no regression elsewhere) (5) docs current ✓ (DESIGN §2.7/§4.6,
  TEST_PLAN paths, FAIL_PATTERNS FP-4 fix layer + FP-7 entry).
  Status → done. New work: FP-7 → ticket 04 (needs-triage).

- 2026-09-17 owner session (M4 extension, same ticket umbrella): M4 core delivered
  (commit e6cdbea) — `harness/tools.py` registry (pytest/ruff/mypy/git shapers,
  generic fallback; `python -m X` dispatch form) + REAL bwrap sandbox for
  model-provenance exec: ro base + tmpfs /etc,/home,/run,/var,/tmp (path-level
  scoping — /etc hidden, not merely denied), rw workdir, venv re-bound, net+pid
  namespaces denied, `--die-with-parent`; kernel invariant: model-provenance exec
  NEVER runs unsandboxed (bwrap missing ⇒ policy_blocked). Shaping keys on the
  model's argv, not the sandbox argv. 121/121 suite; T-02 real-model PASS through
  the full stack. TEST_PLAN §3.2 path-scoping + network tests now real.
