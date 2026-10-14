# Closeout documentation — independent review, round 2 (fresh context, read-only)

**Scope.** Re-review of the repaired closeout docs, focused on the findings in
`closeout-independent-review.md`: `README.md`, `docs/LEARNINGS.md`, `docs/STATUS.md`,
`docs/ROADMAP.md`, `CONTRIBUTING.md`.

**Authority.** Read-only. No reviewed file was modified. This review file is the only
artefact created. No model calls were made.

**Revision / tree.** HEAD `45ebb32`; `git diff --cached` empty (nothing staged). The
reviewed docs are uncommitted working-tree changes; `docs/LEARNINGS.md` and `CONTRIBUTING.md`
are untracked, `README.md`/`docs/STATUS.md`/`docs/ROADMAP.md` are modified.

**Method.** Re-read the current text of all five docs; checked each documented driver
command against the actual `argparse` in `bench/v2_leaf.py`, `bench/v2_sweep.py`,
`bench/v2_tree.py`, `bench/v2_measure.py`, `bench/pi_baseline.py`; resolved every relative
Markdown link with a real filesystem check (Python, no anchors); traced the headline numbers
to the measurement records and the forensics.

---

## Per-item verdict

### P1-1 — server port on runnable commands → **PASS**

Every documented invocation now passes `--server http://127.0.0.1:8834`, matching the server
block's `--port 8834`:

- `README.md:157` `bench/v2_leaf.py --task … --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25`
- `README.md:163` `bench/v2_sweep.py … --calls 24 --server http://127.0.0.1:8834`
- `README.md:164` `bench/v2_tree.py --task … --server http://127.0.0.1:8834 --calls 60 --deadline-hours 0.5`
- `docs/ROADMAP.md:17,18,48,52-53` (V1/V2 slices) also carry `--server http://127.0.0.1:8834`
- `docs/STATUS.md:251,260,264`, `CONTRIBUTING.md:29,33` carry it too.

Each flag used exists in the scripts' `argparse`:
`v2_leaf.py:938-952` (`--task --server --calls --deadline-hours --out --verify …`),
`v2_sweep.py:35-51` (`--tasks --n --server --calls --deadline-hours --verify …`),
`v2_tree.py:522-536` (`--task --server --calls --deadline-hours --out --how-explore …`),
`v2_measure.py:311-323` (`--tasks --n --server --ablate --out`),
`pi_baseline.py:419-442` (`--tasks --n --base-url --thinking --reasoning --out`).
No documented command omits `--server` or names a non-existent flag. (The script defaults
remain `http://127.0.0.1:8833`, but every documented command overrides it explicitly, so the
quickstart is runnable line-for-line.)

### P1-2 — parity wording → **PASS**

No doc claims parity established; the consistent form is *indistinguishable point estimate +
INCONCLUSIVE pre-registered verdict*:

- `README.md:56` table: `INCONCLUSIVE` (parity not established); `README.md:68`:
  `Capability: no detected difference — parity not established (INCONCLUSIVE at M=3)`.
- `docs/LEARNINGS.md:13` short answer: `no detected capability difference — parity not
  established (INCONCLUSIVE at M=3)`; `:45-48`: "statistically indistinguishable … but it is
  not better on capability: the pre-registered test returned INCONCLUSIVE, so neither parity
  within margin nor inferiority is established."
- `docs/ROADMAP.md:34` C1: `parity not established (INCONCLUSIVE at M=3, CI [−3.520, +3.080])`;
  `:37` C4: `statistically indistinguishable, not superior (parity not established;
  INCONCLUSIVE at M=3)`.
- `docs/STATUS.md:31` R1 `INCONCLUSIVE`; `:54-57` spells out `Lo95 >= −M` false, `Hi95 < −M`
  false, "establishes neither parity within margin nor inferiority."

The prior conflict wording is gone: `grep -i "no worse|at parity"` returns nothing; the old
`LEARNINGS.md:44` "It is no worse than a free-form agent loop" is replaced.

### P1-3 — 2026-10-09 gap attribution → **PASS**

The corrected breakdown (T-07 discard, T-30 claim hole, T-14 content; T-17/T-28 later) is
present in the two docs that carried the misdated claim:

- `README.md:76-79`: "the 2026-10-09 starting point was `24/40` vs `27/40`, and the documented
  causes were a discarded grader-passing revision in **T-07**, the closed T-30 claim hole, and
  content in **T-14** (T-17 and T-28, both discarded-revision cases, came on the next revision)."
- `docs/LEARNINGS.md:161-164`: same split — "the delivery discard (T-07 at that revision; T-17
  and T-28 on the next revision) plus the T-30 claim hole, with T-14 content-side".

This matches `parity-forensics.md` §2/§5: at `6b224f5` pi wins only T-07, T-14, T-28, T-30;
D1's verified discards are T-07 (`6b224f5`), T-17 and T-28 (latest revision). One leftover
note, non-blocking: `docs/STATUS.md:67-72` still places "both parity losses" (T-17/T-28, the
latest-revision gap) inside the "Where the starting position came from" paragraph. That text is
**unchanged since round 1**, where the reviewer explicitly accepted it as "the accurate
revision-scoped version"; it states no wrong number, but read in isolation the paragraph header
could mislead about which revision T-17/T-28 belong to.

### P2 items

- **Token figure ~18.9k → PASS.** `README.md:62`, `docs/LEARNINGS.md:245`, `docs/STATUS.md:149`,
  `docs/ROADMAP.md:20,38` all state `~18.9k` tokens/task (4-lane, 40 tasks). Traces to
  `fix-wave-1-measurement-n25.md:168,202` = `18916` (4-lane, all 40 tasks; single-lane subset
  `18287`). `pi ~9k` is retained and still declared partly unmeasured (`STATUS.md:150-152`,
  `LEARNINGS.md:245`). No `17.5k`/`17,538` remains in any of the five docs.
- **Unsupported "works"/certainty phrasing → PASS.** The tournament is now "fires, but costs
  `2.2`–`2.4x` the calls and fixes far fewer tasks" in `README.md:89`, `docs/STATUS.md:200`,
  `docs/LEARNINGS.md:207`. `README.md:73` reads "Not proven stronger; not proven worse"
  (the old "not proven impossible" is gone). No unqualified superiority claim survives: every
  `superior`/`beats` hit is a slice name, an open item, or explicitly negated/qualified.
- **Links resolve → PASS.** 26 relative Markdown links across the five docs were resolved
  against the filesystem in a Python pass; **0 dead**, no in-page anchors. All targets exist,
  including `docs/DESIGN.md`, `docs/FLOW.md`, `bench/corpus/README.md`,
  `bench/runs/evidence/`, `LICENSE.md`, `../.scratch/28-three-requirements/issues/…`. The one
  external link (`https://docs.astral.sh/uv/`) is not a repository artefact.

### Cross-doc link sweep of the five docs → **PASS**

Same run: every relative link in `README.md`, `docs/LEARNINGS.md`, `docs/STATUS.md`,
`docs/ROADMAP.md`, `CONTRIBUTING.md` resolves.

---

## Remaining P0 / P1

- **P0: none.**
- **P1: none.**

## Residual observations (non-blocking, not truth defects)

1. `docs/STATUS.md:61` "full width `6.53` to `6.60`" gives the endpoint range, while
   `docs/LEARNINGS.md:150` and the source (`final-measurement-independent-verification.md:80,82`)
   give the full range `6.44–6.60`. Both are traceable and consistent with round 1's accepted
   STATUS endpoint form; no number is wrong.
2. `docs/STATUS.md:67-72` "starting position" paragraph (see P1-3 note) — wording placement only,
   unchanged from the version round 1 accepted.

## Verdict

**All clear.** Every prior P1 is fixed — runnable commands pass the matching `--server 8834`,
parity wording is consistent and claims no parity, the 2026-10-09 gap is attributed to
T-07/T-30/T-14 with T-17/T-28 on the next revision, the token headline is `~18.9k`, and no
dead links remain; no P0 or P1 is outstanding. Merge verdict: **OK.**
