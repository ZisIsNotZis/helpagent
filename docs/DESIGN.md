# DESIGN — Small-Model Coding Harness

**Codename:** `helpagent`

**One-liner:** A workflow-compiler coding harness where the model is never a free-form engineer — every model invocation is a tiny, artifact-bounded question inside a harness-owned state machine, wrapped in maximum ground-truth injection and minimum error exposure.

**Target:** ≤4B local models (llama.cpp / OpenAI-compatible). Reference model: **XHToken/Spark-X2.5-4B-GGUF:Q4_K_M**. No escalation to bigger models. **Autonomy is a dial:** the run delegates to the human only when a script hits genuine requirement ambiguity (A4 cap) or an unresolvable design question (D9 decision node) — rare by design; every delegation and auto-answer is logged, and needs-user frequency is a tracked metric.

---

## 1. Goals and non-goals

### Goals

1. ≤4B models (reference: Spark-X2.5-4B Q4_K_M) complete real coding tasks (bugfix, small feature, port, scaffold) with professional-grade correctness.
2. Every error the model could make is either prevented (context), caught (checks), auto-fixed (harness), or erased (never shown to a later invocation).
3. Context length per invocation stays small (≤ ~8k tokens: ~5k prompt + ~3k output, envelope overhead counted); shared prefix maximizes KV cache reuse.
4. The harness itself is hardened: typed, tested, and every feature gated by benchmark evidence.
5. All model limitations discovered become data (fail patterns, rules, help gaps) — the system learns structurally, too-old features die by number, not opinion.
6. **The cost is a number too:** every run reports model calls, tokens, and wall time (model + tool/infra separately). Quality-per-cost is the metric features are judged on, not quality alone.

### Non-goals

- Free-form agentic chat; open-ended research; large multi-module design by the model.
- Serving remote API models (design assumes local GPU economics: cheap retries, slow prefill).
- Supporting existing agent harnesses as a base — the conversation store is owned here.
- **v1 out of scope (authoritative — the taxonomy's coverage check cites this line):** deployment ops, CI authoring, team process, production incidents/hotfixes, data migrations involving live stateful verification.

---

## 2. Design principles

1. **The harness is the product.** The model is a natural-language / code / multimodal **adaptor** — its irreplaceable skill is mapping between structured harness state and legible language. Everything semantic (deciding, checking, remembering) is harness; if a shell command, parser, template, or lookup can do it, the model must not.
2. **Model = function.** Canonical invocation contract: `f(input, requirement, AC, output format, help & hint) -> (output, comment)`. Within a step's boundary the model calls a **small per-step-type tool set**: `llm(step_type, artifacts, question, tools=[...])` — one-shot proposal → sandboxed execution → shaped result. Harness-known commands (build/lint/test) are **canonical**: the model's job is to make the canonical command succeed, not invent it; model-proposed ad-hoc commands (probes, greps) are fine — the harness doesn't need to know them. Between steps the model never acts, only answers; the retry-with-missing-info mechanism replaces the free tool loop. **Info-miss retries are a first-class stats counter** — high rate = composer bug, not model bug. Every envelope carries a grammar-enforced `unable: reason` alternative so a needed decision is never inexpressible. Precedents: DSPy, SWE-agent ACI findings, AlphaGo-shaped propose/execute split.

    **Step separation rule (boundary theorem, tightening):** every step must have cleanly isolated inputs/outputs — no step may depend on context detail that is important yet hard to summarize or pass on (the test: could a fresh session with only the artifacts act correctly?). Each envelope's output provides **all information possibly useful** to other stages, debugging, trajectory, and inspection — when trivial/convenient, include it. Where different consumers need different kinds of information, use **specific JSON fields per kind**, so fields can be routed separately; but fields are maximized: if two fields are always routed together, they are related and belong together. Field names: clean, specific, actionable. Concretely: the debug probe's interpretation artifact carries separate routed fields for `implication_for_hypothesis`, `new_evidence`, and `summary_for_trajectory` — the hypothesis step gets the first, the evidence artifact the second, the trajectory the third.

    **Guided decomposition of thought (idea under the adaptor principle):** a "brainstorm/think-about-everything" request is exactly where a small model slacks — it names three things and stops. The fix is structural, not motivational: the *harness* decomposes the thinking task (enumerate dimensions first — enum output; then one incremental call per dimension; then a reduce/merge), same as any other task. This is just proposal→map→reduce, the existing pattern applied to cognition, and it composes with best-of-N. **BUT** it violates nothing only when used sparingly: it multiplies calls (cost rule §6 applies — it must beat single-shot on the corpus to stay), and only for step types where coverage is the failure mode (edge-case enumeration, dimension brainstorming, review-aspect generation). Default is still one-shot; guided thinking is a per-step-type option, not a philosophy. **Containment:** it never changes a step's schema or boundary — it is a within-round strategy (`TASK_TAXONOMY` §J), so the step still has exactly one handover. **Build order:** the cheaper already-specified mechanism goes first — best-of-N with a deterministic union/dedup of samples is poor-man's dimension coverage at zero new machinery; dimension fan-out is built only if that measurably loses. First candidate step types: `draft_acs`, `test_plan` (§9.12 keeps the kill-switch).
3. **Ground truth beats memory.** Never trust what the model "remembers" about an API, symbol, or convention — inject the real signature/doc/example. Model-curated memory exists (Memory Store, 4.4) but is governed: provisional, statistics-promoted, contradicted memories deleted.
4. **Errors are unlearnable, not correctable — refined (owner challenge 2026-09-18; T-01 repeated-mistake observation, not proof of cause).** Three memory layers, three different rules: (a) WITHIN a strategy, attempts ITERATE on the work tree — the current draft is injected from disk each round, so the model's file-view matches the staged work tree; an unchanged one-line retry summary alone may leave attempts indistinguishable. The composer does not inject prior failed text as a separate narrative: feedback is a failure summary + test output, while the draft itself is the current file state; (b) failed attempts live append-only in the ledger/trajectory (never deleted — stats and evidence, for the harness, never injected); (c) AT A STRATEGY BOUNDARY (gear escalation / budget exhaustion) the whole draft is erased (work tree restored to baseline) — the next strategy starts clean and never inherits the previous strategy's failed code. The model's file-view never diverges from disk.
5. **Everything is an artifact.** Files, check results, decisions, learnings — typed, bounded, on disk, resumable. Artifact content passes a **secret filter at the store boundary** (diffs, transcripts, and tool output can contain secrets; the review-phase scan is not the gate).
6. **No feature without a number.** Every autonomous-path subsystem must move the benchmark score by a minimum delta with confidence interval (from N repeated runs — run-to-run sampling noise from best-of-N is real) or be deleted. Piloting UX (B4/B6) is user-judged, exempt from this rule.
7. **Reliability gates cost (owner decision, 2026-09-17):** correctness is the precondition of every comparison — cost metrics only count after correctness holds. A cheaper-but-wrong variant never wins; a feature that breaks correctness is dead regardless of what it saves.
7. **Prefix stability.** Byte-stable prefix = scaffold + **static standing knowledge only** (project conventions, canonical commands, prompt files). All dynamic knowledge — rule-library hits, memory matches, gotchas, help answers — is **suffix injection**. No promotion/demotion of memories ever mutates the prefix.

---

## 3. System architecture

```text
                    ┌─────────────────────────────────────────────┐
                    │              WORKFLOW ENGINE                │
                    │   step graph · session runner · retries     │
                    └──────┬───────────────────────┬──────────────┘
                           │ compose               │ dispatch
              ┌────────────▼────────┐   ┌──────────▼──────────────┐
              │   CONTEXT COMPOSER  │   │      MODEL RUNNER       │
              │ scaffold + suffix   │   │ llama.cpp / grammar-    │
              │ (injections here)   │   │ constrained, JSON out   │
              └────────────┬────────┘   └──────────┬──────────────┘
                           │                       │ structured output
        ┌──────────────────▼───────────────────────▼───────────────┐
        │                      ARTIFACT STORE                      │
        │ typed artifacts · rendered forms · bounds · ledger │
        └──────────────────┬───────────────────────────────────────┘
                           │ touched files / commands
        ┌──────────────────▼──────────────┐   ┌─────────────────────┐
        │        CHECK PIPELINE           │   │  TOOL WRAPPER +     │
        │ format→lint→type→parse→test     │   │  SANDBOXED EXEC     │
        │ auto-fix → escalate → rollback  │   │  shaped outputs     │
        └─────────────────────────────────┘   └─────────────────────┘
        ┌──────────────────────────────────────────────────────────┐
        │              KNOWLEDGE SERVICE (one module)              │
        │  symbol DB · rule library · help dispatcher · gotchas    │
        │  · memory store (governed)                               │
        └──────────────────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────────────┐
        │   TASK TREE (plan/tickets/progress — one artifact,      │
        │   views only) · USER PILOTING (typed message routing)   │
        └──────────────────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────────────┐
        │        BENCHMARK LOOP: corpus → run → fail-patterns      │
        └──────────────────────────────────────────────────────────┘
```

Subsystems 2/4/5/8 from the original brainstorm collapse into: Workflow Engine, Context Composer, Knowledge Service, Check Pipeline, Tool Wrapper + Exec, Artifact Store, Task Tree + piloting, plus the Benchmark Loop that drives all of them.

---

## 4. Subsystems

### 4.1 Workflow Engine

The harness is a **runtime kernel executing a versioned script**. The script — a plain Python package with an entrypoint, containing functions, loops, and branches — describes the entire software-engineering methodology: when to invoke the model and with what question, what to inject, when to run peers/judges (one-shot `llm()` calls, possibly parallel), how to split, retry, compose, verify, and diagnose. The kernel never interprets or understands the script; it executes it and owns the invariants.

- **Kernel/script split (load-bearing, and actually enforced):**
  - **Kernel owns (non-negotiable):** model runner + grammar envelopes, artifact schema validation, check pipeline on every write, erasure semantics (§2.4), stats/ledger recording, memory governance pipeline, model-implication sandbox, **global run budget**.
  - **Script owns (strategy, freely revisable):** flow topology, model-invocation points and questions, injection decisions, peer/judge spawning, split/retry/park logic, per-step budgets within the global cap.
  - **Enforcement mechanism:** the script *is* the strategy, so "bypass" is meaningless for it — the kernel/script split's enforcement value is **A/B comparability** (same kernel ⇒ strategy is the only variable). For test scripts (true/false producers), a dedicated **audit agent** verifies correctness, and all their stdio lands in the trajectory for post-hoc audit.
- **Kernel API (the real design artifact) — six async primitives:**
  - `llm(step_type, artifacts, question, tools=[...]) -> structured-output` — grammar-constrained envelopes with a **per-step-type tool set**; within a step's boundary the model proposes tool calls (one-shot → sandboxed exec → shaped result). Peers/judges are ordinary parallel calls.
  - `exec(spec, provenance) -> shaped-result` — sandboxed command execution (probes, tests, builds) via the wrapper registry; carries model-output provenance so the sandbox applies automatically to anything a model implied. A denial is a first-class shaped result (`policy-blocked`), routed to an allowlist request (user/config), never into the diagnose pipeline.
  - `inject(...)` — budgeted context injection (per-category sub-budgets, §4.3).
  - `check/write(...)` — check pipeline with auto-fix/rollback; sandbox baked in.
  - `memory.write(...)` — governed memory store.
  - `user("...") -> answer-artifact` — pauses the calling subtree, lands the answer as an artifact, unblocks. Piloting surface for clarification (A4), decision bubbling (D9), mid-run steering.
  If the API is stable, script revisions are diffable strategies.
- **Global run budget (kernel-enforced):** per task class — max leaves, max model calls, max wall time. Expansion appetite is bounded per-parent (§4.8) but nothing else stops 3,000-leaf trees; budget overflow → `needs-user` status, like the probe cap but at tree level.
- **Script revision = versioned bundle:** code + colocated prompts + artifact schemas, compared as one unit. Benchmark runs pin `(script revision, corpus task)`; stats artifacts and FAIL_PATTERNS entries cite the revision. This upgrades the loop from "tune the harness" to "evolve competing SE methodologies against the same corpus."
- **Prompts as colocated markdown:** each model-invoking function pairs with a prompt file (`prompts/<step>.md`) loaded verbatim into the stable prefix (byte-stability applies). They travel with the revision bundle.
- **Language (v1): Python — ecosystem-decided, revisable at the API boundary.** Deciding criteria: (a) LSP client libraries — Python's `multilspy` is purpose-built for agents consuming LSP → Python wins where it matters most (symbol DB); (b) async fleet — Node's fanout advantage doesn't bind (fleet is GPU-bounded, a few in-flight generations); (c) tree-sitter — wash; (d) check tools and llama.cpp are CLI/HTTP — agnostic; (e) benchmark/stats analysis leans Python. The kernel API is the portability contract: a future rewrite ports scripts against the same primitives at known cost.
- **Trust boundary: scripts are trusted, models are not.** Scripts are author code — full privileges, no sandbox; sandboxing them would sandbox the author. The sandbox wraps **model-implication execution only** — every command reaching `exec()` with model provenance passes through filesystem scoping, allowlist (per-script config, kernel-enforced), container, network policy. Kernel-owned, script-invisible.
- **No orchestrator model.** Control flow stays deterministic — an LLM in the engine's control path would break the kernel/script/model separation, be the least reliable component (4B) in the most sensitive spot, and destroy run-to-run A/B determinism. **The user is the orchestrator; the harness is the switchboard.** Piloting = user selects a node (interrupt cascades to children) + typed message: **patch** (→ subtree rewrite + cascade; **user patches bypass gate review — the user is the final authority**), **hint** (instruction artifact injected into the node's composed context; node continues under identical schema constraints), **answer** (→ `user()` semantics). Interrupts land at step boundaries only; in-flight rounds complete first. Zero new model components.
- **Step granularity:** each model invocation is one tiny job — fits one sentence; inputs fit a few bounded artifacts. Hard per-step tool-round budget = **leaf estimate × 1.5 headroom** (the estimate itself feeds re-split signals; budget = estimate guarantees churn on estimation error); exhaustion is an automatic split signal feeding re-planning.
- **Fresh session per invocation** with the shared byte-stable prefix + step suffix. KV-cache reuse across sequential invocations is a **property of the llama.cpp server, measured not assumed** — benchmark tracks cache-hit rate; parallel peers/judges thrash the slot cache and are scheduled accordingly (serialize cache-heavy, parallelize judge calls only when latency demands).
- **Failure handling per step type** — a state-machine branch, never a hope: `retry (with failure summary + missing info injected) → re-split into smaller steps → escape to extended probe loop (tighter checking)`.
- **Idempotent + resumable:** every step reads and writes artifacts only; node→produced-artifact linkage is a schema field; a crashed run resumes at the last completed step.
- **Golden flow example (bugfix):** understand → locate → hypothesize (narrowed question) → edit step(s) → verify → summarize (run-summary artifact, mapped to H4/H6 in taxonomy), with check-pipeline hooks around every edit step.

### 4.2 Artifact Store

Artifacts replace shared memory. The real engineering is here.

- **Typed schemas** (pydantic). Invalid artifact = unrepresentable. **Envelope schemas come from a per-leaf-type library — selected, never authored by the model** (a small model writing pydantic is a non-starter).
- **Rendered forms for model-authored artifacts:** never "produce JSON matching schema X" — always a pre-labeled fill-in form with examples (the `<freshest>.json` lesson).
- **Bounded:** hard size caps. **Code output overflow never truncates** — it triggers the pre-declared split-window path.
- **Mandatory self-summary field:** every model-authored artifact carries 2 lines restating its conclusion — contract position from principle 2, gives judges/checkers an intent handle.
- **Secret filter at the store boundary** — every artifact, diff, transcript, and raw tool output passes it before persistence.
- **Ledger:** append-only compressed learnings (from erased failures, help gaps, rule hits). Feeds FAIL_PATTERNS and the Knowledge Service. Never injected wholesale into model context. **Append-only is absolute — erasure never deletes ledger entries (§2.4).**
- **Stats:** every ledger entry carries structured counters — feature fired, check caught, rule hit, retry depth, tokens, **model wall time AND tool/infra wall time** (indexing, checking, git snapshot, sandbox spin-up are not free; F2), info-miss retries, needs-user frequency, policy-blocked denials, memory-reviewer disagreement, cache-hit rate. Per-run aggregation produces a stats artifact; keep/kill decisions query these counters.
- **File-splitting for large files:** whole-file rewrite has a size ceiling at 4B. Standard split step — model rewrites only a bounded line/region window, harness stitches and re-validates the composed file.

### 4.3 Context Composer

Builds every invocation: `byte-stable prefix + step-specific suffix`. With no tool loops, composition quality is the system's center of gravity — the composer must predict what each decision needs.

- **Scaffold (stable prefix):** role, output format, artifact conventions, project conventions, canonical build/test commands, prompt files. **Static standing knowledge only** (§2.7) — nothing context-conditional enters the prefix.
- **Repo index (precomputed, incrementally refreshed):** symbol table, module map, test map, convention file. Per-step injection is lookup + ranking, not a fresh scan. Refresh = invalidate + rescan exactly the paths in the step's trajectory change record.
- **Suffix injection at composition time** (no mid-stream interception — incompatible with a stream): conventions, related code excerpts, covering tests, AC, negative guidance ("don't reimplement X, it lives at Y"), files-not-to-touch, rule-library hits, memory matches, gotchas, help answers.
- **Injection budget: per-call, adaptive — no universal cap.** Each `llm()` call's context is composed to be lean and *sufficient for that call*: requirements, AC, spec, ground truth, the code within the task's declared file boundary, memory matches, gotchas — as much detail as the call needs (a detailed instruction + AC call legitimately carries more). No generic docs are ever injected (knowledge = memory store + auto-injected info + call-necessary info). The measured failure is an **info-miss** (call failed for lack of something it needed) — that counter, not a token cap, is the discipline.
- **File tracking & trajectory (harness-owned git):** the model never calls git. After every action whose execution mutated the work tree (edits — and probe commands too, e.g. builds create files), the harness snapshots status+diff and records `{step_id, node_id, files_changed, diff, commands_run, round transcripts, check results, outcome}`. First-class for post-analysis and drives incremental index refresh.
- **Append-only suffix; never mutate mid-invocation.**

### 4.4 Knowledge Service

<!-- OWNER DECISION 2026-09-17: injection-first, demote the help dispatcher. A small model
cannot be relied on to self-initiate lookups (it forgets the channel exists), and free-form
reading pollutes the composed context. The service's primary surface is therefore the
COMPOSER: ground truth (signatures, examples, gotchas, rule hits) is injected into the step
input automatically, before the model ever speaks. The help dispatcher survives only as a
measured fallback behind the §9.3 escape-hatch counters — never a pillar. Every injection
fix to date (FP-4 diagnosis, FP-7 constants, FP-10 request tokens) already worked this way. -->

### 4.4 Knowledge Service

One module, one storage format; five query surfaces:

- **Symbol DB:** signatures, docstrings, usage examples — from LSP (multilspy)/pydoc/tldr/man + repo index. Query keys: symbol mention, about-to-call, free-form help.
- **Rule library ("legal but usually wrong"):** trajectory-grown deterministic rules (e.g. `list(iter)` intent-mismatch class). Applied by Check Pipeline post-write; each rule carries the corrected idiom to inject. **Knowledge-asset portability is decided explicitly (§6):** which of rules/gotchas/memories are global vs per-repo — a fresh repo otherwise starts from zero.
- **Help dispatcher (`help(anything)`):** free-form → symbol DB → knowledge base → web search fallback (explicit network-policy exception in the sandbox config). Answers are tiny and example-led (signature + 3-line example + one gotcha), never raw man pages. Unanswerable queries are logged as knowledge gaps — the roadmap generator and model feedback channel.
- **Gotchas:** per-library/domain one-liners surfaced at composition time when relevant imports/symbols appear in scope. Suffix injections, never prefix.
- **Memory Store (topic-keyed external memory, model-curated):** during debug/verify steps, the artifact's fill-in form carries a `lesson?` field — one line + a **topic key of 1–6 normalized space-separated terms** (AND-match; **deterministic matcher defined at implementation: exact normalized-term presence, no edit distance until measured** — governance thresholds are arithmetic over defined inputs) + mandatory provenance (task, erased-failure ref, timestamp). The Composer matches each new invocation's context against stored topics and injects matches. **Overlap checking is deterministic set algebra:** full overlap = term-set superset, partial = non-empty intersection (Jaccard/containment). **Governance pipeline (async, never blocks the workflow):** draft → deterministic checks (term sanity: 1–6 normalized terms, no stopwords; evidence ref resolves in ledger; overlap detection) → independent fresh-context reviewer (gets lesson + evidence + ground truth; returns approve/reject/uncertain) → bounded debate (uncertainty branch only, ≤2 exchanges, fork-of-author vs independent judge; unresolved → parked in visible queue) → provisional (low injection priority) → stats-driven promotion (≥N matching successful sessions promote; contradiction demotes; contradicted twice deletes). SSOT conflicts are asymmetric: a promoted incumbent holds its stats as evidence; challenger must win. Deleting a promoted memory requires lifecycle contradiction evidence, not opinion. **Known residual risk, accepted deliberately:** under the no-bigger-model constraint, reviewers share the author's weights — the structural mitigations (fresh context, evidence refs, ground-truth injection, provisional-before-promotion, visible parked queue) are the defense, and reviewer-disagreement is a tracked counter. Governance gets a **synthetic mini-corpus** for testing (30–50 coding tasks will not exercise it).

### 4.5 Check Pipeline

Hooks around every model-implication execution, scoped as follows.

- **Ladder (cheapest first):** formatter → autofixer (ruff/autoflake/prettier, **max 2 auto-fix passes** — a finding that re-appears after a pass is a survivor, not a new bug; tool-fight oscillation is a FAIL_PATTERN) → tree-sitter parse (locate exact broken region) → **project-wide type check with error filtering to touched files** (touched-files-only scoping is unsound — whole-file rewrites break callers in untouched files; the filter is at finding level, not invocation level) → scoped tests → rule library → intent check.
- **Auto-fix everything trivial; re-check; escalate to model only survivors** (bounded excerpt + one-line diagnosis + the fix contract).
- **Erasure semantics = §2.4** (composer-level, ledger-append-only, work-tree rollback via harness git). No conversation-erasure mechanism exists — fresh sessions dissolved it.
- **Intent check (tiered):** Tier 1 deterministic rules → Tier 2 self-check (same model, narrow diff-vs-stated-intent question, gated on the artifact's self-summary) → Tier 2 disagreement triggers retry-with-ground-truth.

### 4.6 Tool Wrapper + Exec

- Registry mapping command → output shaper. Common tools (git, pytest, ruff, npm, cargo) get hand-written structured summaries: `{exit, verdict, n_failures, first 3 excerpts, suggested next action}`.
- Rare tools: generic fallback shaper (nonzero exit → stderr tail + first error-pattern match; zero exit → head 20 lines or diff summary; always ANSI-stripped, byte-capped, deduped).
- Raw output always archived to an artifact (through the secret filter); "show more" is a help query, not a rerun.
- `policy-blocked` denials (allowlist, network, filesystem scope) are distinct shaped results routed to an allowlist request — never burned as diagnose-pipeline probe failures.
- **No free-form read tool.** The model never reads the filesystem directly: file content enters as composer-injected artifacts (§4.3), and everything else is a structured probe through `exec()` — sandboxed, shaped, archived. Reasons, in priority order (2026-09-17 alignment): (1) context-budget discipline — a read result is uncontrolled context injection into the ≤8k window; (2) A/B comparability — uncontrolled reads destroy run-to-run cost/quality accounting; (3) anti-cheat, which is owned structurally by role seams and withholding (§4.8), not by the sandbox alone. A genuine out-of-scope need routes to the allowlist request (config line, logged); recurring friction is the info-miss counter telling the composer to inject — never sandbox widening by default.

### 4.7 Model Interface

- **No tool-calling protocol.** The model returns grammar-constrained structured output only (llama.cpp grammar / json_schema for envelopes — decisions, artifact forms; code bodies ride in string fields). Every envelope schema includes a grammar-enforced `unable: reason` alternative. The harness executes what the output implies, through the sandbox. Works with any OpenAI-compatible endpoint or raw grammars — including base models.
- **Whole-file edits, never diffs** (aider finding): give current file(s within the task's declared boundary) + change description, get complete new file(s); harness computes the diff. **Prompt/output split ~5k/3k within the 8k window** (llama.cpp shares one n_ctx); file-size threshold below which whole-file edit is forbidden, derived from the 3k output ceiling — measured precisely in benchmark (§9).
- Post-generation parse with tree-sitter immediately; trivial syntax errors auto-repaired, otherwise step respawned with only the broken excerpt.
- **Best-of-N at decision points:** sample 3–5, deterministic checker selects. Retries with more ground-truth injection are the escalation path (no bigger model).
- **Tolerant at the parameter layer, strict at the logic layer (owner policy, 2026-09-17):** intent-legible small errors — wrong argument names, enum near-misses, arity-within-reason — are normalized deterministically by the kernel before validation (a small evidence-gated alias registry; every normalization fires a `tolerance_fired` ledger counter — frequent fire on one field is a composer-bug signal, same reading as info-miss). Semantic/logic errors are NOT correctable: the kernel never guesses intent past the parameter layer — erasure + retry governs (§2.4).

### 4.8 Task Tree & User Piloting

One plan artifact — **the task tree** — absorbs planning, tickets, and progress (full taxonomy and rules in `docs/TASK_TAXONOMY.md`).

- **Universal node schema:** `{id, what, why, input, output, ac_test_map, risk, produced_artifact_id, status, children}`. Leaves are minimal tasks; status ∈ `{pending, in-progress, done, blocked, stale, needs-user}`. `input`/`output` are **typed artifact references with explicit producer ids** — validation failure (orphan input, duplicate producer, cycle) → automatic re-expansion request, not silent stall.
- **Expansion (planning operation):** **harness proposes candidate cuts; model annotates/fills — propose-validate, not free decomposition** (multi-module design by the model is a non-goal). Cuts come in two modes, selected by what is known: **structural** (module-map seams) when the task's location is known or irrelevant — feature, port, scaffold, refactor; **evidence-seeded** (failing symbol, stack frames, covering tests) when the location *is* the unknown — bugfix, perf, crash. **A plan authored from filenames alone is a non-goal**: for a diagnostic task `expand` runs after locate and is seeded with the evidence, so the plan names a real symbol instead of a plausible-sounding file. Uniform-layer; leaf criterion = ≤10 tool-rounds estimated, one output artifact, one subsystem area — **applied per side, with the sides splitting independently** (owner decision): a trivial-work/heavy-test node becomes one small work leaf plus test leaves that each own their checks, referenced by the parent's integration map; heavy-work/light-test splits the work side only. E2E ACs stay local and fixture-scoped, never live-stateful. Depth cap 3–4, 5–15 leaves per parent (a default, not a bound), **plus a kernel-enforced global node budget per task class** (§4.1) — per-parent bounds alone permit thousands of leaves.
- **AC test map:** `{ac_id → [check_id, command | subjective]}` — **mandatory for every leaf, optional for an internal node**, where it is an *integration view*: only checks that span its children, each resolving to a check a descendant already owns. References, never copies — so ACs do not repeat upward. Authored by `draft_acs` as a gate definition and **decided by a fresh-context `gate_decide`** (proposer≠decider covers *authoring* of a gate, not just changes to one): a leaf's map after its spec is reviewed, an internal node's after its children are placed. Kernel-validated, held in the node schema — the gate's input exists before any work starts.
- **AC rule & closure gate (kernel-enforced over deterministic checks):** every AC resolves to ≥1 executable check. Spec/interface first; code and tests written **in parallel**, both targeting the map. **Firewall = withhold solutions, share requirements:** both sides receive the contract (`interfaces` + `behavior`); only the implementation artifact is withheld from the test writer, and solver guidance lives in `implementation_notes` (implementer-only) — an unfounded test is as bad as a cheating one. The test writer cannot see code; the implementer *does* see tests (it must run them) but cannot edit them: writes are boundary-scoped, so the test file is outside its seam. A node closes only when: (a) every AC **in its map** has ≥1 test, (b) those tests pass unconditionally, (c) all child nodes closed first. **Subjective ACs close via a multi-aspect LLM judge panel** (configurable aspects — spec-match, test meaningfulness, no corner-cutting; configurable fleet size), **not** routine human confirmation — human delegation is reserved for genuinely ambiguous requirements and unresolvable design questions. **A flaky test is a bug in the test — fix it via the normal pipeline;** if the flake is pre-existing and unrelated, the script decides: fix it (small) or raise a separate ticket (real work). No waiver class.
- **Work-tree exclusivity:** work-tree-mutating leaves execute serialized (v1 — one writer). The user never edits ticket/plan files manually — all steering goes through the message box (B6), so no user-vs-harness file conflict exists.
- **Proposer never decides (gate review):** AC/test/tree-structure changes are proposed with a written reason and decided by an independent fresh-context reviewer. The decider validates the **reason**, not the change: (a) reason describes reality — evidence refs resolve; (b) the change does not weaken, redefine, or eliminate the AC/test it operates on — gate-easing proposals are structurally suspect; (c) the change preserves the gate's meaning (AC-weakening and AC-clarification can look identical in a diff — the reason is what distinguishes them). **User patches bypass this review** — the user is the final authority.
- **Tree-edit cascade (used by B4 patches and D9 growth):** inserting or modifying a node under a `done` parent **reopens the parent** (status → in-progress) and re-runs its AC map; touched leaf → parents re-validate upward; touched branch → children marked `stale` (must re-verify). D9 growth is a `llm()`-authored subtree proposal gated by proposer≠decider review — the harness executes accepted edits, it does not author nodes.
- **Bounded-attempt rule:** an attempt node spans sub-steps (attempt → verify → outcome); outcome `{fixed, fixed-with-concerns, blocked-design-question, new-bug-found, needs-user}`; next hypothesis = new sibling; design questions → decision nodes marked `needs-user`.
- **Autonomy dial (per run):** `needs-user` nodes either park (run pauses, resumes on answer) or auto-answer by configured conservative default (logged, counted into the needs-user metric). The dial is how "human-supervised" and "unattended stretch" coexist honestly.
- **User piloting (no orchestrator model):** user selects a node (interrupt cascades to children), typed message: patch / hint / answer. Interrupts at step boundaries only. Tree rendering is harness work — zero LLM.
- **The same tree-edit operation serves both** user patches (B4) and dynamic growth (D9) — built once, used twice.
- **Work-tree exclusivity:** work-tree-mutating leaves execute serialized (v1 — one writer; parallelism is for read-only judges/peers). The user's own edits to a running work tree are detected via the per-step git snapshot → conflict → pause + `needs-user`, never silent overwrite.

---

## 5. Data flow — one edit step, end to end

1. Script takes next leaf from the task tree (execution DAG validated); knows its type and artifact deps.
2. Composer queries Knowledge Service (symbols in scope, rules, gotchas, memory matches) + Repo Index (related code, covering tests) → builds suffix under per-category budgets.
3. Runner invokes model: prefix + suffix. Model returns structured envelope; the harness executes what it implies (commands via `exec()`, sandboxed; file writes trigger Check Pipeline).
4. Trivial issues auto-fixed (≤2 passes) and rolled back if unfixable; survivors escalated once; persistent failure → retry/re-split branch; failed attempts → ledger + work-tree rollback.
5. Step writes its artifact (with self-summary); kernel validates schema; tree node updates status.
6. Ledger records: rule hits, help queries, failures, latency, token counts, tool wall time, omissions, denials.

---

## 6. Benchmark loop (drives everything)

**Blind gate (owner direction 2026-09-29 — methodology correction).** The corpus tests are the GRADER: per-task `checks.py` (pytest + untouched-files byte identity) is scoring machinery and must never enter a run's view. A run's own verification is what it writes itself; `harness/staging.py` projects the task files to a source-only view for the harness and `bench/external_score.py` applies the run's produced files onto a pristine copy and runs the grader there, after the run. Every run therefore reports two facts: what it CLAIMED and what the grader found. `bench/runs/**` produced before this correction, and every conclusion derived from them, are **contaminated and not citable**; the list of retracted claims is in `.scratch/16-v2-skeleton/issues/16-v2-skeleton.md`. Two mechanics below make "no false success" enforceable rather than aspirational: the grader scores a PRISTINE copy of the task repo, restores every grader-owned path (test paths, test infrastructure, and the corpus task's own `UNTOUCHED` list) before running, and requires its own machine-readable pytest report — the process exit status is forgeable by the run's own code (DESIGN §10.3, round-6 findings F1/F2).

- **Own corpus (primary, daily):** 30–50 tasks across flow topologies — bugfix, add-feature, port, new-repo — each with deterministic checks (tests pass, types clean, behavior assertions, untouched-files contract). **Cost metrics are rubric components, not footnotes:** model calls, tokens, wall time (model + tool separately) reported per task; quality-per-cost is the comparison axis.
- **Score rubric:** fix quality / verification behavior / safety (no unrelated changes) / stopping behavior / cost. No LLM-as-judge.
- **Minimum effect size:** a feature's keep/kill needs a score delta exceeding the confidence interval from N repeated runs (best-of-N sampling noise is real) — otherwise it's vibes, which principle 6 forbids.
- **Cold-start honesty (flywheel payback):** the rule library, memory store, and FAIL_PATTERNS all start empty — the first N tasks run *slower and costlier* than the M0 baseline until knowledge accumulates. Benchmark plots score-per-cost vs task index; **knowledge-asset portability (rules/gotchas/memories: global vs per-repo) is decided upfront** — it determines whether a fresh repo starts from zero.
- **Cold-cache scenario:** at least one benchmark run with cold index + cold KV cache — cache-miss prefill is the dominant hidden cost on slow-prefill hardware, and cache-hit rate is a measured dimension, not an assumption.
- **Public anchor (rare):** small slices of Terminal-Bench (genre match), aider polyglot (edit-format capability), SWE-bench Lite (ceiling probe). Verify feasibility before committing.
- **Process:** every run → FAIL_PATTERNS.md entry → harness fix → re-run → score must move (by the effect-size rule) or feature is deleted. Runs pin `(script revision, corpus task)`. This loop is the project's core method, inherited from auto_maintain_bench.

---

## 7. Repository layout (proposed)

```text
harness/
  kernel/        # six primitives, sandbox, erasure semantics, budget, scheduler
  artifacts/     # schemas, store, secret filter, rendered forms, task tree
  compose/       # context composer, sub-budgets, repo indexer
  knowledge/     # symbol db, rule library, help dispatcher, memory store
  checks/        # check pipeline, auto-fixers, rollback
  tools/         # wrapper registry, shapers
  model/         # runner, grammar envelopes, best-of-N
scripts/         # versioned SE methodology scripts (code + prompts + schemas)
bench/           # corpus, runner, scoring, fail patterns, cost metrics
docs/            # design, taxonomy, ADRs, fail patterns
```

---

## 8. Build order

| # | Milestone | Proves |
| --- | --- | --- |
| 0 | Corpus skeleton + bare `llm()` whole-file-edit baseline | The number everything must beat |
| 1 | Model runner + envelope grammars (incl. `unable` alternative) + whole-file edit + tree-sitter auto-repair | Model can emit valid code reliably |
| 2 | Kernel primitives + artifact store + golden bugfix script + session runner | End-to-end one task class |
| 3 | Check pipeline (format/lint/type/parse, auto-fix ≤2 passes, rollback) | Error classes die |
| 4 | Tool wrapper + sandboxed exec + output shaping | Context stays small; policy-blocked is legible |
| 5 | Corpus (30 tasks) + scoring + cost metrics + FAIL_PATTERNS loop | Feature gating possible, honestly priced |
| 6 | Knowledge service (symbol DB → help dispatcher → rule library) | Ground truth beats memory |
| 7 | Context composer full version (sub-budgets, repo index, incremental refresh) | Per-step context optimal |
| 8 | Task tree + expansion + AC test map + closure gate + user piloting | One artifact runs everything |
| 9 | Memory store lifecycle, best-of-N, intent check tier 2, flow re-split, file-splitting | System learns from failures |

---

## 8.1 Flow tiering (owner decision 2026-09-18 — the §9.10 verdict executed)

The M5 verdict (77/90 bare vs 66/90 pipeline at 1.4 vs 8-10 calls/task) triggered
§9.10's clause: overhead was the suspect and it is guilty on small tasks. The
response is FLOW TIERING, not deletion:

- **Difficulty is discovered, not predicted.** No 4B difficulty self-assessment
  (FP-5 shows the model cannot even classify task class stably) and no mandatory
  human pre-labeling (does not scale to real requests). The ladder starts at the
  cheapest gear and escalates on failure — a task that the cheap gear solves WAS
  easy; one that burns the ladder was hard. Manual gear override stays available
  as the autonomy dial (§4.8).
- **Gears (engine scripts, one kernel, shared safety nets):**
  - **Gear 0 — direct**: 1 whole-file-edit attempt set (≤3) + kernel protections
    (check_write ladder, sandbox, untouched contract — all deterministic, no model
    calls, effectively free).
  - **Gear 1 — guided**: Gear 0 + fix_plan enumeration before each emit (§2.2;
    earned +29pp on the failure family at +1 call/attempt).
  - **Gear 2 — full**: the golden flow (spec → AC map → implement loop). Reserved
    for tasks the cheap gears cannot close; its machinery must pay for itself per
    task class from here on.
- **Benchmark floor calibration:** the 30-task corpus is largely single-file and
  pipeline-adjacent — it measures the working band, not the floor. A harder tier
  (multi-file, control-flow-restructuring, cross-module contracts) and, where the
  network permits, a small public anchor slice (§6) probe the actual limit.

## 9. Open questions

1. **Step size calibration:** what artifact-token size maximizes 4B success per invocation? Tune against corpus.
2. **Self-check value (Tier 2 intent):** does same-model diff-vs-intent checking beat pure rule growth? Measure before keeping.
3. **Escape hatch scope:** how much does the extended probe loop get used; does its failure data force more flow topologies?
4. **Memory store hygiene:** promotion threshold (N), injection priority for provisional memories, topic-term clustering vs sprawl.
5. **Whole-file ceiling:** at what file size does 4B whole-file rewrite break down vs split-window? (Bounded above by the 3k output ceiling — find the real number.)
6. **Expansion constants:** depth cap, leaves-per-parent, the ≤10-round leaf criterion, global node budgets per task class — tune against corpus; watch for over-deep trees and over-splitting.
7. **llm-judge AC reliability:** how much can subjective ACs trust a 4B judge? Track judge-vs-evidence disagreement; user confirmation is the backstop meanwhile.
8. **Gate friction vs strictness:** how often does independent review reject legitimate changes? Tune review scope, never the strictness. Reason quality is the measurable.
9. **Topic-key matching quality:** measure injection precision/recall of deterministic AND-term matching before anything richer (embeddings etc.).
10. **Cost multiplier target:** the design spends ~6–8× a plain agent loop's model calls on gates/reviews/checks (estimated, not yet measured). M1–M2 must measure the real multiplier; if quality-per-cost never beats M0, the architecture's overhead is the first suspect, not the model.
11. **KV-cache hit rate across sequential invocations** on the target llama.cpp build — measured dimension; if reuse is poor, fresh-session economics change and step sizes grow.
12. **Guided thinking payout:** for which step types does harness-decomposed thinking (map-per-dimension) beat one-shot on quality-per-cost? Default off; keep only where it wins.

---

## 10. v2 flow (owner direction 2026-09-29 — supersedes the single-leaf contract in §4.8/§5)

### 10.1 Fixed steps, code-aware

The flow is FIXED — no step fuses or self-selects its depth; complexity may cost time, never correctness. Every step may read the repository through the controlled surfaces of §10.6.

1. **requirement triage** — one user message → N discrete issues, each written up. Reads the authoritative docs first (SSOT: a documented behaviour is not a bug).
2. **issue decomposition** — an issue → sub-issues, recursively, while budget allows. Same layer has no dependencies; a real dependency becomes nesting, never a sibling edge.
3. **specification** — attached to the node being created (one call per node: decompose + specify). A leaf spec carries files to touch, goal, ACs, how to test, and interface (existing vs new). An internal node's spec carries the interface contract between its children plus integration ACs — the file list belongs to whoever actually writes, so an internal node lists files only when it owns work or integration tests of its own.
4. **implementation and tests** — the two sides are written separately (test writer never sees the implementation), then meet: run, review (optional), and judge.
5. **judgement** — on test or review failure, an independent judge attributes the failure (implementation / tests / spec / environment) against the specification as the highest contract; spec defects bubble to the parent.
6. **completion** — a leaf closes only with implementation + passing tests; an internal node closes when its children close and its own integration ACs pass.
7. **discovery mid-flight** — a node that learns its decomposition or requirement is wrong returns to the owning node for re-decomposition; the node's content is reset via Git (discard that subtree's commits).

### 10.2 Budget

Budget is a first-class node field and the primary control on decomposition depth: a node with budget 1 cannot split. Wall-clock deadline is the PRIMARY budget (local inference has no token cost; the scarce resource is the human's return window — a Friday-afternoon task may run to Monday morning); call units are secondary accounting that orders the ladder and feeds cost stats. A parent splits a share to its children and keeps a reserve for integration and grants; unused child calls return to the parent; grants are recorded with their reason.

### 10.3 What "green" may mean (owner policy 2026-09-29 — the worst quadrant is a lie)

The run's own tests gate the run, and a claim additionally needs an independent test; the gate itself must be honest:

- **Red on arrival is required.** A self-test that passes the moment it is written does not
  exercise the failure; it is re-asked once and, if still green, the node stops honestly
  (`no-red-target`) rather than claiming. `red=True` is recorded only for an observed red —
  never asserted.
- **A test may be replaced, never weakened, and only by independent judgement.** The model
  saying "the test is wrong" is never enough: without an independent judge the claim is
  uncredited (`test_blame_uncredited`). A judge-attributed replacement is re-derived from
  scratch and must be red on arrival again; a green that follows a rewrite is reported as
  `green-after-test-rewrite` with `own_test_mutated`, so measurement can separate it.
- **A claim needs an INDEPENDENT TEST, not a text opinion (owner decision 2026-09-29,
  round 7 — replaces the round-4 falsifier).** A fresh-context call writes its own test from
  the goal, the extracted ACs, and the ORIGINAL and FINAL source of the changed files — it
  never sees the run's own test and never a grader path. The harness runs that test on a
  PRIVATE COPY of the pre-run tree and on one of the final tree (temp dirs outside the
  workdir): it must FAIL on the original (a test that passes there is vacuous,
  `independent-test-not-red`) and PASS on the final with the canary and expected node ids
  satisfied. `claimed=True` only when both gates hold and the run's own test is unmodified
  (`claimed_basis="own-test+independent-test"`). A rejection becomes the next attempt's
  failure context and the loop continues; a test that cannot be produced, afforded, or
  evaluated leaves `claimed=False`.
- **A machine-readable pytest report is the only green — the exit status is not
  evidence (owner decision 2026-09-29, round 6, adversarial finding F1).** Run-authored
  code executes inside the gate process (the run's own test imports the run's source), so
  `import atexit, os` + `atexit.register(lambda: os._exit(0))` made BOTH pytest runs exit
  0 with no test summary and turned a false success into a claimed true one. Green now
  requires a JUnit report written to a private `mkdtemp` OUTSIDE the repository: it must
  parse, hold at least one testcase, report zero failures and zero errors, contain the
  EXPECTED test file(s) with everything passed, and contain a per-run RANDOM canary node
  id (a generated test the run never saw). Every anomaly is RED and recorded as
  `gate_report_anomaly` with the detail. The corpus `checks.py` is untouched; the external
  grader adds its OWN report gate and marks the grade `suspected_contaminated_grade` when
  the corpus check exits 0 but the report does not. A transport error (`exit is None`), a
  policy-blocked result, and an un-runnable self-test (`self-test-unverified`, no file
  left behind) remain red. The run's writable scope is the union of the staged-owned paths
  and the corpus task's `UNTOUCHED` list — exactly what the grader restores (F2).

### 10.4 Stops — there is no "give up"
 — there is no "give up"

Six explicit stops, each with its own `stop_reason`: **success** (`green`, or
`green-after-test-rewrite`), **deadline handover** (`deadline`; the tree is kept so the goal
survives a human window), **call budget** (`calls`), **attempt cap** (`attempts`), **spec
bubble** (`spec-bubble`, `signal="bubble"`, `needs_parent=True` — the parent owns the spec),
and **node exhausted** (below, `signal="exhausted"`). A node is exhausted only when the
same-verdict tail coincides with either a structural attempt already made (re-split, parent
spec) or a broadly exercised ladder — so an untried restructuring lever keeps the node alive.
Wasted escalations are reported in the run record, not only in the process ledger.

### 10.5 Escalation ladder

Every escalation must ADD INFORMATION or SHRINK THE UNIT; a repeat that does neither is a wasted call. L1 more samples → L2 guided decomposition → L3 deeper exploration → L4 deterministic rule diagnosis → L5 independent review/judgement → L6 re-split into smaller children → L7 parent spec was wrong → L8 ask the human (non-blocking). Two modes feed the decision: **M1** erase the draft and regenerate with the failure history as intelligence; **M2** keep the draft and ask "do you have a new idea?" (cheapest, tried first). The model's own claim of novelty is never trusted alone: `harness/attempts.py` prefilters on failure signature and touched files and sends only genuine ambiguity to an independent judge.

### 10.6 Piloting is non-blocking

A question notifies and records a reversible default the run proceeds with; the answer arrives later as a normal tree patch (cascade reopens affected nodes). A question whose blocking nodes finished another way is withdrawn with a recorded reason, so the human returns to a short list of live questions instead of a backlog.

### 10.7 Context is curated, not pre-guessed

The harness injects a bounded repo map (files, symbols, call relations — as precise as fits, never "everything"), and the model may issue budgeted, shaped queries. Content the model has consumed is replaced by its own one-line conclusion (with a pointer back to the source), so exploration is controlled by compression rather than by a hard cutoff; deletion is explicit, never silent. Prefix stability is NOT a principle: KV-cache reuse is a measurable trade against curation benefit, reported per run.

### 10.8a Measured trade-off of the claim rule (owner-facing, 2026-09-29)

Blind, 10 tasks x 2 runs, one reference 4B model, grader outside the run. "claimed" is
what the harness asserted; "actual" is the grader; a false success is claimed-and-grader-failed.

| claim rule | actual | claimed | true success | missed | honest | false | calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| own test only (plain) | 12/20 | 11/20 | 10 | 2 | 7 | **1** | 69 |
| + independent test | 15/20 | 10/20 | 9 | 6 | 4 | **1** | 123 |
| + per-criterion discrimination | **16/20** | 4/20 | 4 | 12 | 4 | **0** | 183 |

More verification raises what the harness actually fixes and removes the lies, but it
also makes the harness claim success less often than it deserves, and it costs more
calls. The lever for converting missed success into true success is the QUALITY of the
independently written test (today the same small model writes it), not a looser rule;
loosening it is how the false success comes back.

Residual risk (accepted, not fixable in-process): discrimination proves a test is
sensitive to the old->new delta, never that it asserts the goal — a test can fail on the
pristine source for an unrelated reason (a missing symbol, a wrong type, `!= 0`) and
pass on a wrong fix. The grader remains the only ground truth; the harness's own claim
is evidence, not proof.

### 10.8 Scoring quadrants

Claimed × actual: true success (best) / **false success (worst — the system lied)** / missed success (it stopped although the work was right) / honest failure (it stopped and said so). Cost breaks ties. Honest failure scores below missed success, because both need follow-up but only the latter already achieved the goal. Per-ladder-level success rate and spend are tracked so the ladder order becomes evidence-driven.

---
