## Review

**P1a verdict: BLOCK.** One concrete captured-output counterexample remains in the frozen revision `dc042868…`, package diff `1983b4bc…`.

### Correct
- Non-import AST preservation rejects changed predicates, helpers, signatures and control flow **before writing** (`harness/leaf.py:3770–3786, 8379–8383`).
- Initial and replacement observations are authenticated separately; rejected observations retain the artifact and clear active evidence (`harness/leaf.py:8318–8337, 8348–8352, 8388–8391`).
- The shared setup-repair cap and green-reask integration are explicit (`harness/leaf.py:8359–8368, 8504–8507`).
- The five-line chain repair correctly clears earlier ownership at handling/direct-cause separators. Retained evidence shows two targeted pre-fix assertion failures and final green.
- Inspected final validation evidence supports the supplied 64/314/891 green results and four intended failing controls. Both resource releases are recorded. No tests or compute were launched during this review.

### Finding — P1: Captured output can re-enable exception parsing

**Location:** `harness/leaf.py:3714–3718`; consequence at `:3745–3748, :3813–3814`.

Failure-section headers are recognized **even while `captured=True`**. A header-shaped line printed inside captured stdout resets that flag, allowing subsequent printed text to establish exception ownership.

This input therefore produces test attribution despite the actual terminating exception being `AssertionError`:

```text
tests/test_generated.py:4: AssertionError: assert 0 == 42
---------------- Captured stdout call ----------------
________________ nested run ________________
tests/test_generated.py:4: NameError: printed, not raised
=========================== short test summary info ============================
```

**Static proof:** the captured marker sets `captured=True`; the underscore heading matches line 3714 and resets it to false; the printed location becomes `current`; the summary break leaves that fabricated `NameError` available to `failure_is_test_attributed`.

A valid returned-value test can encounter this output simply because the implementation prints those two lines before returning `0`. Preflight then misclassifies its behavioral failure as setup-invalid and requests test repair instead of forwarding implementation feedback. This violates cycle1’s explicit captured-output countercontrol requirement. Existing captured-output regressions omit the header-shaped line.

**Smallest fix:** make failure-section transitions capture-safe, conservatively leaving ambiguous ownership unclassified, or consume structured per-case traceback information that excludes captured output. Add this counterexample at the classifier and `run_leaf` boundaries.

### Remaining limits
- The counterexample above is source-proven, **not executed**, under the no-test restriction.
- Mechanical hashes/counts were accepted from the supplied revision-bound evidence rather than recomputed.
- Ticket29 and unrelated baseline changes were not re-reviewed.
- Import semantics, broader syntax recovery, P1b routes and real-model capability remain outside P1a acceptance.

**Merge verdict: BLOCK — P1a only; no P1/M1 completion verdict.**