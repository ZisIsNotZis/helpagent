kind:    report
from:    orient-helpagent (package launched by root)
to:      root
spend:   idle-compute
id:      none — first contract, answered in the run final message

First orientation report, filed here by root. Body is the run report verbatim.

## Report — orientation of `helpagent`

### (a) What the project is

`helpagent` is a **closed research campaign, not a product**. It is a Python harness (~72 modules under `harness/`, `bench/`, `tests/`) that wraps one small local model (Spark‑X2.5‑4B Q4_K_M on llama.cpp) in an ordinary software-engineering flow — plan → implement → own test → independent test → review → one claim gate — and scores it with a blind external grader that never enters a run. Its product command (`helpagent "<request>"`) was never built; `docs/ROADMAP.md` V6 records it as `open / does not exist`. The campaign has run to its pre-registered end at revision `45ebb32` and archived three verdicts: capability parity **INCONCLUSIVE** (`24.640/40` vs `pi` `24.960/40`, delta `−0.320`, CI `[−3.520, +3.080]`), verification information **PARTLY / not as stated**, tree decomposition **NEGATIVE** (`47/70` leaf vs `14/70` tree-greedy). Cost is honestly adverse (`~18.9k` vs `~9k` tokens/task). Evidence: `README.md:5`, `README.md:106-124`, `docs/STATUS.md:24-34`, `docs/ROADMAP.md:14-20`, `docs/ROADMAP.md:60-64`. Tree is clean at HEAD `73cc4d9`; the measurement revision is `45ebb32`.

Two open intents coexist in the repo, and they do not agree on order:
1. **M1 recovery** — `docs/ROADMAP.md:17-25` calls recovery "active", but `docs/ROADMAP.md:32` records P1a **BLOCKED / INCOMPLETE at the exhausted two-review cap**, source frozen, and `.scratch/30-harness-recovery/blocked-checkpoint.md:3-10` states continuation needs *one explicitly person-authorised third repair–validation–review cycle* for the same P1a. M2 is unauthorised. As it stands this is a `cost` item, not startable by a worker.
2. **Citable preprint** — the newest commit (`73cc4d9`, 2026-10-20) is `docs/paper-plan.md`, which owns itself to "接手本仓的 agent", names four missing items and a 6-point acceptance. It requires no new experiment, no model, no network write.

### (b) Milestone I propose next

**Milestone: a citable preprint whose every decisive number is recomputable from the repository alone.**

Why this one, from the repo's own evidence:
- It is the latest committed intent (`git log -1`: `73cc4d9`), and it is the only open item that a worker can finish without a person's authorisation (spend would be `idle-compute` + writing; publication itself — Zenodo DOI, push, tag — remains a `cost` act for the root/person).
- Its own acceptance (`docs/paper-plan.md:44-48`) is observable: every number traceable to one line in-repo; **one** reproduce command run once on a clean machine; an explicit "does not refute decomposition itself" statement (`docs/STATUS.md:123`); a frozen tag; no negative result rewritten as success.
- The gap it names is real and small in engineering terms but currently **unmet by a wide margin** in durability terms — this is the finding that matters most:
  - There is **no** reproduce entry point and **no** tag: `ls bench` shows no `reproduce*`; `git tag` is empty; `docs/STATUS.md:216-245` §11 gives seven shell snippets and no expected output.
  - **The decisive raw rows are not in git.** They live in `/tmp` on this machine: `/tmp/wave1/final/n25` (600 MB, R1 head-to-head), `r2` (114 MB, 600-run ablation), `r3` (61 MB, 210-run decomposition) — plus the analysis scripts (`n25/analyze_n25.py` 10.3 KB/251 lines, `r3/analyze.py` 4.5 KB) that compute every CI in the paper. Tracked evidence stops earlier: `git ls-files bench/runs/evidence` = 802 files / 5.4 MB, newest dated `20261006`; `.gitignore:5-7` keeps `bench/runs/*` out of git by design. So today all three verdicts rest on a temporary path, which the law ranks as the lowest durability rung, and on scripts a fresh session cannot find.
  - The **cheap** way out is measured, not guessed: the compact per-run projections are 14.4 MB (`n25`, 656 driver rows) and 13.2 MB (`r2`, 602 rows), and the analysis scripts are single-digit KB — committing those (a few hundred KB after projection) plus the scripts would make the CI tables recomputable without a model server. The **expensive** way out is a re-run (hours of `metered`-class wall-clock against one local server). Choosing between them is a cost decision above me, so I name it rather than take it.
  - Secondary, cheap, in-scope for the same milestone: the entrance documents are stale — root `STATUS.md:17` pins its state to `999ea9a` and does not mention `docs/paper-plan.md`, and `.scratch/active-work.md:11` points at `docs/STATUS.md §8e`, a section that no longer exists (`docs/STATUS.md` runs §1–§12).

**Explicitly not in this milestone:** M2 experiments, the product CLI (V6), new corpus, model swaps, publication itself.

### (c) Questions I cannot answer

1. **Paper before or after the frozen M1 recovery?** The repo holds both open, contradictorily: `docs/ROADMAP.md:32` says recovery is the active line and P1a is HOLD at its cap; `docs/paper-plan.md` (newer) assigns the repo to the paper. Nothing in-repo ranks them, and `docs/ROADMAP.md:32` and the blocked checkpoint make recovery startable only on a person's authorisation. **Tried:** read both documents plus the blocked checkpoint, ticket 29's report and `git log`; no line ranks them or retires either. **Would reopen it:** one sentence from the person naming the order, or approval of a third P1a cycle (which would displace the paper), or a decision to close P1a as `blocked` permanently.
2. **What "reproduce" is required to mean** — recompute from committed rows, or re-run the model? The rows are 775 MB of trajectories in `/tmp` and the score-level projection is ~28 MB before compaction; re-running is hours of one local server. This is a storage/durability-vs-compute cost choice, and the paper's acceptance (`docs/paper-plan.md:45`) does not say which satisfies "one command ... run once on a clean machine". **Tried:** located and sized all three datasets and their analysis scripts; confirmed the tracked evidence predates the final campaign; confirmed no analysis script is in git. **Would reopen it:** a decision one way or the other, or a measurement of the smallest committed subset from which `analyze_n25.py` / `analysis.py` reproduce `24.640`, `−0.320`, `[−3.520, +3.080]` exactly.
3. **How much of the audit's residual unknowns must appear in the paper's external-validity section rather than a footnote.** `docs/STATUS.md:190-214` and the ticket-29 audit keep `pi`'s token count partly unmeasured (~9k not recomputable from final rows), retained `pi` samples with length stops and context-size errors before any code write, and unclean wall-clock; `docs/paper-plan.md:33` demands an explicit boundary section. Whether these belong in §7 (limits) as first-class rows is a writing/design call I did not settle. **Tried:** read §10 of `docs/STATUS.md`, `FINDINGS.md` §3–§4 (9 negative results, 3 retractions — note `docs/paper-plan.md:25` says "十六条", which overstates or mislabels the table) and the ablation record. **Would reopen it:** an author decision at review, or a correction of the "16 negative results" count against `FINDINGS.md:29-49`.

### Side observation (evidence for whoever runs the gate)

`uv run pytest` is green — 891 tests collected, exit 0, whole gate ≈ seconds — **provided `.venv/bin` is on `PATH`**. Running the same suite as `.venv/bin/python -m pytest` without that PATH yields one failure, `tests/unit/test_checks.py::test_type_check_filters_at_finding_level`, because `harness/checks.py:165-167` treats `mypy` exiting ≥2 as `typecheck_unavailable` and returns `[]` silently. That silent degradation is worth one line in the reproduce entry: a green gate on a misconfigured machine does not prove the type stage ran.

Implemented: the orientation report above; no code, docs or design changed.
Changed files: none (working tree clean, `git status --porcelain` empty before and after; two pytest scratch logs went to `/tmp`, outside the project).
Validation: gate run twice, once without `.venv/bin` on PATH (1 failed / 890 passed) and once with it (exit 0, 891 collected); data locations sized with `du`, `wc`, `git ls-files`; intent documents and grep for `reproduce`, `tags`, `§8e` checked.
Open risks/questions: items (c)1–(c)3 above; the headline numbers' only home today is `/tmp/wave1/final`, which one reboot erases.
Recommended next step: root decides (c)1 and (c)2; if the paper wins, dispatch one package: commit a compact per-run score projection plus the three analysis scripts for `n25`/`r2`/`r3`, add a single `bench/reproduce.py` that regenerates every number in `docs/STATUS.md` §3–§7 from committed rows and prints expected output, and create the freeze tag — then stop before publication.