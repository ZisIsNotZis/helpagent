# UI DESIGN — Mission Control (Jet-Operator Style)

The user-facing surface for piloting helpagent runs. Web UI. Design truth for v1.

## 1. Design stance

**The UI is a deterministic renderer over kernel state — zero LLM.** Everything shown exists as typed artifacts (task tree, trajectories, statuses). The user is the orchestrator; the UI is the switchboard's front panel. Two jobs only:

1. **See**: fleet/tree state, live. 2. **Steer**: typed messages into nodes.

No chat pane, no free-text "talk to the agent" — every input is a typed, routed message (patch / hint / answer). The message box is the only input surface, matching DESIGN §4.8.

## 2. Layout

```text
┌────────────────────────────────────────────────────────────────┐
│  RUN HEADER: task · script rev · budget burn (leaves/calls/wall)│
│            · global status (RUNNING / IDLE-WAIT / DONE / HALT)  │
├───────────────────────────────┬────────────────────────────────┤
│                               │  SIDE PANEL (selected node)     │
│   TREE VIEW (center-left)     │  ┌──────────────────────────┐  │
│                               │  │ NODE HEADER               │  │
│   <plan>                      │  │ id · status · role        │  │
│   ├─ <plan.auth>        ●run  │  │ AC test map (green/red)   │  │
│   │  └─ <plan.auth.1>   ✓done │  │ spec / diff / artifacts   │  │
│   ├─ <plan.db>          ⏸wait │  ├──────────────────────────┤  │
│   │  ├─ <plan.db.1>     ●run  │  │ TRAJECTORY (live)         │  │
│   │  └─ <plan.db.2>     ○pend │  │ step stream, token stream │  │
│   └─ <plan.ui>          ○pend  │  │ tool calls + shaped res   │  │
│                               │  ├──────────────────────────┤  │
│   (status glyphs, live)       │  │ MESSAGE BOX               │  │
│                               │  │ [patch|hint|answer] + text │  │
└───────────────────────────────┴────────────────────────────────┘
```

## 3. Node identity & addressing

- **Deterministic path ids**: `<plan>.<subplan>…<job><N>` — e.g. `fixbug.auth.jwt.1`. Ids are assigned at expansion, stable across the run, human-readable, and double as the log/artifact namespace (`artifacts/<run>/fixbug.auth.jwt.1/…`). Regenerated subtrees (patches, D9 growth) get fresh suffixes — ids are never mutated; a changed plan is a new id. This makes every message, artifact, and trajectory entry addressable and greppable.
- **Tree view glyphs**: `● running · ✓ done · ○ pending · ⏸ waiting-for-user · ⛔ blocked · ↻ stale · ⚑ needs-user decision`. Parallel execution is visible — several `●` at once, that's the DAG running.

## 4. Trajectory view (the inspector)

Per selected node, live-streaming (SSE/WebSocket):

- **Step stream**: each model invocation as a block — step type, tools used, tokens, wall time, outcome.
- **Token stream**: generation renders live inside the current step block (read-only; this is an observation feed, not a chat).
- **Tool calls**: proposed command → shaped result (the model never saw raw output; neither does the user by default — expand for raw, secret-filtered).
- **Check pipeline results**: ladder rungs with auto-fix annotations.
- **Erasure honesty**: auto-fixed/rolled-back attempts show as annotated tombstones (`attempt 2 — auto-fixed: ruff format`), not hidden — the UI tells the truth about history without polluting any model's context.

## 5. Input model — the decision

**Selected node + side-panel inbox.** Not per-node inboxes, not root-only.

- **Why not per-node inboxes**: N inboxes = N unread states to manage, and messages usually concern *one* thing the user is looking at. Selection is the addressing mechanism.
- **Why not root-only**: the whole piloting design (patch/hint/answer to any node) collapses if you can only address the root; routing to a deep node from root means retyping its id — the UI's job is to make addressing free.
- **Mechanics**: select a node in the tree (or click a ⏸/⚑ glyph — selects and focuses the pending question); the side panel shows that node's context (AC map, current step, evidence so far) so the message is written *with the node's state visible*; the message box offers exactly three typed actions:
  - **answer** — resolves this node's pending question (enables only when the node has one).
  - **hint** — guidance artifact injected into the node's composed context; node continues under identical schema constraints.
  - **patch** — structural change; opens a confirmation preview (proposed subtree diff before/after) because patches regenerate children — the one destructive input, so it previews.
- **Interrupt semantics are shown, not hidden**: sending to a `●` running node displays "interrupts at next step boundary; children pause" before send. Two-click force-stop lives on the node (graceful ⟶ force), matching the script's interrupt ladder.
- **Unrouted input fallback**: typing with nothing selected targets the run root — the UI never guesses intent; it shows the target on the send button (`→ fixbug.db.2`) so mis-addresses are visible before send.

## 6. Notifications, not surveillance

The user is not watching streams all day. Push moments (banner + optional sound):

- ⏸/⚑ any node waits for user (the rare, designed human-in-loop moment).
- ⛔ all-runnable-exhausted (run idle-waiting, nothing to steer).
- Crash/boot-reset events (from `boot_recover` ledger notes).
- Budget warnings (kernel-enforced caps approaching).

Everything else is pull — the tree glance answers "how's it going."

## 7. What the UI deliberately does not do

- **No plan-file editing** — all structural change flows through patch (message box), per DESIGN §4.8.
- **No LLM features** — summaries, explanations, "what happened?" are rendered from artifacts (the run summary artifact exists, H6). If a view needs a model to explain it, that's a taxonomy/artifact gap — file it, don't patch the UI.
- **No multi-run view in v1** — one run, one page. Fleet-of-runs comes later if stats demand it.
- **No editing of model-authored artifacts** — read + steer; authorship stays with the pipeline (proposer≠decider applies to the user's own patches only in that they bypass it — the user is final authority, the UI makes that power explicit, not casual).

## 8. Implementation notes (v1)

- Backend: kernel exposes a **read-only state socket** (tree snapshot + per-node trajectory stream + event feed) — the same events the ledger already records; the UI adds zero new state.
- Frontend: any reactive framework; tree view is the only custom component worth polish — it is the product's face. Status colors and glyphs match §3 exactly so trajectory logs, docs, and UI share one vocabulary.
- The UI is a **consumer of the event log**, not a peer: kill the UI mid-run, nothing in the run changes (same property as any renderer).
