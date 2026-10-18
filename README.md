# helpagent

A research harness that wraps a small local model in a conventional software-engineering
process, and measures the result honestly.

**Status: campaign completed / research archived.** The three goals remain unmet or unresolved, not disproved. This is not a shipped product. It is a
measurement project with a working research harness. The product command it was built
toward (`helpagent "<request>"` against your own repository) does not exist. The results,
the reusable patterns and the negative findings are in [`docs/LEARNINGS.md`](docs/LEARNINGS.md)
and [`docs/STATUS.md`](docs/STATUS.md).

Reference model: **Spark-X2.5-4B Q4_K_M** on llama.cpp. The model is weak, so the harness
supplies what the model cannot: a fixed pipeline, deterministic checks it cannot talk its
way past, and an honest record of what was and was not verified.

## What it is

The harness is a deterministic program; the model is a contract-bound fallback node. Every
model call is a single bounded step with a typed input and output, used only where no
deterministic code can do the job. The surrounding flow (plan, implement, test, review,
claim) is ordinary code with budgets, and deterministic checks own every fact that can be
computed. The full idea is in [`docs/LEARNINGS.md`](docs/LEARNINGS.md) §1.

## What it does

A run takes one task from the corpus (a `request.md` and a broken `repo/`) and drives it
through:

1. **Plan** the work into a small node structure with ranked approaches (Hows).
2. **Implement** and **write a test** (the test must fail first, then iterate red to green).
3. **Verify**: an independently authored test, then a graded review of the change.
4. **Claim**: a single gate decides whether the run may declare the task fixed, and records
   *which* evidence carried the claim.

The blind protocol is the point:

- **The grader's tests never enter the run.** Each task's own withheld suite scores it. The
  run sees source only; the produced files are later applied to a pristine copy and graded
  there (`bench/external_score.py`).
- **Anything a run could do to its own scoreboard is refused or restored** (rewriting the
  grader's tests, `conftest.py` hooks, module shadowing, a forged exit status), and the
  attempt is recorded.
- **Evidence is a machine-readable pytest report** on a private path with a per-run canary
  and the expected test ids. An exit status is never evidence.
- **One claim gate.** Exactly one function can grant a claim (`harness/leaf.py::claim_decision`),
  and a structural test fails the suite if any other code path could produce one.

## Final measured results

Fair-comparison precondition for every number: the **same model** (Spark-X2.5-4B Q4_K_M),
the **same 32768-token server**, the **same 40-task corpus**, a **blind external grader**,
and the baseline (`pi` CLI) with **thinking max + reasoning**. Revision `45ebb32`.

| requirement | verdict | number |
| --- | --- | --- |
| **1. Coding capability vs a mature agent CLI** | **INCONCLUSIVE** (parity not established) | ours `24.640/40` (sd 1.22) vs `pi` `24.960/40` (sd 2.15), N=25 seeds/arm; delta `−0.320` tasks `= −0.8%`; task-clustered 95% CI `[−3.520, +3.080]`; the pre-registered `M=3` rule returns INCONCLUSIVE by `0.52` tasks. The CI width was flat from N=17 to N=25; at the observed task heterogeneity and point estimate, further seeds alone are not projected to resolve it. |
| **2. Does verification add information?** | **PARTLY / not as stated** | `600`-run five-arm ablation: development-only `70/120 (58.3%)` to full stack `77/120 (64.2%)`. Enabling the own-test loop did not detect a net correctness gain (`−1.33` tasks, CI `[−5.67, +3.00]`, p=0.55), not proof of zero information. The independent-test contrasts did not detect a correctness effect but reduced claims (`−8.67`, p=0.0009) and false successes (`−3.00`, p=0.031) with review present. The review contrast with independent test present gained `+4.00` (p=0.012); without it, false successes increased (`+3.33`, p=0.031). This does not establish an interaction. |
| **3. Does decomposition / multi-approach help?** | **NEGATIVE** | `210`-run pre-registered experiment. Monolithic leaf `47/70 (67.1%, 0 false)` vs tree-greedy `14/70 (20.0%, 4 false)` vs tree-tournament `15/70 (21.4%, 3 false)`; paired delta CI upper bounds below 0, p<0.001. The current tree bundle cost roughly 2 to 3x for far fewer fixes. Planning, budget and closed-only delivery also changed; splitting and field refinement were not isolated. |

False successes across the ablation arms: `0 / 0 / 0 / 10 / 1`. Head-to-head honesty:
ours `2.2%` vs `pi` `6.1%` false successes (difference CI excludes 0). Cost: ours about
`18.9k` tokens/task (4-lane, 40 tasks) vs `pi` about `9k`, so the harness is roughly twice
as expensive, not cheaper. Wall-clock evidence is not clean or comparable and is not
quoted as a result.

## Conclusion

- **Capability: no detected difference — parity not established (INCONCLUSIVE at `M=3`).**
  No aggregate capability difference was detected on this model, corpus and baseline (point estimate `24.640` vs `24.960`, delta `−0.320` tasks `= −0.8%`, inside the `±3` margin), but the pre-registered 95% test could not certify "within margin": the interval `[−3.520, +3.080]` was flat over N=17..25. Further-seed projections assume the observed task effects persist; this is not an impossibility result. Not proven stronger; not proven worse.
- **Reliability: a real but shallow advantage.** The lower false-success rate comes from a
  claim gate that anyone could add to any agent, so it is not a durable moat.
- **Cost: worse.** Roughly twice the tokens for no measured capability gain.
- **Scope:** all of the above holds only for this model, this 40-task corpus and this
  baseline.

The most valuable finding is not the headline. It is that the 2026-10-09 starting point was
`24/40` vs `27/40`, and the documented causes were a discarded grader-passing revision in
**T-07**, the closed T-30 claim hole, and content in **T-14** (T-17 and T-28, both
discarded-revision cases, came on the next revision). A harness can silently destroy
capability it already had, and only comparing the delivered bytes against every revision the
run wrote reveals it.

## What was tried and did not help

Measured, not guessed (details in [`docs/LEARNINGS.md`](docs/LEARNINGS.md) §5):

- **The measured tree / multi-approach bundle**: harmful here (section above); this does not isolate decomposition or field refinement.
- **Injecting a context index** (a compact index for files not declared in full): harmful.
- **Forcing a deterministic file-change order**: harmful.
- **A knowledge pack** (signatures / callers / constants) injected per call: no gain.
- **A competitive tournament of approaches**: fires, but costs `2.2`–`2.4x` the calls and
  fixes far fewer tasks (`15/70` vs `47/70`); greedy is the default.
- **Asking a weak model to write its own tests** (applied to the mature CLI): made it
  worse, because the 4B could not emit a whole test file as one tool argument. Measured at
  8k context; not re-measured at 32k.

These implementations spent extra calls without a measured net capability gain. That is a scoped outcome, not evidence that control flow or decomposition cannot help.

## Reusable parts

[`docs/LEARNINGS.md`](docs/LEARNINGS.md) is the extraction document. The reusable pieces:

- The design principle (harness as program, model as a contract-bound fallback node).
- The blind grading protocol and the tamper guard.
- The one-claim-gate invariant and its structural test.
- The evidence ledger and the `EVIDENCE GAP` state, and the claim-basis distinction.
- The measured division of labour between own test, independent test and review.
- Evaluation checklists, including "compare delivered bytes to every written revision".
- The negative results, which save a future project from repeating them.

The campaign is closed as a resource decision, not as proof that the goals are impossible. The bounded final-revision failure audit and its evidence limits are in [ticket 29](.scratch/29-close-audit/report.md).

## Future research

See [`docs/LEARNINGS.md`](docs/LEARNINGS.md) §8 and [`docs/ROADMAP.md`](docs/ROADMAP.md).
In short: a corpus large enough to resolve the question; the product CLI, run on an unseen
repository with visible tests; the named cheap harness fixes; and a measured
improved-prompt baseline.

## Repository layout

| Path | What it is |
| --- | --- |
| `harness/` | the kernel and the flow: envelopes, the leaf loop, the claim gate, the tree, budget, the ledger, verification records |
| `bench/corpus/`, `bench/anchor/` | the task corpora (`request.md`, `repo/`, `checks.py`, `solution.md`) |
| `bench/v2_*.py`, `bench/pi_baseline.py`, `bench/external_score.py` | the drivers: leaf, tree, sweep, measure, the external grader, and the `pi` baseline |
| `tests/unit/`, `tests/contract/` | the gate: kernel invariants, flow rules, corpus integrity, and the repository's own tamper guard |
| `docs/` | design and current-state docs; start with [`docs/STATUS.md`](docs/STATUS.md) |
| `.scratch/` | the work record: tickets, measurement records, provenance (narrative, not SSOT) |

`docs/` is the current fact; `.scratch/` holds the narrative and the raw provenance.

## How to run

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). PyPI-visible dependencies only.

```sh
uv run pytest                     # the unit/contract gate (fast, no model needed)
```

A model server is required for any real run. Start it, then check health:

```sh
llama-server \
  -m /path/to/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health     # {"status":"ok"}
```

Then one task, the leaf flow (own test + independent verification + review + the claim
gate):

```sh
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25
```

A blind sweep (claimed vs what the grader found), and the tree driver:

```sh
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 --server http://127.0.0.1:8834
uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading --server http://127.0.0.1:8834 --calls 60 --deadline-hours 0.5
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the working rules (single claim gate, one
writer per worktree, how to add a corpus task).

## License

AGPL-3.0. See [`LICENSE.md`](LICENSE.md).
