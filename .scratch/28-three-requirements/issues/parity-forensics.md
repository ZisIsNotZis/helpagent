# Trajectory forensics — why our pure-coding outcome does not match maxed `pi` on the same 4B

Ticket 28, Q1 (diagnosis). Read-only on all code and existing docs; the only writes are this
file and its campaign root.

**Revisions.** Our arm: `bench/runs/v2sweep-20261011T065821Z` (T-01..T-20) and
`bench/runs/v2sweep-20261011T070710Z` (T-21..A-05) at `d24410a`. The campaign measurement the
ticket names is the 2026-10-09 set at `6b224f5`, which I reconstructed from the three banded
directories that produce its published numbers (below). `HEAD` is `72538ab`; the only harness
change after `d24410a` is P8c (`24d801e`, claim rules), which cannot change a grader verdict.
pi evidence: `bench/runs/evidence/pi-maxed-20261006/` (thinking max, reasoning, 32k).

**Method.** For every divergence I (1) read the per-task `trajectory.jsonl` and the delivered
work tree, (2) took every revision the run actually wrote, (3) applied it to a pristine copy of
the task's corpus repo in `/tmp` and ran the withheld grader suite, and (4) read the grader's own
verdict on the delivered bytes in the run record. Every "would have passed" claim below is a
re-run of the withheld tests, not an inference. Where a file was unreadable I say so.

---

## 1. Where the two arms actually stand

| arm (same 4B, 32768-token server, blind, external grader) | actual | claimed | false |
| --- | --- | --- | --- |
| ours, `6b224f5` (2026-10-09 campaign) | **24/40** | 11 | 3 |
| ours, `d24410a` (2026-10-11 runs `...065821Z` + `...070710Z`) | **26/40** | 10 | 1 |
| pi, thinking max + reasoning + 32k (`pi-maxed-20261006`) | **27/40** | 29 | 2 |

**Reconstruction of the `6b224f5` set** (the published 24/40 has no single run directory): the
three banded directories on 2026-10-09 give 5/5 (`...T114753Z`, T-01..T-05), 12/15
(`...T114754Z`, T-06..T-20) and 7/20 (`...T120918Z`, T-21..A-05). Their failures are *exactly*
the 16 the ticket lists — `A-01..A-05, T-13, T-24, T-26, T-27, T-32, T-34, T-35` (both fail) plus
`T-07, T-14, T-28, T-30` (pi-only wins) — and 5+12+7 = 24. I treat those three directories as the
`6b224f5` measurement; the per-task quotes below are read from them.

**Divergences, latest revision (`d24410a`).** pi passes 27, we pass 26.

| | tasks |
| --- | --- |
| pi wins only | **T-17**, **T-28** |
| we win only | T-33 |
| both fail (12) | A-01, A-02, A-03, A-04, A-05, T-13, T-24, T-26, T-27, T-32, T-34, T-35 |
| both pass (23) | the rest |

**Divergences, `6b224f5`.** pi wins only T-07, T-14, T-28, T-30 (4); we win only T-33 (1);
both fail 12 (`A-01..A-05, T-13, T-24, T-26, T-27, T-32, T-34, T-35`); both pass 23.

So the live parity gap is **2 tasks (T-17, T-28)** on the current revision, and 4 (T-07, T-14,
T-28, T-30) on the campaign revision. Of the campaign losses, **T-07, T-28 and T-17 are pure
harness defects** with a grader-verified passing revision inside the run (below); **T-30**'s loss
was a false-success claim that P8b has since closed; **T-14** is model content in that run (no
revision passed) but the process defects around it still stand (§2.4). The 12 shared failures are
not parity losses and closing them is not required for parity.

"our wins T-33/T-35" (from `STATUS §8b`, the 8k-harness vs 32k-pi comparison) is not what the
current runs show: T-33 is a win over pi (pi fails it: 4 turns, empty final message), and **T-35
is a failure for both arms on both revisions** — in `6b224f5` we *claimed* it while the grader
failed it (a false success), in `d24410a` the run ended after 3 calls (§2.7).

---

## 2. Per-task deviation forensics

Each entry: the run, the first step where the run left a path that would have passed, the quoted
evidence, the responsible code path, the minimal change, and the verdict.

### 2.1 T-28-plugin-registry-scaffold — our-defect (delivered a failing revision over a passing one it had just written)

Run `v2sweep-20261011T070710Z`, `work/plugins/registry.py`, sha256 `a801efc3…` (1442 bytes).

The withheld suite is `tests/test_plugins.py`; it calls the module-level API
`registry.register/get/run` (grader notes on the delivered bytes:
`FAILED tests/test_plugins.py::test_get_unknown_raises - AttributeError: modul...`,
`4 failed in 0.02s`). The request says "The design doc calls the module plugins/registry.py" and
the repo's own `README.md` (in the run's view) states
`Plugin registry: register(name, fn) / get(name) / run(name, *args).`

**The passing revision existed in this run.** Attempt 4 (`leaf_attempt n=4`, seq 622) wrote
sha256 `e8484d8b…`, which adds the module-level convenience API:

```python
registry = Registry()

def register(name, fn):
    registry.register(name, fn)
```

I applied that content to a pristine copy of `bench/corpus/T-28-plugin-registry-scaffold/repo`
and ran the withheld suite: **`4 passed`**. The delivered revision fails **4/4**.

**First deviation point.** seq 619 `best_evidence_revision {rank: 1, tier: "review", attempt: 2,
reason: "a combined-positive graded review approved the diff"}` is taken from attempt 3's
revision — and **one event later**, seq 620:

```json
{"event": "documented_api_missing", "data": {"missing": ["the repository documents get, register, run
 as module-level names; your plugins/registry.py exposes them only as methods of Registry"]}}
```

i.e. the harness snapshots a revision and then, in the same breath, its own deterministic check
declares it non-compliant. Every later attempt is taken in mode `M1` (erase), so the rank of the
passing attempt 4 revision is 0 (its two reviews were refused by `review_not_grant_calibre`), and
`restore_refusal_reason()` cannot refuse a `review`-tier snapshot. The run ends:

```json
seq 669 leaf_stop {"signal": "honest-failure", "claimed": false, "calls": 24, "reason": "attempt-cap",
                   "stop_reason": "attempts"}
seq 670 delivered_best_evidence {"rank": 1, "tier": "review", "attempt": 2, ...}
seq 671 documented_api_missing {"missing": ["the repository documents get, register, run ..."]}
seq 674 DELIVERY {"grader_passed": false, "grader_notes": ["... 4 failed in 0.02s", "result: FAIL"]}
```

The harness delivered a revision that its own check rejected, one event after re-running it, while
holding a grader-passing revision from the same run.

**Responsible code path.** `harness/leaf.py::capture_best_evidence` (≈5767) and
`::note_current_evidence` (≈5792) rank only *model-written evidence*
(`BEST_EVIDENCE_ORDER` = agreement > independent-test > own-test > review);
`::restore_refusal_reason` (≈5795) vetoes **only** the `own-test` tier and **only** on
`coverage_missing`; the deterministic check `::documented_api_problem` (≈4039) is computed at the
review-approval site *after* `note_current_evidence` (call order: ≈8382 then ≈8411), and never
reaches either function.

**Minimal change.** Attach the deterministic verdicts (documented-API, request-coverage,
requirement-coverage) to the snapshot at capture, and use them in both directions:
(a) `restore_refusal_reason()` refuses **any** tier whose snapshot revision leaves a deterministic
contract check failing (today only `own-test` + `coverage_missing`); (b) the first revision that
**clears** a check the current best fails is captured as evidence (rank ≥1, tier
`contract-clear`), so the passing attempt-4 revision outranks the review snapshot. ~20 lines, no
new model calls (the run would end earlier).

**pi's path.** 8 turns, 105.0 s, `actual=True`, `wrote_test=False`; it read the README and wrote
the convenience API: *"**Convenience API** (backed by a default registry, matching the README's
`register(name, fn)` / `ge…"*. Same model, same task, same information.

### 2.2 T-17-log-hour-format — our-defect (the model's own bad test outranked four correct revisions)

Run `v2sweep-20261011T065821Z`. Grader on the delivered bytes:
`FAILED tests/test_parser.py::test_morning_hour_unchanged - ValueError: time d...`, `2 failed`.

Revision-by-revision grader re-runs (pristine corpus copy + withheld suite):

| write seq | run's verdict on the grader |
| --- | --- |
| 1219 (attempt 1) | **2 passed** |
| 1228 (attempt 2) | 2 failed |
| 1240 | **2 passed** |
| 1251 | 2 failed |
| 1257 | 2 failed |
| 1265 | **2 passed** |
| 1273 (terminal) | **2 passed** |

The correct revision (`sha256 77cc9fd7…`, 371 bytes) was written **four times** (seq 1219, 1240,
1265, 1273); the delivered bytes are the one-off wrong revision (`3ae7dd6f…`, seq 1228), chosen by
`best_evidence_revision {rank: 2, tier: "own-test", attempt: 1, reason: "the run's own
discriminating test is green"}` because `terminal_rank: 0`.

**First deviation point.** the run's own test, seq 1215 (`write_test`), which pins the input shape
wrongly:

```python
def test_afternoon_timestamp():
    line = "2023-10-26 14:30:00 INFO message"
```

The file the run is editing states the shape in its own docstring — visible on every attempt:
`Line shape: "<YYYY-MM-DD HH:MM:SS> <LEVEL> <message>"` (with the angle brackets), and the
withheld grader uses exactly that (`parse_ts("[2025-06-01 14:30:00] INFO boot ok")`). The model's
test therefore fails on the *correct* fix, the run "fixes" the parser to match its own bad fixture
(judge verdict seq 1245: *"The parser extracts the timestamp from the wrong slice (line[1:20]
instead of line[0:19])"*), and that revision greens the bad test → rank 2 → delivered.

**Responsible code path.** `capture_best_evidence` ranks own-test-green as the second-strongest
evidence; `_own_test_partition` (≈3187) classifies both own-test nodes as *discriminating* (they
fail on the pristine source) and nothing checks the fixture against the staged source's own
documentation; `restore_refusal_reason()` returns `""` because `coverage_missing` is empty, so the
snapshot is restored.

**Minimal change.** extend the own-test admissibility rule (`_own_test_partition` /
`_own_test_contradictions`, the P3d/FIX-1 family) with the visible-doc fixture check: an own test
whose literal inputs contradict a fact stated in the staged source's own docstring/README (here
the line shape) is not admissible evidence and cannot be snapshot as rank 2. Verified outcome:
with the restore refused, the terminal revision (seq 1273) is delivered → **2 passed**.

**pi's path** — the contrast is the whole finding. pi's own trace at T-17 (8 turns, 60.6 s,
`actual=True`): *"My test line used the wrong format. The actual log format is `<YYYY-MM-DD
HH:MM:SS> <LEVEL> <message>`. Let me retest with the correct format:"* — same model, it diagnosed
its own fixture from the visible docstring and corrected it. Our harness instead promoted that
fixture's verdict to ground truth and delivered the revision that satisfied it.

### 2.3 T-07-f-string-sql — our-defect (4 of the 6 written revisions pass the grader; the run delivered one of the two that do not)

`6b224f5` run `v2sweep-20261009T114754Z`. Grader on the delivered bytes:
`FAILED tests/test_store.py::test_name_with_apostrophe_round_trips - sqlite3.O...`,
`contacts/store.py:23: OperationalError`.

| write seq | grader re-run on a pristine copy |
| --- | --- |
| 40 (attempt 1) | **2 passed** |
| 49 (M2 resample, noop) | **2 passed** |
| 56 (after M1 erase) | 2 failed |
| 62 | **2 passed** |
| 68 | **2 passed** |
| 75 (terminal, delivered) | 1 failed, 1 passed |

The delivered bytes (sha256 `82a15f89…`) fix `add_contact` and **revert `find_email` to the original
f-string** (`conn.execute(f"SELECT email FROM contacts WHERE name = '{name}'")`) — the statement
the correct attempt-1 revision (`ee45fb88…`) had already parameterised. The attempt-1 revision was
never delivered because the run's own test never went green on any revision, so no snapshot ever
reached rank ≥1.

**First deviation point.** seq 36 (`write_test`) writes an own test whose assertion SQL is itself
malformed:

```python
add_contact(conn, "O'Brien", "obrien@example.com")
assert conn.execute("SELECT email FROM contacts WHERE name = 'O'Brien'").fetchone()[0] == "obrien@example.com"
```

That assertion can never pass on *any* revision. After attempt 1 fixed the source, the failure
moved into the test — the harness's own excerpt says so, and kept saying so on all six attempts:

```
    add_contact(conn, "O'Brien", "obrien@example.com")
>   assert conn.execute("SELECT email FROM contacts WHERE name = 'O'Brien'").fetchone()[0] == "obrien@example.com"
E   sqlite3.OperationalError: near "Brien": syntax error
test_contacts.py:11: OperationalError
```

The model even flagged it — seq 44 judge answer: `{"status": "failed", "comment": "Failure stems
from the store's use of unescaped string literals in SQL queries.", "blame": "test", ...}` — and
the deterministic filter overrode the label:
`judge_coerced {"reason": "test_wrong without a defect naming the failing test or one of its
assertions (deterministic filter)"}`. From there the attempt verdicts `same`/`undecided` drive
`_mode()` → `M1` → `_erase_draft` (≈8071-8076) on a correct draft, every rung of the ladder is
recorded `escalation_wasted {"reason": "identical attempt refused: same signature/files/claim"}`
(the failure *signature* is identical because it is the same exception on a different line), and
the run stops `ladder` / `ladder-exhausted` with `actual=false`.

**Responsible code path.** `harness/leaf.py::apply_judge_filter` (≈3725) credits `test_wrong` only
when the judge's prose names the failing test/assertion, although the harness already holds the
deterministic fact (the traceback has **no** frame in a changed source file and **one** frame in
the own-test file); `_mode` (≈3488) then erases the draft; `capture_best_evidence` has no
deterministic anchor, so a correct revision with no model-written green is invisible.

**Minimal change.** credit `test_wrong` deterministically when the recorded failure's traceback
contains no frame in a changed non-test source and at least one frame in the run's own test file,
routing into the existing repair path (`if verdict.test_wrong and self_test:` ≈6440) — and never
M1-erase a draft while the last failure is test-attributed. Effect: the own test is repaired
instead of the source being churned, the attempt-1 correct revision survives, and (with §2.1's
anchor) it is delivered. Same rule reaches T-35 (§2.7).

**Latest revision, same task.** `v2sweep-20261011T065821Z`: all five written revisions pass the
grader and the delivered bytes pass; the run is an *unclaimed* pass (`stop=ladder`) because the
independent test has two nodes that assert the **pre-fix crash**:
`with pytest.raises(sqlite3.IntegrityError): add_contact(conn, "O'Brien", "obrien@example.com")`
(in `test_ac1_apostrophe_crash` / `test_ac2_db_error`; `sqlite3` is never imported, so they error
rather than assert). `iv_inverted=false`, `iv_unmet_tests` non-empty → treated as a hard red that
blocks the claim and burns the ladder.

**pi's path.** 9 turns, 37.7 s, `actual=True`; final text *"both `add_contact` and `find_email`
interpolated raw user input directly into SQL strings using f-strings"* — it fixed both sites
without writing a test at all.

### 2.4 T-14-add-export-sorting — model content + our-defect (a documented behaviour was deleted and nothing deterministic noticed)

`6b224f5` run `v2sweep-20261009T114754Z`: **all six written revisions fail the grader**
(`test_totals_are_formatted_with_two_decimals`, and the ordering test on some). The run's own test
was **correct** — seq 213 writes `reporting/test_export.py` asserting the tuple form
(`assert result == [("apple", "200.00"), …]`). The model's revisions nonetheless deleted the
pristine's tuple+formatting return:

```python
    return sorted(
        rows,
        key=lambda r: r["customer"].lower(),
    )

    return [(r["customer"], f"{r['total']:.2f}") for r in rows]   # seq 223/232: now dead code
```

seq 239/256 are byte-identical to the pristine (a no-op revision) and seq 246/263 are
`return sorted(rows, key=lambda r: r["customer"].lower())`, i.e. raw dicts. So the model traded a
documented behaviour for the one it was asked to change, four times, and the run ended
`spec-bubble` after the judge blamed the spec (`claimed_delta: "judge attributed the failure to the
spec"`) — the last attempt did not fix anything either.

**What the harness had in hand.** The module's own docstring, visible on every attempt, states the
contract the model broke: *"Each exported row is `(customer, total formatted with two decimals)`"*,
and the README repeats *"Totals are formatted with two decimals."* The P3d documented-contract check
covers only **call-form names** (`documented_api_names`), so a deleted documented **return shape /
behaviour** is invisible to every deterministic gate; the only feedback was the model's own test
(which it also had, and ignored) and the judge.

**Verdict.** Content: model-ceiling for this run (no revision passes; pi needed 374.9 s and 29
turns — the longest run in the pi set — to pass it). Process: our-defect — a documented behaviour
present in the baseline and stated in the visible docs can be deleted with no deterministic flag,
and §2.7's spec bubble ended the run. On the **latest revision** the same task passes the grader;
it is unclaimed because the IV test is non-discriminating on AC2/AC3
(`independent-test-not-discriminating: … the node selection for AC2, AC3 still PASSES on the
pre-run source`) and the run spends 23 calls on it.

**pi's path.** 29 turns / 374.9 s, `actual=True`, and it kept the tuple form: *"`export_rows` …
exported rows in the raw input order, contradicting the documented promise…"*.

### 2.5 T-30-naive-datetime-compare

`6b224f5` run `v2sweep-20261009T120918Z`: **all six revisions fail the grader** (worst case is a
`NameError: name 'time...` — the delivered revision uses `timezone` without importing it), stop
`green`, `claimed=True`, basis `review` → a **false success** (one of the three in `STATUS §8e`).
Claim route: the independent test had errored on both revisions (`0 failure(s), 3 error(s)`) and
an errored independent run counted as non-blocking. **This claim hole is already closed** at
`d24410a` by P8b (`iv_verdict_is_non_discriminating`, state 2, ≈1833) — the latest run for the same
task is an honest, unclaimed pass.

Latest revision: 3 of 5 revisions pass, the delivered bytes pass; unclaimed because one IV node is
recorded `iv_inverted` (`tests/test_tokens.py::test_ac1_naive_input_no_raise` — green on the
pristine source, red on the final) and one is `iv_unmet` (`test_ac3_naive_treated_as_utc`). The gap
is that `iv_all_inverted` (≈1801) excuses a red only when **every** failing node is inverted; one
unmet node keeps the whole check as a hard block, and the run ends `ladder` after 22 calls. The
inverted node's scenario (`issue(naive)`) is outside the contract the run can see (`README`: "All
datetimes are tz-aware UTC"; request: "don't change issue()"; the grader always issues tz-aware),
so it is a false red on an in-contract fix.

Defect, verification axis: a red IV verdict whose failing nodes are individually inadmissible
(inverted, or asserting a scenario the visible contract excludes) should be dropped rather than
end the run — the same treatment `iv_all_inverted` already gives the all-inverted case. Effect:
claims and calls, not the grader verdict today (the delivered revision already passes).

### 2.6 T-33-serializer-contract — our win, but the win is silently unclaimed

Latest run: the delivered bytes pass the grader; the run stops `independent-test-red-on-final` with
`iv_unmet_tests: ['tests/test_serializer_contract.py::test_ac2_violation_checks']`. That node is the
model's independent test asserting the **pre-fix violations** the request asks to remove:

```python
    # JSON mangles non-ASCII names (fails to roundtrip correctly)
    assert loaded != obj
    with pytest.raises(UnicodeDecodeError):
        ...
    with pytest.raises(pickle.UnpicklingError):
```

It is classified `unmet` (it fails on the pristine too, for a different reason), so the inversion
rule does not excuse it. The harness has exactly this rule for the **own** test (P3a:
`own_test_symptom_ids`, "self-tests may not assert the symptom", rewritten then dropped ≈7801-7827)
and no equivalent for the **independent** verification. Minimal change: extend the
symptom-assertion rule to the IV — an IV node that asserts the behaviour the request calls broken
is not evidence against the revision. pi fails T-33 (4 turns, empty final message), so this one is
ours to keep; only the claim is lost.

### 2.7 T-35-interval-merge-invariants — our-defect (the run was ended after 3 calls by a self-contradicting judge label)

Latest run, `user calls = 3`, `attempts = 1`, `stop_reason = spec-bubble`, delivered revision
`{}`. The run's own test (`spans/test_merge.py`) calls `merge(...)` **without importing it**, so
its four nodes fail with `NameError: name 'merge' is not defined` on every revision. The judge was
handed that failure and answered (seq 1207):

```json
{"status": "failed", "comment": "Defect is in the source merge implementation.", "blame": "spec",
 "problem": "The merge function uses 'start <= current_end' which incorrectly merges touching
 intervals instead of the required half-open [start, end) contract that only merges when start <
 current_end."}
```

`judge_verdict {spec_wrong: true, coerced: false}` → `spec_bubbled_up` → `stop("bubble",
"spec-bubble", "spec-bubble", parent=True)` → the node ends after one attempt. **Responsible code
path:** `harness/leaf.py::apply_judge_filter` (≈3725) — its docstring is explicit: *"``spec_wrong``
and ``environment_broken`` pass through: the loop's decision is dominant-first, and a bogus
spec/environment claim only parks or bubbles, never claims."* `_judge_incoherence` (≈3712) checks
only the `test_wrong` / `implementation_wrong` labels, so a `spec_wrong` verdict that contradicts
its own `comment`/`problem` (both of which name a source defect) bubbles unchecked. The stop site
is the `if verdict.spec_wrong:` block (≈6412-6429).

**Minimal change.** (a) extend `_judge_incoherence` to `spec_wrong`: a spec verdict whose own
comment/problem names a source defect, or reached when no observed failure has a frame in the
changed source, is not credited; (b) require ≥2 attempts before a spec bubble may end a node.
Cost is small. Expected effect is **not** a guaranteed flip: the grader also rejects the written
merge (it returns lists where the withheld test expects tuples and does not drop empty spans:
`test_empty_intervals_dropped - assert [[1, 3]] == ...`, 6 failed). The effect is a fair chance
(9-attempt cap) instead of a 3-call stop. Both arms fail this task in the end (pi claimed it and
failed), so it is not a parity loss.

### 2.8 A-02-protein-translation (the one remaining claim miss)

`v2sweep-20261011T070710Z`: `claimed=true`, `actual=false` → the last false success on the run set
I read. It is **already closed** at HEAD: P8c (`24d801e`, not in these runs) refuses any claim
whose only deterministic green is `source-compiles`, and `STATUS §8h` reports 0 false successes on
the post-P8c probe. pi also falsely claimed A-02, so it is not a divergence.

---

## 3. Classification

**Our-harness-defect (fixable, mechanism named above).** T-28, T-17, T-07, T-35 (early stop),
T-33/T-30/T-14/T-07 (claim + churn on the latest revision), and T-14 (`6b224f5`, process only: a
documented behaviour deleted with no deterministic flag + the spec bubble). Every one has a
deterministic fact the harness had in hand and did not use, or a delivery decision made without
one; none of them needed a better model.

**Model content (content-side ceiling, no harness fix available on this evidence).** T-14's
`6b224f5` revisions (six written, none passing) — pi passes it but needs 29 turns / 374.9 s, its
longest run. This is the only divergence where no revision of ours would have passed.

**Model-ceiling (of the divergences: none of the parity losses).** The 12 shared failures
(`A-01..A-05, T-13, T-24, T-26, T-27, T-32, T-34, T-35`) are not divergences — both arms fail them
with the same model, and `STATUS §8f` gives each a quoted grader failure on the delivered revision.
Reading them as ceiling is supported by the second arm (a maxed CLI with no harness machinery fails
the same 12) but **not proven per task by this ticket**: a real model-ceiling verdict needs the
recurring-failure-with-quoted-deviation-point reading for each, which is V3 work (`§8f` states the
same limit). T-35 is the one I opened: its grader failures are code-level (list vs tuple, empty
spans not dropped) and recur after the harness's own path is inspected — but the run was truncated
at 3 calls, so it cannot yet be labelled ceiling with confidence. The 5 anchors remain the clearest
ceiling set (whole implementations from a text spec; 0/5 both arms, and both pi and we fail them).

**Not taken at face value.** `stop_reason` is not the verdict: `green` hid the T-30 false success
(`6b224f5`), `ladder` described an *exhausted ladder* in T-07 while four grader-passing revisions
had been written and discarded, and `documented-api-missing` named a *stop* in T-28 although the run
had already written a compliant revision that the grader accepts.

---

## 4. Run-to-run variance and the error margin on a 40-task N=1 comparison

All numbers are from repeated runs of the same configuration in `bench/runs/`.

| repeat set | runs | per-run totals | tasks flipped between runs |
| --- | --- | --- | --- |
| T-01..T-20, `...T140136Z` / `...T143344Z` | 2 | 18, 15 | 3/20 (T-13, T-14, T-18) |
| T-21..A-05, `...T141712Z` / `...T144520Z` | 2 | 8, 7 | 1/20 (T-33) |
| 8-task tail ×4 (`...T151917Z`/`152436Z`/`152908Z`/`153458Z`) | 4 | 6, 6, 5, 7 | 6/8 flip at least once; pairwise flips 2-4 |

Per-task behaviour in the ×4 set: `p = .75,.75,.75,.25,.75,1,.75,1` — the easy/mid tasks are
0/1-stable, the hard tail sits at 0.25-0.75.

**Margin.** Pooling the two 20-task pairs (a full 40-task population, one pair each): 4 tasks flip
per same-configuration pair = **10% of tasks per pair** → mean `p(1-p)` = 0.05 → the SD of a single
40-task run is `sqrt(40×0.05)` ≈ **1.4 tasks**; the SD of the difference between two such runs is
≈ **2.0 tasks**. Using the tail band's own spread (mean `p(1-p)` = 0.141) the same arithmetic gives
**2.4** and **3.4** tasks. Revision changes are larger still: the same 40 tasks measured 26/40 and
22/40 across revisions (`STATUS §8e`).

**Statement that applies to the comparison.** An N=1, 40-task difference carries ±2 tasks (1 SD)
of run-to-run noise, ±4 tasks at 2 SD. Therefore the campaign gap (24 vs 27, Δ=3) is ~1.5 SD — not
evidence of a real deficit; and the latest gap (26 vs 27, Δ=1) is ~0.5 SD — parity is not excluded,
nor is a 3-task deficit. **pi's variance is unmeasured** (`pi-maxed-20261006` is N=1 per task), so
its 27/40 carries the same margin; the pi arm must be re-run with the same seed count before any
parity claim.

**Seeds needed to be defensible.** With per-task `p ≈ 0.6`: to bound the two-arm difference to
±3 tasks (7.5 pp) with a 95% interval you need ≈ `1.96²·2·0.24 / 0.075²` ≈ **328 task-runs ≈ 9 seeds
of 40 per arm**; to *detect* a 3-task difference at 80% power, ≈ 670 task-runs ≈ **17 seeds per
arm**; to detect 2 tasks, ≈ **38 seeds per arm**. A claim of "parity within margin" therefore
requires **≥9 seeds per arm** (≈330 runs), and "beats pi" requires **≥17 seeds per arm**, on one
frozen revision. Anything below that can report a number, not a finding.

---

## 5. Prioritized defect list

Ordered by (tasks recoverable × certainty) ÷ cost. "Effect" is on the **actual** pass rate, and is
grader-verified where it says so.

**D1 — delivery has no deterministic anchor: the harness can deliver a revision its own checks
reject, discarding a grader-passing revision from the same run.** (§2.1, §2.2, §2.3)
- Tasks: **T-28** (latest, verified: discarded revision passes 4/4, delivered fails 4/4),
  **T-17** (latest, verified: 4 of 7 revisions pass; the delivered snapshot fails, the terminal
  revision passes), **T-07** (`6b224f5`, verified: 4 of 6 revisions pass, delivered fails).
- Mechanism: `capture_best_evidence` / `note_current_evidence` rank only model-written evidence;
  `restore_refusal_reason` vetoes only `own-test` + `coverage_missing`; `documented_api_problem`
  (deterministic) is computed after the snapshot and never participates.
- Fix: attach the deterministic verdicts to the snapshot; refuse any tier whose snapshot fails a
  deterministic contract check; capture the revision that clears a check the current best fails.
- Effect: **+2 tasks on the latest revision (26 → 28/40)** and +1 on `6b224f5` (T-07). Both
  grader-verified by re-running the withheld suite on the discarded revisions.
- Cost: ~20 lines in `harness/leaf.py` + unit tests; **no additional model calls** (runs end
  earlier).

**D2 — a test-attributed failure is never credited deterministically, so the run edits the source
(or erases a correct draft) because of its own broken test.** (§2.3, §2.7)
- Tasks: **T-07** (`6b224f5`), **T-35** (latest, 3-call stop), T-14/T-17 (contributes).
- Mechanism: `apply_judge_filter` credits `test_wrong` only from the judge's prose, although the
  traceback proves it (`test_contacts.py:11` with no source frame); `_mode` then M1-erases the
  correct draft (`_erase_draft`, ≈8071).
- Fix: credit `test_wrong` from the failure traceback (no frame in a changed source + ≥1 frame in
  the own-test file) into the existing repair path; never M1-erase on a test-attributed failure.
- Effect: T-07 +1 (`6b224f5`) — the correct attempt-1 revision survives, the own test is repaired;
  T-35 gains a fair chance (9-attempt cap) instead of a 3-call stop, not a predicted pass.
- Cost: ~15 lines + tests; no extra calls.

**D3 — the `spec_wrong` judge label ends a node with no coherence check.** (§2.7, §2.4)
- Tasks: **T-35** (latest), **T-14** (`6b224f5`, `spec-bubble`).
- Mechanism: `apply_judge_filter` passes `spec_wrong` through by design; `_judge_incoherence`
  covers only `test_wrong`/`implementation_wrong`; the stop is unconditional at
  `if verdict.spec_wrong:` (≈6412).
- Fix: extend the coherence rule to `spec_wrong` (contradicts its own comment/problem; no source
  frame in any observed failure) and require ≥2 attempts before a bubble.
- Effect: no guaranteed flip (T-35's code is also wrong; T-14's `6b224f5` revisions all fail), but
  removes a 3-call abandonment and the T-14 `spec-bubble` exit.
- Cost: ~15 lines + tests.

**D4 — the documented-contract checks are one-sided: they see call-form names only, never a
deleted documented behaviour.** (§2.1, §2.4)
- Tasks: **T-28** (`6b224f5` attempts 1-2 are docstring-only stubs and pass the check; the latest
  run's revision 4 clears it), **T-14** (`6b224f5`: the pristine's documented `(customer, "7.00")`
  return and the docstring sentence stating it are deleted with no flag).
- Mechanism: `documented_api_problem` reports a miss only when the name exists **as a class
  method**, so a name that is absent entirely, or a documented behaviour that disappears from the
  delivered bytes, is not reported.
- Fix: (a) report a documented name that is not module-level in any target module, for modules the
  change **produced**; (b) compare the delivered revision's own docstring/README-stated behaviour
  with the baseline (a documented literal/shape the pristine had and the revision removed is a
  deterministic red).
- Effect: contributes to D1 (the stub revisions stop being deliverable/claimable); on T-14 it is a
  process gain (the run is not left to a spec bubble) rather than a flip.
- Cost: ~10 lines for (a) + tests; (b) is a new but small scan over the visible docs.

**D5 — the independent verification is model-written and unchecked against the visible ground
truth, so it manufactures reds that block correct revisions and burn the budget.** (§2.3 latest,
§2.5, §2.6)
- Tasks: **T-07, T-14** (band `...T065821Z`) and **T-30, T-33** (band `...T070710Z`) — 4 of the 17
  missed successes across the two latest runs; the 8 `independent-test-red-on-final` misses and 3
  of the `ladder` misses in `STATUS §8c` are the same family.
- Mechanism: `iv_all_inverted` excuses only an *all*-inverted red (`iv_unmet_tests` non-empty keeps
  the block); the IV has no "may not assert the symptom" rule although the own test does (P3a,
  `own_test_symptom_ids`); no IV check reads the staged README/docstring.
- Fix: (a) drop a red IV whose every failing node is individually inadmissible (inverted, or
  asserting a scenario the visible contract excludes); (b) extend the symptom rule to the IV;
  (c) when the IV contradicts a visible documented fact, re-aim/mend the IV instead of ending the
  run.
- Effect: 0 on today's actual pass rate (those tasks already pass the grader); it converts 4+ claims
  and removes 20-40 wasted calls per affected task. In `6b224f5` it is part of what let D2's churn
  lose T-07.
- Cost: medium — needs the documented-literal scan and the IV admissibility rule, plus tests.

**D6 — measurement: N=1 on both arms, pi's variance unmeasured, tokens/wall not single-lane.
** (§4; `STATUS §8e`)
- The current 26 vs 27 is inside the noise band; the A2 arm (pi + improved prompt) is still
  unmeasured (GPU blocker); the wall-clock comparison was taken under 4-way concurrency (mean 26 s
  in `...T065821Z`, 34 s in `...T070710Z`, vs pi's sequential 131 s — not comparable). Tokens are
  comparable and still worse: 18,250 and 19,365 tokens/task over the two latest runs (mean 18,808,
  752,286 total) vs pi's 9,045.
- Fix: freeze one revision; run ≥9 seeds per arm (≥17 to claim a win) with a single lane for the
  wall-clock number; include the A2 arm.
- Effect: turns a number into a finding; no code change.

---

## 6. Gaps and limits of this forensics

1. **The `6b224f5` per-task runs are a reconstruction** (three banded directories), not a
   single labelled campaign directory. The reconstruction is exact on tasks, passes and the 16
   failures, but it is a reconstruction.
2. **A2 (pi + improved prompt) is unmeasured** — no trajectory exists, so the "structure beats a
   better prompt" claim is still unsupported.
3. **Per-attempt model output is still not persisted in full**: the trajectory records the
   `implement_write` envelope, so I could recover every revision for the tasks above, but a run
   whose trajectory is absent (older sweeps without `trajectory.jsonl`) cannot be forensically
   read. No such gap applied to the tasks in §2; the 12 shared failures were not opened
   individually (§3).
4. **pi is N=1 per task**, so its variance is unknown; every margin statement in §4 applies to it
   too and was measured only on our arm.
5. The latest measured runs are at `d24410a`; `HEAD` adds P8c (claim-rule only). Actual pass rates
   are unaffected, claim counts are not comparable across the two.
