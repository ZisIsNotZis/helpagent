# 06-parameter-layer-tolerance

**Status:** done
**Policy:** DESIGN §4.7 "Tolerant at the parameter layer, strict at the logic layer"
(owner directive 2026-09-17: intent-legible small errors — arg names, enum
near-misses — get deterministic correction; logic errors are never guessed).

## Delivered (commit 5765658)

- `harness/normalize.py`: ENUM_CANONICALS + ENUM_ALIASES (status / check_kind /
  task_class), recursive payload walk, whitespace fold, case-fold of canonical
  values themselves, never-guess-past-parameters invariant.
- Hooked in `runner.llm_step` before schema validation; every fire ledgered as
  `tolerance_fired{step_type, field, from, to}`.
- Tests (9): fold/alias/nested/no-op/unknown-rejected/end-to-end + schema
  drift guard (canonicals must equal the schema Literals).
- Evidence for first aliases: `check_kind="REQUIRED"` echo seen in run
  20260917T063255 (T-01 resample).

## Progress log (append-only)

- 2026-09-17 owner session: policy recorded in DESIGN §4.7; implemented, tested
  (130/130 suite), committed. New aliases enter ONLY with a run reference.
