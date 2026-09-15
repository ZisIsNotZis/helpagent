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

## Deviations log
- Reference model Spark-X2.5-4B-Q4_K_M **found** in HF cache (/home/z/hf/models--XHToken--...) —
  the symlink in auto_maintain_bench was dangling; no deviation after all. Server on :8833,
  loads in ~6 s, grammar-constrained JSON (response_format json_schema) works, ~138 tok < 1 s.
- Required: `chat_template_kwargs: {"enable_thinking": false}` — otherwise the model burns the
  budget on a thinking preamble and returns empty content (verified). All runner calls must set it.
- Port 8899 is taken by an unrelated python http.server → baseline uses :8833.
