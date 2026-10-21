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
`sha256sum -c` run from the declared home against the committed manifest returns `28000+` OK
lines and zero `FAILED`, and the report naming the home, the manifest, the command and that
result is in root's mail. Spent: `idle-compute`, local copy and hashing.

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
| WP-0.1 | Copy `/tmp/wave1/final/{n25,r2,r3}` to the declared home `bench/runs/wave1/final/` | running |
| WP-0.2 | Hash every file; commit the manifest and the analysis scripts | queued behind WP-0.1 |
| WP-0.3 | Record the taken-over state (this document, `STATUS.md` route) | running |
| WP-0.4 | Handover report to root | queued behind WP-0.2 |
| WP-1.1 | Answer-independent half of M1: protocol, results and limits sections, which no pending answer can move | queued, starts when M1 is released |
| WP-1.2 | The reproduce entry point; its shape is exactly what the second open answer decides | blocked on the answer |

### In flight, as of the first turn

WP-0.1 is `cp -a` of the three directories into `bench/runs/wave1/final/`, run detached behind
`bench/runs/wave1-copy.log`, because a copy of 28 150 files is not work for a turn. What would
prove it: the destination holding the same 28 150 regular files, with no symlink and no hard
link in the source to begin with, and per-file hashes equal on both sides. WP-0.2 then writes
`bench/manifests/wave1-final.sha256` from the **destination** — the durable copy is the truth
from that moment — and proves the copy by comparing it against a manifest of the source: equal
line counts and an empty `diff`. The scripts are lifted out of the same trees into
`bench/analysis/wave1/`, so their hashes equal their manifest entries by construction, and the
equality is checked rather than assumed. WP-0.3 and WP-0.4 land after those two, in that order.
If this session dies mid-copy, the resume point is to remove the partial home and re-run the
same `cp -a`; nothing committed depends on a partial tree.

## Current facts

**Secured.** The declared home is `bench/runs/wave1/final/`, inside this checkout, holding
`n25/`, `r2/` and `r3/` with the same relative layout as the temporary source, so the analysis
scripts resolve their inputs unchanged. `git` cannot hold 724 MB, so the home is not tracked;
the `.gitignore` entry `bench/runs/*` already covers it and names raw run output as its owner,
and the manifest below is what makes it verifiable rather than merely present. Verification is
`sha256sum -c`, not an exit code: the manifest is `bench/manifests/wave1-final.sha256`, one line
per file, paths relative to the home. The analysis scripts also have a tracked home —
`bench/analysis/wave1/` — so a fresh session finds what computes the intervals without mounting
the 724 MB, and their hashes equal the manifest's entries for the same files.

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
| declared home for the campaign bytes (724 MB, untracked, verify by hash) | `bench/runs/wave1/final/{n25,r2,r3}` |
| hash manifest over that home (28 150 files) | `bench/manifests/wave1-final.sha256` |
| verify command | `cd bench/runs/wave1/final && sha256sum -c ../../../manifests/wave1-final.sha256` |
| analysis scripts, tracked copy | `bench/analysis/wave1/{n25,r2,r3}/`, plus `final-analyze.py` |
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
