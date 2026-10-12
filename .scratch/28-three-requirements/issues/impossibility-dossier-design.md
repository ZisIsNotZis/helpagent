# Impossibility dossier — pre-registered mechanism space, experiment matrix, and decision rule

READ-ONLY design task. No code and no existing document was modified. This is the third and
only other output of the same task as `verification-decomposition-forensics.md` and
`ablation-protocol.md`; read those first for the per-stage information analysis and the R2/R3
ablation arms. This file owns the *end-state decision*: how the project will decide, from
evidence frozen in advance, between

* **D1 — parity**: "our harness reaches or beats `pi` on pure coding within error margin", and
* **D2 — bounded impossibility**: "no mechanism in the enumerated space can beat `pi`".

**Why this is written now.** STATUS §8e/§8f/§8g/§8h already contain the *baseline* results
(ours 24–26/40 vs `pi` 27/40; one false success in §8g, zero on the §8h probe). The
pre-registration cannot be blind to those. It is blind only to the **new mechanism-arm
results**, which do not exist yet. Every threshold, task set, seed count, error-bar method and
verdict condition below is fixed at this revision and must not be changed after a mechanism
arm is run. If a number below is later edited, the edit must be dated and justified **before**
the affected arm runs, or the conclusion is void.

**Revision pin:** git `72538ab` (working tree also carries untracked `bench/v2_measure.py`,
`tests/unit/test_v2_measure.py`, and this `.scratch/28-three-requirements/` directory).
**Model/server pin:** Spark-X2.5-4B Q4_K_M on llama.cpp, `-c 32768 --cache-type-k q8_0
--cache-type-v q8_0`, port 8834. **Arbiter:** the corpus's own withheld tests
(`bench/external_score.py::external_score`), never the harness's claim (STATUS limit 2,
FLOW §4 H6). **One writer / one lane** (`.scratch/active-work.md`).

**Terminology, fixed once here.**
* `actual` = the external grader's verdict (`results.jsonl` `actual` / `delivery.grader_passed`).
* `false success` = `claimed and not actual`.
* `Δ(X vs Y)` = paired per-task difference `actual_X(t) − actual_Y(t)`, averaged over seeds.
* `M` = the pre-registered **parity margin in tasks** (out of 40); see §2.6.
* "mechanism in the space" = a row of the §1 ledger with an implemented or named-proposed toggle.
* "arm" = one frozen configuration of a mechanism, run on a pre-registered task set and seed count.

---

## 0. The two decisions, and why they need different rules

D1 is a **non-inferiority test of our harness against `pi`**. It is decidable by a finite paired
experiment.

D2 is an **impossibility-flavoured claim**. It cannot be proven by any finite experiment: the
mechanism space is a model of what could be tried, not the set of all possible harnesses. D2 is
therefore defined operationally as *bounded spectral exhaustion* — "every mechanism in the §1
ledger was run or bounded, and none moved the grader pass rate past `pi` by `M`" — and its
epistemic bound is stated honestly in §3.4. The two rules share the metric definitions of §2
but are decided separately; a D2 verdict is never allowed to be inferred from D1 alone (two
different configurations can both lose to `pi` without exhausting the space).

---

## 1. MECHANISM SPACE (the exhaustive ledger)

**Completeness argument.** This ledger is the union of: every mechanism in STATUS §3
(tried-and-failed), §2a (designed-not-built), §6 (recommended next steps), §8e (residual
mechanisms); FLOW §2/§4/§6/§7 and DESIGN §10; every named fix site in
`verification-decomposition-forensics.md` §2/§4/§5; the `ABLATIONS`/`VERIFY_MODE_STAGES` arms in
`ablation-protocol.md` §2; and every toggle found by reading `harness/leaf.py`,
`harness/tree_run.py`, `harness/how.py`, `harness/node.py`, `harness/model.py`,
`harness/staging.py`, `harness/knowledge.py`, `bench/v2_leaf.py`, `bench/v2_sweep.py`,
`bench/v2_tree.py`, `bench/pi_baseline.py`, `bench/v2_measure.py`. A mechanism proposed in the
forensics doc but not yet built is marked **[proposed]**; it is still part of the space and must
have an arm (or a recorded reason it cannot be built) before D2.

**Status tags.** `[PASS]` can raise the grader pass rate; `[LIE]` can cut false successes;
`[BOTH]`; `[CTRL]` a settled control that must be held constant, not a free variable;
`[HARM]` measured harmful (STATUS §3) and kept off.

**Line numbers** are at revision `72538ab` (leaf.py is the untracked-at-birth v2 leaf; verify
with `grep -n '<function>' harness/leaf.py` if the tree moves).

### (a) Prompt / context injection

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| A1 | **Full source view** (no hidden index) | `harness/leaf.py::SOURCE_VIEW_MODE` (5339) → `source_view_mode()` (5342) / `_source_view_bounded` (5413) | the model must see the file that *defines* a value, not only the file where the symptom shows (FP-7, T-01); the bounded index was measured harmful (13/24 vs 18/24) | tokens/run (≈16k vs bounded) | set `SOURCE_VIEW_MODE="bounded"` to disable; `"full"` is current `[PASS]` |
| A2 | **Byte-stable context + KV prefix** | `harness/leaf.py::_stable_context` (5448); `harness/model.py::LlamaServerRunner._payload` `cache_prompt` (161) | a repeated prefix rides the server KV cache → same context, lower cost (`cache_hit` telemetry) | none extra | `cache_prompt` True/False; de-duplication in `_stable_context` `[CTRL]` |
| A3 | **Own-test desired-state rule** | `harness/leaf.py::_SELF_TEST_DESIRED_STATE_RULE` (926), injected by `_self_test_artifacts` (5249) as `test_target_rule` | a self-test that asserts the *desired* end state stops the model from reading the reported symptom back as the requirement (T-01) | one constant | remove the `test_target_rule` key from the artifacts to disable `[PASS]` |
| A4 | **Ladder prompt leads** (L2/L3/L4/L5) | `harness/leaf.py::_implement_question` (5202) | "enumerate fix steps" / "check the defining file" / "apply deterministic diagnosis" / "a review is watching" each add a signal to one implement write | one call per rung | driven by `Escalation.strategy` (see D1); blank `esc.strategy` disables `[PASS]` |
| A5 | **Named implement targets (F2)** | `harness/leaf.py::_implement_targets` (5181) + `_implement_question(..., targets=)` (5202) | naming the file the request/test already names stops a blind model re-emitting the unchanged file (T-05) | none | pass `targets=()` to disable `[PASS]` |
| A6 | **Writable / frozen / untouched lists** | `harness/leaf.py::_request_artifact_messages` (2953), emitted in `_implement_artifacts` dict (5139) | tells the model which file is frozen, so it redirects instead of refusing for six attempts (T-01) | none | omit the `writable_files`/`frozen_files`/`untouched_required_artifacts` keys `[PASS]` |
| A7 | **Repository documentation injected** | `_stable_context` `repo_documentation(spec)` (5448) + `documented_api_names` (3878) | the README is the stated API contract (T-28/T-26); hiding it makes a documented API "missing" | tokens | include/exclude the `repository documentation:` block `[PASS]` |
| A8 | **Knowledge pack** (signatures/callers/constants) | `harness/knowledge.py::build_knowledge` (71); wired only in `bench/golden_bugfix.py:375` (`KNOWLEDGE` flag) | cross-file call-site map for multi-file threading (T-31); FP-4/FP-7 remedy | ≤48 rendered lines | `KNOWLEDGE` global; **not wired into the v2 leaf driver** — turning it on is a code change `[PASS]`, measured no gain in §3 |
| A9 | **[proposed] IV desired-state rule** | `bench/v2_leaf.py::_independent_test_question` (707) — append `_SELF_TEST_DESIRED_STATE_RULE` | removes the inverted-IV class at its source: T-06/T-10/T-12/T-19 all assert the pre-fix behaviour the request removes | one constant | add the rule line; absence is today's state `[PASS]` |
| A10 | **Review angles** | `harness/leaf.py::REVIEW_ANGLE_PROMPTS` (672), `review_angles_for_level` (812), `_review_request` (4084) | a declared contract read ("another agent confirms") catches what a test written by the same model misses | one call/angle | `planned_reviews` list; empty disables `[BOTH]` |
| A11 | **Judge prompt + deterministic filter** | `harness/leaf.py::apply_judge_filter` (3728), `ATTRIBUTION_RED_K` (3525) | a fresh-context blame read stops the loop churning against its own wrong test (T-01/T-31) | one call per red | `--judge/--no-judge`; K constant `[PASS]` |

### (b) Verification & claim strategy

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| B1 | **Verification-mode ladder** | `harness/leaf.py::VERIFICATION_MODES` (426), forced in `bench/v2_leaf.py::run_once` (807) | isolates the contribution of each stage: raw (dev only) / test / review / full | calls | `--verify {raw,test,review,full}`, `--judge/--iv/--review` `[PASS]` |
| B2 | **Self-test red→green loop** | `harness/leaf.py::_self_test_artifacts` (5249), `_retry_self_test_artifacts` (5271), `run_self_test` path in `run_leaf` (5583) | a forced discriminating test pins the goal for the implement write | calls (≈5/run, STATUS §1a) | `--verify raw` disables `[PASS]` |
| B3 | **Independent verification (IV)** | `harness/leaf.py::_iv_request` (4318), `evaluate_independent_test` (4917), `_iv_repair_request` (4351), `iv_verdict_for` (5898) | a fresh author that never sees the own test catches a wrong fix | calls | `--iv/--no-iv` `[PASS]` |
| B4 | **Non-discriminating IV cannot carry** | `harness/leaf.py::iv_verdict_is_non_discriminating` (1833) → `claim_decision` input `iv_non_discriminating` (1958) | a test green/error-only on the pristine source proves nothing and must not corroborate a pass (T-30) | none | already on; remove the input to disable `[LIE]` |
| B5 | **Per-criterion inversion split** (generalise `all_inverted` to mixed files) | `harness/leaf.py::iv_inversion_evidence` (1774), `iv_all_inverted` (1801), used by `iv_red_on_final` (6797); `evaluate_independent_test` early return at 4998 | a mixed IV file (one symptom-asserting case + one genuine case) reds a correct fix as an undifferentiated failure (T-21/T-35); split inverted vs unmet before blocking | none (reuses the two gate reports) | today only `all_inverted` is excused; extending it is **[proposed]** `[LIE]` |
| B6 | **[proposed] Re-sample ≠ fresh verdict** | `harness/leaf.py::final_verification` (6988) + `iv_verdict_for` (5898) | `final_verification` re-authors a new IV on exhaustion, so a red-on-final can be replaced by an approving sample that carries the claim (T-35 false success); a re-sample must not upgrade the basis above `review` | none | label the re-sample `independent-test-resampled` and clamp the basis `[LIE]` |
| B7 | **Review outranks a conflicting test** | `harness/leaf.py::claim_decision` rule 4 (1958) | the owner's precedence rule: a graded review decides over the model's own test; buys true claims (STATUS §1) | one review call | supply/omit `review_approved` `[BOTH]` |
| B8 | **RED IV blocks a review-backed claim** | `claim_decision` rule 4 (1958); `iv_red_on_final` (6797) | a fresh discriminating verification that failed may not be overridden by the review (T-14 #2) | none | already on `[LIE]` |
| B9 | **Grant-calibre review evidence** | `harness/leaf.py::_evidence_is_grant_calibre` (4203), `apply_review_filter` (4215) | "looks correct" cannot grant; the reviewer must name a criterion + an observable | none | already on `[LIE]` |
| B10 | **Carrying deterministic anchor (P8c)** | `harness/leaf.py::_CARRYING_ANCHORS` (1890), `deterministic_greens` (1893) | model-written tests and reviews may corroborate but not carry; only `documented-api` / `no-regression` carry (A-02). Costs claims (§8h) | none | already on; drop the `_CARRYING_ANCHORS` branch to disable `[LIE]` |
| B11 | **Request-level coverage** | `harness/leaf.py::_request_coverage` (2919) → `claim_decision` gate 3b (1958) | a request that names N call sites is not done until the diff touches all N (T-31) | none | already on `[PASS/LIE]` |
| B12 | **Per-criterion coverage** | `harness/leaf.py::_requirement_coverage` (2790) → gate 3 (1958) | a named artifact left untouched blocks the claim; the only gate that fixed T-33 | none | already on `[PASS/LIE]` |
| B13 | **Regression check** | `harness/regression.py::RegressionCheck` (66), `visible_test_files` (95); `regression_now` in `run_leaf` | visible suite green before, red after = regression blocks | one suite run | already on; **unobservable on this corpus** (STATUS limit 7) `[LIE]` |
| B14 | **Documented-API check** | `harness/leaf.py::documented_api_names` (3878), `documented_api_problem` (4039) | a name the repo's own docs present in call form must not be swallowed by a class (T-28) | none | already on `[LIE]` |
| B15 | **[proposed] Review attributed to the revision it saw** | `harness/leaf.py::_source_revision_fingerprint` (3284) + `combine_review_verdicts` (857) | a later round may approve a revision an earlier round rejected without the bytes changing (T-26/T-28); require the approving round's fingerprint | one field | record + compare the fingerprint `[LIE]` |
| B16 | **Judge consultation threshold** | `harness/leaf.py::ATTRIBUTION_RED_K` (3525), `apply_judge_filter` (3728) | K=1 asks the judge on the first materially-changed red, stopping churn against a wrong test | one call/red | K constant; `--no-judge` `[BOTH]` |
| B17 | **No-change delivery block** | `harness/leaf.py::_delivery_is_unchanged` (3257) → `claim_decision` gate (1958) | a byte-identical / whitespace-only delivery cannot claim (T-05/T-13/T-16/T-34) | none | already on `[LIE]` |
| B18 | **Verification covenant / tier** | `harness/leaf.py::verification_floor` (577), `enforce_verification` (6235) | the plan's declared verification tier must be met before a claim | none | already on `[LIE]` |

### (c) Decomposition & multi-approach exploration

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| C1 | **Leaf vs tree** | `bench/v2_leaf.py::run_once` (798) vs `harness/tree_run.py::run_tree` (2315) | the tree can split a genuinely multi-part request that the one-write leaf cannot (T-31/T-14/T-26/T-28) | calls | driver choice `[PASS]` |
| C2 | **How list: greedy vs tournament** | `harness/tree_run.py::_run_hows` (1380); `--how-explore` (`bench/v2_tree.py:536`); `harness/how.py::how_exploration_limit` (727); `how.pick` (523); `select_key` (493) | parallel candidates sampling the same model can find a better fix | ≈5× calls & wall (STATUS §3) | `--how-explore 1` (greedy, default) vs `3` `[PASS]` |
| C3 | **Decompose into children** | `harness/node.py::decomposition_from_envelope` (206), `_plan_node_question` (534) | one child per declared file / documented behaviour; each child a leaf with its own write boundary (T-31/T-14/T-26/T-28) | one plan call + children | non-empty `children` in the plan envelope `[PASS]` |
| C4 | **Forced-leaf thresholds** | `harness/tree_run.py::FORCED_LEAF_MAX_FILES` (169), `FORCED_LEAF_MAX_ACS` (170) | small nodes are forced monolithic; a measurement must vary these or the delta is confounded | none | constants `[PASS]` |
| C5 | **Budget split** | `harness/node.py::split_weighted` (459), `can_decompose` (449) | funds children from the node pool | none | weights `[CTRL]` |
| C6 | **Split repeat-refusal** | `harness/node.py::SplitHistory.accept` (498) | an identical split is refused | none | already on `[CTRL]` |
| C7 | **Sequential How retries** | `harness/tree_run.py::SEQUENTIAL_HOW_LIMIT` (177); `harness/how.py::decide_after_failure` (610) | next approach after a confirmed failure, one candidate at a time | calls | constant `[PASS]` |
| C8 | **Multi-file write path** | `harness/leaf.py::_write_one` (8846) + `_request_implement` (5485) | every file in the envelope is written in one revision; the historical "one file per attempt" seam is gone (forensics §4.3) | none | envelope `files` list `[PASS]` |
| C9 | **[proposed] Coverage-rank the best-evidence revision** | `harness/leaf.py::_erase_draft` (3025), `_mode` (3488), `capture_best_evidence` (5767), `BEST_EVIDENCE_ORDER` (3080), `BestEvidenceRevision` (3092) | M1 erase + evidence-ranked capture can lose a more complete multi-file revision to a partial one (T-31) | none | rank by (request-coverage, then evidence) `[PASS]` |
| C10 | **M1 erase / M2 keep-draft** | `harness/leaf.py::_mode` (3488), `_erase_draft` (3025) | M1 regenerates from failure history "as your only intelligence"; M2 keeps the draft | calls | mode selector; M2 for refused writes already forced `[PASS/LIE]` |

### (d) Iteration / escalation strategy

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| D1 | **Escalation ladder L1–L5** | `harness/leaf.py::LADDER` (358), `STRATEGY_LAYER` (371), `escalate` (2422), `_is_repeat` (2400) | each rung adds a distinct signal; a wasted rung is refused | calls | rung index; disable rungs `[PASS]` |
| D2 | **Exhaustion / repeat refusal** | `harness/attempts.py::exhausted` (241), `prefilter` (214) | stops identical retries (the T-01 six-refusal loop) | none | `consecutive_same` `[PASS]` |
| D3 | **Judge threshold K** | `ATTRIBUTION_RED_K` (3525) | one red→judge saves the ladder | call | constant `[PASS]` |
| D4 | **Best-evidence checkpoint/restore** | `harness/leaf.py::capture_best_evidence` (5767), `BestEvidenceRevision` (3092) | the strongest-evidenced revision is delivered, not the erased baseline | none | already on `[LIE]` |
| D5 | **Budget / deadline** | `harness/budget.py`; `bench/v2_leaf.py` `--calls` (936) / `--deadline-hours` (937) | wall-clock is the primary budget | setting | args `[CTRL]` |
| D6 | **Node re-plan triggers** | FLOW §6.2; `harness/tree_run.py::_apply_decomposition` (1237) | a `spec`-blame re-plans the subtree | calls | manager `[PASS]` |
| D7 | **Early exit on a same-verdict tail** | `harness/attempts.py::exhausted` (241) | stop burning calls on identical attempts | none | already on; this is the T-01 exit that the write-guard could not redirect `[PASS]` |

### (e) Decoding / model configuration

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| E1 | **Temperature** | `harness/model.py::LlamaServerRunner.__init__` (80) `temperature=0.2` | lower → reproducibility; higher → candidate diversity | none | ctor arg; **no CLI passthrough** (ablation-protocol §8.9) `[PASS]` |
| E2 | **Output ceiling** | `harness/model.py::MAX_TOKENS` (45) `=3000`; `_payload` `max_tokens` (155) | a 3k output cap truncates verbose thinking (STATUS §8b) | none | ctor arg `[PASS]` |
| E3 | **Grammar-constrained JSON per step** | `harness/model.py::schema_json` (95), `_branch_grammar` (104), `_payload` `response_format` (150) | a parseable two-branch envelope every call | none | already on `[CTRL]` |
| E4 | **In-run thinking disabled** | `harness/model.py::_payload` `chat_template_kwargs enable_thinking:False` (158) | a thinking preamble empties the content and burns budget (ticket 01) | none | flag; `pi` uses `--thinking`/`--reasoning` `[CTRL]` |
| E5 | **KV cache reuse** | `harness/model.py::_payload` `cache_prompt` (162) | lower cost for the stable prefix | none | flag `[CTRL]` |
| E6 | **Server context window** | server `-c` (8192 vs 32768); STATUS §8c | 32k bought *agency* (T-31) but not authoring (anchors 0/5) | infra | server config `[PASS]` |
| E7 | **Model** | Spark-X2.5-4B Q4_K_M (both arms) | the model is the ceiling candidate; a stronger model is out of scope | n/a | swap GGUF `[CTRL]` |
| E8 | **Retry budgets** | `harness/model.py::TRANSPORT_ATTEMPTS` (46); `harness/leaf.py::ENVELOPE_RETRIES` (910), `JUDGE_RETRIES` (919) | transport/envelope robustness | calls | constants `[CTRL]` |
| E9 | **Best-of-n sampling** | `harness/model.py::complete_n` (208); `harness/runner.py:272` | sampling diversity for one step | n calls | `best_of_n` `[PASS]` |

### (f) Task representation

| ID | mechanism | file :: function (exact toggle) | hypothesis | cost | on / off |
| --- | --- | --- | --- | --- | --- |
| F1 | **Acceptance-criteria extraction** | `bench/v2_leaf.py::extract_acs` (235) | sentence-/bullet-per-AC from `request.md`; a bad split mis-states the requirement | none | replace the extractor `[BOTH]` |
| F2 | **LeafSpec shape** | `harness/leaf.py::LeafSpec` (1072) | goal / interfaces / files / grader_paths define exactly what every step sees | none | fields `[CTRL]` |
| F3 | **Blind staging** | `harness/staging.py::stage_blind` (143), `source_only` (138), `excluded_paths` (133), `withheld_path` (128) | the grader's tests never enter a run; cache artifacts withheld (leak retraction) | none | already on `[CTRL]` |
| F4 | **Frozen / grader-owned paths** | `bench/v2_leaf.py::build_spec` `grader_paths` (306); corpus `UNTOUCHED` | byte-identity contract (T-33); a write there is a recorded deviation, restored before grading | none | already on `[CTRL]` |
| F5 | **External grader** | `bench/external_score.py::external_score`; `bench/v2_leaf.py::run_once` `delivery` event (861) | the only correctness arbiter | n/a | already on `[CTRL]` |
| F6 | **Task set / bands** | `bench/corpus/T-01..T-35` + `bench/anchor/A-01..A-05`; `bench/v2_measure.py::PI_BANDS` (69) | band-stratified analysis | n/a | task list `[CTRL]` |
| F7 | **Declared test cases (tree)** | `harness/how.py::planned_test_points` (332), `TestPoint` (306) | the How declares what each test pins | none | plan `[PASS]` |
| F8 | **Declared review angles (leaf driver)** | `bench/v2_leaf.py::build_spec` `planned_reviews=("ac-correctness","contract-compat")` (317) | the leaf driver's fixed two-angle fallback | calls | list `[BOTH]` |
| F9 | **Deviation restore before grading** | `bench/v2_leaf.py::run_once` `restore_deviations` (860) | the grader sees the same bytes the run's outcome describes | none | already on `[CTRL]` |
| F10 | **Multi-part tail** | corpus `T-31`, `T-33`, `T-28`, `T-14`, `T-26` | the subset where decomposition could show a delta (forensics §4.4) | n/a | subset `[CTRL]` |

**Settled controls** (must not vary inside one comparison): F3/F4/F5/F9 (blind staging, frozen
paths, external grader, deviation restore), E3/E7 (grammar, model), D5 (budget), one writer.
**Measured-harmful, kept off** (must not be re-enabled as a "new mechanism" without a fresh
pre-registration): bounded source index (A1 bounded), deterministic file-change order, the
module-importer write spec, the competitive tournament as a default (C2 at `how_explore>1` is a
measurement arm, not a default), the knowledge pack as a default (A8).

---

## 2. PRE-REGISTERED EXPERIMENT MATRIX

### 2.1 Arms

* **Reference (fixed, external):** `P1` = `bench/pi_baseline.py --thinking max --reasoning`
  (A1), 40 tasks; `P2` = `P1 --append-prompt <prompt>` (A2), 40 tasks. `P2` is **environment-
  blocked** today (STATUS §8e: `no assistant message`/`Connection error` while an unrelated GPU
  job holds VRAM). Until `P2` runs, C4/"structure beats a better prompt" is **unmeasured** and
  D1 is decided against `P1` only, with that stated.
* **Harness baseline `H0`:** current best configuration — `--verify full`, judge/IV/review on,
  all §1 `[LIE]`/`[PASS]` mechanisms at their `72538ab` default.
* **Mechanism arms `H0+M_i`:** one mechanism row added to (or removed from) `H0`, one at a time
  (OFAT), with the exact toggle from §1. A proposal that needs code (A9, B5, B6, B15, C9) is an
  arm only after it is built; until then it is `unmeasured` and blocks D2.
* **Stage-ladder arms (from the ablation protocol, reused not redefined):** `A0 raw`, `A1 test`,
  `A2 full --no-review`, `A3 full --no-iv`, `A4 full`; subtractive `--ablate
  {none,independent-test,review,own-test}`.
* **Decomposition arms (tail):** `B0` leaf (`bench/v2_leaf.py`), `B1` greedy tree
  (`--how-explore 1`), `B2` tournament tree (`--how-explore 3`), plus `C3` children on.

### 2.2 Tasks

* **Full set (D1 primary):** all **40** tasks — `bench/corpus/T-01..T-35` (35) +
  `bench/anchor/A-01..A-05` (5).
* **Pre-registered tail subset (D1 secondary + D2 decomposition):** the five multi-part tasks
  named in the objective — **T-31, T-33, T-28, T-14, T-26**. (See §6 contradiction 1: these are
  *inside* the 40, so the tail is a subset for extra seeds (N ≥ 9), not an addition.)
* **Reduced screen set (cost control, from the ablation protocol §3):** T-06, T-10, T-12, T-19,
  T-20, T-21, T-22, T-35 (inversion class) + T-01, T-05, T-16, T-27, T-28, T-30 (delivery/claim
  class) = 14 tasks that carry the measured effect.
* **Easy/mid regression control (decomposition only):** T-02, T-05, T-14, T-20, T-25, T-31.

### 2.3 Seeds (N)

No RNG seed exists: `harness/model.py::LlamaServerRunner.__init__` fixes `temperature=0.2` and
exposes no seed, so a "seed" is an independent stochastic repeat (`--n`). Pre-registered, and
**adopted from the sibling power analysis** (`parity-forensics.md` §4; the ticket
`28-three-requirements.md` Q1 states the same numbers): the 40-task run-to-run difference has
SD ≈ **2.0 tasks** (tail ≈ 3.4). Therefore:

* **N ≥ 9 seeds per arm** to make any **parity-within-margin** statement (binds the two-arm 95%
  interval to ≈ ±3 tasks).
* **N ≥ 17 seeds per arm** to claim a **win** (80% power to detect a 3-task difference).
* **N ≥ 38 seeds per arm** to resolve a **2-task** difference.
* **N = 5 on the reduced 14-task screen** (an explicitly **underpowered screen**: it may
  nominate a mechanism arm for confirmation but can never produce the D1/D2 verdict); the
  5-task tail subset at **N ≥ 9**, and the easy/mid decomposition control at N=5.
* **`pi` must be re-run at the same N** as `H*` before any parity claim — `pi-maxed-20261006`
  is N=1 per task, so its variance is unmeasured (parity-forensics §4/§6).
* A single seed produces **no error bar** (`bench/v2_measure.py::stdev` guards n<2), so N=1
  cannot decide anything.

### 2.4 Metrics

Per run (already in `results.jsonl`/`run.json`): `actual`, `claimed`, `false_success =
claimed && !actual`, `stop_reason`, `claimed_basis`, `calls`, `run_wall_s`, `tokens_total`
(summed `prompt_tokens`+`completion_tokens`; `bench/v2_measure.py::read_token_usage`),
`self_test`, `iv_verdicts`, `review_verdicts`, `changed_files`.

Primary endpoints: **actual pass count / 40**, **false-success count**, **tokens/task**,
**single-lane wall s/task** (`--wall-clock`, one sequential pass, no concurrent lane —
ablation-protocol §8.10).

### 2.5 Error-bar method

* **Task-clustered percentile bootstrap.** For an arm pair `(X,Y)`, build the paired per-task
  difference vector `d_t = mean_seed(actual_X(t)) − mean_seed(actual_Y(t))` over the T tasks.
  Report `mean(d)`, `sd(d)`, and a **95% percentile bootstrap CI** from **10 000** resamples of
  the T tasks (seeds resampled within a task), **bootstrap seed fixed at 20261013** (recorded;
  the same seed for every comparison).
* **Head-to-head counts:** also report the paired 2×2 (X-only / Y-only / both / neither) and an
  **exact McNemar** p-value on `actual`.
* **Single-arm rate:** Wilson 95% interval (do not use the normal approximation at n=40).
* **Noise floor and seeds:** the 40-task run-to-run difference SD is ≈ **2.0 tasks** (tail ≈ 3.4;
  parity-forensics §4). No arm difference smaller than the paired CI excluding 0 is called a
  result; a difference below 3 tasks with a CI that includes 0 is **inconclusive**, never "no
  effect". Parity needs **N ≥ 9** seeds/arm, a win **N ≥ 17**, a 2-task resolution **N ≥ 38**
  (§2.3).
* **Monotone-adjustment control:** because up to ~20 mechanism arms are screened, report both
  the raw 95% CI and a Bonferroni-adjusted threshold (α = 0.05 / number_of_arms) for any claim
  that a mechanism beats `H0`.

### 2.6 The numeric decision rule

**Margin `M` (fixed before any mechanism arm).**

* **`M = 3` tasks (7.5 pp)**, the smallest deficit the measured 40-task run-to-run noise cannot
  explain: the difference SD is ≈ 2.0 tasks (tail 3.4), so the campaign gap (Δ = 3 tasks) is only
  ~1.5 SD (`parity-forensics.md` §4). `M` is quoted from that variance analysis, not chosen to
  fit any observed result, and it is fixed at this revision.
* **Phase 0 (calibration, baseline arms only):** run `H0` and `P1` on the 40 tasks with N ≥ 9 and
  compute the paired difference SD `s` (tasks). `M` is **held at 3** unless Phase 0's `s` differs
  from 2.0 by more than 1 task, in which case `M` is re-derived as `max(3, round(1.5 × s))` and
  **frozen before any mechanism arm runs**. Record `s` and the final `M` in the measurement
  root's `summary.json`. Choosing `M` after a mechanism arm runs voids the conclusion.
  (The CI half-width, not `M`, is what shrinks with N — the CI is the `Lo95`/`Hi95` above; `M`
  is the fixed non-inferiority bound the CI is compared against.)
* The main-agent decision and the reviewer must re-check `M` against the Phase-0 record.

**D1 — parity test (one-sided non-inferiority).** With `H*` = the best mechanism arm by
Phase-2 `actual` (ties → smaller tokens, then smaller wall), and `Δ = actual(H*) − actual(P1)`
paired by task and averaged over seeds:

| condition | verdict |
| --- | --- |
| `Lo95(Δ) ≥ −M` | **PARITY ACHIEVED** (our harness reaches/beats `pi` within margin) |
| `Hi95(Δ) < −M` | **INFERIOR** (documented, with the per-task losses) |
| otherwise | **INCONCLUSIVE** — add seeds to the 40-task arm; do not resolve by argument |

For a **"beats `pi`"** reading (C1's first clause) the rule is stricter: `Lo95(Δ) > 0` at
**N ≥ 17**. Note the honest arithmetic the sibling analysis already worked out: with the 40-task
difference SD at 2.0 tasks, the recorded Δ = −3 (24 vs 27) at N = 9 lands **inconclusive**
(neither parity nor inferior), and even the current-revision Δ = −1 may need more seeds; the
rule is written so it cannot be tuned to declare parity on today's evidence.

**Secondary conditions for D1 to count as "coding parity" (both reported, neither may be
silently dropped):**

* **no-lie:** `false_success(H*)` must be `≤ false_success(P1)` on the same 40 tasks, and the
  task-clustered CI on the false-success difference must not show ours worse by more than 1
  task. (`pi`'s "claimed" is a regex read with no claim gate — STATUS §8c — so only the counts
  and the grader verdict are comparable.)
* **cost:** tokens/task and single-lane wall s/task are reported for both arms. Because `pi`'s
  131 s is sequential and our 190.5 s was measured under 4-way concurrency, **the wall
  comparison is not decidable until the one-lane run exists**; if it is missing, D1's cost limb
  is recorded as `unmeasured` rather than passed.

**D2 — bounded-impossibility rule.** Emit **D2** (for a task set `T`, e.g. the anchors or the
whole tail) iff **all** hold:

1. **Space covered:** every §1 row is `run` or `bounded` (a labelled arm, or a recorded reason
   it cannot be built/toggled). Any `unmeasured` row (crashed arm, blocked `P2`, unbuilt
   proposal) **blocks D2**.
2. **No mechanism reaches parity:** for every mechanism arm `H0+M_i`, `Hi95(Δ_i vs P1) < +M`
   (no mechanism is shown to beat `pi` by margin), and no `H0+M_i` produced a grader pass on a
   task `H0` failed with `Lo95 > 0`.
3. **Best-config still loses:** `H*` satisfies the D1 `INFERIOR` condition on `T`.
4. **Failure evidence complete:** every task still failing has a §3 dossier.

D2's wording is exactly: *"within the mechanism space of §1, on Spark-X2.5-4B / this harness /
this corpus / revision `72538ab` / this server, no mechanism raises the grader pass rate to
`pi`'s by the margin `M`."* It is **not** "no harness can fix this".

---

## 3. MODEL-CEILING VERDICT CRITERIA

For each task `t` still failing after D1's confirmation run, `t` may be reported as
**model-ceiling** (this 4B, this harness, this task) only if **all five** hold. Each is written
so a single observation can falsify it.

**MC1 — invariance across the mechanism space (falsifiable by any passing arm).**
The grader rejects `t` under every arm that reaches a delivery: `raw`, `test`, `review`,
`full`, each built `[PASS]`/`[LIE]` mechanism arm, and — for the tail — `B0`, `B1`, `B2`, `C3`.
The *same* requirement fails each time: record the grader's failing test id and assertion per
arm. If **any** arm produces a grader pass, MC1 is false and `t` is a mechanism defect (name
it). Arms that crash do not count as failing; they are `unmeasured` and block the verdict.

**MC2 — `pi` also fails on the analogous task (falsifiable by a `pi` pass).**
`P1` (and `P2` when unblocked) fails `t`'s grader on the same requirement. If `pi` passes `t`,
`t` is **our-defect**, not a ceiling (this is how T-01/T-05/T-16/T-14/T-28/T-31 were removed
from the ceiling column in STATUS §8d). The comparison task must be the same task and the same
grader revision.

**MC3 — a genuine, revision-bound attempt (falsifiable by a no-op or a missing diff).**
The delivered revision is not byte-identical to the baseline, touches the artifacts the request
names (request-coverage clean), and its exact bytes are captured (sha256) with the grader's
failure on *that* revision. The trajectory shows the model re-attempting to the attempt cap
with the arm's full budget, recurring the same failure. A `no-change-delivery`, a whitespace/
newline-only diff, or a crashed delivery is **not** a ceiling observation (it is a harness
defect); STATUS §8d found exactly this shape in 5 of 40 runs. Additionally, every revision the
run actually *wrote* (not only the delivered one) must be replayed against the grader: if any
written revision passes, the task is **our-defect** (the harness discarded a grader-passing
revision), not a ceiling. `parity-forensics.md` §2.1–2.3 found exactly this for T-28, T-17 and
T-07, so the replay is mandatory, not optional.

**MC4 — no grader-passing revision left untried (falsifiable by a new arm).**
No arm produced a grader-passing revision — delivered **or written-and-discarded** — and every
§1 mechanism that could plausibly target the failure is `run` or `bounded`. If an `[proposed]`
row plausibly targets `t` and is unbuilt, the verdict is `blocked-on-mechanism`, not ceiling.

**MC5 — the grader, not the harness, is the arbiter (falsifiable by a grader defect).**
The failure is the external grader's own outcome on the delivered bytes, not the harness's
claim, stop reason, or the model's review. If the grader itself is defective for `t` (its test
encodes the bug, or is unsatisfiable — the T-06/T-10/T-21 class), the verdict is
`grader-defect`, not ceiling, and the study reports it.

**Not self-confirming.** A model-ceiling verdict may **not** cite "the harness said it tried
hard" or "the model's own test/review agrees". Those are the correlated in-run judges (STATUS
limit 1; forensics §2.4) and are deliberately excluded from MC1–MC5.

### 3.4 The honest epistemic bound of "impossible"

Any D2/ceiling claim carries all of these in the report, in plain words:

* It is about **one model** (`Spark-X2.5-4B Q4_K_M`), **one server config** (`-c 32768`, Q4_K_M),
  **one harness revision** (`72538ab`), **one corpus** (these 40 tasks + their particular
  graders). A stronger model, a different quantisation, a larger window, or a different harness
  may pass a task this study calls a ceiling.
* "Mechanism space" is a **model of what could be tried**, enumerated from the repo and its
  designs. A mechanism that is unknown, mis-implemented, or too expensive to build is outside
  it; the verdict does not reach it.
* The claim is **not a proof**. It is a bounded empirical verdict with a named residual: the
  unbuilt proposals, the environment-blocked `P2` arm, the harness's own claim-gate false
  successes (A-02 class), the corpus's task ambiguity, the unobserved regression stage
  (STATUS limit 7), and the un-remeasured single-lane wall clock.
* A ceiling for `t` is **always revisable** by MC2/MC4: it lives on disk with its revision and
  arm count, so the next arm that passes `t` retracts it mechanically.

---

## 4. FALSIFICATION REGISTER

A D1/D2 conclusion must name, up front, what would overturn it. The following are the
pre-registered falsifiers; each is an experiment, not an opinion.

1. **A new mechanism passes a ceiling task.** Any arm `H0+M_i` produces a grader pass on a task
   this dossier called a ceiling (MC1/MC4) → that task is retracted to `our-defect`.
2. **A currently unbuilt §1 proposal passes a task.** A9/B5/B6/B15/C9 built and run with a CI
   excluding 0 in favour of `H0` → the "space exhausted" premise of D2 fails; D2 must be
   re-derived with the new mechanism in the space.
3. **`P2` (improved prompt) changes the picture.** If `P2` beats `P1` by margin, then `pi`'s
   ceiling is prompt-bound, not model-bound; D1/D2 must be restated against `P2`. Conversely if
   `P2 ≤ P1` with N ≥ 9, the "structure beats a better prompt" claim is refuted.
4. **More seeds move a CI across the threshold.** Any D1/D2 verdict whose deciding CI has
   `Lo95`/`Hi95` within 1 task of `±M` is provisional; the falsifier is the confirmation run at
   the §2.3 seed count (N ≥ 9, or N ≥ 17 for a win).
5. **An `our-defect` fix flips a task.** Fixing T-28 (delivered nothing) or T-14 (spec-bubble)
   and re-running flips them; if they still fail after the fix, they become ceiling candidates.
6. **A stronger model passes the same tasks.** Running a larger model through the same harness
   and grader is an out-of-space test of the model-ceiling claim; a pass retracts "this 4B's
   ceiling" for that task (it does not retract D2's harness-vs-`pi` reading).
7. **A grader defect.** If a task's grader test encodes the bug or is unsatisfiable (MC5), the
   failure is not a capability finding at all.

**Independent-review requirement (before any conclusion may be published).** D1, D2, and any
model-ceiling verdict must be checked by a **fresh-context reviewer who did not run the arms**
(AGENTS.md "Reviewer — independent acceptance"; fresh, never inherited from the worker's
conversation). The reviewer must verify, from the artifacts:

* the **revision/`M` freeze** (git SHA, server config, the Phase-0 `s` and `M`), and that no
  threshold or task set was edited after a mechanism arm ran;
* the **arm coverage** against §1: every row `run` or `bounded`, no silently skipped mechanism;
* the **error-bar math** (task-clustered bootstrap, fixed seed, McNemar) reproduced from
  `results.jsonl`;
* the **pi comparison** on the same tasks/revision/grader, with `pi`'s rows and grader notes;
* the **MC1–MC5** dossiers per ceiling task, each with a falsifier;
* that the report states the §3.4 epistemic bound and the §6 contradictions.

A reviewer who repairs anything becomes a writer and loses independent-acceptance authority; a
modified conclusion needs another fresh reviewer (AGENTS.md "Proof and review"). No conclusion
is "published" — to the owner or anywhere else — on the worker's own say-so.

---

## 5. SKELETON OF THE FINAL OWNER-FACING REPORT

One document, current facts only (no dated narrative; AGENTS.md Documentation). Sections and
what evidence each holds:

1. **Headline / verdict.** D1 status (`PARITY` / `INFERIOR` / `INCONCLUSIVE`) and D2 status
   (`bounded-impossible` / `not-yet`), each with `Δ`, the 95% CI, `M`, and the revision pin.
2. **The two systems side by side.** Table: `actual | claimed | false successes | tokens/task |
   single-lane wall s/task | model calls`, ours (`H*`) vs `P1` (vs `P2` if measured). A footnote
   stating that `pi`'s claim column is a regex read, not a gate (STATUS §8c), and that the wall
   comparison needs the one-lane run.
3. **Per-band table** (easy/mid1/mid2/tail/anchors) and the per-task outcomes, each failing task
   carrying the grader's own failing test id and assertion quote (STATUS §8f style).
4. **Mechanism coverage table.** Every §1 row: arm run?, `Δ` vs `H0`, CI, verdict
   (`passes/loses/inconclusive/unmeasured/bounded`). This is the evidence for D2 condition 1.
5. **Model-ceiling dossiers.** One block per ceiling task: MC1 arm-by-arm failure (test id +
   assertion), MC2 `pi`'s failure, MC3 delivered-bytes sha + `changed_files` + attempt count,
   MC4 which mechanisms were exhausted, MC5 grader check. Each block ends with its falsifier.
6. **Residual harness defects.** The `our-defect` tasks (today T-28, T-14; any new one), each
   with the named §1 mechanism and the fix site, and whether the fix is verified.
7. **Falsification register / what was not measured.** The unbuilt proposals, the blocked `P2`,
   the un-remeasured wall clock, the unobservable regression stage, the per-attempt-output gap.
8. **Epistemic bound + sign-off.** §3.4 verbatim in prose, plus the independent reviewer's
   verification checklist result and the reviewer identity/context basis.
9. **Reproduce.** The exact commands per arm (server health, `v2_measure`/`v2_sweep`/`pi_baseline`
   invocations, the analysis command), the bootstrap seed, and the run-root paths.

---

## 6. CONTRADICTIONS RECORDED (never guessed)

Per the STOP rule, where the objective's assumptions do not match the repo:

1. **"the full 40-task corpus plus the multi-part tail T-31/T-33/T-28/T-14/T-26".** Those five
   tasks are *inside* the 40 (`T-01..T-35` + `A-01..A-05`). There is no separate tail set to add.
   Resolution used here: the 40 is the primary set; the five are a **pre-registered subset** for
   extra seeds (N ≥ 9) and decomposition arms.
2. **"pure coding".** The corpus mixes single-artifact bugfixes (T-11, T-17), contract/serializer
   work (T-33), API scaffolds (T-28), and the five **anchors** which are whole implementations
   from a text spec (STATUS §8b: `pi` 0/5 and the harness 0/5). If "pure coding" means
   bugfix/contract tasks only, the anchors must be reported in a separate band and may not be
   folded into the parity count silently.
3. **"impossible" / "no mechanism can beat pi".** `docs/STATUS.md` §8f explicitly refuses the
   word: model-ceiling is "a statement about *this 4B given this harness on this task*, not a
   claim that no harness could fix the task". This dossier therefore defines D2 as bounded
   spectral exhaustion (§2.6, §3.4) and forbids publishing "impossible" without the §3.4 bound.
4. **"pre-register before the final results are seen".** The baseline results already exist
   (STATUS §8e/§8f/§8g/§8h). Only the **new mechanism-arm** results are unseen. The freeze here
   is therefore: thresholds, task sets and verdict conditions fixed at `72538ab` before any
   mechanism arm runs; the baseline numbers above are quoted, not re-decided.
5. **"error margin" for `pi`.** `pi`'s 27/40 is a single N=1 run (STATUS §8e); there is no
   measured `pi` variance on 40 tasks. A margin computed only from our repeated arm would
   understate the uncertainty. Resolution: Phase 0 runs `P1` with N ≥ 9 and `M` is fixed from the
   pooled baseline difference sd (§2.6).
6. **`pi` claim columns are not comparable.** `pi` has no claim gate; its "claimed"/"missed" are
   a regex read of the final assistant message, and non-claims are mostly truncated turns
   (STATUS §8c). Only `actual` and the false-success/grader counts may be compared; the decision
   rule in §2.6 says so.
7. **Measurement instrument not green.** `bench/v2_measure.py` is **untracked** and its own
   tests currently fail (3 failures; ablation-protocol §8.2: the crash-path record omits
   `tokens_total`, and `task_rate_sd` disagrees with its test). The §2 matrix cannot be trusted
   until the instrument is green; that is a precondition, recorded as a blocker, not a result.
8. **`P2` (pi + improved prompt) is environment-blocked** by an unrelated GPU job (STATUS §8e),
   not by a harness defect. Until it runs, the C4 "structure beats a better prompt" limb is
   `unmeasured`; D1 is decided against `P1` only, and D2 condition 1 stays unsatisfied.
9. **Seed count and margin reconciled with the sibling ticket.** This dossier's first draft
   defaulted to N=3/seed and a margin of 2 tasks. The sibling `28-three-requirements.md` /
   `parity-forensics.md` §4 pre-registers a power analysis from the measured variance (40-task
   difference SD ≈ 2.0 tasks; tail 3.4): **N ≥ 9** seeds/arm for parity, **N ≥ 17** for a win,
   **N ≥ 38** to resolve a 2 tasks. §2.3/§2.5/§2.6 above **adopt those numbers** and set
   `M = 3` tasks. The two workers did not coordinate; this note is the reconciliation, and the
   ticket's numbers win because they are derived from the repo's own repeat runs.
10. **The live parity gap is 2 tasks, not 4.** `parity-forensics.md` §1 finds the current-revision
   pi-only wins are **T-17 and T-28** (not T-31/T-14/T-26), and both have a grader-passing
   revision inside the run that the harness discarded. This does not change the task sets of §2.2
   (the objective names T-31/T-33/T-28/T-14/T-26 as the multi-part tail) but it means T-17 is an
   additional pre-registered `our-defect` candidate for the MC3/MC4 replay.

---

## 7. Preconditions and ordering (so the freeze is real)

1. **Freeze this file** (it is the pre-registration). Record its git status/hash.
2. **Green the instrument** (ablation-protocol §8.2) and give `v2_measure` the cumulative-ladder
   arms, equal-budget pin, `stage_information`/`tokens_by_stage`, bootstrap/McNemar helpers
   (ablation-protocol §8.1, 8.4–8.7). No mechanism arm runs before this.
3. **Phase 0 calibration:** `H0` and `P1`, 40 tasks, **N ≥ 9** → compute `s`, fix `M`, freeze.
4. **Phase 1 screen:** reduced 14-task set, N=5 (underpowered screen — nominates, does not
   decide) + the 5-task tail at N ≥ 9, all built `[PASS]`/`[LIE]` mechanism arms.
5. **Phase 2 confirmation:** 40 tasks, **N ≥ 9** (N ≥ 17 for any "beats" claim), only the arms
   whose Phase-1 CI excluded 0 in favour of `H0`, plus `H*`; `P1` re-run at the same N.
6. **Decision** per §2.6, then **independent review** per §4, then the §5 report.
