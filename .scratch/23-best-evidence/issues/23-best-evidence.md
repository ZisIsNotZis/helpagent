# 23 — deliver the best-evidenced revision, and make the claim gates deterministic

Status: done (commits b028a28, 1d83f27, 416f1bf)
Trigger: the owner's ask to raise the TRUE PASS RATE, and a forensic analysis of the six
grader failures in the 2026-10-02 sweep.

## The forensic finding that started it

Three of the six failures ended with the required source file **byte-identical to the
pristine (broken) source**, after 5-9 attempts that each touched it. M1 (`_erase_draft`)
restores the pre-implement state on every non-novel verdict, and the harness then delivered
that erased tree. In T-05-mutable-default #1 two independent reviews quote the CORRECT fix
in the diff, the delivered file is pristine, and that exact fix passes the grader: the
harness had converted a correct fix into a failure. The other three (T-14 #2, T-31 #1/#2)
are model capability - the model never emitted the required code.

## What was built

1. **Best-evidence delivery.** The run snapshots the work tree whenever an attempt reaches
   the strongest evidence seen so far and, at completion, restores that revision before the
   produced files are collected. One documented order: agreement (own test green +
   independent verification approved) > independent verification > own test green >
   grant-calibre review, asserted in one place and used by every capture site.
2. **Unsafe restores are refused.** An own-test-tier snapshot may be restored only when the
   coverage check AT THAT REVISION found no criterion whose named artifact is untouched;
   otherwise the restore is refused and `restore_refused` is recorded with the artifact.
3. **Request-level artifact coverage (hard block on every route).** Every artifact the whole
   request names (files and symbols, deterministically resolved against the injected source)
   must be touched by the final diff; a frozen/grader-owned artifact is exempt and the
   exemption is recorded with its reason. This closed the T-31 false successes (the request
   names three call sites; the runs touched two and a review approved).
4. **A red independent verification blocks a review-backed claim.** The review still
   outranks the run's own model-written test - which is what the owner's rule was about - but
   not a fresh, independently authored, per-criterion discriminating verification. A vacuous
   or un-collected independent test does not block. This closed the T-14 #2 false success.
5. **Advisory tests and grade fidelity.** When the plan declares no tests, an incidental
   self-test cannot block a review-carried claim; an explicit negative review grade is
   preserved instead of being downgraded to `uncertain`; an uncollectable self-test is a test
   defect, not the target to iterate against.

## Measured outcome (9 tasks x 2 runs, same model)

| claim rule | actual | claimed | true | missed | honest | FALSE | calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agreement required | 14/18 | 4/18 | 4 | 10 | 4 | 0 | 156 |
| review outranks a conflicting test | 12/18 | 11/18 | 9 | 3 | 4 | 2 | 174 |
| + grant-calibre review evidence | 12/18 | 8/18 | 8 | 4 | 6 | 0 | 186 |
| + best-evidence delivery | 14/18 | 11/18 | 8 | 6 | 1 | 3 | 177 |
| + request coverage and red-IV gate (current default) | **15/18** | 8/18 | 8 | 7 | 3 | **0** | 163 |

## Residuals (honest)

- The seven missed successes are dominated by the INDEPENDENT verification being wrong on a
  correct fix (five runs), i.e. the same weak-model test-authoring problem, now in the
  independent role. That is a model-quality lever, not a rule.
- T-14 #2 and T-31 are model capability (single-file writes; no multi-site sequencing).
- The fundamental limit stands: two verifications sharing a misreading agree (DESIGN 10.8a).
- Process note: round 3 was dispatched while round 2 still edited the same files - two
  writers in one work tree. It resolved benignly (both feature sets present, suite green)
  but the discipline is one writer per worktree, verified complete before the next dispatch.
