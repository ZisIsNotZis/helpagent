# 07-corpus-30

**Status:** done
**Milestone:** DESIGN §8 M5 — Corpus (30 tasks) + scoring + cost metrics + FAIL_PATTERNS loop

## Delivered (2026-09-17 owner session)

1. **Corpus 15 -> 30** (bench/corpus, 4-entry anatomy per bench/corpus/README.md):
   - T-16..T-20 (bugfix): class-state-leak, log-hour-format, env-config-precedence,
     slug-separator, average-truncation
   - T-21..T-25 (bugfix + add-feature): swallowed-corruption, case-sort-order,
     stack-is-empty, json-report-flag, chunked-helper
   - T-26..T-30 (port + scaffold + bugfix): plan-dataclass-port, snakecase-ingest,
     plugin-registry-scaffold, prerelease-version-parsing, naive-datetime-compare
   - Every task red->green machine-verified at authoring time (tmp-copy pytest:
     red exit!=0 broken, green exit==0 fixed); class mix now covers bugfix /
     add-feature / port / scaffold.
2. **Scoring + cost metrics** (bench/score.py, commit 5ed9ea3): DESIGN §6 rubric
   (correctness-first overall; verification/safety/stopping components), Wilson
   95% CI per task, §9.10 multiplier vs M0 (calls per PASS / 1.0 by-construction
   baseline, documented). Dual-lane wall: llm_invocation now carries wall_model_s.
3. **FAIL_PATTERNS loop**: operating since ticket 02 (FP-1..FP-8; 6 closed, 2
   open), now gated by score.py CIs.

## Discipline notes

- Authoring generators lived in /tmp (corpus keeps exactly 4 entries per task).
- Incident recorded: T-11..T-14 CRASH in the 065457Z sweep were caused by the
  owner session mutating the working tree mid-sweep — sweeps now run only
  against a committed, frozen tree.
- Seed-bug authoring caught by the machine check twice (T-24 escape-newline,
  T-29/T-27/T-30 broken-vs-test mismatches) — the red->green gate is load-bearing.

## Progress log (append-only)

- 2026-09-17 owner session: batches 1-3 landed (5ed9ea3, then corpus commits);
  M5 capstone N=3 sweep launched on the frozen tree.

- 2026-09-17 owner session (closure): first N=3 (100148Z, with FP-9/FP-10 defects)
  = 64/93 [0.588, 0.773], multiplier 8.3; three zero-call infra crashes diagnosed
  (grounding/style-rule false positives) -> FP-9/FP-10 closed (d31ac30).
  FINAL N=3 (120220Z, fixed tree): **69/93 (74.2%) [0.645, 0.82]**, multiplier 8.4
  calls/PASS, zero crashes. Directly-fixed tasks all 3/3 (T-06/T-12/T-17/T-20).
  Aggregate delta not CI-separated (overlap) — within-task movement is the signal;
  frontier cluster (T-18/24/26/27/28 at 0/3, model-content side) feeds M9
  skeleton/guided experiments (ticket 05 family). M5 = delivered.
