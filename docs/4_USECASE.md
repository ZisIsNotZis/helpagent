# CONFIRMED

## Reading the result without running anything

A person who wants the campaign's outcome opens one file, `docs/paper/preprint.md`, and reads
it end to end — abstract, protocol, the three verdicts, the negative results and retractions,
the limits, the reproduce section, the numbers appendix. No repository knowledge, no model, no
server, no archive is needed for that read, and it is the read the deliverable exists for.

# INFERRED

## Checking one number against its command

A reader who does not take a number on trust follows one row of `docs/paper/numbers.md`: the row
names the value, the `file:line` or section that states it, and one of a printed key of
`python3 reproduce.py`, the bare entry point, an analyzer command from the traceability table,
or `unknown`. The row is closed when the command runs, exits 0, and prints the value the row
quotes. A row marked `unknown` is closed by reading the gap the table names for it, never by
re-running anything.

## Re-deriving the whole table

A reviewer replays the paper's table with one command and no model: `python3 reproduce.py` at
the repository root prints the decisive numbers from committed rows and exits 0 only when every
value equals the value recorded at campaign time. Then `python3 docs/paper/check_citations.py`
proves the paper quotes them and that no citation has rotted. Both are exit codes, so "I
checked the paper" is a diff rather than a reading.

## Accepting the milestone in the form it was promised

M1 was promised as an observation, not as a claim: a clean clone at the frozen tag, one command,
no model server and no network, the printed values equal to the paper's table, and a starved
tree failing loudly. `bench/checks/m1_acceptance.py` is that sentence as one exit code, and it
runs in a temporary directory without touching the working tree.

## Maintaining the evidence

A maintainer who needs to re-hash the campaign bytes runs the verifier over the declared home,
or `sha256sum -c` against the committed manifest; one who wants a projection row back
re-cuts it from the home and re-checks fidelity. Both recipes are in
`docs/9_IMPLEMENTATION.md#evidence-pointers` and both are stated there as commands rather than as
instructions to read a script.

## Starting the next session

The next session reads `AGENTS.md` and `docs/0_ROADMAP.md` and does not re-measure, re-copy or
re-derive anything already landed. The first question it asks is only whether mail in `mail/`
changed the order of work.

## Deciding what to do next on the research

A researcher who wants to continue reads `docs/2_GOAL.md#known-limits` — what the results cannot
carry — then `docs/8_DETAIL.md#negative-results` — which designs already lost, with their numbers
— then `docs/0_ROADMAP.md#not-on-this-roadmap`. A design not refuted by that record is fair
game; a design that lost needs a different design, not a repeat.
