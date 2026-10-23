# A citable preprint of the helpagent campaign — index and read order

Kind: router. Owner: M1 of the helpagent node (`AGENTS.md`).
This is not a result document: every number it uses is owned by `docs/STATUS.md`, `FINDINGS.md`
and `bench/analysis/wave1/NUMBERS.md`, and the paper points at them.

**Open [`preprint.md`](preprint.md) to read the paper.** It is the whole draft in one file —
title, abstract, eight sections and the numbers appendix — and it is a *render*: `python3
docs/paper/build_preprint.py` builds it from the authored files below, so it holds no sentence
those files do not hold. Read a section as the file listed under §Sections when you want to edit
it; read `preprint.md` when you want to read the paper.

The claims themselves are the abstract ([`00-abstract.md`](00-abstract.md)), stated once there
and nowhere else: one `4B` model, one corpus of `40` tasks, one external blind grader, and three
verdicts — parity **INCONCLUSIVE** (`docs/STATUS.md:28`), verification **partly and not as
stated** (`docs/STATUS.md:29`), the tree bundle **NEGATIVE** (`docs/STATUS.md:30`) — with the
protocol and the losing half of the record as the contribution.

## Sections

| file | kind | what it holds |
| --- | --- | --- |
| [`00-abstract.md`](00-abstract.md) | authored | the claims in one page: conditions, three verdicts, method, boundary |
| [`preprint.md`](preprint.md) | render | the paper as one read form, built from the files below; never edited by hand |
| [`01-problem.md`](01-problem.md) | authored | how a harness's "improvement" gets falsified; why the four usual readings fail |
| [`02-protocol.md`](02-protocol.md) | authored | external blind grader outside the run loop, the corpus, pre-registration, the `M=3` rule and why that margin |
| [`03-result-r1.md`](03-result-r1.md) | authored | R1 capability parity: INCONCLUSIVE, and why more seeds do not fix it |
| [`04-result-r3.md`](04-result-r3.md) | authored | R3: the monolithic leaf beats both tree arms; the scope of that negative |
| [`05-result-r2.md`](05-result-r2.md) | authored | R2: verification partly informative, and the unfavourable cost numbers |
| [`06-negative-results.md`](06-negative-results.md) | authored | negative results and retractions as a methodological contribution |
| [`07-limits.md`](07-limits.md) | authored | the external-validity boundary, in its own section, and what this paper does not conclude |
| [`08-reproduce.md`](08-reproduce.md) | authored | one command, its keys verbatim, and how it fails loudly |
| [`numbers.md`](numbers.md) | authored | the single home for every number: Number, Value, Source, Command |

Page budget: `docs/paper-plan.md:32` asks for a paper of the stated length; the source is
markdown and the count of words is reported in the acceptance of this draft, not estimated here.

## How to check the draft

```sh
python3 docs/paper/check_citations.py            # every citation and command resolves
python3 docs/paper/build_preprint.py --check     # preprint.md is exactly what the sources build
python3 reproduce.py                             # the decisive numbers, from committed rows only
```

`build_preprint.py --check` is what a render needs: it rebuilds the paper in memory and names
the first line where the committed `preprint.md` differs, so a hand edit to the read form, or a
section edited without a rebuild, is caught instead of read as current. `check_citations.py`
skips the render for the same reason — its sentences are the authored ones — and checks those.

The script resolves every `path:line` reference in `docs/paper/*.md` against this repository,
re-reads every row of the numbers table, checks each `Source` cell resolves and that the row's
value actually appears on the line it cites, and checks each `Command` cell is either a key the
entry point prints or a command the traceability table already records. It also fails if a
numeral appears in the prose that the numbers table does not carry. Its own failures are named
one per line; it prints `citations resolved N unresolved 0` and exits 0 when nothing is left
unresolved.

What the script does **not** cover: whether a citation supports the sentence that carries it,
and whether the campaign's interpretation is right. It checks coordinates and values, not
reading. A green run means the draft's numbers point where it says they point.

## What this draft is not

Not a published paper. No DOI, no submission, no remote this node has written to: the
publication act is above this node (`AGENTS.md`, and the summary of what it would take is in
`mail/2026-10-23-helpagent-paper-first.md`). Tag `preprint-v1` freezes the revision
`bench/checks/m1_acceptance.py` checks the sections at; freezing a revision is not publishing it,
and it does not contain the §7 limit or this index, which are later than the tag. Not a re-measurement: the numbers were measured once, on revision
`45ebb32` (`docs/STATUS.md:6`), and this draft re-derives them from committed bytes. Not a
success narrative: where the campaign failed to establish something, the sentence says
failed to establish.
