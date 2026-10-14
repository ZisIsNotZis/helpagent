# Fix wave 1 (commit `45ebb32`) — independent review

Fresh-context review of the wave against its own handoff
([`fix-wave-1-handoff.md`](fix-wave-1-handoff.md)). Read-only: no code, test or ticket was
modified; the only file written is this one. No model calls were made; the recorded
samples under `/tmp/wave1` were read, plus one baseline copy at `/tmp/revab` created from
`git archive 72538ab` (outside the repo) to run the new tests against the un-wave code.

**Revisions.** reviewed `45ebb32f1be0977b9149057da3a80ee93ce22840` (HEAD, clean tree, nothing
staged); baseline `72538abfa5e8` (= handoff's "pristine baseline"); P8c baseline
`24d801e449bb`. File hashes at HEAD: `harness/leaf.py bd24f7487df3f331`,
`bench/v2_leaf.py 2acb766eb9cf0f84`, `tests/unit/test_v2_leaf.py 2621ae3c5cda7108`.

## Commands run

| command | result |
| --- | --- |
| `uv run pytest -q -p no:warnings` | exit 0; 827 tests collected, no F/E marker in the progress output (this repo's config prints no summary line) |
| `uv run pytest -q tests/unit/test_v2_leaf.py::test_only_the_single_gate_can_produce_a_claimed_outcome` | 1 passed |
| `uv run pytest -q tests/unit/test_v2_leaf.py -k "claim_gate or single_gate or claim_site"` | 5 passed |
| `/home/z/vibe/helpagent/.venv/bin/python -m pytest -q <12 wave tests>` in `/tmp/revab` (baseline 72538ab) | **12/12 FAIL** (per-test reasons below) |
| `git status --porcelain`, `git diff --cached` | empty (no repo change by this review) |

## 1. Per-claim verdict (code + test)

Baseline copy run: every new wave test fails on `72538ab` and passes on HEAD, so each has a
discriminating regression test. Baseline failure reason (verbatim) in the last column.

| # | claim | code | baseline failure of its test |
| --- | --- | --- | --- |
| FIX 1 | IV prompt carries the desired-state rule + "never the reported symptom" | `bench/v2_leaf.py:770` (`+ _SELF_TEST_DESIRED_STATE_RULE`, rule at `harness/leaf.py:945`) | `assert 'DESCRIBE THE CURRENT BROKEN behaviour' in <prompt>` |
| FIX 2 | per-criterion inversion classification before the red-on-final return | `harness/leaf.py:1829` `iv_blocking_final_ids`, early return `5208-5241`, use `7150` | `ImportError: iv_blocking_final_ids` / `AttributeError: 'IndependentTestVerdict' object has no attribute 'inverted_indices'` |
| FIX 3 | a re-sampled IV cannot upgrade the claim alone | `harness/leaf.py:7395,7419,7450` | `AssertionError: assert 'independent-test' == 'review'` — baseline *grants* on the re-sample |
| FIX 4 | carrying anchor (P8c) — no behaviour change in this wave | `harness/leaf.py:1936` `_CARRYING_ANCHORS`, block `2185-2192` | not part of the wave's tests (see below) |
| FIX 5 | review attributed to the source-revision fingerprint | `harness/leaf.py:871-884` (block), `6301-6302` (stamp; the hash is `_source_revision_fingerprint`, `3395`) | `TypeError: ReviewVerdict.__init__() got an unexpected keyword argument 'source_revision'` |
| FIX 6 | coverage-ranked best evidence | `harness/leaf.py:3216` `_best_evidence_preference`, capture `6054-6065` | `ImportError: _best_evidence_preference` |
| D1 | deterministic contract verdicts + contract-clear capture | `harness/leaf.py:6014` `current_contract`, `3200` `_snapshot_fails_contract`, `6069` `note_contract_clear`, call site `8666-8667` | `AssertionError: assert 'own-test' == 'contract-clear'` |
| D2 | test_wrong credited from the traceback; no M1 erase on test attribution | `harness/leaf.py:3681-3718`, `3920`/`3956`, `8429-8437` | `AssertionError: assert False is True` |
| D3 | judge coherence extended to `spec_wrong` (+ first-attempt bubble deferral) | `harness/leaf.py:3925-3936`, `6733-6745` | `assert True is False` (baseline keeps `spec_wrong`) |
| D3b | self-contradicting "check" ruling may not drop a blocking red | `harness/leaf.py:1971-2021`, call site `7554` | `TypeError: reconciliation_ruling() takes 1 positional argument but 2 were given`; end-to-end test: `assert True is False` (**baseline claims** on the T-35 shape) |
| FIX 7 | `--continue-on-collection-errors` so a collection error cannot hide the canary | `harness/leaf.py:5349` | `assert 'canary-missing' == 'tests-failed'` |

**FIX 4 confirmed at the earlier P8c baseline.** `git show 24d801e -- harness/leaf.py` adds
`_CARRYING_ANCHORS = ("documented-api", "no-regression")` and the `no-deterministic-anchor`
block; both are already present at `72538ab` (`harness/leaf.py:1890,2118`). The wave's
`deterministic_greens` change (`1939-1968`) is **docstring-only** — the diff's added lines in
that function are all comment text; the handoff's row is accurate.

### FIX 2 is behaviour-preserving at the gate (record-only)

`iv_all_inverted` now delegates to `iv_blocking_final_ids` (`1848-1862`) and
`iv_red_on_final` uses it (`7150`). I enumerated the *true* pre-wave predicate
(`not (set(final.failed_ids) <= set(iv_inversion_evidence(...)[0]))`) against the new one over
every failure-set combination of 3 node ids (56 cases): **0 behaviour differences**. The
mixed-file case the test titles ("excuses inverted and blocks the unmet") already blocked at
baseline. FIX 2's real change is that the whole-file early return (`5208-5241`) now populates
`criteria`/`inverted_indices`/`offending_indices` for the record (`6266`); nothing reads
`inverted_indices` for a decision. This is not a defect — it is a claim-scope mismatch (see
finding P2-1).

## 2. Structural single-claim-gate check

- The AST check passes (`tests/unit/test_v2_leaf.py:5404-5504`): `offenders == []`, exactly one
  `_granted_claim`, every literal `claimed=True` inside it, and the call-site whitelist is
  exactly `{"leaf.py": 3, "tree_run.py": 1}`.
- Independent confirmation: `_granted_claim` is *defined and called only inside*
  `harness/leaf.py` (`def` 1783; calls 2156, 2317, 2356, all inside `claim_decision`);
  `ClaimDecision(claimed=True, ...)` at 1786 is its only construction; every other `claimed`
  assignment in `harness/` is `decision.claimed` (7238) or literal `False` (5872, 7788); the
  tree close routes through `claim_decision` (`harness/tree_run.py:2123`). `bench/v2_measure.py`
  only *reads* `claimed` from the persisted run record (`bench/v2_measure.py:346-366`), and its
  exception fallback is `claimed: False` (351) — no second claim path exists, in `harness/` or
  `bench/`.

## 3. T-35 closure (recorded samples)

Recorded evidence, all on disk:

- **WIP-only false success** (`/tmp/wave1/after/T-35-interval-merge-invariants.log:7-9`):
  `claimed=True basis=independent-test … [actual] grader_passed=False … [quadrant] false-success`.
  Its trajectory (`/tmp/wave1/after/trajectory.jsonl`, T-35 sample seq 565-642) shows the exact
  path: reconciliation judge raw `blame="test"` with `problem` naming the source logic
  (`"…because it uses 'start <= current_end'…"`) → `reconciliation_ruling` "check" →
  `claim_reconciliation_check_dropped` → `leaf_green_at_exhaustion basis=independent-test`.
- **6 post-fix samples**, all `claimed=False`: `close/after/T-35-interval-merge-invariants`
  (two samples in one dir: seq 71-73 and 68-70), `-r1`, `-r2`, `-r3`, `-r4`.
  Quadrants from `run.log`/`run.json`: honest-failure ×5 (+ the 2nd sample's `leaf_stop`,
  trajectory-only). No `claim_reconciliation_check_dropped` in any of them.
- **D3b is the mechanism that fired.** In 4 of the 6 samples the `claim_reconciliation` event
  carries the D3b text: `ruling="unclear" … "the judge blamed the check, but its own reason names
  the source and no failing test function (self-contradicting)"` (sample 1 seq 71, r1 seq 90,
  r2 seq 71, r4 seq 80). r3's judge named the failing test function (`test_ac3_implement_to_contract`),
  so D3b correctly did not apply and the *pre-existing* P5(c) guard refused the drop
  (`claim_reconciliation_refused`); sample 2's judge answered "revision" and no drop was needed.
- **Recorded-input replay** (same verdict as the WIP sample, fed to the new code with a
  reconstructed request): `reconciliation_ruling(filtered, req)` → `"unclear" … self-contradicting`,
  while `reconciliation_ruling(filtered)` (legacy `request=None`) still → `"check"`, and
  `reconciled_check_may_be_dropped(ruling="check", independent_approved=True, own_red_blocks=True)`
  is `True` vs `False` for `ruling="unclear"`. So the drop the WIP sample performed is impossible
  after the fix, and the signature is backward compatible.
- **Cannot be trivially satisfied by a wrong fix.** D3b is not a gate the model must pass; it only
  removes an excuse, so it can never grant anything. Its two bypasses stay closed: `blame="implementation"`
  only yields `"revision"` (never a drop), and a *coherent* `blame="test"` that names a failing test
  function still must pass the P5(c) guard, which needs an approving independent verification at the
  same revision (`reconciled_check_may_be_dropped`, `1897-1928`) — and FIX 3 removes a re-sampled IV
  from that corroboration role. The remaining hole is the pre-existing D4 class the handoff discloses
  (all three model-written checks approve + only non-behavioural anchors are green).
- **Battery numbers check out** (run.json/run.log): after arm 15 matched tasks → 1 claim, 9 actual,
  0 false successes; before arm → 3 claims, 10 actual, **2** false successes (A-02, T-35). Matches
  the handoff's table. Disclosure nits: `T-35-r5` is an aborted sample (28 events, no `leaf_stop`,
  no `run.json`) and is correctly absent from the handoff table; the 6th sample shares
  `close/after/T-35-interval-merge-invariants/` with the 1st, whose `run.json`/`grade/` were
  overwritten, so its `actual` is not independently recorded (its `claimed=False` is).

## 4. FIX 7 and the grader gate

Reproduced the before/after on one scenario (temp dir outside the repo; the same pytest
invocation with and without the flag):

```
AFTER  (flag):    observed=True anomaly=tests-failed   n_failed=0 n_errors=1 green=False  canary passed=True
BEFORE (no flag): observed=True anomaly=canary-missing n_failed=0 n_errors=1 green=False  exit=2
_before _gate_blocks_as_red=False iv_non_discriminating=True
_after  _gate_blocks_as_red=False iv_non_discriminating=True
```

So an import error in the independent verification still cannot pass: the gate is not green,
`_gate_blocks_as_red` is `False` (M4: no real failure), and `iv_verdict_is_non_discriminating`
is `True`, i.e. it blocks a review-carried claim (`harness/leaf.py:2245-2300`). The flag only
replaces a false "the report cannot be this run's evidence" reason and lets the canary
authenticate. Scope is correct: the flag is inline in the leaf's runner (`5349`);
`harness/staging.py` is untouched by the commit, and the external grader's own gate
(`bench/external_score.py:233`, the `suspected-contaminated-grade` source) has no flag.

## Findings

### P2-1 — FIX 2 changes no decision (record-only), so its "block the unmet" test does not test a behaviour change
`harness/leaf.py:1848-1862`, `7150`, test `tests/unit/test_v2_leaf.py:7537` (baseline
`ImportError`).
Evidence: exhaustive 56-case comparison of the pre-wave predicate vs `iv_blocking_final_ids`
→ 0 differences; the test's baseline-reachable half (`iv_all_inverted(mixed) is False`) already
held at baseline, and its discriminating half only exercises the new helper's existence.
Smallest fix: none in code; restate §1 FIX 2 in the handoff as "record/ledger classification
(the gate outcome is unchanged)" so the closure claims stay auditable. If a behaviour change was
intended, it needs a test that fails at baseline on a mixed-file *blocking* outcome — which
cannot exist, because the outcome is identical.

### P2-2 — D2's "the recorded traceback proves the run's OWN TEST is at fault" is not reachable with production failure text
`harness/leaf.py:3699-3718` (`failure_is_test_attributed`), `3920`, `3956`, `8429`.
Evidence: `excerpts_of`/`exec._shape` hand the judge at most the first three lines containing
failure markers (`harness/exec.py:70-85`), which for a real own-test failure are
`FAILED tests/test_leaf_self.py::test_goal`, `E       assert 0 == 42`,
`E        +  where 0 = result()` — **no `path.py:line:` frame**, so `_failure_frame_paths`
returns `()` and the attribution is always `False`. Probe output for both a direct assertion
failure and a source-raised exception was the same (no frames). Empirically,
`test_attributed_from_traceback` appears in none of the 16 recorded run trajectories, and no
`judge_test_attributed`/`m1_erase_suppressed` event exists in any of them. Separately, the
heuristic cannot distinguish "the test asserts a wrong value" from "the source returns a wrong
value" (both fail on the test's own assert line), so its docstring "proves" overstates it — it is
inert today (no false-success risk), but widening the excerpt shaping would turn it into a
switch that overrides the judge's `implementation_wrong`.
Smallest fix: state D2 as latent/unexercised in the handoff, and either tighten the guard
(require the failure to be a non-assertion error whose only frame is the test, or require the
judge's label not to name the source) or feed the judge a real traceback so the mechanism has
production inputs.

### P2-3 — D1's `contract-clear` restore installs a revision with no verification of its own, and the record can label it "test"/"review"
`harness/leaf.py:6069-6093` (capture), `6135` (the own-test-only refusal), `7707-7710`
(restore only when unclaimed), `7737-7739` (tier map has no `contract-clear` entry → `"none"`),
`7824` (`delivered_tier or verification_tier …` — `"none"` is falsy, so the run's terminal
verification tier is recorded instead).
Evidence: the D1 test asserts only `delivered_revision["best_tier"] == "contract-clear"` and the
on-disk file (which the *last written* attempt also produced), not `restored is True`; in the one
recorded run where the capture fired (`/tmp/wave1/after/T-28-…log:21`) the delivery was
`restored=False best=contract-clear#1`, so D1's end-to-end delivery effect is unit-test-only.
No false success is possible on this path (a granted claim suppresses the restore), so this is a
traceability issue, not a gate hole.
Smallest fix: give the branch an explicit tier (`{"own-test": "test", …, "contract-clear":
"contract-clear"}`) or force `delivered_tier = "contract-clear"` truthiness so `7824` records it
instead of the run's terminal tier; and (P3) the message at `7765-7773` says "the last-written
revision already carried the strongest evidence (contract-clear, rank 1)" — `contract-clear` is a
snapshot-only label and cannot be a last-written tier (recorded T-28 log line).

### P2-4 — FIX 7 removes the independent test's bounded repair for an import/collection error
`harness/leaf.py:4550-4556` (`_IV_REPAIRABLE`), `5169-5179` (`orig_red` now `True` when the
anomaly is `tests-failed` with `n_failed == 0`), `7405-7412`/`8955-8960` (repair dispatch).
Evidence: before the flag an IV import error produced `canary-missing` →
`independent-test-unobserved`, which is in `_IV_REPAIRABLE` → one bounded re-ask; after the flag
it is `independent-test-red-on-final`, which is deliberately NOT repairable, so a fixable import
typo in the IV is never re-asked. Both states block the review route, so this adds no false
success — it is a new dead end that the handoff's claim does not mention.
Smallest fix: treat an errors-only final red as repairable (or keep `independent-test-unobserved`
as the reason while keeping the corrected gate detail), e.g. add the red-on-final case when
`final_gate.n_failed == 0 and final_gate.n_errors > 0`.

### P2-5 — the recorded isolation block no longer describes the leaf's own pytest invocation
`bench/v2_leaf.py:558-563` records `"pytest_args": list(PYTEST_ISOLATION_ARGS)` with the comment
"both the leaf's own pytest and the grader's pytest run the same env/args"; after FIX 7 the leaf's
own run adds `--continue-on-collection-errors` inline (`harness/leaf.py:5349`). The trajectory's
`test_run` records carry the flag, but the persisted `isolation` summary does not.
Smallest fix: record the leaf's actual args (e.g. `list(PYTEST_ISOLATION_ARGS) +
["--continue-on-collection-errors"]` for the leaf, unchanged for the grader) or amend the comment.

### P2-6 — D3 also removes the spec-bubble stop permanently for an incoherent `spec_wrong` (not just on the first attempt)
`harness/leaf.py:3925-3936` coerces `spec_wrong` → `implementation_wrong` with `coerced=True`,
`6733-6745` then never bubbles, and the coerced verdict cannot set the M2 judge blocker
(`6724-6727` deliberately ignores coerced verdicts). At baseline an incoherent `spec_wrong`
parked the node; now it keeps iterating toward the review route. Intended (T-35 was abandoned
after one attempt on a mislabelled code defect) and empirically safe so far (after arm: 0 false
successes in 15 runs, and the T-35 spec verdicts were coerced in every sample yet all 6 T-35
samples ended unclaimed), but it widens the set of shapes that reach a claim decision and should
be recorded as a residual rather than left implicit in the handoff's "+ ≥2 attempts" phrasing.
Smallest fix: none required; record the residual in the ticket (with the after-arm evidence).

### Not findings (checked, no problem)
- No new *claim* path from D1/FIX 6: `best_revision` feeds only the unclaimed delivery record
  (`7707-7740`); `claim_decision` and its callers never read it, and a granted claim suppresses
  the restore (`7709`).
- FIX 5 only adds blocking; empty `source_revision` (legacy/test callers) is skipped by the
  `verdict.source_revision` guard (`874`), and changed bytes re-approve (verified).
- The commit modifies no pre-existing `.scratch` file (`git show --name-status`: all added) and
  every WIP added-line from `fix-wave-1-wip.patch` appears verbatim in HEAD (no silent revert).
- `bench/v2_measure.py` re-implements nothing: it calls `bench.v2_leaf.run_once` and reads the
  persisted claim (`bench/v2_measure.py:6-8,346-366`).

## Merge verdict

**OK-with-notes.** All eleven fix claims are present in the code, each with a regression test
that fails on `72538ab` and passes on `45ebb32`; the structural one-gate invariant holds; the
T-35 false-success class is closed by D3b (recorded-input replay + 4/6 samples showing the D3b
ruling) with 0 false successes in the 6 post-fix samples; the battery totals match the on-disk
records; and FIX 7 neither weakens the grader nor lets an IV import error pass. No P0/P1. The
notes are scope/record accuracy (P2-1, P2-2, P2-3, P2-5) and two new dead ends/trade-offs worth
recording (P2-4, P2-6); none of them changes a gate outcome, and no unverified mechanism was
presented as measured.
