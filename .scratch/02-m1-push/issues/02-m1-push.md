# 02 — M1 + corpus growth + M2 core (owner granted full autonomous authority)

Owner authorization: "我将全权授权给你这个项目的推进……自动管理你的 subagents，直到
要么已经达成的阶段性目标，要么遇到重要决策需要我停下来做。" Interim: no user input.

## Stage goal (stop-and-report when reached)
1. **M1** — DONE (d8fe22f). LlamaServerRunner (protocol parity, json_schema anyOf of two
   closed branches mirroring §0 — the prescribed fields-optional mapping was falsified by
   integration evidence and replaced citing §0's own words), best-of-N (sequential,
   KV-thrash rationale), TransportError ≠ SchemaViolation, tree-sitter repair (one bounded
   respawn, structural via repair=False), integration tests vs live server (3 passed),
   64 unit tests green.
   **Owner-verification findings (beyond the agent's own evidence):**
   - Agent's end-to-end demo (1/1) did NOT replicate under owner compositions: 0/3 —
     model consistently strips docstring quotes re-emitting a file seen in artifacts
     (temp 0.2 near-deterministic; all N candidates identical). best-of-N selection
     used schema validity only → artifact-echo/fence candidates passed the grammar and
     were selected, then repair-with-same-composition also failed. Two fixes:
     (a) content steps prefer candidates that also PARSE (ledger: candidate_unparseable,
     fallback to repair preserved); (b) composer carries the M0-proven hard-rules block
     (byte-for-byte, module docstring named) for content steps. A/B on same model+file:
     weak phrasing 0/4 → M0 wording green on first call, docstring bytes intact, no
     repair needed. Prevention > repair. Lesson recorded: for a 4B, the composer IS
     the quality lever (DESIGN §4.3 was right); prompt files must be colocated and
     iterated via FAIL_PATTERNS (DESIGN §4.1).
2. **Corpus ≥10** — DONE (a4dbb51): T-05..T-10 landed, 10 tasks total. Owner-session
   independent spot-verification: all 6 red (exit 1), T-06+T-09 solutions green in /tmp
   copies, corruption catch live (T-05, then restored), leak scan clean, T-01..T-04 untouched.
3. **M2 core** — DONE: artifact store + tree.attach (§3.1 two deferred tests closed),
   trajectory git snapshots + conflict-pause (§3.8 closed), boot_recover + lock (§3.5 closed),
   minimal allowlist exec, golden_bugfix.py end-to-end on the real model.
4. **Numbers** — golden sweep N=1 over 11 tasks: **9/11 PASS** (mini_repo + T-01,03,04,06,07,
   08,09,10); FAIL: T-02 off-by-one (wrong-direction fix), T-05 mutable-default (kept shared
   list). M0 ad-hoc loop was 4/4; the golden pipeline adds planning/spec/AC/gate overhead and
   still holds 82% — composition maturity is the gap, not the machinery.
   FAIL_PATTERNS recorded: (a) docstring-quote strip on re-emission — closed by composer
   hard-rules block; (b) cross-file import synthesis — needs locate-driven context (M3);
   (c) grounding false positive on 'e.g' — fixed (abbreviation whitelist).
   Delegation note: M2 agent died on litellm/volcengine 5h quota (429, reset 19:24 CST);
   owner session completed stages 1-5 directly — the canonical fallback, stated once.
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
