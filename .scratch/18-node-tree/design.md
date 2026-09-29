## Current behavior (what exists today)

- `run_leaf` (leaf.py:1127) is a self-contained node: one `LeafSpec` in, one `LeafOutcome` out, spending a `Budget` via `spend()` (leaf.py:1184). It stops with exactly one `stop_reason` (leaf.py:173-186) and signals `green | green-after-test-rewrite | honest-failure | exhausted | handover | bubble`.
- `Budget` (budget.py) already implements subtree accounting: shared `deadline_ts` (budget.py:43-45), `split(n)` keeping the 25% reserve + remainder (budget.py:76-93), `release` (budget.py:95-107), `grant/deny` with reasons (budget.py:103-117), and the `<1 call per child` refusal (budget.py:89-93).
- `TaskTree`/`NodeHandle` (tree.py) is the plan artifact only: `Node.files` (tree.py:102), `set_ac_test_map` (tree.py:609), `close` (tree.py:643) with the integration-view rule enforced via `_descendant_check_keys` (tree.py:710), cascade (tree.py:330), `ready_leaves` overlap grouping (tree.py:411), `refresh_status` auto-close of mapless internal nodes (tree.py:459-482).
- Envelopes for decomposition exist but are **split across steps**: `Expand`/`ChildFill` (envelopes.py:187-250) has children but no spec; `WriteSpec` (envelopes.py:339-360) has the contract; `DraftACs` (envelopes.py:300-327) has the AC map. `SCHEMAS` is pinned at 23 (tests/unit/test_envelopes_schema.py:42).
- `Trajectory` (trajectory.py) does one baseline commit (trajectory.py:49) and per-step diffs (trajectory.py:89) — **there is no per-node checkpoint/reset yet**.
- There is **no caller** that turns a leaf into a tree; `expand` is currently only exercised by the legacy golden pipeline and the "unavailable" test.

---

## The next layer: `run_tree` over `TaskTree`, calling `run_leaf` unchanged

Two new modules: `harness/node.py` (creation + deterministic validation) and `harness/tree_run.py` (recursive budgeted executor + L6/L7). `run_leaf` is called verbatim for every leaf; nothing in it changes.

### (1) Node creation flow

`requirement triage -> decompose+specify (ONE call per node) -> children`.

- **Triage** is the root's single `plan_node` call. The request is sliced deterministically first (reuse `extract_acs`, bench/v2_leaf.py:110) and the SSOT docs are injected by the composer; the root's `children` **are** the discrete issues. No extra schema.
- **One call per node** requires a new fused envelope `PlanNode` (ENVELOPE_SCHEMAS §23; `SCHEMAS` 23→24). Reusing `expand`+`write_spec` would be two calls and violates "ONE call per node".

```python
class ChildPlan(BaseModel):                      # harness/envelopes.py
    model_config = ConfigDict(extra="forbid")
    what: str = req(min_length=1)                # child goal (one line)
    why: str = req(min_length=1)
    kind: Literal["leaf", "internal"] = req()
    files: list[str] = Field(default_factory=list)   # leaf write boundary; [] for pure internal
    acs: list[DraftAC] = Field(default_factory=list) # leaf: mandatory; internal: integration view
    interfaces: list[Interface] = Field(default_factory=list)
    est_calls: int = Field(ge=1, le=8)           # budget-allocation weight

class PlanNode(Envelope):
    goal: str = req(min_length=1)                # THIS node's goal
    behavior: str = req(min_length=1)            # shared contract
    implementation_notes: str = req(min_length=1)
    files: list[str] = req(max_length=10)        # THIS node's write boundary
    acs: list[DraftAC] = req(max_length=10)      # THIS node's AC map (leaf mandatory)
    interfaces: list[Interface] = req(max_length=8)
    children: list[ChildPlan] = req(max_length=15)   # [] ⇒ this node is a LEAF
```

**Deterministic validation** (`harness/node.py`, returns `ValidationFindings`, never raises — mirrors tree.py):

```python
def validate_decomposition(d: Decomposition, *, parent_files: set[str],
                           candidate_files: set[str], depth: int,
                           depth_cap: int, max_children: int) -> ValidationFindings:
    # 1. canonicalize every path: posix normpath, strip "./"; reject ".." and absolute
    # 2. each child.files ⊆ parent_files            (narrowing-only; mirrors WriteSpec._within_boundary, envelopes.py:352)
    # 3. pairwise (i,j): child_i.files ∩ child_j.files == ∅   ← SIBLING DISJOINTNESS (§3)
    # 4. kind=="leaf"  ⇒ children==[] and acs non-empty (mirrors DraftACs._leaf_map_mandatory, envelopes.py:322)
    #    kind=="internal" ⇒ children non-empty
    # 5. every child.est_calls >= 1 and sum(est_calls) affordable (see §2)
    # 6. no two children share a normalized `what` (dedupe)
    # 7. depth <= depth_cap and len(children) <= max_children
    # 8. grounding: any file token in what/why ∈ candidate_files (mirrors ChildFill._grounded_references, envelopes.py:216)
```

If the call returns `unable` or the findings are non-empty: re-ask **once** with the findings as evidence (spends 1); if still invalid, force the node to a leaf. Invalid output never crashes and never silently produces a child.

### (2) Budget flow

`Budget` is a first-class node field. Calls split by weight; the deadline is **shared** (budget.py:43-45) — it is not hard-split per child.

- **Split.** Parent computes `spendable = int(budget.calls * (1 - reserve_fraction))`; allocates `max(MIN_LEAF_CALLS, spendable * w_i / W)` per child capped so `Σ ≤ spendable`; if any child would fall below `MIN_LEAF_CALLS`, drop/merge the smallest children (or force a leaf) rather than emit an unworkable child. Implemented as a new `Budget.split_weighted(weights: list[int], *, min_each: int) -> list[Budget]` (composes `take`, budget.py:67) — `Budget.split` (equal shares) stays for callers that want it. The reserve + integer remainder stay with the parent.
- **Reserve** (25%, budget.py:22) pays for: the parent's own integration re-run/`close` cost, and grants to a child that bubbles "needs more" — each `grant(amount, reason)` (budget.py:103) records the reason and feeds stats.
- **Completion/release.** Every child is run in `try/finally: parent.release(child_budget)` (budget.py:95-107) so a crashed/exhausted child still returns its unused pool. Add a conservation assertion at each join: `parent.calls + Σ child.calls + spent` equals the pre-split total.
- **Handover.** `budget.expired(now)` is checked at every loop entry; when true, no new node starts, checkpoints are kept, the tree parks (`needs-user`/resume).
- **"Budget 1 cannot split".** Enforced *before any model call*:

```python
MIN_LEAF_CALLS = 3   # self-test + ≥1 implement (+ headroom); 5 when judge+iv are on

def can_decompose(budget: Budget, n_children: int = 2, *, min_leaf_calls=MIN_LEAF_CALLS) -> bool:
    spendable = int(budget.calls * (1.0 - budget.reserve_fraction))
    return spendable // n_children >= min_leaf_calls
```

If `can_decompose` is False, `run_node` skips `plan_node` and executes the node as a leaf. `Budget.split`'s `<1` refusal (budget.py:89-93) is a second line of defense, caught and converted to forced-leaf (never a crash).

### (3) Sibling file disjointness

- **Exact check (build time):** canonicalize each sibling's `files` (posix `normpath`, strip leading `./`, reject `..`/absolute), then `for i<j: set_i.isdisjoint(set_j)` must hold for **every pair**. Run in `validate_decomposition` step 3, before children are inserted.
- **Why build-time and not the scheduler:** `ready_leaves()` (tree.py:411) already serializes overlapping writers, but a decomposition that hands two siblings the same file has no clean boundary and cannot be integrated deterministically.
- **On failure:** refuse the split with a structured `Finding(kind="sibling-overlap", detail="a.py: child N-1,N-3")` → re-ask `plan_node` once with the overlap as evidence; if still overlapping, **merge** the overlapping children into one (the union becomes its boundary) or force the node to a leaf; if the overlap is with a `grader_paths` entry, the split is rejected outright.

### (4) Internal nodes vs leaves

- **File list:** a **leaf** owns its write boundary (`Node.files`, tree.py:102) — the source files it may write; its own test is written at runtime at a free path by `run_leaf` (`_relocate_self_test`, leaf.py). A pure-internal node owns `files=[]`.
- **Integration tests:** any behavior that spans children and is not owned by one child gets its **own dedicated integration leaf** (`kind="leaf"`, `files=[the integration test path]`, `acs=[the integration ACs]`). It goes through `run_leaf` unchanged, so red-on-arrival + independent test + report gate apply to it automatically. The internal node owns only the **integration AC map (references)**.
- **Parent's own integration ACs:** stored via `set_ac_test_map` (tree.py:609) as `check_kind="test"` entries whose `key` is a descendant leaf's test id. `close()` (tree.py:643) already enforces each key resolves to a descendant check (`_descendant_check_keys`, tree.py:710) and passes.
- **Verification with existing machinery:** before `close()`, `integration_verdicts()` re-runs every referenced descendant test on the **frozen final tree** through the report gate (`gate_report.evaluate_gate`), producing `CheckResults(verdicts={key: "pass"})` — so the parent integration AC is machine-verified, never aggregated from child `claimed` flags. A regression reopens the responsible child (`stale`).
- **Anti-false-close guard:** `refresh_status` auto-closes mapless internal nodes (tree.py:459-482). The tree runner therefore requires an explicit `close()` at the root and at any internal node with ≥2 writing descendants; an empty integration map is allowed only with a `no-integration` flag decided by `gate_decide` (envelopes.py:674) — never by the authoring call.

### (5) Escalation L6 / L7

- **L6 (re-split into smaller children)** — trigger: `run_leaf` returns `signal=="exhausted"` (`stop_reason=="attempts"`, `exhausted=True`). This is already the leaf's structural terminal — `harness/attempts.exhausted` (attempts.py:144-163) guarantees it only fires after a same-verdict tail + ≥3 layers, so a re-split is the correct next lever.
- **L7 (parent spec was wrong)** — trigger: `run_leaf` returns `needs_parent==True` with `stop_reason=="spec-bubble"` (set when the judge attributes the failure to `spec`, leaf.py `stop("bubble","spec-bubble",…,parent=True)`).
- **Git reset:** extend `Trajectory` (trajectory.py:36):

```python
def checkpoint(self, node_id: str) -> str:      # git add -A; commit -q -m "checkpoint:<node_id>"; return HEAD sha
def reset_to(self, sha: str, *, reason: str, note=None) -> None:
    # record every SHA discarded since sha into the append-only ledger FIRST,
    # then git reset --hard <sha> && git clean -fdq   (no -x: ignored files kept)
```

A checkpoint is taken before each node's first mutation. L6 resets to **that node's** pre-checkpoint; L7 resets to the **owning parent's** pre-checkpoint. Because writes are serialized (DESIGN §4.8), sibling branches are untouched. After reset, re-run `plan_node` on the same node (L6) or the parent (L7) with the child's `failure_signature`/judge verdict as evidence.
- **Avoid repeating the same split:** per-node `SplitHistory: list[SplitAttempt]` where `signature = hash(sorted(norm(child goios)) + sorted(sorted-files))`. A new decomposition is refused (recorded `wasted`, ladder advances) when its signature equals a prior one **and** it did not shrink the unit. Shrink rule: `max(child_budget) < prior_max_child_budget` **or** `len(children) > prior_len`. Mirror `attempts.prefilter` (attempts.py:117-140). L7 likewise requires the new spec to differ from the old on `behavior`/`interfaces`/`acs` (deterministic diff). Bound L6/L7 rounds per node (≤2) then `needs-user`.

### (6) Module / interface proposal

```python
# harness/node.py
NodeKind = Literal["internal", "leaf"]
@dataclass(frozen=True)
class NodeSpec:
    goal: str; files: tuple[str, ...]; acs: tuple[str, ...]
    interfaces: tuple[str, ...]; kind: NodeKind; est_calls: int = 1
@dataclass(frozen=True)
class Decomposition:
    spec: NodeSpec; children: tuple[NodeSpec, ...]; signature: str

async def plan_node(model, *, goal: str, evidence: str, boundary: set[str],
                    candidate_files: set[str], depth: int, grader_paths: tuple[str, ...],
                    context: dict) -> Decomposition: ...          # ONE llm_step("plan_node")

def validate_decomposition(d, *, parent_files, candidate_files, depth, depth_cap,
                           max_children) -> ValidationFindings: ...
def split_weighted(budget: Budget, weights: list[int], *, min_leaf_calls) -> list[Budget]: ...
def can_decompose(budget, n_children=2, *, min_leaf_calls=MIN_LEAF_CALLS) -> bool: ...

# harness/tree_run.py
@dataclass
class NodeOutcome:
    node_id: str; claimed: bool; stop_reason: str      # "closed"|"resplit"|"respec"|"parked"|leaf stop_reason
    leaf: LeafOutcome | None; children: list["NodeOutcome"]
    calls: int; wall_s: float; integration_verdicts: dict[str, str]; reset_to: str | None
@dataclass
class TreeOutcome:
    root: NodeOutcome; claimed: bool; calls: int; wall_s: float
    budget: Budget; checkpoints: dict[str, str]; split_history: dict[str, list]

async def run_tree(model, root: NodeSpec, tree: TaskTree, workdir: Path, budget: Budget, *,
                   root_grader_paths: tuple[str, ...], judge=None, iv=None,
                   run_tests=None, now=None, on_event=None,
                   depth_cap: int = 4, max_children: int = 15,
                   min_leaf_calls: int = MIN_LEAF_CALLS) -> TreeOutcome: ...

async def run_node(ctx, node: NodeHandle, budget: Budget) -> NodeOutcome: ...

def leaf_spec_from(node: NodeSpec, workdir: Path, *,
                   root_grader_paths: tuple[str, ...]) -> LeafSpec: ...   # reuses source_only view
def integration_verdicts(tree, node, run_tests, workdir) -> CheckResults: ...
```

`leaf_spec_from` builds the `LeafSpec` from `Node` (goal/files/acs/interfaces) and **always** sets `grader_paths=root_grader_paths` (single source, so no child can write a withheld path). `run_node` calls `run_leaf(model, spec, workdir, budget, judge=judge, iv=iv, run_tests=run_tests, now=now, on_event=on_event)` — same signature, no branch inside `run_leaf`. Tree edits/status/close all go through the existing `tree.py` handles (`insert_ticket` tree.py:214, `set_ac_test_map` tree.py:609, `close` tree.py:643, cascade tree.py:330).

### (7) Minimal test list (name → the exact bug it pins)

1. `test_sibling_files_must_be_disjoint` — two children declaring the same file are refused at build time (otherwise two writers claim one file and the split is ill-defined).
2. `test_path_canonicalization_blocks_disjointness_evasion` — `./pkg/a.py` vs `pkg/./a.py` vs `pkg/a.py` are detected as overlapping (otherwise the disjointness check is bypassable).
3. `test_budget_one_cannot_split` — a node with budget 1 (or `can_decompose` False) never calls the decomposer and runs as a leaf (pins the DESIGN §10.2 rule; a `BudgetError` from `split` never escapes).
4. `test_split_keeps_reserve_and_releases_children` — reserve stays with the parent and unused child calls return; conservation holds at the join (pins budget leaks/double-count).
5. `test_internal_close_requires_integration_pass` — a parent with an integration AC cannot close while that check has no passing verdict (pins the auto-close false success, tree.py:459).
6. `test_leaf_inherits_root_grader_paths` — every descendant `LeafSpec.grader_paths` is the root's set (pins a withheld-file write via a child spec).
7. `test_spec_bubble_triggers_l7_and_resets_subtree` — a child `needs_parent=True` causes a git reset to the parent checkpoint + a re-`plan_node` with the failure as evidence, never a fresh `run_leaf` on the same spec.
8. `test_exhausted_child_triggers_l6_resplit` — `signal=="exhausted"` re-splits into smaller children.
9. `test_identical_resplit_is_refused_as_wasted` — a re-split with the same signature and no shrink is refused (pins the T-31 "nine identical retries" defect at the tree layer).
10. `test_subtree_reset_leaves_siblings_untouched` — L6/L7 reset restores only the node's own branch and records discarded SHAs (pins work-tree exclusivity).
11. `test_deadline_expiry_stops_tree_and_keeps_checkpoints` — after the shared deadline no new node starts and the tree persists for resume.
12. `test_tree_calls_run_leaf_unchanged` — monkeypatch `harness.tree_run.run_leaf` and assert it is invoked with a `LeafSpec`/`Budget` (pins that the tree layer reuses the leaf loop instead of reimplementing it).

### (8) Top five false-success / runaway vectors + deterministic guards

1. **Parent closes with no real integration check** (mapless internal node auto-closes, tree.py:459-482; empty internal maps are "optional"). Guard: explicit `close()` required at the root and any internal node with ≥2 writing descendants; an empty map needs a `gate_decide`-approved `no-integration` flag; `integration_verdicts()` must produce a passing machine-readable report for every referenced check.
2. **Aggregating child `claimed=True` on a stale/overwritten tree** (a later child breaks an earlier one; children may have overlapped). Guard: before any internal `close()`, re-run every referenced descendant check on the **frozen final tree** via the report gate; any regression reopens the responsible child (`stale`) — the parent never closes on child claims alone.
3. **Runaway/never-terminating decomposition** (each split is affordable, or an L6/L7 loop repeats the same split). Guard: `can_decompose` + `MIN_LEAF_CALLS` refuse unworkable splits; per-node `SplitHistory` + shrink-or-differ rule refuses repeats; depth cap 3–4 and leaves-per-parent ≤15; a kernel-enforced global node budget per task class; the shared deadline is the final stop.
4. **Budget leak / double-spend on child completion** (unreleased child pool starves siblings, or a re-run reuses a spent pool). Guard: `release` in a `finally`; `spent_calls` is monotonic (budget.py:67); a conservation assertion at every join; a node may re-run at most N times (tree-level cap mirroring `attempt_cap`, leaf.py:1177).
5. **Grader-path or shadow write slipping in through a child** (a child spec without the root's `grader_paths`, or a shadowing top-level module). Guard: `leaf_spec_from` always injects `root_grader_paths` from the root (never from child output); `run_leaf`'s existing write guard (`_source_write_problem`, `owned_paths`, staging.py:95) and the gate-time shadow scan remain the enforcement points; sibling disjointness never relaxes the grader-path check.

---

## Assumptions / unresolved decisions (each with a recommended default)

1. **New `PlanNode` envelope vs reuse `expand`+`write_spec`.** Recommendation: **new `PlanNode`** (SCHEMAS 23→24, update tests/unit/test_envelopes_schema.py:42) — the requirement is explicitly "ONE call per node"; splitting into `expand`+`write_spec` is two calls and `Expand`'s `seam_id ∈ candidate_cuts` grammar (envelopes.py:213) does not carry a spec. Confirm the schema-count bump is acceptable.
2. **Weighted vs equal child split.** Recommendation: add `Budget.split_weighted(weights, min_each)` and weight by `child.est_calls`; keep equal `split` for compatibility. Alternative: equal split + parent grants (simpler, matches DESIGN §10.2 wording literally).
3. **Hard wall-clock split.** Recommendation: **do not** hard-split the deadline (budget.py:43-45 keeps it shared); give children a soft time slice only as a scheduler ordering hint, off by default, because a hard per-child split can starve the one child doing the real work on slow-prefill hardware.
4. **`MIN_LEAF_CALLS` value.** Recommendation: 3 (no judge/iv) / 5 (judge+iv on); make it a `run_tree` parameter so it is benchmark-tunable.
5. **Where integration work lives.** Recommendation: always a dedicated integration **leaf** (so red-on-arrival + independent test + report gate apply unchanged), with the internal node holding only the reference map. Alternative: the internal node executes `run_leaf` itself with `files=[]` — rejected because `run_leaf` assumes it must implement source.
6. **Checkpoint granularity.** Recommendation: per-node commit checkpoints in the harness-owned workdir (throwaway), with discarded SHAs ledger-recorded before `reset --hard`; never applied to the user's repo.

---

DESIGN CHECKPOINT — hand this to the implementer as: (a) `harness/node.py` (`PlanNode` envelope, `Decomposition`, `validate_decomposition`, `split_weighted`/`can_decompose`); (b) `harness/tree_run.py` (`run_tree`/`run_node`, `leaf_spec_from`, `integration_verdicts`, L6/L7); (c) `Trajectory.checkpoint`/`reset_to`; (d) tests 1–12. `run_leaf`, `Budget`'s existing methods, and `tree.py` handles stay unchanged except the additive `split_weighted`.