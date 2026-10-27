# 5. R2 — verification: partly informative, and more expensive than it returned

The question: does the verification ladder carry information — does adding own test,
independent test, review and a single claim gate make the delivered work more often correct,
and make the harness lie less often?

## The design

`600` runs: `5` cumulative arms, `40` tasks, `3` repeats, external grader only
(`docs/2_GOAL.md#r2-verification-information`). One stage is added per arm, so the ladder is:

| arm | runs solved | claimed | false success | calls/task | tokens/task |
| --- | --- | --- | --- | --- | --- |
| A0 development only, never claims | `70/120` | `0` | `0` | `1.01` | `1198` |
| A1 own test | `66/120` | `0` | `0` | `5.54` | `8480` |
| A2 own test + independent test | `65/120` | `1` | `0` | `6.63` | `10570` |
| A3 own test + review | `71/120` | `54` | `10` | `9.13` | `12696` |
| A4 full: own + independent + review + claim gate | `77/120` | `28` | `1` | `12.86` | `18894` |

The pairs are the analysis, not the totals: enabling a stage changes feedback, iteration,
stopping and delivery together, so each contrast is a net workflow effect
(`docs/2_GOAL.md#r2-verification-information`).

## What is informative

- **The independent test, with review present, reduces what the harness claims and how often
  it lies.** Claims fall by `-8.67` (p=`0.0009`) and false successes by `-3.00` with interval
  `[-5.67, -1.00]` (p=`0.031`) (`docs/2_GOAL.md#r2-verification-information`). In the full arm it withheld approval in
  `92/110` runs, `57` of which the final grader passed; that join is a stage-to-outcome
  comparison, not a measure of diagnostic accuracy (`docs/2_GOAL.md#r2-verification-information`).
- **Review, with the independent test present, has a positive correctness contrast:**
  `+4.00` with interval `[+1.33, +7.00]`, p=`0.012` (`docs/2_GOAL.md#r2-verification-information`).

## What is not

- **The own-test loop has no detected net correctness gain:** `-1.33` tasks with interval
  `[-5.67, +3.00]`, p=`0.549` (`docs/2_GOAL.md#r2-verification-information`). The interval includes both losses and
  gains, so this is not proof of zero information, and not proof of equivalence
  (`docs/2_GOAL.md#r2-verification-information`) — and the routing that feedback took inside the loop is a heuristic
  in its own right, so the null does not settle what test feedback carries (§7).
- **The independent test's own correctness effect is unresolved** — `+2.00` with interval
  `[-0.67, +4.67]`, p=`0.388` (`docs/2_GOAL.md#r2-verification-information`).
- **Review without the independent test raises false successes** by `+3.33` with interval
  `[+1.00, +6.33]`, p=`0.031` (`docs/2_GOAL.md#r2-verification-information`). A significant contrast beside a
  non-significant one does not establish that their difference — the interaction — is
  significant (`docs/2_GOAL.md#r2-verification-information`).
- **The net full-stack gain is unresolved:** `+2.33` tasks with interval `[-0.33, +5.33]`,
  p=`0.34` (`docs/2_GOAL.md#r2-verification-information`). The requirement R2 was written to test is therefore not met
  as stated (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).

Three readings hold this section together. First, these are workflow effects, not measurements of
information content: a stage that changes the code path can change the outcome without any
signal in it (`docs/2_GOAL.md#r2-verification-information`). Second, agreement is not proof: both internal verifiers can
share one misreading and certify a wrong fix, and the final audit found a run where the
independent test and the review jointly approved an answer the grader failed
(`docs/8_DETAIL.md#false-successes-and-honesty`). The external grader is the only correctness arbiter
(`docs/2_GOAL.md#known-limits`). Third, the p-values are descriptive rather than confirmatory: five paired
contrasts on three metrics with no multiplicity correction, three repeats per task, stage costs
that are not matched, and a server restarted mid-campaign, so an unseen configuration drift would
be undetectable (`docs/2_GOAL.md#r2-verification-information`). A reader should treat each p-value as one unadjusted
contrast among several, which is why this section reports the intervals beside them.

## The cost, which is unfavourable

Verification is not free, and the ladder prices it:

- the own-test loop costs about `7` times the tokens and `6.6` times the wall time of
  development-only (`docs/2_GOAL.md#r2-verification-information`);
- the full stack costs `12.86` calls and `18894` tokens per task against `1.01` call and
  `1198` tokens for development-only (`docs/2_GOAL.md#r2-verification-information`, `docs/2_GOAL.md#r2-verification-information`);
- against the mature CLI, the harness spends about `18.9k` tokens per task against about `9k`
  (`docs/8_DETAIL.md#cost`). The harness is roughly twice as expensive, not cheaper.

The `pi` half of that token comparison is only partly measured: the driver carries no token
counters, so its `~9k` comes from the recorded reference and is not recomputable from the final
rows (`docs/8_DETAIL.md#cost`). It is recorded as unknown in the numbers table, not as fine.

Wall-clock is not clean or comparable — ours was measured under concurrency and `pi`
sequentially, so the two are not like-for-like (`docs/8_DETAIL.md#cost`). A single-lane subset
measured `31.0` s/task against `47.5` s/task on `8` tasks, one run, skewed easy
(`docs/8_DETAIL.md#cost`), which is indicative only; a clean single-lane comparison of both arms
over the full corpus is outstanding and is recorded as open (`docs/8_DETAIL.md#cost`). No
wall-clock win is claimed anywhere in this paper.

## What a reader should take away

Verification bought honesty more reliably than it bought correctness: the claim gate made
lying measurable (`docs/3_REQUIREMENT.md#a-verification-pipeline-that-can-be-reused`) and the false-success column is where the harness
beats the baseline (§3), while the correctness contrasts are mostly unresolved and the
cost is roughly double. A reader who installs a claim gate should expect a lower false-success
rate; a reader who installs a test loop should expect to pay for it and should measure whether
the correctness moved, because this campaign could not show that it did.
