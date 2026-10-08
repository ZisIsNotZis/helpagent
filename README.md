# helpagent

A coding harness for a **small local model** (reference: Spark-X2.5-4B on llama.cpp). The
model is weak, so the harness supplies what it cannot supply for itself: a fixed pipeline,
deterministic checks it cannot talk its way past, and an honest record of what was and was
not verified.

Measured position (same reference model, nine corpus tasks, two runs each, grader run
OUTSIDE the run): the harness fixes roughly two thirds of the tasks, claims only what it can
back with evidence, and records exactly what evidence every claim — or refusal to claim —
rested on. Numbers, method and known limits: [`docs/STATUS.md`](docs/STATUS.md).

## The idea in one page

- **The grader's tests never enter the run.** Each corpus task's own suite is the scoring
  instrument. The harness sees only source; the produced files are later applied to a
  pristine copy and graded there (`bench/external_score.py`). Anything a run could do to
  its own scoreboard — rewriting the grader's tests, `conftest.py` hooks, module shadowing,
  a forged exit status — is refused or restored, and every attempt is recorded.
- **A run must verify itself, and must not lie about it.** A node writes its own test
  (which must fail first), iterates red to green, and the harness re-derives the evidence
  from the machine-readable pytest report (a private report path, a per-run canary and the
  expected test ids — an exit status is never evidence).
- **One claim gate.** There is exactly one function that can grant a claim
  (`harness/leaf.py::claim_decision`), every path routes through it, and a structural test
  fails the suite if any other code path could produce a claimed outcome. It refuses a
  claim when the run's own test is red, when coverage missed a criterion's named artifact,
  when there are no criteria, or when the evidence ledger is empty.
- **Evidence in both directions.** Each acceptance criterion gets a ledger row —
  satisfied / violated / unverifiable — pointing at what was actually observed. A stop
  that produced no evidence at all is recorded as an EVIDENCE GAP, not as an honest
  failure.
- **Greedy by default.** A node plans ranked approaches ("Hows"), takes the top one and
  spends its budget there; competitive exploration of several candidates is opt-in
  (`--how-explore`). Measured: the tournament costs several times more and fixes fewer
  tasks, so it is not the default.

## Running it

```sh
uv run pytest                     # the unit/contract gate (fast, no model needed)
uv run pytest tests/unit/test_corpus_integrity.py   # every corpus task must be winnable
```

With a local model server on `http://127.0.0.1:8833`:

```sh
# one task, the leaf driver (self-test + independent verification + review + claim gate)
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --calls 24 --deadline-hours 0.25

# a blind sweep (claimed vs what the grader found)
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24

# the tree driver (budgeted decomposition over the leaf loop, greedy Hows)
uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading --calls 60 --deadline-hours 0.5
```

PyPI-visible dependencies only; Python 3.12+.

## Layout

| Path | What it is |
| --- | --- |
| `harness/` | the kernel and the flow: envelopes, the leaf loop, the claim gate, the tree, budget, the ledger, the verification records |
| `bench/corpus/`, `bench/anchor/` | task corpora (`request.md`, `repo/`, `checks.py`, `solution.md` — exactly four entries) |
| `bench/v2_*.py` | the drivers: leaf, tree, blind sweep, external grader, plus the baselines used to measure the harness against |
| `tests/unit/` | the gate: kernel invariants, the flow rules, corpus integrity, and the repository's own tamper guard |
| `docs/` | design and contracts; start with [`docs/STATUS.md`](docs/STATUS.md) and [`docs/DESIGN.md`](docs/DESIGN.md) §10 |

`docs/DESIGN.md` is the long-form design and records which parts are implemented, which
are designed but not built, and the residual risks that are accepted rather than fixed.

## Where each thing is documented (SSOT)

One owner per subject; if two files disagree, the one listed here wins.

| subject | file |
| --- | --- |
| the flow: how a task is processed, node structure, execution, states, judge, verdict | `docs/FLOW.md` |
| architecture: subsystems, data flow, repository layout, design principles | `docs/DESIGN.md` |
| the measured position: what works, what was retracted, what is not built, how to reproduce | `docs/STATUS.md` |
| the kernel's envelope/step API and its invariants | `docs/KERNEL_API.md` (index), `docs/ENVELOPE_SCHEMAS.md` (per-schema detail) |
| the test plan the suite is built from | `docs/TEST_PLAN.md` |
| known model failure patterns and the rule that fixes each | `bench/FAIL_PATTERNS.md` |
| the corpus (tasks, anchors, checks contract) | `bench/corpus/README.md` |
| active work and handover | `.scratch/active-work.md`, `.scratch/<ticket>/` |
| run evidence (curated) | `bench/runs/evidence/` |

Nothing else in this repository is documentation: a file that only restates another file's subject
gets deleted, not kept. When a section is superseded, it becomes a one-line pointer.
