#!/usr/bin/env python3
"""Blind v2 leaf driver — stage source-only, run the leaf, score externally.

Owner direction 2026-09-29 (DESIGN §6/§10). The corpus tests are the GRADER: they
never enter the run. This driver

1. stages the task's *source-only* projection into a workdir (``stage_blind``),
2. runs :func:`harness.leaf.run_leaf` with the real model and the leaf's own tests,
3. scores whatever the run produced on a OWN pristine copy via
   :func:`bench.external_score.external_score`,
4. prints the two facts that matter — what the run CLAIMED and what the grader
   FOUND — plus the resulting quadrant (DESIGN §10.7), and
5. persists one run record (JSON) with the claim, the verdict, the quadrant, and
   the cost counters.

The independent attribution judge is ON by default (ticket 17 round 3): a fresh-context
model call that attributes a red failure to implementation / tests / spec / environment,
never seeing a grader path. Pass ``--no-judge`` for the conservative baseline where a
model's own "the test is wrong" claim is never credited. Round 4 adds a second
independent call: a fresh-context FALSIFIER (default ON, ``--no-falsify`` to disable)
that must fail to REFUTE the finished candidate before the run may claim. The record says
which modes ran (``judge``, ``falsify``) and carries every judge verdict and falsifier
verdict, raw and coerced.

Usage:
  uv run python bench/v2_leaf.py --task bench/corpus/T-31-parameter-threading \
      --calls 24 --deadline-hours 6 [--no-judge] [--no-falsify]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.blind_run import produced_files, quadrant  # noqa: E402
from bench.external_score import (  # noqa: E402
    ExternalScore,
    external_score,
    untouched_paths,
)
from harness.budget import Budget, default_deadline  # noqa: E402
from harness.gate_report import JUNIT_FAMILY_ARGS  # noqa: E402
from harness.leaf import (  # noqa: E402
    FalsifyRequest,
    FalsifyVerdict,
    JudgeRequest,
    JudgeVerdict,
    LeafOutcome,
    LeafSpec,
    run_leaf,
)
from harness.model import LlamaServerRunner  # noqa: E402
from harness.runner import llm_step  # noqa: E402
from harness.staging import (  # noqa: E402
    PYTEST_ISOLATION_ARGS,
    PYTEST_ISOLATION_ENV,
    excluded_paths,
    source_only,
    stage_blind,
)

__all__ = ["build_parser", "build_record", "build_spec", "load_task", "main",
           "model_falsifier", "model_judge", "quadrant", "run_once"]

DEFAULT_SERVER = "http://127.0.0.1:8833"

#: debug_judge ``blame`` → the judge's attribution domain. ``both`` is coerced to
#: implementation (conservative: an ambiguous blame is never credited to the test).
_JUDGE_ATTRIBUTION = {"code": "implementation", "test": "tests", "spec": "spec",
                     "both": "implementation"}


def load_task(task_dir: Path) -> dict:
    """Load the task repo + request. Test files ARE loaded here so the grader set
    can be identified, but they are withheld from the run by ``build_spec``."""
    task_dir = Path(task_dir)
    repo = task_dir / "repo" if (task_dir / "repo").exists() else task_dir
    files = {
        str(p.relative_to(repo)): p.read_text()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    request_path = task_dir / "request.md"
    request = request_path.read_text() if request_path.exists() else (
        "Fix the reported behaviour so the project's own conventions hold."
    )
    return {"task_id": task_dir.name, "task_dir": str(task_dir),
            "request": request, "files": files}


def build_spec(task: dict) -> LeafSpec:
    """The blind leaf contract: source only in ``files``, grader paths withheld.

    ``grader_paths`` is the UNION of the staged-owned paths (every test path / test
    infrastructure path :func:`harness.staging.owned_paths` owns) and the corpus task's
    own ``UNTOUCHED`` list from ``checks.py`` (ticket 17 F2). Before this fix the leaf
    guarded only ``owned_paths`` while the grader also restored ``UNTOUCHED``, so a run
    could green by writing a frozen source file (``api/__init__.py``) that the grader
    then restored — a false success. One definition, used by both sides.
    """
    frozen = untouched_paths(Path(task["task_dir"])) if task.get("task_dir") else set()
    grader_paths = tuple(sorted(set(excluded_paths(task["files"])) | frozen))
    return LeafSpec(
        goal=task["request"],
        files=source_only(task["files"]),
        acs=[],
        interfaces=[],
        grader_paths=grader_paths,
    )


def build_record(task_id: str, goal: str, outcome: LeafOutcome, *, withheld: list[str],
                 produced: dict[str, str], score: ExternalScore, quad: str,
                 run_wall_s: float, judge_enabled: bool = False,
                 falsify_enabled: bool = False) -> dict:
    """Assemble the persisted run record. One place, so the JSON that lands in
    ``run.json`` and the shape the tests pin cannot drift apart — including the
    wasted escalations that used to live only in the process-global ledger, every
    judge verdict (raw + coerced), every falsifier verdict, the claim basis, the
    grader restores/shadow refusals that neutralized run tampering, the leaf's own
    write-guard refusals, the gate report anomalies, the machine-readable grader
    report gate (ticket 17 F1), and the interpreter isolation applied to both pytest
    runs."""
    return {
        "task": task_id,
        "goal": goal,
        "withheld_grader_paths": withheld,
        "judge": judge_enabled,
        "falsify": falsify_enabled,
        "claimed": outcome.claimed,
        "claimed_basis": outcome.claimed_basis,
        "actual": score.passed,
        "quadrant": quad,
        "signal": outcome.signal,
        "stop_reason": outcome.stop_reason,
        "exhausted": outcome.exhausted,
        "exhaustion_reason": outcome.exhaustion_reason,
        "self_test": outcome.self_test,
        "own_test_mutated": outcome.own_test_mutated,
        "test_rewrites": outcome.test_rewrites,
        "needs_parent": outcome.needs_parent,
        "calls": outcome.calls,
        "wall_s": outcome.wall_s,
        "run_wall_s": run_wall_s,
        "layers_used": outcome.layers_used,
        "wasted_escalations": [dataclasses.asdict(w) for w in outcome.wasted_escalations],
        "judge_verdicts": [v.model_dump(mode="json") for v in outcome.judge_verdicts],
        "falsify_verdicts": [dataclasses.asdict(v) for v in outcome.falsify_verdicts],
        "falsify_counterexample": outcome.falsify_counterexample,
        "attempts": [a.model_dump(mode="json") for a in outcome.attempts],
        "questions": [q.model_dump(mode="json") for q in outcome.questions],
        "grader_exit": score.exit,
        "grader_notes": score.notes[-6:],
        "grader_restored": score.restored,
        "grader_shadowed": score.shadowed,
        # Ticket 17 F1: the machine-readable report gate on the grader copy, and the
        # flag that says the corpus exit status and the report disagreed.
        "grader_report_gate": (dataclasses.asdict(score.report_gate)
                               if score.report_gate is not None else None),
        "grader_suspected_contaminated_grade": score.suspected_contaminated_grade,
        "gate_anomalies": outcome.gate_anomalies,
        "refusals": outcome.refusals,
        # Interpreter isolation (ticket 17 round 5) and the report policy (round 6):
        # both the leaf's own pytest and the grader's pytest run the same env/args,
        # and both gate on a report in a private directory outside the repo.
        "isolation": {
            "env": dict(PYTEST_ISOLATION_ENV),
            "pytest_args": list(PYTEST_ISOLATION_ARGS),
            "report_args": list(JUNIT_FAMILY_ARGS),
            "report_dir": "private mkdtemp outside the repository",
            "canary": "per-run random token in the generated canary node id",
            "grader_env": score.isolation,
        },
        "produced": sorted(produced),
        "applied": score.applied,
        "skipped": score.skipped,
    }


def _judge_question(request: JudgeRequest) -> str:
    """The fresh-context judge prompt. With ``fresh=True`` the runner injects no
    artifacts, so the evidence rides the question verbatim (DESIGN §2.4 / §10.1)."""
    acs = "\n".join(f"- {a}" for a in request.acs) or "- (none given)"
    files = "\n".join(f"--- {rel} ---\n{text}" for rel, text in sorted(request.files.items()))
    return (
        "You are an INDEPENDENT judge attributing a red test failure. You did not write "
        "the source and you did not write the test.\n"
        f"GOAL:\n{request.goal}\n\n"
        f"ACCEPTANCE CRITERIA:\n{acs}\n\n"
        f"THE RUN'S OWN TEST ({request.test_path or 'none'}):\n{request.test_content}\n\n"
        f"FAILING TEST OUTPUT:\n{request.failure}\n\n"
        f"CURRENT SOURCE FILES:\n{files}\n\n"
        "Decide whether the failure is caused by the code, the test, the spec, or the "
        "environment. Put the CONCRETE defect in one sentence in 'problem'. If you blame "
        "the test, name the failing test function or quote the exact "
        "assertion/expectation you believe is wrong."
    )


async def model_judge(model: Any, request: JudgeRequest) -> JudgeVerdict:
    """The driver's DEFAULT judge: a FRESH-CONTEXT model call (DESIGN §10.1 step 5).

    It sees only the run's own evidence — goal, ACs, the run's own test, the failing
    output, and the blind source view — never a grader path. It reuses the existing
    §16 ``debug_judge`` envelope (no new schema); an ``unable`` envelope is read as an
    environment attribution. The deterministic filter in
    :func:`harness.leaf.apply_judge_filter` is applied by the leaf, not here.
    """
    env = await llm_step(model, "debug_judge", artifacts={},
                         question=_judge_question(request), fresh=True)
    # The envelope's unset (unable-branch) payload fields hold the REQUIRED sentinel,
    # which pydantic cannot serialize — keep the raw verdict as plain JSON fields.
    raw = json.dumps({
        "status": env.status,
        "comment": getattr(env, "comment", ""),
        "blame": getattr(env, "blame", "") if isinstance(getattr(env, "blame", ""), str) else "",
        "problem": (getattr(env, "problem", "") if isinstance(getattr(env, "problem", ""), str) else ""),
        "unable_reason": env.unable_reason or "",
    }, ensure_ascii=False)
    if env.status == "unable":
        return JudgeVerdict(attribution="environment",
                            defect=(env.unable_reason or "").strip(), raw=raw)
    attribution = _JUDGE_ATTRIBUTION.get(getattr(env, "blame", ""), "implementation")
    return JudgeVerdict(attribution=attribution,
                        defect=getattr(env, "problem", "") or "", raw=raw)


def _falsify_question(request: FalsifyRequest) -> str:
    """The fresh-context falsifier prompt. With ``fresh=True`` the runner injects no
    artifacts, so the evidence rides the question verbatim (DESIGN §2.4 / §10.1 step 5).
    It is asked to REFUTE; it sees no grader path."""
    acs = "\n".join(f"- {a}" for a in request.acs) or "- (none given)"
    return (
        "You are an INDEPENDENT FALSIFIER. You did not write the fix and you did not "
        "write its test. Your job is to REFUTE the candidate: construct a SPECIFIC input "
        "or observation (a concrete call and its wrong result, or an exact counterexample "
        "to an acceptance criterion) showing the goal is NOT met. BOTH the fix and its "
        "self-test may be wrong — trust neither.\n"
        f"GOAL:\n{request.goal}\n\n"
        f"ACCEPTANCE CRITERIA:\n{acs}\n\n"
        f"THE RUN'S OWN TEST ({request.test_path or 'none'}):\n{request.test_content}\n\n"
        f"FINAL SOURCE DIFF (baseline -> candidate):\n{request.diff or '(none)'}\n\n"
        "Answer with decision='reject' and the concrete counterexample in 'explanation' "
        "whenever you can refute the candidate. Answer with decision='accept' ONLY when "
        "you cannot construct any counterexample. If you cannot check, answer 'unable' "
        "with a reason — that is NOT an approval."
    )


async def model_falsifier(model: Any, request: FalsifyRequest) -> FalsifyVerdict:
    """The driver's DEFAULT falsifier: a FRESH-CONTEXT model call asked to refute the
    fix (ticket 17 round 4). It sees only the blind evidence — goal, ACs, the run's own
    test, and the source diff — never a grader path. It reuses the §20 ``gate_decide``
    envelope (no new schema): ``accept`` approves, ``reject`` carries the counterexample
    in ``explanation``, and an ``unable`` envelope is NOT an approval."""
    env = await llm_step(model, "gate_decide", artifacts={},
                         question=_falsify_question(request), fresh=True)

    def _text(field: str) -> str:
        value = getattr(env, field, "")
        return value if isinstance(value, str) else ""

    raw = json.dumps({
        "status": env.status,
        "comment": _text("comment"),
        "decision": _text("decision"),
        "explanation": _text("explanation"),
        "unable_reason": env.unable_reason or "",
    }, ensure_ascii=False)
    if env.status == "unable":
        return FalsifyVerdict(approved=False,
                              counterexample=(env.unable_reason or "").strip(), raw=raw)
    if _text("decision") == "accept":
        return FalsifyVerdict(approved=True, raw=raw)
    return FalsifyVerdict(approved=False, counterexample=_text("explanation"), raw=raw)


def run_once(task_dir: Path, out_dir: Path, server: str, calls: int,
             deadline_hours: float, use_judge: bool = True,
             use_falsify: bool = True) -> dict:
    task = load_task(task_dir)
    spec = build_spec(task)

    workdir = out_dir / "work"
    if workdir.exists():
        import shutil

        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    withheld = stage_blind(workdir, task["files"])

    budget = Budget(calls=calls, deadline_ts=default_deadline(time.time(), deadline_hours * 3600))
    model = LlamaServerRunner(server)
    # Default ON: a fresh-context attribution judge. --no-judge is the conservative
    # baseline where the model's own "the test is wrong" claim is never credited.
    judge = (lambda request: model_judge(model, request)) if use_judge else None
    # Default ON: a fresh-context falsifier that must fail to REFUTE the fix before any
    # claim. --no-falsify is the own-test-only basis (claimed_basis="own-test").
    falsifier = (lambda request: model_falsifier(model, request)) if use_falsify else None
    started = time.monotonic()
    outcome = asyncio.run(run_leaf(model, spec, workdir, budget, judge=judge,
                                   falsifier=falsifier))
    wall = round(time.monotonic() - started, 1)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(outcome.claimed, score.passed)

    record = build_record(
        task["task_id"], spec.goal, outcome, withheld=withheld, produced=produced,
        score=score, quad=quad, run_wall_s=wall, judge_enabled=use_judge,
        falsify_enabled=use_falsify)

    print(f"== v2 leaf: {task['task_id']} ==")
    print(f"[judge]  {'on' if use_judge else 'off (conservative baseline)'} "
          f"({len(outcome.judge_verdicts)} verdict(s))")
    print(f"[falsify]  {'on' if use_falsify else 'off (own-test basis)'} "
          f"({len(outcome.falsify_verdicts)} verdict(s))")
    print(f"[claim]  claimed={outcome.claimed} basis={outcome.claimed_basis} "
          f"signal={outcome.signal} stop={outcome.stop_reason or 'n/a'} "
          f"exhausted={outcome.exhausted} ({outcome.exhaustion_reason or 'n/a'})")
    print(f"[actual] grader_passed={score.passed} exit={score.exit} "
          f"suspected_contaminated={score.suspected_contaminated_grade}")
    print(f"[quadrant] {quad}  (calls={outcome.calls} wall={outcome.wall_s}s)")
    print(f"[self_test] {outcome.self_test or 'none'}  withheld={len(withheld)} grader path(s)")
    return record


def build_parser() -> argparse.ArgumentParser:
    """The CLI parser, exposed so the judge/falsify defaults can be pinned by a test."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="corpus task dir (has repo/)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--deadline-hours", type=float, default=6.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--judge", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent attribution judge (default ON); "
                             "--no-judge for the conservative baseline")
    parser.add_argument("--falsify", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent refutation pass (default ON); "
                             "--no-falsify for the own-test-only claim basis")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    task_dir = Path(args.task)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"v2leaf-{ts}" / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    record = run_once(task_dir, out_dir, args.server, args.calls, args.deadline_hours,
                      use_judge=args.judge, use_falsify=args.falsify)
    record_path = out_dir / "run.json"
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(f"[persist] {record_path}")
    return 0 if record["quadrant"] == "true-success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
