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

Usage:
  uv run python bench/v2_leaf.py --task bench/corpus/T-31-parameter-threading \
      --calls 24 --deadline-hours 6
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.blind_run import produced_files, quadrant  # noqa: E402
from bench.external_score import ExternalScore, external_score  # noqa: E402
from harness.budget import Budget, default_deadline  # noqa: E402
from harness.leaf import LeafOutcome, LeafSpec, run_leaf  # noqa: E402
from harness.model import LlamaServerRunner  # noqa: E402
from harness.staging import excluded_paths, source_only, stage_blind  # noqa: E402

__all__ = ["build_record", "build_spec", "load_task", "main", "quadrant", "run_once"]

DEFAULT_SERVER = "http://127.0.0.1:8833"


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
    return {"task_id": task_dir.name, "request": request, "files": files}


def build_spec(task: dict) -> LeafSpec:
    """The blind leaf contract: source only in ``files``, grader paths withheld."""
    grader_paths = tuple(excluded_paths(task["files"]))
    return LeafSpec(
        goal=task["request"],
        files=source_only(task["files"]),
        acs=[],
        interfaces=[],
        grader_paths=grader_paths,
    )


def build_record(task_id: str, goal: str, outcome: LeafOutcome, *, withheld: list[str],
                 produced: dict[str, str], score: ExternalScore, quad: str,
                 run_wall_s: float) -> dict:
    """Assemble the persisted run record. One place, so the JSON that lands in
    ``run.json`` and the shape the tests pin cannot drift apart — including the
    wasted escalations that used to live only in the process-global ledger."""
    return {
        "task": task_id,
        "goal": goal,
        "withheld_grader_paths": withheld,
        "claimed": outcome.claimed,
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
        "attempts": [a.model_dump(mode="json") for a in outcome.attempts],
        "questions": [q.model_dump(mode="json") for q in outcome.questions],
        "grader_exit": score.exit,
        "grader_notes": score.notes[-6:],
        "produced": sorted(produced),
        "applied": score.applied,
        "skipped": score.skipped,
    }


def run_once(task_dir: Path, out_dir: Path, server: str, calls: int,
             deadline_hours: float) -> dict:
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
    started = time.monotonic()
    outcome = asyncio.run(run_leaf(model, spec, workdir, budget))
    wall = round(time.monotonic() - started, 1)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(outcome.claimed, score.passed)

    record = build_record(
        task["task_id"], spec.goal, outcome, withheld=withheld, produced=produced,
        score=score, quad=quad, run_wall_s=wall)

    print(f"== v2 leaf: {task['task_id']} ==")
    print(f"[claim]  claimed={outcome.claimed} signal={outcome.signal} "
          f"stop={outcome.stop_reason or 'n/a'} exhausted={outcome.exhausted} "
          f"({outcome.exhaustion_reason or 'n/a'})")
    print(f"[actual] grader_passed={score.passed} exit={score.exit}")
    print(f"[quadrant] {quad}  (calls={outcome.calls} wall={outcome.wall_s}s)")
    print(f"[self_test] {outcome.self_test or 'none'}  withheld={len(withheld)} grader path(s)")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="corpus task dir (has repo/)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--deadline-hours", type=float, default=6.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    task_dir = Path(args.task)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"v2leaf-{ts}" / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    record = run_once(task_dir, out_dir, args.server, args.calls, args.deadline_hours)
    record_path = out_dir / "run.json"
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(f"[persist] {record_path}")
    return 0 if record["quadrant"] == "true-success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
