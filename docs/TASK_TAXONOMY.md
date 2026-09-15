# TASK TAXONOMY — Everything Software Engineering Does

Companion to DESIGN.md §4.1. Every activity SE ever requires, classified: minimal (or how to split), harness vs model job, and the clean input/output at the step boundary.

## Boundary theorem

- **Fuzziness only inside a round; only clean artifacts cross step boundaries.** A step is minimal iff it has exactly one handover (one schema-able output, validated by the kernel).
- **An activity with no schema-able output is not a step** — it is the interior of one (bounded probe loop, hard-capped rounds) and persists only via the step's final clean output.
- **Harness** = deterministic / checkable / mechanical. **Model** = judgment: translation, choice, pattern recognition. Dominant pattern: **propose-validate** (model emits clean artifact one-shot; harness validates and executes).
- **Splitting rule:** a step needing two handovers splits into two. **Non-step rule:** an output that can't be pydantic-schema'd or acceptance-checked stays in-round.
- **Merge rule (too simple):** steps chained by yes/no + dependent question merge into one step with a union schema (e.g. `{bugs: [...] | []}`). Also merge steps sharing identical inputs and one judgment round.
- **Bounded-attempt rule (too complex):** no step "solves" anything open-ended. A fix/attempt step = one hypothesis, implemented, verified, outcome recorded: `{fixed, fixed-with-concerns, blocked-design-question, new-bug-found, needs-user}`. Next hypothesis = new sibling node; design questions bubble to the user as decision nodes.
- **AC rule & closure gate (100% strict, kernel-enforced):** every AC is a checkbox resolving to ≥1 executable check — UT/API/E2E test, script assertion, or, for genuinely subjective ACs, an `llm("check: ...")` judge script (schema'd verdict + confidence). **Every leaf carries an AC test map; an internal node MAY carry one**, and an internal map is an *integration view*: only checks that span its children, each resolving to a check a descendant already owns (a command or test id) — references, never copies, so ACs do not repeat upward. Spec/interface defined first; then code and tests are written **in parallel**, both targeting the AC test map. **Firewall = withhold solutions, share requirements:** both sides get the full contract (`interfaces` + `behavior`); only the implementation artifact is withheld from the test writer (the test writer never sees code — independent verification), while solver guidance lives in `implementation_notes` (implementer-only). A node closes only when: (a) every AC **present in its map** has ≥1 test, (b) every such test passes unconditionally (no skips, no flaky tolerance), (c) all child nodes are closed first. Closure is procedural — F7 runs the map mechanically; the model never decides whether to close, at most flags candidate gaps that become new nodes. **The map is a gate definition, so authoring it is a propose≠decide act:** `draft_acs` proposes, a fresh-context `gate_decide` decides (`weakens_gate` is exactly the subjective-where-deterministic-is-feasible check).
- **Proposer never decides:** AC/test/tree-structure changes (add/remove/modify) are proposed by one agent with a written reason and decided by an independent fresh-context reviewer reading that reason. System-wide rule, same pattern as memory governance: no agent ever loosens a gate it is itself measured against.
- **Expansion strategy:** **harness proposes candidate cuts, model annotates/fills — propose-validate, never free decomposition.** Two candidate modes, selected by what is known: **structural** (module-map seams) when the task's location is known or irrelevant — feature, port, scaffold, refactor; **evidence-seeded** (failing symbol, stack frames, covering tests — from the locate/reproduce artifact) when the location *is* the unknown — bugfix, perf, crash. Filename-only planning for a diagnostic task is a non-goal: when the location is the unknown, `expand` runs **after** locate, seeded with evidence, so the plan points at a real symbol instead of a plausible-sounding file. Uniform-layer expansion: one layer at a time; all children of a node pass the same leaf criterion before the layer is done. Leaf criterion: (a) estimated execution ≤10 tool-rounds, (b) exactly one output artifact, (c) one subsystem area. Defaults: depth cap 3–4, 5–15 leaves per parent (a *default*, not a bound — a small seam list legitimately yields fewer), plus a kernel-enforced **global node budget per task class** (per-parent bounds alone permit thousands of leaves).

Legend: `H` harness · `M` model one-shot · `H+M` propose-validate (M proposes, H validates/executes).

### Pipeline routing by task class

The sections below are the activity catalogue, not a fixed sequence: the task class picks the entry point, because *what is unknown* differs.

| task_class | Entry | Why |
| --- | --- | --- |
| bugfix, perf, crash (`location unknown`) | A → **C3 locate / D reproduce** → B expansion (evidence-seeded) → E/F | The plan cannot be written from names; the failing symbol comes from evidence, and the plan is written *after* it exists. Routes through the D pipeline from D0. |
| add-feature, port, refactor (`location known or irrelevant`) | A → **B expansion (structural)** → E/F | The layers/modules the request names *are* the seams; module-map cuts are grounded. |
| scaffold, new-repo | A → C6 bootstrap → B expansion (structural) | Environment and skeleton precede seams. |
| docs-only | A → H | No code boundary to plan. |

C1/C2 (index build) is a precondition of A/B, not a later phase — B1 consumes candidate cuts, and A3 consumes the index. The C activities that consume it per-need (C3 locate, C4 context, C5 negative-space) run where the routing table says.

## A. Understand & specify

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| A1 | Requirement intake (NL → structure) | yes | M + `user()` gate | raw user request | task_card {goal, constraints, out-of-scope}; user confirms via `user()` |
| A2 | Acceptance-criteria drafting + AC test map authoring | yes | H+M | task_card (+ spec, for leaves — ACs derive from the frozen contract) | AC list each with ≥1 check `{ac_id → [check_id, command]}` (kernel-validated; held in node schema), **decided by a fresh-context `gate_decide` before it is frozen** (authoring is gate-defining, so proposer≠decider applies); uncheckable → needs-human |
| A3 | Feasibility / repo-fit | yes | H+M | task_card + repo index | feasibility {blocking risks, affected areas, verdict} |
| A4 | Clarification question to user | yes | `user()` primitive | task_card + ambiguity list | answered task_card; **hard cap 3 rounds** → excess ambiguities become needs-user decision nodes |

`user("...") -> answer-artifact` is the fifth kernel primitive — an async function exactly like `llm()`: it pauses the calling subtree, lands the answer as an artifact, unblocks.

## B. Plan — all operations over THE task tree

There is exactly one plan artifact: **the task tree**. Every node (big or small) has the universal schema `{id, what, why, input, output, AC, status, children}`; leaves are minimal tasks; status carries `{pending, in-progress, done, blocked, stale, needs-user}`. Planning, user confirmation, execution scheduling, and progress display are all views/operations over this one artifact — no translation layer between what the user approved and what the engine runs.

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| B1 | Plan: expansion into task tree (merged impact-scoping + splitting) | yes | H+M (propose-validate) | task node + candidate cuts (structural: module map · evidence-seeded: locate/reproduce artifact) | child subtree (each node with selected output schema); harness proposes cuts, model fills |
| B2 | Split review (peer agent, fresh ctx) | yes | M | subtree + ACs | verdict {ok, issues[]} |
| B3 | Dependency ordering | yes | H | tree (leaf I/O edges) | validated execution DAG |
| B4 | User patch from node | yes | H + M (user exempt from gate review — final authority) | user-selected node + intent | rewritten subtree; cascade: touched leaf → parents re-validate up (done parent reopens, AC map re-runs); touched branch → children marked stale (must re-verify) |
| B5 | Tree rendering / progress display | yes | H | tree + live status | rendered view (zero LLM) |
| B6 | User piloting (typed message routing) | yes | H | user-selected node + typed message | one of: **patch** (→ B4 flow, cascade, no gate review), **hint** (instruction artifact injected into node's composed context; node continues under same schema constraints), **answer** (→ `user()` semantics; unblocks decision nodes) |
| B7 | Risk/estimate per leaf | yes | M | subtree | per-leaf risk flag + round estimate (drives per-step budget = estimate × 1.5) |

## C. Orient

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| C1 | Repo mapping (index build) | yes | H | repo tree | symbol table, module map, test map |
| C2 | Index refresh trigger | yes | H | git events / staleness | fresh index |
| C3 | Locate (where is X) | yes | M over H-ranked slices | query + ranked candidates | candidate list {path, symbol, confidence, why} |
| C4 | Context gathering | yes | H (composer) | target file/symbol | bounded context bundle (budget-enforced) |
| C5 | Negative-space check (what exists already) | yes | H | intended new symbol | duplicates/overlap list (anti-reimplement) |

| C6 | Environment & build bootstrap | yes | H (engine-owned lifecycle per known stack: python/node/react/vue/angular/…; M fallback for resolution failures) | repo tree + manifest (dependency list generated after specification phase) | `{installed, build-ok, shaped error}` — install → build → test lifecycle; precondition for F3 |

## D. Diagnose — two entry channels, one per-bug pipeline

**Channel 1 — mechanical:** check pipeline / compile / runtime anomaly already flags a concrete failure → D1.
**Channel 2 — identified:** user report or "something's off" → D0 (merged "is there a bug?" + "what bugs?" — one step, union schema).
Each identified bug becomes a **ticket = task-tree node** (universal schema, child of the debug node). Per-bug pipeline follows; each fix attempt = one hypothesis per attempt node (bounded-attempt rule).

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| D0 | Bug identification | yes | M | channel evidence (report, anomalies) | `{bugs: [{symptom, evidence, suspected location, severity, reproducible}] \| []}` — one step, merged question |
| D1 | Mechanical failure triage | yes | H rules → M fallback | error excerpt | triage {test-bug, code-bug, env} + location |
| D2 | Probe proposal | yes | M | evidence-so-far | probe {command, expected-info, why} |
| D3 | Probe execution | yes | H | probe | shaped output (wrapper registry) |
| D4 | Probe interpretation | yes | M | shaped output | finding {fact, implies} (appended to evidence) |
| D5 | Hypothesis formation + confidence ranking | yes | M | evidence list | hypotheses[{mechanism, predicted-fix, falsification test, confidence}] |
| D6 | Falsification run | yes | H+M | top hypothesis | verdict {confirmed, killed}; **schema carries {n_trials, observed_rate}** — flaky/intermittent bugs get rate thresholds; irreproducible → needs-user park ladder, never infinite verdict flip |
| D7 | Probe loop bound | yes | H (script) | round count | continue / escalate-to-replan (hard cap) |
| D8a | Fix attempt implementation (one hypothesis per node) | yes | M (→ E-flow) | hypothesis + region | change spec → E4/E5/E6 |
| D8b | Attempt outcome recording | yes | H (from verify artifacts) | verify results | **outcome** `{fixed, fixed-with-concerns, blocked-design-question, new-bug-found, needs-user}` + reason (content for D9 authoring) |
| D9 | Dynamic tree growth / bubbling | yes | H executes; M authors proposal via `llm()` (gated by proposer≠decider) | attempt outcome + reason | new-bug → subtree proposal → accepted → child node inserted (done parent reopens, AC map re-runs); design-question → decision node marked needs-user (pauses subtree, answer via `user()`, unblocks) |

Probe loop (D2→D4) = scripted bounded loop of separate invocations (fresh session per round); each round emits clean per-round outputs; the loop ends at D5's artifact; hard cap (script-owned, ~8 rounds) → escalate. Attempt ladders are reviewable: N failed attempts with distinct hypotheses = signal to reformulate at design level (bubbles via D9). Policy-blocked probes (sandbox denials) route to allowlist requests, never into this pipeline.

## E. Implement

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| E1 | Interface/signature design | yes | M | need + conventions | signature + docstring (reviewable artifact) |
| E2 | Type/schema design | yes | M | data requirements | type definitions |
| E3 | Edge-case enumeration | yes | M | signature | case list {input, expected} (feeds tests) |
| E4 | Write new file | yes | M (whole-file) | spec + patterns + ground truth | file content |
| E5 | Edit file (bounded region) | yes | M (region rewrite) | target region + change spec | new region (H stitches) |
| E6 | Large-file split-window edit | yes | M per window | window + change spec | new window (H stitches + revalidates) |
| E7 | Boilerplate/config fill | yes | H template + M blanks | template + need | filled file |
| E8 | Dependency selection | yes | H+M | need | candidate {pkg, version, license}; **compat verified by H** (sandbox install + import probe); license allowlist policy |
| E9 | Multi-file change | NOT MINIMAL | — | — | split into E4/E5/E6 per file; **condition for spawning review agent** instead of assuming correctness |
| E9b | Multi-file compose | yes | H validates (LSP cross-file refs) → M repairs (→ E5) | all changed files | `{refs-ok, violations[] → repair specs}` — imports, call sites, type wiring |
| E10 | Check pipeline on write | yes | H | file write | verdict {clean, auto-fixed, escalated findings} |
| E11 | Feature removal | yes | M plan (ordered moves) + H verify | removal spec (what/why) | removal executed per E5; **AC = LSP zero-references check** + doc/changelog sync |

## F. Verify

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| F1 | Test plan (parallel with code, after spec) | yes | M | AC test map + interface spec | test case list (each concrete; writer never sees implementation) |
| F2 | Test writing | yes | M | one test case + patterns | test file |
| F3 | Run tests / build / lint | yes | H | command + scope | shaped result (wrapper registry) |
| F4 | Failure triage | yes | H rules → M fallback | failure excerpt | triage {test-bug, code-bug, env} + file/function |
| F5 | Fix proposal | yes | M | triage + region | change spec (→ E5) |
| F6 | Regression selection | yes | H | touched files + test map | scoped test list |
| F7 | AC satisfaction check | yes | H for deterministic checks; H+M judge panel for subjective ACs | AC test map (authored at planning, in node schema) | done/remaining map — run the map, report green/red per checkbox; subjective ACs close via multi-aspect judge panel (no routine human confirmation) |
| F8 | Candidate-gap flagging | yes | M | done/remaining map | candidate gaps[] (become new nodes). Closure itself is procedural — the gate decides, never the model |

## G. Review & quality

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| G1 | Intent self-check (diff vs stated intent) | yes | M | diff + intent (self-summary) | issues[] (Tier 2) |
| G2 | Peer review | yes | M (fresh ctx) | diff + ACs | verdict {ok, issues[]} |
| G3 | Idiom/style conformance | yes | H | diff | rule-library hits + fixes |
| G4 | Security spot-check | yes | H tools (secret scan, dep audit, SAST: bandit/semgrep) + governed versioned checklist | diff | findings[] triaged by M into issues[] — tool-backed, never a bare model verdict |
| G4b | Review-issues triage | yes | M | issues[] (from G2/G4) | per-issue node-level change spec / new node / design-question — feeds task tree |
| G5 | Perf measurement | yes | H | benchmark cmd | metrics artifact |
| G6 | Perf interpretation + target | yes | M | metrics | bottleneck hypothesis (→ D5 flow) |
| G7 | Review adjudication | yes | H | reviewer verdicts | accept / loop-back-to-step |

## H. Document & commit

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| H1 | Doc writing | yes | M | doc spec + outline | doc file |
| H2 | Commit message | yes | M | diff + intent | message (conventional) |
| H3 | Commit/branch ops | yes | H | message + files | git state |
| H3b | Conflict detection & resolution | yes | H detects (git snapshot anomalies across steps) → H+M resolves | work-tree state | conflict report; resolution via E5-shaped steps |
| H4 | PR description | yes | M | diff + step history | description |
| H5 | Changelog entry | yes | M | diff + ACs | entry |
| H6 | Run summary | yes | M | step history + outcomes | summary artifact (closes the golden flow's "summarize") |

## I. Maintain & evolve

| # | Activity | Min? | Job | Clean input | Clean output |
| --- | --- | --- | --- | --- | --- |
| I1 | Refactor decision (what/why) | yes | M | smell signal + context | refactor plan (ordered moves) |
| I2 | Mechanical refactor exec | yes | H (LSP rename/move) | move spec | rewritten code (no model!) |
| I3 | Port/migrate unit | yes | M per unit | source unit + target idiom | ported unit (→ E10) |
| I4 | Dependency upgrade run | yes | H | upgrade spec | shaped result |
| I5 | Upgrade breakage triage | yes | M | failures | triage (→ F4 flow) |
| I6 | Memory/lesson writing | yes | M (governed) | debug evidence | lesson artifact: one line + topic key (1–6 normalized AND-terms) + provenance (governance pipeline) |
| I7 | Stats review (do more/less) | yes | H | ledger counters | keep/kill verdicts |
| I8 | Fail-pattern capture | yes | H | run outcome | FAIL_PATTERNS entry |

## J. The non-artifacts (fuzzy interior — never handed around)

Things that exist only inside a round, consumed by the model in the same breath:

- "which of these lines looks suspicious" (reasoning; its clean output = D2/D4 artifacts)
- "does this feel right" (gist judgment; clean output = a verdict enum)
- "what would I search next" (in-round; clean output = probe spec)
- "why do I believe this hypothesis" (narrative; clean output = mechanism field)
- reading comprehension of a long file (in-round; clean output = the extracted structure)

Rule: whenever one of these seems like the *deliverable*, it isn't — wrap it so the step emits its structured shadow (choice, verdict, excerpt-set, mechanism). If no structured shadow exists, the activity is a human conversation, not a model step.

**Guided thinking is a within-round strategy, not an exception to this rule** (DESIGN §2.2): an enum call → one map call per dimension → a *mechanical* reduce (union/dedup) still emits exactly one handover, so the step keeps its schema and boundary. It is a per-step-type option, spent only where coverage is the failure mode, and only after the cheaper already-specified mechanism (best-of-N + deterministic union) has been measured against it.

## Coverage check (SE phases × taxonomy)

Requirements A (root task card = tree root, user-confirmed) · planning/confirmation/scheduling = task-tree operations B · design E1–E3 · implementation E (incl. env bootstrap C6, removal E11, multi-file compose E9b) · debugging D · testing F · review G · docs/commits H (incl. conflict handling H3b) · refactoring/migration I · dependency mgmt C6/E8/I4–I5 · performance G5–G6 · security G4. Not covered (v1 non-goals, DESIGN §1): deployment ops, CI authoring, team process, production incidents/hotfixes, live-stateful data migrations. Noted dispositions: a11y/i18n audits, monorepo tooling, external API contract negotiation — deferred; legacy untested code — covered via A2 AC gate forcing characterization tests; secrets provisioning — out of scope v1 (secret *filtering* is kernel-side, §4.2).
