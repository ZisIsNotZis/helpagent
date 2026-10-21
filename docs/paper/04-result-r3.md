# 4. R3 — decomposition: the leaf beats both tree arms, and the scope of that negative

This is the campaign's clearest single point. The question: does planning a task as a tree of
child candidates, and delivering the winner, fix more tasks than a single monolithic leaf with
the same budget?

## The result

`210` runs: `14` tasks, `3` arms, `5` seeds, `70` runs per arm, paired by `(task, seed)`, with
the decision rule fixed before any outcome was read (`docs/STATUS.md:104`).

| arm | runs solved | claimed | false success | mean calls/task | mean wall s/run |
| --- | --- | --- | --- | --- | --- |
| monolithic leaf | `47/70` | `8/70` | `0` | `14.4` | `175` |
| tree-greedy | `14/70` | `18/70` | `4` | `31.6` | `408` |
| tree-tournament | `15/70` | `18/70` | `3` | `35.2` | `498` |

Every paired comparison points the same way, with the interval's upper bound below zero
(`docs/STATUS.md:115`):

| comparison | mean delta | 95% CI | tree-only / leaf-only fixes | McNemar p |
| --- | --- | --- | --- | --- |
| tree-greedy vs leaf, decomposable tasks | `-0.444` | `[-0.733, -0.178]` | `0` / `20` | `0.000` |
| tree-greedy vs leaf, forced-leaf tasks | `-0.520` | `[-0.920, -0.120]` | `1` / `14` | `0.001` |
| tree-tournament vs leaf, decomposable tasks | `-0.422` | `[-0.689, -0.178]` | `2` / `21` | `0.000` |
| tree-tournament vs leaf, forced-leaf tasks | `-0.520` | `[-0.800, -0.240]` | `1` / `14` | `0.001` |

The pre-registered rule returns NEGATIVE for both tree arms, because every decomposition-related
interval has an upper bound below zero (`docs/STATUS.md:122`). The tree also costs more while
fixing less: `2.2` to `2.4` times the calls, `2.3` to `2.9` times the wall clock and at least
`1.85` times the tokens, for one third of the leaf's grader passes (`docs/STATUS.md:122`).

## Did the mechanism even fire?

A negative result is only informative if the thing being tested ran. Decomposition fired in
`3/70` runs on `3/9` decomposable tasks in the greedy arm, and in `9/70` runs on `4/9`
decomposable tasks in the tournament arm (`docs/STATUS.md:122`). That establishes that
splitting sometimes happened; it does not establish causal isolation, because the arms differ
in more than splitting.

*Inference (mine, from the forced-leaf rows and the scope paragraph below):* the
`-0.520` delta on tasks where splitting is not applicable at all is consistent with a
bundle-level cost — extra calls, extra budget spent on planning, and a delivery rule that
withholds unclaimed work — rather than with a penalty specific to decomposition. This is an
inference from `docs/STATUS.md:118` and `docs/STATUS.md:123`, not an isolated measurement; the
campaign did not run the design that would separate the two.

## The scope of the negative — what this does not say

**The current tree bundle is worse here; decomposition, field refinement and structural
superiority in general are not refuted** (`docs/STATUS.md:123`). The reasons are specific and
worth reading in full, because the headline number is easy to over-read:

- the bundle changes planning and specification rewriting, budget and delivery as well as
  splitting (`docs/STATUS.md:123`);
- the tree merges only closed, claimed candidates, whereas the leaf also delivers unclaimed
  code (`docs/STATUS.md:123`), so the delivery rule alone can produce the difference;
- both tree arms delivered pristine Python source on all `52` unclaimed failures, and the leaf
  passed `39` unclaimed runs (`docs/STATUS.md:123`);
- the deleted tree candidates cannot establish how many of them were correct
  (`docs/STATUS.md:123`).

So the honest sentence is: an intervention intended to raise capability lowered it by about
two thirds of the leaf's passes on this corpus, this model and this bundle, and the experiment
does not attribute the loss to decomposition. The test that would — splitting and field
refinement isolated from planning, budget and delivery — is recorded as future work, not as
done (`docs/ROADMAP.md:88`), and the forced-leaf thresholds were never swept
(`docs/LEARNINGS.md:225`).

This is also why the paper does not call the tree "harmful" without its scope: it was harmful
*as a bundle, here*. A reader who takes "decomposition loses" away from this section has taken
away a claim the experiment does not support.

## Why this is the strongest point

The other two requirements end in a verdict that admits its own uncertainty: INCONCLUSIVE, and
partly. This one ends in a paired comparison where every interval clears zero on the same side,
the pairing removes between-task variance, the intervention was pre-registered, the mechanism's
firing was measured rather than assumed, and the cost moved opposite to the benefit. It is the
shape a negative result should have — and it is still bounded by §7.
