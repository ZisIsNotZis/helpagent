# Roadmap — what you can see at each step

This project has no UI. Its product surface is **a command you run and the honest report it
prints**, so every slice below is something you can run and look at yourself. A slice is done
when you can see it, not when the code for it exists.

The goal statement is in [`README.md`](../README.md); the current numbers are in
[`docs/STATUS.md`](STATUS.md) §8e; the internal implementation phases (which are means, not
milestones) are in the work record `.scratch/27-campaign/`. If this file and a work record
disagree about *what you can see*, this file wins.

## The slices

| # | what you can see | the check you run yourself | state |
| --- | --- | --- | --- |
| **V1** | *One task, fixed, with its evidence.* You hand the harness a request; it edits the repo, runs its own verification, and prints what it changed, what it verified, and what it could not. | `uv run python bench/v2_leaf.py --task bench/corpus/T-01-ttl-seconds-ms --calls 24 --out /tmp/slice1` then read `work/` and the printed claim basis | **done** |
| **V2** | *The honest scoreboard.* You run the whole corpus and get a table: what the harness claimed, what an independent grader actually found, and the trajectory behind every one of them. | `uv run python bench/v2_sweep.py --tasks T-01..T-20 --n 1 --calls 24 --verify full --server http://127.0.0.1:8834` then `bench/runs/v2sweep-*/results.jsonl` | **done** |
| **V3** | *It does not lie, and it explains itself.* The scoreboard's false-success column reads **0**, and every task that still fails prints a one-line reason you can check against its trajectory. | the same sweep: count `claimed && !actual` (must be 0) and read each failed task's `stop_reason`; the per-task verdicts exist for all 40 | **open** — today: 3 false successes (T-27, T-30, T-35) and 12 failures with no verdict yet |
| **V4** | *It beats the mature CLI on the same model, and costs less.* You run both arms on the same 40 tasks and see one side-by-side table: actual, claimed, tokens, wall-clock. | our sweep + `bench/pi_baseline.py --thinking max --reasoning` (and the same with `--append-prompt`), one revision each | **open** — 24/40 vs pi's 27/40, tokens 18.4k vs 9.0k; the prompt-improved arm is blocked by an unrelated GPU job |
| **V5** | *It works on a repository it has not seen before.* You point it at a repo that ships its own visible tests (so "no regression" is actually observable) plus a hidden grading suite, and it behaves the same as on the corpus. | a new corpus task with a visible smoke suite; the regression stage must report `observable=True` | **open** — on today's corpus the regression stage is unobservable (STATUS limit 7) |
| **V6** | *The product.* One command you can point at your own repository: `helpagent "<request>"` → it edits, verifies, and prints what it verified and what it could not, with the evidence trail on disk. Installable, with a short usage page. | run it on a repo outside this one, from a clean install | **open** — this is the thing all of the above is for; it does not exist yet |

Related work that is **not** a slice (means, so not milestones): the node structure, the three
states, the judge rules, the write policy, the prompt shape, the knowledge service. They are
tracked in `.scratch/27-campaign/` and described in `docs/FLOW.md`.

## What "done" means overall

All six slices are visible at once, on one frozen revision, with the numbers in
`STATUS.md` §8e. The five acceptance criteria that decide that are:

| # | criterion | which slice shows it |
| --- | --- | --- |
| C1 | coding >= pi on the same model with every knob maxed, and better in wall-clock and tokens | V4 |
| C2 | verification carries information (no meaningless test or review; failures traced to their exact deviation point) | V3 + the trajectory behind every line of V2 |
| C3 | no unexplained failures: every remaining failure has an evidenced `our-defect` (with the fix) or `model-ceiling` (with the evidence) | V3 |
| C4 | structural superiority: work that prompting alone cannot get out of pi but the structure can | V4, the `--append-prompt` arm |
| C5 | efficiency measured, not assumed | V4 |

## What you can see today

```sh
# V1 — one task, end to end
uv run python bench/v2_leaf.py --task bench/corpus/T-01-ttl-seconds-ms --calls 24 --out /tmp/slice1

# V2 — the honest scoreboard for a slice of the corpus
curl -fsS --max-time 3 http://127.0.0.1:8834/health     # the model server must answer ok
uv run python bench/v2_sweep.py --tasks T-01-ttl-seconds-ms,T-02-off-by-one --n 1 --calls 24 \
  --verify full --server http://127.0.0.1:8834
```

V1 and V2 work now. V3 through V6 do not, and each row above says exactly what is missing rather
than how far along the code is.
