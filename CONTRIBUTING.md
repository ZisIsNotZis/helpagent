# Contributing

This is an archived research harness. The rules below are the ones that kept its results
trustworthy; follow them for any change.

## Run the gate

```sh
uv run pytest -q -p no:warnings     # unit + contract; no model needed; check the exit code
```

The gate includes the corpus-integrity suite and the repository's own tamper guard. Check
the exit code, never pipe it. A flow change is not done until it has also been exercised
once against the real model (see below).

## Run a task or a sweep

A model server is required. Start one and check health first:

```sh
llama-server \
  -m /path/to/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health     # {"status":"ok"}
```

```sh
# one task, the leaf flow (own test + independent verification + review + the claim gate)
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 \
  --calls 24 --deadline-hours 0.25

# a blind sweep (claimed vs what the grader found)
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 \
  --verify full --server http://127.0.0.1:8834
```

## Invariants

- **One claim gate.** Exactly one function can set a pass claim
  (`harness/leaf.py::claim_decision`), and every path routes through it. Never add a path
  that sets `claimed=True` anywhere else; a structural test fails the suite if you do.
- **Evidence is a report, not an exit status.** A change to the verification path must
  keep the machine-readable report, the per-run canary and the expected test ids.
- **One writer per worktree.** Read-only work needs no branch. Every concurrent writer
  (docs included) gets its own branch or worktree and never touches the main area while a
  measurement lane is running.
- **Retract in the same breath.** A number a later measurement contradicts is retracted in
  the commit that contradicts it.
- **A flow change needs a measurement.** Unit tests alone have let dead paths ship here; a
  behaviour change is not done until it has run once against the real model.

## Adding a corpus task

One directory per task (`T-<nn>-<slug>/`) with exactly four entries: `request.md`,
`repo/`, `checks.py`, `solution.md`. The contract is in
[`bench/corpus/README.md`](bench/corpus/README.md); the short version:

1. Build `repo/` with exactly one seeded bug and a focused failing test.
2. Verify red to green by hand: apply the fix, `pytest` passes, revert byte-exactly,
   SHA-256 check the restore.
3. Write `request.md` symptom-first (no file paths or symbol names), `solution.md` outside
   `repo/`, and `checks.py` with its explicit `UNTOUCHED` list.
4. On the pristine (broken) task, `checks.py snapshot && verify` must report the contract
   OK while the tests fail. That is the shipped state.

Then run `uv run pytest tests/unit/test_corpus_integrity.py`: every corpus task must be
winnable.

## Docs and the work record

`docs/` holds current facts (one home per fact); `.scratch/` holds the narrative, tickets
and provenance. Do not leave "was A, later B" narration in `docs/`; rewrite the current
fact in place and put the history in the ticket.
