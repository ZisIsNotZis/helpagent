# 02 — M1 + corpus growth + M2 core (owner granted full autonomous authority)

Owner authorization: "我将全权授权给你这个项目的推进……自动管理你的 subagents，直到
要么已经达成的阶段性目标，要么遇到重要决策需要我停下来做。" Interim: no user input.

## Stage goal (stop-and-report when reached)
1. **M1** — real model runner (LlamaServerRunner, protocol parity with FakeModelRunner),
   json_schema grammar per step type (sentinel translation aligned with §0 — K's risk note),
   best-of-N (first-valid selection for M1), KV-cache hit tracking (timings.cache_n/prompt_n
   → ledger), tree-sitter parse-on-arrival + bounded respawn with broken excerpt (DESIGN §4.7),
   integration tests against live server :8833 (marked slow, outside the unit gate).
2. **Corpus ≥10** — DONE (a4dbb51): T-05..T-10 landed, 10 tasks total. Owner-session
   independent spot-verification: all 6 red (exit 1), T-06+T-09 solutions green in /tmp
   copies, corruption catch live (T-05, then restored), leak scan clean, T-01..T-04 untouched.
3. **M2 core** — artifact store + tree.attach (closes TEST_PLAN §3.1 producer-linkage +
   size-cap tests), trajectory per-step git snapshots (closes §3.8 user-edit-conflict test),
   boot_recover.
4. **Numbers** — N=5 real-model runs over the corpus through the M1 runner: pass rate,
   calls/tokens/wall distributions, cache-hit rate, FAIL_PATTERNS entries.

## Deps added (design-mandated, per DESIGN §4.7 tree-sitter)
tree-sitter 0.26.0, tree-sitter-python 0.25.0 (owner pre-approved via design docs; same
treatment as pydantic/pytest). Nothing beyond the design's own stack.

## Agent assignments (disjoint file ownership)
- Agent M1: `harness/model.py`, `harness/repair.py`, `harness/runner.py` (context/repair
  glue), `tests/unit/`, `tests/integration/`. NOT tree.py, NOT bench/.
- Agent CORPUS: `bench/corpus/T-0[5-9]`, `T-10` only. No installs.
- Main session: reviews, gates, all commits, M2 agent afterwards, final numbers + report.

## Deviations / decisions log
- (will fill)
