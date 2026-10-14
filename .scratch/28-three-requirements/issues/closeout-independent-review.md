# Closeout documentation — independent review (fresh context, read-only)

**Scope.** Independent review of the uncommitted closeout changes before commit/push:
`README.md`, `docs/LEARNINGS.md`, `docs/STATUS.md`, `docs/ROADMAP.md`, `CONTRIBUTING.md`,
`.gitignore` and `.scratch/28-three-requirements/issues/28-three-requirements.md`.

**Authority.** Read-only. No reviewed file was modified. This review file is the only artefact
created. No model calls were made.

**Method.** Every decisive number was re-read from the authoritative measurement records and,
where possible, recomputed from the raw rows under `/tmp/wave1/final/` with an independently
written read (not from the docs' prose): `analysis-n25-final.json`, `r2/analysis.json`
plus `r2/runs/**/results.jsonl`, `r3/analysis-r3.txt` plus `r3/*/run.json`. Link resolution
is a real filesystem check of every relative Markdown link. `CONTRIBUTING.md` commands were
checked against the actual `argparse` flags, scripts and fixtures. One targeted test ran
(`tests/unit/test_v2_leaf.py -k claim_gate`, 4 passed).

**Revision / tree.** HEAD `45ebb32`; `git diff --cached` empty (nothing staged).

---

## Verdict summary

- **Decisive numbers: all traced, no mismatch.** R1, R2, R3 totals, deltas, CIs, p-values,
  false-success counts and the CI-width claim each match the raw evidence exactly.
- **Links: none dead.** All 30 relative links in the five Markdown docs (plus the ticket) resolve.
- **CONTRIBUTING commands: correct.** Every flag, path and sub-command exists.
- **Merge verdict: OK-with-notes.** No P0. Four P1 items (one broken runnable command, one
  parity wording conflict, one misdated causal claim, one commit-scope risk) are cheap text
  fixes that should land in the same commit; P2 items are traceability/polish.

---

## Correct — verified against raw evidence

### R1 head-to-head (N=25)
`docs/STATUS.md` §3, `README.md` table row 1, ticket Q2. Raw:
`/tmp/wave1/final/n25/analysis-n25-final.json` (1000 rows/arm verified by count).

| claim | raw | source |
| --- | --- | --- |
| ours 616/1000, mean 24.640, sd 1.221 | 616, 24.64, 1.2207 | analysis-n25-final.json |
| pi 624/1000, mean 24.960, sd 2.150 | 624, 24.96, 2.1502 | analysis-n25-final.json |
| Δ −0.320 tasks = −0.8 pp | −0.32 | analysis-n25-final.json |
| 95% CI [−3.520, +3.080] | [−3.52, 3.08] | analysis-n25-final.json |
| M=3 → INCONCLUSIVE, misses by 0.520 | verdict INCONCLUSIVE, −3.52 ≥ −3 false | analysis + rule |
| false 22/1000 = 2.20% vs 61/1000 = 6.10%, Δ_fs −1.56 [−3.16, −0.20] | 22 / 61 / −1.56 [−3.16, −0.20] | analysis-n25-final.json |
| CI width structural, flat N=17→25 | widths 6.53 … 6.60 (range 6.44 at N=23); ~8.7% seed noise, ~6.3-task floor | `final-measurement-independent-verification.md` §1.3–1.4 |

### R2 five-arm ablation (600 runs)
Raw `r2/analysis.json` + 600 rows counted.

| claim | raw |
| --- | --- |
| A0…A4 actual 70/66/65/71/77 of 120 | 70, 66, 65, 71, 77 |
| false successes 0/0/0/10/1 | 0, 0, 0, 10, 1 |
| own test −1.33 [−5.67,+3.00] p=0.549 | matches (Δ −1.3333) |
| IV correctness −0.33 p=1.000 and +2.00 p=0.388 | matches |
| IV −8.67 claims p=0.0009 | Δclaimed −8.6667, p=8.55e-4 |
| IV −3.00 false p=0.031 | matches |
| review +4.00 [ +1.33,+7.00] p=0.012 | Δ 4.0, p=0.0117 |
| review-alone +3.33 false p=0.031 | matches |
| full-arm IV withheld 92/110, 57 grader-passed | signals: blocked 92, false-block 57 |

### R3 decomposition (210 runs)
Raw `r3/analysis-r3.txt`, 70/arm counted.

| claim | raw |
| --- | --- |
| leaf 47/70, greedy 14/70, tournament 15/70 | matches |
| false 0 / 4 / 3 | matches |
| decomposable −0.444 [−0.733,−0.178] p=0.000; forced-leaf −0.520 [−0.920,−0.120] p=0.001 | matches |
| tournament −0.422 [−0.689,−0.178]; forced-leaf −0.520 [−0.800,−0.240] | matches |
| mechanism fired 3/70 on 3/9 tasks (B1), 9/70 on 4/9 (B2) | matches census |
| "p<0.001" | verified true: exact McNemar p = 2·(1+15)/2^15 = 0.000977 < 0.001 (b=1, c=14); p for 0/20 = 1.9e-6 |

### Other verified claims
- **Conclusion triad follows from the data**, except the parity wording (P1-2): reliability
  advantage is real (Δ_false CI excludes 0), labelled "not a moat" as a reason, not a measurement;
  cost is worse (≈2× tokens).
- **`pi` token gap declared**: `pi_baseline.py` carries no token counters; `~9k` traces to the
  recorded reference `parity-forensics.md:541` (pi 9,045); STATUS §6/§10 disclose it as partly
  unmeasured. Honest.
- **Scope stated** in all three fact docs (model / 40-task corpus / baseline) and in the open list.
- **Open items complete** (`STATUS.md` §10.10, ticket closeout): no superiority proof, no
  impossibility proof, no product CLI, improved-prompt `pi` arm unmeasured, `pi` token cost
  partly unmeasured, clean single-lane wall-clock outstanding.
- **Secondary negative-result numbers trace**: knowledge pack 4/15 vs 3/15, importers 10/15 vs
  10/15, forced order 14/15 vs 7/15, boundary 1/5 vs 1/5 (ticket 20 §table; tickets 11/12/14);
  bounded index 13/24 vs 18/24 (ticket 27 §F2, commit `25dafaf`); pi self-tests 16/40 vs 21/40
  (ticket 25); "9 of 10 last-band runs length-truncated at 8k" (tickets 25/26); `−31.3%` token
  headline retracted (commit `25dafaf`).
- **Claim-gate code claim**: `harness/leaf.py:2025` defines `claim_decision`; the structural test
  passes (4 passed).

---

## Findings

### P0 — none.

### P1-1 — Runnable quickstart points at the wrong server port (introduced by this rewrite)
- **Where.** `README.md:151` (`bench/v2_leaf.py ... --calls 24 --deadline-hours 0.25`),
  `README.md:157` (`bench/v2_sweep.py ...`), `README.md:158` (`bench/v2_tree.py ...`),
  `docs/ROADMAP.md:48` (V1 command) — all omit `--server`.
- **Evidence.** The README's own server block (`README.md:141-144`) starts the model on
  `--port 8834` and checks `http://127.0.0.1:8834/health`, but the driver defaults are port
  **8833**: `bench/v2_leaf.py:186` `DEFAULT_SERVER = "http://127.0.0.1:8833"`, re-used by
  `v2_sweep`/`v2_measure`, and `bench/v2_tree.py:94`; there is no env override. Following the
  README line-for-line therefore connects to a port with no server. The pre-change README
  (`git show 45ebb32:README.md:74`) documented the dev server on 8833, so the command and the
  server description were consistent before this rewrite changed only the server block.
  `CONTRIBUTING.md:29` and `:33-34` and `STATUS.md` §11 are correct because they pass
  `--server http://127.0.0.1:8834`.
- **Smallest fix.** Add `--server http://127.0.0.1:8834` to the three README examples and to the
  V1 command in `docs/ROADMAP.md` (or document the dev server on 8833 for those examples).

### P1-2 — "Capability: parity" conflicts with the pre-registered verdict "INCONCLUSIVE (parity not established)"
- **Where.** `README.md:67` ("**Capability: parity.** … statistically indistinguishable"); the
  same headline in `docs/LEARNINGS.md:13` (short answer), and
  `docs/ROADMAP.md:37` ("coding is at parity, not superiority"); `docs/LEARNINGS.md:44`
  ("It is no worse than a free-form agent loop").
- **Evidence.** The pre-registered rule was not met: `docs/STATUS.md:31` and the raw analyser
  give Δ=−0.320, CI [−3.520, +3.080], and `Lo95 ≥ −M` is false by 0.520, so the verdict is
  INCONCLUSIVE — "neither parity within margin nor inferiority is established"
  (`fix-wave-1-measurement-n25.md` §1, §5.2). "Coding is at parity" and "no worse" assert the
  non-inferiority the test declined to establish. Within the same README paragraph the doc's own
  table row says "**INCONCLUSIVE** (parity not established)", so the headline and the table
  conflict (SSOT: no conflicting statements).
- **Smallest fix.** State the measured fact, not the criterion label: e.g. "**Capability: no
  detected difference — parity not established (INCONCLUSIVE at `M=3`).** The harness and the
  mature CLI are statistically indistinguishable on this model, corpus and baseline; superiority
  is not shown, and neither is non-inferiority within the 3-task margin." Change LEARNINGS:13 and
  ROADMAP:37 to the same wording.

### P1-3 — The "three tasks lost to discarded revisions" claim is not supported as dated
- **Where.** `README.md:76-77` ("at the 2026-10-09 starting point the harness lost three tasks to
  `pi` **because it discarded or overwrote revisions that already passed the grader**").
- **Evidence.** `parity-forensics.md` §2: the `6b224f5` (2026-10-09) pi-only wins are
  **T-07, T-14, T-28, T-30** — a 3-task net gap because T-33 is our win. §5 D1 attributes a
  discarded/overwritten grader-passing revision to **T-07 (`6b224f5`), T-17 (latest `d24410a`)
  and T-28 (latest, run `v2sweep-20261011T070710Z`)**. At the 2026-10-09 point, therefore, the
  documented discard loss is **T-07 only**: T-17 was not a 2026-10-09 loss, T-28's discard is
  proven on the later revision, and T-30's loss was a false-success claim closed by P8b (§2.5),
  with T-14 content-side. So neither reading of "three" fits the stated cause at that date — as
  three discard-caused tasks, or as the 3-task net gap (which is 1 part discard, 1 part claim
  hole, 1 part content). `docs/STATUS.md:68` ("both parity losses", the live T-17 + T-28 gap) is
  the accurate revision-scoped version.
- **Smallest fix.** Separate the gap from its causes, e.g. "the 2026-10-09 position was 24/40 vs
  27/40; the documented causes were a discarded grader-passing revision in **T-07**, the closed
  T-30 claim hole, and content in T-14 (T-17 and T-28, both discarded-revision cases, came on
  the next revision)".

### P1-4 — Commit-scope risk: four cited evidence files are untracked
- **Where.** `docs/STATUS.md:269-271` and ticket Q2/Q3/Q4 name
  `fix-wave-1-measurement-n25.md`, `requirement-2-ablation.md`, `requirement-3-result.md`,
  `final-measurement-independent-verification.md`; the ticket's "closeout deliverables" list
  (`28-three-requirements.md:145-152`) names only the six docs and this ticket.
- **Evidence.** `git status --porcelain` shows those measurement records (and
  `fix-wave-1-measurement.md`, `-n9`, `fix-wave-1-measurement-final.md`,
  `requirement-3-design.md`, `fix-wave-1-independent-review.md`) as untracked. If the
  integration commit stages only the deliverables list, the SSOT's pointers to its own evidence
  dangle in a fresh clone.
- **Smallest fix.** Stage the cited measurement records in the same commit (all of
  `.scratch/28-three-requirements/issues/*.md` referenced by the docs), or drop the pointers.

### P2-1 — Token cost headline is an earlier subset number, not the final R1 measurement
- **Where.** `README.md:62`, `docs/STATUS.md:148`, `docs/ROADMAP.md:20` and `:38`,
  `docs/LEARNINGS.md:240` — "ours about `17.5k`/task".
- **Evidence.** The decisive R1 record `fix-wave-1-measurement-n25.md` §3 measures ours
  **18,916 tokens/task (4-lane, all 40 tasks)** and **18,287** on the single-lane 8-task subset;
  `analysis-n25-final.json` agrees (18,916.4). `17,538` is the **N=5/N=9** 8-task single-lane
  subset (`fix-wave-1-measurement.md:156`, `-n9.md:177`), i.e. an earlier, smaller subset. The
  ratio changes from 1.94× to 2.09× — still "about twice", so the conclusion survives, but the
  quoted number is not the final one.
- **Smallest fix.** Quote `~18.9k` (4-lane, 40 tasks) or `~18.3k` (single-lane subset), noting
  the subset; keep `pi ~9k` as the declared reference.

### P2-2 — "The 3-task gap … was caused by this" over-attributes to the discard defect
- **Where.** `docs/LEARNINGS.md:159-161`.
- **Evidence.** Of the four 2026-10-09 losses, **T-07** is a documented discard case
  (`parity-forensics.md` §5 D1), **T-30** is a false-success claim (P8b, §2.5), **T-14** is
  content-side, and **T-28**'s discard evidence is on the later revision; the net gap is 3
  because T-33 is a win. So "caused by this [discard]" holds for one of the three net
  2026-10-09 tasks; the other harness share is the T-30 claim hole.
- **Smallest fix.** Say the gap was harness-side (the delivery discard plus the T-30 claim
  hole, "not model capability"), and keep the T-07/T-17/T-28 discard examples.

### P2-3 — "The full stack does carry information overall" omits its non-significance
- **Where.** `docs/STATUS.md:114`.
- **Evidence.** The full-vs-raw contrast is A4−A0 = **+2.33 tasks [−0.33, +5.33], p=0.344**
  (`requirement-2-ablation.md` §2, raw `r2/analysis.json`); it is not significant. The only
  significant correctness gain is A4−A2 = +4.00, p=0.012.
- **Smallest fix.** Add the number and qualifier: "the full stack is net-positive in point
  estimate (+2.33 [−0.33, +5.33], p=0.34, not significant); the only significant correctness
  gain is review on top of own test + independent test".

### P2-4 — The tournament is labelled "works" although R3 measures it as worse
- **Where.** `README.md:89` ("A competitive tournament of approaches: works, but several times
  the cost for fewer fixes"), `docs/STATUS.md:201`, `docs/LEARNINGS.md:206`.
- **Evidence.** R3's B2 arm *is* the tournament (`--how-explore 3`):
  `15/70 (21.4%, 3 false)` vs leaf `47/70 (67.1%, 0 false)`, decomposable CI
  [−0.689, −0.178] — a significant loss (`requirement-3-result.md` §3–§4).
- **Smallest fix.** Replace "works, but" with "fires, but costs 2.2–2.4× the calls and fixes far
  fewer tasks".

### P2-5 — CI-width range reads as endpoints
- **Where.** `docs/LEARNINGS.md:150` "flat (`6.44` to `6.60` tasks from N=17 to N=25)".
- **Evidence.** The endpoint widths are **6.53 (N=17)** and **6.60 (N=25)**; 6.44 is the N=23
  width (`final-measurement-independent-verification.md` §1.3). `docs/STATUS.md:61` uses the
  endpoint form correctly.
- **Smallest fix.** "flat (range 6.44–6.60; 6.53 at N=17, 6.60 at N=25)" or "6.53 to 6.60".

### P2-6 — "not proven impossible" is the wrong contrast
- **Where.** `README.md:68-69` ("Not proven stronger; not proven impossible.").
- **Evidence.** The claim being negated is inferiority; "impossibility" is a different open item
  (`STATUS.md` §10.10: "no proof of superiority and no proof of impossibility").
- **Smallest fix.** "Not proven stronger; not proven worse."

### P2-7 — `13/24 vs 19/24` is traceable only to a commit message
- **Where.** `docs/LEARNINGS.md:201`, `docs/STATUS.md:202`.
- **Evidence.** The work record records only `13/24 vs 18/24`
  (`27-campaign.md:40,49`). The 19/24 side exists only in the body of commit **`25dafaf`**
  ("V0 (pre-P2, e190a4f) … actual 19/24"). The number is real but not resolvable from the
  current docs' cited evidence; the previous STATUS carried "(commit `25dafaf`)".
- **Smallest fix.** Re-add the commit/record citation next to the number.

### P2-8 — Stale/incomplete work-record files the closeout would commit
- `fix-wave-1-measurement-final.md:3` still reads "**Status: RUN IN PROGRESS**" and stops at
  N=17; it is superseded by `fix-wave-1-measurement-n25.md` but is cited as Q2 evidence
  (`28-three-requirements.md:105`). Fix: mark the header "superseded by
  fix-wave-1-measurement-n25.md", or drop it from the evidence line.
- `fix-wave-1-wip.patch` (54 KB, tracked since `45ebb32`) no longer applies
  (`git apply --check --reverse` fails at `tests/unit/test_v2_leaf.py:7507`); it is redundant
  with commit `45ebb32`. Pre-existing, not introduced by the closeout — delete or annotate.
- No other junk found: root has only the six expected files, no stray artefacts, and the raw
  `bench/runs/*` output is ignored while `bench/runs/evidence/` is kept (`.gitignore:5-9`).

### P2-9 — Dated narrative retained in a fact doc
- `docs/STATUS.md:67-70` ("Where the starting position came from … The 2026-10-09 campaign
  measurement …") is history, which the ticket's closeout rule says lives in the ticket
  (`28-three-requirements.md:139-143`, "the home for the dated narrative that was removed from
  `docs/STATUS.md`"). It is defensible as current-fact context for the fix wave, but it
  duplicates ticket Q1. The retraction at `STATUS.md:157` is allowed (a retraction is a current
  fact per policy).

---

## Link check (real filesystem resolution, all relative targets)

All **30** relative links in `README.md`, `docs/LEARNINGS.md`, `docs/STATUS.md`,
`docs/ROADMAP.md`, `CONTRIBUTING.md` and the ticket resolve (including
`../.scratch/28-three-requirements/issues/28-three-requirements.md`, `DESIGN.md`, `FLOW.md`,
`bench/corpus/README.md`, `bench/runs/evidence/`, `.scratch/27-campaign/...`). No in-page
anchors are used. **No dead links.** One external link (`https://docs.astral.sh/uv/`) was not
fetched (network), not part of the repository.

## CONTRIBUTING command check

- `uv run pytest -q -p no:warnings` — valid; corpus-integrity suite
  (`tests/unit/test_corpus_integrity.py`) and tamper guard exist.
- `bench/v2_leaf.py --task --server --calls --deadline-hours` — all flags exist
  (`v2_leaf.py:938-952`); default `--verify full`.
- `bench/v2_sweep.py --tasks --n --calls --verify --server` — exist (`v2_sweep.py:35-51`).
- Corpus-task contract (four entries; `request.md`, `repo/`, `checks.py`, `solution.md`) —
  verified on `T-02-off-by-one`; `checks.py snapshot|verify` sub-commands exist
  (`checks.py:119`, `bench/corpus/README.md:38-42`).
- `harness/leaf.py::claim_decision` — exists (`leaf.py:2025`).

## .gitignore / caches

Covered: `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`,
`.cache/`, `.pi/`, `.pi-glla/`, `.untouched.baseline.json`, `bench/runs/*` with
`!bench/runs/evidence/`, `*.log`, plus the new build/coverage/editor block. `git status
--ignored` shows all cache dirs ignored. No `.gitignore` gap found.

## Merge verdict

**OK-with-notes.** No P0: every decisive number in `README.md`/`STATUS.md`/`ROADMAP.md` traces
to the raw rows, no link is dead, and the CONTRIBUTING commands are correct. Recommend fixing
P1-1 (broken quickstart port), P1-2 (parity wording vs INCONCLUSIVE), P1-3 (2026-10-09 causal
claim) and P1-4 (stage the cited evidence) in the same commit; P2 items are optional polish,
except P2-1/P2-7 which are cheap traceability edits.
