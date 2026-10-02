# KERNEL API — helpagent runtime kernel

Specification of the script-facing surface of the runtime kernel that executes versioned
SE-methodology scripts (`scripts/v1/`, per ENGINE_SCRIPT.md). Implementable as-is; schemas
referenced but not defined here live in **ENVELOPE_SCHEMAS.md**.

---

## 1. Trust model and the capability-object principle

- **Script = strategy, trusted.** Author code, full privileges, no sandbox (DESIGN §4.1).
  The script decides sequence, questions, injection decisions, retry/split/park logic.
- **Kernel = invariants.** Model runner + grammar envelopes, artifact schema validation,
  check pipeline on every write, erasure semantics (§2.4), sandbox, ledger/stats, memory
  governance, global run budget. Kernel never interprets the script.
- **Sandbox scope:** wraps **model-implication execution only**. Every command reaching
  `exec()` with `provenance="model"` passes filesystem scoping, allowlist, container,
  network policy — kernel-owned, script-invisible. Script-provenance exec is unsandboxed
  except for network/filesystem policy set in per-script config.
- **Capability-object principle:** the six primitives below are the *only* `k`-namespace
  callables that can (i) invoke a model, (ii) execute a command, (iii) mutate the work
  tree, (iv) pause for the user, or (v) write governed memory. Every other name reachable
  from `k` is a **handle or accessor**: a typed, read/validation/persistence surface over
  kernel-owned state that performs none of (i)–(v) and consumes no budget. Handles are
  data, not primitives. `<!-- DECISION: this rule is the reconciliation criterion for §8; DESIGN enumerates six primitives but not the status of other k.* names; this is the minimal consistent reading. -->`
- **A/B comparability:** same kernel + same corpus ⇒ the script revision is the only
  variable. The kernel must therefore be deterministic in everything except the model.

---

## 2. Reconciliation of every `k.*` call in ENGINE_SCRIPT.md

| Script call | Disposition | Where |
| --- | --- | --- |
| `k.llm(...)` (via `llm_step`) | primitive 1 | §3.1 |
| `k.exec(probe, provenance="model")` | primitive 2 | §3.2 |
| `k.compose(leaf, spec, files[, failure])` | primitive 3 (`inject`) | §3.3 |
| `k.check_write(change)` | primitive 4 | §3.4 |
| `k.memory.write(...)` | primitive 5 | §3.5 |
| `k.user(render(...))` | primitive 6 | §3.6 |
| `budget.exceeded()`, `run_config.budget` | read-only kernel-injected data object | §7 |
| `k.validate_dag(root)` | → `tree.validate_dag()` (TaskTree handle) | §4.1 |
| `node.set_ac_test_map(acs)` | NodeHandle method (kernel validates the map) | §4.2 |
| `tree.ready_leaves() / refresh_status / insert_ticket / insert_attempt / expansion_findings / has_work / snapshot / root` | TaskTree handle methods | §4.1 |
| `leaf.close()`, `node.status = ...`, `leaf.estimate_rounds`, `node.initial_evidence`, `evidence.add(f)` | node-handle members | §4.2 |
| `k.gate.run(map)`, `k.gate.all_green(leaf, ...)` | → `tree.gate.run / tree.gate.close` (bound to tree handle) | §4.3 |
| `k.index.build(repo)`, `index.files_in_scope`, `k.index.propose_cuts(node, evidence=…)`, `k.index.conventions`, `k.index.test_patterns` | Index handle + its constructor accessor | §4.4 |
| `k.git.diff(node)` | → `trajectory.diff(node)` (read from recorded per-step snapshots) | §4.5 |
| `k.trajectory.summary()`, `k.evidence.for_leaf(leaf)` | Trajectory read access | §4.5 |
| `k.ledger.resolve(refs)` | Ledger read access | §4.5 |
| `k.ledger.note(kind, text)` | Ledger handle append (typed note event only) | §4.5 |
| `k.artifacts.write(artifact, node=...)` | → `tree.attach(node, artifact)` | §4.6 |
| `k.git.dirty / k.git.reset_hard_clean / k.lock` | kernel-internal, behind `boot_recover` | §6 |
| `boot_recover(k, workdir)` | sanctioned kernel entry point `k.boot_recover(workdir)` | §6 |
| `k.triage_rules(failures)` | **raised** — see §8 | §8 |

Everything in this table is either one of the six primitives, a handle/accessor method, or
raised in §8. No seventh primitive is introduced.

---

## 3. The six primitives

All are `async`. Error convention: **programmer errors** (bad argument types, unknown
step_type, invalid handle) raise immediately; **operational outcomes** (check failures,
policy denials) return shaped results per ENVELOPE_SCHEMAS.md; **parked outcomes**
(needs-user, budget) raise after durably recording parked state. Every call appends its
event to the log (§5) and its counters to the ledger before returning or raising.

### 3.1 `llm`

```python
async def llm(step_type: str,
              artifacts: dict[str, ArtifactRef],
              question: str,
              tools: list[str] | None = None,
              fresh: bool = False) -> StepResult   # see ENVELOPE_SCHEMAS.md
```

- Loads `prompts/<step_type>.md` verbatim into the byte-stable prefix (missing file ⇒
  `PromptNotFound` raise at call time, never a silent fallback). Composes suffix via the
  composer (per-call adaptive injection, no fixed cap; per-category sub-budgets §4.3).
  `fresh=True` composes without author-context artifacts (reviewers, judges).
- `tools` = per-step-type tool set from the wrapper registry; within the step the model
  proposes tool calls — one-shot proposal → sandboxed exec → shaped result. Tool rounds
  are hard-capped at `leaf.estimate_rounds × 1.5` (kernel tracks; exhaustion ends the step
  with a `rounds_exhausted` shaped result — the split signal is the script's to act on).
- Returns the grammar-constrained, schema-validated envelope; the kernel persists it as a
  typed artifact (secret filter at the store boundary, mandatory self-summary field) and
  links it to the calling node when the script later calls `tree.attach`.
- Raises: `PromptNotFound`, `SchemaViolation` (model output fails validation after
  bounded re-ask — recorded, then raised), `BudgetExceeded` (§7).
- Invariants enforced: grammar envelopes + `unable: reason` alternative in every schema;
  schema validation; ledger/stats recording; budget accounting; erasure — the failed
  attempt's text is never returned to a later invocation, only a failure summary.
- **Schema library.** `harness/envelopes.SCHEMAS` holds one grammar envelope per
  `step_type` (ENVELOPE_SCHEMAS §0–§23, §26–§29), **28 registered** as of ticket 20. Ticket 22
  adds no schema: it extends the existing `plan_node` (ENVELOPE_SCHEMAS §23) envelope (and
  its `ChildPlan`) with the PLAN-TIME policy fields `verification_policy`
  (`test`/`review`/`either`) and the REQUIRED `verification_reason`, so the count stays 28.
  Ticket 18's
  newest was `plan_node` (ENVELOPE_SCHEMAS §23): the node tree's ONE fused
  decompose+specify call — a node's `children` plus its own goal/behavior/files/ACs plus the
  declared per-criterion test cases (`test_cases`, ticket 19 D) and the per-node verification
  policy (`verification_policy`/`verification_reason`/`review_angles`/`best_effort`+
  `best_effort_reason`, ticket 22) in a single invocation.
  Ticket 19 adds `leaf_review` (ENVELOPE_SCHEMAS §26): the review-based verification verdict
  used when no test can carry verification (goal + ACs + final diff → a five-grade ordinal
  verdict for ONE angle + evidence, ticket 20).
  Ticket 20 adds `verify` (ENVELOPE_SCHEMAS §27): the WRITTEN `none+reason` justification used
  only when the plan opted into `best_effort` and neither a discriminating test nor an
  independent review could carry the claim; a claim that survives it is recorded UNVERIFIED.
  Ticket 20 step 2a adds `how_list` (ENVELOPE_SCHEMAS §28): the node's FIRST planning step,
  N ranked approaches. Ticket 20 step 2b-ii adds `manager_decision` (ENVELOPE_SCHEMAS §29):
  the node's managing call — ONE decision from the closed four plus a required reason over
  the node's structured record.

### 3.2 `exec`

```python
async def exec(spec: ExecSpec, provenance: Literal["model", "script"]) -> ShapedResult
```

- Sandboxed command execution via the wrapper registry (`{exit, verdict, n_failures,
  excerpts, suggested_next_action}`; generic fallback shaper for rare tools — always
  ANSI-stripped, byte-capped, deduped).
- `provenance="model"` ⇒ full sandbox (fs scope, allowlist, container, network). A denial
  is a first-class `policy-blocked` shaped result routed to an allowlist request — never a
  diagnose-pipeline probe failure, never raised.
- Raw output archived to an artifact through the secret filter before the shaped result is
  returned. Work-tree-mutating side effects of probes are captured by the per-step git
  snapshot (§4.5).
- Raises: `BudgetExceeded` only. Never raises on command failure — nonzero exit is a
  shaped result.

### 3.3 `compose` (the `inject` primitive)

```python
async def compose(node: NodeHandle, spec: ArtifactRef, files: list[Path],
                  *, failure: FailureSummary | None = None) -> ComposedContext
```

- DESIGN §4.1 names this primitive `inject(...)`; the script-facing name is `compose`.
  `<!-- DECISION: ENGINE_SCRIPT calls k.compose; DESIGN's inject describes the same budgeted-injection capability — one primitive, script-facing name compose. -->`
- Builds `byte-stable prefix + step suffix`: conventions, related code excerpts, covering
  tests, AC, negative guidance, rule-library hits, memory matches, gotchas, help answers
  — per-category sub-budgets, no universal token cap; the info-miss counter is the
  discipline. `failure=` injects the honest failure summary + missing info of a prior
  round (never the failed attempt's text — erasure, §2.4).
- Repo-index lookups served from the Index handle's state (§4.4); memory matches served
  from the governed memory store (provisional items at low injection priority).
- Raises: nothing operational. Pure assembly; no budget consumed beyond what the
  subsequent `llm()` call accounts.

### 3.4 `check_write`

```python
async def check_write(change: ProposedChange) -> WriteResult   # {ok, verdict, findings}
```

- The work-tree write path: whole-file or bounded-region content → harness computes diff
  → check pipeline ladder (formatter → autofixer ≤2 passes → tree-sitter parse →
  project-wide type check filtered to touched findings → scoped tests → rule library →
  intent check tier 1/2).
- Auto-fix everything trivial, re-check; survivors escalated once as a shaped result;
  unfixable ⇒ **work-tree rollback via harness git** + ledger append, `ok=False` returned.
  Model never sees failed text — only the shaped survivor summary.
- Enforces invariants: file tracking & trajectory snapshot after every work-tree mutation
  (including probe side effects); work-tree exclusivity — a second writer in the same
  file-overlap group parks (`WriteContended`, §4.1 ready_leaves); secret filter on the
  diff artifact; index refresh triggered for exactly the changed paths.
- Raises: `BudgetExceeded` only.

### 3.5 `memory.write`

```python
async def memory.write(lesson: LessonDraft) -> MemoryRef
```

- Governed memory store. `LessonDraft` = one line + topic key (1–6 normalized
  space-separated terms) + mandatory provenance (task, erased-failure ref, timestamp).
- Kernel runs deterministic checks (term sanity, evidence ref resolves in ledger, overlap
  set algebra) synchronously; the reviewer/debate/promotion pipeline is async and never
  blocks the workflow — the draft enters as `provisional`.
- Raises: `EvidenceRefUnresolvable`, `TermKeyInvalid` (deterministic pre-checks).

### 3.6 `user`

```python
async def user(message: UserPrompt) -> AnswerArtifact
```

- Pauses the calling subtree only (other ready leaves keep running); lands the question as
  an event (`user.requested`) pushed to the message box immediately; the typed answer
  arrives as an artifact and the call unblocks. Also the surface for decision-node
  answers (D9) and mid-run steering delivery.
- A4 cap: the kernel enforces max 3 clarification rounds per task card; round 4 raises
  `ClarificationCapExceeded` after marking the node `needs-user`.
- Autonomy dial (per run config): `auto_answer` mode answers with the configured
  conservative default instead of pausing — logged, counted into the needs-user metric.
  The script cannot tell the difference; the artifact records which happened.
- Raises: `RunTerminated` (user aborted the run while paused).

---

## 4. Handle objects

Handles are obtained from the kernel-injected namespace or as return values. They are
plain data objects over kernel-owned state; the kernel re-validates every mutation at the
next tree commit point and emits an event per mutation.

### 4.1 `TaskTree`

The one plan artifact (DESIGN §4.8, TASK_TAXONOMY §B). Node schema:
`{id, what, why, input, output, ac_test_map, risk, produced_artifact_id, status, children}`;
`input`/`output` are typed artifact references with explicit producer ids. Status ∈
`{pending, in-progress, done, blocked, stale, needs-user}`. Methods:

- `tree.root`, `tree.snapshot()` — read-only views (snapshot feeds run-summary).
- `tree.validate_dag()` — validates I/O edges into an execution DAG: orphan inputs,
  duplicate producers, cycles ⇒ `ValidationFindings` returned (script routes to
  re-expansion), never a silent stall. Kernel-enforced (B3).
- `tree.ready_leaves() -> list[NodeHandle]` — leaves whose deps are satisfied, not held
  (no pending `user()` question), and whose files are unlocked. **File-overlap grouping:**
  leaves are grouped by overlap of their declared `files` boundary; at most one writer per
  group is ready concurrently (v1: one writer per group, groups run in parallel);
  read-only judges/peers are never in a writer group. This is the scheduler input for the
  script's parallel DAG loop.
- `tree.refresh_status()` — re-validates upward: closure requires (a) every AC **present in
the node's map** has ≥1 test, (b) those tests pass unconditionally, (c) all children closed
first; re-validates `done` parents whose subtree was touched. A node with no map closes on
(c) alone.
- `tree.insert_ticket(parent, issue) -> NodeHandle`,
  `tree.insert_attempt(node, hypothesis) -> NodeHandle` — tree edits; kernel assigns ids,
  validates producer/input refs, runs the **cascade**: insertion/modification under a
  `done` parent reopens it (status → `in-progress`) and re-runs its AC map; touched
  branch ⇒ children marked `stale` (must re-verify); touched leaf ⇒ parents re-validate
  upward. Serves B4 user patches and D9 growth identically.
- `tree.has_work()`, `tree.expansion_findings()` — read-only.

### 4.2 `NodeHandle`

- `node.status` — script may assign; kernel validates the transition table
  (`<!-- DECISION: script writes statuses directly in ENGINE_SCRIPT; kernel re-validates at refresh/commit rather than gating every assignment — minimal change to the script. -->`). Illegal transition ⇒ `StatusTransitionInvalid` at commit.
- `node.set_ac_test_map(raw)` — kernel validates every `ac_id → ≥1 executable check`
  (`{check_id, command}` or `subjective`); invalid ⇒ findings returned (A2: uncheckable
  ⇒ needs-human path). Replaces `k.validate_ac_map`. The map is held in the node schema
  before any work starts. **Mandatory for leaves, optional for internal nodes** — an
  internal map is an integration view whose every entry must resolve to a descendant
  check or an existing command at close time (`<!-- DECISION: references-not-copies keeps
  E2E/integration ACs expressible without repeating leaf ACs at every ancestor; an entry
  that resolves to nothing fails the node's close, which is the existing generic path
  (findings → re-expansion) rather than a new mechanism. -->`). Authored by `draft_acs`
  and **decided by `gate_decide` before the map is frozen** (ENVELOPE_SCHEMAS §6).
- `node.close(results, quality, verdicts) -> bool` — the script proposes closure; the
  kernel re-checks (a)(b)(c) itself and refuses (`False` + reasons) if not green. The
  model never decides closure (F7/F8).
- `node.gate` — see §4.3. `node.initial_evidence`, `node.estimate_rounds`,
  `node.risk`, `node.produced_artifact_id` — read-only fields.

### 4.3 `tree.gate` (closure gate, bound to the tree handle)

`<!-- DECISION: k.gate.* operates only on the tree's AC maps; binding it to the TaskTree handle keeps it a handle method (§1 criterion) while remaining kernel-enforced per DESIGN §4.8. -->`

- `tree.gate.run(ac_test_map) -> GateResults` — mechanically executes every deterministic
  check in the map (existence/completeness of tests per AC checked by code, never by LLM).
  Runs over any node's map, leaf or internal. Read-only over the work tree; returns
  `{per_check verdicts, all_map_entries_have_tests, missing, failures}`.
- `tree.gate.close(leaf, results, quality, verdicts) -> bool` — combines deterministic
  green + judge-panel verdicts (subjective ACs, multi-aspect, config-driven fleet) and
  applies `leaf.close` semantics. Rejection reasons are structured (per-AC, per-rule).

### 4.4 Index handle

- `index = await k.index.build(repo)` — builds/resumes the repo index (symbol table,
  module map, test map, convention file). Incremental: refresh rescans exactly the paths
  in the trajectory change records. **Called before A/B: B1 consumes candidate cuts and A3
  consumes the index, so building it after planning is an ordering bug, not a style choice.**
  `<!-- DECISION: k.index.build performs kernel-internal infra compute over kernel-owned state (no model call, no work-tree mutation, no budget); under §1 it is a handle constructor accessor, not a primitive. -->`
- `index.files_in_scope(leaf)`, `index.conventions`, `index.test_patterns`,
  `index.propose_cuts(node, evidence=None)` — candidate cuts for B1, in two modes selected by
  task class (TASK_TAXONOMY pipeline routing): **structural** (`evidence=None`) = module-map
  seams, for tasks whose location is known or irrelevant; **evidence-seeded** (`evidence` =
  the locate/reproduce artifact) = cuts around the failing symbol, stack frames and covering
  tests, for tasks where the location is the unknown. All read-only.
  `<!-- DECISION: the model must not choose the file to change from filenames alone — that is
  a lookup, and DESIGN §2.1 forbids handing the model a lookup. The mode split keeps
  propose-validate for feature work without letting a diagnostic plan be fabricated from names. -->`

### 4.5 Trajectory / Ledger read access

- Per-step git snapshot (harness-owned git; the model never calls git) records
  `{step_id, node_id, files_changed, diff, commands_run, round transcripts, check
  results, outcome}`. Script reads:
  - `trajectory.diff(node) -> DiffArtifact` — the recorded snapshot diff (replaces
    `k.git.diff`; `<!-- DECISION: harness git rollback/reset are kernel-internal to check_write/boot; only the recorded read-view is script-facing. -->`).
  - `trajectory.summary() -> TrajectorySummary` (H6 input).
  - `trajectory.evidence_for(leaf) -> EvidenceArtifact` (replaces `k.evidence.for_leaf`;
    evidence lives in the node's evidence artifact, not in any conversation).
- `ledger.resolve(refs) -> list[LedgerEntry]` — evidence-ref resolution for gate review
  (reason describes reality ⇒ refs must resolve). `ledger.note(kind, text)` appends a
  typed note event; append-only is absolute, erasure never deletes entries
  (`<!-- DECISION: kernel owns the ledger store; scripts may append typed notes (boot notes, script-level markers) but never edit — keeps boot_recover's audit trail without a write primitive. -->`).

### 4.6 Artifact handles

Typed, bounded, pydantic-validated (schemas per leaf-type library, selected never
authored by the model; rendered fill-in forms; mandatory self-summary). Content passes
the secret filter **at the store boundary** — diffs, transcripts, raw tool output
included; the review-phase scan is not the gate. Code output overflow never truncates —
it triggers the pre-declared split-window path.

- `tree.attach(node, artifact)` — sets `produced_artifact_id`; kernel validates the
  artifact schema and the single-producer rule. Replaces `k.artifacts.write`
  (`<!-- DECISION: llm() results already persist automatically; the only script-visible operation left is linking an artifact to a node — a tree-handle method. -->`).
- Artifact handles are immutable once attached; reads return bounded excerpts on demand.

---

## 5. Event log contract

Append-only event stream; both the ledger and the UI consume it (UI_DESIGN.md §8 — the UI
is a consumer, not a peer; killing the UI changes nothing). The same events the ledger
records; the UI adds zero new state.

- **Ordering:** monotonic `seq` per `run_id`; emitted after the step's artifacts are
  committed (a step's events never precede its artifact persistence). Crash mid-step ⇒ no
  events for the unflushed step; the last committed step is the truth (§6).
- **Envelope:** `{run_id, seq, ts, type, node_id?, script_revision, payload}` — payload
  schemas in ENVELOPE_SCHEMAS.md.
- **Event types:** `node.status_changed{from,to,reason}` · `step.completed{step_id,
  artifact_ref, counters}` · `llm.invocation{step_type, tokens, wall_model, wall_tool,
  cache_hit, fresh}` (no content) · `exec.result{exit, verdict, policy_blocked?}` (shaped
  only, raw archived) · `check.verdict{clean|auto_fixed|escalated|rolled_back, findings}` ·
  `write.committed / write.rolled_back{files, diff_ref}` · `user.requested{question_ref} /
  user.answered{ref, auto: bool}` · `gate.verdict{per_ac, closed: bool}` ·
  `tree.cascade{reopened[], staled[]}` · `budget.warning / budget.exceeded{cap, value}` ·
  `boot.recover{action, details}` · `ledger.note{kind}` · `memory.governance{stage,
  verdict}`.
- Delivery: read-only state socket (tree snapshot + per-node trajectory stream + event
  feed), replayable from seq 0. Notifications (banner-worthy: needs-user, all-idle,
  boot-reset, budget) are UI-side subscriptions on these types — the kernel pushes no
  notification concepts of its own.

---

## 6. Boot sequence

`async def k.boot_recover(workdir) -> BootReport` — the single sanctioned startup call;
its internals are kernel-internal. `<!-- DECISION: ENGINE_SCRIPT implements boot_recover as script code calling k.lock/k.git.*; hand-resetting the work tree and taking the instance lock are kernel invariants (work-tree exclusivity), so the machinery moves inside the kernel and the script gets one auditable entry point. -->`

1. **Single-instance lock** per workdir (file lock; a second harness process fails fast,
   `InstanceLocked`).
2. **Reset unknown state:** if `git dirty` (uncommitted / untracked / non-ignored) —
   trajectory may not have flushed — `reset_hard_clean`. The workdir is harness-owned;
   runs start only from a clean tree. Emits `boot.recover` event + ledger note
   (feeds the UI crash/boot-reset notification).
3. **Index:** reuse if present and consistent with HEAD, else build; refresh is
   incremental thereafter (§4.4).
4. **Tree resumption:** reload the task tree artifact; resume from the last committed
   step. Artifacts are the memory, files are rebuilt by re-execution: `done` nodes keep
   status (their artifacts are committed); `in-progress` nodes reset to `pending`
   (their work-tree state was wiped in step 2); `needs-user` nodes stay held. Emits
   `node.status_changed` for every reset.

---

## 7. Budget enforcement

Global run budget, kernel-enforced, per task class: `max_leaves`, `max_calls`,
`max_wall`. Expansion appetite is bounded per-parent (depth 3–4, 5–15 leaves/parent — a default,
not a hard bound) but
the global cap is what stops 3,000-leaf trees.

- **Pre-check:** before each primitive call the kernel verifies headroom. `budget`
  (from `run_config`) exposes read-only `exceeded()` and remaining counters so the script
  can route early (e.g. `expand_subtree` marks `needs-user` instead of recursing).
- **Overflow semantics:** the primitive durably records the calling node as `needs-user`
  and emits `budget.exceeded`, **then** raises `BudgetExceeded`. `<!-- DECISION: DESIGN says overflow → needs-user status; ENGINE_SCRIPT says throws BudgetExceeded → pilot UI. Both: park first (durable, resumable), then throw so the script's run-level handler exits to the pilot UI. -->`
- **What the script sees:** `BudgetExceeded` at any primitive call site; parked node and
  event already recorded, so resumption after a user budget raise continues from the last
  committed step. No shaped-error soft variant — budget is a hard invariant.
- **Per-step round budget** (leaf estimate × 1.5) is enforced *inside* `llm()` as
  `rounds_exhausted` shaped results feeding the split signal — exhaustion is data, not an
  exception. Warnings (`budget.warning`) fire at configurable thresholds for the UI.

---

## 8. Gaps requiring a 7th primitive or kernel-internal reclassification

**G1. `k.triage_rules(failures)` (D1 mechanical failure triage).** Not one of the six
primitives; not a method on any handle the script otherwise holds; yet it is real kernel
logic (deterministic rule-library application, H job per TASK_TAXONOMY). **Raised.**
Recommendation: reclassify as a read-only query surface on the Knowledge Service, exposed
as `index.rules.triage(failures)` — same status as the Index handle: deterministic,
consumes/produces data only, no model invocation, no budget. This respects §1's criterion
(never invokes/executes/mutates/pauses/governs) without a 7th primitive. Alternative if
rejected: make triage a step the script performs via `llm()` with an M fallback — but
that contradicts D1's "H rules → M fallback" ordering. *(Recommendation stands: handle
query surface, not a primitive.)*

**G2. Script-authored artifacts that are not `llm()` results.** `k.artifacts.write` was
folded into `tree.attach` on the grounds that every scripted artifact in v1 originates
from an `llm()` call. If a future script needs to persist a purely harness-computed
artifact (e.g. a benchmark stats artifact), `tree.attach` must accept store-less drafts —
still a tree-handle method, since schema validation + secret filter + single-producer are
kernel-side anyway. No 7th primitive required; watch for scripts wanting *unattached*
artifact storage (store-level `put/get`), which would be a genuine new surface.

**G3. `k.lock` as a general facility.** Folded into `boot_recover`. If scripts ever need
other critical sections (v1 has none — work-tree exclusivity is kernel-enforced via
file-overlap groups), a general script-facing lock would be a new capability outside all
six primitives. Keep it kernel-internal until a concrete script needs it.

**G4. Direct `node.status` assignment vs handle-enforced transitions.** The script
assigns statuses directly (ENGINE_SCRIPT). Kernel re-validation at commit is the minimal
reconciliation, but it means invalid states are observable between assignment and commit.
If that proves bug-prone, switch to `node.set_status()` with an eager transition table —
a handle-method change, not a primitive change.

No seventh primitive is introduced by this spec. Every script call in ENGINE_SCRIPT.md is
accounted for in §2.

---

## 9. Tree runner entry points (ticket 18)

The budgeted node tree (DESIGN §10.1–§10.2) is driven by three script-facing functions in
`harness/tree_run.py`. None is a seventh primitive: they compose the six primitives over
the `TaskTree` handle and call `run_leaf` (the leaf loop) VERBATIM for every leaf.

- `run_tree(model, root, tree, workdir, budget, *, root_grader_paths, ...)` — the tree
  executor: one `plan_node` call per node, weighted budget split, and the shared
  `budget.deadline_ts` as the final stop (no new node starts once it passes).
  `root_grader_paths` is the single withheld set every descendant leaf inherits.
- `run_node(ctx, node, budget)` — one node: decompose if it can afford to, else execute it
  as a leaf; applies the L6 (re-split) / L7 (parent spec) subtree resets and the
  structural close rule.
- `leaf_spec_from(spec, workdir, *, root_grader_paths)` — builds the `LeafSpec` a node's
  `run_leaf` call receives. The node's declared `files` are BOTH the blind view and the
  runtime write boundary (a write outside it is refused at the parameter layer), and
  `grader_paths` is always the root's set — never anything a child declared.

An internal node closes only when all children closed and its own integration ACs pass;
an empty integration map is not by itself sufficient — a node with ≥2 writing descendants
needs a passing report-gated integration verdict from its dedicated integration leaf, and
a failing verdict reopens its responsible writer descendants (bounded per node).
<!-- DECISION: the structural close rule is deterministic (writing-descendant count), not
an extra model call; an integration leaf that exposes no test artifact is not a verdict
(no keys ⇒ no close). -->

## 10. The How axis, selection, and the manager loop (ticket 20 steps 2a/2b-ii)

`harness/how.py` owns the pieces below. None is a seventh primitive: the How axis and the
manager loop are composition over the six primitives (the first planning call is one
`how_list` envelope; each explored How is one `plan_node` bound to its `how_id`).

- **Hows are the diversity axis.** `HowList` is an APPEND-ONLY, frozen list of `How`
  records `{id, text, rank, reason, prior, status}` with `status` one of `untried`,
  `active`, `succeeded`, `failed`, `abandoned`. The content is immutable and a status
  transition returns a NEW `How`; a failure never edits a How or its decomposition — it
  appends a NEW How and marks the old one failed/abandoned.
- **The prior is a scheduler hint, never evidence.** `prior_for_rank` is the default
  geometric decay table (rank 1 ⇒ 0.5); `how_viability(prior, children)` is
  `prior × best viable child value`, with failed/abandoned children removed. Success is
  decided ONLY by hard evidence (tests / integration verification).
- **The plan-time test list is the contract.** The planning step declares each test point
  as a `harness.how.TestPoint` — its NAME, the FILE it lives in, WHAT it verifies (the AC
  statement it serves), and the acceptance criterion it serves. `planned_test_points(spec)`
  reads it from the plan's declared test cases; the list flows into the run record (the
  candidate's `planned_points`) and into the selection key. `point_results(points, leaves)`
  reads a candidate's own-test gate reports: an UNOBSERVED declared point is uncovered (it
  never counts as a pass). `extra_test_points(points, leaves)` names the two-way DEVIATION —
  extra tests beyond the plan do NOT score; they ride the node's structured record to the
  manager, which decides whether the plan under-specified or the implementation is padding.
- **The selection function** (`select_key`) is the pure, lexicographic, deterministic key
  `(test score, review score, rank, cost)`. Test score =
  `planned_test_score(planned, results)` = (planned points covered, pass rate over the
  PLANNED points); no tests ⇒ 0. The points are the candidate's DECLARED points, never the
  tests it invented. Review score = the predefined weighted angle aggregate
  `combine_review_verdicts` with the critical-angle veto; no review ⇒ 0. Ties fall through
  to rank, then to smaller cost. A negative review grade is an ACTION ITEM
  (`Selection.repair_reason`), not merely a lost comparison.
- **The manager loop** (`decide_after_failure`). When a How fails or exhausts, the node's
  STRUCTURED RECORD (`NodeRecordView`: How list with statuses, each failure's evidence and
  reason, which Hows remain untried, and the test DEVIATIONS) goes to the managing call,
  which returns ONE decision plus a reason out of exactly four:
  `continue-with-next-how`, `author-a-new-how`, `request-feasibility-review`,
  `escalate-or-park`. Automatic advance is allowed ONLY when a feasibility review judged
  the How infeasible; otherwise the manager decides. Every decision is recorded
  (`CandidateSet.decisions`). The REAL manager is a fresh-context model call
  (`bench/v2_tree.model_manager`, ENVELOPE_SCHEMAS §29) wired into the product tree driver;
  with no manager injected the node parks.
- **The plan-time test list flows to the leaf.** A child's declared test cases ride its
  `NodeSpec.test_cases` into `leaf_spec_from`'s `LeafSpec.test_cases` unchanged, so the leaf
  that implements the tests verifies the declared file/function contract mechanically
  (`_declared_test_case_problems`); a missing point blocks the claim.
- **No destructive reset.** Each How candidate works in its OWN isolated directory copied
  under the run's output area (`create_candidate` → `<run_outdir>/candidates/<node>/<how>`).
  Abandoning a How discards its directory (`abandon_candidate`) and appends a new How. There
  is no `git reset`/`git clean` on a candidate path; the existing write-boundary audit is
  applied per-candidate-directory (`audit_candidate_boundary`). Git worktrees are a later
  round. This is WIRED: `run_node`/`_attempt_internal` no longer reset the node's subtree
  with `trajectory.reset_to` for L6/L7.
- **The node record area** (`NodeRecord`) is a model-maintained text record that is
  REWRITTEN (not appended) and whose every update carries a reason. It is separate from
  the ledger (harness-written, append-only, never in model context) and is NEVER evidence
  (`IS_EVIDENCE = False`).
- **Budget.** `how_exploration_limit(budget, n_hows)` bounds how many Hows a node may
  explore: the non-reserve pool divided by `min_leaf_calls + 1` (one per-How decomposition
  call plus a leaf's worth of work), capped by the number of Hows.
- **Greedy is the default (ticket 20 step 2c).** `run_tree(..., how_explore=1)` and
  `bench/v2_tree.py --how-explore N` (default `1`) control how many How candidates a node
  may OPEN. With `1` the node plans its Hows, takes the TOP-ranked one, and puts the
  budget into that single candidate; a second candidate opens only with `N > 1` (the
  tournament path is otherwise unchanged). The setting is recorded in the run record
  (`run.json` key `how_explore`). Two further greedy rules: an unusable `plan_node` result
  is not a dead How --- it falls back to running that How as a leaf in its candidate
  directory (`how_case == "fallback-leaf-How"`; only a failing leaf fails the How); and the
  chosen candidate's slice is reserved out of the node pool BEFORE its planning / manager /
  feasibility calls, which draw on the node's reserve, so they cannot starve it.
