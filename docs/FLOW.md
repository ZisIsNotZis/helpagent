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
           · emits ONE structure (§2): description, ONE reason, the four lists,
             and the ordered approaches (each declaring whether it splits and into what)
           └─(C) children recurse (B); siblings are independent
                 └─(D) work unit: implement ∥ author tests → run → review
                       └─(E) verdict: requirement satisfied AND no regression
```

Every step — (A), every (B), every judge/review call — **may explore**.

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

## 7. Thinking, and parallelism

- **Thinking is optional and never a decision input.** The model behind any step may think or not;
  if it thinks, the thinking is recorded in the trajectory and used for nothing else — every
  decision is computed from the parsed structure's fields.
- **Parallelism**: every place that can run in parallel, should — siblings, implementation ∥ tests,
  review angles. **Deferred**: accuracy first. The flow does not depend on it.

## 8. Evidence

Every run writes `trajectory.jsonl` (`harness/telemetry.py`): each model call's prompt, artifacts,
**thinking (when present)**, raw answer, parsed structure, tokens, wall; every harness event; every
write (sha256 + whether it differs from the baseline); every test execution with output; the
delivery and the grader's verdict. Complete, always on.

## 9. What this changes relative to the current code

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
| 9 | judge/review/independent test = the same small model | configurable; expected to be a stronger model |
| 10 | non-pass states collapse into "not claimed" | explicit three-state test/review, and the node update is a recorded act |

## 10. Open decisions for the owner

1. **Which model/endpoint serves the judge/review/independent-test role** (§9 row 9).
2. §4.4's last line: when no approach passes, confirm the exact output — current spec: deliver the
   best-evidence revision, claim nothing, report `uncertain` with the reasons.
3. The parallelism granularity when it is picked up (§7): siblings from the start, or gated by
   budget/clock; parallel writers need confined work trees.
