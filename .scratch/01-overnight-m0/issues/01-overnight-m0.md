# 01 — Overnight run: docs slices 2–3 + kernel core + M0 baseline numbers

Owner authorization (verbatim intent): "go automatically for this night, no stop until
you've got some significant numbers and ready to report to me... authorize you to take
full control, orchestrate independent fork=false subagents to do actual work."

## Scope decided for tonight
1. **Slice 2 (docs)** — INFO_FLOW §2 worked example: feature-class showcase (rate-limit
   story: DB column + endpoint + UI) + bugfix re-homed to the diagnostic path
   (locate → reproduce → evidence-seeded plan). DB leaf = test-DB-verified schema change
   (owner agreed (a)); never live-stateful. Owner's new rule recorded: leaf criterion
   applies **per side** — work-heavy and test-heavy split independently (DONE: DESIGN
   §4.8 + TASK_TAXONOMY expansion bullet).
2. **Slice 3 (docs)** — consistency sweep, cross-reference audit.
3. **Kernel core (code)** — harness/ per DESIGN §7 + envelopes (ENVELOPE_SCHEMAS all),
   TaskTree invariants (KERNEL_API §4), FakeModelRunner (TEST_PLAN §2), pytest suite
   per TEST_PLAN §3.1 + §3.8 (+ new invariants). No GPU needed (unit gate).
4. **Corpus (code)** — bench/ 4 bugfix tasks + tests/fixtures/mini_repo (TEST_PLAN §4).
5. **M0 baseline (code + numbers)** — llama-server + Qwen3.5-2B-UD-Q4_K_XL (GPU 4090
   present; reference 4B not on disk — noted as deviation), whole-file-edit step,
   grammar-constrained JSON, run over corpus → calls/tokens/wall/pass-rate.

## Agent assignments (file ownership, disjoint)
- Agent K: `harness/`, `tests/`, `pyproject.toml`, `uv.lock` — kernel + tests. No commits.
- Agent C: `bench/`, `tests/fixtures/` — corpus + fixtures. No installs, no commits.
- Main session: `docs/` (slices 2–3), integration, review, all commits, gates.

## Gates before each commit
- docs: none beyond self-review + cross-ref grep.
- code: `uv run pytest -q` green, <10 s (TEST_PLAN unit gate), recorded per commit.

## Numbers to report (fill at end)
- [ ] pytest: N passed / N total, runtime
- [ ] invariants covered vs TEST_PLAN §3.1–3.8 pinned list
- [ ] docs contradictions closed (slice 3 list)
- [ ] M0 baseline: tasks fixed / total, model calls, tokens, wall time, per-task
- [ ] deviations + blockers

## Numbers (final, 2026-09-15 night)
- **pytest: 41 passed / 41, 0.18 s** (gate ≤10 s) — TEST_PLAN §3.1 + §3.8 pinned invariants
  incl. the 4 added ones; erasure contract test green; happy-path contract scenario green.
- **Kernel: 2,848 lines** (envelopes 722, tree 671, fake model 158, runner 194, tests 1,013);
  24 doc-ambiguity decisions recorded inline; 3 TEST_PLAN items honestly deferred (artifact
  store, tree.attach, trajectory git — M2+ machinery).
- **Docs: slices 2+3 landed** — feature showcase + diagnostic trace, per-side split rule,
  consistency sweep (B7 de-duplicated, index threading, bound phrasing).
- **M0 baseline (Spark-X2.5-4B-Q4_K_M, the design's reference model, llama-server :8833):**
  run 1: 4/4 fixed · 4 calls · 6,488 tok · 16.8 s wall (model 10.2 / harness 6.6)
  run 2: 4/4 fixed · 6 calls · 20,175 tok · 47.0 s wall — T-03 needed 3 attempts.
  => Sampling noise at temp 0.2 is real (same task: 1 vs 3 calls) — N-repeated-runs and
  best-of-N are empirically necessary, not just doctrine (DESIGN §6).
  KV-cache reuse: 744–932 of ~1,400 prompt tokens cached per call (§9.11 datum).
  Every fix was the minimal one-liner; untouched-files contract held in all 8 task-runs;
  zero grammar refusals/schema violations across 10 calls; `unable` fired once (designed escape).
- **Erasure independently re-verified (sharper than the agent's audit):** positional check —
  attempt-2's prompt embeds `is_enterprise` with the restored original buggy line, so the failed
  attempt's text is genuinely absent; the one line my first diff flagged is byte-identical to the
  pre-existing `is_known` body (the agent's false-positive explanation, confirmed).
- **Fix-variant finding:** run 2 accepted a non-canonical T-03 fix (`plan == PLAN_ENTERPRISE.lower()`;
  official run = canonical `==`). Checks correctly pass both — gate = correctness, diff-canonicity
  belongs to the scoring rubric (DESIGN §6 "fix quality"). "Minimal one-liner" claim is scoped to
  the official run.
- Corpus: 4 tasks + mini_repo, all red→green verified, contract validated incl. corruption catch.

## Deviations log
- Reference model Spark-X2.5-4B-Q4_K_M **found** in HF cache (/home/z/hf/models--XHToken--...) —
  the symlink in auto_maintain_bench was dangling; no deviation after all. Server on :8833,
  loads in ~6 s, grammar-constrained JSON (response_format json_schema) works, ~138 tok < 1 s.
- Required: `chat_template_kwargs: {"enable_thinking": false}` — otherwise the model burns the
  budget on a thinking preamble and returns empty content (verified). All runner calls must set it.
- Port 8899 is taken by an unrelated python http.server → baseline uses :8833.

## Kernel report — verification addendum (post-night)
- Headline reproduced by owner session before commit: 41/41 green; inventory matches; no
  network/exec surface. Now 44/44 (3 new tests, below).
- DECISION spot-checks: (15) internal-entry resolution and (1)/(5) sentinel + context-only
  validation verified against docs — implementations carry correct doc citations.
- Gap found & closed (050f064): decision (5) lets reference checks (seam grounding, boundary
  subset, ac_id ∈ map) skip silently when no validation context is injected. llm_step now
  records `validation_context_missing` in the ledger for expand/draft_acs/write_spec/
  test_plan/write_test. **M1 requirement: the real runner must inject context on every call —
  the ledger note is the safety net, not the fix.**
- K's remaining-risk note (REQUIRED-sentinel consolidated error vs per-field errors) adopted
  as an M1 constraint: the real decoder grammar must branch identically to §0 so error
  messages align. (§0 already specifies the two-alternative grammar; this is implementation
  guidance, no doc change needed.)
