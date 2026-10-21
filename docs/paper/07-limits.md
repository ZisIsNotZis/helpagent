# 7. Limits and non-conclusions: the external-validity boundary

This section is a section and not a footnote, because the boundary is where most of the reuse
lives. Everything above is true inside it and may be false outside it.

## The boundary

**One model, one revision, one corpus.** Every number in this paper was measured with one
quantised 4B model on llama.cpp, on one revision (`45ebb32`), on one corpus of `40` tasks. No
claim is made about other models, other corpora, other languages or real repositories
(`docs/STATUS.md:209`). The model is small by current standards; a stronger model could erase
the reliability advantage measured here or change the sign of the structure results, and neither
is tested (`docs/LEARNINGS.md:55`).

**A synthetic corpus.** The tasks are seeded bugs in small self-contained repositories,
verifying red-to-green by hand before entry (`bench/corpus/README.md:19`), plus anchors drawn
from Exercism exercises (`docs/paper-plan.md:21`). They are not real projects, and the corpus
was authored by the harness's author, which is a conflict the anchors only partly mitigate.

**One baseline, at one configuration.** The comparison arm is one mature CLI with its own knobs
maxed (`docs/STATUS.md:21`). The improved-prompt baseline arm is unmeasured
(`docs/STATUS.md:213`), so "no detected difference" is a statement about this baseline as
configured, not about free-form agents in general.

**The regression stage is unobservable here.** Each task's `repo/tests/` is the grader's suite
and the blind protocol withholds it, so the staged view usually contains no visible test file,
and "no regression" rests on the external grader's own suite (`docs/STATUS.md:202`).

**The internal verifiers are not independent.** They share the model's weights; fresh context
helps and does not make them independent (`docs/STATUS.md:188`). Adversarial code can forge the
gate's own evidence — the design is tamper-evident, not tamper-proof (`docs/STATUS.md:193`).
A weak but genuinely discriminating test passes the harness's checks without encoding the
requirement, and that class produced the residual false successes (`docs/STATUS.md:195`).
Missed success — a run that fixes the task and cannot verify it — is the strongest residual on
the quality axis (`docs/STATUS.md:198`). The review tier is measured, not proven
(`docs/STATUS.md:200`).

**Some quantities are unmeasured, and are recorded as unknown.** The baseline's token count is
partly unmeasured, because its driver carries no token counters, so its cost figure is not
recomputable from the final rows (`docs/STATUS.md:128`). Wall-clock is unclean and not
comparable across arms (`docs/STATUS.md:131`). The baseline's retained samples contain length
stops and explicit context-size errors before any code write, and the bounded audit leaves their
runtime cause unknown (`docs/STATUS.md:39`). The interval-width projection that carries
§3's argument has no committed command that re-derives it; the numbers table records
those rows as unknown with the gap named rather than filled.

## Non-conclusions

The following sentences are not in this paper, and their absence is deliberate:

- that the harness has parity with the baseline, or is "essentially equivalent" to it — the
  pre-registered test returned INCONCLUSIVE (`docs/STATUS.md:28`);
- that the harness is worse than the baseline — inferiority is not established either
  (`docs/STATUS.md:54`);
- that decomposition, field refinement or structural superiority in general is refuted — the
  negative is bundle-, corpus- and model-scoped (`docs/STATUS.md:123`);
- that tests or review are worthless — the measured effects are workflow effects with
  unresolved contrasts, not information measurements (`docs/STATUS.md:100`);
- that this harness is cheaper, in tokens or in wall-clock (`docs/STATUS.md:127`,
  `docs/STATUS.md:131`);
- that more seeds would have resolved the parity question — that is a projection from observed
  task effects, not an impossibility proof (`docs/STATUS.md:61`);
- that the goal is impossible or that the design is proven superior: the campaign ends with no
  proof of superiority and no proof of impossibility (`docs/STATUS.md:212`).

The product the research was for — one command you point at your own repository — does not
exist (`docs/ROADMAP.md:45`), so nothing here is a claim about a tool anyone can run.

## What reproduction can and cannot establish

The reproduce path proves that the analysis is arithmetic a reader can redo from committed
bytes. It does not carry why a run came out as it did: the transcript, ledger and test source of
a single run stay in the secured home, and a reader following one number back to its provenance
needs that home (`bench/analysis/wave1/NUMBERS.md:68`). A reproduction that succeeds proves the
numbers; it does not prove the interpretation, and it does not turn a bundle-scoped negative into
a general one.

There is also a failure mode specific to reproduction, and it is a boundary in its own right: a
reader who feeds the analysis a short input gets a *different experiment* rather than an error
(`bench/analysis/wave1/NUMBERS.md:75`). Section 8 states how the entry point closes that hole by
construction, and why a reproduction that reports parity after reading an empty directory is
worse than no reproduction at all (`AGENTS.md` §Current facts).
