# Benchmark corpus

One directory per task (`T-<nn>-<slug>/`). Every task directory contains exactly four
entries — nothing else is ever added to the corpus itself:

```text
T-01-ttl-seconds-ms/
  request.md    # the user's raw request, verbatim; the ONLY input a run is given
  repo/         # the self-contained work tree the run operates on — ships BROKEN
  checks.py     # deterministic checks, Python stdlib only, no deps beyond pytest
  solution.md   # the minimal fix — lives OUTSIDE repo/, never shown to a run
```

## Task repos

- Self-contained: no dependency on helpagent or on sibling tasks; importable with
  `pythonpath = ["."]` via each repo's own `pyproject.toml` (no conftest.py anywhere).
- ≤10 files; Python stdlib + pytest only.
- **Ships broken:** `python -m pytest` inside `repo/` FAILS on the seeded bug and PASSES
  after applying `solution.md`'s minimal fix. Red→green is verified by hand before a task
  enters the corpus, and the repo is restored to its exact broken bytes afterwards
  (SHA-256 checked).
- No solution leakage: repo code and docs state the *requirements*, never the fix
  (no "this should be X" comments; no correct-but-unused idiom planted next to the bug
  where avoidable).

## `request.md`

Written as a real user would write it: symptom first, hunches allowed, no file paths or
symbol names given away. This is the string the run's intake step receives verbatim
(see INFO_FLOW §2 Step 1).

## `checks.py` — deterministic checks (DESIGN §6)

Stdlib-only script per task. Two subcommands:

```bash
python checks.py snapshot              # BEFORE the run: SHA-256 every path in the task's
                                       # UNTOUCHED list -> .untouched.baseline.json
python checks.py verify                # AFTER the run: (a) pytest in repo/ must exit 0,
                                       # (b) every UNTOUCHED path must be byte-identical
python checks.py verify --baseline F   # explicit baseline file (default: .untouched.baseline.json)
```

- Exit codes: `0` all green · `1` check failure · `2` setup/usage error (no baseline,
  snapshot-time missing file).
- **Untouched-files contract:** the paths a correct solution must not modify are listed
  explicitly in `UNTOUCHED` inside each checks.py. The file the minimal fix touches is
  deliberately absent from the list. Missing files count as violations; files *created*
  by a run (e.g. `__pycache__/`, `.pytest_cache/`) do not — the contract hashes the listed
  paths, it does not forbid new files.
- `.untouched.baseline.json` is a runtime artifact written next to checks.py; it travels
  with a copied task dir and is not part of the corpus content.

## Running a task

1. Copy the task dir to the run's workdir (or run in place).
2. `python checks.py snapshot`.
3. Hand `request.md` to the run. The run never sees `solution.md`, `checks.py`, or the
   baseline; it works inside `repo/` only.
4. `python checks.py verify` — exit 0 is the deterministic part of the score.

## Scoring inputs (DESIGN §6)

`checks.py` covers the deterministic rubric components: fix quality (pytest green) and
safety (untouched-files contract = "no unrelated changes"). Cost metrics — model calls,
tokens, wall time (model vs tool/infra separately) — are recorded by the benchmark
runner, not by the task; they are rubric components, not footnotes.

## Adding a task

1. Build `repo/` with exactly one seeded bug and a focused failing test.
2. Verify red→green by hand (apply fix, pytest, revert byte-exactly, SHA-256 check).
3. Write `request.md` symptom-first, `solution.md` outside `repo/`, and the task's
   `checks.py` with its explicit `UNTOUCHED` list.
4. Re-run `snapshot && verify` on the pristine (broken) task: contract must be OK while
   tests fail — that is the shipped state.
