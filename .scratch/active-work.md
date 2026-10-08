# Active work — start here

As of 2026-10-01 (handover while the owner was away).

**Read first:** [`../docs/STATUS.md`](../docs/STATUS.md) — what works, what was measured,
what is known not to work, and the recommended next steps.

**The flow itself:** [`../docs/FLOW.md`](../docs/FLOW.md) — the owner spec for how a task is
processed (one flow, exploration in every step, node structure, execution, verdict). Where the
older `docs/DESIGN.md` §10 describes a different layering, FLOW.md wins.

**Then, if you are changing code:** [`../docs/DESIGN.md`](../docs/DESIGN.md) §10 (the v2 flow)
and §10.10 (implemented vs designed-but-not-built).

## State

**Current measured position (2026-10-06, clean, all 40 tasks, N=1):** development-only
(harness `--verify raw`) fixes **21/40 (52%)**; the full default reaches 20/33 (61%) on the
tasks it completed, all measured against an 8192-token server. **The mature-agent comparison
was corrected on 2026-10-06: the recorded pi arm was throttled by our own configuration**
(`--thinking` was clamped to `off` because the temp model entry declared no reasoning support,
and the server window was 8k). Re-measured with reasoning max and a 32768-token window, pi fixes
**27/40 (68%)** with 2 false successes — so the earlier "development capability is a TIE" and
"the hard tail is a capability boundary" readings are **retracted**; T-31 (four-file parameter
threading) is fixed by the same 4B given room to iterate. What survives: the anchor band
(writing a whole correct implementation from a text spec) is 0/5 both ways, and our claim gates
keep false successes at 0-2 where pi has no gate. Full tables and caveats: `docs/STATUS.md`
sections 1, 1a, 8 and **8b** (section 1's review-tier numbers were measured under the retracted
cache leak; the "asking for tests makes pi worse" finding is an 8k-only measurement and has not
been re-measured at 32k). Working record: `.scratch/26-pi-maxed/issues/26-pi-maxed.md`.

**The largest known loss channel is now our own independent verification.** In the 32k `full`
run, several tasks reached a revision the grader accepts and the harness still refused to claim
it, because the independently authored test **asserts the pre-fix behaviour** (T-10's IV test
demands `pytest.raises(IndexError)` for the crash the request asks to fix) and therefore turns
red when the bug is fixed. The per-test outcomes on the original and final revisions are already
recorded, so this is deterministically separable into `iv_inverted_tests` (final-red,
original-green) and `iv_unmet_tests` (red on both). An owner decision is open on whether the
inverted case may go to the judge; see the ticket.

- The test gate is the authority: `uv run pytest` (includes the repository's own tamper guard
  and the 107-case corpus-integrity suite). It must be green before and after any change.
- A change to the flow is not done until it has been exercised once against the REAL model
  (`bench/v2_leaf.py` / `bench/v2_tree.py` on a single corpus task) — unit tests alone have
  let dead paths ship repeatedly here (the How axis was "complete" three times while never
  executing).
- Every claim (success or failure) must be traceable in `run.json` to evidence; never add a
  path that sets `claimed=True` outside `harness/leaf.py::claim_decision` (a structural test
  enforces this).

## A finding to keep in mind before changing anything

A mature agent CLI (`pi` itself) driving the SAME 4B model scored 4/6 actual on three tasks
(our harness: 3/6 on the same three), and it claims far more because it has no claim gate.
Its loop is real (read/bash/edit/write, shell commands every run). So do not assume the
harness's value is raw pass rate on easy tasks: its value is the blind scoring protocol, the
deterministic gates, the auditable evidence trail, and the structural layers. A controlled
follow-up (much larger budget, or the red-independent-test gate relaxed to a label) would
separate "the gate costs fixes" from "the gate costs only claims". Details:
`.scratch/24-mature-agent-baseline/issues/24-mature-agent-baseline.md`.

## Open items (nothing blocking; ordered)

1. **Re-measure after the claim-gate rounds** and refresh `docs/STATUS.md` numbers.
2. The known false-success rate is now bounded by the documented fundamental limit; the
   remaining quality work is on the MISSED-SUCCESS side (runs that fix the task and cannot
   verify it) — the ledger now says why for each case.
3. Designed but not built: requirement triage, model-side context curation, the knowledge
   service, worktrees/parallel trees, a human-facing piloting surface (see DESIGN §10.10).
4. `bench/golden_bugfix.py` is the legacy v1 pipeline, kept as a reference only; its numbers
   predate the blind protocol and are not citable.
