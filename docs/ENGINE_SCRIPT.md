# ENGINE SCRIPT — Pseudocode Draft v1

The SE methodology as a Python-ish script against the six kernel primitives. This is `scripts/v1/` — the reference revision. Kernel guarantees assumed here (not re-stated): schema validation, sandbox, check pipeline, erasure semantics, ledger, global budget enforcement.

```python
# ============================================================
# scripts/v1/main.py — entrypoint
# Kernel injects `k` (the six primitives) + `run_config` {request, repo, budget}.
# ============================================================

async def main(k, run_config):
    budget = run_config.budget          # max_leaves, max_calls, max_wall (kernel-enforced)

    # ---- C1/C2. Index build — a PRECONDITION of planning, not a later phase: B1 consumes
    #      candidate cuts and A3 consumes the index, so it precedes A/B. The C activities
    #      that consume it per-need (locate, context gathering) stay where routing puts them. ----
    index = await k.index.build(run_config.repo)  # C1/C2: harness-side, no model call

    # ---- A+B. Understand & plan CO-EVOLVE: trial decomposition is the ambiguity detector ----
    task, tree = await understand_and_plan(k, run_config.request, budget)

    # ---- C6. Environment: engine-owned lifecycle per stack ----
    await bootstrap_environment(k, tree)

    # ---- Execute the tree ----
    await execute_tree(k, tree, index, budget)

    # ---- H6: run summary ----
    summary = await llm_step(k, "run_summary",
        artifacts={"tree": tree.snapshot(), "trajectory": k.trajectory.summary()},
        question="Summarize what was done, what changed, what remains.")
    k.artifacts.write(summary, node=tree.root)


# ============================================================
# A. Intake ⟷ B. Plan — one stabilization loop, not two phases
# ============================================================

async def understand_and_plan(k, request, budget):
    """Understanding and decomposition co-evolve: you often can't know whether a task
    is well-understood until you try to split it precisely — the split IS the test.
    Intake is done when trial expansion stops surfacing contradictions.

    Routing (TASK_TAXONOMY pipeline routing): for a DIAGNOSTIC task class (bugfix/perf/crash)
    the location is the unknown, so trial decomposition is seeded by locate/reproduce
    (C3/D pipeline) and the evidence-seeded cuts land in `node.initial_evidence` — the plan
    is written after the evidence exists. The structural case below (plan straight from
    module-map seams) is for tasks whose location is known or irrelevant."""
    card = await llm_step(k, "task_card",
        artifacts={"request": request},
        question="Extract: goal, constraints, out-of-scope.")

    for round in range(UNDERSTAND_ROUNDS):                  # bounded
        # A4: direct ambiguities first (cheap check before expensive planning)
        ambiguities = await llm_step(k, "find_ambiguities",
            artifacts={"task_card": card},
            question="List high-risk ambiguities that block a correct plan.")
        if ambiguities.items:
            answer = await k.user(render(ambiguities))      # ask immediately, pause only this path
            card = apply_answers(card, answer)
            continue

        # trial decomposition — the real ambiguity detector
        tree = await plan_trial(k, card, budget)
        findings = tree.expansion_findings()     # contradictions, un-splittables, missing info
        if not findings.items:
            return card, tree                     # stable: split cleanly, no forced choices

        # findings feed back into the task card (some via user, some self-answerable)
        needs_human = [f for f in findings.items if f.kind == "needs-user"]
        if needs_human:
            card = apply_answers(card, await k.user(render(needs_human)))
        card = await llm_step(k, "revise_task_card",
            artifacts={"card": card, "findings": findings},
            question="Revise the task card given what precise splitting revealed.")
    return card, tree                         # cap hit: proceed with best understanding, findings on tree


# ============================================================
# B. Plan — expansion + reviews + scheduling
# ============================================================

async def plan_trial(k, task, budget):
    root = Tree.root(task)                          # universal node schema
    await expand_subtree(k, root, depth=0, budget=budget)
    k.validate_dag(root)                            # I/O edges → DAG; orphans/cycles → findings
    return root

async def expand_subtree(k, node, depth, budget):
    if budget.exceeded() or depth > DEPTH_CAP:
        node.status = "needs-user"                  # STABLE-but-parked: node won't execute without input.
                                                    # Question is pushed to the message box IMMEDIATELY;
                                                    # the DAG continues with independent subtrees; if nothing
                                                    # else is runnable, the run idles (cheap — local).
        return

    if is_leaf_sized(node):                         # ≤10 est. rounds, 1 artifact, 1 area
        return                                      # its ACs are authored later, AFTER the spec
                                                    # (execute_leaf below) — the gate must derive
                                                    # from the frozen contract, not from this line

    # harness proposes candidate cuts; model fills/annotates. Two modes (KERNEL_API §4.4):
    #   structural      — module-map seams: location known or irrelevant (feature/port/refactor)
    #   evidence-seeded — failing symbol / stack frames / covering tests: location IS the unknown
    #                     (bugfix/perf/crash). Never filename-only planning for a diagnostic task.
    candidates = k.index.propose_cuts(node, evidence=node.initial_evidence)   # H
    subtree = await llm_step(k, "expand",
        artifacts={"node": node, "candidate_cuts": candidates},
        question="Fill in child tasks along the proposed seams: what/why + leaf flag per child.")  # M

    # peer review the split (fresh context) — B2
    verdict = await llm_step(k, "split_review",
        artifacts={"subtree": subtree, "parent": node},
        question="Does this split work? Issues only.", fresh=True)
    if not verdict.ok:
        subtree = await revise(k, subtree, verdict.issues)      # bounded retries below
        # (revise → re-review, ≤2 rounds, then re-split smaller or needs-user)

    node.children = subtree.children
    for child in node.children:
        await expand_subtree(k, child, depth + 1, budget)       # uniform-layer recursion

    # Integration ACs for THIS node — optional by design: an empty list is the explicit
    # "no cross-child behavior" answer. Checks span the children just placed; each resolves
    # to a check a descendant already owns (a view, never a copy of leaf ACs).
    await author_acs(k, node)

async def author_acs(k, node, spec=None):
    """One step type, two triggers (ENVELOPE_SCHEMAS §6): a leaf's own ACs after its spec is
    frozen; an internal node's integration ACs after its children are placed. Either map is a
    GATE DEFINITION — authored here, decided by gate_decide in fresh context (proposer≠decider
    covers authoring a gate, not just changing one)."""
    acs = await llm_step(k, "draft_acs",
        artifacts={"node": node, "spec": spec, "children": node.children},
        question="For each AC give the check: test, script assertion, or 'subjective'.")
    verdict = await llm_step(k, "gate_decide",
        artifacts={"proposal": acs, "node": node, "spec": spec},
        question="Is this AC map a real gate? Flag 'subjective' where a deterministic check is feasible.",
        fresh=True)                                 # fresh ctx: never the author
    if verdict.decision != "accept":
        acs = await revise(k, acs, verdict.explanation)     # bounded: re-decide ≤2 rounds
    node.set_ac_test_map(acs)                       # kernel: every ac_id → ≥1 check


# ============================================================
# Execution — parallel DAG scheduler + per-leaf pipeline
# ============================================================

async def execute_tree(k, tree, index, budget):
    """Leaves are the DAG nodes; dependency-free AND conflict-free leaves run IN PARALLEL —
    that is the point of async. Scheduler: as leaves become ready (deps satisfied), spawn
    execute_leaf tasks up to the concurrency limit (work-tree-writers serialize per file-
    overlap group; read-only judges/peers parallelize freely). needs-user items are HELD —
    not blocking others; the moment the user answers (message box fires), the leaf is ready
    and enters the ready set immediately."""
    ready = tree.ready_leaves()                     # deps satisfied + not held + files-unlocked
    running = {asyncio.create_task(execute_leaf(k, leaf, index)) for leaf in ready}
    while running or tree.has_work():
        done, _ = await asyncio.wait(running, return_when=FIRST_COMPLETED)
        for t in done: running.discard(t)
        tree.refresh_status()                       # statuses propagate; done parents reopen if re-touched
        for leaf in tree.ready_leaves():            # fire immediately as deps/held-clear
            running.add(asyncio.create_task(execute_leaf(k, leaf, index)))
        # nothing runnable & run not finished → idle (cheap, local) until user/parked resolution

async def execute_leaf(k, leaf, index):
    leaf.status = "in-progress"                     # TRANSIENT: owned by this pipeline only.
    try:
        ...spec + parallel implement/test + gate as below...
    except Interrupted:                             # graceful: finish current step boundary first
        raise
    except Exception:                               # crash/OOM/kill — assume WIRE MIDDLE STATE.
        raise                                       # Recovery is BOOT-TIME (see boot_recover),
                                                    # not per-leaf: trajectory may not have flushed.

async def boot_recover(k, workdir):
    """Sudden death means the trajectory may not reflect the last mutations — per-leaf
    rollback is unreliable. Instead, on program boot (single-instance lock per workdir —
    never two harness processes in one workdir): reset everything we don't know and that
    is not ignored in the workdir — i.e. git-clean all uncommitted/untracked state.
    The workdir is harness-owned; the run only ever starts from a clean tree. Resumption
    then proceeds from the task tree's last committed step — artifacts are the memory,
    files are rebuilt by re-execution."""
    with k.lock(workdir):                           # single-instance guard
        if k.git.dirty(workdir):                    # uncommitted / untracked / non-ignored
            k.git.reset_hard_clean(workdir)
            k.ledger.note("boot", "reset dirty workdir: crash recovery")
    rounds_budget = leaf.estimate_rounds * 1.5      # headroom (kernel tracks; exhaustion → split signal)

    # ---- Spec is professional and complete (E1–E3): interfaces, types/schema, behavior
    #      contract (semantics/invariants/pre-post), error model, edge cases, affected files ----
    spec = await llm_step(k, "write_spec",
        artifacts={"leaf": leaf, "conventions": k.index.conventions},
        question="Write the spec: interfaces, types, behavior contract, error model, edge cases, files.")
    spec = await review(k, spec, reviewer="spec_review")       # E1 artifact IS reviewed — fresh ctx

    # ---- The gate's contract is frozen from the FROZEN spec, and decided by gate_decide —
    #      never authored from the plan line, never self-approved (A2) ----
    await author_acs(k, leaf, spec=spec)

    # ---- Code and tests in parallel. Firewall = withhold solutions, share requirements:
    #      both sides get interfaces + behavior; implementation_notes goes to the implementer
    #      only. The test writer never sees code; the implementer sees tests (it must run them)
    #      but its boundary excludes the test files, so it cannot edit them. ----
    code_t = asyncio.create_task(implement(k, leaf, spec, rounds_budget))
    test_t = asyncio.create_task(write_tests(k, leaf, spec))   # whole contract, never the code

    code_ok, tests_ok = await asyncio.gather(code_t, test_t, return_exceptions=True)

    # ---- Verify: closure gate is procedural ----
    results = k.gate.run(leaf.ac_test_map)          # F7: deterministic checks — existence/completeness
                                                    # of tests per AC is CHECKED HERE BY CODE, not by LLM
    if not results.all_map_entries_have_tests:
        return queue_test_writing(k, leaf, results.missing)    # trivially checkable → fix mechanically

    quality = await review(k, results, reviewer="test_quality")  # LLM's real job: are the tests
                                                    # meaningful, exercising the AC, non-tautological?
    verdicts = await judge_subjective_acs(k, leaf, results, quality)

    if not k.gate.all_green(leaf, results, quality, verdicts):
        await handle_failure(k, leaf, results.failures)        # F8-flagged gaps → router below
    else:
        leaf.close()                                # kernel re-checks (a)(b)(c) — never the script


# ============================================================
# Implement one leaf — bounded attempt loop
# ============================================================

async def implement(k, leaf, spec, rounds_budget):
    files = index.files_in_scope(leaf)              # task's declared file boundary
    ctx   = await k.compose(leaf, spec, files)      # per-call adaptive injection (no fixed cap)

    for attempt in range(MAX_ATTEMPTS):             # bounded-attempt rule: one hypothesis each
        change = await llm_step(k, "implement",
            artifacts={"ctx": ctx, "spec": spec},
            tools=TOOLSET_IMPLEMENT,                # per-step tool set: read_file, run_probe…
            question=f"Implement per spec. {'Attempt %d failed: %s' % (attempt, why) if attempt else ''}")

        wrote = await k.check_write(change)         # kernel: check pipeline, auto-fix ≤2,
                                                    # rollback + ledger on unfixable
        if wrote.ok:
            return wrote

        # failure → shaped survivors or rollback; model never sees failed text (§2.4)
        ctx = await k.compose(leaf, spec, files, failure=why)
    return split_signal(leaf)                       # → re-split into smaller leaves (below)


async def write_tests(k, leaf, spec):
    plan = await llm_step(k, "test_plan",
        artifacts={"ac_test_map": leaf.ac_test_map, "spec": spec},   # contract only — no code
        question="Concrete test cases per check_id.")
    files = []
    for case in plan.cases:
        files += await llm_step(k, "write_test",
            artifacts={"case": case, "patterns": k.index.test_patterns},
            question="Write this test.")
    return files
# ============================================================
# Failure routing — judge first, then route to the guilty side
# ============================================================

async def handle_failure(k, leaf, failures):
    """Two classes, different routes:
    (1) compile / static check / artifact check / runtime error-warning — the implementer
        ALREADY saw these (it ran the code once); harness re-checks anyway. Route straight
        back to the implementer (or auto-fix) — no judge needed.
    (2) UT/API/E2E failures — code ran, behavior wrong. FIRST judge which side is buggy
        (code | test | spec), THEN route to the guilty role."""
    for failure in failures:
        if failure.is_static_class:                 # saw-it-before class → no judge
            await route_to_implementer(k, leaf, failure)
            continue

        verdict = await llm_step(k, "failure_judge",      # the judge BEFORE routing
            artifacts={"failure": failure, "spec": leaf.spec,
                       "diff": k.git.diff(leaf), "test_src": failure.test_source},
            question="Which side is buggy: code | test | spec? Evidence for each.",
            fresh=True)

        match verdict.side:
            case "code": await route_to_implementer(k, leaf, verdict)
            case "test": await queue_fix_ticket(k, leaf, target=failure.test, kind="test-bug")
            case "spec": await propose_spec_change(k, leaf, verdict)   # gate-reviewed — touches the gate

    bugs = await surface_more_bugs(k, leaf, failures)         # D0: anything beyond routed failures
    for bug in bugs.items:
        node = tree.insert_ticket(leaf, bug)                  # ticket = task-tree node
        await debug_pipeline(k, node)

async def surface_more_bugs(k, leaf, failures):
    triage = k.triage_rules(failures)                         # D1 mechanical first
    if triage: return triage
    return await llm_step(k, "identify_bugs",                 # D0 merged question
        artifacts={"failures": failures, "evidence": k.evidence.for_leaf(leaf)},
        question="Do you see bug(s)? List with symptom/evidence/location/severity.")

async def debug_pipeline(k, node, probe_rounds=PROBE_CAP):
    """Judge → fix → re-judge loop, kept SHORT by design: the model never carries the
    session history — each fix attempt is a fresh invocation with: the judge's verdict,
    the proposed fix, and the shaped failure if a previous try failed. Long debugging
    history is the enemy (small model + long history = lost); evidence persists in the
    node's evidence artifact, not in any conversation."""
    evidence = node.initial_evidence

    for _ in range(probe_rounds):                   # scripted bounded probe loop
        probe = await llm_step(k, "propose_probe",
            artifacts={"evidence": evidence}, tools=TOOLSET_PROBE,
            question="Next most-informative probe + why.")
        if probe.confident_enough: break
        result = await k.exec(probe, provenance="model")     # sandboxed; policy-blocked → allowlist req
        finding = await llm_step(k, "interpret_probe",
            artifacts={"probe_result": result},
            question="What did we learn? Fact + implication.")
        evidence.add(finding)

    # Judge: who's to blame (code | test | spec | both), what's the problem, possible fixes.
    verdict = await llm_step(k, "debug_judge",
        artifacts={"evidence": evidence, "spec": node.spec, "diff": k.git.diff(node)},
        question="Who's to blame? What exactly is wrong? List possible fixes (ranked).",
        fresh=True)

    # Fix loop: the fixer is an AGENT, not a courier — the judge's diagnosis + ranked fixes
    # are context (free advice), not orders. Each attempt is a fresh invocation carrying:
    # verdict, ranked fixes, prior shaped failures — the fixer reasons on its own and returns
    # a structured envelope:
    #   {status: fixed | failed | blocked,
    #    new_issues: [{keywords, description, blocked: bool}],   # discovered mid-fix → tickets
    #    comment: self-summary}                                  # contract position (§4.2)
    # new_issues.blocked=true → immediately bubbled as a ticket; run continues otherwise.
    # Termination: fixed | MAX_FIX_ATTEMPTS (→ needs-user, ladder visible) | all-blocked.
    prior_failures = []
    for _ in range(MAX_FIX_ATTEMPTS):
        result = await llm_step(k, "fix_attempt",
            artifacts={"verdict": verdict, "ranked_fixes": verdict.fixes,
                       "prior_failures": prior_failures},
            tools=TOOLSET_IMPLEMENT,
            question="Fix per diagnosis and fixes — or reason on your own. Report the envelope.")

        for issue in result.new_issues:             # discovered during fixing — bubble immediately
            tree.insert_ticket(node, issue)
        if result.status == "fixed":
            node.close(); return
        if all(i.blocked for i in result.new_issues) and result.status == "blocked":
            node.status = "needs-user"; return      # everything blocked → human
        prior_failures.append(result)               # short structured residue, never full history
    node.status = "needs-user"                      # ladder exhausted → human, ladder visible


# ============================================================
# Reviews, judges, gate review (propose ≠ decide)
# ============================================================

async def judge_subjective_acs(k, leaf, results):
    """Multi-aspect panel; aspects & fleet size from run_config."""
    tasks = [llm_step(k, f"judge_{aspect}",
                artifacts={"leaf": leaf, "diff": k.git.diff(leaf), "results": results},
                question=ASPECT_PROMPTS[aspect], fresh=True)
             for aspect in run_config.judge_aspects]      # e.g. spec-match, test-meaning, no-corner-cut
    return merge_verdicts(await asyncio.gather(*tasks))   # disagreement → record + weight

async def gate_review(k, proposal):                  # AC/test/tree changes: propose ≠ decide
    """Proposer wrote proposal + reason (never this agent's own gate)."""
    verdict = await llm_step(k, "gate_decide",
        artifacts={"proposal": proposal, "evidence": k.ledger.resolve(proposal.refs)},
        question="Validate the REASON: real? does it weaken the gate? meaning preserved?",
        fresh=True)
    return verdict                                   # reject → back to proposer with reason


# ============================================================
# Utilities the script relies on
# ============================================================

async def review(k, artifact, reviewer):
    """Fresh-context reviewer for a spec/test-quality artifact. Returns verdict {ok, issues[]}."""
    return await llm_step(k, reviewer, artifacts={"artifact": artifact},
                          question="What is here, what are its flaws?", fresh=True)

async def llm_step(k, step_type, *, artifacts, question, tools=None, fresh=False):
    """One model invocation. Kernel does: prompt-file load (byte-stable prefix),
    composer injection (per-call adaptive), grammar envelope, schema validation,
    ledger, budget accounting. `fresh=True` = no author context leakage."""
    return await k.llm(step_type, artifacts, question, tools=tools, fresh=fresh)

def split_signal(leaf):
    """Round/attempts exhausted → re-split this leaf into smaller ones (B1 op on a leaf)."""
    ...
```

## Reading notes for review

- **What to scrutinize:** boot-time crash recovery (`boot_recover`): reset-all-unknown-on-boot vs any smarter reconciliation — and the single-instance lock, is that enough guarding? The debug fix loop: fixer-as-agent (judge's fixes = advice, not orders; fixer returns structured envelope with new_issues/status/comment) — is the envelope schema right? Is `MAX_FIX_ATTEMPTS` the right bound? The parallel DAG scheduler: file-overlap grouping vs full serialization for writers? The failure router: "code|test|spec" with confidence enough? `needs-user`: held-not-blocking + fire-immediately-on-answer — right?
- **Kernel/script seam visible here:** everything mechanical is `k.*` (compose, check_write, gate.run, exec, user); the script only decides *sequence and questions*. If a reviewer can't tell which side a call belongs to, that's a design bug — flag it.
- **Prompts are placeholders.** The `question="..."` strings are demo-level; real prompts live in `prompts/<step>.md` — detailed, example-led, fill-in-form style per DESIGN §4.2.
- **Deliberately not shown (kernel-side):** erasure/rollback inside `check_write`, sandbox policy inside `exec`, schema validation inside `llm`, DAG validation inside `tree.next_ready_leaf()`, budget enforcement (throws `BudgetExceeded` → pilot UI).
- **Open knobs:** `MAX_ATTEMPTS`, `PROBE_CAP`, `DEPTH_CAP`, `judge_aspects`, per-step tool sets. All config, all measurable.

```
