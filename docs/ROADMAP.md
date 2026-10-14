# Roadmap — what you can see, and the final verdicts

This project has no UI. Its product surface is **a command you run and the honest report it
prints**, so every slice below is something you can run and look at. A slice is done when
you can see it, not when the code for it exists. The project is now **complete and
archived**: the slices and the acceptance criteria have final verdicts, recorded here.

The current numbers are in [`STATUS.md`](STATUS.md). The extraction of what is reusable
and what is not is in [`LEARNINGS.md`](LEARNINGS.md). The narrative and the raw provenance
of the final campaign are in `.scratch/28-three-requirements/`. If this file and a work
record disagree about *what you can see*, this file wins.

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
| C2 | verification carries information (no meaningless test or review; failures traced to their exact deviation point) | **NOT MET as stated** | the own test is zero-information (`−1.33`, p=0.55) and review alone raises false successes (`+3.33`, p=0.031); only the review + independent-test combination carries a significant correctness gain (`+4.00`, p=0.012). `STATUS.md` §4. |
| C3 | no unexplained failures: every remaining failure has an evidenced `our-defect` (with the fix) or `model-ceiling` (with the evidence), zero false successes | **NOT MET** | per-task verdicts exist for the campaign revision (`d24410a`), but the final wave (`45ebb32`) changed which tasks fail; the final false-success rate is `2.20%` at N=25, not zero. `STATUS.md` §7, §10. |
| C4 | structural superiority: work that prompting alone cannot get out of `pi` but the structure can | **REFUTED / not shown** | decomposition / multi-approach is NEGATIVE (`STATUS.md` §5); coding is statistically indistinguishable, not superior (parity not established; INCONCLUSIVE at `M=3`); the improved-prompt baseline arm is unmeasured. |
| C5 | efficiency measured, not assumed | **MET (result unfavourable)** | tokens measured for ours (`~18.9k`/task) and partly for `pi` (`~9k`); the honest result is that the harness costs roughly twice as much. `STATUS.md` §6. |

## What you can see today

The two runnable slices (V1 and V2) work now; the campaign's three requirement verdicts
are recorded and independently recomputed from the raw rows. Everything else is either
not closed (V3, C1–C4) or never attempted (V5, V6).

```sh
# V1 — one task, end to end
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 --calls 24 --out /tmp/slice1

# V2 — the honest scoreboard for a slice of the corpus
curl -fsS --max-time 3 http://127.0.0.1:8834/health     # the model server must answer ok
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 \
  --verify full --server http://127.0.0.1:8834
```

## What is explicitly deferred as future research

- A corpus large enough to resolve the parity question (the 40-task corpus caps the CI at
  about `6.3` tasks even at infinite seeds).
- The product CLI (V6), and with it V5.
- The named cheap harness fixes (redirect on refusal, multi-file accumulation,
  coverage-ranked delivery, the green-path claim rule).
- A measured improved-prompt baseline.
- A clean single-lane wall-clock comparison for both arms.
- Sweeping the forced-leaf thresholds and re-testing requirement-level splitting on a
  design that isolates splitting from planning overhead.
