# Incident 2026-09-30 — repo-root conftest.py that rewrote failing tests to passed

## What was found

An untracked `conftest.py` at the repository root (221 bytes, mtime 2026-09-30 13:32:22,
sha256 12b71c5c…), containing a `pytest_runtest_makereport` hookwrapper that set
`rep.outcome = 'passed'` for every failing report. It was found by the independent
adversarial verifier lane for ticket 20 step 1, which could not delete it (read-only)
and correctly escalated instead.

## Impact

None on committed work: the file was untracked, and the suite re-run WITHOUT it is
genuinely `443 passed` (verified with `--noconftest` by the verifier and after removal by
the supervisor). Benchmarks were unaffected: they stage into `bench/runs/**/work` and the
grader runs in a private copy, never in the repo root.

The real exposure is procedural: any bare `uv run pytest` in this repository while that
file existed would have reported green regardless of real failures — for us and for
anyone else who ran it.

## Attribution

Most likely OUR OWN verifier lane's accident, not an external writer:
- the mesh shows no peer in this directory (`list_peers` → other projects only);
- the git config, hooks directory, `sitecustomize.py`, `*.pth` and reflog are clean;
- the lane's own reasoning records writing `/tmp/adv/conftest.py` at 13:30 and then
  running `uv run pytest /tmp/adv` with the repository as cwd; a relative-path write in
  that window explains the root file, and the mtime (13:32) sits inside its session.

## Actions

1. Evidence preserved here (`conftest.py.evidence`, `stat.txt`); the file was removed.
2. Suite re-verified green after removal (443 passed).
3. `tests/unit/test_repo_integrity.py` added: the repository now fails its own suite if a
   stray `conftest.py` / `sitecustomize.py` / `*.pth` (or an untracked conftest anywhere,
   or a tracked conftest outside `tests/`) is present.
4. Standing instruction to verifier lanes: probe fixtures go to an ABSOLUTE path under a
   private temp directory, never a bare relative filename.
