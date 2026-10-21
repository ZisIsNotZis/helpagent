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
measurement revision. **Accepted and released by root on 2026-10-21, in exactly that wording;
this node is on it now.** The order question does not gate it: protocol, results, limits and
the traceability table are worth writing before the answer, because the paper is written
whichever way the order goes and only its framing changes. "What reproduce may cost" is settled
here by measurement rather than by the answer: the projection is built over the committed
rows and its size and fidelity are reported; if the tables cannot be regenerated without the
2 GB home, that finding *is* the answer and is reported rather than papered over.

**Reached, in that wording.** `python3 bench/checks/m1_acceptance.py` clones this repository at
tag `preprint-v1` into a temporary directory, runs the one command there with no untracked home
present, requires each printed key to be quoted on one line of `docs/paper/`, and requires three
starved trees to fail loudly; it exits 0 and prints `m1 acceptance: OK`. The tags: `wave1-measurement`
names the measurement revision `45ebb32`, `preprint-v1` names the revision the check runs at.
What M1 does not deliver, and does not claim, is publication — a DOI, a push or an arXiv
submission is a `cost` act above this node and is not taken here.

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
| WP-0.5 | Traceability seed: which number comes from which command, and which are not yet re-derived | done — `bench/analysis/wave1/NUMBERS.md` |
| WP-1.1 | Paper draft: problem, protocol, results 1–3, negative results and retractions, external-validity boundary, reproduce section | done — `docs/paper/`, 8 sections + `numbers.md` (97 rows, 26 marked unknown) |
| WP-1.2 | Reproduce entry point over a committed projection, inputs asserted, no network and no model | done — `reproduce.py`, `bench/projection/` (472 files, 2 810 rows, 523 499 bytes) |
| WP-1.3 | Freeze the measurement revision as a tag; integration check that the paper's table equals the command's output | done — `wave1-measurement`, `preprint-v1`, `bench/checks/m1_acceptance.py` |
| WP-1.4 | Handover report to root naming M1, its command and the decision needed | done — the report in `mail/` |

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

Landed this advance: two packages ran in parallel into disjoint paths and were integrated here —
the paper (`docs/paper/`, WP-1.1) and the entry point (`reproduce.py` with `bench/projection/`,
WP-1.2). Four things the integration repaired rather than noted. The acceptance checker written
before the package landed starved the tree by deleting `bench/projection/README.md`, a file no
analyzer reads, so it would have failed a healthy tree: found by the package, fixed here, and its
victims are now records under `bench/projection/wave1/final/` with the short-sample case added.
`bench/analysis/wave1/NUMBERS.md` had a four-column header over three-cell rows, broken by this
node in the act that made the key a column and repaired in the same advance. `docs/paper-plan.md:22`
claimed "sixteen negative results" where `FINDINGS.md` §三 holds nine rows and §四 three; the
count is deleted and the sections are named, because a row count is derived and a derived
number stored by hand drifts. And the paper's citations to this document by line number became
section references, so editing this file cannot silently invalidate the paper; its references
into `docs/STATUS.md` and `FINDINGS.md`, which this advance did not touch, stay as line numbers
and are resolved by `docs/paper/check_citations.py`.

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

**Recomputable from the repository alone, measured.** `python3 reproduce.py` prints 21
`key value` lines and exits 0 in 4.4 s on a tree with no `bench/runs` at all. It feeds the
campaign's own analyzers from `bench/projection/wave1/final/` — 472 files, 2 810 rows, 523 499
bytes raw, 57 561 gzipped, cut from the 62 MiB of inputs the analyzers read — and compares every
value against the record committed beside its analyzer before it prints one line. Fidelity of
the projection to the home it was cut from: `python3 bench/analysis/wave1/fix/verify_projection.py`
returns `ok files=472 rows=2810 mismatches=0`, and one flipped `actual` in a copy returns
`mismatches=1`, exit 1. Loud failure, three ways, each exiting 1 with zero stdout lines: a
deleted record (`missing input: … file not found`), a zero-row record (`empty input: … 0 rows
read`), a short sample (`short sample: R1 arm a (ours) seed 20 — 35 rows, wanted 40 … arm a
then has 995 of 1000`). Two limits are recorded rather than smoothed: R2's `analysis.json` is
compared parsed, not byte-wise, because its `stop_reasons` ties depend on set-iteration order;
and `r3/supp.py`'s one `/tmp` literal is replaced under an exactly-once assertion so a future
edit stops the run instead of silently reading a temporary path.

**Taken over, as found.** HEAD `73cc4d9` plus root's mail commit `bf0fed7`; working tree clean
before this node's first write; no git tag; `bench/runs/evidence/` (802 files, 5.4 MB) is the
only tracked run evidence and it predates the final campaign, newest `20261006`. The whole
project's decisive numbers hang on three archived verdicts recorded in `docs/STATUS.md` §2–§7.

**Decided.** No new experiment is needed for M1 (the repo's own `docs/paper-plan.md:36-38`
says so, and this node agrees on the evidence: the analyzers plus the secured rows recompute
the numbers). Publication — a DOI, a push, a tag — is a `cost` act above this node and is not
taken here.

**Granted, and what it is.** Root granted the authoring package on 2026-10-21: the spend is
`tokens` against this level's model budget plus `idle-compute` wall-clock, not metered money, so
no grant is outstanding for it and no package waits on one. The grant covers this node and the
workers it dispatches; it does not cover a push, a DOI or a rented device.

**The reproduce interface, fixed here so that two workers cannot diverge.** One command at the
repository root, `python3 reproduce.py`, run from a clean clone: it needs no `/tmp`, no model
server and no network, and it must not require the untracked 2 GB home. It prints one
`key value` line per decisive number (`r1_a_mean_tasks 24.640`, `r1_delta_tasks -0.320`,
`r1_lo95 -3.520`, `r1_hi95 3.080`, `r3_leaf 47/70`, `r3_tree_greedy 14/70`, and the R2 rows),
and exits 0 only when every printed value equals the value recorded at campaign time. The paper
quotes these keys verbatim, so the acceptance is a diff and not a reading.

**A short home fails loudly, by construction.** The n17 trap found on takeover is a requirement
on the entry point, not a note: a missing root, a zero-row file and a short sample each stop the
run with a named line naming the input and the count it wanted, before any number is printed.
The paper's boundary section states this, because a reproduction that reports parity after
reading an empty directory is worse than no reproduction.

**Open, raised and waiting above (do not restate, wait for mail).** Two questions were raised
to the person before this node existed and are not repeated here: the order between the
preprint and the frozen recovery line (`mail/` of root, `2026-10-21-helpagent-order.md`), and
what "reproduce" is allowed to cost — a committed projection or a re-run
(`2026-10-21-helpagent-reproduce.md`). Neither gates M1 any more: the authoring package runs in
either order, and the projection's measured cost is reported as the answer to the second rather
than waited on. Their answers still arrive in `mail/` and still move what this node does next.

**Closed, this node's own — what "reproduce" may cost.** It costs 0.5 MB of committed rows, not
2 GB: the decisive numbers recompute from `bench/projection/wave1/final/` with no home, no
`/tmp`, no model and no network, in under five seconds, and every number is gated against the
record the campaign committed. The committed projection was the option the open question named;
it is now measured rather than proposed, so the question no longer blocks anything.

## Evidence pointers

| what | where |
| --- | --- |
| the preprint, section by section, with its index | `docs/paper/README.md` |
| every number the paper uses, its `file:line` source and the command that re-derives it (97 rows; 26 marked unknown with the gap named) | `docs/paper/numbers.md` |
| resolve the paper's citations and its Numbers table (fails loudly on a moved line or a number with no command) | `python3 docs/paper/check_citations.py` → `citations resolved N unresolved 0`, exit 0 (N is printed, not stored) |
| M1's deciding observation as an exit code: clone at the tag, one command, paper must quote every key, starved trees must fail loudly | `python3 bench/checks/m1_acceptance.py` |
| recompute every decisive number from committed rows, no home, no `/tmp`, no model, no network | `python3 reproduce.py` |
| what a projection row is, which fields it keeps, what it cannot show | `bench/projection/README.md` |
| rebuild or re-check the projection against the home (maintainer recipe; needs the home) | `python3 bench/projection/build_projection.py --check` |
| projection fidelity to the home it was cut from | `python3 bench/analysis/wave1/fix/verify_projection.py` → `ok files=472 rows=2810 mismatches=0` |
| declared home for the campaign bytes (2.0 GB, 53 270 files, untracked, verify by hash) | `bench/runs/wave1/` |
| hash manifest over that home | `bench/manifests/wave1.sha256` |
| verify the home (rehash every file, check the 36 analysis copies) | `python3 bench/analysis/wave1/verify_home.py` → `ok 53270 mismatch 0 missing 0 analysis-copies-ok 36 analysis-copies-bad 0`, exit 0 |
| verify with the standard tool instead | `cd bench/runs/wave1 && sha256sum -c ../../manifests/wave1.sha256` → 53 270 OK, 0 FAILED |
| recompute R1 from the home (`−0.320`, `[−3.520, +3.080]`) | `python3 bench/analysis/wave1/recompute_n25.py` |
| recompute R2 from the home | `python3 bench/analysis/wave1/r2/r2_analyze.py --glob 'bench/runs/wave1/final/r2/runs/*/*/*/results.jsonl' --out /tmp/r2.json --text /tmp/r2.txt` |
| recompute R3 from the home | `R3=bench/runs/wave1/final/r3 python3 bench/analysis/wave1/r3/analyze.py` |
| every number above, the command that re-derives it, and the gaps not yet re-derived | `bench/analysis/wave1/NUMBERS.md` |
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
session's first question is only whether mail in `mail/` has changed the order of work. The
preprint is `docs/paper/README.md`; the command that proves it is `python3 bench/checks/m1_acceptance.py`.

**Where things differ from the general convention.** The decisive evidence is *not* in git —
the home above, verified by the manifest, is the highest rung `git` cannot reach. Mail for this
node lands in `mail/` here; answers to the two raised questions arrive there too.

**Not current, and says so on its face.** `STATUS.md`'s state pin to `999ea9a` and
`.scratch/active-work.md` (dated 2026-10-09, pointing at a `docs/STATUS.md` §8e that no longer
exists — `docs/STATUS.md` runs §1–§12) are historical handover notes, kept as records. The
current state of this project is this file.
