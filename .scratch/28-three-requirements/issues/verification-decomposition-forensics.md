# Forensics — where verification and decomposition stop carrying information

READ-ONLY investigation. No code or existing doc was modified. This document and
`ablation-protocol.md` are the only outputs.

Scope: `docs/STATUS.md` §1, §1a, §3, §8c–§8h; `docs/FLOW.md`; `harness/leaf.py`,
`harness/tree_run.py`, `harness/how.py`, `harness/node.py`, `bench/v2_leaf.py`,
`bench/v2_sweep.py`, `bench/v2_tree.py`, `bench/v2_measure.py`, `bench/FAIL_PATTERNS.md`;
raw evidence under `bench/runs/**/trajectory.jsonl` and `bench/runs/**/results.jsonl`.

Reproduce a quote: `bench/runs/<run>/<task>-<i>/trajectory.jsonl`, event `seq`. The
persisted record is the source of truth; where STATUS and the record disagree, the record
wins.

**Terminology.** *Information* here means what a stage changes about the outcome the
external grader would give (the only correctness arbiter, STATUS limit 2). A stage *adds
no information* when its verdict is uncorrelated with the grader's; it *adds negative
information* when its signal flips a grader-correct revision to a non-claim (missed
success), or carries a grader-wrong revision to a claim (false success).

**R2/R3 mapping (recorded gap).** "requirements 2 and 3" are not named in any file in the
repo. From the objective's own structure — (a) test/IV/review vs (b) step-splitting — and
from `docs/ROADMAP.md`, the only in-repo numbering, they map to **R2 = C2 "verification
carries information (no meaningless test or review)"** and **R3 = C4 "structural
superiority: work the structure gets out of the model that prompting alone cannot"**.
This mapping is an inference, flagged here, and `ablation-protocol.md` restates it.

---

## 1. The single decision point

Every claim is granted in exactly one place, `harness/leaf.py::claim_decision`
(line 1958; the `apply_claim` consumer at 6888). Stages never decide; they feed evidence
into that gate. So a stage "carries information" only through the fields its verdict
sets there:

| stage | field | what it is supposed to add |
| --- | --- | --- |
| own test | `own_test_green`, `own_test_red_is_evidence` | a red-then-green loop that pins the goal behaviour |
| independent test (IV) | `iv_approved`, `iv_red_on_final`, `iv_non_discriminating` | fresh, independently authored, discriminating check of the same goal |
| review | `review_approved`, `review_verdicts` | a diff-vs-spec contract read ("another agent confirms") |
| judge | `judge_implementation_wrong` | attribution of a red to implementation/tests/spec |

The gate also has hard deterministic blocks (coverage, documented API, regression,
no-change delivery) — those *do* carry information because they are mechanical. The
model-written stages are where the losses are.

---

## 2. Stage-by-stage: promised information vs the exact code path where it is zero or negative

### 2.1 The own test

**Promise (FLOW §4 W1–W2):** a forced red-then-green loop; the test is the run's target.

**Asymmetry that manufactures negative information (named fix site).** The own-test
artifacts inject `test_target_rule = _SELF_TEST_DESIRED_STATE_RULE`
("Goal/acceptance lines may DESCRIBE THE CURRENT BROKEN behaviour; assert the DESIRED end
state a correct fix produces, never the reported symptom") —
`harness/leaf.py::_self_test_artifacts` (5249), rule text at 926. The independent-test
question does **NOT** carry that rule: `bench/v2_leaf.py::_independent_test_question`
(707) asks only "Write a test that FAILS against the ORIGINAL source and PASSES against
the FINAL source." See §2.2.

**Where the own test adds zero:** when the plan declared no tests the own test is advisory
(`own_test_advisory`, `claim_decision` rule 6 at 2229). Evidence, T-30
(`v2sweep-20261009T120918Z`): `"self_test": null` in the result record — the own test was
never written, and the review carried the claim (false success; see §3).

### 2.2 The independent test

**Promise (FLOW §4, `_iv_request` 4318):** a fresh author that never sees the run's own
test, given the goal, the numbered ACs, and the ORIGINAL and FINAL source of the changed
files, producing one test function per criterion that is red on the original and green on
the final.

#### (a) The inverted test — the dominant blocker

`evaluate_independent_test` (4917) is deterministic. Step 1 requires the whole file to be
red on the ORIGINAL source; step 4 requires the whole file green on the FINAL source. If
step 4 fails it returns immediately:

> `return IndependentTestVerdict(approved=False, reason="independent-test-red-on-final", ...)` — 4998

The per-criterion classifier `_criterion_evidence` (4502) — which is the only place a
node that "still PASSES on the pre-run source" is labelled `not-discriminating` — is
**never reached** on that early return. So a test file that mixes one genuine red case
with one case that encodes the *symptom* passes the whole-file discrimination gate and
then reds the correct fix as an undifferentiated failure.

Ground truth on disk (the §8c run, revision before P3b):

* **T-06** (`v2sweep-20261006T040753Z/results.jsonl`, `quad=missed-success`): the IV file
  contains
  ```python
  with pytest.raises(TypeError, match="can't compare offset-naive and offset-aware datetimes"):
      is_due(job)
  ```
  and, two functions later, `assert is_due(job) is True`.
  `independent_test_reason: independent-test-red-on-final: 1 failure(s), 0 error(s):
  tests/scheduler_jobs_test.py::test_ac1_offset_aware_compare`. The first function asserts
  the bug the request asks to remove; the file still passes step 1 because the third
  function fails on the buggy source. The IV blocked a grader-correct fix.
* **T-10** (same run): the IV file contains
  ```python
  with pytest.raises(IndexError):
      next_bin(empty_stock)
  ```
  — exactly the crash the request says to remove. `independent_test_reason:
  independent-test-red-on-final: ... test_ac1_empty_stock_no_indexerror`. `missed-success`.
* **T-19** (`v2sweep-20261008T140136Z` seq 1194): IV red on `test_ac1_underscores`; review
  had approved the hyphen-slug fix (`seq 1185`); `review_blocked_by_red_independent_test`
  (`seq 1196`); `leaf_stop ... stop_reason=independent-test-red-on-final` (`seq 1197`).
* **T-12** (`v2sweep-20261011T065821Z` seq 856–858): IV red on
  `test_ac1_webhook_editor_rejected_app_editor_allowed` (it asserts the rejection the
  request says is wrong) while two review angles approved the `is`→`==` fix; the claim is
  blocked. In this run the re-sampled IV (`seq 862/866`) came back `independent-test-not-red`
  (vacuous) — the stage contributed nothing either way.
* **T-22** (`v2sweep-20261009T120918Z` seq 67–71): IV red on
  `test_ac1_caps_jump_front`; the record explicitly classifies it
  `independent_test_inverted: {"all_inverted": true, "inverted_ids":
  ["tests/test_independent.py::test_ac1_caps_jump_front"], "unmet_ids": []}`. This is the
  P3b path (`iv_inversion_evidence` 1774, `iv_all_inverted` 1801, used by `iv_red_on_final`
  6797): when **every** final-failing id passed on the pristine source the red does not
  block. It fires for T-22 but not for a mixed file (T-21/T-35 below), and it did not exist
  in the §8c revision at all.
* **T-21** (`v2sweep-20261012T125531Z/results.jsonl`, `missed-success`): the IV file is
  broken and unsatisfiable — `load(path)` with `path` never bound, and a misused
  `pytest.raises` context manager:
  ```python
  def test_ac3_loader_fixed():
      with pytest.raises(StorageError):
          load(path)
  ```
  `independent_test-reason: independent-test-red-on-final: 3 failure(s) ... test_ac1...,
  test_ac2..., test_ac3...`. It fails on both revisions, so `iv_all_inverted` is False and
  the red blocks a grader-correct revision.
* **T-20** (`v2sweep-20261009T101718Z` seq 1179–1201): first IV red on
  `tests/ratings_stats_test.py::test_ac1_4_star_items` while the grader **passed**
  (`missed-success`).

**Why this is negative information, not a bug in one test.** The discrimination gate
(`evaluate_independent_test` step 1) and `pristine_red_is_discriminating` (1819) treat
"red on the pristine source" as *the* proof the goal was pinned. That only proves the
test is coupled to the bug, not to the fix — a symptom-asserting test is maximally
coupled to the bug. STATUS limit 4 already concedes the direction ("a weak-but-genuinely-
discriminating test ... passes even if it does not encode the requirement"); this is the
converse and more damaging one.

#### (b) Re-sampling the verifier until it agrees

`final_verification` (6988) calls `iv_verdict_for` again on the exhausted ladder, and
`iv_verdict_for` (`harness/leaf.py` closure at 5898) authors a **fresh** test each call
(`_call_iv` → `model_independent_test`). So a red-on-final IV can be replaced by a new
stochastic sample that approves the same revision.

* **T-35** (`v2sweep-20261009T120918Z`): first IV red-on-final (3 failures) → blocked at
  `review_blocked_by_red_independent_test` (seq 330), then `final_verification` (331)
  re-authored a different file `tests/merge_test.py` that approved (seq 341), the claim
  was granted `basis independent-test` (seq 343) and **the grader failed**
  (`test_empty_intervals_dropped` + `test_gap_preserved`). False success.
* **T-20** (above): first IV red → re-sampled IV approved (seq 1192). Here the grader had
  passed; the point is that the "independent" verdict is a second draw of the same model,
  not independent information.

#### (c) Two verifications that share the misreading agree

STATUS limit 1 and §8e name this. Two trajectory-grounded instances:

* **T-27** (`v2sweep-20261009T120918Z`): IV approved with
  `test_ac1_snake_case_passthrough` asserting
  `normalize({"firstName": "John"}) == {"first_name": "John"}` — i.e. it agrees with the
  model's wrong reading (the request says node (b): "Downstream code now expects snake_case
  keys ... and unknown keys must be dropped"). `best_evidence_revision rank=3
  tier=independent-test`; `leaf_green` (`basis review+independent-test`); grader:
  `test_snake_keys_pass_through AssertionError`. False success.
* **A-02** (`v2sweep-20261011T070710Z`, the §8g run): `independent_test_verdict approved
  true, criteria_count 17, covered_indices [1..17]` (seq 1338), own test green, claim
  granted; grader `test_tyrosine_rna_sequence AssertionError`. False success. This is the
  case P8c (`_CARRYING_ANCHORS`) was written for.

#### (d) The IV is reused for two different roles

`_iv_request` (4318) and `model_independent_test` reuse the `write_test` envelope, so the
IV and the own test are the same step type from the same model; only `fresh=True`
distinguishes them in the trajectory. This matters for cost attribution (see the
protocol's missing `tokens_by_stage`).

### 2.3 The review

**Promise (FLOW §4, `combine_review_verdicts` 857):** weighted multi-angle review; a
critical angle's `definitely-problematic` vetoes, all critical angles must be present, and
the weighted score must be positive.

**Where it adds zero/negative: the LAST approving round carries the claim.** FLOW §4.4
re-runs the review every iteration; `combine_review_verdicts` only sees one revision's
verdicts, and `claim_decision` rule 4 grants on an approving review. The loop can therefore
keep re-emitting the same wrong file (M1 erase, §4.2) and the review converges on
"approved" without the revision changing in substance.

* **T-28** (`v2sweep-20261008T141712Z`, false success): the review verdicts on the same
  wrong module alternate `definitely-problematic` / `uncertain` and then run
  `definitely-ok` eight times; the last `definitely-ok` even confabulates the missing
  surface:
  > `plugins/registry.py ... raises KeyError for unknown names, and exposes module-level
  > register/get/run. Satisfies AC-2 and AC-3.`
  The grader: `FAILED tests/test_plugins.py::test_register_and_get - TypeError: 'Registry'
  object ...` — only class methods exist. `self_test: null`, `independent_test_reason:
  independent-test-unobserved`, `stop=green basis=review`. The review approved a partial
  fix and carried the claim.
* **T-26** (same run, false success): same shape; review flips to `definitely-ok` on a
  `Plan` that broke dict access; grader `FAILED tests/test_model.py::
  test_old_dict_access_still_works`. STATUS §8e names it.
* **T-30** (`v2sweep-20261009T120918Z`): 12 `definitely-ok` review verdicts, of which the
  first ten were filtered `review_not_grant_calibre` (thin evidence), and two survived
  (`seq 396/398`); claim granted `basis review`; grader `NameError: name 'time...`. Before
  P8b a non-discriminating IV (errors-only red) could not block the review —
  `iv_verdict_is_non_discriminating` (1833) now does, per §8g.

The residual is exactly STATUS limit 1: a *specific* yet mistaken approval still grants.
The grant-calibre filter (`apply_review_filter` 4215, `_evidence_is_grant_calibre` 4203)
removes "looks correct" but cannot tell a confidently wrong specific claim from a right
one.

### 2.4 Cross-stage: shared generator, shared blind spot

Every in-run judge is the same 4B (FLOW §7). The gate's only defence is *agreement*:
rule 4 requires an approving IV to corroborate a review (`claim_decision` 2173–2226) and
rule 7/8 require IV agreement after a test rewrite. But the corroborating IV is written by
the same model from the same goal text, so agreement is not independent evidence — T-27
and A-02 are agreement on a wrong reading. The one genuinely informational signal in the
gate is the mechanical set: `_request_coverage`, `documented_api_missing_now`,
`deterministic_greens`/`_CARRYING_ANCHORS` (P8c), regression (`regression_now`). Those do
not depend on the model's reading.

---

## 3. Case ledger (each line: quote + code path + information verdict)

| case | run / record | quoted evidence | code path | verdict |
| --- | --- | --- | --- | --- |
| T-06 | `v2sweep-20261006T040753Z/results.jsonl` | IV asserts the bug (`pytest.raises(TypeError, match="can't compare offset-naive...")`); `independent-test-red-on-final: ...test_ac1_offset_aware_compare`; `quad=missed-success` | `_independent_test_question` (bench/v2_leaf.py:707); `evaluate_independent_test` step 4 (leaf.py:4987); `claim_decision` rule 4 (2189/2200) | negative (blocked a correct fix) |
| T-10 | same | `with pytest.raises(IndexError): next_bin(empty_stock)`; red on `test_ac1_empty_stock_no_indexerror`; `missed-success` | same | negative |
| T-12 | `v2sweep-20261011T065821Z` seq 856–874 | IV red `test_ac1_webhook_editor_rejected_app_editor_allowed`; review approved; `review_blocked_by_red_independent_test` | `evaluate_independent_test` step 4; `iv_red_on_final` (6797) | negative |
| T-19 | `v2sweep-20261008T140136Z` seq 1194–1197 | IV red `test_ac1_underscores`; review approved; stop `independent-test-red-on-final` | same | negative |
| T-20 | `v2sweep-20261009T101718Z` seq 1179–1201 | IV red `test_ac1_4_star_items`; grader passed; `final_verification` re-sampled IV approved | `final_verification`; `iv_verdict_for` (5898) | negative + zero (re-sample) |
| T-21 | `v2sweep-20261012T125531Z/results.jsonl` | IV `load(path)` unbound; `independent-test-red-on-final: 3 failure(s)`; `missed-success` | `iv_all_inverted` (1801) requires *all* final ids inverted; mixed file not excused | negative |
| T-22 | `v2sweep-20261009T120918Z` seq 67–71 | `independent_test_inverted {all_inverted:true, inverted_ids:[test_ac1_caps_jump_front], unmet_ids:[]}` then claim green | `iv_inversion_evidence`→`iv_all_inverted`→`iv_red_on_final` | zero (correctly defused) |
| T-35 | `v2sweep-20261009T120918Z` seq 328–345 | first IV red → `review_blocked_by_red_independent_test`; `final_verification` re-authored `tests/merge_test.py` → approved; `basis independent-test`; grader failed | `final_verification`; `_call_iv` re-sample | zero + negative (approved wrong) |
| T-27 | `v2sweep-20261009T120918Z` | IV `test_ac1_snake_case_passthrough` agrees with the wrong reading; `best tier=independent-test`; grader `test_snake_keys_pass_through` | shared goal text; STATUS limit 1 | zero (agreement on a wrong reading) |
| T-30 | `v2sweep-20261009T120918Z` | `self_test: null`; IV `0 failure(s), 3 error(s)`; 12 review `definitely-ok`; claim review; grader `NameError` | pre-P8b; `iv_verdict_is_non_discriminating` (1833) now blocks | negative (carried a wrong fix) |
| T-28 | `v2sweep-20261008T141712Z` | review `definitely-ok` claims "exposes module-level register/get/run"; grader `TypeError: 'Registry' object` | `combine_review_verdicts` (857); `claim_decision` rule 4 | negative (approved a partial fix) |
| T-26 | `v2sweep-20261008T141712Z` | review `definitely-ok` on a `Plan` that broke dict access; grader `test_old_dict_access_still_works` | same | negative |
| A-02 | `v2sweep-20261011T070710Z` seq 1338–1341 | IV approved 17/17; own test green; grader `test_tyrosine_rna_sequence` | shared model; P8c `_CARRYING_ANCHORS` (1890) | zero (agreement on a wrong reading) |

**The 8 §8c cases.** §8c lists T-06, T-10, T-12, T-19, T-20, T-21, T-22, T-35. The §8c
sweep `v2sweep-20261006T040753Z` kept only the first band's `results.jsonl` (T-01..T-10);
its later bands and every trajectory are absent (see §6). T-06 and T-10 are quoted from
that exact run; T-12/T-19/T-20/T-21/T-22/T-35 are quoted from the nearest on-disk runs
that exhibit the same mechanism (run and revision named per row), which is a substitution,
not the original record — recorded as a gap.

---

## 4. Decomposition and multi-approach exploration

### 4.1 What "exploration" actually is, measured

The leaf's ladder (`LADDER`, leaf.py:358) is L1-resample, L2-guided, L3-deeper-explore,
L4-rule-diagnosis, L5-review-judge. Each rung changes only the *prompt lead* on one
implementation write (`_implement_question` 5202): L2 "First enumerate the ordered fix
steps", L3 "Check every source file in the stable context", L4 inject the deterministic
diagnosis, L5 "An independent review is watching". There is no ranked candidate set in the
leaf. `escalate` (2422) *refuses a rung that adds nothing* (`_is_repeat` 2400; `wasted`
when the L4 diagnosis is empty) — i.e. the loop already treats an information-free rung as
wasted. Trajectory evidence: T-30 `v2sweep-20261009T120918Z` seq 364/376/388 —
`escalation_wasted {"reason": "identical attempt refused: same signature/files/claim"}`,
`L4 diagnosis surfaced nothing new`.

The tree's How exploration is in `harness/tree_run.py::_run_hows` (1380) and
`harness/how.py::HowList`. Its default is **greedy** (`how_explore <= 1`): plan the Hows,
take the top-ranked one, fund that single candidate (`budget.split(1)[0]`); only
`how_explore > 1` opens parallel candidates compared by `harness.how.pick` (523). STATUS §3
recorded the tournament as "works, but ~5× the calls and wall time for fewer fixes", and
§1a records the pattern: "structure that costs calls without adding information loses".

### 4.2 Why greedy wins on *this* corpus

Every corpus task is a single-artifact bugfix or a small contract addition; the request
text names the one file/function in most cases. Multi-approach exploration spends a model
call per candidate but the candidates are samples of the same 4B on the same prompt, so
they add sampling variance, not information. The measured ladder is flat: §1a
`raw 17/33 → test 18/33 → review 18/33 → full 20/33`. That is the same shape as every
"structure without signal" mechanism in §3 (knowledge pack 4/15 vs 3/15; file order
harmful; source index harmful).

### 4.3 The write seam and the M1 erase (T-31 etc.)

**The single-file seam is historical, not current.** STATUS §8d ("T-31: per-attempt writes
alternate transport.py / client.py ... one file per attempt + an M1 erase") describes the
revision before ticket 26. The current main loop writes **every** file in the envelope:
`pairs = [(fc.file_path, fc.content) for fc in (env.files or [])]` then a
`_write_one(...)` loop (leaf.py ~8163–8200). On disk, T-31 now writes all four files in one
attempt: `v2sweep-20261009T120918Z` seq 7–10 → `api/client.py, api/service.py,
api/transport.py, exporter/bulk.py` (and the same four again at seq 45–48 after the M1
erase at seq 43). So the seam is **not** the current cause of any failure.

**The M1 erase is still live and still lossy across attempts.**
`_mode` (3488) returns `"M1"` after any non-`novel` verdict (or `same`/`undecided`), and
the loop then calls `_erase_draft(workdir, baseline)` (3025) which restores every baseline
file and deletes every created file. `capture_best_evidence(...)` (5767) checkpoints the
revision first, so the erase no longer *destroys* evidence; but the checkpoint is ranked by
**evidence** (`BEST_EVIDENCE_ORDER`: agreement > independent-test > own-test > review,
3080), never by how much of the required surface the revision covers. So a multi-file
revision with weak evidence loses to a partial revision with strong evidence. T-31's record
shows exactly the erase/re-emit cycle (single attempt then attempt-3 re-emit, both
four-file), and its current stop is the IV red-on-final, not the seam or the erase.

The request-coverage gate (`_request_coverage` 2919 → `request-artifacts-uncovered` in
`claim_decision` 2140) is the mechanical countermeasure that a partial multi-file fix must
now clear; that is the T-31 fix of ticket 23.

### 4.4 Which multi-part failures are multi-part, and where a positive delta is measurable

| task | multi-part shape | current stop (§8f/§8g) | plausible decomposition |
| --- | --- | --- | --- |
| T-31 | 3 ACs, 4 files; request names `send()`/`fetch()`/service/bulk | IV red-on-final (§8g) | file-level children: transport→client→service+bulk, integration check |
| T-33 | serializer contract with a frozen base | deterministic `contract` completeness (the only task the gates fixed) | already benefits from the coverage gate |
| T-28 | module-level API documented in the repo README | delivered nothing (`documented-api-missing`) | one child per documented name |
| T-14 | two documented behaviours in one request | half the contract, delivered as best evidence (`spec-bubble`) | behaviour-level split |
| T-26 | dataclass port must keep dict access | review-approved partial; grader dict-access fail | contract child + behaviour child |

A positive delta from decomposition is only *plausibly* measurable on this tail
(T-31, T-33, T-28, T-14, T-26) and essentially zero on the easy/mid bands, where the
monolithic leaf already passes. That is the R3 hypothesis the protocol must test.

### 4.5 The decomposition mechanism, at file + function level

These are the seams a measurement would toggle; none is a new decision, only an extension
of what exists.

1. **`harness/node.py::plan_node` / `decomposition_from_envelope` (206) → children.** One
   child per declared file or per documented behaviour; each child is a leaf with its own
   write boundary (`leaf_spec_from` gives each child its declared files as the runtime write
   boundary).
2. **`harness/tree_run.py::_run_hows` (1380) greedy vs `how_explore>1`.** The parallel
   tournament (`harness.how.pick`) is the "multi-approach exploration" arm to measure.
3. **`harness/tree_run.py::_apply_decomposition` (1237)** — budget split and
   `SplitHistory.accept` (harness/node.py:498) repeat-refusal.
4. **`FORCED_LEAF_MAX_FILES = 3` / `FORCED_LEAF_MAX_ACS = 3`** (tree_run.py:165) —
   the deterministic gate that forces small nodes to run monolithic. T-31's view has 7
   files and 3 ACs, so it clears the file threshold; a task with ≤3 files is forced even if
   it declares children. Any decomposition measurement must vary these.
5. **`harness/leaf.py::_write_one` (8846) loop** — the multi-file write path; already
   supports N files per attempt, so "one file per attempt" is no longer a code constraint.
6. **`harness/leaf.py::_mode`/`_erase_draft` (3488/3025)** — the cross-attempt erase; the
   mechanism to fix is ranking `BestEvidenceRevision` by coverage, not only evidence
   (`capture_best_evidence` 5767).

---

## 5. Prioritized fix list for R2/R3

Expected effect is stated against the measured deltas in STATUS §1a/§8c (§8c: 8 of 11
missed wins were `independent-test-red-on-final`) and §8g (false successes 3→1).

**R2 — verification carries information**

1. **Give the IV the same desired-state rule the own test gets.**
   `bench/v2_leaf.py::_independent_test_question` (707): append
   `_SELF_TEST_DESIRED_STATE_RULE` and an explicit "the AC text may describe the broken
   symptom; assert the desired end state" line. Expected: removes the T-06/T-10/T-12/T-19
   inversion class at its source. Cost: one constant in one function; no new call.
2. **Classify per-criterion inversions even when the whole file is red on the final.**
   `harness/leaf.py::evaluate_independent_test` (4917): before returning
   `independent-test-red-on-final` at step 4, run `iv_inversion_evidence` and split the
   final failures into inverted vs unmet; block only when a final-failing id also failed on
   the pristine source (a genuine unmet criterion). This generalises `iv_all_inverted`
   (which needs *all* ids inverted) to mixed files, T-21/T-35. Cost: reuse of existing
   `iv_inversion_evidence`; no new call.
3. **Make the re-sampled IV on exhaustion count as a re-sample, not a fresh verdict.**
   `harness/leaf.py::final_verification` (7138) currently calls `iv_verdict_for` again;
   when the first IV was red-on-final, a new approving sample should be recorded as
   `independent-test-resampled` and must not, by itself, upgrade the basis above
   `review`. Expected: removes the T-35 false success. Cost: one branch + a label.
4. **Require a carrying deterministic anchor before any model-written check carries
   (extend P8c).** P8c (`_CARRYING_ANCHORS`, 1888) already requires a deterministic green
   on the main path; the T-27/A-02 residual is a *discriminating but mis-aimed* test on
   the `green` path (STATUS limit 8). Apply the same carrying-anchor requirement to the
   green path. Expected: removes the last false-success class. Cost: one gate branch;
   measured cost is fewer claims (§8h already states this).
5. **Attribute the review to the revision it saw.** `combine_review_verdicts` (857) folds
   each attempt's verdicts; record and require the source-revision fingerprint
   (`_source_revision_fingerprint` 3284) for the approving round, so a later round cannot
   approve a revision the earlier round rejected without the bytes changing. Expected:
   removes T-26/T-28. Cost: a field + a comparison.

**R3 — decomposition / exploration**

6. **Coverage-rank the best-evidence revision.** `harness/leaf.py::capture_best_evidence`
   (5767) / `BestEvidenceRevision` (3092): rank by (request-coverage of the revision,
   then evidence) so an M1 erase cannot lose a more complete multi-file fix to a partial
   one. Expected: helps T-31-class multi-file tasks. Cost: one comparator.
7. **Measure greedy vs tournament and the forced-leaf thresholds.**
   `harness/tree_run.py::_run_hows` (1380), `FORCED_LEAF_MAX_FILES/ACS` (165). This is a
   measurement, not a change: the ablation protocol covers it. Expected: possibly nothing
   on the easy/mid bands, a measurable delta (if any) only on the tail.

Item 7 is the R3 verdict itself; items 1–5 are R2. Items 1–3 are cheap and target the
dominant measured blocker (8 of 11 missed wins).

---

## 6. Evidence gaps (never guessed — recorded and worked around)

1. **The §8c 8-case run has no trajectories.** `bench/runs/v2sweep-20261006T040753Z`
   keeps only `results.jsonl` (band T-01..T-10) and no `trajectory.jsonl`; the other three
   bands named in §8c (`041641Z`, `042104Z`, `042844Z`) are absent. T-06 and T-10 are
   quoted from the surviving `results.jsonl`; the other six are substituted from later
   runs (named per row in §3). The original per-call envelopes for all eight are lost.
2. **Per-attempt model output is not persisted** for the §8c/§8e runs (STATUS §8d's stated
   gap): only `claimed_delta`, `touched_files` and the failure signature, not the
   file content the envelope carried. The "did the model emit a no-op, or did M1 revert a
   real fix" question stays an inference from delivered bytes.
3. **T-20's first IV failed on a revision the grader passed, but the persisted record does
   not contain the failing assertion text** (the verdict carries `detail` and the ids, not
   the report body). The mechanism (IV red blocks a correct fix) is certain from the
   events; the exact reason that specific test failed is not recoverable.
4. **`bench/v2_measure.py` is untracked and its own tests are currently red** (see the
   protocol's tooling section); the ablation tool exists but is not yet a green,
   runnable instrument.
