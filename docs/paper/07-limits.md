# 7. Limits and non-conclusions: the external-validity boundary

This section is a section and not a footnote, because the boundary is where most of the reuse
lives. Everything above is true inside it and may be false outside it.

## The boundary

**One model, one revision, one corpus.** Every verdict number in this paper was measured with
one quantised 4B model on llama.cpp, on one revision (`45ebb32`), on one corpus of `40` tasks. Two
kinds of number sit outside that sentence and say so where they occur: the starting position in
§3 (`24/40` against `27/40`) was measured on the earlier revision `6b224f5`, and the nine rows of
§6 were measured on earlier revisions, one of them at a smaller context and not re-measured at
the final one. No
claim is made about other models, other corpora, other languages or real repositories
(`docs/2_GOAL.md#known-limits`). The model is small by current standards; a stronger model could erase
the reliability advantage measured here or change the sign of the structure results, and neither
is tested (`docs/6_ARCHITECTURE.md#harness-as-program-model-as-fallback-node`).

**A synthetic corpus.** The tasks are seeded bugs in small self-contained repositories,
verifying red-to-green by hand before entry (`bench/corpus/README.md:19`), plus anchors drawn
from Exercism exercises (`docs/9_IMPLEMENTATION.md#where-the-evidence-is`). They are not real projects, and the corpus
was authored by the harness's author, which is a conflict the anchors only partly mitigate.

**One baseline, at one configuration.** The comparison arm is one mature CLI with its own knobs
maxed (`docs/6_ARCHITECTURE.md#fair-comparison-precondition`). The improved-prompt baseline arm is unmeasured
(`docs/2_GOAL.md#known-limits`), so "no detected difference" is a statement about this baseline as
configured, not about free-form agents in general.

**The regression stage is unobservable here.** Each task's `repo/tests/` is the grader's suite
and the blind protocol withholds it, so the staged view usually contains no visible test file,
and "no regression" rests on the external grader's own suite (`docs/2_GOAL.md#known-limits`).

**The internal verifiers are not independent.** They share the model's weights; fresh context
helps and does not make them independent (`docs/2_GOAL.md#known-limits`). Adversarial code can forge the
gate's own evidence — the design is tamper-evident, not tamper-proof (`docs/2_GOAL.md#known-limits`).
A weak but genuinely discriminating test passes the harness's checks without encoding the
requirement, and that class produced the residual false successes (`docs/2_GOAL.md#known-limits`).
Missed success — a run that fixes the task and cannot verify it — is the strongest residual on
the quality axis (`docs/2_GOAL.md#known-limits`). The review tier is measured, not proven
(`docs/2_GOAL.md#known-limits`).

**The harness's own attribution of a red check is a heuristic, and no number here rests on it.**
When a check goes red, the measured revision decides from the parsed pytest failure text whether the run's own test or the source it edited is at fault, and the run writes both the test and any output that parsing can read — the heuristic is in this repository today (`harness/leaf.py:3733`) and the measured revision `45ebb32` carries it.
Nothing independent judges that decision, and in a stage contrast a routing error and a useless signal look the same.
That bounds the reading of §5 and not its numbers: solved and false success are the external grader's verdict, and the claim column is the harness's own claim compared against that verdict (§2), so the ablation's arms, costs and claim gate stand as measured — while §5's null about the own-test loop cannot be read as evidence that test feedback carries no information, because the feedback it carried was routed by this heuristic.
No repair of the heuristic is validated in this repository, so this question stays open rather than settled.

**The baseline ran under a per-turn output cap, and some of its runs ended on it.** The baseline
is driven with its per-turn output capped at `8192` tokens, a quarter of the server's window, so
that the rest of the window stays available to the tool transcript (`bench/pi_baseline.py:71`).
The bounded audit found baseline samples that stopped at that cap or reported the context size
exceeded before any code write, while the driver-level counters record no timeout
(`docs/2_GOAL.md#r1-capability-parity`). "No crashes and no timeouts" therefore does not mean every baseline
inference completed: how many of its failed runs this cost is unrecorded, and the parity number
does not exclude a baseline loss from it.

**The remaining false successes are on the plain green path.** At the end of the campaign they
come from runs whose own test was green, whose independent test was green and whose review
approved, and which the grader then failed; the rules that close the review route are not fully
applied to that green route (`docs/2_GOAL.md#known-limits`). Two of the campaign's stated goals are
therefore not met as written: zero false successes was not reached (`2.2`% in the head-to-head, and the full
ablation arm still produced a false success), and not every final failure has a deviation-point explanation
(`docs/2_GOAL.md#r2-verification-information`). "A claim gate buys honesty" means it made lying measurable, not that it
removed it.

**Some quantities are unmeasured, and are recorded as unknown.** The baseline's token count is
partly unmeasured, because its driver carries no token counters, so its cost figure is not
recomputable from the final rows (`docs/8_DETAIL.md#cost`). Wall-clock is unclean and not
comparable across arms (`docs/8_DETAIL.md#cost`). Every quantity that carries §3's argument now
re-derives (`python3 reproduce.py`); the baseline's token count, the wall-clock subset and the
size of the truncation above do not, and the numbers table records each as unknown with its gap
named.

## Non-conclusions

The following sentences are not in this paper, and their absence is deliberate:

- that the harness has parity with the baseline, or is "essentially equivalent" to it — the
  pre-registered test returned INCONCLUSIVE (`docs/2_GOAL.md#the-three-requirements-and-their-verdicts`);
- that the harness is worse than the baseline — inferiority is not established either
  (`docs/2_GOAL.md#r1-capability-parity`);
- that decomposition, field refinement or structural superiority in general is refuted — the
  negative is bundle-, corpus- and model-scoped (`docs/2_GOAL.md#r3-decomposition-and-multi-approach`);
- that tests or review are worthless — the measured effects are workflow effects with
  unresolved contrasts, not information measurements (`docs/2_GOAL.md#r2-verification-information`);
- that this harness is cheaper, in tokens or in wall-clock (`docs/8_DETAIL.md#cost`,
  `docs/8_DETAIL.md#cost`);
- that more seeds would have resolved the parity question — that is a projection from observed
  task effects, not an impossibility proof (`docs/2_GOAL.md#r1-capability-parity`);
- that the goal is impossible or that the design is proven superior: the campaign ends with no
  proof of superiority and no proof of impossibility (`docs/2_GOAL.md#known-limits`).

The product the research was for — one command you point at your own repository — does not
exist (`docs/2_GOAL.md#the-campaign-slices-and-their-verdicts`), so nothing here is a claim about a tool anyone can run.

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
worse than no reproduction at all (`docs/7_INTERFACE.md#entry-point-contract).
