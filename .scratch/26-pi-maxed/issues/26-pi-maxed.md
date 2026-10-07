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

## Round 2 — trajectory forensics on the three owner questions (2026-10-06)

The owner asked: why is our actual pass rate lower than pi's; why was pi's "missed" column a
dash; and why do we have MORE false successes. Answers from the per-attempt records (no new
model runs were made).

### What the records show (`bench/runs/v2sweep-20261006T04*`)

Seven tasks are pi-only wins: T-01, T-05, T-07, T-14, T-16, T-28, T-31. Six of the seven are
our own machinery, not the model:

| task | record evidence | defect |
| --- | --- | --- |
| T-05 | own test `test_tagger.py::test_tags_are_independent...` red in attempts 3-6, verdicts `same`; the SAME code passed this task at 8k (18 calls) | self-test loop |
| T-07 | own test ImportError, then independent test red; passed at 8k (16 calls) | self-test loop |
| T-14 | passed at 8k in 5 calls; at 32k the review marked all three criteria `violated` | review-driven iteration |
| T-01 | `touched_files: []`, six `refusals: auth/sessions.py: grader-owned path`, exit on `same-verdict tail`; sessions.py is in the task's UNTOUCHED contract, the fix belongs in `auth/config.py` | refusal loop never re-plans |
| T-31 | attempt writes alternate `transport.py` / `client.py`; `_mode()` returns M1 (`_erase_draft`) after each `same`/`undecided` verdict, erasing the other file's fix; ends `attempt-cap` with coverage naming the untouched files | M1 erase vs multi-file fixes |
| T-16 | stopped at 6 model calls of a 24-call budget (`ladder-exhausted`) | early-exit ladder |
| T-28 | 1 attempt, `self_test: null`, `iv approved=false (unobserved)`, review approved; grader: 4 failed | gate correlation |

Three of the seven (T-05, T-07, T-14) were fixed by our own harness at 8k, so part of the gap is
a 32k regression of ours rather than pi's superiority (N=1 per task).

### pi's "missed" is not a dash, and the column is not comparable

pi has no claim gate; the driver's `claimed` is a regex over its final assistant message.
Counter over the 40 records: (claimed, actual) = (True, True) 27, (False, False) 11,
(True, False) 2 => missed 0, false 2. Ten of the eleven non-claims are `claim_reason: no
assistant message` (a truncated turn), not an admission of failure. Only `actual` and
`false success` are comparable across the two agents. `docs/STATUS.md` 8c was corrected.

### The false successes are one deliberate path

All three of ours (T-26, T-28, A-05) ended `stop=green` with `claimed_basis=review`,
`self_test: null` and `iv approved=false` (`independent-test-unobserved`, or
`-not-discriminating` in A-05 where 22 IV tests pinned only AC1-4 and the review marked AC5-21
satisfied). `claim_decision`'s docstring states this is by design: a vacuous/non-discriminating
independent test "is NOT a red verdict and does not block", and rule 6 lets a review carry a
claim when no own test was ever written. So a run that keeps a wrong reading of the request
carries its own test, its independent test and its reviewer with it — correlated agreement, not
evidence. That, not a new bug, is why our false-success count exceeds pi's.

### Agenda for the next round (in order, none implemented yet — the sweep needed one code revision)

1. **Refusal → re-plan**: after a refused write, the next attempt must be told the refusal and
   the writable set, and must choose a different target; the current loop only counts the
   attempt and eventually exits on a same-verdict tail (T-01).
2. **Multi-file accumulation**: either keep a per-attempt draft (a non-erasing mode for
   multi-artifact requests), or make best-evidence ranking coverage-aware so the most complete
   revision is preserved across an M1 erase (T-31).
3. **Early exit**: the ladder ends runs with most of the call budget unspent (T-16); separate
   "the ladder has no new idea" from "the task is not done".
4. **Review-only claim path**: require at least one *observed, discriminating* independent check
   for a claim, or record that a claim rests on a single correlated reviewer (T-26/T-28/A-05).
5. **Inversion detection** (from round 1): record `iv_inverted_tests` / `iv_unmet_tests`; owner
   decision pending on whether the inverted case may reach the judge.

## Round 3 — the concrete forensics (owner: "this report is too abstract")

Every claim below is from a record, a delivered file, or pi's own event stream. No new model
runs were made. Where the record cannot answer the question, that is stated as a gap.

### T-01, step by step

- The bug is `repo/auth/config.py`: `SESSION_TTL_SECONDS = 60`; `auth/sessions.py` only consumes
  it (`now + timedelta(seconds=config.SESSION_TTL_SECONDS)`).
- `build_spec` puts BOTH files in the run's view: `spec.files` = README.md, auth/__init__.py,
  **auth/config.py**, **auth/sessions.py**. The run's `current_files` artifact is built from
  `_repo_view(spec, workdir, baseline)` = those files, so the model was shown the broken
  constant on every attempt.
- `checks.py` `UNTOUCHED` includes `repo/auth/sessions.py`, and `build_spec` folds UNTOUCHED into
  `grader_paths`, so the write guard refuses it — correctly (writing it fails the contract).
- All six attempts targeted `auth/sessions.py` and were refused: `refusals` = 6x
  `auth/sessions.py: grader-owned path`; `touched_files` = [] on every attempt; each attempt's
  own claim text reads "Updated session TTL to 3600 seconds…" (the model believed it had written).
- The feedback the model got was `implement refused: grader-owned path` (in `failure_output`),
  and the M1 wording it got next was "Your previous draft was erased. Regenerate the target file
  **from the failure history as your only intelligence**." Nothing in the loop says which files it
  MAY write, and nothing forces a different target.
- So: the specification was not wrong. The requirement text ("a seconds/milliseconds mixup when
  the session TTL was moved into config") and the visible file set both pointed at config.py; the
  **implementation step chose the frozen call site every time**, and the loop's only response was
  to count the refusal.
- pi, same model, same task: `ls`+`find`, then read README.md, **auth/config.py**,
  auth/sessions.py, auth/__init__.py, then `edit auth/config.py` 60 -> 3600, then ran four ad-hoc
  assertions including the 3599/3601 s boundary and `inspect.signature` to prove the public API
  was unchanged. One file, one correct change, self-verified.

### Multi-file: there is no multi-file write, and there never was in this driver

- The implement question is literally: "Emit the complete new content of **ONE** implementation
  file (file_path + content)." The envelope carries a single `file_path` + `content`.
- What DOES allow many files is the leaf's write BOUNDARY (`PlanNode.files`, up to 10) and the
  tree's decomposition; `docs/DESIGN.md` line 291 names "(multi-file, control-flow-restructuring,
  cross-module contracts)" as the class of task that must be SPLIT into children. The 40-task
  sweep runs the single-leaf driver, i.e. the un-split path.
- T-31's spec is not the problem: `spec.files` = client, service, transport, bulk (all visible)
  and AC-2 says verbatim "Add a `timeout` parameter (default 1.0) to the transport's `send()`,
  thread it through the client's `fetch()`, and make sure BOTH call sites (the service … )".
  The coverage gate later names exactly those untouched artifacts. The run's per-attempt writes
  alternate `transport.py` / `client.py` because each attempt writes one file and M1
  (`_erase_draft`) restores every written file to its pristine content after any `same`/`undecided`
  verdict — so the two changes never coexist in the delivered revision.
- Best-evidence capture is ranked by evidence (own test / independent test / review), never by how
  much of the required surface a revision covers, so the more complete revision is not preserved.

### T-16, step by step

- The run's own test was CORRECT (`test_carts_are_independent`: `cart1.add(...)`; `assert
  cart2.contents() == []`).
- Attempt modes: M2, M1, M2, M1, M1 (M1 = erase). The final delivered `cart/cart.py` differs from
  the buggy original by **one missing trailing newline** — `items = []` is still a CLASS attribute.
  The grader failed on both of the run's own assertions.
- pi: read `cart/cart.py`, `cart/__init__.py`, `README.md`, wrote an `__init__` with a per-instance
  list, then ran a two-cart check in bash. 5 turns.

### T-05 and the "8k good / 32k worse" question

- The context/output cap was NOT hit: `malformed_steps` is `[]` in both the 8k and the 32k records
  (50 envelopes, 0 truncated), and the 32k run spent 10 of its 24 calls.
- 8k: own test `test_tagger_bleed.py` ("explicit tags list is respected"), 18 calls, delivered a
  CHANGED `tagger/notes.py`, grader PASSED.
- 32k: own test `test_tagger.py` ("explicit tags list can be shared"), 10 calls, and the delivered
  `tagger/notes.py` is BYTE-IDENTICAL to the buggy original (`diff` empty; no `tags=None` guard).
  The failing signature at the end is only the independence test, i.e. the run had regressed to the
  unmodified file. The last attempt was M1 (erase -> "regenerate from the failure history").
- So the difference is not context size but the run's own iteration: a different self-test changed
  the failure the loop optimised for, and the last M1 attempt replaced the draft with a copy of the
  original. N=1 per cell; the mechanism, not the delta, is the finding.

### The strongest single number: five of forty runs delivered nothing

Comparing the delivered work tree against the task's pristine sources file by file (non-test .py):
`T-01` (nothing at all), `T-05` (nothing), `T-34` (nothing), `T-13` (whitespace only),
`T-16` (trailing newline only). All five failed the grader; **pi fixed three of them (T-01, T-05,
T-16).** In all five the LAST attempt was an M1 erase attempt. The pipeline has no delivery-time
check that the revision it is about to hand over differs from the baseline in any file it was
supposed to fix.

### pi's "claim" column is not a measurement of honesty

12 non-claiming rows (11 tasks after de-duplicating A-01, which two bands measured): **10 have a
completely empty final assistant message and the eleventh ends mid-sentence** ("Let me search for
any spec, corpus, or test hints related to this task."). The driver's `claimed` field is a regex
over that message; an empty message is a TRUNCATED turn at the output cap, not an admission of
failure. pi was never asked to state a claim, so "missed = 0" is an artifact of the instrument.
The only claim-related numbers that compare across agents are `actual` and "asserted success on a
revision the grader rejects".

### The false successes are not a requirement-decomposition failure

- T-26: the request says verbatim "must keep the old dict-style access working for callers not yet
  migrated" AND "Plan instances must be real dataclass objects with attribute access". The
  delivered `plan/model.py` is a plain `@dataclass` with no `__getitem__`, so `p["name"]` raises
  `TypeError` — the grader's first test. The requirement was explicit and in the ACs; the review
  marked all three ACs `satisfied` (`review:ac-correctness`).
- T-28: the required API is documented IN THE REPO, in `repo/README.md`, which `build_spec` puts in
  the model's view: "Plugin registry: register(name, fn) / get(name) / run(name, *args)." The run
  wrote a `Registry` CLASS instead, so `registry.register(...)` raised AttributeError. Review:
  definitely-ok; own test: never written; independent test: `unobserved`.
- A-05: independent test ran 22 nodes, 0 failed, but was rejected as
  `independent-test-not-discriminating` (its nodes pinned only AC1-4); AC5-21 were marked
  `satisfied` by the review alone; the grader then failed the two puzzle-answer tests.
- Common pattern: no own test was ever written, the independent test was unusable (unobserved or
  non-discriminating), and `claim_decision`'s documented rule 6 lets the review carry the claim —
  with the reviewer being the same model that wrote the code.

### What the record CANNOT answer (stated as a gap, not a guess)

The per-attempt MODEL OUTPUT is not persisted: the record keeps `claimed_delta` (the model's
one-line summary), `touched_files`, and the failure signature, but not the `file_path`/`content`
the envelope carried. So "did the model emit a no-op file, or did something revert a real fix?"
can only be answered indirectly (the delivered bytes + the M1 mode), not read off directly. Adding
the envelope content (or its hash) per attempt is a prerequisite for the next round of forensics.

## Round 4 — T-01: what the model was actually shown, and what it was never told

### First, the persistence question (owner: "trajectory 保存全部信息，根本不需要看 Git")

Checked, three ways:

1. `harness/runner.py::llm_step` builds `LLMRequest(step_type, artifacts, question, tools,
   fresh, prompt)` and calls `model.complete(request)`. The only thing it records is
   `note("llm_invocation", step_type, cache_hit, prompt_tokens, completion_tokens,
   wall_model_s)` — and the module docstring says so explicitly: "counters only, never
   content" (KERNEL_API §5, a deliberate design decision). No prompt, no response.
2. There is no environment switch or debug sink that dumps them (`os.environ` appears only
   for the pytest/sandbox env in `harness/exec.py` and `harness/staging.py`).
3. The llama-server log (`/tmp/llama-max-ctx.log`, the 32k server these runs used) logs token
   counts and timings, not content.

So for OUR runs the per-attempt model text is genuinely unrecoverable. The only model-authored
text kept per attempt is `claimed_delta` (= the envelope's `comment`, one line). By contrast
pi's `events.jsonl` keeps the system prompt, the user message, every `thinking_*` delta and
every tool call — which is why pi's thinking can be quoted verbatim and ours cannot. That is a
harness gap to close (capture the request/response per call), not a fact of nature.

### T-01: the exact inputs, reconstructed deterministically

`build_spec` gives the run the whole source projection, and both steps push it into the prompt:

- Step 1 (`write_test`) artifacts: `goal`, `acceptance_criteria`, `interfaces` (empty), and
  `repo_files` = **the full text of all four files**, including
  `auth/config.py` = `SESSION_TTL_SECONDS = 60` and `README.md` = "Sessions last one hour
  (documented product behavior)".
- Every implement attempt gets: `goal`, `acceptance_criteria`, `interfaces`, `current_files`
  (again all four files), `self_test`, `failure_output`, `failure_history`, `escalation`,
  `escalation_detail`, `retry_mode`.

What the artifacts never contain: **a list of files the run may write**, any statement that
`auth/sessions.py` is frozen, and any hint about which file holds the defect.

The implement question is: "Emit the complete new content of ONE implementation file
(file_path + content). Never edit a test file or a grader path — fix the source."

After the first refusal, the next attempt receives exactly:

- `failure_output` = `implement refused: grader-owned path`   ← **the file name is not in it**
  (`_source_write_problem` returns the bare reason; the record's `refusals` list adds
  `source_rel`, but `last_excerpts = [f"implement refused: {refusal}"]` — only the reason — is
  what the model sees),
- `failure_history` = `- [L1-resample/sampling] claim='Updated session TTL to 3600 seconds to
  restore 1-hour expiry.' sig= verdict=same` (nothing about the code),
- `retry_mode` = `M1`, and the question: "Your previous draft was erased. Regenerate the target
  file **from the failure history as your only intelligence**."

### The reconstructed flow (consistent with `calls: 9`)

1. `write_test`: the model writes a test for the TTL bug. It **passes on the buggy source**
   (it does not discriminate), so the one re-ask fires, it passes again → `self_test = None`
   (the file is deleted), `no-red-target` path.
2. The judge is consulted there and answers with the correct diagnosis:
   `implementation_wrong: true, reason: "The code sets SESSION_TTL_SECONDS to 60, causing
   sessions to expire in 60 seconds instead of the required 1 hour."` (its `raw` vote said
   `blame: test`, which the deterministic filter coerced, because the defect text named no
   failing test).
3. `handle_verdict` takes the `implementation_wrong` branch: `return "implementation"` — the
   diagnosis text is **not** written into `last_excerpts`, so it never reaches the implementer.
4. The run enters review verification and starts the ladder: six implement attempts, every one
   targeting `auth/sessions.py`, every one refused (`refusals` = 6 x "auth/sessions.py:
   grader-owned path"), `touched_files` = [] each time.
5. All six verdicts are `same` (nothing written, nothing new claimed) → exhaustion
   `"same-verdict tail across layers [implementation,sampling,spec]"`.
6. Delivered revision: unchanged files (`applied: ["auth/config.py"]`, content identical to
   pristine). Grader: `tests/test_sessions.py:21: AssertionError` → FAIL.

Call accounting: 1 self-test + 1 re-ask + 1 judge + 6 implement attempts = **9 = `calls`**. The
reconstruction therefore matches the record exactly.

### Why sessions.py, and was it ever going to do config.py?

What we can prove: it was shown config.py's broken line on every step, it chose sessions.py six
times, its own words each time were about "session TTL" ("Updated session TTL to 3600
seconds…"), and it never attempted config.py. What we cannot prove: whether it considered
config.py and rejected it, or was about to change both — the chain of thought is not captured.
Its choice also contradicts the request's own clause "don't touch the public API while fixing
it" (sessions.py holds `create_session`/`is_expired`).

pi, for the same task, with the same text: THINK #5 says, verbatim, "The public API here is
likely the functions in `sessions.py` — `create_session` and `is_expired`. We shouldn't change
those. We should only fix the config value." It read README.md, auth/config.py, auth/sessions.py
and auth/__init__.py first (pi has a `read` tool and chose to use it), then made one edit.

### Defects this walkthrough establishes (T-01 alone)

1. **The implementer is never told which files it may write**, and the refusal text it gets
   omits even the file name. (Contrast: the record's `refusals` has the name; the prompt does
   not.)
2. **The judge's correct diagnosis is dropped** on the `implementation_wrong` path.
3. **A refusal is treated as "no information about the code"** and yet the next prompt says to
   regenerate "from the failure history as your only intelligence" — a write refusal carries no
   code information at all, so the retry is blind by construction.
4. **Nothing checks that the delivered revision differs from the baseline.**
