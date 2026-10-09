# 27 — the campaign (owner mandate 2026-10-06, full delegation)

**What the owner can see at each step is [`docs/ROADMAP.md`](../../../docs/ROADMAP.md)** (the
vertical slices V1–V6 and the acceptance criteria C1–C5). This work record tracks the **internal
implementation phases** below - means, not milestones - plus the ticket's transient contracts,
evidence and handoffs.

Owner: "you are fully delegated; manage and orchestrate; let the workers do the concrete work;
don't stop until the research is finished; I only want the final result."

## Internal implementation track (means, not a roadmap)

| # | phase | state |
| --- | --- | --- |
| P1 | flow v3 core (writes recorded+restored, regression stage, three states, best-of) | P1a/P1b/P1c-1 done; P1c-2 open (sweep still drives the leaf loop) |
| P2 | node structure v3 + exploration + triage | open; the bounded source view was tried and reverted |
| P3 | meaningful verification, per-failure forensics | mostly done; per-task verdicts missing for the 12 shared failures |
| P4 | pi parity (baseline, prompt-improved) + efficiency | open; A2 blocked by GPU contention |
| P5 | drive the residual to zero | open |

## Discipline for this ticket

One writer per work tree; every phase re-measures against the REAL model; numbers are retracted
and re-measured after any flow change; every phase leaves its evidence in this directory.

## Landed in this ticket (each re-measured by the orchestrator)

| commit | what | measured effect |
| --- | --- | --- |
| `827d8dd` | P1a off-plan writes land, are recorded and are restored before grading; P1b the regression stage | grader sees the same bytes; the suite is green |
| `01d9bee` | P1c-1 three states + How terminal semantics + best-of propagation | red own tests no longer reach review |
| `8cb22be` | P3a: self-tests may not assert the symptom; K=1 red attribution; no-op writes recorded | T-05, T-16 flipped |
| `f5d88e9` | P3b: inverted independent verification unblocks; reviews anchor on the repo's own docs | fewer wrong blocks |
| `d10e172` | P3c: per-case discriminating power; `test_wrong` must really change the test; empty delivery is a first-class outcome | true successes up |
| `2f057bd` | P3e: the documented-API check catches class-rooted bindings (a real bypass case) | T-28 honest |
| `d8e136a` | P4a: judge incoherence; a review may not override a contradicting verdict; compile check; false reds do not block | **0 false successes on the probe** |
| `e190a4f` | P5: a claim follows the evidence, one bounded reconciliation | claims rose from 1/6 to 2/6 with 0 lies |
| `1af450d` | P2: prompt de-duplication + bounded source view (later partly reverted) | see the retraction |
| `076302e` | P6: closed the two false successes (two different causes) and restored full injection | 0 lies on the probe |
| `25dafaf` | V2: C2 (bounded index) disabled after the A/B proved it costs 5 tasks; **the P2 token headline retracted** | 13/24 → 18/24 |
| `6b224f5` | P8: a non-discriminating independent check can no longer carry a pass claim | 6/6 actual, 0 lies on the probe |
| `8eedab9` | `STATUS.md` §8e: the campaign's final numbers, the losses, the lies, what stays open | — |

## Findings that moved into the docs (keep the pointer, not the copy)

- **F1 — the regression stage is unobservable on this corpus.** Each task's `repo/tests/` IS the
  grader's suite and the blind protocol withholds it, so the staged view usually has no visible
  test file. Now `STATUS.md` limit 7.
- **F2 — the bounded source view costs real fixes.** 13/24 vs 18/24 on the same 12 tasks x2; the
  P2 token win did not reproduce (16,006 / 16,132 / 16,872). Now `STATUS.md` §3, and the retraction
  is in commit `25dafaf`.
- **P1c was re-cut**: P1c-1 landed; P1c-2 (the sweep driving the unified tree runner) is folded
  into P2 and is still open.

## Handoff (2026-10-09, HEAD `6b224f5`)

Our 40-task measurement: **24/40 actual, 11 claimed, 3 false successes** (T-27, T-30, T-35) against
pi's 27/40. The A2 arm (pi + improved prompt) could not be measured — an unrelated GPU job holds
VRAM and the pi client needs the 32768-token context. One row per open item is in
`docs/ROADMAP.md` → V3/V4 (the open slices); the numbers and their evidence are in
`docs/STATUS.md` §8e and `bench/runs/v2sweep-*`.
