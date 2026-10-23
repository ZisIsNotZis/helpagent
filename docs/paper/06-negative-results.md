# 6. Negative results and retractions as method

A campaign that reports only what worked wastes the expensive half of its evidence. This
section treats the losing designs and the killed claims as first-class results, because they are
what a reader with the same idea needs most: a place where a plausible design already lost, and
the reason a confident headline was withdrawn.

## Nine designs that lost here

| idea | measured result | source |
| --- | --- | --- |
| a bounded source index: declared files in full, the rest as an index | harmful, `13/24` against `18/24` on the same tasks, and `13/24` against `19/24` against the pre-change revision | `docs/STATUS.md:181` |
| forcing a deterministic file-change order | harmful, `14/15` against `7/15` | `docs/STATUS.md:178` |
| injecting a knowledge pack (signatures, callers, constants) on every call | no gain, `4/15` against `3/15`, off by default | `docs/STATUS.md:176` |
| putting module importers into the write specification | no gain, `10/15` against `10/15` | `docs/STATUS.md:177` |
| extending the write boundary on rule evidence | no gain, `1/5` against `1/5` | `docs/STATUS.md:179` |
| competitive exploration of several approaches (a tournament of candidates) | fires, costs `2.2` to `2.4` times the calls, fixes fewer tasks: `15/70` against `47/70` | `docs/STATUS.md:180` |
| asking the mature CLI to write and run its own tests | worse at a small context, `16/40` against `21/40`; not re-measured at the final context | `docs/STATUS.md:182` |
| delivering the last revision the run wrote, rather than the best one it verified | harness-side loss: a grader-passing revision discarded and a failing one delivered | `docs/STATUS.md:67` |
| extending verification without matching its cost | the harness is roughly twice as expensive as the baseline for no measured capability gain | `docs/STATUS.md:127` |

Every row is a case where an implementation spent extra calls without a measured net capability
gain. What they jointly show is bounded: they do not show that structure in general cannot help
(`docs/STATUS.md:184`), and the delivery case shows the opposite direction is possible — control
flow can also *destroy* capability the model already produced (`docs/LEARNINGS.md:145`).

Two of these rows are the ones a future project is most likely to repeat, so they are worth
stating as advice rather than as data. A source index that hides source from the model lost, and
source is no longer hidden (`docs/LEARNINGS.md:183`). A tournament of candidates looks like more
exploration and measured as more cost with fewer fixes, which is why greedy is the default
(`docs/STATUS.md:167`).

## Three retractions

A retraction is a claim that died with a reason, and the record keeps the reason rather than the
claim: the row's status word is 已撤回 — retracted — and its reason for the first row is 未复现,
"did not reproduce" (`FINDINGS.md:47`).

| withdrawn claim | why it died | source |
| --- | --- | --- |
| a token-saving headline of `-31.3%` | it did not reproduce | `docs/STATUS.md:136` |
| the implicit claim that the harness is cheaper, on wall-clock grounds | the two arms were measured under different concurrency, so the readings are not comparable; the only indicative subset is a small single-lane run | `docs/STATUS.md:131` |
| an earlier maturity comparison that judged the baseline weaker | that comparison clamped the baseline itself (thinking off, small context); re-measured under the fair precondition it was worse for the harness | `docs/LEARNINGS.md:147` |

The third is the instructive one. The error was not arithmetic; it was a comparison condition
that quietly favoured the harness, which is exactly hazard 2 of §1. The retraction is
what makes the corrected result credible: the campaign that published the favourable reading is
the campaign that published its removal.

## Why this is a contribution and not an appendix

Three properties make the record reusable rather than confessional.

1. **Each negative names the design, not just the failure.** "A bounded source index was
   harmful, `13/24` against `18/24`" tells the next project what not to build; "the model was
   weak" tells them nothing.
2. **Each negative carries its cost.** The tournament row is not merely worse, it is worse while
   costing `2.2` to `2.4` times the calls (`docs/STATUS.md:180`), which is the part that changes
   a design decision.
3. **Each retraction survives as a rule.** The wall-clock retraction is why this paper says no
   wall-clock win is claimed anywhere (§5); the maturity retraction is why the fair
   precondition is a precondition and not a courtesy (§2).

The corpus of negatives also bounds the positive results. When the strongest point of the paper
is that a bundle lost (§4), the reader can see that the same campaign recorded nine designs
that lost or gained nothing, one of them the tree bundle of §4 and still declined to generalise from them (`docs/STATUS.md:184`). The discipline
is uniform: measure, bound the conclusion, keep the row.
