# FLOW — the one flow (owner spec, 2026-10-06)

Single source of truth for how a run processes a task. It replaces the "single-leaf mode vs tree
mode" split: **a single leaf is just a tree of one node**. `docs/DESIGN.md` §10 describes the older
layering; where they disagree, this file wins.

**Nothing here leaks the benchmark.** A requirement NEVER names a file, so no step may take a file
list from the user's text; file lists come from **exploration** of the repository.

Priority order (owner direction): **accuracy first**; parallelism is a principle to apply
everywhere it can be applied, but it is deferred until the accuracy work lands (§7).

## 1. Shape

```
user text
 └─(A) triage: ONE step → one or more ISSUES (each issue = a root node)
     └─(B) per node: ONE recursive step
           · explores the repository freely (read), then
           · emits ONE structure (§2): what + reason, and the ordered Hows, each How
             carrying what + reason + the four lists + its children
           └─(C) children recurse (B); siblings are independent
                 └─(D) work unit: implement ∥ author tests → run → review
                       └─(E) verdict: requirement satisfied AND no regression
```

Every step — (A), every (B), every judge/review call — **may explore**.

## 1.5 The flow as a state machine, with every case

```
S0  input: the user's text
S1  TRIAGE (one call; may explore) -> issues[] (>=1); each issue is a root node
S2  NODE (one call per node; may explore) -> {what, reason, hows[]}
      per How: {what, reason, docs[], files[], tests[], reviews[], children[]}
S3  the node takes its FIRST How (list order); the previous How must be confirmed failed
      children != []  -> recurse S2 for every child
                         all children pass           -> the How passes (then the integration check)
                         any child uncertain/failed  -> the How is uncertain
      children == []  -> work unit, S4
S4  WORK UNIT  (the executing How)
      W1 implement || author tests          (two writers: source vs test file)
      W2 run the declared tests
           fail               -> the How's state is FAIL; review does NOT run here
                                 (the judge is asked only about WHOSE fault it is; the state
                                  stays fail until a check actually passes)
           pass               -> W3
           uncertain          -> W3 (an unevaluable test may still go to review)
      W3 discrimination check: every declared case must be RED on the pristine source
           discriminates      -> W4
           green on pristine  -> the test is UNCERTAIN: repair it (bounded); if it cannot be
                                 made to discriminate -> node update (drop the test, reason updated)
      W4 regression check: every visible test green on the pristine sources must still be green
           none               -> W5
           regression         -> judge -> iterate, or node update (fix/revert)
      W5 review (only when the test state is pass or uncertain, and only angles were declared)
           pass               -> S5
           fail / uncertain   -> iterate (bounded); at the cap, node update (drop the review,
                                 or switch the check to the other kind) or take the next How
      RETRY CAP REACHED, state still fail       -> the How is FAIL      (never "uncertain")
      RETRY CAP REACHED, state still uncertain  -> the How is UNCERTAIN
      (a review may run after an UNCERTAIN test; a FAIL test never reaches review)
S5  VERDICT AND CLAIM
      every declared check of the executing How is `pass`, no regression -> the claim gate decides
      the How ended fail or uncertain -> the NEXT How (both states advance to the next How)
      every How exhausted with no pass -> take the BEST of them: if any How is UNCERTAIN the
        node is UNCERTAIN, otherwise the node is FAIL; the state propagates upward that way
        (claim nothing either way; deliver the best-evidence revision with every How's evidence)
S6  SUMMARY: per issue/node: pass | uncertain | parked-for-user
```

### Case table

| case | what happens |
| --- | --- |
| How splits | children recurse; the How itself executes nothing; its four lists are its plan/expectation (§11 H1) |
| How does not split, tests only | W1-W4, then W5 skipped; the test evidence must carry the claim |
| How does not split, reviews only | W1 (no test), W4 (regression on the visible suite), W5; the review evidence carries the claim |
| How does not split, both | all of W1-W5; a review that cannot pass may be dropped by a node update, and a test-based claim survives that |
| How declares neither check | §11 H2: currently unverifiable — the How cannot establish "requirement satisfied" |
| tests red, judge unavailable/malformed | §11 H8: the verdict is uncredited; the run keeps implementing (today's rule) or stops by policy |
| regression found | judge first (it is a red signal), then iterate or node update |
| budget/deadline exhausted mid-node | handover: stop with `uncertain`, deliver best evidence, record where it stopped |
| a criterion that no check can pin | the How says so in its `reason`; the claim cannot rest on it |
| two nodes writing the same file | §11 H5: they cannot be executed in parallel without isolation |
| one issue passes, another does not | the summary reports per issue; the run as a whole does not claim the failed one |

## 2. The node structure — fields

Two rules decide what exists here:

- **A list carries its own order** — never add a `rank` field to a list.
- **`what` is freeform text holding everything meaningful for the next step; `reason` is freeform
  text holding why (audit).** Nothing that a `what` can say gets its own field.

There is **no `kind`** (whether a node splits is what its `children` say), **no budget estimate**
(nobody can estimate calls for a step that has not happened), **no `interfaces`** (that is `what`),
and **no separate acceptance criteria** (§2.4).

### 2.1 The node

| field | type | notes |
| --- | --- | --- |
| `what` | str `req` | what this node is, in the user's terms |
| `reason` | str `req` | why this node exists and why it decomposes the way it does |
| `docs` / `files` / `tests` / `reviews` | lists `opt` | the node's OWN work — the work that sits ABOVE its children (integration, glue). A node that is purely a parent has all four EMPTY, and that is the normal case; a node that does everything itself may carry them with children absent |
| `hows` | [How] `req` (≥1) | the approaches, in priority order (first = first attempted) |

### 2.2 A How (an implementation approach)

| field | type | notes |
| --- | --- | --- |
| `what` | str `req` | the plan: how to do it, what exactly to do — everything the next step needs |
| `reason` | str `req` | **why** — required whether the lists below are empty or not: why these files/tests/reviews/docs, why any of them is empty, why anything was dropped |
| `docs` | [DocUpdate] `opt` | may be empty |
| `files` | [FileChange] `opt` | may be empty |
| `tests` | [DeclaredTest] `opt` | may be empty |
| `reviews` | [ReviewAngle] `opt` | may be empty |
| `children` | [node] `opt` | `[]` = this How runs as one work unit; non-empty = it splits, each child a node of this same shape |

**Empty means DOES NOT EXIST, never "unrestricted".** `files: []` says this approach changes no
source file at all (a docs-only requirement is exactly that); it does NOT license writing
anything. A write outside the declared `files` is therefore a **deviation**: allowed (writes are
never refused), recorded, and it forces a node update — the How's `files` is extended and its
`reason` updated.

### 2.3 The four lists — item fields

| item | fields |
| --- | --- |
| `DocUpdate` | `path`, `what` |
| `FileChange` | `path`, `what`, optionally `region` (a line range / symbol / anchor) — an entry may be as coarse as a file or as fine as one region |
| `DeclaredTest` | `file`, `cases` ([str] — the test node names this entry adds), `what` (the behaviour each pins) |
| `ReviewAngle` | `angle` (from our predefined angle list), `what` (what the reviewer must establish) |

### 2.4 Where the "acceptance criteria" went

Nowhere: **the criteria ARE the declared tests and reviews.** The old flow extracted criteria by
splitting the user's text into sentences, which is how T-01's own test came to assert "a session
must expire exactly 60 seconds" — the reported symptom read back as the requirement. Evidence is
now per declared check: the ledger lists every declared test and review, its state (§4), and the
evidence for that state. A How that declares no check anywhere still has to say why in its
`reason`.

## 4. Execution and the three states

**Not every job needs a review, and not every job needs a test.** Hard work deserves a review;
between the two, **prefer the review** — a test authored by the same weak model is often simply
wrong (T-01's own test asserted the bug). Trivial work may legitimately declare neither, and the
`reason` must say so.

Within a work unit: **the implementation and the test authoring run in parallel** (two writers,
disjoint targets: source vs test file), followed by the test run, then the review.

### 4.1 Test states

| state | when |
| --- | --- |
| **pass** | the declared tests run GREEN on the final revision **and** they discriminate (each is RED on the pristine source — checked after the fact, deterministically) |
| **fail** | the declared tests run RED on the final revision (the report names the failing ids) |
| **uncertain** | the tests could not be evaluated (collection/import error in the test, the test was dropped or rewritten without re-proving discrimination, no report, environment fault), or a rewrite left the discrimination unproven |

### 4.2 Review states

| state | when |
| --- | --- |
| **pass** | every declared angle approves, with grant-calibre evidence (names a criterion and an observable behaviour) |
| **fail** | a critical angle rejects |
| **uncertain** | mixed verdicts, a missing angle, insufficient evidence, or the reviewer was unavailable |

### 4.3 What a non-pass state means

**A test is never simply ignored.** If the node declared tests, then either they reach **pass**, or
the node is **updated** (§6) and the test is dropped in that update — which also invalidates any
claim that rested on it. The same rule for reviews: pass, or update the node and drop the review.

### 4.4 The approach (How) loop

```
for how in hows (list order):
    run the work unit; on a non-pass state, iterate up to the node's attempt cap
      · each iteration may repair the implementation, the test, or the review target
      · every iteration's evidence is recorded
    if pass → the node may claim (§5), subject to the existing claim gate
    if the cap is exceeded with uncertain/fail → this How has FAILED (confirmed)
        → take the next approach (non-redundant: only after the previous one is confirmed failed)
if no approach passed → the node's state is UNCERTAIN
        → nothing is claimed; the best-evidence revision is delivered and the node reports
          "uncertain" with every approach's evidence and the node's reason for each drop
```

A node whose `approaches` is exhausted this way is **uncertain**, never silently green. (An
internal node's state is derived from its children: `pass` only if every child passed AND the
integration check passed; `fail` if any child failed; otherwise `uncertain`.)

## 5. The verdict and the claim

- **Requirement**: the per-criterion ledger, every row carrying a check and evidence.
- **Regression**: the whole visible test suite on the final revision versus the same suite on the
  pristine source; **green before, red after = regression** → blocks the claim, drives another
  iteration.
- **Nothing else counts.** Touching one file or a thousand makes no difference; there is **no
  refusal for an "unexpected" file**. The writable set is what the executing How declared in `files[]`; empty means that How
  touches no source file (never "unrestricted"), and any write outside it is a recorded
deviation that forces a node update (§6.2).
- Write integrity the harness itself needs (its own test infrastructure, pytest config, module
  shadows) is preserved by **allowing the write and restoring the file before grading**, with the
  attempt recorded — never by refusing (six blind retries in T-01 came from refusing).

## 6. The judge, and when the node is updated

### 6.1 The judge's output (one envelope, fresh context)

| field | type | meaning |
| --- | --- | --- |
| `status` | `ok` \| `failed` \| `blocked` \| `unable` | the envelope grammar (unchanged) |
| `comment` | str | ≤2 lines, the judge's own summary |
| `blame` | `implementation` \| `tests` \| `spec` \| `environment` | **exactly one** dominant attribution |
| `problem` | str | the defect; when `blame=tests` it MUST name the failing test or one of its assertions (otherwise the verdict is not credited — the existing deterministic coercion) |
| `evidence` | str | what in the diff / the test output supports it |
| `advice` | str `opt` | what to do next: which file/symbol, or which assertion is wrong (the caller may put it straight into the next attempt's failure context) |
| `confidence` | `low` \| `medium` \| `high` | how sure the judge is |

The judge sees the goal, the criteria, the diff, the test output and the node's `reason` — never
the author's conversation. Its verdict selects the next move:

| blame | next move |
| --- | --- |
| `implementation` | iterate the implementation (with `problem`/`advice` as the failure context) |
| `tests` | the test is the defect: repair or replace it (bounded), re-prove discrimination |
| `spec` | bubble up: the node's own description/ACs are wrong → the PARENT re-plans (§6.2) |
| `environment` | park the node (`needs-user`); nothing in-process can fix it |

### 6.2 Node-update (re-plan) triggers — the exhaustive list

1. **Test cap exceeded** and the test is still uncertain/fail → update the node: drop the test
   (recorded) or change approach.
2. **Review cap exceeded** and the review is still uncertain/fail → update the node: drop the
   review (recorded) or change approach.
3. **The judge says `spec`** → the parent node re-plans this subtree.
4. **A requirement has no possible check** (no test and no review pins it) → add one in the node
   update, or record in the How's `reason` why none can exist.
5. **The executing How needs a file it did not declare** → that How's `files[]` is extended in a
   node update (recorded, with its `reason` updated; writes were never refused).
6. **Regression detected** → the node is updated: fix or revert that part, and `files[]`/`tests`
   are adjusted accordingly.
7. **Budget/deadline exhausted** → handover: the node stops with state `uncertain`, delivering its
   best-evidence revision.

## 7. Thinking, parallelism, and who judges what

- **Thinking is optional and never a decision input.** The model behind any step may think or not;
  if it thinks, the thinking is recorded in the trajectory and used for nothing else — every
  decision is computed from the parsed structure's fields.
- **Every judge inside a run is the SAME small model that writes the code** — the attribution
  judge, the review, the independent test. There is no stronger in-run judge. Their verdicts are
  what the run has to work with, and the run knows they are correlated with the author (that is why
  a non-discriminating test counts for nothing).
- **Parallelism**: every place that can run in parallel, should — siblings, implementation ∥ tests,
  review angles. **Different nodes are different git worktrees/branches**, merged afterwards.
  **Deferred**: accuracy first; the flow does not depend on it.

### 7.1 The one place a STRONGER model is used: the out-of-band regression review (manual)

Inside a run, no stronger model exists. The single case that needs one is this:

> the run wrote files it did NOT declare, and our tests are not sufficient to decide whether that
> introduced a regression.

Then the decision is made **outside the run, by hand, by the operator's agent** (a strong model
reading the actual diff), because a benchmark-level judgement about "did this break something" is
not something the small model or the visible test suite can settle. Its output is a plain verdict
with evidence:

| field | meaning |
| --- | --- |
| `verdict` | `regression` \| `no-regression` \| `cannot-tell` |
| `files_reviewed` | the undeclared files that were touched, with their diffs |
| `tests_considered` | which tests could have caught a regression here, and why they could not |
| `evidence` | what in the diff supports the verdict |
| `residual_risk` | what remains unchecked |

It never runs inside the harness and its verdict is never fed back into a run; it is recorded with
the run's evidence so a reader can see how the undeclared change was adjudicated.

## 8. Evidence

Every run writes `trajectory.jsonl` (`harness/telemetry.py`): each model call's prompt, artifacts,
**thinking (when present)**, raw answer, parsed structure, tokens, wall; every harness event; every
write (sha256 + whether it differs from the baseline); every test execution with output; the
delivery and the grader's verdict. Complete, always on.

## 9. What this changes relative to the current code

**Snapshot taken 2026-10-06; the "today" column describes the code at that commit.** State now
(2026-10-09): rows 5, 7, 8 and 10 have landed (`8cb22be`, `827d8dd`, `01d9bee`); row 3 landed for
the tree's Hows while the leaf driver still uses its fixed questions; rows 1, 2 and 6 are still
open and are the node-structure work in `.scratch/27-campaign/`.

| # | today | this spec |
| --- | --- | --- |
| 1 | two drivers (`v2_leaf` direct leaf, `v2_tree` tree) | ONE runner; a single leaf is a tree of one node |
| 2 | no exploration; the whole source is pushed into every prompt | an explicit bounded read step inside every node step |
| 3 | leaf driver: no test plan, two fixed review angles | each How declares docs/files/tests/reviews + ONE reason |
| 4 | tests authored first, required red on arrival | implementation ∥ tests; discrimination checked post-hoc on the pristine source |
| 5 | a red test iterates the implementation directly | a red test goes to the judge (§6.1) first |
| 6 | file list from the plan (tree) or regex over the requirement (leaf) | from exploration; the requirement-text regex is judge input, never a gate |
| 7 | writes outside the boundary / into a frozen path are REFUSED | allowed, recorded, decided by the outcome |
| 8 | no regression stage | regression = visible suite green before, red after |
| 9 | judge/review/independent test = the same small model | UNCHANGED (they stay the small model); the only stronger-model role is the manual out-of-band regression review (§7.1) |
| 10 | non-pass states collapse into "not claimed" | explicit three-state test/review, and the node update is a recorded act |

## 11. Holes in this flow (found while walking it; none is decided)

| # | hole | why it matters | proposal |
| --- | --- | --- | --- |
| **H1** | RESOLVED: a splitting node's four lists are its OWN work (above the children); a purely parental node leaves them empty, which is normal | — | — |
| **H2** | RESOLVED: neither check is allowed for trivial work; the `reason` says why, and such a How cannot claim beyond the deterministic checks | — | — |
| **H3** | RESOLVED: states are pass / fail / uncertain / parked-for-user. A test that says FAIL ends the How as FAIL (never "uncertain"); UNCERTAIN only when the test or the judge itself reports uncertain; when every How is exhausted the node takes the best of them (uncertain if any is uncertain, else fail) | — | — |
| **H4** | RESOLVED: all Hows exhausted → best-of (uncertain beats fail) → that state propagates upward; a judge's `spec` verdict is still the path that asks the parent to re-plan | — | — |
| **H5** | RESOLVED: parallel nodes get **separate git worktrees/branches**, merged afterwards | — | — |
| **H6** | The regression check's coverage | it can only run the VISIBLE test suite; the grader's own suite is withheld by the blind protocol, so a run can be regression-free by our check and still fail the grader | state it plainly in every report: our regression verdict is partial; the external grader is the final word |
| | *measured 2026-10-08: on this corpus the staged view usually has no visible test at all, so the stage is skipped (`observable=False`) - see `STATUS.md` limit 7* | | |
| **H7** | When is the judge consulted? | every red (one extra call per attempt) versus after K consecutive reds (today: K=2, plus a volunteer trigger) | every red: T-01/T-05 both burned 4-6 attempts churning against a wrong test, which one judge call would have stopped |
| | *decided 2026-10-08: K=1 — every red goes to the judge (commit `8cb22be`, `ATTRIBUTION_RED_K`), at most once per attempt* | | |
| **H8** | The judge is unavailable or malformed | the attribution is missing, and "keep implementing" is a guess | keep implementing for at most one attempt, then treat the test as UNCERTAIN and repair it (a wrong test is the likelier defect in that state) |
| **H9** | The work unit's stop conditions are not enumerated | "iterate (bounded)" hides: what is the cap, what happens at the cap, does the cap reset when the judge changes the diagnosis | one cap per How (attempts), renewed only by a node update; at the cap the How is confirmed failed and the next How starts |
| **H10** | Exploration bookkeeping | "every step may explore" says nothing about what the exploration found, who pays for it, or whether the later steps can see it | an exploration result is a first-class artifact: reads are recorded in the trajectory, their excerpts ride into the steps of the SAME node, and the reads are charged to that node's budget |
| **H11** | The top level with several issues | the flow says "one or more issues" but not whether they are sequential, parallel, or what the run claims when one passes and another does not | execute issues in order (or in parallel only when their `files` do not overlap — H5); the run's report is per issue and the run claims nothing that failed |

## 10. Open decisions for the owner

1. RESOLVED: every in-run judge stays the small model; the strong model appears only as the manual
   out-of-band regression review (§7.1).
2. §4.4's last line: when no approach passes, confirm the exact output — current spec: deliver the
   best-evidence revision, claim nothing, report `uncertain` with the reasons. **Implemented and
   kept** (`best_of_how_states` / `propagate_node_state`, `01d9bee`; the empty-delivery case is a
   first-class outcome, `d10e172`).
3. The parallelism granularity when it is picked up (§7): siblings from the start, or gated by
   budget/clock; parallel writers need confined work trees.
