# helpagent

A research harness that wraps a small local model in a conventional software-engineering process,
and measures the result honestly. Reference model: **Spark-X2.5-4B Q4_K_M** on llama.cpp.

**Status: the campaign ran to its pre-registered end and the research is archived.** None of the
three goals was established and none was disproved; the product this was built toward does not
exist. What the campaign produced is a measurement protocol, three verdicts and a body of
retracted claims — and it is now written as a paper a person can read and check without running
a model.

## Read the result

| what | where |
| --- | --- |
| the whole campaign as one paper — abstract, protocol, three verdicts, negative results, limits, numbers appendix | [`docs/paper/preprint.md`](docs/paper/preprint.md) |
| every decisive number, its source and one command that re-derives it | `python3 reproduce.py`, then [`docs/paper/numbers.md`](docs/paper/numbers.md) |
| the verdicts and what they cannot carry | [`docs/2_GOAL.md`](docs/2_GOAL.md) |
| the harness' design and its one flow | [`docs/6_ARCHITECTURE.md`](docs/6_ARCHITECTURE.md) |
| what was tried and lost, with numbers | [`docs/8_DETAIL.md`](docs/8_DETAIL.md) |
| order of work, and what is deliberately not on it | [`docs/0_ROADMAP.md`](docs/0_ROADMAP.md) |

`python3 reproduce.py` re-derives every decisive number from committed rows: no model, no network,
no campaign archive, under five seconds. `python3 docs/paper/check_citations.py` proves the paper
still quotes them.

## What it is

The harness is a deterministic program; the model is a contract-bound fallback node. Every model
call is one bounded step with a typed input and output, used only where no deterministic code can
do the job. The surrounding flow — plan, implement, test, review, claim — is ordinary code with
budgets, and deterministic checks own every fact that can be computed
(`docs/1_PROBLEM.md`).

A run takes one task from the corpus (a `request.md` and a broken `repo/`) and drives it through
planning into a small node structure with ranked approaches, implementation and a test that must
fail first, an independently authored test and a graded review, and one claim gate that decides
whether the run may declare the task fixed and records which evidence carried the claim.

The blind protocol is the point:

- **The grader's tests never enter the run.** Each task's own withheld suite scores it on a
  pristine copy afterwards (`bench/external_score.py`).
- **Anything a run could do to its own scoreboard is refused or restored**, and the attempt is
  recorded.
- **Evidence is a machine-readable pytest report** on a private path with a per-run canary and the
  expected test ids. An exit status is never evidence.
- **One claim gate.** Exactly one function can grant a claim
  (`harness/leaf.py::claim_decision`), and a structural test fails the suite if any other path
  could produce one.

## Run it

The tests need no model; a task needs a local server.

```sh
uv run pytest -q -p no:warnings      # the gate: unit, contract, corpus integrity, tamper guard

uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one \
  --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25
```

The server flags, the sweep driver and the corpus contract are in
[`docs/9_IMPLEMENTATION.md`](docs/9_IMPLEMENTATION.md).

## Repository layout

| path | what it is |
| --- | --- |
| `harness/` | the kernel and the flow: envelopes, the leaf loop, the claim gate, the tree, budget, the ledger, verification records |
| `bench/corpus/`, `bench/anchor/` | the task corpora (`request.md`, `repo/`, `checks.py`, `solution.md`) |
| `bench/v2_*.py`, `bench/pi_baseline.py`, `bench/external_score.py` | the drivers: leaf, tree, sweep, measure, the external grader, and the `pi` baseline |
| `bench/runs/wave1/` | the campaign's measured bytes, 2.0 GB, untracked and verified by hash — not needed to reproduce the paper |
| `bench/projection/` | the committed rows the reproduce entry point reads |
| `tests/` | the gate: kernel invariants, flow rules, corpus integrity, the tamper guard |
| `docs/` | the design, the verdicts and the evidence — levels `1`..`9` plus the preprint in `docs/paper/` |
| `.scratch/` | the work record: tickets, measurement records, provenance; narrative, not truth |
| `mail/` | messages to and from this node |

`docs/` is the current fact. `.scratch/` is what produced it.

## License

[`LICENSE.md`](LICENSE.md).
