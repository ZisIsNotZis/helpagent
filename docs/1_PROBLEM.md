# CONFIRMED

## The one experiment

Wrap a weak local model — Spark-X2.5-4B Q4_K_M on llama.cpp — in a conventional
software-engineering process, and measure honestly whether the result is better than the same
model driving a mature free-form agent CLI (`pi`) on the same 40 tasks with every knob maxed,
scored by a blind external grader. That is the whole project; everything else is a means to
it.

## Why it was worth paying for

Three claims were worth a measurement, and each is a claim about the process rather than about
the model:

- **Capability.** A checked, bounded process can carry a 4B model to the coding level of a
  mature CLI on the same weights, and not merely to a plausible transcript
  (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).
- **Verification.** A test and a review written by the same weak model carry information about
  correctness, rather than a second opinion that agrees with the first mistake
  (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).
- **Structure.** Decomposition into nodes with several candidate approaches buys work that
  prompting alone cannot get out of the baseline
  (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).

Cost is part of the claim, not a footnote: a process that matches the baseline by spending
twice the tokens has not carried the model anywhere. The requirement that cost be measured
rather than assumed is C5 in `docs/2_GOAL.md#the-campaign-slices-and-their-verdicts`.

## What the project is not

- Not a product. The command it was built toward, `helpagent "<request>"` against an arbitrary
  repository, was never built; it is V6 and it does not exist
  (`docs/5_PRODUCT.md#what-is-deliberately-absent`).
- Not a benchmark and not a claim about other models, corpora or languages. Every result holds
  for one model, one revision and one 40-task corpus
  (`docs/2_GOAL.md#known-limits`).
- Not a proof that any of the three goals is impossible. The campaign ended as a resource
  decision with the goals unmet or unresolved
  (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`).

# INFERRED

## How the project ends, and what the problem is now

The campaign ran to its pre-registered end and stopped. What it produced is a reusable
measurement protocol, three verdicts, and a body of retracted claims with the reason each was
retracted — and the value of all three is lost unless somebody who is not this machine can
read them and check them.

So the problem the repository holds now is not another experiment. It is that a finished,
priced, decidable experiment is unreadable in the only form it currently has: somebody would
have to read the repository in order to see the protocol, the verdicts and the retractions at
all. A preprint changes no number and answers no open question; it changes who can use the
result (`docs/5_PRODUCT.md#the-deliverable`).

That reframing is what the repository is measured against today, and it is why the deliverable
is a paper plus one reproduce command rather than a fourth harness.
