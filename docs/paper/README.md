# A citable preprint of the helpagent campaign — draft index

Kind: authored draft plus one check script. Owner: M1 of the helpagent node (`AGENTS.md`).
This is not a result document: every number it uses is owned by `docs/STATUS.md`, `FINDINGS.md`
and `bench/analysis/wave1/NUMBERS.md`, and this draft points at them.

## What the draft claims

One 4B model, one corpus of `40` tasks, one external blind grader. A harness written as a
program, with the model as a contract-bound node, did not establish a capability difference
against a mature free-form agent CLI: the pre-registered non-inferiority test returned
**INCONCLUSIVE** (`docs/STATUS.md:28`). The same harness's tree-of-children bundle was clearly
worse than its monolithic leaf on the same corpus (`docs/STATUS.md:30`). Verification stages
carried *some* information and cost more than they returned (`docs/STATUS.md:29`). The paper's
methodological contribution is the protocol plus the negative-result and retraction record.

## Sections

| file | what it holds |
| --- | --- |
| [`01-problem.md`](01-problem.md) | how a harness's "improvement" gets falsified; why the four usual readings fail |
| [`02-protocol.md`](02-protocol.md) | external blind grader outside the run loop, the corpus, pre-registration, the `M=3` rule and why that margin |
| [`03-result-r1.md`](03-result-r1.md) | R1 capability parity: INCONCLUSIVE, and why more seeds do not fix it |
| [`04-result-r3.md`](04-result-r3.md) | R3: the monolithic leaf beats both tree arms; the scope of that negative |
| [`05-result-r2.md`](05-result-r2.md) | R2: verification partly informative, and the unfavourable cost numbers |
| [`06-negative-results.md`](06-negative-results.md) | negative results and retractions as a methodological contribution |
| [`07-limits.md`](07-limits.md) | the external-validity boundary, in its own section, and what this paper does not conclude |
| [`08-reproduce.md`](08-reproduce.md) | one command, its keys verbatim, and how it fails loudly |
| [`numbers.md`](numbers.md) | the single home for every number: Number, Value, Source, Command |

Page budget: `docs/paper-plan.md:32` asks for a paper of the stated length; the source is
markdown and the count of words is reported in the acceptance of this draft, not estimated here.

## How to check the draft

```sh
python3 docs/paper/check_citations.py   # exits 0 only when every citation and command resolves
```

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

Not a published paper. No DOI and no submission: the publication act is above this node
(`AGENTS.md`). Tag `preprint-v1` freezes the revision `bench/checks/m1_acceptance.py` checks
this draft at; freezing a revision is not publishing it. Not a re-measurement: the numbers were measured once, on revision
`45ebb32` (`docs/STATUS.md:6`), and this draft re-derives them from committed bytes. Not a
success narrative: where the campaign failed to establish something, the sentence says
failed to establish.
