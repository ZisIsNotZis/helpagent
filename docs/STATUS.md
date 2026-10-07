# Status — what works, what was measured, what is not solved

Written 2026-10-01 while the owner was away. Everything below is either measured (with the
command to reproduce it) or explicitly marked as not built. When this document and the code
disagree, the code and its tests win; when this document and the run records disagree, the
records win.

## 1. The measured position

Reference model: Spark-X2.5-4B (Q4_K_M) on llama.cpp, one local server. Method: **blind** —
the corpus's own test suite is the grader and never enters the run; the run's produced files
are applied to a pristine copy afterwards and scored there. Nine corpus tasks, two runs
each, driver `bench/v2_leaf.py` (the leaf flow: own test, independent verification, review,
the claim gate).

Measured 2026-10-03 at commit `416f1bf`, 9 tasks x 2 runs, `bench/v2_sweep.py`; the run record
is kept under `bench/runs/evidence/` (the newest sweep) with the rest under `bench/runs/`.

| metric | value |
| --- | --- |
| **actual** (the grader's verdict) | **15/18 (83%)** |
| **claimed** (what the harness said) | 8/18 |
| true success (claimed + grader passed) | 8 |
| missed success (did not claim, grader passed) | 7 |
| honest failure (did not claim, grader failed) | 3 |
| **false success (claimed, grader failed)** | **0** |
| model calls | 163 (9.1 per run) |

**The five claim rules measured on the same nine tasks and model**, in the order they were
built. Each line is a real sweep; the last is the current default:

| claim rule | actual | claimed | true | missed | honest | **false** | calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agreement required (a red test could never be overridden) | 14/18 | 4/18 | 4 | 10 | 4 | 0 | 156 |
| the graded review outranks a conflicting test | 12/18 | 11/18 | 9 | 3 | 4 | **2** | 174 |
| ... plus grant-calibre review evidence | 12/18 | 8/18 | 8 | 4 | 6 | 0 | 186 |
| ... plus best-evidence delivery (never deliver the erased baseline) | 14/18 | 11/18 | 8 | 6 | 1 | **3** | 177 |
| ... plus request-level coverage and a red independent verification blocking a review | **15/18** | 8/18 | 8 | 7 | 3 | **0** | 163 |

Reading the curve: the owner's review-precedence rule bought claims but leaked two false
successes (a 20% rate on the review tier); requiring grant-calibre review evidence removed
them; delivering the best-evidenced revision recovered two graded successes (both T-05 runs,
whose correct fix M1 had been erasing) but re-exposed three false successes, because a
partial multi-site fix and a wrong fix could still satisfy a graded review; and the two
deterministic gates closed those: **every artifact the request names must be touched by the
final diff** (frozen/grader-owned artifacts are exempt, recorded with the reason) and **a
RED independently authored per-criterion verification blocks a review-backed claim** (the
review still outranks the run's own model-written test, which is what the rule was written
about). The gates cost three claims and one graded success was recovered elsewhere; the
net is the best measured configuration: **15/18 fixed, 0 lies**.

**Claims by evidence basis** (the field a consumer should filter on - never on
`verification.tier`, which can read `test` on a review-decided claim):

| tier | claims | true | **false** | false rate |
| --- | --- | --- | --- | --- |
| `review` (graded, grant-calibre, gates clear) | 7 | 7 | 0 | 0% |
| `review+independent-test` | 1 | 1 | 0 | 0% |

**Why seven graded successes were not claimed:** the dominant blocker is now the
independently authored verification being WRONG on a correct fix (five runs ended
`independent-test-red-on-final`; the ledger names the failing independent test), plus two
`ladder` runs whose ledger names the unverifiable criterion. That is the same weak-model
test-authoring problem the forensics found, now surfacing in the independent role.

**What the harness contributes, measured.** The same model driving a plain agent loop
(free-form chat plus list/read/write/run tools, sandboxed, grader tests withheld) solved
**0 of 6** hard tasks: it wrote no test and ran no command, edited one file and declared
itself done. The harness's forced red-then-green loop, its deterministic gates and its
evidence ledger are what make the model fix 15 of 18 - and its claim gates are what keep
the false-success count at zero while doing so.

**Caveat on section 1 (added 2026-10-03):** those nine-task runs were measured while the
corpus still shipped `.pytest_cache` (the leak retracted below). The harness arms proved
insensitive to it - development-only and self-test re-measured identically without the cache
(21/40 and 23/40) - but the REVIEW tier was not: its false-claim count rose from 10 to 13 when
the cache was removed, i.e. the reviewer had been reading the cache too. Treat section 1's
review-tier numbers as optimistic; sections 1a and 8 are the clean measurements.

### 1a. The development-vs-verification matrix (clean, 2026-10-03, commit `124c41d`)

The claim rule was retracted as a leaked-exam measurement on 2026-10-03 (task repos shipped a
stale `.pytest_cache` holding the grader's own test node ids, and the mature-agent baseline
visibly read it; `harness/staging.py` now withholds cache artifacts and the corpus caches are
gone). This matrix is the clean re-measurement on all 40 tasks, N=1, using a `--verify` mode
selector that isolates the mechanisms. It compares only the 33 tasks that every arm completed.

| arm | what drives the loop | actual | claimed | FALSE | model calls | calls/run |
| --- | --- | --- | --- | --- | --- | --- |
| `raw` | **development only** - no self-test, no independent test, no review, never claims | **17/33 (52%)** | 0 | 0 | 37 | **1.12** |
| `test` | the run's own test, red on arrival, iterate to green | 18/33 (55%) | 0 | 0 | 165 | 5.00 |
| `review` | the graded review is the only feedback; iterate until it approves | 18/33 (55%) | 28 | **11** | 191 | 5.79 |
| `full` | today's default: self-test + independent verification + review + the deterministic gates | **20/33 (61%)** | 12 | 2 | 338 | 10.24 |

Reading it:

- **Our protocol's development-only baseline is 52%** at ~1.1 calls per task; that is the
  number a "normal agent loop" has to beat on the same tasks and model.
- **Verification helps, but only as a combination.** The self-test loop adds ~3 points for
  4.5x the calls; review-driven iteration adds the same ~3 points, and its own verdicts are
  wrong 11 times out of 28 claims (39%) - so review does not make the model a better
  programmer, it makes it more willing to say "done". The full stack adds ~9 points (52 -> 61)
  at ~9x the calls, and it is the only arm that fixed T-33 (the contract-completeness task the
  deterministic gates force).
- **The machinery also loses tasks:** `full` failed T-01, which `raw` fixed (and in the
  earlier sweep it lost T-05 and T-18 the same way). The iteration can talk the model out of a
  correct one-shot fix.
- **Ten tasks no arm fixed** (anchors A-01..A-03 plus T-24, T-26, T-27, T-28, T-31, T-32,
  T-34): the capability tail. T-31's four-file parameter threading is in that set — **but see
  section 8: T-31 is fixed by the same 4B when the mature CLI is given reasoning budget and a
  32k window, so that task was throttled by our 8192-token server, not by the model's ceiling.**
  These arms were all measured against that 8k server; the tail-band re-measurement at 32k is
  recorded in section 8.

## 2. What the harness does (one paragraph each)

**Blind protocol.** The run never sees the grader's tests. It stages only source, works in a
sandbox, and is scored afterwards on a pristine copy. A run that "fixes" its own tests, adds
a `conftest.py` hook, shadows `json.py`/`pytest.py`, or forces a zero exit status is refused
or restored, and the attempt is recorded.

**Self-verification that cannot lie about itself.** The gate is a machine-readable pytest
report written to a private path, containing a per-run random canary and the expected test
ids. An exit status is never evidence; a missing report, a missing canary or a mismatched id
is red.

**One claim gate.** A claim is granted in exactly one place. It requires: at least one
acceptance criterion, a non-empty evidence ledger, no missed PER-CRITERION artifact
coverage, no missed REQUEST-LEVEL artifact coverage (ticket 23 round 3, Gate 1), and — for
anything more than the run's own green test — a supporting verification. A red own test plus
a passing test is recorded as a verifier CONFLICT and cannot claim; the graded review
outranks a conflicting test, EXCEPT that a RED independent verification blocks a
review-backed claim (ticket 23 round 3, Gate 2). A structural test fails the suite if any
other code path could grant a claim.

**Evidence in both directions.** Every acceptance criterion gets a ledger row (satisfied /
violated / unverifiable) pointing at what was observed. A run that stops without any
satisfied or violated row is an EVIDENCE GAP and says so, rather than reporting a vague
"attempts exhausted".

**Decomposition is budgeted and greedy.** A request becomes a root node; a node plans ranked
approaches (Hows), takes the top one, and spends its budget there; failed approaches are
abandoned and a new one may be appended (bounded), or the node re-plans into children when
its own boundary is genuinely multi-part. Wall-clock deadline is the primary budget.

## 3. What was tried and did NOT help (measured, not guessed)

| Mechanism | Result |
| --- | --- |
| injecting a knowledge pack (signatures/callers/constants) | no gain (4/15 vs 3/15) |
| putting module importers into the write spec | no gain (10/15 vs 10/15) |
| forcing a deterministic file-change order | harmful (14/15 vs 7/15) |
| extending the write boundary on rule evidence | no gain (1/5 vs 1/5) |
| competitive How exploration (tournament of candidates) | works, but ~5× the calls and wall time for fewer fixes; greedy is now the default |
| a "bare" agent loop as a baseline | 0/6 — it wrote no test and ran no command; the harness's forced verification is what makes the model move at all |

The pattern across all of them: structure that costs calls without adding **information**
loses. What moved the numbers was giving the model more signal (the forced red-then-green
loop, deterministic diagnosis rules, the report gate, coverage and discrimination checks).

## 4. Known limits (accepted, not pretended away)

1. **Two verifications that share the same misreading agree**, so a wrong fix can be
   certified. No deterministic in-process rule can catch this without a ground-truth oracle.
   The external grader is the only correctness arbiter. (DESIGN §10.8a.) Ticket 22 makes
   this sharper: the graded REVIEW now outranks a conflicting test, so a review that
   approves a wrong fix claims directly rather than being backstopped by an agreeing test.
   Ticket 22 round 2 hardens the route: a review that is about to GRANT must name the
   acceptance criterion it serves AND the specific behaviour/observable/value it verified
   (a changed path or a generic "looks correct" no longer grants; the refusal is recorded
   as `review_not_grant_calibre`). The remaining risk is now exactly the reviewing model's
   error rate when it approves on substantive evidence: thin evidence can no longer
   manufacture a review-backed claim, but a specific yet mistaken approval still can.
2. **The harness is not an oracle.** Its own claim is evidence, not proof; every number in
   section 1 is the grader's verdict, never the harness's.
3. **Adversarial code can forge the gate's own evidence** (it runs in the same process and
   filesystem). This is tamper-*evident* (every anomaly is recorded) but not prevented; a
   run would have to write deliberately hostile code, which the reference model never did.
4. **A weak-but-genuinely-discriminating test** (red on the pristine source, green on the
   final) passes the harness's checks even if it does not encode the requirement.
5. **The strongest residual on the quality axis is MISSED success**: runs that fix the task
   and cannot verify it. The ledger now names which criterion was unverifiable and why.
6. **The review tier is measured, not proven.** In the last sweep its review-backed claims
   were 0/8 false, down from 2/10 before the grant-calibre evidence rule; one sweep is one
   sample, and the tier's error rate is the reviewing model's own. A consumer that cannot
   tolerate that filters on `claimed_basis` (accept `own-test`, `own-test+independent-test`,
   `independent-test`, `review+independent-test`; treat `review` alone as reviewed-but-weak).
   `verification.tier` is NOT the filter to use - it can read `test` on a review-decided claim.

## 5. Where the evidence lives

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage, manager decisions, budget accounting) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/NN-*/issues/*.md` (ticket 21 covers the claim model; ticket 20 the
  How axis and its measured verdict; tickets 17–19 the leaf, the tree and the covenant).
- Design: `docs/DESIGN.md` §10 (flow) and §10.10 (implemented vs not built).

## 6. Recommended next steps (ordered)

1. **The claim rule is settled by measurement; do not re-open it without new numbers.**
   Three rules were measured on the same tasks and model (section 1): the owner's
   review-outranks-tests rule, once requiring grant-calibre evidence, claims twice as many
   true successes as the conservative rule at the same measured false-success count (0), and
   the two false successes the unhardened rule produced are refused by the evidence rule.

2. **Attack the remaining missed-success bucket (4 of 18).** Every case's ledger says which
   criterion was unverifiable and which check was attempted; two of the four are T-33, whose
   criteria name a file the task freezes (a criterion/corpus mismatch worth fixing in the
   task, not the harness).

3. **The independent test is still the weakest link** (14 attempts, 3 repairs, and it was the
   blocker in the earlier conservative sweep). A stronger verifier model - even a modest
   remote one - for the test-authoring and review roles is the single change most likely to
   raise true successes; every run records whether its verification was independent or
   reviewed, so the effect would show in the very next sweep.

4. Build the designed-but-unbuilt layers only if a task needs them: requirement triage,
   model-side context curation, worktrees/parallel trees, a human-facing piloting surface
   (DESIGN §10.10).

## 7. Reproducing the numbers

```sh
# unit gate (no model required) — includes the repo tamper guard and corpus integrity
uv run pytest

# one task, leaf flow, with the ledger and claim record
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --calls 24 --deadline-hours 0.25

# the headline sweep (claimed vs grader), nine tasks, two runs each
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-03-wrong-comparison,T-05-mutable-default,T-08-add-cache-invalidation,T-14-add-export-sorting,T-20-average-truncation,T-25-chunked-helper,T-31-parameter-threading,T-33-serializer-contract --n 2 --calls 24
```

The reference model server used for every number above:

```sh
llama-server \
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8833 --host 127.0.0.1 -ngl 99 -c 8192
```

`curl -fsS http://127.0.0.1:8833/health` must answer `{"status":"ok"}` before a sweep.

## 8. Mature agent CLI baseline (the same model, all 40 tasks, clean)

> **The pi rows below were THROTTLED by our own configuration** (thinking clamped off, 8192
> tokens of context). Read **8b** for the corrected measurement before quoting any of them.

`bench/pi_baseline.py` runs the real **`pi` CLI headless** against a corpus task with the same
blind staging (source-only; the grader never enters the run), a temp pi agent dir (the owner's
real config is never touched), a bwrap sandbox, and the same external grader. Measured on all
40 tasks (35 corpus + 5 anchors), N=1, after the cache-leak fix (`124c41d`).

| agent | actual | claimed | FALSE | cost |
| --- | --- | --- | --- | --- |
| harness `--verify raw` (development only) | **21/40 (52%)** | 0 | 0 | **1.1 model calls/task**, ~6 s |
| harness `--verify test` | 23/40 (58%) | 0 | 0 | 4.9 calls/task, ~28 s |
| harness `--verify review` | 22/40 (55%) | 34 | **13** | 5.4 calls/task, ~18 s |
| harness `--verify full` (default) | 20/33 (61%)\* | 12 | 2 | 10.2 calls/task, ~96 s |
| **pi CLI, request only** (throttled — see 8b) | **21/40 (52%)** | 21 | **4** | ~8 turns/task, ~120 s |
| **pi CLI, request only, reasoning max + 32k (8b)** | **27/40 (68%)** | 29 | **2** | 8.9 turns/task, 131 s |
| **pi CLI + an explicit "write and run your own tests" instruction** | **16/40 (40%)** | 22 | **6** | ~8 turns/task, 90-160 s |
| our minimal agent loop (`bench/v2_agent.py`) | 0/6 (hard subset) | n/a | n/a | - |
| our plain one-shot driver (`bench/v2_free.py`) | 3/12 | n/a | n/a | 1 call |

\* the `full` arm hit the 25-minute per-lane cap at 33 of 40 tasks; the number is on the 33 that
ran, which is why the comparison table in section 1a uses the tasks every arm completed.

Per band, pi (request only) vs the harness arms on the same tasks:

| band | pi | harness `raw` | harness `test` |
| --- | --- | --- | --- |
| T-01..T-10 (easy) | 9/10 | **10/10** | - |
| T-11..T-20 (middle) | 7/10 | 6/10 | **9/10** |
| T-21..T-30 (hard) | 5/10 | 6/10 | **7/10** |
| T-31..T-35 + anchors (tail) | **0/10** | 0/10 | 0/10 |

**What this shows (REVISED 2026-10-06 — the original reading is retracted).** The original text
here said development capability was a TIE, and that the hard tail was a model-capability
boundary. Both readings were measured against a **throttled** pi: `--thinking` was `off`, and
it could not have been anything else because the temp model entry declared no reasoning support
(pi clamps the level to what the model advertises), on a server with only **8192 tokens of
context** — which is exactly where that arm's tail runs were dying. Re-measured with those
ceilings removed (section 8b): pi fixes **27/40 (68%)**, not 21/40. So we do **not** tie a
properly configured mature CLI, and T-31 is not a model-capability boundary. What survives is
narrower and better supported: the harness's gates keep false successes at 0-2 where pi, which
has no claim gate, certifies wrong fixes, and the anchor band (writing a whole correct
implementation from a text spec) is still 0/5 both ways.

### 8b. The same pi, configured properly (reasoning + 32k) — 2026-10-06

The owner asked whether the comparison above was fair. It was not, in two ways that were ours:
`--thinking off` was not merely a weaker setting but the only level the model declaration
allowed, and the server's window was 8k. `bench/pi_baseline.py` now has `--reasoning` (default
off, so the arms above stay reproducible) which declares reasoning support and the server's real
32768-token window; the server was restarted at `-c 32768` with quantised KV cache.

| band | recorded (thinking≈off, 8k) | **maxed (thinking max, 32k)** |
| --- | --- | --- |
| T-01..T-10 easy | 9/10 | **10/10** |
| T-11..T-20 middle | 7/10 | **9/10** |
| T-21..T-30 hard | 5/10 | **7/10** |
| T-31..T-35 tail | 0/5 | **1/5** (T-31) |
| A-01..A-05 anchors | 0/5 | **0/5** |
| **total** | 21/40 (52%), 25 claimed, 4 false | **27/40 (68%)**, 29 claimed, **2 false** |

Mean cost 131 s and 8.9 turns per task. On the 33 tasks the harness `full` arm also ran, pi here
is **22/33 (67%)** against the harness's recorded **20/33 (61%)**; pi-only wins are T-01, T-12,
T-28, T-31 and the harness-only wins are T-33, T-35. Evidence (per-task records, band summaries
and a reasoning-trace-free README): `bench/runs/evidence/pi-maxed-20261006/`, guarded by
`tests/unit/test_pi_maxed_evidence.py`.

**What the extra budget actually buys — and what it does not.** It buys *agency*: T-31's
four-file threading is fixed (49 s, 9 turns) and the mid/easy bands gain four tasks, i.e. long
multi-step tool sequences were being cut off by our window, not by the model. It buys nothing on
*authoring a correct implementation*: the anchors stay 0/5, and the failure shape is the
diagnosis — A-03 spent 238 s in **one** turn making **zero** tool calls and A-05 207 s with zero
tool calls, because a single thinking block ate the per-turn output budget and was truncated.
Two false successes remain (A-02 "The implementation is complete and verified.", T-35), so a
reasoning budget does not substitute for a claim gate either.

**Still un-remeasured, and therefore not claimed:** whether an explicit "write and run your own
tests" instruction still *harms* pi at 32k. The 9-of-10 length-truncated tail runs that finding
rested on were an 8k artifact, so that paragraph below is now only known to hold at 8k.

### 8c. Our harness at 32k — the other half of the fairness gap, and an unfavourable result

Every recorded harness arm used the 8192-token server, so the comparison in 8b would have been
unfair to *us*. The `full` arm was therefore re-run on all 40 tasks, N=1, four sequential bands,
against the same 32768-token server (`bench/runs/v2sweep-20261006T040753Z`, `...T041641Z`,
`...T042104Z`, `...T042844Z`).

| arm (all 40 tasks, N=1, same grader) | actual | claimed | missed | **FALSE** | mean cost |
| --- | --- | --- | --- | --- | --- |
| harness `full`, 8k server (33 tasks) | 20/33 (61%) | 12 | 8 | 2 | 96 s, 10.2 calls |
| **harness `full`, 32k server (40 tasks)** | **22/40 (55%)** | 14 | **11** | **3** | 47 s, 8.5 calls |
| **pi CLI, reasoning max + 32k (40 tasks)** | **27/40 (68%)** | 29 | 0 | **2** | 131 s, 8.9 turns |

**pi's claim columns are not the same measurement as ours.** pi has no claim gate: its
"claimed" is this driver's regex reading of its final assistant message, so "missed" is 0 by
construction and its non-claims are *empty* final messages (a truncated turn at the output cap),
not an admission of failure — 11 non-claiming tasks, of which 10 end with a completely empty
message and the eleventh stops mid-sentence ("Let me search for any spec, corpus, or test hints
related to this task."). pi was never asked to state a claim, so that instrument measures nothing
about honesty. Only `actual` and `false success` are comparable across the two; on those, pi
asserted success on a wrong result twice and we did so three times (section 8d).

On the 21 tasks measured under both harness configurations, 8k fixed 16 and 32k fixed 14: **more
context did not make our protocol better** (our prompts and evidence are bounded, so the window
was not our limiter), and on the whole set we are now **five tasks behind a mature CLI that we
previously recorded as tied**, with one more false success. That is the honest headline.

**Where the eleven missed wins went** (grader passed, the harness did not claim):

| blocker | count | tasks |
| --- | --- | --- |
| `independent-test-red-on-final` | **8** | T-06, T-10, T-12, T-19, T-20, T-21, T-22, T-35 |
| `ladder` (the escalation ladder ran out) | 3 | T-02, T-17, T-30 |

The dominant blocker is not the model, it is our own independently authored verification: in the
cases examined, its test **asserts the pre-fix behaviour** and turns red precisely because the bug
was fixed — T-10's IV test demands `pytest.raises(IndexError)` for the crash the request asks to
remove; T-22's asserts `["Zoe", "alice"]`, the ordering the request calls wrong; T-06's passes on
the buggy code and fails on the fixed code. Because we already record each IV test's outcome on
the original and the final revision, the signature is deterministic: `iv_inverted_tests`
(final-red, original-green, 3 of the 5 examined here) versus `iv_unmet_tests` (red on both, i.e.
genuinely unaddressed or an unsatisfiable test — T-12's test is red on both revisions and T-21's
suite demands both "raises" and "does not raise"). The three false successes all ended
`stop=green`, i.e. own test green, independent test green and review approved on a revision the
grader rejects — the opposite failure of the same weak-model test-authoring problem.

Working record and the open decision (may an inverted-test block be sent to the judge, or does
the rule stay absolute): `.scratch/26-pi-maxed/issues/26-pi-maxed.md`.

### 8d. Why our actual pass rate is lower: the seven tasks only pi fixed

The gap holds seven tasks on pi's side (T-01, T-05, T-07, T-14, T-16, T-28, T-31) against two on
ours (T-33, T-35). Reading the per-attempt records, **six of the seven are our own machinery, not
the model's capability:**

| task | what the records and the delivered bytes show | whose defect |
| --- | --- | --- |
| T-01 | `touched_files: []` on all six attempts; six refusals of `auth/sessions.py`. The bug is `auth/config.py: SESSION_TTL_SECONDS = 60`, and **config.py was in the run's view on every attempt** (`spec.files` carries README.md, auth/__init__.py, auth/config.py, auth/sessions.py). pi read all four files and edited config.py in one turn | refusal loop: no redirect, and M1 says "regenerate … from the failure history as your only intelligence" |
| T-05 | own test red, 10 calls; the delivered `tagger/notes.py` is **byte-identical to the buggy original** (no `tags=None` guard). The same code fixed this task at 8k (18 calls, different own test) | M1 erase + no delivery check |
| T-16 | our own test was CORRECT (two carts, `cart2.contents() == []`); the delivered `cart/cart.py` differs from the buggy original by **one trailing newline** | M1 erase + no delivery check |
| T-13 | delivered a whitespace-only change | M1 erase + no delivery check |
| T-31 | per-attempt writes alternate `transport.py` / `client.py`; the spec and AC-2 name all four artifacts and the coverage gate listed them, but one file per attempt + an M1 erase means the changes never coexist | no multi-file write path; M1 erase |
| T-07 | own test died with ImportError, then independent test red; fixed at 8k (16 calls) | self-test loop |
| T-14 | fixed at 8k in 5 calls; at 32k the graded review marked all three criteria `violated` | review-driven iteration |
| T-28 | one attempt, own test never written, independent test `unobserved`, review approved a class where the repo's own README (in the run's view) documents module-level functions | gate correlation |

**The single clearest number: five of the forty runs delivered nothing.** Comparing each
delivered work tree against the task's pristine sources, file by file (non-test `.py`): T-01 and
T-05 and T-34 changed nothing at all, T-13 changed only whitespace, and T-16 changed only a
trailing newline. All five failed the grader, and **pi fixed three of them** (T-01, T-05, T-16).
In all five the LAST attempt was an M1 erase attempt (`_mode` returns M1 after any `same` or
`undecided` verdict; the prompt then says the draft was erased and to regenerate from the failure
history). Nothing in the pipeline checks, before handing the revision over, that it differs from
the baseline in any file the request named.

Details worth stating plainly:

- **T-01's refusal is correct, its consequence is not.** `auth/sessions.py` is in the task's
  `UNTOUCHED` contract (byte-identity), so refusing the write is right; the message says
  "grader-owned path", which is misleading (the file is visible but frozen), and the loop then
  counted six identical attempts and exited on `same-verdict tail` without ever prompting the
  model to write a *different* file. The write-guard and the coverage gate both fire *after* the
  model has chosen a target, so nothing in the loop is forced to re-plan.
- **T-31 is the multi-file case the M1 erase cannot survive.** `_mode()` picks M1
  (`_erase_draft`, which restores every written file to its pristine content) after any `same` or
  `undecided` verdict; the write seam accepts one implementation file per attempt. A task whose
  fix spans four files therefore cannot accumulate: the record shows exactly that oscillation,
  and the run died on `attempt-cap` with the request-coverage gate naming the untouched files.
  Best-evidence capture is ranked by *evidence* (own test / independent test / review), never by
  how much of the required surface a revision covers, so the multi-file revision was not saved.
- **The three false successes are one path, not three accidents.** All three (T-26, T-28, A-05)
  ended `stop=green`, `claimed_basis=review`, **`self_test: null`** (no own test was ever
  written) and **`iv approved=false`** (`independent-test-unobserved` for T-26/T-28;
  `independent-test-not-discriminating` for A-05, whose 22-test suite pinned only AC1-4 while
  AC5-21 were marked `satisfied` by the review). `claim_decision`'s own docstring makes this
  deliberate: a vacuous or non-discriminating independent test "is NOT a red verdict and does
  not block", and rule 6 lets a review carry the claim when the own test was never written. The
  cost is that when the model keeps its own wrong reading, its own test, its independent test and
  its reviewer all inherit that reading — agreement between checks that share the generator is
  not evidence. pi has the same weak judge but no gate, so it lands in the same trap less often
  (two false successes) only because its loop keeps working instead of declaring green early.
  These are **not** requirement-extraction failures: T-26's request states verbatim that the port
  "must keep the old dict-style access working" and the delivered plain `@dataclass` has no
  `__getitem__`, and T-28's required module-level API is printed in the repo's own `README.md`,
  which the run was shown.

**A gap that limits this forensics.** The per-attempt MODEL OUTPUT is not persisted: the record
keeps `claimed_delta` (the model's own one-line summary), `touched_files` and the failure
signature, but not the `file_path`/`content` the envelope carried. So "did the model emit a no-op
file, or did something revert a real fix?" can only be inferred from the delivered bytes plus the
M1 mode, not read off directly. Capturing the envelope content (or its hash) per attempt is a
prerequisite for the next round.

None of these was fixed in this round: the sweep had to stay on one code revision, and the fixes
change behaviour the owner has opinions about (the M1 erase, the early-exit ladder, the review-only
claim path). They are the concrete agenda for the next round, in this order — refusal redirect,
multi-file accumulation / coverage-ranked best-evidence, then the review-only claim path.

**Asking a small model to write its own tests made a mature CLI WORSE (measured at 8k; see the
caveat above).** On the same 40
tasks, pi with the request alone fixes 21; with an explicit "write test files that fail on the
buggy code and pass once fixed, then run them" instruction it fixes **16** (per band: 7/10,
4/10, 4/10, 1/10 versus 9, 7, 5, 0). The behavioural trace explains why: the 4B cannot emit a
whole test file as a tool argument (the write hits the output-token limit and is dropped, then
re-issued), and it burns its response/context budget on the attempt - in the last band **9 of
10 runs ended on a length-truncated thinking block**, i.e. it stopped because it ran out of
tokens, not because it had finished. That is the measured reason the harness writes its own
test in small, checked steps and keeps the self-test optional rather than mandatory: for this
class of model, "go write tests" is a cost centre, not a quality lever.

**Behavioural contrast.** pi really iterates: it runs shell commands in every run (ls/find/grep,
ad-hoc `python3 -c` assertions) and self-corrects when its own scripts fail. Its two structural
weaknesses are that the 4B cannot emit a whole test file as a tool argument (the write hits the
output-token limit and is re-issued or lost), and that pi ends the run the moment the model
answers without a tool call - a one-shot headless run has no user turn to say "continue", so an
unfinished task simply ends (this is where its run-to-run variance comes from).

## 5. Where the evidence lives

- Run records: `bench/runs/**/run.json` (per node: stop reason, ledger rows, verification
  basis, coverage, manager decisions, budget accounting) and `results.jsonl` for sweeps.
- Curated evidence kept in the repository: `bench/runs/evidence/`.
- Work records: `.scratch/NN-*/issues/*.md` (ticket 21 covers the claim model; ticket 20 the
  How axis and its measured verdict; tickets 17–19 the leaf, the tree and the covenant).
- Design: `docs/DESIGN.md` §10 (flow) and §10.10 (implemented vs not built).

## 6. Recommended next steps (ordered)

1. **The claim rule is settled by measurement; do not re-open it without new numbers.**
   Three rules were measured on the same tasks and model (section 1): the owner's
   review-outranks-tests rule, once requiring grant-calibre evidence, claims twice as many
   true successes as the conservative rule at the same measured false-success count (0), and
   the two false successes the unhardened rule produced are refused by the evidence rule.

2. **Attack the remaining missed-success bucket (4 of 18).** Every case's ledger says which
   criterion was unverifiable and which check was attempted; two of the four are T-33, whose
   criteria name a file the task freezes (a criterion/corpus mismatch worth fixing in the
   task, not the harness).

3. **The independent test is still the weakest link** (14 attempts, 3 repairs, and it was the
   blocker in the earlier conservative sweep). A stronger verifier model - even a modest
   remote one - for the test-authoring and review roles is the single change most likely to
   raise true successes; every run records whether its verification was independent or
   reviewed, so the effect would show in the very next sweep.

4. Build the designed-but-unbuilt layers only if a task needs them: requirement triage,
   model-side context curation, worktrees/parallel trees, a human-facing piloting surface
   (DESIGN §10.10).

## 7. Reproducing the numbers

```sh
# unit gate (no model required) — includes the repo tamper guard and corpus integrity
uv run pytest

# one task, leaf flow, with the ledger and claim record
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one --calls 24 --deadline-hours 0.25

# the headline sweep (claimed vs grader), nine tasks, two runs each
uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-03-wrong-comparison,T-05-mutable-default,T-08-add-cache-invalidation,T-14-add-export-sorting,T-20-average-truncation,T-25-chunked-helper,T-31-parameter-threading,T-33-serializer-contract --n 2 --calls 24
```

The reference model server used for every number above:

```sh
llama-server \
  -m /home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf \
  --port 8833 --host 127.0.0.1 -ngl 99 -c 8192
```

`curl -fsS http://127.0.0.1:8833/health` must answer `{"status":"ok"}` before a sweep.

## 8. Mature agent CLI baseline (the same model, the same tasks)

`bench/pi_baseline.py` runs the real **`pi` CLI headless** against a corpus task with the same
blind staging (source-only; the grader never enters the run) and scores it with the same
external grader. Same 4B reference model, same llama-server, temp pi agent dir (the owner's
real config is never read or written).

| agent | T-02 | T-05 | T-31 | actual | claimed |
| --- | --- | --- | --- | --- | --- |
| our harness (newest sweep, N=2) | 2/2 | 1/2 | 0/2 | 3/6 | 0/6 |
| **pi CLI** (2 passes, 1 run each) | 1/2 | 1/2 | **2/2** | **4/6** | 4/6 |
| our own minimal agent loop (`bench/v2_agent.py`) | - | - | - | 0/6 | n/a |

**Behavioural evidence (the important part).** pi drives a real tool loop - `read`, `bash`,
`edit`, `write` - and **ran shell commands in every run**, iterating on their results; that is
exactly what our minimal loop could not do. It wrote **no tests**: the 4B could not emit a
whole test file as a tool argument (it hit the output-token limit and the write failed), so
its verification was ad-hoc `python3 -c` assertions. Its dominant failure mode is structural:
pi **ends the run when the model returns an assistant message with no tool call**, and the 4B
does that prematurely (turn 4, turn 8) - in one-shot headless mode there is no user turn to
say "continue", so an unfinished task simply ends. That is where most of the run-to-run
variance (3/3 vs 1/3) comes from.

**What this shows, and what it does not.** On three tasks the mature CLI is at least as good
as the harness on the grader's verdict, and it claimed far more (it has no claim gate at
all - its "claims" are our reading of its prose). It does **not** establish a general rate
(three tasks, one or two passes each), and the comparison is not apples-to-apples: pi has no
call budget, no honesty gates, no evidence ledger, while the harness caps calls and refuses
unverified claims. The honest reading: on a small model a mature CLI's loop is competitive,
so the harness's contribution is not "it fixes more easy tasks" - it is the blind scoring
protocol, the deterministic gates, the evidence trail, and the fact that its claims can be
audited. The harness also covers nine tasks and the structural work (trees, budgets,
escalation) that a one-shot CLI run does not do at all.
