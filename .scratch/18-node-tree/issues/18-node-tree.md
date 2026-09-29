# 18 — node tree: budgeted decomposition over the working leaf

Status: planned (implementation starts only after the running measurement finishes)
Depends on: ticket 17 (the leaf loop, suite 296 green at commit 327b923)
Need-review: yes (independent adversarial verifier lane)
Need-test-cases: yes (the 12 pinned cases in the design note below)

## Objective

Turn one working leaf (actual 5/8 blind, 0 false success, ~48 calls) into a budgeted
tree: requirement triage -> per-node decompose+specify -> leaves -> integration, with
L6 re-split and L7 parent-spec-correction. `run_leaf` and `Budget`'s existing methods
stay unchanged; the tree calls the leaf verbatim.

## Source of truth

The full design is in the design lane's artifact. Copy it here when implementing:
`.scratch/18-node-tree/design.md` (to be written from the lane output verbatim, so the
implementer and the verifier read the same contract).

## Supervisor decisions on the design's open items

1. **New `PlanNode` fused envelope: YES (one call per node is an owner requirement).**
   `SCHEMAS` goes 23 -> 24; update the pinning test AND `docs/ENVELOPE_SCHEMAS.md` +
   `docs/KERNEL_API.md` in the same commit. This is an additive contract extension,
   deliberate and documented, never a silent drift.
2. **Weighted split: YES** (`Budget.split_weighted(weights, min_each)`), with the
   deterministic rule that if any child's share < `MIN_LEAF_CALLS` the smallest
   children are merged (union boundary) or the node is forced to a leaf. Equal
   `Budget.split` stays for other callers.
3. **Wall-clock: shared, never hard-split per child** (soft slice as an ordering hint
   only, off by default).
4. **`MIN_LEAF_CALLS` = 5 when judge+iv are on, 3 otherwise**, a `run_tree` parameter.
5. **Integration work always lives in a dedicated integration LEAF** (so red-on-arrival,
   the independent test and the report gate apply unchanged); internal nodes hold only
   the reference AC map and may never close without a machine-verified integration verdict.
6. **Checkpoints are per-node git commits inside the harness-owned workdir**, with every
   discarded SHA ledger-recorded before `reset --hard`; the user's repo is never touched.
7. **Grader paths are injected from the ROOT only** (`leaf_spec_from` always uses the
   root's set), never from child output.

## Deliverables

- `harness/node.py` (PlanNode envelope, `Decomposition`, `validate_decomposition`,
  `can_decompose`, `split_weighted`), `harness/tree_run.py` (`run_tree`/`run_node`,
  `leaf_spec_from`, `integration_verdicts`, L6/L7), `Trajectory.checkpoint`/`reset_to`.
- The 12 pinned tests from the design (sibling disjointness incl. canonicalization
  evasion; budget-1 cannot split; reserve/release conservation; internal close needs a
  passing integration verdict; root grader paths inherited; spec bubble -> L7 + subtree
  reset; exhausted -> L6; identical re-split refused as wasted; subtree reset leaves
  siblings untouched; deadline stops the tree and keeps checkpoints; the tree calls
  `run_leaf` unchanged).
- A blind end-to-end demonstration on a task that genuinely needs decomposition.

## Non-goals

Parallel writers (serialize first), the knowledge service, and any change to the leaf
loop's claim policy.
