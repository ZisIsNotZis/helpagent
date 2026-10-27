# EXPLICIT

## The paper goes first unless the paper needs the broken tool

> we can't wait for research done, so it's fix the 短板 first before doing more research; if tool
> needed to write paper, fix that, otherwise do paper first

The rule turns on one question — do the preprint's claims, numbers or reproduce commands need the
repair — and on this tree the answer is no, file by file:

- Every row of `docs/paper/numbers.md` names one of four commands, and none of them executes
  `harness/`: a printed key of the entry point, the bare entry point, an analyzer under
  `bench/analysis/wave1/`, or `unknown` with the gap named.
- The entry point and the four analyzers it runs import nothing outside the standard library and
  this repository, and none of them mentions `harness/`.
- The draft cites harness source once, in `docs/paper/07-limits.md`, in the limit that discloses
  the coupling and never in support of a result.
- The counterexample the recovery line blocked on cannot be inside the measured revision: the
  captured-output boundary, the counterfeit-heading route and the setup-repair classifier are
  code this campaign never ran.

So the repair cycle the person made available stays unspent and P1a stays blocked
(`docs/0_ROADMAP.md#the-frozen-recovery-line`). One coupling is real and is disclosed rather than
repaired: at the measured revision the harness decides whether a red check blames the run's own
test or its source by parsing pytest failure text the run can influence, and the paper's limits
section says what that bounds — the reading, not the numbers, whose arbiter is the external
grader.

# INFERRED

## The deliverable

Two things, and neither is a fourth harness:

- **The preprint**, `docs/paper/preprint.md`, read as one file: abstract, eight sections, the
  numbers appendix. It is a render built from the authored section files, so it holds no sentence
  they do not hold, and `python3 docs/paper/build_preprint.py --check` proves the render is
  current.
- **The reproduce entry point**, `python3 reproduce.py`: the decisive numbers recomputed from
  committed rows, no model, no network, no campaign archive
  (`docs/7_INTERFACE.md#entry-point-contract`).

The campaign's own result — three verdicts, the negative results, the retractions — is the
paper's content and the documents it cites; it is not restated here
(`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).

## Read order

`docs/paper/README.md` is the index: the abstract states the claims once, the numbered sections
carry the argument, `numbers.md` is the single home for every number with the command that
re-derives it. A reader who wants the result reads the render. A reader who wants to edit reads
the section file, because the render is derived and is never edited by hand.

## What "reproduce" costs

Half a megabyte of committed rows, not 2 GB: the decisive numbers recompute from
`bench/projection/wave1/final/` with no home, no `/tmp`, no model and no network, in under five
seconds, and every number is gated against the record the campaign committed. Fidelity of the
projection to the home it was cut from is itself a check
(`docs/9_IMPLEMENTATION.md#evidence-pointers`). This closes the question the person left open — what
"reproduce" is allowed to cost — by measurement rather than by argument.

## Reusable parts

The extraction is `docs/8_DETAIL.md#negative-results` and the methodology requirements in
`docs/3_REQUIREMENT.md`. In one list:

- The design principle: harness as program, model as a contract-bound fallback node.
- The blind grading protocol and the tamper guard.
- The one-claim-gate invariant with its structural test.
- The evidence ledger and the `EVIDENCE GAP` state.
- The claim-basis distinction: a claim is only as strong as the check that carried it.
- The measured division of labour between the own test, the independent test and the review —
  and the finding that they are not interchangeable.
- The evaluation checklists, including "compare the delivered bytes to every revision the run
  wrote".
- The negative results, which save a future project from repeating them.
- The design hypothesis, unproven rather than established: small, bounded, checked steps can make
  a weak model usable on a narrow task class.

## What does not transfer

- **The reliability advantage is not a moat.** The lower false-success rate
  (`2.2%` against `6.1%`) comes from a claim gate that is straightforward to add to any agent; it
  is a property of a design, not a durable capability.
- **The cost result is unfavourable.** Roughly twice the tokens of the mature CLI
  (`~18.9k` against `~9k` per task) for no measured capability gain; wall-clock evidence is not
  clean or comparable, so it is not quoted as a win either way
  (`docs/8_DETAIL.md#cost`).
- **Nothing generalises past its scope.** One 4B model, one revision, one 40-task corpus. No
  claim about stronger models, other corpora, other languages, or real repositories.
- **The tree result is bundle-, corpus- and model-scoped.** It does not isolate decomposition or
  field refinement from planning, budget and closed-only delivery, even where splitting fired
  (`docs/8_DETAIL.md#negative-results`).
- **The internal verifiers share the model's weights.** Fresh context helps and does not make
  them independent; the external grader is the arbiter.

## Published, and what is owed to the person

The repository is public and the preprint is pushed to it, and the preprint says so on its face.
Both frozen tags are on the remote as well, so the revision the acceptance check runs at is
reachable by a reader and not only by this clone.

What is still the person's: a DOI deposit and any arXiv submission. This node publishes nothing
further — no DOI, no second public surface — and a tag is not a publication. The revision to
cite is this repository's current one; tag `preprint-v1` freezes only the revision the numbers
check runs at.

### What publishing would take, and what would be permanent

Three acts, each separable, each with a different price:

- **Making the repository public.** Already taken above this node. What becomes public is the
tracked tree and its whole history: the paper, the numbers appendix, the harness source, the
corpus, the half-megabyte projection that makes every number checkable, the licence (AGPL-3.0,
with the five Exercism anchors keeping their own MIT notice) — and also the internal record,
`mail/`, `.scratch/` with its model transcripts, and the author name and address in every commit.
What stays private is the 2 GB evidence home: it is untracked, so a reader re-derives the numbers
from the projection instead of inspecting raw runs.
- **A DOI deposit** (Zenodo, per the paper plan's publication form). This is the only act that
cannot be withdrawn afterwards: a minted DOI resolves forever, and Zenodo restricts or tombstones
a record rather than deleting it.
- **An arXiv submission**, which the plan declines to promise because a new submitter needs
endorsement. A withdrawal stays visible with its abstract.

Why they are three decisions and not one: a pushed commit is cloned and mirrored within minutes,
so rewriting history afterwards does not reach copies; the repository's visibility is the only
step that is genuinely reversible after the fact.

## What is deliberately absent

- **The product CLI.** `helpagent "<request>"` against an arbitrary repository was the thing the
  research was for and was never built; V6 exists as a promise and a UI sketch,
  `docs/mockups/mission_control.html`.
- **A second evaluation.** The M2 controlled evaluation needs the person's approval again, and it
  needs a local model server that this node's hardware cannot run
  (`docs/3_REQUIREMENT.md#no-gpu-and-none-expected-on-this-machine`); it is not started
  (`docs/0_ROADMAP.md#the-frozen-recovery-line`).
- **A DOI, an arXiv submission, any further public surface.** The person's, listed above.
