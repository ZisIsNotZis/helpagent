# 22 — verification policy at spec time, review precedence, and what it costs

Status: done (commits 4aec0ac, 64a592d)
Owner direction: 2026-10-02 — "judge the difficulty of writing a verification AT SPEC TIME;
if it looks hard, require a REVIEW instead; when a review and a verification disagree, the
REVIEW wins; if the verification cannot be written correctly after several tries, give up on
it and switch to review — i.e. update the plan."

## What was built

1. **Plan-time policy.** `PlanNode`/`ChildPlan`, `NodeSpec`, `LeafSpec` and every run record
   carry `verification_policy` (`test` | `review` | `either`) with a REQUIRED
   `verification_reason`. `test` = a discriminating test is required; `review` = a graded
   review is SUFFICIENT (a working test is still accepted, and is the stronger evidence);
   `either` = prefer a test, fall back to review. The policy is a FLOOR, not a mandate.
2. **The graded review outranks a conflicting test.** On the review route a well-evidenced,
   approving review grants a claim even when the run's own test and/or the independent test
   is red on the same revision; a rejecting review refuses even when a test is green. The
   disagreement is recorded with both sides' evidence (`verification_disagreement`) and the
   claim carries its basis.
3. **One recorded plan update.** A `test`-policy node whose test cannot be made to work
   (judge-credited `test_wrong` with a named defect, bounded repairs exhausted) performs ONE
   in-place update to review-based verification, recorded (old/new policy, reason, judge
   reason, attempt counts). At most once; never for `review`/`either`; never without the
   judge's confirmation. The declared policy and the effective policy are both recorded.
4. **Grant-calibre review evidence** (added after an adversarial lane demonstrated a review
   approving a wrong fix whose evidence named only a changed path): a review may GRANT only
   if it names the acceptance criterion it serves AND a specific observation (a value, or a
   behavioural verb with a symbol present in a changed file). A refusal is recorded as
   `review_not_grant_calibre`; reviews that merely inform are unaffected.
5. **The single claim gate still holds**, now with a hardened structural test: exactly one
   `_granted_claim` definition, the only literal `claimed=True` in the package, a recursive
   walk over `harness/**`, and an explicit whitelist of `claim_decision` call sites
   (`leaf.py: 3`, `tree_run.py: 1`).

## Measured (nine tasks, N=2, same model; the decisive table)

| claim rule | actual | claimed | true | missed | FALSE | calls |
| --- | --- | --- | --- | --- | --- | --- |
| agreement required (round 5) | 14/18 | 4/18 | 4 | 10 | 0 | 156 |
| review outranks a conflicting test | 12/18 | 11/18 | 9 | 3 | **2** | 174 |
| ... plus grant-calibre review evidence | 12/18 | 8/18 | **8** | 4 | **0** | 186 |

Per tier after the hardening: `review` 7 claims -> 7 true / 0 false; `review+independent-test`
1 -> 1 / 0. Before it: `review` 10 -> 8 / 2 (20%), both false successes on T-31 (a partial
call-site threading the review had approved). The evidence rule refused those grants instead.

## Honest residuals

- The review tier's error rate is the reviewing model's own; the sweep measures 0/8 but one
  sweep is one sample. That is why every claim records `claimed_basis` and why consumers are
  told to filter on it (never on `verification.tier`, which can read `test` on a review-decided
  claim).
- The grant-calibre filter is satisfiable by an echo of the criterion text containing a number
  (an adversarial lane showed this); it raises the bar substantially but cannot make a weak
  reviewer correct.
- The fundamental limit stands: two verifications sharing the same misreading agree, and no
  in-process rule catches that without a ground-truth oracle (DESIGN §10.8a).
