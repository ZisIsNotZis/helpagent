# Fix wave 1 — handoff (recovered after the 30-minute worker timeout)

**Status: complete; code committed.** The previous worker was killed by the subagent
timeout leaving uncommitted edits. This handoff reconstructs each change against the
intended fix list, closes the two defects the after-run exposed (T-35 false success and
the canary-missing independent-test evidence), records the real-model before/after, and
commits.

Upstream record: [`parity-forensics.md`](parity-forensics.md) §2.1/§2.5/§5 (D1–D3),
[`parity-forensics-independent-verification.md`](parity-forensics-independent-verification.md)
(execution-verified D1 facts). WIP diff preserved as
[`fix-wave-1-wip.patch`](fix-wave-1-wip.patch).

## 0. Verification summary

| check | command | result |
| --- | --- | --- |
| unit/integration suite | `uv run pytest -q -p no:warnings` | **exit 0** (all green) |
| pytest (re-run at handoff) | `uv run pytest -q -p no:warnings` | **exit 0** |
| claim-gate single path | `grep -n claim_decision harness/leaf.py` | one gate; no new claim path added (only a ruling-coherence guard and a pytest flag) |

Working-tree changes: `bench/v2_leaf.py`, `harness/leaf.py`, `tests/unit/test_v2_leaf.py`
(the fix wave) plus new `bench/v2_measure.py`, `tests/unit/test_v2_measure.py`
(measurement tooling). No other `.scratch` ticket was modified.

## 1. Per-fix inventory

`file::function` → regression test → status.

| # | fix | file :: function | regression test | status |
| --- | --- | --- | --- | --- |
| 1 | IV desired-state rule in the independent-test prompt | `bench/v2_leaf.py::_independent_test_question` (uses `harness.leaf::_SELF_TEST_DESIRED_STATE_RULE`) | `test_fix1_independent_test_prompt_carries_the_desired_state_rule` | **implemented** |
| 2 | per-criterion inversion classification before the red-on-final early return | `harness/leaf.py::evaluate_independent_test` + `iv_blocking_final_ids` | `test_fix2_iv_blocking_final_ids_excuses_inverted_and_blocks_the_unmet`, `test_fix2_evaluate_independent_test_classifies_inversion_before_the_early_return` | **implemented** |
| 3 | re-sampled IV labelled `independent-test-resampled`, cannot upgrade the basis alone | `harness/leaf.py::run_leaf::final_verification` | `test_fix3_resampled_independent_test_does_not_upgrade_the_claim` | **implemented** |
| 4 | carrying anchor required on the green path (P8c `_CARRYING_ANCHORS`) | `harness/leaf.py::claim_decision` (pre-existing at 72538ab; wave adds the doc note in `deterministic_greens`) | existing P8c tests | **already present at baseline** (no behaviour change in this wave) |
| 5 | review attributed to the source-revision fingerprint | `harness/leaf.py::combine_review_verdicts` + `ReviewVerdict.source_revision` + `_source_revision_fingerprint` at review time | `test_fix5_review_round_cannot_reapprove_bytes_it_rejected` | **implemented** |
| 6 | coverage-ranked best evidence | `harness/leaf.py::capture_best_evidence` / `_best_evidence_preference` / `BestEvidenceRevision` | `test_fix6_best_evidence_prefers_more_complete_request_coverage` | **implemented** |
| D1 | deterministic delivery anchor (contract-clear snapshots) | `harness/leaf.py::run_leaf::current_contract` / `note_contract_clear` / `_snapshot_fails_contract` / `restore_refusal_reason` | `test_d1_contract_clear_revision_displaces_a_failing_snapshot` | **implemented** |
| D2 | credit `test_wrong` from the failure traceback; never M1-erase on a test-attributed failure | `harness/leaf.py::failure_is_test_attributed` / `apply_judge_filter` / the M1-erase site | `test_d2_test_attributed_traceback_credits_test_wrong` | **implemented** |
| D3 | judge coherence extended to `spec_wrong` (+ ≥2 attempts before a spec bubble) | `harness/leaf.py::_judge_incoherence` / `apply_judge_filter` / `handle_verdict` | `test_d3_spec_wrong_naming_a_source_defect_is_not_credited` | **implemented** |
| **D3b** | **(NEW, closes T-35)** a self-contradicting reconciliation "check" ruling may not drop a blocking red | `harness/leaf.py::reconciliation_ruling` (now takes the request) + call site | `test_d3b_reconciliation_ruling_refuses_a_self_contradicting_check_blame`, `test_d3b_incoherent_check_ruling_cannot_carry_a_false_success` | **implemented** |
| **FIX 7** | **(NEW, closes canary-missing)** `--continue-on-collection-errors` so a collection error cannot hide the canary | `harness/leaf.py::_default_run_tests` | `test_fix7_a_collection_error_still_runs_and_authenticates_the_gate` | **implemented** |

Not in this wave (recorded, not implemented): D4 (one-sided documented-contract check),
D5 (IV model-written admissibility/symptom rule), D6 (measurement seeds). See §5.

## 2. T-35 false-success resolution

The reported false success (`claimed=True basis=independent-test stop=green`, grader
failed) is reproduced from the previous worker's `/tmp/wave1/after` trajectory. Its
mechanism is **not** a bypass of P8c — the carrying anchor (`documented-api`) was green.
The claim path was:

1. the run's own test (`spans/test_merge.py`) was RED on every attempt;
2. D3 deferred the premature `spec_wrong` bubble (attempt 1) so the run reached
   exhaustion;
3. `final_verification`'s single independent test approved the revision;
4. the P5(c) reconciliation judge answered `blame="test"` while its own `problem` named
   the **source** defect ("the code fails to merge … because it uses 'start <=
   current_end'");
5. `reconciliation_ruling` read the RAW blame word first → `"check"`, and with
   `independent_approved=True` the soundness guard dropped the own red;
6. the gate then granted `route="independent-test"` (basis `independent-test`).

**Fix (D3b):** `reconciliation_ruling` now applies the SAME coherence rule the
deterministic filter already applies to a `test_wrong` label (`_judge_incoherence`: a
reason that names the SOURCE and no failing test function). When it is self-contradicting
the ruling is `"unclear"`, the own red keeps blocking, and the exhaustion claim becomes a
verifier CONFLICT (honest failure). Signature is backward compatible (`request=None`
preserves the legacy raw-blame behaviour).

### Real-model resolution (T-35, `--calls 24`, temp 0.2, server `:8834`)

| arm | run | claimed | actual | quadrant |
| --- | --- | --- | --- | --- |
| before (72538ab, no wave) | sample A | False | False | honest-failure |
| before | sample B | **True** (basis review+independent-test) | False | **false-success** |
| WIP-only (`/tmp/wave1/after`, prior worker) | sample | **True** (basis independent-test) | False | **false-success** (the D3b path) |
| after (wave + D3b + FIX 7) | `close/after/T-35` | False | False | honest-failure |
| after | `close/after/T-35-r1` | False (verifier-conflict) | False | honest-failure |
| after | `close/after/T-35-r2` | False | False | honest-failure |
| after | `close/after/T-35-r3` | False | False | honest-failure |
| after | `close/after/T-35-r4` | False | False | honest-failure |
| after | `close/after/T-35-interval-merge-invariants` (2nd sample) | False | False | honest-failure |

**Result: 0 false successes in 6 post-fix samples; the WIP-only sample's
`basis=independent-test` claim no longer reproduces.**

**Residual (out of scope, pre-existing).** The before sample B and the base arm show a
SECOND T-35 false-success mechanism that D3b does not address: the run's own test,
the graded review and the independent test all approve the wrong fix, and the only
deterministic anchor is the non-behavioural `documented-api`/`no-regression` pair. That is
the D4 defect in `parity-forensics.md` §5 (the documented-contract checks never see a
deleted/contradicted documented BEHAVIOUR), explicitly NOT in this wave's fix list. It is
present at baseline, not introduced by this wave. Closing it needs D4 or a behavioural
anchor.

## 3. Canary-absent independent-test evidence (FIX 7)

**Finding (reproduced deterministically, no model needed).** The message
`the per-run canary … is absent from the report; the report cannot be this run's evidence`
is emitted when the independent test file fails to IMPORT. pytest aborts the session on
a collection error before the canary file is collected; the junit report still parses (one
`<error>` testcase for the test module), so the gate reaches the canary check with no
canary and reports `canary-missing`. `evaluate_independent_test` then classifies the
verdict as `independent-test-unobserved` — a NON-DISCRIMINATING state that blocks the
review route. Two things are wrong: the report IS this run's report, and a real observed
failure is downgraded to "nothing was observed".

Reproduction (before fix):
```
exit 2  anomaly canary-missing  n_tests 1
detail the per-run canary tests/test_gate_canary_<token>.py::test_gate_canary_<token> is absent …
```
Reproduction (after fix): `exit 1  anomaly tests-failed  n_tests 2`, canary PASSED,
collection error recorded as the failed node — the trustworthy observed RED.

**Fix:** `harness/leaf.py::_default_run_tests` adds `--continue-on-collection-errors` to
the leaf's pytest invocation (the collection errors are still reported, the canary runs,
the report authenticates). Applied in the leaf only — `harness.staging.PYTEST_ISOLATION_ARGS`
is shared with `bench/external_score.py`, whose recorded grader semantics
(`suspected-contaminated-grade`) must not change.

**Real-model evidence:** before arm T-28, T-26, T-30 report `independent-test-unobserved:
… canary … is absent`; after arm reports none (T-22 instead reports the genuine
`0 failure(s), 1 error(s)` collection error of its IV test).

## 4. Real-model battery (before/after)

Same tasks, same command, one sample each (temperature 0.2, `--calls 24`). `before` =
pristine worktree `/tmp/helpagent-base` (detached 72538ab); `after` = this working tree.

| task | before actual/claimed/quad | after actual/claimed/quad |
| --- | --- | --- |
| T-35 | F/T **false** (sample B); F/F honest (A) | F/F honest ×6 |
| T-28 | F/F honest (canary) | F/F honest |
| T-26 | F/F honest (canary) | F/F honest |
| T-30 | T/F missed (canary) | T/F missed |
| T-22 | T/F missed | F/F honest |
| T-06 | T/F missed | T/F missed |
| T-19 | T/F missed | T/F missed |
| T-12 | T/F missed | T/F missed |
| T-10 | T/T **true-success** | T/F missed |
| T-31 | T/F missed | T/F missed |
| T-17 | T/F missed | T/F missed |
| T-27 | F/F honest | F/F honest |
| T-20 | T/F missed | T/F missed |
| T-21 | T/F missed | **T/T true-success** |
| A-02 | F/T **false-success** | F/F honest |

Totals (15 primary tasks): before actual 10/15, claims 3, **false successes 2**;
after actual 9/15, claims 1, **false successes 0**. The actual delta is inside the
documented ±2-task N=1 noise band; the false-success count is the metric this wave moves
(2 → 0 on the matched set; 6/6 honest on T-35). Single-sample caveat: these are N=1 per
task except T-35 and should be re-measured at ≥9 seeds per D6 before publication.

## 5. Reverts / out-of-scope

- Nothing from the WIP was reverted; every listed fix validated against the code.
- FIX 4 (carrying anchor) needed no code change: P8c is already at baseline (`24d801e`),
  and the WIP only updated `deterministic_greens`' docstring.
- D4/D5/D6 remain open (see §2 residual and `parity-forensics.md` §5); they are outside
  the approved wave-1 fix list.

## 6. Exact commands

```bash
# safety + reconstruction
git diff > /tmp/wave1-fixer-wip.patch
uv run pytest -q -p no:warnings                       # exit 0

# after arm (working tree)
uv run python bench/v2_leaf.py --task bench/corpus/<TASK> --calls 24 \
    --server http://127.0.0.1:8834 --out /tmp/wave1/close/after/<TASK>
uv run python bench/v2_leaf.py --task bench/anchor/A-02-protein-translation --calls 24 \
    --server http://127.0.0.1:8834 --out /tmp/wave1/close/after/A-02-protein-translation

# before arm (pristine baseline worktree)
( cd /tmp/helpagent-base && /home/z/vibe/helpagent/.venv/bin/python bench/v2_leaf.py \
    --task bench/corpus/<TASK> --calls 24 --server http://127.0.0.1:8834 \
    --out /tmp/wave1/close/before/<TASK> )

# health gate before any measurement
curl -sS http://127.0.0.1:8834/health                   # {"status":"ok"}
```

Evidence directories: `/tmp/wave1/close/{before,after}/<TASK>/` (per-task `run.log`,
`run.json`, `trajectory.jsonl`, `grade/`, `work/`); prior worker's data
`/tmp/wave1/{before,after}`.
