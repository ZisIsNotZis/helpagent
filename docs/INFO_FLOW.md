# INFORMATION FLOW — Engine Script v1 (pure dataflow, worked example inside)

The main diagram is the complete topology. **The worked examples below it are the same
graph with real payloads filled in** — §2 traces the *structural* entry (feature class: the
request names the layers, so module-map seams are the real seams), §3 the *diagnostic* entry
(bugfix: location unknown, so the plan is written after `locate` produces evidence). Read the
examples first if the full diagram is too dense; read the diagram to see how they generalize.

## 2. Worked example — "add per-user login rate limiting" (feature class, structural)

Stack pinned for concreteness: **FastAPI + SQLite + React** (the mechanism is stack-agnostic —
C6 owns a per-stack bootstrap; unknown stacks fall back to the model). This trace shows the
*structural* entry: the request names the layers, so the module map's seams are the real seams.
It includes one rejected split, one rejected AC, and one spec-blame failure — the interesting
steps are the ones where the harness says no.

### Step 0 — `task_card` (intake)

**Input** (kernel-composed from `run_config`): the user's raw request, verbatim —

```json
{"request": "Add per-user login rate limiting: after 5 failed logins within 15 minutes, reject that user's attempts for 15 minutes, reset the counter on success. Show remaining attempts on the login screen. Stack: FastAPI + SQLite + React."}
```

**Output envelope:**

```json
{
  "status": "ok",
  "comment": "Cross-layer feature: DB state, API enforcement, UI display. No ambiguity blocking a plan.",
  "task_class": "feature",
  "goal": "Per-user login rate limiting: 5 failed logins in 15 min → 15 min lockout per user; success resets. UI shows remaining attempts.\nConstraints: existing users unaffected (no data loss); follow repo conventions.\nOut of scope: IP-based limiting, e-mail notification."
}
```

`task_class: "feature"` → structural candidate cuts, index build already done (C1/C2 precede A/B).

### Step 1 — structural cuts → `expand` → `split_review` rejects → re-expand

**Candidate cuts** (harness-side, from the module map — lookup + deterministic ranking, no model):

```json
{"candidate_cuts": [
  {"seam_id": "seam-db",  "files": ["backend/db/schema.py", "migrations/"],      "rationale": "users table DDL and migrations"},
  {"seam_id": "seam-api", "files": ["backend/api/auth.py"],                      "rationale": "login endpoint"},
  {"seam_id": "seam-ui",  "files": ["frontend/src/Login.jsx"],                   "rationale": "login form component"},
  {"seam_id": "seam-tests","files": ["tests/"],                                  "rationale": "auth test scope"}
]}
```

**First `expand` output — rejected by `split_review`:**

```json
{
  "status": "ok",
  "comment": "Three work leaves along the seams.",
  "children": [
    {"seam_id": "seam-api", "what": "Failed-login counter + lockout check in the login endpoint", "why": "Enforcement point", "leaf": true, "est_rounds": 6},
    {"seam_id": "seam-db",  "what": "Add failed_login_attempts + locked_until columns, backfill", "why": "State for the counter", "leaf": true, "est_rounds": 4},
    {"seam_id": "seam-ui",  "what": "Show remaining attempts on the login form", "why": "Requested UI", "leaf": true, "est_rounds": 3}
  ]
}
```

```json
{"ok": false,
 "issues": [
  {"kind": "overlap", "target": "seam-api", "description": "lockout read/write hits the users row that seam-db owns — both leaves mutate the same row"},
  {"kind": "missing-piece", "target": "parent", "description": "nothing owns 'counter resets on success' — it spans the endpoint and the row"}
 ]}
```

The kernel hands the issues back to `expand` (bounded revise → re-review). **Second attempt — accepted:**

```json
{
  "status": "ok",
  "comment": "DB leaf owns the row shape, API leaf owns enforcement via that row, UI reads it. Tests split out per side.",
  "children": [
    {"seam_id": "seam-db",  "what": "users table gains failed_login_attempts INTEGER NOT NULL DEFAULT 0 and locked_until TEXT NULL; migration 0007", "why": "Row shape is the single owner of lockout state", "leaf": true, "est_rounds": 4},
    {"seam_id": "seam-api", "what": "Login endpoint enforces the window through the users row: count, lock, reset on success", "why": "One writer of lockout state, behind the existing transaction", "leaf": true, "est_rounds": 6},
    {"seam_id": "seam-ui",  "what": "Login form renders remaining attempts and the locked message from the 429 body", "why": "Requested UI", "leaf": true, "est_rounds": 3},
    {"seam_id": "seam-tests", "what": "API tests for lockout window, reset, and user-indistinguishable errors (tests/api/test_lockout.py)", "why": "Test side is heavier than the UI side — split it (per-side leaf criterion)", "leaf": true, "est_rounds": 5},
    {"seam_id": "seam-tests", "what": "E2E: full login flow through UI + API + DB (tests/e2e/test_login_flow.py)", "why": "The user story's AC is end-to-end and must be exercised locally", "leaf": true, "est_rounds": 4}
  ]
}
```

Note the shape this produces: three *work* leaves and two *test* leaves — the owner rule in
action (the criterion applies per side; the UI's own light component test stays inside
`seam-ui`, no split needed there). The two test leaves share the `seam-tests` scope but own
disjoint files; `files_touched` narrows each to its own file, and the file-overlap scheduler
serializes same-group writers.

### Step 2 — `write_spec` (leaf `seam-api`)

**Input** (kernel-composed): node + boundary (`backend/api/auth.py`) + conventions + symbol
ground truth (`login` handler exists at `backend/api/auth.py:31`).

```json
{
  "status": "ok",
  "comment": "One interface; window math and state ownership are the whole feature.",
  "interfaces": [
    {"name": "login", "signature": "async def login(credentials: Credentials) -> TokenResponse", "contract": "On success: 200 + token, counter reset, locked_until cleared. When locked: 429, body carries retry_after_seconds. Existing/unknown users are indistinguishable in error bodies."}
  ],
  "behavior": "Lockout window 15 min, threshold 5 failures, per user. Counter and locked_until live on the users row (migration 0007). Failure path increments inside the existing transaction; the 6th attempt within the window → 429. Success path resets both fields in the same transaction as token issue.",
  "implementation_notes": "No new table — state is two columns on users. Read-modify-write inside the existing session transaction; no second round-trip.",
  "files_touched": ["backend/api/auth.py"]
}
```

**Routed (the firewall — withhold solutions, share requirements):**

- `interfaces + behavior + implementation_notes` → `implement` ctx
- `interfaces + behavior` → the *test* leaves' ctx — never `implementation_notes`, never the
  diff, never code. The test writer asserts the **contract** (429, `retry_after_seconds`,
  indistinguishable errors) because the contract said so — not because it guessed.
- `files_touched` narrows the boundary (kernel checks ⊆); the implementer *cannot* write
  `tests/…` even though it must run those tests — different seam, policy-blocked.

### Step 3 — AC map from the frozen spec → `gate_decide` decides

Authored **after** `spec_review` passed, from the frozen contract (never from the plan line):

```json
{"acs": [
  {"ac_id": "AC-1", "statement": "6th failed attempt within the window → 429, body carries retry_after_seconds", "check_kind": "test", "check_hint": "tests/api/test_lockout.py::test_sixth_attempt_429"},
  {"ac_id": "AC-2", "statement": "successful login resets failed_login_attempts and clears locked_until", "check_kind": "test", "check_hint": "tests/api/test_lockout.py::test_success_resets"},
  {"ac_id": "AC-3", "statement": "locked-out and unknown users are indistinguishable", "check_kind": "subjective", "check_hint": "inspect error responses in the diff"}
]}
```

`gate_decide` (fresh context) **rejects** it:

```json
{"decision": "reject", "reason_is_real": true, "weakens_gate": true, "meaning_preserved": false,
 "explanation": "AC-3 as subjective is gate-easing: a deterministic check is feasible — assert identical error body for existing vs unknown user."}
```

Revised AC-3 → `check_kind: "test"`, hint `test_lockout.py::test_unknown_user_indistinguishable`.
Map frozen. This is the subjective-inflation guard doing its one job.

### Step 4 — `implement` ⟂ test leaves (parallel, per side)

`seam-api` implements in a bounded tool-loop (writes through the check pipeline, runs the
canonical command itself, envelope is the report only):

```json
{"status": "ok", "comment": "Window math in auth.py:31-58; state via users row; ran pytest tests/api -x green locally.", "tests_run": ["pytest tests/api -x"]}
```

`seam-db`'s migration is verified on a **throwaway SQLite file the harness creates and
destroys** — apply → test → drop; never live-stateful. `T-api` writes its test file blind to
the implementation:

```json
{"file_path": "tests/api/test_lockout.py", "content": "...whole test file..."}
```

### Step 5 — gate red → `failure_judge` blames the SPEC

TC for AC-1 fails: the test asserts `retry_after_seconds` in the 429 **body**; the repo's
`ApiError(status, detail)` has no body-field mechanism — the spec invented a response shape the
error model cannot produce. Judge (fresh context, sees failure excerpt + test source + spec +
diff):

```json
{"status": "ok",
 "comment": "Test and code each match the spec; the spec's contract is unimplementable as written.",
 "problems": [
  {"side": "spec", "description": "contract requires retry_after_seconds in the 429 body; ApiError has no body-field path", "evidence": "backend/api/errors.py:8 vs AC-1", "confidence": "high"}
 ]}
```

`side: "spec"` routes to a spec-change proposal, gate-reviewed (proposer ≠ decider), revised to
*"429 status; `retry_after_seconds` as a response header"*. Both sides get the revised contract;
the gate re-runs. Green.

### Step 6 — closure

- Work leaves close on their own maps (regression command + own tests).
- Test leaves close on their own files' results.
- The **parent** (the feature node) closes on (c) + its **integration map** — the view rule:

```json
{"ac_test_map": [
  {"ac_id": "INT-1", "statement": "full story: 5 failures → locked → success after window", "check_kind": "test", "command": "pytest tests/e2e/test_login_flow.py::test_lockout_story"},
  {"ac_id": "INT-2", "statement": "API contract holds (429 + retry_after_seconds)", "check_kind": "test", "command": "pytest tests/api/test_lockout.py"},
  {"ac_id": "INT-3", "statement": "migration applies on a fresh DB", "check_kind": "script-assertion", "command": "python -m minirepo.migrate --throwaway"}
]}
```

Every entry resolves to a check a descendant already owns — references, never copies, which is
why five leaves did not produce five copies of the same AC.

## 3. Worked example b — the same bug, the diagnostic entry (evidence-seeded)

Request: *"Sessions expire after 60s instead of 1h. Probably broke when we refactored auth."*
Location is the unknown, so the plan is written **after** the evidence exists.

**D1 `locate`** — C3: model over H-ranked slices (index already built). Ranked candidates:

```json
{"candidates": [
  {"path": "auth/config.py", "symbol": "SESSION_TTL", "confidence": "high", "why": "only definition of the TTL constant"},
  {"path": "middleware/auth.py", "symbol": "check_session", "confidence": "high", "why": "reads expiry; in the failing path"},
  {"path": "tests/auth/test_expiry.py", "symbol": "test_expiry_is_one_hour", "confidence": "medium", "why": "covers the reported behavior"}
]}
```

**D2 reproduce** — canonical command runs, shaped failure; call-graph lookup shows
`create_session → get_session_expiry` — the create path reads the *same* constant.

**D3 evidence-seeded cuts** — `propose_cuts(node, evidence)`:

```json
{"candidate_cuts": [
  {"seam_id": "seam-config", "files": ["auth/config.py"], "rationale": "failing symbol's constant, anchored by stack frame + test"},
  {"seam_id": "seam-tests", "files": ["tests/auth/"], "rationale": "regression pin for the reported behavior"}
]}
```

**D4 `expand` (evidence-seeded):**

```json
{
  "status": "ok",
  "comment": "One constant, one regression pin. Create path shares the constant — no second fix.",
  "children": [
    {"seam_id": "seam-config", "what": "auth/config.py:12 — SESSION_TTL is 60 (seconds) where the consumer treats it as hours; set 3600 and rename to SESSION_TTL_SECONDS with an explicit unit", "why": "Failing symbol's constant is the root cause (evidence: test_expiry red + single definition)", "leaf": true, "est_rounds": 2},
    {"seam_id": "seam-tests", "what": "Pin expiry == creation + 1h (tests/auth/test_expiry.py already red — make it the regression)", "why": "The failing test is the AC's check", "leaf": true, "est_rounds": 1}
  ]
}
```

What changed against the old trace, by name: the plan names **file:line** because `locate` put
it in the evidence (grounding, not filenames — and `est_rounds` 2 comes from a one-constant
diff, not a guess). The invented `seam-3b` ("session-create sets expiry from config") is
**refuted by the call graph** — the create path already reads the constant, so a second leaf
would have been duplicated work and an unrelated change. And nothing invented a 401 feature:
the only behaviors in the plan are the reported one and its regression pin. Everything
downstream (spec → AC map → parallel impl/test → gate) is identical in shape to §2.

## 4. Full topology — how to read it against the example

- Every edge label in §1 names fields; the example shows their concrete shapes.
- **Stores are the memory**: `task tree` and `evidence artifact` are the two hubs; the
  work tree is the only place code lives; the ledger/trajectory are append-only truth.
- **Two entry points, one graph**: `task_class` selects the candidate-cut mode — **structural**
  (feature/port/refactor/scaffold: module-map seams) or **evidence-seeded** via `locate`
  (bugfix/perf/crash: the failing symbol, stack frames, covering tests). A diagnostic plan is
  never fabricated from filenames, which is why `EXP` sits downstream of `LOC` for those classes
  (TASK_TAXONOMY pipeline routing).
- **Isolation is enforced by routing + boundary, not by edge absence**: the test writer has no
  edge from `IMPL` and never receives `implementation_notes`; the implementer has no edge from
  any transcript (only `prior_failures[]`, shaped) and *cannot edit the tests* even though it
  must run them — writes are scoped to its seam boundary, and the check pipeline blocks the rest.
  Both sides receive the full contract (`interfaces` + `behavior`): withholding *requirements*
  produced unfounded tests, not independence. `comment` fields route to inspection only, never
  to another model step.
- **Kernel-computed nodes** (routing, outcome, gate.close, cascade): all-data in,
  decision-out — the "model never decides" principle as graph shape.
- **`lesson` is the only debug→memory edge.**
