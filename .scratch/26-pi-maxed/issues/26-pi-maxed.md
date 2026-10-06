# 26 — the maxed-config pi arm (the fairness correction), and the independent-test inversion

Status: measurement done (commits a058ae0, 5697e27); one owner decision open (see end)
Trigger: the owner asked — "when we ran pi bare, were ALL tools on? was the request clear?
and crucially, how was its thinking length set — none, max, or what? If we pull every knob
to the max, same 4B, does it change the answer?"

## What was actually configured in the recorded baseline (commit `ef13a14`)

| knob | recorded | verdict |
| --- | --- | --- |
| tools | no `--tools` flag => pi's full default tool set | fair |
| prompt | `PI_PROMPT` + the task's `request.md` verbatim, including "verify your work" | fair |
| `--thinking` | **`off`** | not fair |
| reasoning support | **not declared** in the temp model entry, so pi advertises only `["off"]` (`docs/rpc-commands.md`) — **`--thinking max` would have been silently clamped too** | not fair |
| server context | **`-c 8192`** — and 9 of 10 runs in the recorded ask-tests tail band died on a length-truncated thinking block | not fair |

The owner's suspicion was correct: two ceilings of OUR making were throttling the mature CLI.

## The correction

`bench/pi_baseline.py` gained `--reasoning` (default off, so the recorded arms stay
reproducible). It writes a temp model entry declaring `reasoning: true` with the server's real
`contextWindow: 32768` and `maxTokens: 8192`; the server was restarted at `-c 32768` with
quantised KV cache. 40 tasks, N=1, same grader, same blind staging:

| band | recorded (thinking≈off, 8k) | maxed (thinking max, 32k) |
| --- | --- | --- |
| T-01..T-10 | 9/10 | 10/10 |
| T-11..T-20 | 7/10 | 9/10 |
| T-21..T-30 | 5/10 | 7/10 |
| T-31..T-35 | 0/5 | 1/5 (T-31) |
| A-01..A-05 | 0/5 | 0/5 |
| total | 21/40 (52%), 4 false | **27/40 (68%), 2 false** |

Evidence: `bench/runs/evidence/pi-maxed-20261006/`, guarded by
`tests/unit/test_pi_maxed_evidence.py`.

**Retracted:** "development capability is a tie" and "the hard tail is a model-capability
boundary". T-31 (four-file parameter threading) is fixed by the same 4B given room to iterate
(49 s, 9 turns); what the budget buys is *agency* (long multi-step sequences), not the ability
to *author* a correct implementation. The anchors stay 0/5 and keep their failure shape: A-03
spent 238 s in one turn with **zero** tool calls, A-05 207 s with zero tool calls (a single
thinking block ate the per-turn output budget and was truncated), and A-02 still certified a
wrong fix.

**Also un-remeasured:** whether asking pi to write its own tests still harms it at 32k. The
9-of-10 truncations that finding rested on were an 8k artifact, so `docs/STATUS.md` §8's
"asking for tests makes pi worse" paragraph is now explicitly marked as an 8k-only measurement.

## Our harness at 32k (the other half of the fairness gap)

`--verify full`, all 40 tasks, 4 sequential bands, against the same 32768-token server. This
was run *after* the correction above, so that our side is not the one with a hidden ceiling.

Result, all 40 tasks against the same 32768-token server: **actual 22/40 (55%)**, 14 claimed, 11
missed, **3 false**; mean 47 s and 8.5 model calls per task. Per band: T-01..T-10 7/10,
T-11..T-20 7/10, T-21..T-30 6/10, tail+anchors 2/10. Eight of the eleven missed wins were blocked
by `independent-test-red-on-final` and three by `ladder`; the three false successes all ended
`stop=green`. Full breakdown and the comparison against the maxed pi arm: `docs/STATUS.md` §8b/§8c.

## The defect this probe found (bigger than the score)

At 32k our `full` arm repeatedly reached a grader-passing revision and then **refused to claim
it**: `stop_reason=independent-test-red-on-final`. Reading the records, the dominant cause is
that **the independent test asserts the pre-fix behaviour** and vetoes the fix:

```python
# T-10's independently authored test, verbatim from the record
def test_ac1_empty_stock_no_indexerror():
    """AC1: The restock picker crashes with IndexError when stock is empty."""
    empty_stock = {}
    with pytest.raises(IndexError):      # the request asks for the crash to be fixed
        next_bin(empty_stock)
```

The gate requires the suite to be RED overall on arrival, which such a test satisfies by
*agreeing with the bug*; it then flips to red when the bug is fixed. Per-test outcomes are
already recorded on both revisions (`iv_original_gate`, `iv_final_gate`), so the signature is
deterministic:

- `iv_inverted_tests` = final-red ∩ original-**green** — the test asserts pre-fix behaviour
  (T-06, T-10, T-22: three of the five blocked grader-passing fixes in the 32k run).
- `iv_unmet_tests` = final-red ∩ original-**red** — the criterion really is still unmet, or the
  test is unsatisfiable/self-contradictory (T-12's test is red on both revisions; T-21's suite
  demands both "raises" and "does not raise"). These must stay blocked, or go to the existing
  `test_blame` judge.

**Decision needed from the owner** (it changes a rule the owner set — "a red independent
verification blocks a review-backed claim"):

| option | effect |
| --- | --- |
| A. keep the hard block | never over-claims, but keeps discarding fixes the grader accepts |
| B. record the split (step 1, no rule change) and **route only `iv_inverted_tests` to the existing judge**, with the failing test's text, its original-vs-final outcome, and the acceptance criterion quoted | recovers the wrongfully blocked fixes; one extra judge call, and the judge can still say "regression" and keep the block |
| C. allow the claim automatically when the final-red tests were all green on arrival | cheapest, but it waves through genuine regressions the fix introduced |

Recommendation: **B**. Step 1 (recording `iv_inverted_tests` / `iv_unmet_tests`) is safe and
does not touch the rule; it was deliberately NOT implemented during the sweep (a code change
mid-sweep would have put two code versions into one evidence set).
