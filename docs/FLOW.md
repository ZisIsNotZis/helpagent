# FLOW — the one flow (owner spec, 2026-10-06)

This file is the single source of truth for how a run processes a task. It replaces the
"single-leaf mode vs tree mode" split: **a single leaf is just a tree of one node**, so there is
one flow and one runner. `docs/DESIGN.md` §10 describes the older leaf/tree layering; where the
two disagree, this file wins.

Nothing in this file leaks the benchmark: a requirement NEVER names a file, so no step may take a
file list from the user's text. File lists are produced by **exploration** of the repository.

## 1. The shape

```
user text (the requirement)
 └─(A) triage: ONE step → one or more ISSUES (each issue = a root node)
     └─(B) per issue: ONE step, recursion down the tree
           · explores the repository freely (read), then
           · emits ONE structure: description + the four lists + the ranked approaches,
             and, per approach, whether it splits and into what
           └─(C) children recurse (B) — children of a node are INDEPENDENT, so they may run
                 in parallel (they are reads + their own confined writes)
                 └─(D) execution of a work unit (a leaf): implement ∥ test, then review
                      └─(E) verdict: requirement satisfied AND no regression
```

Every step — including (A) and every (B) — **may explore**: reading is never a separate rarified
phase, it is how a step decides what it is looking at.

## 2. The node structure (one step, one structure)

One model step produces the whole node. Fields (everything except the description is a list):

| field | meaning | empty |
| --- | --- | --- |
| `description` | what this node is and why (goal + the acceptance criteria it owns) | required |
| `docs_updates[]` | documentation this node will add/change, with the reason | allowed |
| `files[]` | source files this node will create/change | allowed |
| `tests[]` | test cases this node will add/change, each pinning which criterion | allowed |
| `reviews[]` | review angles this node wants evaluated | allowed |
| `approaches[]` | 1..N implementation approaches, ORDERED (rank = position) | required |
| `approaches[i].children[]` | if this approach must be split: the sub-nodes (each one is a node of this same shape) | `[]` = do not split |
| (unchanged) `acs`, `interfaces`, `est_calls`, … | as today | as today |

**Every one of the four lists is optional — optional means it MAY BE EMPTY, not null — and an
empty list must carry a substantive reason** (the same rule the two verification lists already
have: `planned_tests`/`planned_reviews` with `verification_reason`). A node that writes no docs,
touches no file, adds no test and asks for no review is not "done", it is "unexplained".

## 3. Recursion and parallelism

- Node → structure → children (if the chosen approach splits) → each child repeats the same step.
- **Siblings are independent**: the design may run them in parallel (that is what the whitespace
  is for). Concurrency is an executor concern; the flow does not change.
- **Within a work unit, implementation and test authoring run in PARALLEL** — both are authored
  by the model against the same explored context, and they touch disjoint files (source vs test).

## 4. Execution of a work unit (leaf)

| the unit declared | what happens |
| --- | --- |
| tests **and** reviews | author implementation ∥ author tests → run tests → **green**: run the reviews → claim rules as today; **red**: attribution (§5) |
| tests, no reviews | author implementation ∥ author tests → run tests → **green**: the test evidence carries the claim (today's `own-test`/`independent-test` route); **red**: attribution |
| reviews, no tests | implement → run the reviews → the review evidence carries the claim (today's review route) |
| neither | implement → only the deterministic per-criterion checks stand; the node records why there is no test and no review, and cannot claim more than those checks support |

**Tests authored in parallel are still checked for discrimination, after the fact:** a test that
also passes on the PRISTINE source does not pin the goal and cannot carry a claim (the existing
`red on arrival` guarantee is kept, just evaluated post-hoc instead of gating the authoring
order). This is deterministic — we always have the pristine source.

## 5. Attribution (the value question: whose fault)

When the tests are red, the run does NOT simply iterate the implementation. It asks the
independent judge which side is wrong, with the four labels that already exist
(`implementation_wrong`, `test_wrong`, `spec_wrong`, `environment_broken`). Dominance is
unchanged: spec → environment → test → implementation, with the deterministic coercion rule
(a `test_wrong` verdict must name the failing test or assertion, else it is not credited).

The strongest available model should fill this role (see §7): judging your own work with the same
small model is correlated, not independent.

## 6. Verdict: requirement + regression (no file-counting)

- **Satisfied**: the acceptance-criteria ledger, each row carrying a check and evidence.
- **No regression**: the whole visible test suite is run on the final revision and compared with
  the same suite on the pristine source; **green before, red after = a regression** — it blocks
  the claim and drives the next iteration. (The grader's own byte-identity contract is exactly
  such a regression check; the run does not need to be told about it in advance.)
- **Nothing else counts.** Touching one file or ten makes no difference. There is **no refusal for
  an "unexpected" file**: the writable set is what the plan declared, and if the plan declared no
  files, everything visible is writable (§2 `files[]`, empty = no restriction).
- **Write integrity that the harness itself needs** (its own test infrastructure, pytest config,
  module shadows) is preserved by **allowing the write and restoring the file before grading**,
  with the attempt recorded — never by refusing, which is what put T-01's model into six blind
  retries.

## 7. Independence of the judge

`judge`, `review` and the independent test may be served by a **stronger model** than the one
that writes the code. That is a configuration choice (endpoint/model per role), not a flow change.

## 8. Evidence

Every run writes `trajectory.jsonl` (see `harness/telemetry.py`): each model call's prompt,
artifacts, raw answer, parsed structure, tokens and wall time; every harness event; every write
(sha256 + whether it differs from the baseline); every test execution with its output; the
delivery and the grader's verdict. Complete and always on — a run that cannot be read back cannot
be audited.

## 9. What this changes relative to the current code

| # | today | this spec |
| --- | --- | --- |
| 1 | two drivers: `bench/v2_leaf.py` drives one leaf directly (the sweep path), `bench/v2_tree.py` drives the tree | ONE runner; the single-leaf case is a tree of one node (no split declared) |
| 2 | no exploration; the whole source is pushed into every prompt | an explicit, bounded read/explore action inside every node step |
| 3 | the leaf driver declares no test plan and two fixed review angles | the node step declares `docs/files/tests/reviews`, each with a reason when empty |
| 4 | tests are AUTHORED FIRST and must be red on arrival; implementation follows | implementation ∥ tests; discrimination is checked post-hoc against the pristine source |
| 5 | a red test drives implementation-only iteration | a red test goes to attribution (judge) first |
| 6 | the file list comes from the plan (tree) or from regex over the requirement (leaf) | from exploration; the requirement-text regex is demoted to judge input, never a gate |
| 7 | writes outside the boundary / into a frozen path are REFUSED | allowed; recorded; the outcome (tests + judge) decides |
| 8 | no regression stage | regression = visible tests green before, red after |
| 9 | judge/review/independent test = the same small model | configurable, expected to be a stronger model |

## 10. Open decisions for the owner

1. **Which model/endpoint serves the judge/review/independent-test role** (§7).
2. The parallelism granularity in §3: siblings in parallel from the start, or when the budget /
   wall-clock makes it worth it (the tree today serializes; parallel writers need confined trees).
3. Whether the four lists must be non-empty at least once per node **subtree** or only "a reason
   when empty" (today: a reason).
