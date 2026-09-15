# ENVELOPE SCHEMAS — Grammar-Target Output Contracts for Every `llm_step`

Companion to DESIGN §4.2/§4.7 and ENGINE_SCRIPT. One schema per `llm_step` type in `scripts/v1/`.
These are the structured envelopes a ≤4B model returns via grammar-constrained decoding
(llama.cpp GBNF / `json_schema`). Kernel-side validation duties live in **KERNEL_API.md** —
this doc names *what* must be validated; KERNEL_API.md owns *how*.

## 0. Base conventions (fixed — every envelope extends this, no variations)

```python
class Envelope(Base):
    status: Literal["ok","failed","blocked","unable"]
    comment: str                      # self-summary, ≤2 lines (DESIGN §4.2 mandatory field)
    unable_reason: str | None         # REQUIRED iff status=="unable"
```

**`unable` semantics (DESIGN §2.2):** `unable` is a legal value of every envelope's
*top-level* `status` only — never mid-generation inside a nested enum or list. The grammar
branches on `status`: the `ok` branch requires the payload fields; the `unable` branch
requires `unable_reason` and forbids payload fields (one grammar alternative each). A needed
decision is therefore always expressible without inventing content.

**Enum-first rule:** any field a 4B could hallucinate freely is an enum, a constrained
pattern, or a reference to something the harness injected (candidate-cut ids, AC ids, file
paths inside the declared boundary). Free strings appear only where the harness executes or
re-checks the content anyway (code bodies, sandboxed probe commands).

**Forms, not JSON (DESIGN §4.2):** the model never sees "produce JSON matching schema X".
The runner renders a pre-labeled fill-in form with examples inline. Forms below show the
rendered shape (short filled example); `[ ]` marks an enum choice the model fills, `-` a
list slot.

---

## 1. `task_card` — A1: raw request → structured goal (user confirms via `user()`)

```python
class TaskCard(Envelope):
    task_class: Literal["bugfix","feature","port","scaffold","refactor"]  # DECISION: taxonomy coverage set — drives budget class
    goal: str                      # ≤6 lines — what to do, constraints, out-of-scope, inline
```
<!-- DECISION: constraints/out_of_scope merged into goal — no program consumes them separately
(only LLM context, which one field serves). task_class stays: it selects the budget class. -->

```text
task_class: [bugfix]
goal:       > Sessions expire after 60s instead of 1h — fix the computation.
            > Constraints: no new dependencies; public API stays backward compatible.
            > Out of scope: session persistence across restarts.
```

**Kernel validates:** non-empty goal (length cap grammar-enforced). Budget: ~150 tok. No split risk.

## 2. `find_ambiguities` — A4: ambiguity list, hard cap 3 rounds

```python
class Ambiguity(Base):
    kind: Literal["needs-user","self-answerable"]   # DECISION: needs-user ones route to k.user()
    topic: Literal["requirement","domain","environment","conflict"]
    question: str                                   # ≤2 lines, answerable in one line

class FindAmbiguities(Envelope):
    items: list[Ambiguity]         # 0–5 items  <!-- DECISION: 5 aligns with A4's 3-round cap -->
```

```text
ambiguity 1:
  kind:    [needs-user]     topic: [requirement]
  question: > Is 1h the fixed expiry, or per-role configurable?
```

**Kernel validates:** none beyond schema (questions are free text by nature). Budget: ~250 tok.

## 3. `revise_task_card` — loop feedback: trial-split findings folded back into the card

```python
class ReviseTaskCard(Envelope):
    changed: list[Literal["goal","task_class"]]  # what moved
    card: TaskCard                 # full revised payload, re-validated like §1
    because: str                   # ≤1 line — which finding drove it
```

```text
changed:    [goal]
card:
  task_class: [bugfix]
  goal:       > Sessions expire after 60s instead of 1h — fix the computation.
              > Constraints: no new dependencies; public API backward compatible;
              > the fix must not invalidate existing sessions (from split findings).
              > Out of scope: session persistence across restarts.
because:    > child task touching token format contradicted backward-compat line
```

**Kernel validates:** revised card re-validated; `because` non-empty. Budget: ~250 tok.

## 4. `expand` — B1: fill child tasks along harness-proposed seams (propose-validate)

```python
class ChildFill(Base):
    seam_id: str                   # MUST be one of the injected candidate_cuts ids — grammar enum per call
    what: str                      # ≤2 lines
    why: str                       # ≤1 line
    leaf: bool                     # leaf criterion (≤10 rounds, 1 artifact, 1 area) — harness re-checks
    est_rounds: int                # 1–10; drives per-step budget = estimate × 1.5 (B7)

class Expand(Envelope):
    children: list[ChildFill]      # 1–15 items per layer  <!-- DECISION: taxonomy default is 5–15; per-class config, not a bound — a small seam list legitimately yields fewer. -->
```

```text
child 1:
  seam_id:     [seam-3]            ← chosen from candidate list injected above
  what:        > Add expires_at check in middleware/auth.py
  why:         > Central enforcement point for all routes
  leaf:        [x]    est_rounds: [4]
```

**Kernel validates (KERNEL_API.md: DAG rules):** `seam_id` ∈ proposed candidates; est_rounds
range; leaf count within per-class config; resulting I/O edges → DAG (orphans/cycles → findings,
not stall). **`what`/`why` are reference-checked** — the enum-first rule (§0) applied to the two
free strings: any file path or symbol they name must appear in the injected candidate scope or
the symbol DB, else the child is rejected as ungrounded. Behaviors stay free text (they are
checked by `split_review`, which validates the reason against the evidence).
Budget: ~600 tok at 15 children. **Split risk: none** (children are one-liners).

**Where boundary files come from:** the injected `candidate_cuts` each carry a file scope
derived from the repo index's module map (`{seam_id, files, rationale}`). The leaf's file
boundary = its seam's file scope; `write_spec.files_touched` narrows it; writes outside it
are policy-blocked. The engine never has to guess which files a task touches — the index
told it before the model was ever asked.

<!-- DECISION: propose_cuts has two modes, chosen by task class (TASK_TAXONOMY pipeline
routing): structural (module-map seams) when the location is known or irrelevant —
feature/port/refactor/scaffold; evidence-seeded (failing symbol, stack frames, covering tests
from the locate/reproduce artifact) when the location IS the unknown — bugfix/perf/crash.
The single-mode version made the model invent the file to change from filenames alone, and
since the child's `why` becomes the leaf's spec input, an invented cause propagated as ground
truth into the spec, the ACs and the tests. Filename-only planning for a diagnostic task is a
non-goal; for those classes `expand` runs after locate. -->

## 5. `split_review` — B2: fresh-context peer review of a split

```python
class SplitIssue(Base):
    kind: Literal["overlap","missing-piece","wrong-seam","too-big","unclear-ac"]
    target: str                    # child id or "parent" — kernel checks it exists
    description: str               # ≤2 lines

class SplitReview(Envelope):
    ok: bool
    issues: list[SplitIssue]       # 0–5; ok==True ⇒ issues==[] (grammar-enforced pair)
```

**Kernel validates:** `target` resolves to a node in the reviewed subtree; ok/issues
consistency. Budget: ~300 tok.

## 6. `draft_acs` — A2: AC list + check kind per AC (a gate definition, decided by `gate_decide`)

```python
class DraftAC(Base):
    ac_id: str                     # pattern ^AC-[0-9]{1,3}$
    statement: str                 # ≤2 lines, checkbox-shaped
    check_kind: Literal["test","script-assertion","subjective"]
    check_hint: str | None         # test/assertion: command or test name hint; subjective: what to judge

class DraftACs(Envelope):
    acs: list[DraftAC]             # 0–10; EMPTY LIST = "this node has no map" — the explicit
                                   # answer for an internal node with no cross-child behavior.
                                   # A LEAF returning empty is invalid (leaf maps are mandatory).
```

**Two triggers, one schema — the input set is what differs:**

- **leaf** — after `spec_review` passes, on `{node, spec}`: the node's own checks, derived from
the contract it just froze. Authoring ACs before the spec lets a plan one-liner define the gate,
and both impl and tests then aim at an invented AC.
- **internal node** — after its children are placed, on `{node, children[], seam scopes}`:
integration ACs only — checks that span the children just placed, each resolving to a check a
descendant already owns (a command or test id). A *view*, never a copy of leaf ACs, which is also
why there is no repetition upward.

**Decided, not self-approved:** the resulting map goes to `gate_decide` (§20) in fresh context
before it is frozen — `weakens_gate` is precisely the subjective-inflation check
(`check_kind: "subjective"` where a deterministic check is feasible), and `meaning_preserved`
catches ACs that restate nothing in the spec. Authoring a gate is a gate-defining act, so
proposer≠decider (DESIGN §4.8) covers it, not just later changes.

**Kernel validates (KERNEL_API.md: AC map):** ids unique + pattern; every `check_kind !=
"subjective"` resolves to ≥1 executable check later; subjective entries must carry
`check_hint` (feeds the judge panel); **a leaf's map is non-empty; an internal node's entries
each resolve to a descendant check or an existing command at close time.** Budget: ~500 tok at 10 ACs.

## 7. `write_spec` — E1–E3 merged: the professional spec artifact

```python
class Interface(Base):
    name: str                      # symbol name — LSP-checked against injected ground truth
    signature: str                 # ≤2 lines
    contract: str                  # ≤3 lines: semantics/pre-post/invariants

class WriteSpec(Envelope):
    interfaces: list[Interface]        # 0–8 — LSP-checked against ground truth (distinct consumer)
    behavior: str                      # ≤15 lines — semantics, invariants, types, error model —
                                       # the SHARED CONTRACT: implementer AND test writer (see routing note)
    implementation_notes: str          # ≤6 lines — where the change goes and why. IMPLEMENTER-ONLY
    files_touched: list[str]           # 0–10 paths — NARROWING of the leaf boundary; must ⊆ seam file scope
```
<!-- DECISION: behaviour is routed to both sides — this is the firewall fix. The test writer
was fed `interfaces` only, so any contract detail living in `behavior` (status codes, error
model, defaults, edge cases) was invisible to it: tests asserted whatever the writer invented,
and the failure_judge then blamed a side for a gap the spec never closed. The asymmetry that
matters is on SOLUTIONS, not requirements: withhold the implementation (code) and the
`implementation_notes` from the test writer; never withhold the contract from either side. -->
<!-- DECISION: edge_cases dropped — enumerating concrete cases is test_plan's job (E3 merged into
F1: same input, one judgment round — merge rule). types_schema + error_model folded into behavior:
the composer routes them to the same consumers (implement, failure_judge), so one field. files_touched
answers "where do boundary files come from": the LEAF BOUNDARY comes from the seam candidate cut
(repo-index module map, injected into expand); the spec may narrow it, never widen — kernel checks ⊆. -->

**Kernel validates:** `files_touched` ⊆ seam file scope (the leaf boundary — narrowing only);
interface names resolve in symbol DB (ground-truth check, DESIGN §2.3). Budget: **~800 tok.**
Split rule: if interfaces > 5, re-invoke per section, harness stitches.

## 8. `spec_review` — E1 artifact reviewed fresh-context

```python
class SpecIssue(Base):
    severity: Literal["blocking","minor"]
    location: str                  # interface name or section label
    description: str               # ≤2 lines

class SpecReview(Envelope):
    ok: bool
    issues: list[SpecIssue]        # 0–6; ok==True ⇒ issues==[]
```

**Kernel validates:** location resolves. Budget: ~350 tok.

## 9. `test_plan` — F1: concrete cases per AC, enumerating edge cases from the spec

**Input is the whole contract:** `ac_test_map` + `interfaces` + `behavior`. The writer never
receives the implementation, the diff, or the implementer's `implementation_notes` — the
firewall withholds solutions, not requirements.

(absorbed E3 — merge rule). Writer never sees implementation; written BEFORE implementation exists (TDD order).

```python
class TestCase(Base):
    case_id: str                   # pattern ^TC-[0-9]{1,3}$
    ac_id: str                     # MUST exist in the leaf's AC test map — grammar enum per call
    kind: Literal["unit","api","e2e","script"]
    description: str               # ≤2 lines: setup → act → assert
```

**Kernel validates:** `ac_id` ∈ ac_test_map; every ac_id covered at least once (else
`queue_test_writing` for the missing ones — mechanical). Budget: ~600 tok at 12 cases.

## 10. `write_test` — F2: one test per case, whole-file

```python
class WriteTest(Envelope):
    file_path: str                 # within test map's scope
    content: str                   # complete file (whole-file, never diffs — DESIGN §4.7)
```

**Kernel validates:** path scope; tree-sitter parse on arrival; check pipeline on write.
Budget: **~2,500 tok — near the 3k ceiling.** Split: one `write_test` per case (already
one-per-case in the script); a single test file exceeding the ceiling goes through the
standard file-split-window path.

## 11. `implement` — E4/E5: a bounded tool-loop, not a patch emitter

The implementer works like a regular engineer within its step boundary: it receives the
spec, the boundary files, and the **canonical test commands** (written already — TDD order),
then edits files via tools (`edit_file` — each write passes the check pipeline), runs the
tests itself, and iterates within the round budget. The envelope is only the final report —
**no file contents travel in it**; the harness knows every change from the trajectory
git snapshots.

```python
class Implement(Envelope):
    # status: ok = implementer confirmed tests green itself; the gate re-verifies regardless
    tests_run: list[str]           # commands it ran (trajectory/inspection)
```

**Kernel validates:** every tool-round write through the check pipeline (auto-fix ≤2,
rollback); work confined to boundary; round budget. Budget: tiny (report only) — the
3k-output ceiling no longer binds implementation.

## 12. `failure_judge` — F4/D1 fallback: which side is buggy, before routing

```python
class Problem(Base):
    side: Literal["code","test","spec"]
    description: str               # ≤2 lines — what is wrong on that side
    evidence: str                  # ≤2 lines — file:line / test id / spec section
    confidence: Literal["low","medium","high"]

class FailureJudge(Envelope):
    problems: list[Problem]        # 0–6 — one entry per genuine problem; multiple sides allowed
```
<!-- DECISION: replaced single `side` enum with a problems list — "both sides buggy" is the
common case, and the router acts on whichever sides have entries (code → implementer,
test → fix ticket, spec → gate review), so both/all route in one verdict. -->

**Kernel validates:** each problem's evidence non-empty; any low-confidence problem triggers
best-of-N resample (DESIGN §4.7) before routing. Budget: ~300 tok.

## 13. `identify_bugs` — D0 merged question: `{bugs: [...] | []}` union

```python
class Bug(Base):
    symptom: str                   # ≤2 lines
    evidence: str                  # ≤2 lines — cite probe/findings, not vibes
    location: str                  # path#symbol or test id
    severity: Literal["critical","major","minor"]
    reproducible: bool

class IdentifyBugs(Envelope):
    bugs: list[Bug]                # 0–8; EMPTY LIST is the explicit "no bugs" answer (merge rule)
```

**Kernel validates:** each bug becomes a ticket node — `location` must resolve to an
existing path or symbol (else the bug is parked as needs-user, not dropped). Budget: ~500 tok.

## 14. `propose_probe` — D2: next most-informative probe

```python
class ProposeProbe(Envelope):
    command: str                   # free string — LEGAL: harness sandboxes it (model provenance)
    expected_info: str             # ≤1 line: what answer would distinguish hypotheses
    why: str                       # ≤1 line
    confident_enough: bool         # True ⇒ skip remaining probe rounds (D7 bound respected)
```

**Kernel validates:** command through sandbox allowlist/scoping; `policy-blocked` denials
route to allowlist requests, never counted as probe failures. Budget: ~150 tok.

## 15. `interpret_probe` — D4: shaped output → finding (carries the `lesson?` field)

```python
class InterpretProbe(Envelope):
    fact: str                      # ≤2 lines — what the probe showed
    implies: str                   # ≤2 lines — what it rules in/out
    lesson: Lesson | None          # §22 fill-in form; only when a real lesson emerged
```

**Kernel validates:** nothing semantic (evidence artifact is append-only). Budget: ~200 tok.

## 16. `debug_judge` — D5: blame, problem, ranked fixes (fresh context)

```python
class RankedFix(Base):
    rank: int                      # 1..5, unique — grammar-enforced
    approach: str                  # ≤1 line
    how: str                       # ≤3 lines

class DebugJudge(Envelope):
    blame: Literal["code","test","spec","both"]
    problem: str                   # ≤3 lines — what exactly is wrong (mechanism, not narrative)
    fixes: list[RankedFix]         # 1–5
```

**Kernel validates:** ranks unique/contiguous; problem non-empty (feeds fix attempts as
advice-not-orders — fixer is an agent, ENGINE_SCRIPT). Budget: ~350 tok.

## 17. `fix_attempt` — D8: one hypothesis, implemented, with discovered issues

Fixed shape from ENGINE_SCRIPT (`status`/`new_issues`/`comment`), plus the file changes the
harness will execute:

```python
class NewIssue(Base):
    keywords: str                  # 1–4 space-separated terms — ticket topic key, ^[a-z0-9_-]+( [a-z0-9_-]+){0,3}$
    description: str               # ≤2 lines
    blocked: bool                  # True ⇒ bubbled as ticket immediately; run continues otherwise

class FixAttempt(Envelope):
    status: Literal["fixed","failed","blocked"]
    blocked_kind: Literal["design-question","technical"] | None   # REQUIRED iff blocked
    blocked_reason: str | None     # REQUIRED iff blocked — content for D9 authoring
    tests_run: list[str]           # commands it ran — it confirms the fix itself before reporting
    new_issues: list[NewIssue]     # 0–4
```

Like `implement`, the fixer is a **tool-loop**: it receives the judge's problems + failing
test commands, edits via tools (check pipeline on every write), runs the tests, and reports
only when it believes it is fixed (or blocked). The gate re-verifies — the model's
"confirmed" is a claim, never a close.

**Kernel validates:** tool-round writes through check pipeline; work confined to boundary;
`blocked_kind`/`blocked_reason` presence iff blocked; `new_issues[].keywords` pattern.

**Attempt outcome enum (D8b — recorded by the harness from verify artifacts + this
envelope; the model never emits it):**

| condition (mechanical) | outcome |
| ------------------------------------------ | -------------------------- |
| status==fixed, verify green, no new_issues | `fixed` |
| status==fixed, verify green, open new_issues (blocked=false) | `fixed-with-concerns` |
| status==blocked, blocked_kind==design-question | `blocked-design-question` → D9 decision node, `needs-user` |
| status==failed AND a new bug was identified (new_issues or fresh identify_bugs) | `new-bug-found` → D9 subtree proposal |
| verify red / ladder or MAX_FIX_ATTEMPTS exhausted | `needs-user` (ladder visible) |

Budget: tiny (report only).

## 18. `judge_<aspect>` — F7 subjective-AC panel, aspect-parameterized

The shape is **one schema for all aspects**; `aspect` is an echo field instantiated as a
grammar enum over `run_config.judge_aspects` per run (e.g. `spec-match`,
`test-meaningfulness`, `no-corner-cutting`). The aspect only changes the injected question
(`ASPECT_PROMPTS[aspect]`), never the structure — one grammar, N cheap parallel calls.

```python
class JudgeAspect(Envelope):
    aspect: Literal[...]           # enum generated from run_config.judge_aspects at build time
    target_ac_id: str              # which AC this verdict covers — enum over the leaf's map
    verdict: Literal["pass","fail"]
    confidence: Literal["low","medium","high"]
    evidence: str                  # ≤3 lines — must cite the diff/artifact, not restate the AC
```

**Kernel validates (KERNEL_API.md: gate):** `target_ac_id` ∈ map; evidence non-empty on
fail; panel disagreement recorded + weighted; closure is procedural — the model flags, the
gate decides. Budget: ~200 tok each; panel runs in parallel.

## 19. `run_summary` — H6: closes the run

```python
class RunSummary(Envelope):
    outcome: Literal["complete","partial","parked-needs-user"]
    what_was_done: str             # ≤4 lines
    what_changed: str              # ≤4 lines — files/areas, from trajectory, not memory
    what_remains: str              # ≤4 lines — open tickets, parked nodes
```

**Kernel validates:** none beyond schema; rendered from trajectory summary so the model
summarizes ground truth. Budget: ~300 tok.

## 20. `gate_decide` — propose ≠ decide: validate the REASON, not the change

Decides three proposal classes with one schema: AC/test/tree-structure **changes** (DESIGN
§4.8), **initial AC maps** from `draft_acs` (§6 — authoring a gate is gate-defining), and
memory/lesson promotions where a reason must be validated.

```python
class GateDecide(Envelope):
    decision: Literal["accept","reject"]
    reason_is_real: bool           # evidence refs resolve (kernel hands over resolved evidence)
    weakens_gate: bool             # does it weaken/redefine/eliminate the AC/test?
    meaning_preserved: bool        # AC-weakening vs AC-clarification disambiguated by reason
    explanation: str               # ≤3 lines — REQUIRED on reject; proposer gets it back
```

**Kernel validates:** `decision==reject` ⇒ explanation non-empty; `weakens_gate==True` ⇒
decision must be `reject` (grammar pair — gate-easing proposals are structurally suspect,
DESIGN §4.8). Budget: ~250 tok.

## 21. `propose_growth` — D9: subtree proposal, gated by proposer≠decider

```python
class ProposedNode(Base):
    kind: Literal["ticket","decision"]         # decision ⇒ marked needs-user (D9 rule)
    what: str                      # ≤2 lines
    why: str                       # ≤1 line

class ProposeGrowth(Envelope):
    trigger: Literal["new-bug","design-question"]
    evidence_refs: list[str]       # 1–6 ledger/trajectory refs — DECISION: proof over opinion
    nodes: list[ProposedNode]      # 1–6
    reason: str                    # ≤4 lines — what the reviewer will validate
```

**Kernel validates (KERNEL_API.md: ledger):** every `evidence_refs` entry resolves in the
ledger; accepted proposals execute via the standard tree-edit cascade (done parent reopens,
AC map re-runs) — the harness authors nothing. Budget: ~400 tok.

## 22. `lesson` — I6: memory-store fill-in form (embedded via §15, or standalone step)

Topic key is 1–6 normalized AND-terms (deterministic matcher — exact term presence);
provenance is mandatory (governance pipeline, DESIGN §4.4).

```python
class Lesson(Base):
    line: str                      # ≤1 line — the lesson itself
    topic_key: list[str]           # 1–6 terms, pattern ^[a-z0-9_-]+$ each; grammar-enforced count
    provenance_task_id: str        # node/task the lesson came from
    provenance_ref: str            # ledger or evidence ref — must resolve
```

```text
lesson:
  line:       > list(iter(x)) consumes the iterator — wrap in list() first if reusing.
  topic_key:  python iterator gotcha list
  from task:  [T-42]   evidence: [ledger:fp-1187]
```

**Kernel validates:** 1–6 terms, term pattern, no stopwords (deterministic), evidence ref
resolves in ledger, overlap detection vs store (set algebra). Draft memories enter
governance as provisional. Budget: ~120 tok.

---

## 23. Token-budget summary (3k output ceiling)

| Tier | Schemas | Budget | Note |
| --- | --- | --- | --- |
| Tiny ≤400 tok | find_ambiguities, revise_task_card, split_review, spec_review, failure_judge, propose_probe, interpret_probe, debug_judge, judge_aspects, run_summary, gate_decide, propose_growth, lesson, implement, fix_attempt | — | reports only — work happens via tool rounds |
| Medium ≤800 tok | task_card, expand, draft_acs, test_plan, identify_bugs, write_spec | — | no risk |
| **Ceiling-risk** | write_test (~2.5k) | — | the only content-emitting schema left; one case per call; overflow → file split-window (never truncate) |

Every code-carrying schema declares its split path in advance (§4.2 bounded artifacts;
overflow triggers the path, never truncates).

## 24. Cross-cutting validation split (details in KERNEL_API.md)

- **Grammar-enforced at decode:** enums, patterns (ac_id/case_id/keywords/topic_key),
  list caps, conditional requirements (unable_reason, blocked_kind, ok⇒issues==[]).
- **Kernel post-hoc:** reference resolution (seam_id, ac_id, evidence_refs, location,
  files ⊆ declared boundary), DAG/AC-map rules, ledger provenance, check pipeline on
  writes, best-of-N resample on low-confidence judges.
- **Script-owned:** which envelope to request, retry/re-split routing, aspect config —
  scripts never author or alter schemas (§4.2: schemas are selected from this library).
