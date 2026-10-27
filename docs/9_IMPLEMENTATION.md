# INFERRED

The practice: the gate, the model server, the corpus, the commands that produce and re-derive
every number, the secured home the campaign bytes live in, and the work record they are cited
from. The numbers themselves are in `docs/8_DETAIL.md` and their verdicts in `docs/2_GOAL.md`.

This is an archived research harness. The rules below are the ones that kept its results
trustworthy; follow them for any change.

Commands are written to be run at the repository root.

## How to run

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). PyPI-visible dependencies only.

### Run the gate

```sh
uv run pytest -q -p no:warnings   # unit + contract; no model needed; check the exit code
```

The gate includes the corpus-integrity suite and the repository's own tamper guard. Check
the exit code, never pipe it. A flow change is not done until it has also been exercised
once against the real model (see §run-a-task-or-a-sweep).

### The model server

A model server is required for any real run. Start one and check health first:

```sh
# the model server (final measurement config)
llama-server \
  -m /path/to/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8834 --host 127.0.0.1 -ngl 99 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0
curl -fsS http://127.0.0.1:8834/health     # {"status":"ok"}
```

### Run a task or a sweep

Then one task, the leaf flow (own test + independent verification + review + the claim gate):

```sh
# one task, the leaf flow (own test + independent verification + review + the claim gate)
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 \
  --calls 24 --deadline-hours 0.25
```

A blind sweep (claimed vs what the grader found), and the tree driver:

```sh
# a blind sweep (claimed vs what the grader found)
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 \
  --verify full --server http://127.0.0.1:8834
# the same sweep without --verify full
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-20-average-truncation --n 2 --calls 24 --server http://127.0.0.1:8834
uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading --server http://127.0.0.1:8834 --calls 60 --deadline-hours 0.5
```

The rules that go with these runs are `docs/3_REQUIREMENT.md#the-scoring-instrument-never-enters-the-run`
and `docs/3_REQUIREMENT.md#one-claim-gate-structurally-enforced`; how to add a corpus task is
§adding-a-corpus-task below.

## Reproducing the numbers

With the gate green and the model server up (§run-the-gate, §the-model-server), each requirement is
measured by its own driver. The frozen revision is `45ebb32`.

### R1 — our arm and the `pi` arm

```sh
# R1 our arm, one task (leaf flow, full verification)
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --server http://127.0.0.1:8834 \
  --calls 24 --deadline-hours 6 --verify full

# R1 pi arm (maxed baseline)
uv run python bench/pi_baseline.py --tasks T-02-off-by-one --n 1 \
  --base-url http://127.0.0.1:8834/v1 --reasoning --thinking max --out /tmp/pi-run
```

### R2 — the five-arm ablation

```sh
# R2 five-arm ablation (one arm per invocation; see the measurement record for the four arms)
uv run python bench/v2_measure.py --tasks "<task list>" --n 1 \
  --server http://127.0.0.1:8834 --ablate none --out /tmp/ablation
```

### R3 — the decomposition arms

```sh
# R3 decomposition arms
uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading \
  --server http://127.0.0.1:8834 --calls 48 --deadline-hours 1 --how-explore 1 --out /tmp/tree
```

The exact commands, seed lists, analysis scripts and
per-task tables for each requirement are in the work record
`.scratch/28-three-requirements/issues/`:
`fix-wave-1-measurement-n25.md` (R1), `requirement-2-ablation.md` (R2),
`requirement-3-result.md` (R3), and `final-measurement-independent-verification.md` (a
fresh-context recomputation of all three from the raw rows).

## Recomputing the archived numbers

The home (§the-secured-home) and the committed projection (§the-entry-point) make the three
verdicts recomputable without re-running a single task. The commands are rows of
§evidence-pointers; what they were measured to return is here.

**Recomputable from the home, measured for all three verdicts.** R1: `recompute_n25.py` runs
the campaign's own `analyze_n25.py` with its four roots pointed at the home and gets
`24.640` / `24.960` / `−0.320` / `[−3.520, +3.080]` over 1000 rows per arm, equal to the
recorded `analysis-n25-final.json`. R2: `r2_analyze.py --glob
'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` reproduces `analysis.txt` and
`analysis.json` byte-identically. R3: `R3=bench/runs/wave1/final/r3 analyze.py` reproduces
`analysis-r3.txt` byte-identically (`leaf 47/70` in the arm table's 70 runs, `tree-greedy`
`14/70`, `tree-tournament` `15/70`, McNemar `p ≤ 0.001`). So the three verdicts no longer
depend on a temporary path for anything a reader needs to check.

## The entry point

**Recomputable from the repository alone, measured.** `python3 reproduce.py` prints 21 `key value`
lines and exits 0 in 4.4 s on a tree with no `bench/runs` at all. What it reads, and why the
projection is small enough to commit, is `docs/8_DETAIL.md#the-projection`; how it fails on a
starved input is `docs/8_DETAIL.md#a-short-input-stops-the-run`, and the interface the command has
to keep is `docs/7_INTERFACE.md#entry-point-contract`.

Fidelity of the projection to the home it was cut from: `python3 bench/analysis/wave1/fix/verify_projection.py`
returns `ok files=472 rows=2810 mismatches=0`, and one flipped `actual` in a copy returns
`mismatches=1`, exit 1.

## The secured home

The declared home is `bench/runs/wave1/`, inside this checkout, a byte-for-byte
mirror of `/tmp/wave1/`: 53 270 files, 1 996 009 173 bytes, including `final/{n25,r2,r3}` and
the three roots the R1 analysis also reads. The layout is the source's, so the analysis
scripts resolve their arms unchanged. `git` cannot hold 2.0 GB, so the home is not tracked;
`bench/runs/*` already ignored it and now names it (`bench/runs/wave1/`). What makes it evidence
rather than merely present is `bench/manifests/wave1.sha256`: 53 270
lines, one per file, paths relative to the home, and `sha256sum -c` against it returns 53 270
`OK`, 0 `FAILED`, exit 0. The analysis scripts have a tracked home too —
`bench/analysis/wave1/{final,n25,r2,r3}/`, 36 files, 252 KB — so a fresh session finds what
computes the intervals without mounting the 2 GB; `verify_home.py` checks each of those 36
against the manifest entry of the file it came from, and all 36 match. They are frozen copies of
scripts that ran during the campaign, so their own prose still names the documents by their old
paths; do not edit them, because the manifest is what makes them evidence.

## What is tracked, and what is not

`bench/runs/evidence/` (802 files, 5.4 MB) is the only tracked run evidence, and it predates the
final campaign — its newest record is dated `20261006`. The campaign's decisive numbers hang on
three archived verdicts, stated in `docs/2_GOAL.md` and measured in `docs/8_DETAIL.md#cost` and
`docs/8_DETAIL.md#false-successes-and-honesty`, whose bytes are the untracked home above.

## Adding a corpus task

One directory per task (`T-<nn>-<slug>/`) with exactly four entries: `request.md`,
`repo/`, `checks.py`, `solution.md`. The contract is in
`bench/corpus/README.md`; the short version:

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

`docs/` holds current facts, one home per fact, filed by level: `1_PROBLEM`, `2_GOAL`,
`3_REQUIREMENT`, `4_USECASE`, `5_PRODUCT`, `6_ARCHITECTURE`, `6_FLOW`, `7_INTERFACE`,
`7_ENVELOPES`, `8_DETAIL`, `9_IMPLEMENTATION`, plus `0_ROADMAP` and `0_STAGING` for order and for
what has no home yet. Zoning inside each file says where its content came from. `.scratch/` holds
the narrative, tickets and provenance — never truth. Do not leave "was A, later B" narration in
`docs/`; rewrite the current fact in place and put the history in the ticket.
`docs/paper/` is the deliverable and stands outside the levels: it renders itself and its numbers
are checked against the entry point (`docs/5_PRODUCT.md#the-deliverable`).

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/28-three-requirements/issues/` for this campaign; earlier tickets
  under `.scratch/17-*` .. `.scratch/27-*`.
- The extraction document (what is reusable, what is not): `docs/5_PRODUCT.md`.
- Stale handover notes inside `.scratch/` (for example `active-work.md`, dated 2026-10-09, which
  points at a status section that no longer exists) are kept as records and are superseded by
  `AGENTS.md` and `docs/`; do not read them as current.

## Where the evidence is

- Measured position: `docs/2_GOAL.md`; every decisive number and what it cost: `docs/8_DETAIL.md`;
  the reproduction commands: §reproducing-the-numbers of this document.
- Slices and acceptance-criteria verdicts: `docs/2_GOAL.md`.
- Measurement records, raw-row recomputation and provenance:
  `.scratch/28-three-requirements/issues/`
  (`fix-wave-1-measurement-n25.md`, `requirement-2-ablation.md`,
  `requirement-3-result.md`, `final-measurement-independent-verification.md`).
- Bounded final-revision causal audit, retained samples and evidence limits: `.scratch/29-close-audit/report.md`.
- Design and flow: `docs/6_ARCHITECTURE.md`, `docs/6_FLOW.md`.
- Curated baseline evidence: `bench/runs/evidence/`.

## Evidence pointers

| what | where |
| --- | --- |
| the preprint as one file a person reads end to end | `docs/paper/preprint.md` (a render; built and checked by `python3 docs/paper/build_preprint.py [--check]`) |
| the preprint's abstract, sections and index of kinds | `docs/paper/00-abstract.md`, `docs/paper/README.md` |
| every number the paper uses, its source and the command that re-derives it; the row count and the `unknown` rows are printed by the checker, and every unknown names its gap | `docs/paper/numbers.md` |
| resolve the paper's citations and its Numbers table (fails loudly on a moved anchor or a number with no command), and every document's cross-reference | `python3 docs/paper/check_citations.py` → `citations resolved N unresolved 0`, exit 0 (N is printed, not stored) |
| prove `docs/` still obeys the level scheme: level file names, zone order, unique anchors, no line-number references | `python3 bench/checks/docs_layout.py` → `docs layout: 0 problem(s)` |
| M1's deciding observation as an exit code: clone at the tag, one command, paper must quote every key, starved trees must fail loudly | `python3 bench/checks/m1_acceptance.py` |
| recompute every decisive number from committed rows, no home, no `/tmp`, no model, no network | `python3 reproduce.py` |
| what a projection row is, which fields it keeps, what it cannot show | `bench/projection/README.md` |
| rebuild or re-check the projection against the home (maintainer recipe; needs the home) | `python3 bench/projection/build_projection.py --check` |
| projection fidelity to the home it was cut from | `python3 bench/analysis/wave1/fix/verify_projection.py` → `ok files=472 rows=2810 mismatches=0` |
| declared home for the campaign bytes (2.0 GB, 53 270 files, untracked, verify by hash) | `bench/runs/wave1/` |
| hash manifest over that home | `bench/manifests/wave1.sha256` |
| verify the home (rehash every file, check the 36 analysis copies) | `python3 bench/analysis/wave1/verify_home.py` → `ok 53270 mismatch 0 missing 0 analysis-copies-ok 36 analysis-copies-bad 0`, exit 0 |
| verify with the standard tool instead | `cd bench/runs/wave1 && sha256sum -c ../../manifests/wave1.sha256` → 53 270 OK, 0 FAILED |
| recompute R1 from the home (`−0.320`, `[−3.520, +3.080]`) | `python3 bench/analysis/wave1/recompute_n25.py` |
| recompute R2 from the home | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl' --out /tmp/r2.json --text /tmp/r2.txt` |
| recompute R3 from the home | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| every number above, the command that re-derives it, and the gaps not yet re-derived | `bench/analysis/wave1/NUMBERS.md` |
| analysis scripts, tracked copy (36 files) | `bench/analysis/wave1/{final,n25,r2,r3}/` |
| source-side hash list taken at copy time (untracked, expires with `/tmp`) | `bench/runs/wave1-src-manifest.sha256` |
| copy and verification logs | `bench/runs/wave1-copy.log`, `-copy-full.log`, `-hash.log`, `-verify.log` (ignored) |
| three verdicts, every decisive number | `docs/2_GOAL.md`; `docs/8_DETAIL.md` |
| negative results and retractions | `docs/8_DETAIL.md#negative-results`; the retractions in `docs/2_GOAL.md#retractions` |
| the preprint's own intent and acceptance | `docs/5_PRODUCT.md` |
| recovery line, frozen | `docs/0_ROADMAP.md#the-frozen-recovery-line`, `.scratch/30-harness-recovery/blocked-checkpoint.md` |
| why the preprint does not wait on P1a, re-checkable in two commands | `grep -c 'harness/' docs/paper/numbers.md reproduce.py` → `0` for both; `grep -rn 'harness/' docs/paper/` → one line, `docs/paper/07-limits.md`, the disclosure and not a result |
| the decision itself, the person's words and what it cost | `docs/5_PRODUCT.md#the-paper-goes-first-unless-the-paper-needs-the-broken-tool` |
