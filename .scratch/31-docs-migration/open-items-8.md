# Open items — `docs/8_DETAIL.md` and `docs/9_IMPLEMENTATION.md`

Written by the worker that migrated the measured detail (8) and the practice (9). Everything the
assignment allowed is landed; what follows is what a reader of the diff should know and what only
the manager can decide.

## 1. Zone plan, as executed

Both files are a single `# INFERRED` zone. Every source line in the assigned ranges is measured or
derived from a measurement; none of the ranges carries a person's quoted words (the one quoted
person's rule in `AGENTS.md` §Current facts is outside them), and none carries something the
person approved verbatim. So no `# EXPLICIT` and no `# CONFIRMED` zone was created — the shape rule
is that only non-empty zones exist.

## 2. Deliberately dropped, with reasons

- `CONTRIBUTING.md:37-50` (its `## Invariants` section) — **not migrated**: the assignment keeps it
  behind in `CONTRIBUTING.md`; the manager takes it (planned home `docs/3_REQUIREMENT.md`).
- `CONTRIBUTING.md:1` (`# Contributing`) — the document title; the level file's title is the zone.
  Its two intro sentences (`:3-4`) are carried in the lead of `docs/9_IMPLEMENTATION.md`.
- `AGENTS.md:109` (`## Current facts`) — a node-document container heading. Its content is
  distributed into four sections of 9 (`§the-secured-home`, `§recomputing-the-archived-numbers`,
  `§the-entry-point`, `§taken-over-as-found`); the heading itself names nothing that survives.
- `AGENTS.md:95-96` — the work-package ids `WP-1.1` / `WP-1.2`. Node-document work-package
  identifiers; the table that defines them (`AGENTS.md` §Work packages) is not a source for this
  migration. The sentence keeps its content without the ids.
- `AGENTS.md:115`, `AGENTS.md:231` — `owner: this node`. Node-document ownership note; "this node"
  has no referent in `docs/`.
- `AGENTS.md:133` "before this node's first write" → "before the takeover's first write"
  (`docs/9_IMPLEMENTATION.md` §taken-over-as-found): same reason.
- `FINDINGS.md:40` the leading date `2026-10-09` — diary residue, stripped; the row's numbers,
  cases and status are unchanged.
- Heading numbers (`## 6. Cost`, `## 11. Reproducing the numbers`, `## 三、负结果`, …) — stripped,
  per the assignment.
- Bold/italic lead-ins that duplicate a heading: `**Secured.**`, `**Taken over, as found.**`,
  `Two limits are recorded rather than smoothed:`. The heading says it once.

## 3. Duplicate source text, kept once

The sources state several facts more than once. Each meaning now has one home; nothing was lost,
the second copy is a pointer.

- The `llama-server` invocation appeared three times (`CONTRIBUTING.md:20-25`, `README.md:149-153`,
  `docs/STATUS.md:222-226`) — one block in `docs/9_IMPLEMENTATION.md` §the-model-server.
- The gate line appeared twice with different flags (`CONTRIBUTING.md:9` `-q -p no:warnings`,
  `README.md:143`) — both lines in one block in §run-the-gate, so neither flags set was dropped.
- The one-task leaf command `CONTRIBUTING.md:29-30` and `README.md:159` are the same command;
  kept once (two-line form).
- `CONTRIBUTING.md:18` "A model server is required." merged into `README.md:146`'s longer
  "A model server is required for any real run. Start it, then check health:".
- The two sweep forms (`CONTRIBUTING.md:33-34` with `--verify full`, `README.md:165` without) are
  both kept, the second labelled as the same sweep without `--verify full`.
- Negative results are three tables at three grains (`docs/STATUS.md:173-184` mechanism → result,
  `docs/LEARNINGS.md:180-189` reusable statement, `FINDINGS.md:31-41` one conclusion per row with
  its status). The assignment preserves every table, so all three are kept and a connective
  says which grain each one is.
- The three verdicts appear in `docs/STATUS.md` §6–§7 (→ 8) and in the `AGENTS.md` recompute prose
  (→ 9); 8 keeps the measured statement, 9 keeps the command and its expected output.

## 4. Cross-references rewritten

No `file:line` reference survives in either file. Documents this migration deletes are cited by
their **target** path. Those targets were confirmed against the sibling maps and files that
landed while this work was in flight (`map-6.tsv`, `map-7.tsv`, `docs/2_GOAL.md`,
`docs/5_PRODUCT.md`, `docs/6_ARCHITECTURE.md`, `docs/6_FLOW.md`, `docs/7_INTERFACE.md`,
`docs/0_ROADMAP.md`); every `path#anchor` in either file was resolved against the target file's
own headings after landing, not guessed:

| cited in | old reference | new reference |
| --- | --- | --- |
| 8, 9 | `docs/STATUS.md` §2–§7 | `docs/2_GOAL.md` (+ `docs/8_DETAIL.md` for §6–§7) |
| 8, 9 | `FINDINGS.md` §三 / §四 | `docs/8_DETAIL.md#negative-results-one-conclusion-per-row` / `docs/2_GOAL.md` (retractions) |
| 8, 9 | `docs/paper-plan.md` | `docs/5_PRODUCT.md` |
| 8 | `docs/LEARNINGS.md` §6 §7 | `docs/5_PRODUCT.md` |
| 9 | `docs/ROADMAP.md` | `docs/0_ROADMAP.md` (anchor unknown; bare path) |
| 9 | `docs/DESIGN.md`, `docs/FLOW.md` | `docs/6_ARCHITECTURE.md`, `docs/6_FLOW.md` |
| 8 | `docs/paper/07-limits.md:39` | `docs/paper/07-limits.md` (bare path) |
| 8 | `analyze_n25.py:40-43` | `bench/analysis/wave1/n25/analyze_n25.py` |
| 8, 9 | `[x](../…)` markdown links | bare repo-root-relative paths, because both files live in `docs/` and the sources' links were root-relative |

Two sentences in 8 were about the state *before* this migration and named documents that no longer
exist under those names; they now say "the status and findings documents" and "the plan document"
while citing the target path once, earlier in the sentence.

## 5. Left unplaced — outside my assigned ranges

These `AGENTS.md` blocks belong to `docs/9_IMPLEMENTATION.md` by content but were not in the
assignment's source list, so they carry no row in `map-9.tsv` and are **not** in 9:

- `AGENTS.md:153-167` (§Decided, §Published) and `AGENTS.md:169-172` (§Granted) — publication and
  grant state; a `docs/0_ROADMAP.md` or `docs/5_PRODUCT.md` question.
- `AGENTS.md:174-186` — the reproduce **interface contract** ("one command at the repository root,
  `python3 reproduce.py`, run from a clean clone; 21 keys; the acceptance is a diff and not a
  reading") and "A short home fails loudly, by construction". **Placed elsewhere:** `map-7.tsv`
  sends `AGENTS.md:174-187` to `docs/7_INTERFACE.md#entry-point-contract`, and 9 §the-entry-point
  now points there. The loud-failure demand itself is in 8 §a-short-input-stops-the-run from
  `:140-143`, so nothing is lost between the two.
- `AGENTS.md:188-200` — the paper-first decision and the person's quoted rule. That is `# EXPLICIT`
  material for whichever file takes the person's words; not mine.
- `AGENTS.md:202-206` — what "reproduce" may cost (0.5 MB of committed rows, not 2 GB). Reads as 9
  or `docs/5_PRODUCT.md`; unplaced here for the same reason.
- `docs/STATUS.md:1-124`, `:152-215`; `FINDINGS.md:1-28`, `:43-…`; `README.md:1-137`, `:172-…`;
  `docs/LEARNINGS.md:1-174`, `:196-253`, `:265-…` — other levels.

## 6. Two judgement calls the manager may overturn

- **Minus signs.** The sources write `−0.320` with U+2212; `docs/paper/numbers.md` and the preprint
  write `-0.320` with ASCII. Every digit is identical and no value was re-written, but the glyph
  differs. I preserved the source glyph, because normalising typography is not in the allowed edit
  list. If the level scheme wants one glyph, it is a single `sed` over `docs/8_DETAIL.md` and
  `docs/9_IMPLEMENTATION.md` — and, for consistency, over `docs/2_GOAL.md` and the rest.
- **Two near-identical tables of negative results.** `docs/STATUS.md` §9 and
  `docs/LEARNINGS.md` §5 hold the same eight mechanisms; SSOT would merge them into one. Merging
  was not allowed (preserve every table), so both are kept with a connective sentence that names
  the grain of each. If the manager prefers one table, the LEARNINGS one is the richer and the
  STATUS one is the campaign-close summary.

## 7. Map format — a deviation you should know about

The assignment asked for four tab-separated fields per row
(`oldpath, oldstartline, oldendline, newanchor`). `.scratch/31-docs-migration/rewrite_refs.py` —
the tool that turns these maps into the paper's rewritten citations — parses **five** cells
(`oldpath, oldstartline, oldendline, newpath, newanchor`) and silently skips any line that has a
different count. A four-field map would therefore have been read as empty and every citation into
my sections would have been reported unmapped. `map-8.tsv` and `map-9.tsv` are written in the
tool's five-field form, with no header row, to match `map-6.tsv` and `map-7.tsv`; the anchor field
is a bare slug, and `newpath` is the target file. Nothing else about the rows differs from the
assignment: one row per migrated source section, source line range in the middle.

Two consequences worth a glance:

- The tool matches a citation by the **smallest heading section that contains the cited line**, so
  only a row whose `oldstartline` is a real heading start can ever be used. Those rows are present
  for every heading my ranges own (`docs/STATUS.md` 125, 138, 171, 216, 252; `docs/LEARNINGS.md`
  175, 254; `AGENTS.md` 72, 109, 208). The finer rows (paragraph-level splits inside a section) are
  documentation of the split and are inert to the tool; they do no harm.
- `AGENTS.md` §Current facts (109-207) is one heading section split across `docs/2_GOAL.md`,
  `docs/5_PRODUCT.md`, `docs/7_INTERFACE.md` and 9. The tool can hold one target per heading start,
  so a citation to a line in that section lands on `docs/9_IMPLEMENTATION.md#the-secured-home`
  whatever it cites. The paper cites it eight times **by section name**
  (`` `AGENTS.md` §Current facts ``, in `docs/paper/03-result-r1.md`, `07-limits.md`,
  `08-reproduce.md`), which the tool does not rewrite at all: those need a hand edit — the
  reproduce-interface ones to `docs/7_INTERFACE.md#entry-point-contract`, the loud-failure ones to
  `docs/9_IMPLEMENTATION.md#a-short-input-stops-the-run` or `docs/8_DETAIL.md`
  §a-short-input-stops-the-run. `docs/paper/README.md` also names `AGENTS.md` as the node owner,
  which is a fact about the old node document and not a fact any level file holds.

## 8. Verification run for this hand-over

- `wc -l`: 168 lines in `docs/8_DETAIL.md`, 225 in `docs/9_IMPLEMENTATION.md`.
- Every heading slug is unique inside its file (13 in 8, 17 in 9, `# INFERRED` included), checked
  by collapsing each heading to `[a-z0-9-]`; each file carries exactly one zone, `# INFERRED`.
- Every `§Heading` / `path#anchor` reference inside the two files resolves to a heading that
  exists in the file it names (`docs/7_INTERFACE.md#entry-point-contract`,
  `docs/0_ROADMAP.md#the-frozen-recovery-line`, `CONTRIBUTING.md#invariants`,
  `docs/8_DETAIL.md#…`).
- No `file:line` reference and no surviving date (the one `20xx-xx-xx` in 9 is a mail filename).
- `python3 .scratch/31-docs-migration/rewrite_refs.py --check` (dry run, writes nothing):
  `refs rewritten 114, unmapped 402`. None of the 402 unmapped citations lands in a section these
  two maps own — every mapped section of mine resolves — so the rest is the other maps' work in
  progress, not a gap here.
- Line-level coverage: every non-blank source line of every assigned range was matched against the
  two files, and every cell of the `FINDINGS.md` table matched cell by cell; the only unmatched
  lines are the drops in §2 and the rewritten references in §4.
