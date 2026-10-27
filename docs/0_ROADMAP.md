# CONFIRMED

## What this node owed, and what it delivered

Two milestones, each decided by an observation rather than by a claim.

**M0 — the campaign's evidence secured and the takeover recorded.** Decided by one observation:
the campaign bytes are in a declared home inside this checkout, hashed, and re-hashing returns
every file OK and none failed — 53 270 files, 1 996 009 173 bytes, copied from `/tmp/wave1` while
that temporary path still existed. Reached; the home, the manifest and the two commands that
verify it are in `docs/9_IMPLEMENTATION.md#evidence-pointers`.

**M1 — a citable preprint whose every decisive number is recomputable from the repository
alone.** Decided by one observation: on a clean clone at the frozen tag, one command with no model
server and no network prints the decisive numbers and they equal the paper's table, and a starved
tree fails loudly. `python3 bench/checks/m1_acceptance.py` is that observation as an exit code;
it prints `m1 acceptance: OK` and exits 0. Reached and accepted above this node.

What M1 does not deliver, and does not claim, is publication. It delivered a reading form, a
reproduce entry point, a traceability table and the freeze. The push was taken above this node,
so the preprint is publicly readable; a DOI and an arXiv submission are still the person's.

## The frozen recovery line

The recovery line is not on this roadmap. It stands where a previous round left it and is
authorised to no node below root:

- **M1 recovery (harness and test workflow): BLOCKED / INCOMPLETE.** It reached P1a, whose two
  repair-and-independent-review cycles are spent. The final review found that a counterfeit
  failure heading inside captured stdout re-enables exception parsing, so printed `NameError`
  text can misclassify a genuine `AssertionError` and suppress implementation feedback. Source is
  frozen; renaming the package does not reset the cap. P1b and P2–P5 are not done; the recovery
  M1 has not passed or been delivered (`.scratch/30-harness-recovery/blocked-checkpoint.md`).
- **M2 (controlled evaluation): not authorised.** It needs the person's approval again after a
  recovery delivery.
- Order: `approval → P1 → P2 → P3 → P4 → P5 → M1 user gate → renewed approval → M2`.

Why it stays frozen: the person's rule is that a 短板 is repaired only if the paper needs it, and
the preprint needs nothing P1a touches (`docs/5_PRODUCT.md#the-paper-goes-first-unless-the-paper-needs-the-broken-tool`).
The repair cycle the person made available is therefore unspent rather than used.

## The spend

The authoring package was granted at this level: tokens against this level's model budget plus
`idle-compute` wall clock, not metered money. So no package waits on a grant. The grant covers
this node and the workers it dispatches; it does not cover a push, a DOI or a rented device.

# INFERRED

## Not on this roadmap

Deferred, with the reason each is deferred and what would reopen it:

- **A corpus or design with the power to settle R1.** The observed task effects project an
  asymptotic interval width of about `6.3` tasks, so the 40-task corpus cannot carry a decisive
  answer; a decisive test needs a corpus whose between-task heterogeneity is smaller relative to
  the effect, or a paired within-task design with the power analysis done first
  (`docs/3_REQUIREMENT.md#what-a-decisive-result-would-still-need`).
- **The product CLI, V6, and with it V5.** The command the research was for, run against an
  unseen repository that ships visible tests beside a hidden grading suite. Building it is a
  different project, and it would need its own evidence base rather than this one.
- **The measured effectiveness of the named harness fixes.** The fixes and their deterministic
  checks are recovery work; any capability or cost claim needs the separately approved M2
  evaluation.
- **An improved-prompt baseline arm.** Never measured, so "structure beats a better prompt"
  remains untested.
- **A clean single-lane wall-clock comparison.** Both arms were measured under conditions that do
  not match; a re-measurement would close a gap the paper currently names.
- **A sweep of the forced-leaf thresholds, and requirement-level splitting on a design that
  isolates splitting from planning, budget and delivery policy.**

Every one of these is a means to a claim the campaign could not settle, not a defect in what it
delivered.

## Where the order stands

M0 and M1 are reached; the paper path is the one this node took, and it is finished. Nothing in
this repository is waiting on a worker. What remains is either the person's act (a DOI, an arXiv
submission, approval of M2) or a new research programme that this roadmap deliberately does not
authorise.
