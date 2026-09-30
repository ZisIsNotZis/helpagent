#!/usr/bin/env python3
"""Blind v2 tree driver — stage source-only, run the budgeted tree, score externally.

Owner direction 2026-09-29 (DESIGN §6/§10). The corpus tests are the GRADER: they never
enter the run. This driver is the tree analogue of ``bench/v2_leaf.py``:

1. stages the task's *source-only* projection into a workdir (``stage_blind``),
2. builds the root :class:`harness.node.NodeSpec` from the request + ``extract_acs`` and
   runs :func:`harness.tree_run.run_tree` with the real model — the tree decomposes into
   leaves that each call :func:`harness.leaf.run_leaf` unchanged,
3. scores whatever the run produced on a OWN pristine copy via
   :func:`bench.external_score.external_score`,
4. prints the two facts that matter — what the run CLAIMED and what the grader FOUND —
   plus the resulting quadrant (DESIGN §10.8), and
5. persists one run record with the node tree, per-node budgets, stop reasons, the split
   history, and every integration verdict.

The independent attribution judge and the independent test are ON by default and passed
through to every leaf (``--no-judge`` / ``--no-iv`` to disable). ``grader_paths`` are
injected from the ROOT only, so no child can widen its withheld set.

Usage:
  uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading \
      --calls 48 --deadline-hours 6 [--no-judge] [--no-iv]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.blind_run import produced_files, quadrant  # noqa: E402
from bench.external_score import ExternalScore, external_score, untouched_paths  # noqa: E402
from bench.v2_leaf import (  # noqa: E402
    extract_acs,
    load_task,
    model_independent_test,
    model_judge,
    model_review,
)
from harness.budget import Budget, default_deadline  # noqa: E402
from harness.model import LlamaServerRunner  # noqa: E402
from harness.node import (  # noqa: E402
    MIN_LEAF_CALLS,
    MIN_LEAF_CALLS_WITH_JUDGE,
    NodeSpec,
)
from harness.staging import excluded_paths, source_only, stage_blind  # noqa: E402
from harness.tree import TaskTree  # noqa: E402
from harness.tree_run import NodeOutcome, TreeOutcome, run_tree  # noqa: E402

__all__ = ["build_parser", "build_record", "build_root", "main", "node_record", "run_once"]

DEFAULT_SERVER = "http://127.0.0.1:8833"


def build_root(task: dict) -> tuple[NodeSpec, tuple[str, ...]]:
    """The blind root contract + the withheld grader set.

    The root's write boundary is every SOURCE file (the tree narrows it per child); its
    ACs are the extracted task requirements — cross-child integration criteria, which the
    tree puts in a dedicated integration leaf. ``grader_paths`` is the same definition
    ``bench/v2_leaf.build_spec`` uses (staged-owned paths ∪ the task's ``UNTOUCHED`` list),
    injected from the root so no child can widen it.
    """
    frozen = untouched_paths(Path(task["task_dir"])) if task.get("task_dir") else set()
    grader_paths = tuple(sorted(set(excluded_paths(task["files"])) | frozen))
    source = source_only(task["files"])
    root = NodeSpec(
        goal=task["request"],
        files=tuple(sorted(source)),
        acs=tuple(extract_acs(task["request"])),
        interfaces=(),
        kind="internal",
        est_calls=1,
    )
    return root, grader_paths


def node_record(outcome: NodeOutcome) -> dict:
    """One node's persisted facts (recursively) — the tree, stop reasons, and verdicts."""
    leaf = outcome.leaf
    return {
        "node": outcome.node_id,
        "claimed": outcome.claimed,
        "stop_reason": outcome.stop_reason,
        "calls": outcome.calls,
        "wall_s": outcome.wall_s,
        "leaf_signal": (leaf.signal if leaf is not None else None),
        "leaf_stop_reason": (leaf.stop_reason if leaf is not None else None),
        "self_test": (leaf.self_test if leaf is not None else None),
        # Ticket 19: the leaf's claim basis, verification basis, review verdicts, coverage
        # results, declared-case problems, attribution labels, and needs-user flag.
        "claimed_basis": (leaf.claimed_basis if leaf is not None else None),
        "verification_basis": (leaf.verification_basis if leaf is not None else None),
        "needs_user": (leaf.needs_user if leaf is not None else False),
        "review_verdicts": ([dataclasses.asdict(v) for v in leaf.review_verdicts]
                            if leaf is not None else []),
        "coverage": ([dataclasses.asdict(c) for c in leaf.coverage]
                     if leaf is not None else []),
        "coverage_missing": (list(leaf.coverage_missing) if leaf is not None else []),
        "coverage_unresolved": (list(leaf.coverage_unresolved) if leaf is not None else []),
        "test_case_problems": (list(leaf.test_case_problems) if leaf is not None else []),
        "malformed_steps": (list(leaf.malformed_steps) if leaf is not None else []),
        "judge_verdicts": ([v.model_dump(mode="json") for v in leaf.judge_verdicts]
                           if leaf is not None else []),
        "integration_verdicts": dict(outcome.integration_verdicts),
        "close_rule": outcome.close_rule,
        "integration_reopen_rounds": outcome.integration_reopen_rounds,
        "boundary_audit": (outcome.boundary_audit.to_dict()
                           if outcome.boundary_audit is not None else None),
        "reset_to": outcome.reset_to,
        "resplit_rounds": outcome.resplit_rounds,
        "respec_rounds": outcome.respec_rounds,
        "children": [node_record(c) for c in outcome.children],
    }


def build_record(task_id: str, goal: str, outcome: TreeOutcome, *, withheld: list[str],
                 produced: dict[str, str], score: ExternalScore, quad: str,
                 run_wall_s: float, judge_enabled: bool, iv_enabled: bool,
                 review_enabled: bool, acs: list[str]) -> dict:
    """Assemble the persisted run record (nodes, budgets, stop reasons, split history)."""
    return {
        "task": task_id,
        "goal": goal,
        "acs": list(acs),
        "withheld_grader_paths": withheld,
        "judge": judge_enabled,
        "iv": iv_enabled,
        "review": review_enabled,
        "claimed": outcome.claimed,
        "actual": score.passed,
        "quadrant": quad,
        "calls": outcome.calls,
        "tree_wall_s": outcome.wall_s,
        "run_wall_s": run_wall_s,
        "budget": outcome.budget.to_dict(),
        "checkpoints": dict(outcome.checkpoints),
        "split_history": {
            node: [dataclasses.asdict(attempt) for attempt in attempts]
            for node, attempts in outcome.split_history.items()
        },
        "nodes": node_record(outcome.root),
        "produced": sorted(produced),
        "grader_exit": score.exit,
        "grader_notes": score.notes[-6:],
        "grader_restored": score.restored,
        "grader_shadowed": score.shadowed,
        "grader_report_gate": (dataclasses.asdict(score.report_gate)
                               if score.report_gate is not None else None),
    }


def run_once(task_dir: Path, out_dir: Path, server: str, calls: int,
             deadline_hours: float, use_judge: bool = True, use_iv: bool = True,
             use_review: bool = True) -> dict:
    task = load_task(task_dir)
    root, grader_paths = build_root(task)

    workdir = out_dir / "work"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    withheld = stage_blind(workdir, task["files"])

    budget = Budget(calls=calls,
                    deadline_ts=default_deadline(time.time(), deadline_hours * 3600))
    model = LlamaServerRunner(server)
    judge = (lambda request: model_judge(model, request)) if use_judge else None
    iv = (lambda request: model_independent_test(model, request)) if use_iv else None
    review = (lambda request: model_review(model, request)) if use_review else None
    # The higher per-leaf floor when the independent machinery is on (design §2).
    min_leaf_calls = (MIN_LEAF_CALLS_WITH_JUDGE if (use_judge and use_iv)
                      else MIN_LEAF_CALLS)

    tree = TaskTree(what=root.goal, why="blind v2 tree run", files=list(root.files))
    started = time.monotonic()
    outcome = asyncio.run(run_tree(
        model, root, tree, workdir, budget, root_grader_paths=grader_paths,
        judge=judge, iv=iv, review=review, min_leaf_calls=min_leaf_calls))
    wall = round(time.monotonic() - started, 1)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(outcome.claimed, score.passed)

    record = build_record(
        task["task_id"], root.goal, outcome, withheld=withheld, produced=produced,
        score=score, quad=quad, run_wall_s=wall, judge_enabled=use_judge,
        iv_enabled=use_iv, review_enabled=use_review, acs=list(root.acs))

    print(f"== v2 tree: {task['task_id']} ==")
    print(f"[judge]  {'on' if use_judge else 'off (conservative baseline)'}")
    print(f"[iv]  {'on' if use_iv else 'off (own-test basis)'} "
          f"min_leaf_calls={min_leaf_calls}")
    print(f"[acs]  {len(root.acs)} extracted from the request")
    print(f"[claim]  claimed={outcome.claimed} root={outcome.root.stop_reason} "
          f"calls={outcome.calls} budget_left={outcome.budget.calls}")
    print(f"[actual] grader_passed={score.passed} exit={score.exit}")
    print(f"[quadrant] {quad}  (tree_wall={outcome.wall_s}s run_wall={wall}s)")
    return record


def build_parser() -> argparse.ArgumentParser:
    """The CLI parser, exposed so the judge/iv defaults can be pinned by a test."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="corpus task dir (has repo/)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--calls", type=int, default=48)
    parser.add_argument("--deadline-hours", type=float, default=6.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--judge", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent attribution judge per leaf (default ON)")
    parser.add_argument("--iv", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent test per leaf (default ON)")
    parser.add_argument("--review", action=argparse.BooleanOptionalAction, default=True,
                        help="run the mandatory review verification per leaf (default ON)")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    task_dir = Path(args.task)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"v2tree-{ts}" / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    record = run_once(task_dir, out_dir, args.server, args.calls, args.deadline_hours,
                      use_judge=args.judge, use_iv=args.iv, use_review=args.review)
    record_path = out_dir / "run.json"
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(f"[persist] {record_path}")
    return 0 if record["quadrant"] == "true-success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
