**English** | [简体中文](README.zh-CN.md)

<img src="assets/logo.svg" alt="helpagent" width="200">

# helpagent

### A coding harness wrapped around a 4B local model, measured to its pre-registered end — with the losing half of the record kept.

**It answers one question with evidence instead of a demo: does a program wrapped around a small
local model code better than the same model driving a free-form CLI? The measured answer here is
"not established, and probably not as built" — and every decisive number still re-derives offline
from this repository in one command.**

> **Status: archived research.** The campaign ran to its pre-registered end. None of the three
> goals was established and none was disproved; the product this was built toward does not exist.
> What it produced is a measurement protocol, three verdicts and a body of retracted claims — now
> written as a paper a person can read and check without running a model. The campaign cannot be
> extended from this checkout: it ran a local 4B model on a GPU, and the machine holding it now has
> none ([`docs/3_REQUIREMENT.md#no-gpu-and-none-expected-on-this-machine`](docs/3_REQUIREMENT.md#no-gpu-and-none-expected-on-this-machine)).

## 1. Read the result

| what | where |
| --- | --- |
| the whole campaign as one paper — abstract, protocol, three verdicts, negative results, limits, numbers appendix | [`docs/paper/preprint.md`](docs/paper/preprint.md) |
| every decisive number, its source and the command that re-derives it | `python3 reproduce.py`, then [`docs/paper/numbers.md`](docs/paper/numbers.md) |
| the verdicts, and what they cannot carry | [`docs/2_GOAL.md`](docs/2_GOAL.md) |
| the harness' design and its one flow | [`docs/6_ARCHITECTURE.md`](docs/6_ARCHITECTURE.md) |
| what was tried and lost, with numbers | [`docs/8_DETAIL.md`](docs/8_DETAIL.md) |
| order of work, and what is deliberately not on it | [`docs/0_ROADMAP.md`](docs/0_ROADMAP.md) |

The three verdicts, in one line each: capability parity with the mature CLI is **INCONCLUSIVE** at
the pre-registered margin (`24.640/40` tasks vs `24.960/40`, delta `−0.320`, task-clustered 95%
interval `[−3.520, +3.080]`); verification is **partly informative, not as stated**, at about twice
the baseline's token count; the tree-of-children bundle is **NEGATIVE** (`14/70` runs fixed against
`47/70` for a plain leaf).

## 2. Quick start

```sh
git clone https://github.com/ZisIsNotZis/helpagent && cd helpagent
python3 reproduce.py                 # every decisive number, from committed rows only
python3 docs/paper/check_citations.py   # the paper still quotes those numbers: 0 unresolved
```

No install, no model, no network, no 2 GB campaign archive — the entry point reads
`bench/projection/` (half a megabyte, tracked) and fails loudly on a starved or zero-row input.
Reading the paper needs nothing at all: [`docs/paper/preprint.md`](docs/paper/preprint.md).

## 3. What it does

The harness is a deterministic program; the model is a contract-bound fallback node. Every model
call is one bounded step with a typed input and output, used only where no deterministic code can
do the job. The surrounding flow — plan, implement, test, review, claim — is ordinary code with
budgets, and deterministic checks own every fact that can be computed
([`docs/1_PROBLEM.md`](docs/1_PROBLEM.md)).

One run takes a task from the corpus (a `request.md` and a broken `repo/`) through planning into a
small node structure with ranked approaches, implementation plus a test that must fail first, an
independently authored test and a graded review, and one claim gate that decides whether the run
may declare the task fixed — recording which evidence carried the claim.

The blind protocol is the point, and it is what makes the numbers worth reading:

- **The grader's tests never enter the run.** Each task's own withheld suite scores it on a
  pristine copy afterwards ([`bench/external_score.py`](bench/external_score.py)).
- **Anything a run could do to its own scoreboard is refused or restored**, and the attempt is
  recorded: grader-owned paths are reset, `sys.path`-shadowing files are never applied.
- **Evidence is a machine-readable pytest report** on a private path with a per-run canary and the
  expected test ids. An exit status is never evidence.
- **One claim gate.** Exactly one function can grant a claim
  (`harness/leaf.py::claim_decision`), and a structural test fails the suite if any other path
  could produce one.

## 4. What works now

- **The gate** — unit, contract, corpus-integrity and tamper-guard tests; no model required.
- **One task end to end** — leaf flow plus evidence trail on disk (`bench/v2_leaf.py`).
- **A blind sweep** — claimed vs what the external grader actually found, table and trajectories
  (`bench/v2_sweep.py`, `bench/external_score.py`).
- **The tree driver** — the multi-node bundle that the campaign measured and rejected
  (`bench/v2_tree.py`).
- **The `pi` baseline arm** — the mature CLI on the same model, for the head-to-head
  (`bench/pi_baseline.py`).
- **Offline reproduction** — `reproduce.py` recomputes the paper's numbers and refuses a key it
  does not print; `bench/checks/m1_acceptance.py` states the acceptance as an exit code;
  `bench/checks/docs_layout.py` keeps `docs/` filed by level.

## 5. Architecture

Two halves that never share a process: the harness that does the work, and the grader that scores
it. The harness (`harness/`) is the kernel and the flow — envelopes, the leaf loop, the claim gate,
the node tree, budget, the ledger and verification records. The drivers (`bench/`) run the
harness, grade the result and reduce the numbers: one task, a sweep, a tree, the baseline, the
external grader, the projection that the reproduction entry point reads. The model speaks only
through one envelope-typed interface (`harness/model.py`), and the fair comparison precondition
that makes the two arms comparable is stated in
[`docs/6_ARCHITECTURE.md#fair-comparison-precondition`](docs/6_ARCHITECTURE.md#fair-comparison-precondition).

```
.
├── harness/          the kernel and the flow: envelopes, leaf loop, claim gate, tree, budget, ledger
├── bench/
│   ├── corpus/       T-01..T-35: request.md, broken repo/, checks.py, solution.md
│   ├── anchor/       A-01..A-05, the five anchor tasks
│   ├── v2_*.py       the drivers: leaf, tree, sweep, measure
│   ├── external_score.py, pi_baseline.py   the blind grader and the baseline arm
│   ├── projection/   the committed rows reproduce.py reads
│   └── runs/evidence/  the curated evidence; bench/runs/wave1/ (2.0 GB) is untracked, hash-verified
├── tests/            the gate: kernel invariants, flow rules, corpus integrity, tamper guard
├── docs/             the current fact: levels 1..9 plus the preprint in docs/paper/
├── .scratch/         the work record behind it — narrative, not truth
└── reproduce.py      every decisive number, offline
```

`docs/` is the current fact; `.scratch/` is what produced it; a conflict resolves for `docs/`.

## 6. Develop

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/); dependencies are PyPI-visible only.

```sh
uv sync                              # dev deps, from uv.lock
uv run pytest -q -p no:warnings      # the gate: unit + contract, no model, <10s
python3 reproduce.py                 # the numbers still recompute
python3 docs/paper/check_citations.py
python3 bench/checks/m1_acceptance.py   # the frozen tag and HEAD both re-derive
```

A task needs a local llama.cpp server; start it, check `/health`, then drive one task:

```sh
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one \
  --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25
```

Server flags, the sweep driver, the corpus contract and how to add a task are in
[`docs/9_IMPLEMENTATION.md`](docs/9_IMPLEMENTATION.md).

## 7. Contribute

[`CONTRIBUTING.md`](CONTRIBUTING.md): this is an archived harness, so a change is worth making only
if it keeps a published result checkable — the gate green, the paper's numbers still re-deriving.
The rules any change must preserve are [`docs/3_REQUIREMENT.md`](docs/3_REQUIREMENT.md).

## 8. Roadmap

**Implemented** — M0: the campaign bytes secured in a declared home and hashed (`53 270` files,
`1 996 009 173` bytes, `bench/manifests/wave1.sha256`). M1: a citable preprint whose every decisive
number recomputes from the repository alone, with the acceptance as an exit code. V1: one task,
fixed, with its evidence. V2: the honest scoreboard.

**Not built, and not planned here** — V3 (zero false successes) closed at `2.20%`, not at zero. V4
(beating the mature CLI at lower cost) is met with an unfavourable answer: parity INCONCLUSIVE and
about `2x` the tokens. V5 and V6 — the product command you could point at your own repository —
were never attempted. The recovery of the harness and the controlled M2 evaluation stay frozen
where a previous round left them, authorised to no node below root
([`docs/0_ROADMAP.md`](docs/0_ROADMAP.md)).

What a future programme would need is stated rather than promised: a corpus with the statistical
power to settle parity, a paired within-task design, an improved-prompt baseline arm, and a clean
single-lane wall-clock comparison. Nothing in this repository is waiting on a worker.

## 9. License

[`LICENSE.md`](LICENSE.md) — GNU AGPL-3.0. Copyright (C) ZisIsNotZis.
