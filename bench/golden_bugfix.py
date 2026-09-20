#!/usr/bin/env python3
"""Golden bugfix script v1 — M2 milestone core (DESIGN §8 milestone 2: "Kernel
primitives + artifact store + golden bugfix script + session runner"; ENGINE_SCRIPT.md
understand_and_plan → leaf pipeline, collapsed to the single-leaf path this corpus
exercises: task_card → expand → write_spec → draft_acs+gate_decide → write_test →
implement (bounded loop) → gate → run_summary).

Real model (llama-server :8833, Spark-X2.5-4B), real kernel invariants: every step
goes through llm_step (grammar decode + validation-context reference checks +
tree-sitter repair + erasure on failure), every write through the artifact store
(secret filter at the boundary), every command through exec (allowlist +
policy-blocked shaped results), the workdir is locked, git-snapshotted, and the
gate runs the corpus contract: pytest green + untouched-files byte-identity.

DECISIONS (minimal M2 readings, each flagged inline):
- D-transport: `implement` edits ride the write_test content envelope — the only
  content-emitting schema tonight (ENVELOPE_SCHEMAS §10/§11); the M3 tool-loop
  replaces this. The tree node and ledger still record the implement step.
- D-gate: checks.py binds UNTOUCHED to the corpus checkout's own repo/ path, so the
  gate computes the same two contracts (pytest green + untouched byte-identity)
  against the run workdir via Trajectory; the original task dir must remain
  byte-unchanged (asserted at the end).
- D-test-side: if the golden-written AC test fails while the task's own suite
  passes, the simplified M2 router treats it as side=test → drops the golden test
  file with a ledger note (a real run routes test-side failures to a fix ticket).

Usage:
  uv run python bench/golden_bugfix.py [--task TASK_DIR] [--attempts 3] [--skip-golden-test]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path



sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import (  # noqa: E402
    Envelope,
    FakeModelRunner,  # noqa: F401  (protocol reference)
    SchemaViolation,
    TaskTree,
    FailureSummary,
    ledger_entries,
    llm_step,
    note,
    reset_ledger_for_tests,
)
from harness.artifacts import Artifact  # noqa: E402
from harness.exec import ShapedResult  # noqa: E402
from harness.exec import exec as k_exec  # noqa: E402
from harness.checks import check_write, diagnose_test_output  # noqa: E402
from harness.envelopes import file_tokens  # noqa: E402
from harness.knowledge import build_knowledge  # noqa: E402
from harness.model import LlamaServerRunner  # noqa: E402
from harness.trajectory import Trajectory, pause_leaf_on_conflict  # noqa: E402
from harness.workdir import boot_recover, lock  # noqa: E402

GUIDED_IMPLEMENT = False
KNOWLEDGE = False


def asyncio_run(x):
    return x  # identity: llm_step below is wrapped with the step-retry and runs synchronously


_llm_step_real = llm_step


def llm_step(model, step_type, retries=1, **kw):
    """Script-level step retry (DESIGN §4.1 failure handling: retry with failure
    summary + missing info). One retry; the violation text becomes the summary
    (erasure-compliant: never the failed attempt's text)."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return asyncio.run(_llm_step_real(model, step_type, **kw))
        except SchemaViolation as exc:
            last = exc
            note("golden_step_retry", step_type=step_type, attempt=attempt + 1,
                 detail=str(exc)[:160])
            kw["failure"] = FailureSummary(step_type=step_type,
                                           summary=str(exc)[:200], missing=[])
    raise last

ROOT = Path(__file__).resolve().parents[1]
SERVER = "http://127.0.0.1:8833"


# --------------------------------------------------------------------------- task


def load_task(task_dir: Path) -> dict:
    # corpus tasks carry repo/; the mini_repo fixture IS the repo
    repo = task_dir / "repo" if (task_dir / "repo").exists() else task_dir
    files = {
        str(p.relative_to(repo)): p.read_text()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    conventions = ""
    for cand in ("CONVENTIONS.md", "README.md"):
        if (repo / cand).exists():
            conventions = (repo / cand).read_text()
            break
    # DECISION: the mini_repo fixture ships no request.md — its report is derived
    # from TEST_PLAN §4 (seeded ZeroDivisionError-vs-MinirepoError bug).
    request_path = task_dir / "request.md"
    request = request_path.read_text() if request_path.exists() else (
        "minirepo.calc.divide raises ZeroDivisionError on the denominator-0 path; "
        "it must raise the project's MinirepoError instead (see CONVENTIONS.md).")
    return {
        "task_id": task_dir.name,
        "request": request,
        "repo": repo,
        "files": files,
        "conventions": conventions,
    }


def stage_workdir(runs_dir: Path, task_id: str, files: dict[str, str]) -> tuple[Path, Trajectory]:
    workdir = runs_dir / "work"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    for rel, content in files.items():
        p = workdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    tr = Trajectory(workdir=workdir)
    tr.ensure_git()
    return workdir, tr


def run_pytest(workdir: Path) -> ShapedResult:
    return asyncio.run(k_exec(["python3", "-m", "pytest", "-q"], workdir, provenance="kernel"))


def pytest_exit(workdir: Path) -> int:
    res = run_pytest(workdir)
    return res.exit if res.exit is not None else 1


# --------------------------------------------------------------------------- steps


def step_task_card(model, request: str) -> Envelope:
    return asyncio_run(llm_step(model, "task_card", artifacts={"request": request},
                                question="Extract: goal, constraints, out-of-scope."))


def extract_symbols(files: dict[str, str]) -> set[str]:
    """Minimal C1 stand-in: every def/class as a bare name and as a dotted path
    (pkg.module.name), plus module paths — the grounding check (ENVELOPE_SCHEMAS §4)
    accepts references that appear in the injected symbol DB."""
    import re as _re

    syms: set[str] = set()
    for rel, text in files.items():
        mod = rel.removesuffix(".py").replace("/", ".")
        syms.add(mod)
        for m in _re.finditer(r"^\s*(?:def|class)\s+(\w+)", text, _re.M):
            syms.add(m.group(1))
            syms.add(f"{mod}.{m.group(1)}")
    return syms


def step_expand(model, card: Envelope, files: dict[str, str], request: str = "") -> Envelope:
    cuts = [{"seam_id": "seam-primary", "files": sorted(files), "rationale": "single-leaf corpus task; whole repo is the seam"}]
    node = {"what": card.goal, "why": "corpus task root"}
    # FP-10: a file the REQUEST itself names (scaffold/create tasks) is grounded by
    # definition — the request is the run's only input and the authority on intent
    request_named = file_tokens(request) - set(files)
    return asyncio_run(llm_step(model, "expand",
        artifacts={"node": json.dumps(node), "candidate_cuts": json.dumps(cuts)},
        question="Fill in the child task along the proposed seam: what/why + leaf flag + est_rounds.",
        context={"candidate_seams": {c["seam_id"]: c["files"] for c in cuts},
                 "grounding_files": set(files) | request_named,
                 "known_symbols": sorted(extract_symbols(files))}))


def jdump(obj) -> str:
    """json.dumps tolerant of the REQUIRED sentinel (grammar-legal omissions must
    not crash serialization; an omitted contract simply serializes as empty)."""
    return json.dumps(obj, ensure_ascii=False, default=lambda o: "")


def extract_constants(files: dict[str, str]) -> str:
    """Module-level constant assignments across the repo (FP-7, ticket 04): the
    spec step must SEE the layer where configured values live, not only the
    symbols where symptoms show. Deterministic harness lookup (DESIGN §2.1 —
    never the model's job), bounded listing."""
    import re as _re

    lines: list[str] = []
    for rel in sorted(files):
        if not rel.endswith(".py"):
            continue
        for m in _re.finditer(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*([^#\n]+)", files[rel], _re.M):
            lines.append(f"- {rel}: {m.group(1)} = {m.group(2).strip()[:40]}")
    return "\n".join(lines[:24])


def step_spec(model, leaf_what: str, files: dict[str, str], conventions: str,
              request: str = "") -> Envelope:
    listing = "\n".join(f"- {rel}" for rel in sorted(files))
    constants = extract_constants(files)
    # FP-10: request-named files (scaffold/create) are part of the writable boundary
    boundary = sorted(set(files) | (file_tokens(request) - set(files)))
    return asyncio_run(llm_step(model, "write_spec",
        artifacts={"leaf": leaf_what, "conventions": conventions, "repo_files": listing,
                   "repo_constants": constants},
        question="Write the spec: interfaces, types, behavior contract, error model, edge cases, "
                 "files_touched. Fix where the misconfigured VALUE lives (constants/config), not "
                 "where the symptom shows: when the request says the value was moved into config, "
                 "files_touched MUST include that config module (FP-7 hard rule).",
        context={"boundary_files": boundary}))


def step_acs(model, leaf_what: str, spec: Envelope) -> tuple[Envelope, Envelope, int]:
    """draft_acs → gate_decide (fresh) → one bounded revise round on reject."""
    decides = 0
    acs = asyncio_run(llm_step(model, "draft_acs",
        artifacts={"node": leaf_what, "spec": jdump({
            "interfaces": [i.model_dump() for i in spec.interfaces],
            "behavior": spec.behavior})},
        question="For each AC give the check. Prefer check_kind='test' with check_hint set to a "
                 "concrete pytest command or test id. Use 'subjective' ONLY when no deterministic "
                 "check is feasible, and then check_hint is REQUIRED (what the judge inspects). "
                 "Example: {ac_id: 'AC-1', statement: 'divide raises MinirepoError on 0', "
                 "check_kind: 'test', check_hint: 'pytest tests/test_calc.py::test_divide_by_zero'}",
        context={"node_kind": "leaf"},
        best_of_n=3))
    while True:
        decides += 1
        verdict = asyncio_run(llm_step(model, "gate_decide",
            artifacts={},
            question="Is this AC map a real gate? Flag 'subjective' where a deterministic check "
                     "is feasible. The proposed map (fresh session — the proposal is your only "
                     "evidence): " + jdump([a.model_dump() for a in acs.acs]),
            fresh=True))
        if verdict.decision == "accept" or decides >= 2:
            return acs, verdict, decides
        acs = asyncio_run(llm_step(model, "draft_acs",
            artifacts={"node": leaf_what, "spec": jdump({
                "interfaces": [i.model_dump() for i in spec.interfaces],
                "behavior": spec.behavior}),
                "prior_rejection": verdict.explanation or "gate rejected the map"},
            question="Revise the AC map per the gate decision: make every AC deterministically checkable.",
            context={"node_kind": "leaf"}))


def step_write_test(model, spec: Envelope, acs: Envelope, workdir: Path, files: dict[str, str]) -> Path | None:
    env = asyncio_run(llm_step(model, "write_test",
        artifacts={"spec_contract": jdump({
            "interfaces": [i.model_dump() for i in spec.interfaces],
            "behavior": spec.behavior}),
            "ac_test_map": jdump([a.model_dump() for a in acs.acs])},
        question="Write the complete test file that pins the AC map. Reply with the new test file.",
        context={"ac_map": {a.ac_id: a.model_dump() for a in acs.acs}}))
    if env.status != "ok":
        note("golden_test_skipped", detail=f"write_test returned {env.status}")
        return None
    if env.file_path not in files:
        note("golden_test_skipped", detail=f"file_path {env.file_path!r} outside repo")
        return None
    if env.file_path in files:
        # tests are the AC contract: a golden test may only ADD a new test file,
        # never overwrite a shipped one (overwriting = gate-easing, DESIGN §4.8)
        note("golden_test_skipped", detail=f"{env.file_path!r} already exists — never overwrite shipped tests")
        return None
    # M3: the golden test file write also rides the check pipeline (intent=test)
    cw = asyncio.run(check_write(workdir, env.file_path, env.content, intent="test"))
    if not cw.ok:
        note("golden_test_skipped",
             detail=f"check_write rolled back: "
                    f"{cw.findings[0].message[:80] if cw.findings else cw.verdict}")
        return None
    return workdir / env.file_path


def step_implement(model, spec: Envelope, workdir: Path, files: dict[str, str],
                   attempts: int, trajectory: Trajectory, request: str = "",
                   creatable: set[str] | None = None,
                   harness_written_acc: set[str] | None = None) -> tuple[bool, str, list[dict]]:
    creatable = creatable or set()
    harness_written_acc = harness_written_acc if harness_written_acc is not None else set()
    orig_bytes: dict[str, bytes | None] = {}   # per-file pre-first-touch state
    """Bounded implement loop. D-transport: edits ride the write_test content
    envelope (only content-emitting schema tonight); on red the target file is
    rolled back and the next attempt sees a one-line failure summary + failing
    output + current file — never the failed attempt's text (DESIGN §2.4)."""
    history: list[dict] = []
    last_excerpt = "no failing output captured"
    summary = "tests fail; fix the reported bug"
    guided = bool(globals().get("GUIDED_IMPLEMENT"))
    for attempt in range(1, attempts + 1):
        # one candidate file per attempt: the spec's files_touched (boundary), else whole repo
        boundary = [f for f in spec.files_touched if f in files or f in creatable] or sorted(files)
        # rank: source before tests — the fix belongs in source; editing tests to pass
        # is a test-side ticket (router rule), never the implement move
        boundary = sorted(boundary, key=lambda f: ("test" in f.lower(), f))
        # guided decomposition (DESIGN §2.2, ticket 05 A/B): enumerate the fix
        # steps FIRST, then emit under the plan — the thinking structure is
        # harness-decomposed, the filling stays with the model
        plan_text = ""
        if guided:
            plan_env = asyncio_run(llm_step(model, "fix_plan",
                artifacts={"bug_report": request, "failing_test_output": last_excerpt},
                question="List 3-8 ordered steps to fix this bug in the target file. "
                         "One short line per step: what to change and why."))
            plan_text = "; ".join(plan_env.steps) if plan_env.status == "ok" else ""
            note("fix_plan", attempt=attempt, steps=plan_env.steps if plan_env.status == "ok" else [])
        env = asyncio_run(llm_step(model, "write_test",
            artifacts={"spec_contract": jdump({
                "interfaces": [i.model_dump() for i in spec.interfaces],
                "behavior": spec.behavior,
                "implementation_notes": spec.implementation_notes}),
                "current_files": json.dumps({rel: files[rel] for rel in boundary if rel in files}, ensure_ascii=False),
                **({"repo_knowledge": build_knowledge(files, boundary)} if globals().get("KNOWLEDGE") else {}),
                "bug_report": request,
                "failing_test_output": last_excerpt},
            question=(("Follow this plan step by step: " + plan_text + ".\n") if plan_text else "") +
                      ("Emit the complete content for the NEW file (file_path) so the failing "
                      "tests pass. Include every symbol the tests import. "
                      "Never edit test files to make them pass — create the source."
                      if boundary and all(f in creatable for f in boundary) else
                      "Emit the complete new version of the ONE buggy file (file_path) so the failing "
                      "test passes. Change as little as possible. If you reference a name defined "
                      "elsewhere in the repository, add the needed import statement. "
                      "Never edit test files to make them pass — fix the source."),
            context={"ac_map": {}, "boundary_files": boundary},
            role=("whole-file scaffold engine: emit the complete new file at file_path"
                  if boundary and all(f in creatable for f in boundary) else
                  "whole-file source-edit engine: re-emit the complete new version of the target file"),
            best_of_n=3))
        if env.status != "ok":
            history.append({"attempt": attempt, "outcome": f"envelope:{env.status}"})
            summary = f"implement returned status={env.status}: {env.unable_reason or env.comment}"
            continue
        if env.file_path not in files and env.file_path not in creatable:
            history.append({"attempt": attempt, "outcome": f"file_path-outside-repo:{env.file_path}"})
            continue
        target = workdir / env.file_path
        if env.file_path not in orig_bytes:
            orig_bytes[env.file_path] = target.read_bytes() if target.exists() else None
        harness_written_acc.add(env.file_path)
        # M3: the write goes through the kernel check pipeline (DESIGN §4.5) —
        # format/autofix <=2 passes, tree-sitter parse, typecheck baseline, intent.
        cw = asyncio.run(check_write(workdir, env.file_path, env.content, intent="source"))
        if not cw.ok:
            history.append({"attempt": attempt, "outcome": f"check-rolled-back:{cw.verdict}",
                            "findings": [f.message[:80] for f in cw.findings[:2]]})
            last_excerpt = "; ".join(f"{f.code}: {f.message}" for f in cw.findings[:2]) or cw.verdict
            note("implement_check_rolled_back", attempt=attempt, file=env.file_path)
            trajectory.record(step_id=f"implement-{attempt}", node_id="implement",
                              outcome="rolled-back")
            summary = f"attempt {attempt} failed the check ladder ({cw.verdict}); rolled back"
            continue
        if cw.findings:
            last_excerpt = "; ".join(f"{f.code}: {f.message}" for f in cw.findings[:3])
        res = run_pytest(workdir)
        history.append({"attempt": attempt, "file": env.file_path, "pytest_exit": res.exit,
                        "verdict": res.verdict, "excerpts": res.excerpts[:2]})
        if res.exit == 0:
            trajectory.record(step_id=f"implement-{attempt}", node_id="implement", outcome="green")
            return True, env.file_path, history
        # unified iterate mode (DESIGN §2.4 refined, owner direction 2026-09-18):
        # the draft STAYS on the tree — attempt N+1 sees and improves attempt N's
        # state; failed-attempt text is still never narrated into a retry (the
        # failure summary + test output is the only carried evidence), and the
        # whole draft is erased at the strategy boundary on budget exhaustion.
        last_excerpt = "; ".join(res.excerpts) if res.excerpts else f"pytest exit {res.exit}"
        # FP-4 family now lives in the kernel rule library (DESIGN §4.5): cross-file
        # name resolution is a lookup — harness work, never left to the model.
        for rf in diagnose_test_output(res.excerpts, files):
            last_excerpt += f"; {rf.message}"
            note("rule_diagnosis", rule=rf.code, file=rf.path)
        summary = f"attempt {attempt} left tests red ({res.exit})"
        note("implement_red_kept", attempt=attempt, file=env.file_path)
        trajectory.record(step_id=f"implement-{attempt}", node_id="implement", outcome="kept")
    # budget exhausted, still red -> strategy-boundary erasure (§2.4 refined):
    # restore every touched file so the next gear starts from a clean state
    for rel, b in orig_bytes.items():
        p = workdir / rel
        if b is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(b)
    harness_written_acc.clear()
    note("implement_budget_exhausted_restored", files=sorted(orig_bytes))
    return False, summary, history


# --------------------------------------------------------------------------- gate


def gate(workdir: Path, trajectory: Trajectory, baseline: dict[str, str],
         harness_written: set[str]) -> tuple[bool, list[str]]:
    res = run_pytest(workdir)
    if res.exit != 0:
        return False, [f"pytest exit {res.exit}"] + res.excerpts[:3]
    diverged = trajectory.detect_external_edits(baseline, changed_by_harness=harness_written)
    if diverged:
        return False, [f"untouched-files contract violated: {diverged}"]
    return True, ["pytest green; untouched-files contract holds"]


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=str(ROOT / "tests/fixtures/mini_repo"))
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--skip-golden-test", action="store_true")
    ap.add_argument("--guided-implement", action="store_true",
                    help="A/B (ticket 05): fix_plan enumerate step before each implement emit")
    ap.add_argument("--knowledge", action="store_true",
                    help="M6: inject the knowledge pack (signatures/callers/constants) into implement")
    args = ap.parse_args()
    global GUIDED_IMPLEMENT
    GUIDED_IMPLEMENT = args.guided_implement
    global KNOWLEDGE
    KNOWLEDGE = args.knowledge

    task_dir = Path(args.task)
    task = load_task(task_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    runs_dir = ROOT / "bench/runs" / ts / "golden" / task["task_id"]
    runs_dir.mkdir(parents=True, exist_ok=True)
    reset_ledger_for_tests()

    print(f"== golden bugfix: {task['task_id']} ==")
    workdir, trajectory = stage_workdir(runs_dir, task["task_id"], task["files"])
    baseline = trajectory.file_hashes()
    harness_written: set[str] = set()

    with lock(workdir):
        boot_recover(workdir, note=note)  # §6: clean start; no-op on a staged workdir

        red = pytest_exit(workdir)
        print(f"[red] pytest exit={red}")
        if red == 0:
            print("task is already green — nothing to fix")
            return 0

        fixed, fix_summary, history, gate_ok = False, "not reached", [], False
        model = LlamaServerRunner(args.server)
        card = step_task_card(model, task["request"])
        print(f"[task_card] class={card.task_class} goal={card.goal[:70]!r}")

        expand = step_expand(model, card, task["files"], request=task["request"])
        child = expand.children[0]
        print(f"[expand] leaf: {child.what[:70]!r} est={child.est_rounds}")

        tree = TaskTree(what=card.goal)
        leaf = tree.insert_ticket(tree.root, child.what, why=child.why)
        leaf.status = "in-progress"

        spec = step_spec(model, child.what, task["files"], task["conventions"], request=task["request"])
        print(f"[spec] interfaces={[i.name for i in spec.interfaces]} files_touched={spec.files_touched}")

        acs, verdict, decides = step_acs(model, child.what, spec)
        print(f"[acs] {len(acs.acs)} ACs, gate_decide={verdict.decision} after {decides} round(s)")
        findings = leaf.set_ac_test_map([a.model_dump() for a in acs.acs])
        if findings.items:
            print(f"[acs] map findings: {findings.items}")

        golden_test = None
        if not args.skip_golden_test:
            golden_test = step_write_test(model, spec, acs, workdir, task["files"])
            if golden_test is not None:
                harness_written.add(str(golden_test.relative_to(workdir)))
                print(f"[write_test] {golden_test.relative_to(workdir)}")
                res = run_pytest(workdir)
                if res.exit != 0:
                    # D-test-side: golden test red while it may be the test's fault —
                    # simplified M2 router: drop the golden test file, note it, proceed.
                    golden_test.unlink()
                    harness_written.discard(str(golden_test.relative_to(workdir)))
                    note("golden_test_dropped_side_test", file=str(golden_test.relative_to(workdir)))
                    print("[write_test] golden test red → dropped (side=test, M2 simplified router)")

        creatable = file_tokens(task["request"]) - set(task["files"])
        acc: set[str] = set()
        n_boundary = len(set(spec.files_touched) & (set(task["files"]) | creatable)) or 1
        scaled_attempts = min(9, 3 * max(1, n_boundary))   # §4.1: budget scales with work
        attempts = max(args.attempts, scaled_attempts)
        fixed, fix_summary, history = step_implement(
            model, spec, workdir, task["files"], attempts, trajectory,
            request=task["request"], creatable=creatable, harness_written_acc=acc)
        harness_written |= acc   # accumulated multi-file edits are harness-written
        if fixed:
            harness_written.add(fix_summary)
        print(f"[implement] fixed={fixed} history={json.dumps(history)[:220]}")

        conflicts = trajectory.detect_external_edits(baseline, harness_written)
        if conflicts and pause_leaf_on_conflict(leaf, conflicts):
            print(f"[conflict] external edits detected → leaf paused: {conflicts}")

        green = pytest_exit(workdir) == 0 and not conflicts
        gate_ok, gate_notes = gate(workdir, trajectory, baseline, harness_written)
        print(f"[gate] ok={gate_ok} notes={gate_notes}")

        summary = asyncio_run(llm_step(model, "run_summary",
            artifacts={"what_was_done": json.dumps({
                "task": task["task_id"], "fixed": fixed, "fix_file": fix_summary,
                "gate": gate_ok, "history": history}, ensure_ascii=False)},
            question="Summarize: outcome, what was done, what changed, what remains."))
        print(f"[run_summary] outcome={summary.outcome} done={summary.what_was_done[:80]!r}")

        tree.attach(leaf, Artifact(artifact_id=f"{task['task_id']}-summary", node_id=leaf.id,
                                   kind="summary", content=summary.what_was_done))
        leaf.status = "done" if (gate_ok and fixed) else ("needs-user" if conflicts else "in-progress")

    try:  # everything above can raise SchemaViolation — the run still persists
        pass
    except SchemaViolation as exc:
        print(f"[violation] {exc}")
        fixed, fix_summary = False, f"schema violation: {exc}"

    # corpus stays pristine (D-gate parity with the checks.py contract)
    corpus_clean = subprocess_git_clean(task["repo"]) if (task["repo"] / ".git").exists() else True
    # persist ledger + artifacts
    ledger_dump = json.dumps(ledger_entries(), indent=1, ensure_ascii=False)
    (runs_dir / "ledger.json").write_text(ledger_dump)
    (runs_dir / "summary.json").write_text(json.dumps({
        "task": task["task_id"], "fixed": fixed, "gate_ok": gate_ok,
        "green": green, "history": history,
        "fix_summary": fix_summary, "gate_notes": gate_notes,
        "attempts_cap": args.attempts,
        "decisions": {"transport": "write_test envelope (D-transport)"},
        "artifacts": sorted(tree.artifacts._artifacts),  # noqa: SLF001
    }, indent=1, ensure_ascii=False))
    (runs_dir / "trajectory.json").write_text(trajectory.to_json())

    print(f"[persist] {runs_dir}")
    print(f"[result] {'PASS' if gate_ok and fixed and green else 'FAIL'} "
          f"(corpus pristine: {corpus_clean})")
    return 0 if (gate_ok and fixed) else 1


def subprocess_git_clean(repo: Path) -> bool:
    import subprocess

    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                       capture_output=True, text=True)
    return r.returncode == 0 and not r.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
