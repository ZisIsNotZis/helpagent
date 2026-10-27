# Open items — FLOW §10 and §11

Decisions and holes from `docs/FLOW.md` that do not belong in the architecture text. One item per
line, with the source line of each item.

## 10. Open decisions for the owner

- **Open decision 1** — RESOLVED: every in-run judge stays the small model; the strong model appears only as the manual out-of-band regression review (`docs/6_FLOW.md` §7.1). (source docs/FLOW.md:315-318)
- **Open decision 2** — §4.4's last line: when no approach passes, confirm the exact output — current spec: deliver the best-evidence revision, claim nothing, report `uncertain` with the reasons. **Implemented and kept** (`best_of_how_states` / `propagate_node_state`, `01d9bee`; the empty-delivery case is a first-class outcome, `d10e172`). (source docs/FLOW.md:319-322)
- **Open decision 3** — The parallelism granularity when it is picked up (`docs/6_FLOW.md` §7): siblings from the start, or gated by budget/clock; parallel writers need confined work trees. (source docs/FLOW.md:323-324)

## 11. Holes in this flow (found while walking it; none is decided)

| # | hole | why it matters | proposal |
| --- | --- | --- | --- |
| **H1** | RESOLVED: a splitting node's four lists are its OWN work (above the children); a purely parental node leaves them empty, which is normal | — | — (source docs/FLOW.md:330) |
| **H2** | RESOLVED: neither check is allowed for trivial work; the `reason` says why, and such a How cannot claim beyond the deterministic checks | — | — (source docs/FLOW.md:331) |
| **H3** | RESOLVED: states are pass / fail / uncertain / parked-for-user. A test that says FAIL ends the How as FAIL (never "uncertain"); UNCERTAIN only when the test or the judge itself reports uncertain; when every How is exhausted the node takes the best of them (uncertain if any is uncertain, else fail) | — | — (source docs/FLOW.md:332) |
| **H4** | RESOLVED: all Hows exhausted → best-of (uncertain beats fail) → that state propagates upward; a judge's `spec` verdict is still the path that asks the parent to re-plan | — | — (source docs/FLOW.md:333) |
| **H5** | RESOLVED: parallel nodes get **separate git worktrees/branches**, merged afterwards | — | — (source docs/FLOW.md:334) |
| **H6** | The regression check's coverage | it can only run the VISIBLE test suite; the grader's own suite is withheld by the blind protocol, so a run can be regression-free by our check and still fail the grader | state it plainly in every report: our regression verdict is partial; the external grader is the final word (source docs/FLOW.md:335) |
| **H6 (measured note)** | *measured 2026-10-08: on this corpus the staged view usually has no visible test at all, so the stage is skipped (`observable=False`) - see `docs/2_GOAL.md`* (source docs/FLOW.md:336) | | |
| **H7** | When is the judge consulted? | every red (one extra call per attempt) versus after K consecutive reds (today: K=2, plus a volunteer trigger) | every red: T-01/T-05 both burned 4-6 attempts churning against a wrong test, which one judge call would have stopped (source docs/FLOW.md:337) |
| **H7 (decided note)** | *decided 2026-10-08: K=1 — every red goes to the judge (commit `8cb22be`, `ATTRIBUTION_RED_K`), at most once per attempt* (source docs/FLOW.md:338) | | |
| **H8** | The judge is unavailable or malformed | the attribution is missing, and "keep implementing" is a guess | keep implementing for at most one attempt, then treat the test as UNCERTAIN and repair it (a wrong test is the likelier defect in that state) (source docs/FLOW.md:339) |
| **H9** | The work unit's stop conditions are not enumerated | "iterate (bounded)" hides: what is the cap, what happens at the cap, does the cap reset when the judge changes the diagnosis | one cap per How (attempts), renewed only by a node update; at the cap the How is confirmed failed and the next How starts (source docs/FLOW.md:340) |
| **H10** | Exploration bookkeeping | "every step may explore" says nothing about what the exploration found, who pays for it, or whether the later steps can see it | an exploration result is a first-class artifact: reads are recorded in the trajectory, their excerpts ride into the steps of the SAME node, and the reads are charged to that node's budget (source docs/FLOW.md:341) |
| **H11** | The top level with several issues | the flow says "one or more issues" but not whether they are sequential, parallel, or what the run claims when one passes and another does not | execute issues in order (or in parallel only when their `files` do not overlap — H5); the run's report is per issue and the run claims nothing that failed (source docs/FLOW.md:342) |
