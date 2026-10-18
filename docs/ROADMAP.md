# Roadmap — what you can see, and the final verdicts

This project has no UI. Its product surface is **a command you run and the honest report it
prints**, so every slice below is something you can run and look at. A slice is done when you can see it, not when the code for it exists. The measured campaign is **complete and the research archived**; its verdicts are recorded here. The goals and acceptance criteria below are unchanged: unmet or unresolved is not disproved or impossible.

The current numbers are in [`STATUS.md`](STATUS.md). The extraction of what is reusable
and what is not is in [`LEARNINGS.md`](LEARNINGS.md). The narrative and the raw provenance
of the final campaign are in `.scratch/28-three-requirements/`. If this file and a work
record disagree about *what you can see*, this file wins.

## Approved recovery milestones

The measured campaign remains complete and archived; recovery work is active without changing R1/R2/R3, V1–V6 or C1–C5 below. The execution contract and complete known-problem dispositions are in [ticket 30](../.scratch/30-harness-recovery/ticket.md) and its [issue ledger](../.scratch/30-harness-recovery/issues.md). A package finishing is not a milestone finishing.

| milestone | deliverable and acceptance | user synchronisation |
| --- | --- | --- |
| **M1 — harness and test-workflow recovery** | Modified harness, deterministic regression tests that expose the original errors, and evidence for every known problem with disposition `verified fixed`, `refuted` or `blocked`; distinguish syntax/import/setup from assertion failures, route valid test/review feedback into implementation, preserve/revert/deliver candidates consistently across tree/leaf independently of claim, separately record context/length termination, and review visible-spec gaps without exposing hidden answers or changing acceptance. Configured project tests, fresh independent review and integrated consistency checks must pass; an unverified item cannot be represented as fixed. | Execute now; deliver evidence and pause at M1. |
| **M2 — frozen-method controlled evaluation** | After M1 method freeze, original-task regression plus held-out tasks and controlled retests isolating checker capability, feedback closure, field refinement and decomposition; hold model, grader, acceptance and resource conditions fixed, register comparisons before outcomes, report effectiveness and cost with uncertainty rather than infer gains from unit tests. | **Not authorised to start** until the user approves again after M1 delivery. No M2 experiments during M1. |

M1 packages are owned by the current sole worker unless the parent explicitly reassigns exclusive file ownership; depth 0, no worker delegation. The parent owns fresh-review scheduling and final integration. Implementation packages use one writer in the current worktree; read-only review may overlap a stable revision only.

| package / owner | cohesive outcome and proof | dependencies |
| --- | --- | --- |
| **P1 — test failure ownership / worker** | Separate test syntax/import/setup faults from behavior assertions; bounded repair/re-observation of malformed tests before source iteration; protect valid behavior-red feedback and record honest unavailable evidence. Deterministic regression fixtures include missing imports and genuine source failures. | Approved contract, baseline and resource admission for tests. |
| **P2 — feedback and accumulation / worker** | Valid independent-test/review diagnostics reach a subsequent implementation when budget permits; redirect repeated refusal/off-plan errors and accumulate multi-file changes without losing valid earlier work; retain deterministic closure/redirect/accumulation regressions. | P1 evidence interface; parent fresh review of stable P1. |
| **P3 — candidates and common delivery / worker** | Preserve per-attempt candidate bytes and evidence, rank required-surface coverage explicitly, revert unsafe later candidates, and use the same delivery policy for tree/leaf without conflating delivery with claim; plain-green discrimination remains enforced. Regression checks catch discarded valid candidates and non-discriminating green claims. | P1; P2 feedback/attempt interface. |
| **P4 — termination and visible-spec evidence / worker** | Distinct inference context/length vs driver-timeout records, visible-spec gap audit with declared unknowns and no hidden-answer injection, disposition evidence for every audit29/LEARNINGS issue. | P1–P3 records; can statically diagnose earlier but no overlapping writes. |
| **P5 — integrated M1 gate / parent integrator with assigned sole writer** | Configured project gate, scoped negative controls, fresh final-revision review and integration checks; exact hashes, issue dispositions and remaining limitations; deliver M1 and stop. Model experiments remain deferred to M2 notwithstanding the ordinary real-model contribution gate. | P1–P4 and their reviews; user approval required before any M2 work. |

DAG: `approval → P1 → P2 → P3 → P4 → P5 → M1 user gate → renewed approval → M2`. Scope discovery may split these into sequential cohesive packages in the ticket, not silently omit issues. Every package has at most two repair–independent-review cycles; two consecutive attempts without new evidence require a changed hypothesis or a recorded blocker.

**Current recovery state: P1a BLOCKED / INCOMPLETE at the exhausted two-review cap.** [Final independent review](../.scratch/30-harness-recovery/review-cycle2.md) found that a counterfeit failure heading inside captured stdout re-enables exception parsing, allowing printed `NameError` text to misclassify a genuine `AssertionError` and suppress implementation feedback. Passing suites do not satisfy final independent acceptance. Source is frozen; no further repair, test or third review is authorised, and renaming the package does not reset its cap. P1b and P2–P5 are not done; P1/M1 have not passed or been delivered. [Blocked checkpoint](../.scratch/30-harness-recovery/blocked-checkpoint.md) records the unchanged reviewed source, released resources, bounded report-schema finding and conditional next action; M2 remains unauthorised.

Budget: first round cumulative execution **8 hours**; at most **2 parallel execution packages**, currently only **1 worker**, **depth 0**. The first dispatch is at most **90 minutes**, an internal review/checkpoint slice rather than a user gate. No model experiments, paid services, model swaps, push, CLI or hidden-grader specialization. Heavy computation requires coordinated complete-bundle admission and observed runtime binding; small project tests use one conservative runner and bounded threads only after resource coordination. Preserve the pre-existing dirty documents/ticket29; no reset, stage, commit or push. All original acceptance below remains unchanged.

## The slices

| # | what you can see | the check you run yourself | final state |
| --- | --- | --- | --- |
| **V1** | *One task, fixed, with its evidence.* Hand the harness a request; it edits the repo, runs its own verification, and prints what it changed, what it verified, and what it could not. | `uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25` then read the printed claim basis | **done** |
| **V2** | *The honest scoreboard.* Run a corpus slice and get a table: what the harness claimed, what an independent grader actually found, and the trajectory behind each. | `uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 --server http://127.0.0.1:8834`, then read `bench/runs/v2sweep-*/results.jsonl` | **done** |
| **V3** | *It does not lie, and it explains itself.* Every task that fails prints a one-line reason you can check against its trajectory, and the false-success column is zero. | the same sweep, plus the campaign's per-task verdicts and the ablation false-success counts | **not closed** — the false-success rate was cut to `2.20%` head-to-head (ours) and to `1/120` in the full ablation arm, but not to zero; per-task failure verdicts exist for the campaign revision, and the final fix wave changed which tasks fail |
| **V4** | *It beats the mature CLI on the same model, and costs less.* Run both arms on the same 40 tasks and see one side-by-side table: actual, claimed, tokens, wall-clock. | our sweep + `bench/pi_baseline.py --thinking max --reasoning`, one revision | **not met** — head-to-head is INCONCLUSIVE at the pre-registered margin (`24.640/40` vs `24.960/40`), and tokens are about `2x` the baseline's (`~18.9k` vs `~9k`); the improved-prompt baseline arm is unmeasured |
| **V5** | *It works on a repository it has not seen before.* Point it at a repo that ships its own visible tests plus a hidden grading suite, and it behaves the same as on the corpus. | a new corpus task with a visible smoke suite; the regression stage must report `observable=True` | **open / not attempted** — on today's corpus the regression stage is unobservable (`STATUS.md` limit 7) |
| **V6** | *The product.* One command you can point at your own repository: `helpagent "<request>"` → it edits, verifies, and prints what it verified and what it could not, with the evidence trail on disk. | run it on a repo outside this one, from a clean install | **open / does not exist** — this is the thing the research was for; it was never built |

Related work that is **not** a slice (means, not milestones): the node structure, the
three states, the judge rules, the write policy, the prompt shape, the knowledge service.
They are described in [`FLOW.md`](FLOW.md) and tracked in the work record.

## Acceptance criteria — final verdicts

The five criteria the campaign set out to meet, with their final verdicts:

| # | criterion | verdict | evidence |
| --- | --- | --- | --- |
| C1 | coding >= `pi` on the same model with every knob maxed, and better in wall-clock and tokens | **NOT MET** | parity not established (INCONCLUSIVE at `M=3`, CI `[−3.520, +3.080]`); tokens about `2x` worse; wall-clock not cleanly comparable. `STATUS.md` §3, §6. |
| C2 | verification carries information (no meaningless test or review; failures traced to their exact deviation point) | **NOT MET as stated** | the own-test loop has no detected net correctness gain (`−1.33 [−5.67, +3.00]`, p=0.55), not proven zero information; review without independent test raises false successes (`+3.33`, p=0.031), while with independent test its correctness contrast is positive (`+4.00`, p=0.012); interaction not established and final failures not fully traced. `STATUS.md` §4. |
| C3 | no unexplained failures: every remaining failure has an evidenced `our-defect` (with the fix) or `model-ceiling` (with the evidence), zero false successes | **NOT MET** | per-task verdicts exist for the campaign revision (`d24410a`), but the final wave (`45ebb32`) changed which tasks fail; the final false-success rate is `2.20%` at N=25, not zero. `STATUS.md` §7, §10. |
| C4 | structural superiority: work that prompting alone cannot get out of `pi` but the structure can | **NOT SHOWN** | the current tree bundle is NEGATIVE; splitting and field refinement were not isolated from planning, budget and delivery policy (`STATUS.md` §5); no aggregate coding difference was detected (parity not established; INCONCLUSIVE at `M=3`); the improved-prompt baseline arm is unmeasured. |
| C5 | efficiency measured, not assumed | **MET (result unfavourable)** | tokens measured for ours (`~18.9k`/task) and partly for `pi` (`~9k`); the honest result is that the harness costs roughly twice as much. `STATUS.md` §6. |

## What you can see today

The two runnable slices (V1 and V2) work now; the campaign's three requirement verdicts
are recorded and their numerical results independently recomputed from the raw rows; that recomputation does not validate causal interpretations. Everything else is either
not closed (V3, C1–C4) or never attempted (V5, V6).

```sh
# V1 — one task, end to end
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 --calls 24 --out /tmp/slice1

# V2 — the honest scoreboard for a slice of the corpus
curl -fsS --max-time 3 http://127.0.0.1:8834/health     # the model server must answer ok
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 \
  --verify full --server http://127.0.0.1:8834
```

The bounded final-revision explanations in [ticket 29](../.scratch/29-close-audit/report.md) do not close C3: missing records and ungraded intermediate candidates remain explicitly unknown.

## What is explicitly deferred as future research

- A corpus/design with sufficient power for the parity question (the observed task effects project an asymptotic CI width of about `6.3` tasks; this is not an impossibility result).
- The product CLI (V6), and with it V5.
- The measured effectiveness of the named harness fixes: their implementation and deterministic checks are M1 work above; any capability/cost claim requires the separately approved M2 evaluation.
- A measured improved-prompt baseline.
- A clean single-lane wall-clock comparison for both arms.
- Sweeping the forced-leaf thresholds and re-testing requirement-level splitting on a
  design that isolates splitting and field refinement from planning/spec rewriting, budget and delivery policy.
