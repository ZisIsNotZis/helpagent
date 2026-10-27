# Unhomed

Facts that deserve filing and have no home yet. Nothing here is a decision; each line leaves the
moment it lands in a level document.

## The person's, not this node's

- A DOI deposit and an arXiv submission. The repository is public and the preprint says so on its
  face; a DOI or a second public surface is a `cost` act above this node, and this node takes no
  further publication step (`docs/5_PRODUCT.md#published-and-what-is-owed-to-the-person`).

## Gaps in an existing check

- `bench/checks/m1_acceptance.py` runs at the frozen tag `preprint-v1`, so it proves the acceptance
  revision and says nothing about `HEAD`. A later edit to the paper could regress the current tree
  with that check still green. The tag is a parameter, so `python3 bench/checks/m1_acceptance.py
  master` checks the tip; whether the default should follow the branch rather than the tag is
  undecided, and the tag is what a reader reproduces.
- R2's `analysis.json` is compared parsed rather than byte-wise, because its `stop_reasons` ties
  depend on set-iteration order. Closing that gap means giving the analyzer a stable order, which
  changes a measured artifact; not attempted (`docs/8_DETAIL.md#two-limits-recorded-rather-than-smoothed`).

## Unmeasured, and worth knowing

- `pi`'s token counters: its driver carries none, so the `~9k` tokens/task comes from the recorded
  reference and cannot be recomputed from the final rows. A token-counted baseline run would close
  it, and the roadmap carries that as deferred research (`docs/0_ROADMAP.md#not-on-this-roadmap`).
