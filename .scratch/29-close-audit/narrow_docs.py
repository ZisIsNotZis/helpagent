"""One-off documented semantic corrections for ticket 29; no measurement changes."""
from pathlib import Path


def replace(path, pairs):
    p = Path(path)
    s = p.read_text()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old, s.count(old))
        s = s.replace(old, new)
    p.write_text(s)


replace('README.md', [
('**Status: completed / archived research.** This is not a shipped product.', '**Status: campaign completed / research archived.** The three goals remain unmet or unresolved, not disproved. This is not a shipped product.'),
('The CI width is a structural limit of the 40-task corpus (flat from N=17 to N=25), so more seeds cannot resolve it.', 'The CI width was flat from N=17 to N=25; at the observed task heterogeneity and point estimate, further seeds alone are not projected to resolve it.'),
('The own test alone is zero-information (`−1.33` tasks, p=0.55). The independent test does not significantly change correctness but cuts claims (`−8.67`, p=0.0009) and false successes (`−3.00`, p=0.031). Review adds the only significant correctness gain, and only on top of own test + independent test (`+4.00`, p=0.012); review alone adds false successes (`+3.33`, p=0.031).', 'Enabling the own-test loop did not detect a net correctness gain (`−1.33` tasks, CI `[−5.67, +3.00]`, p=0.55), not proof of zero information. The independent-test contrasts did not detect a correctness effect but reduced claims (`−8.67`, p=0.0009) and false successes (`−3.00`, p=0.031) with review present. The review contrast with independent test present gained `+4.00` (p=0.012); without it, false successes increased (`+3.33`, p=0.031). This does not establish an interaction.'),
('The mechanism verifiably fired, and the tree cost roughly 2 to 3x for far fewer fixes.', 'The current tree bundle cost roughly 2 to 3x for far fewer fixes. Planning, budget and closed-only delivery also changed; splitting and field refinement were not isolated.'),
('and does not tighten\n  with more seeds. Not proven stronger; not proven worse.', 'was flat over N=17..25. Further-seed projections assume the observed task effects persist; this is not an impossibility result. Not proven stronger; not proven worse.'),
('- **Decomposition / step-splitting / multi-approach**: harmful (section above).', '- **The measured tree / multi-approach bundle**: harmful here (section above); this does not isolate decomposition or field refinement.'),
('The pattern: structure that costs calls without adding information loses. What moved the\nnumbers was giving the model more signal, not more control flow.', 'These implementations spent extra calls without a measured net capability gain. That is a scoped outcome, not evidence that control flow or decomposition cannot help.'),
('## Future research', 'The campaign is closed as a resource decision, not as proof that the goals are impossible. The bounded final-revision failure audit and its evidence limits are in [ticket 29](.scratch/29-close-audit/report.md).\n\n## Future research'),
])
replace('docs/STATUS.md', [
('**complete and archived**: the campaign that the owner mandated (match or beat a mature\nagent CLI on the same model, without lying, with verification that carries information)\nhas run to its pre-registered end and reported its verdicts. The product CLI does not\nexist.', '**campaign complete and research archived**: the campaign has run to its pre-registered end and reported its verdicts. The goals (match or beat a mature agent CLI on the same model, without lying, with verification that carries information) remain unmet or unresolved, not disproved. The product CLI does not exist.'),
('the CI width is structural, so more seeds cannot resolve it.', 'the CI width was flat over N=17..25, so further seeds alone are not projected to resolve it at the observed task effects.'),
('own test `−1.33` tasks (p=0.55, zero-information); independent test neutral on correctness, `−8.67` claims (p=0.0009) and `−3.00` false successes (p=0.031); review `+4.00` correctness (p=0.012) only on top of own test + independent test, and `+3.33` false successes (p=0.031) on its own.', 'own-test loop `−1.33` tasks (CI `[−5.67, +3.00]`, p=0.55), net correctness effect unresolved; independent-test correctness effects unresolved, `−8.67` claims (p=0.0009) and `−3.00` false successes (p=0.031) with review present; review `+4.00` correctness (p=0.012) with independent test present, and `+3.33` false successes (p=0.031) without it; interaction not established.'),
('p<0.001; the mechanism verifiably fired.', 'p<0.001; negative for the current tree bundle, not isolated decomposition or field refinement.'),
('**Why N=25 did not resolve it (structural, not a lucky draw).**', '**Why N=25 did not resolve it (projection from observed task effects).**'),
('`~6.3`-task floor at infinite seeds. The rule would need the point estimate to move to\nabout `+0.3` tasks, or a different or larger task set, to return ACHIEVED.', '`~6.3`-task asymptotic width projected from the observed effects. At that width the rule would need the point estimate to move to about `+0.3` tasks, or a different or larger task set, to return ACHIEVED. This is not proof that more seeds cannot change the estimate, nor that the capability goal is impossible.'),
('Paired incremental contributions (one stage isolated per contrast, 40 tasks, 95%\npercentile bootstrap, seed `20261013`):', 'Paired stage-enable contrasts (net workflow effects, 40 tasks, 95% percentile bootstrap, seed `20261013`); enabling a stage also changes feedback, iteration, stopping and delivery, so this does not isolate the information in a test or review:'),
('| contrast | stage isolated |', '| contrast | stage enabled |'),
('''- **The own test is zero-information on correctness.** The point estimate is negative, the
  CI spans 0, and the self-test never carried a claim in any of the 600 runs
  (`claimed_basis` is always review and/or independent test). It costs about 7x the tokens
  and 6.6x the wall time of development-only.
- **The independent test is a false-claim suppressor, not a correctness lever.** On actual
  correctness it is indistinguishable from zero, but it cuts claims (`−8.67`, p=0.0009) and
  false successes (`−3.00 [−5.67, −1.00]`, p=0.031). It is conservative: in the full arm
  it withheld approval in `92/110` runs, `57` of which the grader passed.
- **Review buys correctness only when backstopped.** Added to the own test alone, review
  gives no significant correctness change while producing `+18.00` claims and `+3.33`
  false successes. Added on top of own test + independent test, it is the **only
  significant correctness gain in the ladder** (`+4.00 [ +1.33, +7.00]`, p=0.012).
- **The requirement as stated is not supported.** Not every stage carries
  positive information: the own test is zero-information, and review alone is negative
  information (it raises false successes). The full stack is net-positive in point estimate
  (`+2.33` tasks `[−0.33, +5.33]`, p=0.34, not significant); the only significant
  correctness gain is review on top of own test + independent test. The stages are not
  interchangeable.''', '''- **No net correctness gain was detected from enabling the own-test loop.** Its CI `[−5.67, +3.00]` includes losses and gains; this is not proof of zero information or equivalence. Own tests never directly carried a claim, but can change code and block later claims. The loop costs about 7x the tokens and 6.6x the wall time of development-only.
- **The independent-test contrasts leave correctness unresolved and reduce false claims with review present.** Claims fall (`−8.67`, p=0.0009) and false successes fall (`−3.00 [−5.67, −1.00]`, p=0.031). In the full arm it withheld approval in `92/110` runs, `57` of which the final grader passed; that join is not an independent diagnostic-accuracy experiment.
- **Review has a positive correctness contrast with independent test present.** `A4−A2` is `+4.00 [+1.33, +7.00]`, p=0.012. Without independent test, `A3−A1` has no detected correctness effect and increases false successes by `+3.33`. A significant contrast beside a nonsignificant one does not establish that their difference (the interaction) is significant.
- **The requirement remains not met as stated.** The net full-stack gain is unresolved (`+2.33 [−0.33, +5.33]`, p=0.34), not every final failure has a deviation-point explanation, and the final R2 A-05#1 shows independent test and review jointly approving wrong answers. These workflow measurements do not measure information content. Small N, unmatched stage costs and multiple unadjusted contrasts limit interpretation; see the measurement record and [bounded final-revision audit](../.scratch/29-close-audit/report.md).'''),
('''The pre-registered rule fires NEGATIVE for both tree arms (every decomp-related CI upper
bound is below 0). The mechanism verifiably fired, so this is a valid negative and not an
unfired-mechanism artefact: decomposition ran in `3/70` runs on `3/9` decomposable tasks
(B1) and `9/70` runs on `4/9` tasks (B2). The tree cost `2.2` to `2.4x` the calls, `2.3` to
`2.9x` the wall and at least `1.85x` the tokens, for one third of the leaf's grader passes.
The correct wording is: **structural superiority is refuted on this corpus; the monolithic
leaf matches or beats the tree at a fraction of the cost.**''', '''The pre-registered rule returns NEGATIVE for both current tree arms (every decomp-related CI upper bound is below 0). Decomposition ran in `3/70` runs on `3/9` decomposable tasks (B1) and `9/70` runs on `4/9` tasks (B2); this establishes that it sometimes fired, not causal isolation. The tree cost `2.2` to `2.4x` the calls, `2.3` to `2.9x` the wall and at least `1.85x` the tokens, for one third of the leaf's grader passes.
**The current tree bundle is worse here; decomposition, field refinement and structural superiority in general are not refuted.** It changes planning/spec rewriting, budget and delivery as well as splitting: tree merges only closed, claimed candidates, whereas leaf also delivers unclaimed code. Both tree arms delivered pristine Python source on all 52 unclaimed failures; leaf passed 39 unclaimed runs. The deleted tree candidates cannot establish how many were correct. See [ticket 29](../.scratch/29-close-audit/report.md) for code/byte evidence and limits.'''),
('| decomposition / step-splitting / multi-approach | harmful (R3 above) |', '| current tree / multi-approach bundle | harmful here; splitting and field refinement not isolated (R3 above) |'),
('The pattern: structure that costs calls without adding information loses.', 'These implementations spent extra calls without a measured net capability gain; this does not show that structure in general cannot help.'),
])
replace('docs/LEARNINGS.md', [
('advantage.** The value of the project is the design principle it validated, the', 'advantage.** This closes the measured campaign, not the goals or their feasibility. The value of the project is the design principle it exercised, the'),
('not shown to beat a good free-form loop on capability, and a stronger model would likely\nerase most of the reliability gap (section 7).', 'not shown to beat a good free-form loop on capability. Whether a stronger model would erase the reliability gap is an untested hypothesis, not a measured result.'),
('Paired incremental contributions (one stage isolated per contrast, 40 tasks):', 'Paired stage-enable contrasts (40 tasks): net workflow effects, including changed feedback, iteration, stopping and delivery; not isolated measurements of signal information.'),
('the only significant correctness gain, and only **on top of** own test + independent test:', 'a significant correctness gain **with** own test + independent test present:'),
('''1. **A check that shares the generator of the thing it checks is not independent
   evidence.** The own test is written by the same model that writes the code; measured,
   it is zero-information on correctness (`−1.33`, p=0.55). The independent test is
   written by the same model in a fresh context; on correctness it is also
   indistinguishable from zero. When the model keeps a wrong reading, its code, its own
   test, its independent test and its reviewer all inherit that reading, so agreement
   between them proves nothing. The external grader is the only correctness arbiter.

2. **Each verification stage has a different, measurable job, and they are not
   interchangeable.** The independent test is a **false-claim suppressor** (it buys
   honesty, not fixes), and it is a conservative one: in the full arm it withheld approval
   in `92/110` runs, `57` of which the grader passed. The review is a **correctness** lever
   only when it is backstopped by an independent test; alone it mostly produces confident
   wrong claims (`+3.33` false successes). The own test is a cost centre with no measured
   correctness benefit here. A pipeline should assign these roles deliberately instead of
   treating "more verification" as strictly better.''', '''1. **Fresh context does not remove shared-model error.** No net correctness gain was detected from the own-test loop (`−1.33 [−5.67, +3.00]`, p=0.55); independent-test correctness contrasts are also unresolved. Neither establishes zero information. A shared wrong reading can survive code, own test, independent test and review; final R2 A-05#1 is a direct example. Agreement is not proof of correctness; the external grader remains this experiment's arbiter.

2. **Measure the workflow effect without assigning universal stage roles.** With review present, enabling independent test reduced false successes (`−3.00 [−5.67, −1.00]`, p=0.031). In the full arm it withheld approval in `92/110` runs, `57` of which the final grader passed; this is a stage/final-outcome join, not independent diagnostic accuracy. Review's correctness contrast is positive with independent test present (`+4.00`, p=0.012); without it, false successes rise (`+3.33`) and correctness is unresolved. This does not establish an interaction or that review works only when backstopped. Own tests can change code and block claims without directly carrying a claim. Stage costs are unmatched and contrasts unadjusted for multiplicity; do not equate net outcome with signal information.'''),
('''- **The decision rule can be structurally unable to resolve.** At N=25 the CI width was
  flat (range `6.44`–`6.60`; `6.53` at N=17, `6.60` at N=25) because it is set by between-task
  heterogeneity in the 40-task corpus, not by seed noise; more seeds cannot close the
  0.52-task gap to the margin. The lesson is to compute the resolvable effect size from
  the corpus before promising a decisive answer, and to say "the test cannot resolve this"
  rather than "more data needed".''', '''- **Separate a statistical projection from impossibility.** At N=25 the CI width was flat (range `6.44`–`6.60`; `6.53` at N=17, `6.60` at N=25), dominated by between-task heterogeneity. At the observed task effects, more seeds alone are not projected to close the 0.52-task gap; future estimates can still move. Compute the resolvable effect size before promising a decisive answer, and distinguish the campaign's inconclusive stopping result from the capability goal's feasibility.'''),
('''wisdom "write tests, review the change" is not uniformly true here: the model's own test
is worthless, and review without an independent test manufactures confident errors. The
process is worth codifying, but each stage must earn its place by measurement, not by
analogy to a human team.''', '''wisdom "write tests, review the change" does not by itself establish benefit here: the own-test loop has no detected net correctness gain, and enabling review without independent test increases false successes. These are workflow effects, not proof that tests are worthless or review signals inherently negative. Each implementation must earn its place by measurement, not analogy to a human team.'''),
('| decomposition / step-splitting / multi-approach (tree of children; a tournament of Hows) | **harmful.**', '| current tree / multi-approach bundle (tree of children; a tournament of Hows) | **harmful here.**'),
('The mechanism verifiably fired (decomposition on 3 of 9 decomposable tasks in one arm, 4 of 9 in the other), so this is a valid negative, not an unfired mechanism.', 'Decomposition fired on 3 of 9 decomposable tasks in one arm, 4 of 9 in the other. Planning/spec rewriting, budget and closed-only delivery also differ; this is not an isolated test of splitting or field refinement (STATUS.md §5).'),
('''The pattern across all of them: **structure that costs calls without adding information
loses.** What moved the numbers was giving the model more signal (a forced red-then-green
loop, deterministic diagnosis rules, coverage and discrimination checks), not more
elaborate control flow.''', '''These implementations added calls without a measured net capability gain. Historical delivery/attribution defects demonstrate that control flow can also lose already generated capability; no isolated experiment here establishes that all structural changes lose or that only added signal helps.'''),
('''- **The decomposition result is corpus- and model-scoped.** The negative is strong on "the
  tree stage does not pay for itself here"; it bounds, but does not prove, "requirement-
  level splitting can never help" (the planner only split on a minority of tasks). The
  forced-leaf thresholds were never swept.''', '''- **The tree result is bundle-, corpus- and model-scoped.** This tree stage does not pay for itself here. It does not isolate decomposition or field refinement from planning/spec changes, budget and closed-only delivery, even where splitting fired. The forced-leaf thresholds were never swept; structural superiority in general remains unshown, not refuted.'''),
('''1. **A larger or differently shaped corpus.** The 40-task corpus structurally caps the
   resolvable difference at about 6.3 tasks even at infinite seeds. A decisive''', '''1. **A larger or differently shaped corpus.** At the observed task effects, the 40-task corpus projects an asymptotic CI width of about 6.3 tasks, not a capability ceiling. A decisive'''),
('that isolates splitting from planning overhead.', 'that isolates splitting and field refinement from planning/spec rewriting, budget and delivery policy.'),
('- Design and flow:', '- Bounded final-revision causal audit, retained samples and evidence limits: [ticket 29](../.scratch/29-close-audit/report.md).\n- Design and flow:'),
])
replace('docs/ROADMAP.md', [
('''prints**, so every slice below is something you can run and look at. A slice is done when
you can see it, not when the code for it exists. The project is now **complete and
archived**: the slices and the acceptance criteria have final verdicts, recorded here.''', '''prints**, so every slice below is something you can run and look at. A slice is done when you can see it, not when the code for it exists. The measured campaign is **complete and the research archived**; its verdicts are recorded here. The goals and acceptance criteria below are unchanged: unmet or unresolved is not disproved or impossible.'''),
('the own test is zero-information (`−1.33`, p=0.55) and review alone raises false successes (`+3.33`, p=0.031); only the review + independent-test combination carries a significant correctness gain (`+4.00`, p=0.012).', 'the own-test loop has no detected net correctness gain (`−1.33 [−5.67, +3.00]`, p=0.55), not proven zero information; review without independent test raises false successes (`+3.33`, p=0.031), while with independent test its correctness contrast is positive (`+4.00`, p=0.012); interaction not established and final failures not fully traced.'),
('**REFUTED / not shown** | decomposition / multi-approach is NEGATIVE', '**NOT SHOWN** | the current tree bundle is NEGATIVE; splitting and field refinement were not isolated from planning, budget and delivery policy'),
('are recorded and independently recomputed from the raw rows.', 'are recorded and their numerical results independently recomputed from the raw rows; that recomputation does not validate causal interpretations.'),
('''- A corpus large enough to resolve the parity question (the 40-task corpus caps the CI at
  about `6.3` tasks even at infinite seeds).''', '''- A corpus/design with sufficient power for the parity question (the observed task effects project an asymptotic CI width of about `6.3` tasks; this is not an impossibility result).'''),
('design that isolates splitting from planning overhead.', 'design that isolates splitting and field refinement from planning/spec rewriting, budget and delivery policy.'),
('## What is explicitly deferred as future research', 'The bounded final-revision explanations in [ticket 29](../.scratch/29-close-audit/report.md) do not close C3: missing records and ungraded intermediate candidates remain explicitly unknown.\n\n## What is explicitly deferred as future research'),
])
