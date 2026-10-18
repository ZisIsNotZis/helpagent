## Review

**Static checkpoint only.** Reviewed the incremental `package.diff`, named contracts/ledger, scoped code/tests, and required gate dependencies. Ticket29 was not re-reviewed. No writes, tests, model calls, process launches, or subdelegation.

### Correct
- Ordinary assertion-only tracebacks no longer automatically establish test blame; the revised regression includes assertion and source-NameError countercontrols (`harness/leaf.py:3709–3716`; `tests/unit/test_v2_leaf.py:7670–7685`).
- Setup repair has a shared one-attempt cap, uses the existing test path, and re-runs the replacement before ordinary source iteration (`harness/leaf.py:8238–8274`). Known unrepaired setup faults clear active evidence and stop without source attempts (`:8282–8292`).
- `record_gate` now clears `last_gate` when the current result lacks a report, closing the specific stale-report retention mechanism (`harness/leaf.py:6948–6952`).
- The regressions use real pytest/JUnit behavior with a scripted model, rather than merely fabricating successful classification (`tests/unit/test_own_test_setup.py:72–104`).

### Findings

**P1 — Exception-name text inside an ordinary assertion is misclassified as setup failure.**  
**Location:** `harness/leaf.py:3709–3716, 3733–3737`.

The classifier searches for `NameError:` anywhere in the combined output, independently of the exception actually terminating the traceback. For example, this failure text satisfies every condition:

```text
tests/test_generated.py:4: AssertionError: NameError: unexpected result
```

A legitimate check such as `assert result() == 42, "NameError: unexpected result"` therefore enters setup repair despite having evaluated the implementation. The new preflight makes this consequential before any source attempt; an unchanged repair then stops the run rather than addressing the behavior defect.

**Smallest fix:** Establish the actual exception type and its associated failing traceback, rather than matching exception-name text anywhere in output. Add an assertion-message/captured-output countercontrol that must remain implementation feedback.

**P1 — Setup repair can replace or weaken behavioral checks without detection.**  
**Location:** `harness/leaf.py:8265–8279`.

Acceptance checks only status, nonempty changed content, successful write, and absence of another recognized setup fault. The instruction to preserve assertions is not enforced. Starting from the missing-import fixture, a repair can both add the import and change `assert result() == 42` to `assert result() >= 42`. On pristine `return 0`, that replacement still produces a behavioral red and proceeds as the discriminator.

This is narrower than proving semantic oracle correctness: the newly introduced setup-only operation can silently change an existing oracle, contrary to its own repair instruction.

**Smallest fix:** Reject or separately adjudicate changes to existing behavioral checks during setup-only repair. For parseable originals, preserve their assertion predicates/check structure mechanically; explicitly handle cases where preservation cannot be established. Add a still-red weakened/changed-assertion regression—the current green-repair case does not catch this (`tests/unit/test_own_test_setup.py:171–180`).

**P1 — Re-observation conflates “no setup fault detected” with “trustworthy replacement observed.”**  
**Location:** `harness/leaf.py:8273–8279`; downstream `:8401–8409, 8449–8477`.

`_own_test_setup_problem` returns an empty classification for missing, unobserved, or structurally anomalous reports (`:3724–3726`). The repair helper treats that empty result as sufficient to return the replacement.

Two concrete consequences follow:

- With the existing missing-report fixture (`tests/unit/test_own_test_setup.py:151–168`), the replacement is returned and subsequently deleted by the legacy collection fallback at `harness/leaf.py:8462`, violating the checkpoint’s inspectable-artifact retention requirement. The regression does not assert retention.
- A replacement report with `observed=True`, `anomaly="canary-missing"`, and an own-test failed ID bypasses the outer unobserved check. Collectibility and partitioning can then accept its failed ID and enter source iteration despite structural distrust.

**Smallest fix:** Distinguish an authenticated re-observation from an unclassifiable result. Missing/unobserved/structurally anomalous repair observations should stop uncertain, retain the artifact, and clear active evidence. Extend the current missing-report test and add an observed-but-structurally-untrusted report countercontrol.

### Targeted missing proof
After explicit resource admission:
- Run the new suite, affected leaf suite, and configured project gate recorded in `commands.md`.
- Execute both planned negative controls and retain actual failing output.
- Add and exercise the three counterexamples above.
- Cover setup failure introduced by the green re-ask, shared repair-cap exhaustion, no remaining calls/deadline, and unusable repair status/path handling.

All behavioral tests and negative controls remain **unverified**, not PASS.

### Merge verdict: BLOCK
The three P1 findings require repair and revision-bound proof before P1a acceptance. This is not a package-completion or M1-completion verdict.