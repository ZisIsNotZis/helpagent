# helpagent — node document

The `helpagent` campaign reached its pre-registered end at revision `45ebb32` and stopped:
three verdicts are archived (capability parity **INCONCLUSIVE**, verification information
**PARTLY / not as stated**, tree decomposition **NEGATIVE**) and the product CLI was never
built. What this repository owes now is not another measurement but a form in which the
measurement can be read and checked by somebody who is not this machine. This node owns that
ending. The order of its work follows from one asymmetry: the bytes behind every decisive
number sit on `/tmp/wave1/final`, a path one reboot erases, while the writing can be restarted
at any hour from documents that are already committed. So durability comes before authorship —
the evidence is copied to a declared home and hashed on the first day, before a sentence of the
preprint exists — and authorship in turn waits on two answers that sit above this node (whether
the preprint or the frozen recovery line runs first, and what "reproduce" is allowed to cost),
because each one changes what the next milestone is rather than how it is worded. Nothing here
re-measures, runs a model, or needs a server: this node spends `idle-compute` and writes.

## Roadmap

### Milestones, owed to root

**M0 — the campaign's evidence secured and the takeover recorded.** Decided by one observation:
`sha256sum -c` run from the declared home against the committed manifest returns 53 270 `OK`
lines and zero `FAILED`, and the report naming the home, the manifest, the command and that
result is in root's mail. Spent: `idle-compute`, local copy and hashing. **Reached** — the
observation is in the evidence pointers below; the report is WP-0.4.

**M1 — a citable preprint whose every decisive number is recomputable from the repository
alone.** Decided by one observation: on a clean clone at the frozen tag, one command with no
model server and no network prints `24.640`, `24.960`, `−0.320`, `[−3.520, +3.080]`, `47/70`,
`14/70` and the R2 rows, and that output equals the table in the paper; and `git tag` names the
measurement revision. Gated on two answers that are already above this node (order; what
reproduce may cost) — they decide whether M1 runs now, and which half of its hardest item
(committed projection versus re-run) the acceptance is written against.

**Not on this roadmap:** the recovery line (P1a frozen at the exhausted two-review cap,
`docs/ROADMAP.md:32`, `.scratch/30-harness-recovery/blocked-checkpoint.md`). It becomes a
milestone here only if the order answer puts it first; until then it is not this node's work to
start, because its continuation needs a person's authorisation that no node below can lend.

### Work packages

| id | package | state |
| --- | --- | --- |
| WP-0.1 | Copy `/tmp/wave1/` to the declared home `bench/runs/wave1/` | done — `rsync -a`, 53 270 files, 1 996 009 173 bytes, two runs, exit 0 |
| WP-0.2 | Hash every file; commit the manifest and the analysis scripts | done — `bench/manifests/wave1.sha256`, `bench/analysis/wave1/` |
| WP-0.3 | Record the taken-over state (this document, `STATUS.md` route) | done |
| WP-0.4 | Handover report to root | done |
| WP-1.1 | Answer-independent half of M1: protocol, results and limits sections, which no pending answer can move | queued, starts when M1 is released |
| WP-1.2 | The reproduce entry point; its shape is exactly what the second open answer decides | blocked on the answer |

### What was in flight, and how it landed

The copy was widened past the three directories the contract named, because the analyzers read
more than those three: `analyze_n25.py:40-43` opens `our-n5`, `n9` and `n17` as well, since
seeds 1..17 of the R1 head-to-head predate the `n25` wave. That is not an optimisation, it is
the difference between an interval and a silent wrong answer — `read_jsonl` returns `[]` for a
root that is missing, so with `n17` absent the same script prints `delta +0.06`, `CI
[−3.35, +3.71]` over 680 rows instead of `−0.320` / `[−3.520, +3.080]` over 1000, and raises
nothing. So the declared home is the whole `/tmp/wave1` root, and the observable that catches a
short home is the row count (1000 per arm for R1), which is why `recompute_n25.py` checks it
before it compares anything.

Proven, in this order. The copy: `rsync -a --numeric-ids /tmp/wave1/ bench/runs/wave1/`,
`total size is 1 996 009 173`, exit 0, run twice (the first run carried only `n25`, `r2`, `r3`,
the second the rest of the root; rsync skips what is already equal). Equality of the copy with
its source, measured rather than assumed: `sha256sum` over both trees, sorted, and `diff` of
the two lists — empty, 53 270 lines each; the source-side list is kept at
`bench/runs/wave1-src-manifest.sha256` (untracked, so the equality stays re-checkable while
`/tmp` survives, and is deletable when it does not). Durability: `sha256sum -c` from the home
returned 53 270 `OK` and 0 `FAILED`, exit 0. And usability, which is the part a hash cannot
promise: all three verdicts recompute from the home — see the evidence pointers below.

## Current facts

**Secured.** The declared home is `bench/runs/wave1/`, inside this checkout, a byte-for-byte
mirror of `/tmp/wave1/`: 53 270 files, 1 996 009 173 bytes, including `final/{n25,r2,r3}` and
the three roots the R1 analysis also reads. The layout is the source's, so the analysis
scripts resolve their arms unchanged. `git` cannot hold 2.0 GB, so the home is not tracked;
`bench/runs/*` already ignored it and now names it (`bench/runs/wave1/`, owner: this node).
What makes it evidence rather than merely present is `bench/manifests/wave1.sha256`: 53 270
lines, one per file, paths relative to the home, and `sha256sum -c` against it returns 53 270
`OK`, 0 `FAILED`, exit 0. The analysis scripts have a tracked home too —
`bench/analysis/wave1/{final,n25,r2,r3}/`, 36 files, 252 KB — so a fresh session finds what
computes the intervals without mounting the 2 GB; `verify_home.py` checks each of those 36
against the manifest entry of the file it came from, and all 36 match.

**Recomputable from the home, measured for all three verdicts.** R1: `recompute_n25.py` runs
the campaign's own `analyze_n25.py` with its four roots pointed at the home and gets
`24.640` / `24.960` / `−0.320` / `[−3.520, +3.080]` over 1000 rows per arm, equal to the
recorded `analysis-n25-final.json`. R2: `r2_analyze.py --glob
'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl'` reproduces `analysis.txt` and
`analysis.json` byte-identically. R3: `R3=bench/runs/wave1/final/r3 analyze.py` reproduces
`analysis-r3.txt` byte-identically (`leaf 47/70` in the arm table's 70 runs, `tree-greedy`
`14/70`, `tree-tournament` `15/70`, McNemar `p ≤ 0.001`). So the three verdicts no longer
depend on a temporary path for anything a reader needs to check.

**Taken over, as found.** HEAD `73cc4d9` plus root's mail commit `bf0fed7`; working tree clean
before this node's first write; no git tag; `bench/runs/evidence/` (802 files, 5.4 MB) is the
only tracked run evidence and it predates the final campaign, newest `20261006`. The whole
project's decisive numbers hang on three archived verdicts recorded in `docs/STATUS.md` §2–§7.

**Decided.** No new experiment is needed for M1 (the repo's own `docs/paper-plan.md:36-38`
says so, and this node agrees on the evidence: the analyzers plus the secured rows recompute
the numbers). Publication — a DOI, a push, a tag — is a `cost` act above this node and is not
taken here.

**Open, raised and waiting above (do not restate, wait for mail).** Two questions were raised
to the person before this node existed and are not repeated here: the order between the
preprint and the frozen recovery line (`mail/` of root, `2026-10-21-helpagent-order.md`), and
what "reproduce" is allowed to cost — a committed projection or a re-run
(`2026-10-21-helpagent-reproduce.md`). M1's start and M1's hardest acceptance line both hang on
them.

**Open, this node's own.** Whether the committed projection is small enough to make
"recomputable from the repository alone" true on a machine that has never seen `/tmp` — that is
the measurement `docs/paper-plan.md` asks for and it is not taken yet. Nothing here closes it by
assumption.

## Evidence pointers

| what | where |
| --- | --- |
| declared home for the campaign bytes (2.0 GB, 53 270 files, untracked, verify by hash) | `bench/runs/wave1/` |
| hash manifest over that home | `bench/manifests/wave1.sha256` |
| verify the home (rehash every file, check the 36 analysis copies) | `python3 bench/analysis/wave1/verify_home.py` → `ok 53270 mismatch 0 missing 0 analysis-copies-ok 36 analysis-copies-bad 0`, exit 0 |
| verify with the standard tool instead | `cd bench/runs/wave1 && sha256sum -c ../../manifests/wave1.sha256` → 53 270 OK, 0 FAILED |
| recompute R1 from the home (`−0.320`, `[−3.520, +3.080]`) | `python3 bench/analysis/wave1/recompute_n25.py` |
| recompute R2 from the home | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl' --out /tmp/r2.json --text /tmp/r2.txt` |
| recompute R3 from the home | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| analysis scripts, tracked copy (36 files) | `bench/analysis/wave1/{final,n25,r2,r3}/` |
| source-side hash list taken at copy time (untracked, expires with `/tmp`) | `bench/runs/wave1-src-manifest.sha256` |
| copy and verification logs | `bench/runs/wave1-copy.log`, `-copy-full.log`, `-hash.log`, `-verify.log` (ignored, owner: this node) |
| three verdicts, every decisive number | `docs/STATUS.md` §2–§7 |
| negative results and retractions | `FINDINGS.md` §3–§4 |
| the preprint's own intent and acceptance | `docs/paper-plan.md` |
| recovery line, frozen | `docs/ROADMAP.md:32`, `.scratch/30-harness-recovery/blocked-checkpoint.md` |

## Entrance

**Start** with `STATUS.md` (one screen: what this is, what state it is in, where progress
lands), then this file. The law this node runs under is `/home/z/vibe/agent-policy/AGENTS.md`;
it is read once and not copied here.

**Continue** from the roadmap above. The tree is committed at every hand-over, so the next
session's first question is only whether mail in `mail/` has changed the order of work.

**Where things differ from the general convention.** The decisive evidence is *not* in git —
the home above, verified by the manifest, is the highest rung `git` cannot reach. Mail for this
node lands in `mail/` here; answers to the two raised questions arrive there too.

**Not current, and says so on its face.** `STATUS.md`'s state pin to `999ea9a` and
`.scratch/active-work.md` (dated 2026-10-09, pointing at a `docs/STATUS.md` §8e that no longer
exists — `docs/STATUS.md` runs §1–§12) are historical handover notes, kept as records. The
current state of this project is this file.
