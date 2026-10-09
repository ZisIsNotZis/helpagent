# Active work — start here

As of 2026-10-09 (campaign handover).

**What the owner can see at each step:** [`../docs/ROADMAP.md`](../docs/ROADMAP.md) — the
vertical slices V1–V6, each with the command you run to see it, plus the acceptance criteria
C1–C5. Read this first; it is the SSOT for the roadmap. (The internal implementation phases are
tracked in `.scratch/27-campaign/`, not there.)

**The numbers:** [`../docs/STATUS.md`](../docs/STATUS.md) §8e — the campaign's 40-task
measurement, the retractions (the P2 token headline; the throttled pi baseline) and the known
limits. `§1` and `§8b` are the earlier measurements and say so.

**The flow itself:** [`../docs/FLOW.md`](../docs/FLOW.md) — the owner spec for how a task is
processed. Where `docs/DESIGN.md` §10 describes a different layering, FLOW.md wins.

**If you are changing code:** [`../docs/DESIGN.md`](../docs/DESIGN.md) §10 (the flow) and §10.10
(implemented vs designed-but-not-built).

## State (2026-10-09, revision `6b224f5`)

Our harness fixes **24/40** of the corpus (claims 11, three false successes: T-27, T-30, T-35).
pi with every knob maxed fixes **27/40** (2 false successes). Both pass 23; we win 1, pi wins 4
(T-07, T-14, T-28, T-30), 12 fail for both. Tokens: ours 18,401/task vs pi 9,045; wall-clock is
not comparable yet (ours was measured under four-way concurrency). **None of the five acceptance
criteria is met yet** — the straight reading and the per-item evidence are in ROADMAP.md and
STATUS.md §8e.

The A2 arm (pi + improved prompt) is **unmeasured**: an unrelated GPU job holds VRAM and the pi
client needs the 32768-token window, so every pi run dies in ~15 s with `Connection error` while
our own harness runs fine against the same server.

## Standing rules for whoever picks this up

- **The test gate is the authority:** `uv run pytest -q -p no:warnings` (includes the repository's
  own tamper guard and the corpus-integrity suite). Never pipe it; check the exit code.
- **A flow change is not done until it has been exercised once against the REAL model**
  (`bench/v2_leaf.py` / `bench/v2_sweep.py` on corpus tasks). Unit tests alone have let dead paths
  ship repeatedly here.
- **One claim gate:** never add a path that sets `claimed=True` outside
  `harness/leaf.py::claim_decision`; a structural test enforces this.
- **One writer per work tree.** Never edit code while a measurement lane is running.
- **Retract and re-measure.** A headline that a later measurement contradicts gets retracted in
  the same commit that contradicts it (see `25dafaf`).
- **Check the server before any measurement:** `curl -fsS --max-time 3
  http://127.0.0.1:8834/health`.

## Where the evidence is

- `bench/runs/v2sweep-*` — every sweep, with `trajectory.jsonl` per task (rendered prompts, raw
  answers, writes, test runs, verdicts, deliveries). The campaign's final runs are the directories
  dated 2026-10-09.
- `bench/runs/evidence/` — the curated, tamper-guarded baseline (`pi-maxed-20261006/`).
- `.scratch/27-campaign/issues/27-campaign.md` — this ticket's commits and findings.
- Work records for the earlier tickets: `.scratch/17-*` … `.scratch/26-*`.
