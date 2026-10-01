# Active work — start here

As of 2026-10-01 (handover while the owner was away).

**Read first:** [`../docs/STATUS.md`](../docs/STATUS.md) — what works, what was measured,
what is known not to work, and the recommended next steps.

**Then, if you are changing code:** [`../docs/DESIGN.md`](../docs/DESIGN.md) §10 (the v2 flow)
and §10.10 (implemented vs designed-but-not-built).

## State

- The test gate is the authority: `uv run pytest` (includes the repository's own tamper guard
  and the 107-case corpus-integrity suite). It must be green before and after any change.
- A change to the flow is not done until it has been exercised once against the REAL model
  (`bench/v2_leaf.py` / `bench/v2_tree.py` on a single corpus task) — unit tests alone have
  let dead paths ship repeatedly here (the How axis was "complete" three times while never
  executing).
- Every claim (success or failure) must be traceable in `run.json` to evidence; never add a
  path that sets `claimed=True` outside `harness/leaf.py::claim_decision` (a structural test
  enforces this).

## Open items (nothing blocking; ordered)

1. **Re-measure after the claim-gate rounds** and refresh `docs/STATUS.md` numbers.
2. The known false-success rate is now bounded by the documented fundamental limit; the
   remaining quality work is on the MISSED-SUCCESS side (runs that fix the task and cannot
   verify it) — the ledger now says why for each case.
3. Designed but not built: requirement triage, model-side context curation, the knowledge
   service, worktrees/parallel trees, a human-facing piloting surface (see DESIGN §10.10).
4. `bench/golden_bugfix.py` is the legacy v1 pipeline, kept as a reference only; its numbers
   predate the blind protocol and are not citable.
