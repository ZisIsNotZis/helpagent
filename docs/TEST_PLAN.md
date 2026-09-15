# TEST PLAN — the helpagent harness itself

Covers DESIGN Goal 4 ("the harness is hardened: typed, tested"). The benchmark corpus (DESIGN §6) is
**out of scope here** — it evaluates model+script quality; this plan evaluates the kernel's guarantees.
References: DESIGN §2.4 (erasure), §4.1–4.8, TASK_TAXONOMY (taxonomy codes A–I), ENGINE_SCRIPT.md.

<!-- DECISION: KERNEL_API.md defines the six primitives; the contract tests below are its executable form.
The `k.*` surface matches KERNEL_API §2 reconciliation. Any drift between these tests and KERNEL_API.md
or ENGINE_SCRIPT.md is a doc bug — the contract suite is deliberately the binding artifact. -->

Conventions: pytest (not unittest), `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/e2e/`,
fixtures in `tests/fixtures/`. Unit gate (PR-blocking): unit + contract, all <10 s total, no GPU, no network.
Integration/E2E: `@pytest.mark.slow`, nightly or manual.

---

## 1. Test pyramid

| Level | What runs | Model layer | Gate |
| --- | --- | --- | --- |
| **Unit** | kernel logic per invariant: validation, budget, governance, cascade, check ladder, sandbox policy, secret filter | `FakeModelRunner` (deterministic) or pure logic (no model at all) | PR-blocking |
| **Contract** | script↔kernel API surface; envelope schema round-trips; the engine script runs unchanged against a fixture tree | `FakeModelRunner` with scripted scenario fixtures | PR-blocking |
| **Integration** | real llama.cpp server + tiny model: cache-hit rate, grammar validity, best-of-N | real (tiny model, e.g. Qwen2.5-0.5B-Instruct GGUF) | slow/optional |
| **E2E** | one full golden bugfix run on a fixture repo (`tests/fixtures/mini_repo/`) with the fake model | fake (deterministic E2E of the *harness*, not the model) | slow/optional |
| **Benchmark** | the corpus, scoring, cost metrics, FAIL_PATTERNS | real | separate loop, never CI |

The pyramid is inverted on cost: unit tests must exhaust every kernel invariant *without a GPU*, because
llama.cpp prefill is slow and benchmarks are already the expensive layer. Everything below is engineered
to make that possible.

---

## 2. The FAKE MODEL LAYER — the single most important test asset

A deterministic scripted model runner standing in for `harness/model/runner.py`. Every kernel invariant
(schema validation, budget, erasure, governance review, judge panels) is exercised by feeding it canned
envelopes — including deliberately malformed ones.

### Interface (mirrors the real runner's)

```python
# tests/fakes/model.py
class FakeModelRunner:
    """Implements the same protocol as model.Runner: async complete(request) -> Envelope.
    The kernel's llm() primitive calls it identically; scripts cannot tell the difference."""
    def __init__(self, script: dict[str, list[EnvelopeSpec | Exception]]): ...
        # keyed by step_type; consumed FIFO per step_type; exhausted => AssertionError
        # (a test that expected more calls than the script made is itself a failure)
    def calls(self, step_type: str) -> list[CallRecord]   # (artifacts, question, tools, fresh)
```

```python
class EnvelopeSpec:      # one canned response, or a built-in misbehavior
    step_type: str
    body: dict           # valid envelope payload OR raw_text (bypasses formatting for malformed cases)
    kind: Literal["ok", "raw"] = "ok"
    # helpers:
def ok_edit(path, content): ...          # implement envelope: whole-file edit + self-summary
def unable(reason): ...                  # grammar-enforced unable: reason alternative
def malformed_json(): ...                # kind="raw", body truncated mid-JSON
def schema_violation(missing="self_summary"): ...  # valid JSON, missing mandatory field
def code_with_syntax_error(): ...        # valid envelope, string field has broken Python
```

### Fixture format (colocated per test, no global registry)

```python
# tests/unit/kernel/test_check_write_rollback.py
fake = FakeModelRunner({
    "implement": [ok_edit("calc.py", BROKEN_CODE),   # attempt 1: unfixable finding
                  ok_edit("calc.py", GOOD_CODE)],    # attempt 2: clean
})
k = make_kernel(model=fake, repo=fixture_repo("mini_repo"))
wrote = await k.check_write(...)
assert wrote.ok and fake.calls("implement")[0].artifacts["spec"].keys() >= {"interfaces"}
# erasure: the retry prompt must NOT contain attempt 1's text
assert BROKEN_CODE not in render_prompt(k, call=1)
```

Misbehavior cases every suite must be able to inject: `malformed_json`, `schema_violation`,
`code_with_syntax_error`, `unable`, **exhaustion** (script wants N calls, model scripted for N−1 →
BudgetExceeded / split-signal path), and **call-count assertions** (kernel made exactly the scripted
number of `llm()` calls — pins retry/re-split topology).

<!-- DECISION: canned envelopes are keyed FIFO per step_type, not matched on question text. Matching on
question content would make tests brittle to prompt rewording; FIFO + call-count assertions are enough
to pin sequencing. If a script revision changes call order, the fixture breaks loudly — which is the
point, per DESIGN "script revision = versioned bundle". -->

---

## 3. Per-invariant test matrix (unit level)

Format: name — arrange/act/assert — [fake | pure].

### 3.1 Schema validation (artifacts + envelopes)

- `test_envelope_rejects_missing_self_summary` — feed `schema_violation()` → `llm()` raises
  `SchemaViolation`; ledger records `validation_failed`; **no artifact written**. [fake]
- `test_unable_alternative_is_in_every_envelope_schema` — iterate the per-leaf-type schema library;
  assert each has a discriminant accepting `unable: reason`. [pure]
- `test_artifact_size_cap_triggers_split_window_not_truncation` — write code artifact > cap → kernel
  raises `SplitWindowRequired`, artifact NOT truncated on disk. [pure]
- `test_producer_linkage_is_schema_field` — write artifact without `node_id` linkage → rejected.
  [pure]

### 3.2 Sandbox / allowlist / policy-blocked

- `test_model_command_outside_scope_is_policy_blocked` — `exec()` with `provenance="model"`, command
  `cat /etc/passwd` → shaped result `policy-blocked`, **no exception**, no diagnose-pipeline entry.
  [pure]
- `test_same_command_with_kernel_provenance_runs` — identical spec, `provenance="kernel"` → executes.
  Pins that the sandbox keys on provenance, not command text. [pure]
- `test_network_denied_by_default_and_routed_to_allowlist_request` — probe calls web → `policy-blocked`
  - allowlist-request artifact created; counter `policy_blocked_denials` +1. [pure]
- `test_ansi_stripped_and_byte_capped_in_generic_shaper` — 10 MB noisy output → shaped ≤ cap, raw
  archived through secret filter. [pure]
- `test_renamed_command_bypass_is_still_scoped` — `python -c "open('/etc/passwd')"` → filesystem scope
  blocks by path, not by argv[0]. [pure]

### 3.3 Check pipeline

- `test_autofix_stops_after_two_passes` — file whose lint finding survives a fixer pass → exactly 2
  fixer invocations, then survivor escalation to `llm()` with bounded excerpt. [fake]
- `test_tool_fight_oscillation_is_fail_pattern` — fixer A reintroduces B's finding → after pass 2,
  escalate; ledger records FAIL_PATTERN `tool_fight`. [fake]
- `test_unfixable_write_rolls_back_worktree` — parse error post-write → `git` state equals
  pre-write snapshot; ledger entry references the erased attempt; disk file unchanged. [pure +
  tmp git repo]
- `test_type_check_filters_at_finding_level` — write breaks a caller in an untouched file → finding
  survives filtering (finding-level, not invocation-level scoping, DESIGN §4.5). [pure]
- `test_touched_files_only_scoping_is_rejected` — config attempting invocation-level scoping →
  config validation error. [pure]

### 3.4 Erasure semantics (§2.4)

- `test_retry_prompt_contains_failure_summary_not_failed_text` — attempt 1 emits `code_with_syntax_error()`;
  inspect composed prompt for attempt 2: contains the one-line failure summary + ground truth; does NOT
  contain the broken source string. [fake]
- `test_failed_attempts_persist_in_ledger_after_retry` — after successful attempt 2, ledger still has
  attempt 1's entry with diff + outcome. Append-only: also assert no API on the ledger can delete
  (`Ledger` exposes append/query only). [fake]
- `test_erase_then_verify_file_view_matches_disk` — post-rollback, a fresh `read_file` tool call inside
  a later `llm()` returns the pre-attempt content. [fake]

### 3.5 Workdir boot-reset & single-instance lock

- `test_boot_recover_resets_dirty_workdir` — leave uncommitted edit + untracked file; run
  `boot_recover(workdir)` → tree clean, ignored files intact, ledger has `boot: reset dirty workdir`.
  [pure + tmp git repo]
- `test_clean_workdir_is_not_touched` — clean repo → no reset, no ledger entry. [pure]
- `test_second_instance_in_same_workdir_is_refused` — hold `k.lock(workdir)`; second `lock()` raises
  `InstanceLocked` immediately (no blocking wait). [pure]
- `test_lock_released_on_crash` — holder process killed; next `lock()` succeeds (lockfile with pid
  liveness check). [pure]

### 3.6 Global budget

- `test_max_leaves_overflow_yields_needs_user` — script expands beyond `max_leaves` → next expansion
  gets `BudgetExceeded` → node `needs-user`, message-box question queued immediately. [fake]
- `test_max_model_calls_accounted_per_call_not_per_step` — best-of-N (3 samples) costs 3. [fake]
- `test_wall_clock_budget_uses_model_and_tool_time` — inject fake timers; tool/infra time counts.
  [pure]
- `test_step_round_budget_is_estimate_times_headroom` — leaf estimated 4 rounds → exhaustion at 6 →
  split signal artifact. [fake]

### 3.7 Memory governance pipeline

- `test_term_sanity_rejects_bad_topic_keys` — 0 terms, 7 terms, stopwords, non-normalized case →
  draft rejected with reason. [pure]
- `test_evidence_ref_must_resolve_in_ledger` — lesson citing missing ref → rejected. [pure]
- `test_full_and_partial_overlap_detection` — term sets {a,b,c} vs {a,b} → full (superset); {a,b} vs
  {b,d} → partial (intersection); {a} vs {z} → none. Exact set algebra, no fuzz. [pure]
- `test_provisional_memory_not_promoted_below_threshold` — N−1 matching successful sessions → stays
  provisional (low injection priority). [fake for reviewer step, pure for stats]
- `test_challenger_must_beat_incumbent_stats` — incumbent promoted, challenger approved once →
  incumbent retains injection slot; demotion only after challenger wins with stats. [fake]
- `test_contradicted_twice_deletes_promoted_memory` — two contradiction verdicts → deleted, deletion
  itself ledger-recorded. [fake]
- `test_reviewer_gets_fresh_context_and_ground_truth` — inspect the `memory_review` call's composed
  prompt: contains lesson + evidence ref target + ground truth; does NOT contain author context.
  [fake]
- `test_debate_capped_at_two_exchanges_then_parked` — uncertain → 2 exchanges → unresolved → visible
  parked queue artifact. [fake]
- `test_memory_lifecycle_never_mutates_prefix_bytes` — promote/demote/delete memories; hash of every
  composed prefix before vs after is identical (§2.7). [fake]

### 3.8 Task-tree rules

- `test_reopen_done_parent_on_child_edit` — insert/modify node under `done` parent → parent
  `in-progress`, its AC map re-runs. [pure]
- `test_touched_branch_marks_children_stale` — edit branch node → all descendants `stale`; stale
  leaves cannot close until re-verified. [pure]
- `test_closure_gate_requires_three_conditions` — table-driven: (a) AC missing test → no close;
  (b) test skipped/flaky → no close; (c) child open → no close; all three → close. Gate decision
  asserted to be kernel code, not an `llm()` call. [pure]
- `test_leaf_ac_map_mandatory_internal_optional` — leaf with empty map → `set_ac_test_map`
  findings; internal node with empty map → accepted, and the node closes on (c) alone. [pure]
- `test_internal_ac_entry_must_resolve_to_descendant_check` — internal entry naming a command
  or test id no descendant owns → close refused with a structured reason. [pure]
- `test_ac_map_is_decided_not_self_approved` — canned `draft_acs` map with a `subjective`
  entry where a deterministic check is feasible → canned `gate_decide` rejects → map not frozen;
  assert the `gate_decide` call ran `fresh=True` and in a session without the author's context. [fake]
- `test_ungrounded_child_reference_rejected` — canned `expand` child whose `what` names a file
  outside the injected candidate scope + symbol DB → kernel rejects the child (enum-first rule
  applied to the free strings), so an invented file cannot enter the plan. [fake]
- `test_dag_validation_rejects_orphan_duplicate_producer_cycle` — three cases each produce a
  structured re-expansion request, not a stall or exception leak. [pure]
- `test_file_overlap_serializes_writers` — two ready leaves touching `calc.py` → executed
  sequentially (event-order assertion); disjoint leaves run interleaved under the concurrency limit.
  [pure, async]
- `test_user_edit_conflict_pauses_not_overwrites` — dirty snapshot divergence mid-run → leaf pauses,
  `needs-user`. [pure]

### 3.9 Composer

- `test_info_miss_counter_increments_on_retry_with_missing_info` — [fake]
- `test_no_generic_docs_ever_injected` — composed prompt for any step contains no doc-chunk field.
  [pure]
- `test_prefix_is_byte_stable_across_steps` — compose 5 different steps in one run → prefix bytes
  identical. [pure]

---

## 4. Contract tests — the engine script runs unchanged against the fake model

The engine script (`scripts/v1/`) executes under `FakeModelRunner` with a fixture tree. If these pass
without touching script code, the kernel API is compatible. **These are KERNEL_API.md's executable
form.**

Shared fixture: `tests/fixtures/mini_repo/` — a tiny Python package with one seeded bug
(`calc.py: divide by zero path`), a test file, a conventions file. Scenarios = scripted envelope
sequences in `tests/contract/scenarios/<name>.py`.

1. `test_scenario_happy_path_bugfix` — understand → plan (clean trial split, no findings) → DAG
   validated → spec → AC map decided by `gate_decide` → parallel code+tests → gate all_green →
   run summary. Assert: call counts per
   step_type match the script's topology; tree root `done`; leaf artifact carries self-summary; the
   golden flow's six phases each appear in the trajectory.
2. `test_scenario_test_bug_loop` — test writer's canned test is wrong; `failure_judge` envelope says
   `side="test"` → script queues test-fix ticket, does NOT route to implementer; ticket node created
   via tree.insert_ticket; run ends with both nodes closed.
3. `test_scenario_flaky_test` — falsification run returns `{n_trials: 5, observed_rate: 0.4}` →
   flake detected; script fixes the flaky test via normal pipeline (no waiver); ledger notes it.
4. `test_scenario_policy_blocked_probe` — canned probe proposes `curl` → `policy-blocked` shaped
   result reaches the script; assert it was NOT counted as a probe failure and an allowlist request
   artifact exists; probe loop continues with the next scripted probe.
5. `test_scenario_needs_user_parking_and_resume` — planning surfaces a needs-user finding → run
   parks, subtree paused, independent leaves still execute; `user()` answer artifact lands → parked
   leaf fires immediately and run completes. Assert: `needs-user` node was held-not-blocking, and
   resume reused persisted artifacts (see also §5 WAL-free resumption).

Contract extras (not scenarios, per-pair):

- `test_scenario_feature_path_uses_structural_cuts` — `task_class=add-feature`:
  `propose_cuts(evidence=None)`, no `locate` call, expand runs straight off module-map seams.
- `test_scenario_diagnostic_routing_evidence_seeded_cuts` — `task_class=bugfix`: assert call order
  (`locate` before `expand`), that `propose_cuts` received the evidence artifact, and that the
  composed `expand` ctx carries evidence-anchored cuts — not filename-only cuts. Pins the rule that
  a diagnostic plan is never fabricated from names.
- `test_firewall_contract_reaches_both_sides_solutions_do_not` — compose the leaf's prompts and
  assert: `test_plan`/`write_test` ctx contains `interfaces` + `behavior` and does **not** contain
  `implementation_notes`, the diff, or any code; `implement` ctx contains `implementation_notes`;
  a write attempt by the implementer into the test file's path is policy-blocked. [fake]

- `test_all_step_types_have_prompt_file_and_schema` — every `llm_step` step_type in `scripts/v1/` has
  `prompts/<step>.md` + an envelope schema; both ship in the revision bundle. [pure]
- `test_envelope_round_trip` — for every schema in the library: build a valid instance → serialize →
  parse → equal; and the `unable` alternative parses for each. [pure]
- `test_script_makes_no_kernel_calls_outside_six_primitives` — static analysis (AST walk) of
  `scripts/v1/`: only `k.llm/exec/inject/check_write/memory.write/user` + documented utilities. [pure]

---

## 5. The harness's own failure classes

- `test_kill9_mid_step_recovers_via_boot_reset` — run scenario 1 under a harness subprocess; kill −9
  between implement and check; restart → `boot_recover` resets workdir, resumption rebuilds the leaf
  by re-execution from the tree's last committed step; final state identical to uncrashed run
  (artifact hashes). Asserts the ENGINE_SCRIPT "wire middle state" assumption. [fake, subprocess]
- `test_two_instance_lock_refuses_second_run` — scenario 1 running; launch second → exits with
  `InstanceLocked`, first run unaffected. [fake, subprocess]
- `test_secret_filter_at_store_boundary` — table-driven: API key pattern, private key header, AWS
  creds, `password=` in tool output/diff/transcript → persistence refused/redacted; benign `password`
  policy text passes (no over-blocking). Assert the filter runs for **raw tool output and diffs**, not
  only review-phase scans (§2.5). [pure]
- `test_wal_free_resumption_relies_on_artifacts_only` — crash with in-flight step; assert no
  journal/WAL file exists anywhere in workdir, and resume is correct purely from artifacts + git
  reset. This pins the design choice that recovery = boot-reset, not reconciliation. [fake]
- `test_parallel_judge_calls_do_not_corrupt_slot_state` — two concurrent fresh judges → both complete
  (serialization correctness even if scheduling is dumb). [fake]

---

## 6. Integration tests (real llama.cpp — slow, optional, never the unit gate)

`@pytest.mark.slow @pytest.mark.integration`; tiny GGUF model; single-server fixture on a random port;
skipped when no model file present.

- `test_grammar_output_validity_rate` — N=50 single-step invocations per envelope type with
  grammar-constrained sampling → ≥99% parse under the schema. Measures the §4.7 assumption; a drop
  here invalidates unit-level fakes and must be investigated before trusting contract tests.
- `test_cache_hit_rate_sequential_invocations` — 10 sequential calls sharing the byte-stable prefix →
  server-reported cached-token ratio ≥ threshold. **This is the measured-not-assumed property of
  DESIGN §4.1/§9.11** — it is a timing/behavior property of llama.cpp and cannot be faked.
- `test_best_of_n_decision_sampling` — one ambiguous decision step, 3–5 samples, deterministic checker
  selects; assert selection is deterministic given fixed seed, and cost counters ×N (feeds §3.6).
- `test_tree_sitter_auto_repair_loop` — prompt the model to emit slightly-broken Python → parse →
  auto-repair or respawn-with-excerpt path fires with real model output.

## 7. E2E (harness-deterministic, no GPU)

- `test_e2e_golden_bugfix_mini_repo` — scenario 1 end-to-end through the real kernel + real tmp git
  repo + real check pipeline (ruff, pytest) against `mini_repo`; fake model. Assert: bug fixed, tests
  pass, unrelated files untouched (`git diff` == expected diff), stats artifact has model/tool wall
  time split, run summary exists.
- `test_e2e_run_summary_and_ledger_shape` — post-run invariants from DESIGN §5 step 6: counters
  present (info-miss, policy-blocked, tokens, both wall times), per-run aggregation parses.

---

## 8. What is NOT unit-testable (feasibility critique; design honest about limits)

| Property | Why not | Where tested instead |
| --- | --- | --- |
| KV-cache reuse quality | llama.cpp server timing behavior | §6 `test_cache_hit_rate_sequential_invocations` + cold-cache benchmark scenario (§6 of DESIGN) |
| Fuzzy memory matching quality | deterministic matcher is trivial; *quality* (injection precision/recall of AND-term matching, DESIGN §9.4) needs realistic distributions | synthetic mini-corpus below + benchmark |
| Tier-2 self-check value | "does same-model diff-vs-intent checking beat pure rule growth" is a keep/kill question (§9.2) | benchmark-only, N repeated runs, effect-size rule |
| Grammar validity at scale | sampling-dependent | §6 validity-rate test |
| Effect of prompt wording on a 4B model | the whole point of the benchmark loop | corpus + FAIL_PATTERNS |

### Synthetic mini-corpus for governance testing (DESIGN §4.4)

`tests/fixtures/memory_corpus/` — deterministic, versioned, no model required for the deterministic
stages; the reviewer/debate stages use the fake model with scripted verdicts.

- **~20 fake contexts**: (project-domain, topic terms present, should-inject?) tuples — e.g. pytest
  fixture-scoping gotcha with terms `{pytest fixture scope}`; async-cleanup lesson `{asyncio cleanup
  cancel}`; decoy contexts sharing one term ({pytest}, {fixture}) that must NOT match. ~7 positive,
  ~13 negative matches at the AND-match boundary.
- **~10 lessons with known-good/known-bad overlaps**: 3 known-good (provenance resolves, terms sane,
  non-overlapping), 2 full-overlap (superset of an existing lesson → reject/merge), 2 partial-overlap
  (distinct-enough → admit), 2 poisoned (broken evidence ref / 7-term key → reject). Expected
  pipeline verdicts asserted for each: `test_governance_corpus_expected_verdicts`.
- `test_matcher_precision_recall_on_corpus` — inject-or-not decision for all 20 contexts vs labeled
  truth → precision/recall numbers recorded as a tracked artifact. This is the §9.4 measurement,
  done deterministically.
- `test_promotion_lifecycle_on_corpus` — run the full pipeline (fake reviewer) across the corpus;
  known-good lessons promote after threshold, poisoned ones never leave draft.

---

## 9. What the gate blocks on (summary)

PR merge requires: all of §3 (unit), §4 (contract), §5 failure-class unit tests — green in <10 s,
CPU-only. Nightly: §6 integration + §7 E2E. Continuously, outside CI: the benchmark loop. If a feature
cannot show a number at its level of the pyramid, it does not exist (DESIGN §2.6 applies to tests too).
