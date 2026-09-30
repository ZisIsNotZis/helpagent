# 19 — attribution, claim, and decomposition rules (round 1)

Status: round 1 implemented (delegated worker lane); suite 394 green.
Depends on: ticket 17 (leaf), ticket 18 (tree).

## Why

The matched 9-task × N=2 measurement (blind, reference model) showed the strict
(own-test + judge + independent-test-as-veto) arm was WORSE on what it fixes: 11 actual vs
14 traditional, because 10 of its 11 graded successes were unclaimed and every blocker was a
defective TEST, not bad code. The judge was consulted ZERO times in 36 runs (it only fired on
a model-volunteered blame). One honest failure was ours: a green-on-arrival self-test stopped
the leaf with NO implementation attempt. And the T-31 false success (a request naming two call
sites, the run changing one) had no deterministic answer.

## Owner direction (implemented exactly)

- **A. Proactive multi-label attribution.** The judge fires on a RED report (K=2 consecutive
  red attempts with a material code change, or immediately when the own test cannot be made
  red). Verdict = `implementation_wrong`/`test_wrong`/`spec_wrong`/`environment_broken` +
  reason + evidence. Dominance: spec (bubble) → environment (park needs-user) → test (repair,
  bounded) → implementation (keep implementing). A `test_wrong` label must name a concrete
  defect (deterministic filter).
- **B. Mandatory review when no test can carry verification.** No red target, or a
  non-discriminating repaired test, or an unwritable test path ⇒ a fresh-context reviewer of
  the final diff returns pass/fail WITH concrete evidence. No claim until then.
- **C. A green claim is validated regardless of cause.** Own test a real discriminator (red
  on pristine, now green, unmodified) OR unwritable test path + review pass. The independent
  test is demoted to an extra label (no veto). Per-requirement coverage replaces it.
- **D. Declared test-case contract** (file + function names per AC), verified mechanically
  from the report, boundary-aware; a missing name/file is a distinct repairable failure.
- **E. Per-requirement artifact coverage of the diff** (file paths + symbols named by the
  criterion must appear in the final diff) — the T-31 answer.
- **F. Decomposition by requirement, not by file.** Sibling file sets may overlap; the tree
  serializes overlapping writers and keeps the per-node boundary audit; child ⊆ parent, depth
  and child caps stay. PlanNode guidance updated.
- **G. Nothing else weakened** (report gate, owned paths, write guard, shadow refusal).

## Round 1 — decision → code → test

| decision | code | tests |
| --- | --- | --- |
| A multi-label verdict | `harness/attempts.py` `JudgeVerdict` (+labels, `normalize_judge_labels`) | `test_judge_verdict_is_multilabel_with_a_dominant_summary`, `test_apply_judge_filter_domain_and_coercion` |
| A proactive trigger (K=2) | `harness/leaf.py` loop (`red_code_changes`, `judge_triggered`) | `test_proactive_judge_fires_once_on_the_kth_red_code_changing_attempt` |
| A spec dominates → bubble | `handle_verdict` (`spec_wrong`) | `test_spec_wrong_dominates_and_bubbles_to_the_parent` |
| A environment → park needs-user | `handle_verdict` (`environment_broken`), stop `environment` | `test_environment_broken_parks_needs_user_without_burning_budget` |
| A test_wrong → repair (bounded) | `handle_verdict` (`test_wrong`) | `test_judge_tests_rewrites_the_test_and_later_green_is_green_after_rewrite`, `test_repaired_test_that_cannot_discriminate_switches_to_review` |
| B review mode | `ReviewRequest`/`ReviewVerdict`/`apply_review_filter`, `enter_review`, `run_review` | `test_no_red_target_switches_to_review_and_claims_with_evidence`, `test_apply_review_filter_requires_naming_a_changed_file_or_line`, `test_review_without_evidence_cannot_claim`, `test_review_blocks_the_claim_until_it_passes`, `test_unwritable_self_test_path_switches_to_review`, `test_no_red_target_consults_the_judge_immediately`, `test_no_red_target_environment_verdict_parks_needs_user` |
| B review envelope | `harness/envelopes.py` `LeafReview` (SCHEMAS 25) | `test_envelope_round_trip`, `test_driver_review_defaults_on_and_maps_the_leaf_review_envelope` |
| C own-test claim + iv label | `run_leaf` green path | `test_independent_test_rejection_is_recorded_but_no_longer_vetoes`, `test_vacuous_independent_test_is_rejected_as_not_red`, `test_unobserved_independent_test_is_a_label_not_a_veto`, `test_malformed_independent_test_output_is_recorded_as_a_label`, `test_unaffordable_independent_test_leaves_the_own_test_basis`, `test_iv_repair_that_fails_again_is_recorded_before_the_claim`, `test_iv_red_on_final_is_a_fix_failure_and_is_not_repaired`, `test_incomplete_coverage_after_repair_is_recorded_on_the_outcome` |
| D declared test cases | `DeclaredTestCase`, `_declared_test_case_problems`, `_repaired_test_is_red_on_pristine`, repair path, stop `test-cases` | `test_declared_test_case_present_and_passing_allows_the_claim`, `test_declared_test_case_missing_is_a_repairable_failure_and_blocks_the_claim`, `test_declared_test_case_name_check_is_boundary_aware`, `test_declared_case_repair_must_still_discriminate` |
| E artifact coverage | `RequirementCoverage`, `_requirement_coverage` (claim blocker, no stop) | `test_requirement_artifact_coverage_blocks_a_claim_when_the_named_file_is_untouched`, `test_requirement_coverage_two_call_sites_requires_both`, `test_requirement_coverage_records_symbols_and_skips_unresolvable_text`, `test_t31_untouched_files_are_grader_paths_and_the_write_is_refused` |
| D wiring | `NodeSpec.test_cases`, `ChildPlan`/`PlanNode.test_cases`, `leaf_spec_from` | `test_plan_node_carries_declared_test_cases`, `test_a_child_carries_declared_test_cases`, `test_leaf_spec_from_carries_declared_test_cases` |
| F sibling overlap allowed + serialized | `harness/node.py` `validate_decomposition`; `tree_run` sequential children | `test_sibling_files_may_overlap_and_boundaries_still_narrow`, `test_path_canonicalization_keeps_boundary_narrowing_honest`, `test_overlapping_siblings_are_allowed_and_serialized`, `test_boundary_audit_still_holds_for_overlapping_siblings` |
| F planner splits by requirement | `_plan_node_question` | `test_planner_guidance_splits_by_requirement_and_declares_test_cases` |
| record fields (item 3) | `bench/v2_leaf.build_record`, `bench/v2_tree.node_record`/`build_record` | `test_run_record_carries_the_verification_basis_and_coverage`, `test_run_record_carries_the_attribution_labels`, `test_tree_run_record_carries_the_new_leaf_fields` |

## New stops / basis values

- stop_reason `environment` (park needs-user, budget preserved), signal `honest-failure`,
  `needs_user=True`.
- stop_reason `test-cases` (a declared test case is still missing/unpassed after the repair).
- Per-requirement artifact coverage is a CLAIM BLOCKER, not a stop: it is recorded as
  `coverage_missing` / the `requirement_uncovered` event and the loop keeps working.
- claimed_basis `review` (review-based verification); `verification_basis` `"test" | "review"`.
- `red_code_changes`, `judge_triggered`, `review_verification`, `requirement_uncovered`,
  `test_case_repair`, `independent_test_uncollected`, `review_verdict` ledger events.

## Residual risk

A wrong green can still claim by TWO routes, both recorded (not silent):
1. own-test route — the test discriminates (red on pristine) and greens on a wrong fix whose
   named artifacts were touched; per-requirement coverage only proves the named files/symbols
   moved, never the behavior (the accepted DESIGN §10.8a residual). A declared-case repair is
   re-proved RED on the pristine source in a private copy, so it cannot smuggle in a weakened
   test; but it is still the same weak model that authored both tests.
2. review route — when no test can carry verification, a reviewer of the same weak model
   approves a plausible diff; the deterministic filter only requires evidence naming a changed
   file/line. This is the widest residual band and the reason the default keeps the own-test
   claim whenever a test can carry it.

The grader remains the only ground truth. Open tuning item: symbol extraction in coverage can
over-gate (a request-wide symbol the run did not touch blocks the claim), trading false
success for missed success — measure before tightening or loosening.

## Measurement plan (not run in round 1 — sweeps are out of scope)

Re-run the matched 9×2 comparison with the default rule (own test + proactive judge + coverage
+ review) against the traditional and strict arms; watch for true/missed/honest/false and
calls. Any false success is a blocker; a large missed-success band at ~2× calls is the
tuning target for coverage strictness (symbol extraction).

---

# 19 round 2 — the adversarial holes (implemented)

Status: round 2 implemented (delegated worker lane); suite 403 green (394 round-1 tests,
4 renamed/updated for superseded decisions, 9 added). No benchmark sweep was run.

An independent adversarial verification of the round-1 claim rules, plus the blind
measurement, found five concrete holes. They are fixed in `harness/leaf.py` (with the new
`malformed_steps` / `coverage_unresolved` fields surfaced by `bench/v2_leaf.build_record`
and `bench/v2_tree.node_record`).

## Round 2 — finding → code → test

| finding | code | tests |
| --- | --- | --- |
| F1 review evidence must name a REAL diff artifact; a bare `line N` no longer bypasses; an unchanged tree can never claim | `_evidence_names_an_artifact` (drop `_LINE_REF` bypass; require a changed path or a symbol in a changed file's final text; empty `ReviewRequest.final` ⇒ False); `_review_request` uses the stripped diff | `test_apply_review_filter_requires_a_changed_artifact_not_a_bare_line`, `test_review_of_a_no_op_diff_cannot_claim` |
| F2 an unresolvable criterion is NOT skipped — a DECLARED discriminating test must carry it; an empty criteria list cannot claim on the test basis | `_criterion_unresolved`, `_declared_case_index`, `_declared_case_discriminates`; claim path blockers `coverage_unresolved` / `criterion_unresolved`; empty-criteria force-review + `no-acceptance-criteria` | `test_unresolved_criterion_is_carried_by_a_discriminating_declared_test`, `test_unresolved_criterion_without_a_declared_test_cannot_claim`, `test_empty_acceptance_criteria_cannot_claim_on_the_test_basis`, `test_empty_acceptance_criteria_forces_review_and_claims_with_evidence`, `test_requirement_coverage_records_symbols_and_flags_unresolvable_text` |
| F3 file coverage satisfied by a comment/unrelated edit; symbol coverage by a pre-existing token | `_stripped` (comments + whitespace); `_changed_files` and `_review_request` compare stripped | `test_comment_only_edit_is_not_a_change`, `test_symbol_that_only_moved_in_a_comment_is_not_covered`, `test_changed_files_ignore_comments_and_whitespace` |
| F4 a declared test carried by a placeholder | the F2 discrimination check (red on pristine, green on final) | `test_unresolved_criterion_with_a_placeholder_declared_test_cannot_claim` |
| F5 malformed output ended the node (missed successes) | `request_bounded` records the step and never stops; `request_envelope` (self-test) is budget-bounded; every call site continues (implement/judge/review/rewrite/test-cases); `malformed-output` removed from `STOP_REASONS` | `test_malformed_self_test_envelope_is_retried_then_the_node_continues`, `test_a_raising_model_never_crashes_the_leaf`, `test_malformed_implement_envelope_does_not_end_the_node`, `test_malformed_judge_output_is_recorded_and_the_node_continues`, `test_malformed_test_rewrite_is_recorded_and_the_node_continues`, `test_malformed_steps_are_recorded_on_the_run_record` |

## New reason / event values

- stop_reason `no-acceptance-criteria` (empty criteria list, no reviewer ⇒ no test-basis
  claim). stop_reason `malformed-output` is REMOVED: a malformed envelope consumes its
  calls and the node continues (bounded by calls/attempts/ladder).
- claim blockers (kept working, not stops): `coverage_unresolved` + `criterion_unresolved`
  event (an unresolvable criterion with no declared discriminating test).
- events `envelope_malformed_step`, `judge_unavailable`, `no_acceptance_criteria_claim_blocked`;
  outcome/record fields `coverage_unresolved`, `malformed_steps`.

## Round-2 residual routes (not closed here)

- F1: review evidence still matches a CHANGED file by basename, so a different same-named
  file can be cited; and a symbol that pre-existed in a really-changed file still counts
  (the accepted "behavior changed" note). The stripped-diff relaxation in F3 removes only
  comment/whitespace-only edits.
- F2/F4: the declared-test discrimination check is only applied on the TEST basis; in
  review mode the reviewer's grounded evidence (F1) is the only carrier.
- Coverage over-gating from round 1 is unchanged (a request-wide symbol the run did not
  touch still blocks the claim).
