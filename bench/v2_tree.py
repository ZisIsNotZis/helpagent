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

The MODEL-BACKED MANAGING CALL is wired in too (ticket 20 step 2b-ii, ``--no-manager`` to
disable): when a How fails the node's structured record drives a fresh-context decision
out of the closed four, so a failed How can lead to a new How or a feasibility review
instead of parking immediately. The manager falls back to the safe ``escalate-or-park``
when the model is unavailable.

Usage:
  uv run python bench/v2_tree.py --task bench/corpus/T-31-parameter-threading \
      --calls 48 --deadline-hours 6 [--no-judge] [--no-iv] [--how-explore N]

The How axis is GREEDY by default (ticket 20 step 2c, ``--how-explore 1``): a node plans
its Hows, takes the top-ranked one, and funds that single candidate. Greedy is
SEQUENTIAL, not inert (ticket 20 step 2d): a failed How still goes to the manager, so
``continue-with-next-how`` abandons the current candidate and tries the next untried How
in a fresh copy and ``author-a-new-how`` appends and tries a new one (bounded by a small
constant and the budget; the count is recorded as ``sequential_attempts``).
``--how-explore N`` with ``N > 1`` restores the PARALLEL tournament (open up to N
candidates and pick a winner with the picker).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import shutil
import sys
import time
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.blind_run import produced_files, quadrant, verified_quadrant  # noqa: E402
from bench.external_score import ExternalScore, external_score, untouched_paths  # noqa: E402
from bench.v2_leaf import (  # noqa: E402
    extract_acs,
    load_task,
    model_independent_test,
    model_judge,
    model_review,
)
from harness.budget import Budget, default_deadline  # noqa: E402
from harness.how import (  # noqa: E402
    MANAGER_DECISIONS,
    ManagerDecision,
    ManagerUnavailable,
    NodeRecordView,
)
from harness.leaf import covenant_diluted  # noqa: E402
from harness.model import LlamaServerRunner  # noqa: E402
from harness.runner import llm_step  # noqa: E402
from harness.node import (  # noqa: E402
    MIN_LEAF_CALLS,
    MIN_LEAF_CALLS_WITH_JUDGE,
    NodeSpec,
)
from harness.staging import excluded_paths, source_only, stage_blind  # noqa: E402
from harness.tree import TaskTree  # noqa: E402
from harness.tree_run import NodeOutcome, TreeOutcome, run_tree  # noqa: E402

__all__ = ["build_parser", "build_record", "build_root", "main", "model_manager",
           "node_record", "run_once"]

DEFAULT_SERVER = "http://127.0.0.1:8833"


def _manager_question(record: NodeRecordView) -> str:
    """The managing call's prompt: the node's STRUCTURED RECORD, never its chat memory.

    It carries the How list with statuses, the current and untried Hows, every failure's
    evidence and reason, and the test deviations observed so far. ``fresh=True`` means the
    runner injects no author-context artifacts, so the record rides the question verbatim.
    """
    hows = "\n".join(
        f"- {h.id} (rank {h.rank}, status {h.status}): {h.text} [why: {h.reason}]"
        for h in record.hows) or "(no Hows)"
    failures = "\n".join(
        f"- {f.how_id}: reason={f.reason}; evidence={f.evidence}"
        for f in record.failures) or "(none)"
    untried = ", ".join(record.untried) or "(none)"
    selections = "\n".join(
        f"- {how_id}: score(tests={sel.test_covered}/{sel.test_pass_rate:.2f}, "
        f"review={sel.review_score}, rank={sel.rank}, cost={sel.cost})"
        for how_id, sel in record.selections) or "(none closed)"
    deviations = "\n".join(f"- {d}" for d in record.deviations) or "(none)"
    return (
        "You are the MANAGING AGENT for ONE node of a work tree. You see ONLY the "
        "node's STRUCTURED RECORD below --- no chat history and no conversation. A How "
        "(an approach) failed or exhausted. Decide the node's NEXT move, exactly one of:\n"
        "- continue-with-next-how: try the next untried How;\n"
        "- author-a-new-how: the existing Hows are exhausted or wrong; append a NEW How;\n"
        "- request-feasibility-review: have the plan-level review judge a How's "
        "feasibility before spending more;\n"
        "- escalate-or-park: stop and hand the node back to the owner.\n"
        f"NODE: {record.node_id}\n"
        f"HOWS:\n{hows}\n"
        f"CURRENT HOW: {record.current_how_id or '(none)'}\n"
        f"UNTRIED HOWS: {untried}\n"
        f"CANDIDATE SELECTIONS:\n{selections}\n"
        f"FAILURES:\n{failures}\n"
        "TEST DEVIATIONS (extra tests beyond the declared plan; they never score):\n"
        f"{deviations}\n"
        "A decision is an ACTION, never evidence. Give the decision and a REQUIRED "
        "reason that names the concrete How and the concrete failure or deviation that "
        "drove it.\n"
        "Reply with envelope status 'ok' (NOT blocked/unable) and the REQUIRED decision "
        "and reason fields; a non-ok status is a manager that did not decide."
    )


async def model_manager(model: Any, record: NodeRecordView) -> ManagerDecision:
    """The driver's DEFAULT managing call (ticket 20 step 2b-ii): a FRESH-CONTEXT model
    call over the node's structured record.

    It sees no chat history and no conversation --- only the How list with statuses, each
    failure's evidence and reason, the untried Hows, and any test deviations --- and
    returns ONE decision plus a reason out of exactly the four
    (:data:`harness.how.MANAGER_DECISIONS`).

    A non-``ok`` envelope status (the model NOT deciding) or an unusable payload raises
    :class:`harness.how.ManagerUnavailable`: that is not a decision, so the runner records
    it as ``manager_unavailable`` and parks (ticket 20 step 2b-iii). A model-call failure
    (the call itself raising) falls back to the SAFE default ``escalate-or-park``.
    """
    try:
        env = await llm_step(model, "manager_decision", artifacts={},
                             question=_manager_question(record), fresh=True)
    except Exception as exc:  # noqa: BLE001 --- a model failure must never crash the node
        return ManagerDecision(
            "escalate-or-park",
            f"the managing call was unavailable ({type(exc).__name__}: {exc}); "
            "parking conservatively")
    if env.status != "ok":
        # A blocked/unable envelope is the manager FAILING TO DECIDE, not a decision.
        raise ManagerUnavailable(
            f"the managing call returned status={env.status!r}, not a decision")
    decision = getattr(env, "decision", "")
    reason = getattr(env, "reason", "")
    if (not isinstance(decision, str) or decision not in MANAGER_DECISIONS
            or not isinstance(reason, str) or not reason.strip()):
        raise ManagerUnavailable(
            "the managing call returned no usable decision")
    return ManagerDecision(decision, reason.strip())


def build_root(task: dict) -> tuple[NodeSpec, tuple[str, ...]]:
    """The blind root contract + the withheld grader set.

    The root's write boundary is every SOURCE file (the tree narrows it per child); its
    ACs are the extracted task requirements — cross-child integration criteria, which the
    tree puts in a dedicated integration leaf. ``grader_paths`` is the same definition
    ``bench/v2_leaf.build_spec`` uses (staged-owned paths ∪ the task's ``UNTOUCHED`` list),
    injected from the root so no child can widen it. This union serves the LEAF WRITE
    guard (frozen visible files are restored by the grader, so writing one can never
    green). The PLAN-TIME guard is fed only the genuinely-HIDDEN subset
    (``stage_blind``'s return) so a plan that legitimately touches a visible frozen file
    is accepted (ticket 21 round 3, fix C).
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
        # Ticket 22 PLAN-TIME POLICY. The root owns the integration boundary and has no
        # planner call of its own, so it declares ``either`` (prefer a test, fall back to
        # review) with the REQUIRED reason; every child gets its own policy + reason from
        # the planner.
        verification_policy="either",
        verification_reason=("root spec (no planner): prefer a discriminating test and "
                             "fall back to the graded review when a test cannot carry "
                             "the integration requirement"),
    )
    return root, grader_paths


def node_record(outcome: NodeOutcome, *, diluted: bool = False) -> dict:
    """One node's persisted facts (recursively) — the tree, stop reasons, and verdicts.

    In a covenant-diluted run a weakened claim (a ``none`` tier or a best-effort downgrade)
    is recorded UNVERIFIED here too, so no per-node field presents it as a verified claim.
    """
    leaf = outcome.leaf
    weakened = bool(leaf is not None and _leaf_weakened(leaf))
    verified = bool(leaf.verified) if leaf is not None else False
    claim_status = (leaf.claim_status if leaf is not None else "")
    if diluted and weakened:
        verified = False
        claim_status = "unverified-success" if claim_status.endswith("success") else claim_status
    return {
        "node": outcome.node_id,
        "claimed": outcome.claimed,
        "stop_reason": outcome.stop_reason,
        "calls": outcome.calls,
        "wall_s": outcome.wall_s,
        # Ticket 20 step 2e: the node pool's conservation check (initial/remaining/spent +
        # a computed ``ok``), so a reader can see at a glance that every slice this node
        # split off was returned exactly once.
        "accounting": dict(outcome.accounting),
        "accounting_ok": bool(outcome.accounting.get("ok", False)),
        "leaf_signal": (leaf.signal if leaf is not None else None),
        "leaf_stop_reason": (leaf.stop_reason if leaf is not None else None),
        "self_test": (leaf.self_test if leaf is not None else None),
        # Ticket 19: the leaf's claim basis, verification basis, review verdicts, coverage
        # results, declared-case problems, attribution labels, and needs-user flag.
        "claimed_basis": (leaf.claimed_basis if leaf is not None else None),
        "verification_basis": (leaf.verification_basis if leaf is not None else None),
        # Ticket 20: the explicit verification record + four-way claim status per node.
        "verified": verified,
        "claim_status": claim_status,
        "verification": (dataclasses.asdict(leaf.verification)
                         if leaf is not None and leaf.verification is not None else None),
        # Ticket 22: the declared policy + reason, every recorded plan update, and any
        # review-vs-test disagreement the review outranked, per node.
        "verification_policy": (leaf.verification_policy if leaf is not None else None),
        "verification_policy_reason": (leaf.verification_policy_reason
                                       if leaf is not None else None),
        "plan_updates": ([dataclasses.asdict(u) for u in leaf.plan_updates]
                         if leaf is not None else []),
        "verification_disagreement": (leaf.verification_disagreement
                                      if leaf is not None else None),
        "needs_user": (leaf.needs_user if leaf is not None else False),
        "review_verdicts": ([dataclasses.asdict(v) for v in leaf.review_verdicts]
                            if leaf is not None else []),
        "coverage": ([dataclasses.asdict(c) for c in leaf.coverage]
                     if leaf is not None else []),
        "coverage_missing": (list(leaf.coverage_missing) if leaf is not None else []),
        "coverage_unresolved": (list(leaf.coverage_unresolved) if leaf is not None else []),
        "test_case_problems": (list(leaf.test_case_problems) if leaf is not None else []),
        # Ticket 21: the per-criterion ledger + the evidence-backed failure report (with
        # the distinct EVIDENCE-GAP state) so a node that did not close carries its own
        # evidence, never just a stop reason.
        "ledger": ([dataclasses.asdict(e) for e in leaf.ledger]
                   if leaf is not None else []),
        "failure_report": (dataclasses.asdict(leaf.failure_report)
                           if leaf is not None and leaf.failure_report is not None
                           else None),
        "evidence_gap": (leaf.evidence_gap if leaf is not None else False),
        "malformed_steps": (list(leaf.malformed_steps) if leaf is not None else []),
        "judge_unavailable": (leaf.judge_unavailable if leaf is not None else 0),
        "judge_verdicts": ([v.model_dump(mode="json") for v in leaf.judge_verdicts]
                           if leaf is not None else []),
        "integration_verdicts": dict(outcome.integration_verdicts),
        "close_rule": outcome.close_rule,
        "integration_reopen_rounds": outcome.integration_reopen_rounds,
        "boundary_audit": (outcome.boundary_audit.to_dict()
                           if outcome.boundary_audit is not None else None),
        # Ticket 20 step 2b: the How axis — the node's Hows with statuses, its per-
        # candidate audit records (isolated directory + Selection + evidence + who won),
        # the manager-loop decisions, and the winning How id. Empty for a legacy single-
        # plan node (one that could not plan Hows).
        "hows": list(outcome.hows),
        "candidates": [c.to_dict() for c in outcome.candidates],
        "manager_decisions": list(outcome.manager_decisions),
        # Ticket 20 step 2b-iii: managing calls that returned no usable decision (a
        # blocked/unable envelope). Kept SEPARATE so a non-decision never reads as one.
        "manager_unavailable": list(outcome.manager_unavailable),
        "winner": outcome.winner,
        # Ticket 20 step 2d: how many How candidates this node tried one after another
        # (greedy sequential retries included), and the deterministic allocation guard's
        # decision for the top How (thresholds, counted files/ACs, forced-to-leaf).
        "sequential_attempts": outcome.sequential_attempts,
        "allocation": dict(outcome.allocation),
        "children": [node_record(c, diluted=diluted) for c in outcome.children],
    }


def _tree_verified(outcome: NodeOutcome, *, allow_weakened: bool = True) -> bool:
    """The tree's terminal verification strength (ticket 20): every terminal leaf's
    evidence is a VERIFIED tier (``test`` or ``review``). In a covenant-diluted run
    (``allow_weakened=False``) a weakened claim (a ``none`` tier or a best-effort
    downgrade) never counts as verified."""
    if outcome.leaf is not None:
        if not outcome.leaf.verified:
            return False
        if not allow_weakened and _leaf_weakened(outcome.leaf):
            return False
        return True
    if not outcome.children:
        return False
    return all(_tree_verified(child, allow_weakened=allow_weakened)
               for child in outcome.children)


def _leaf_weakened(leaf: Any) -> bool:
    """True when a code-writing leaf's claim was covenant-weakened (ticket 20 items 4-5)."""
    record = getattr(leaf, "verification", None)
    return bool(record is not None and record.wrote_code
                and (record.downgraded or record.tier == "none"))


def _covenant_counts(outcome: NodeOutcome) -> tuple[int, int]:
    """The run-level ``(weakened, code-writing leaf)`` counts for the dilution cap."""
    weakened = total = 0
    if outcome.leaf is not None:
        record = getattr(outcome.leaf, "verification", None)
        if record is not None and record.wrote_code:
            total += 1
            weakened += 1 if _leaf_weakened(outcome.leaf) else 0
    for child in outcome.children:
        child_weakened, child_total = _covenant_counts(child)
        weakened += child_weakened
        total += child_total
    return weakened, total


def _sequential_attempts(outcome: NodeOutcome) -> int:
    """Ticket 20 step 2d: total How candidates tried one after another across the tree.

    Greedy is sequential, so ``> 1`` per node means the manager drove at least one retry
    (``continue-with-next-how`` / ``author-a-new-how``); this is the run-level counter
    that shows whether sequential retries actually happened.
    """
    return outcome.sequential_attempts + sum(_sequential_attempts(c)
                                             for c in outcome.children)


def _verification_tally(outcome: NodeOutcome) -> tuple[int, int]:
    """The run-level ``(best_effort_declared, downgrades)`` count across the tree
    (ticket 20 item 4): how many code-writing nodes opted into a weaker tier, and how
    many actually claimed below their required tier."""
    declared = downgrades = 0
    if outcome.leaf is not None and outcome.leaf.verification is not None:
        record = outcome.leaf.verification
        declared += 1 if record.best_effort else 0
        downgrades += 1 if record.downgraded else 0
    for child in outcome.children:
        child_declared, child_downgrades = _verification_tally(child)
        declared += child_declared
        downgrades += child_downgrades
    return declared, downgrades


def build_record(task_id: str, goal: str, outcome: TreeOutcome, *, withheld: list[str],
                 produced: dict[str, str], score: ExternalScore, quad: str,
                 run_wall_s: float, judge_enabled: bool, iv_enabled: bool,
                 review_enabled: bool, acs: list[str], verified_quad: str = "",
                 how_explore: int = 1) -> dict:
    declared, downgrades = _verification_tally(outcome.root)
    weakened, nodes = _covenant_counts(outcome.root)
    diluted = covenant_diluted(weakened, nodes)
    """Assemble the persisted run record (nodes, budgets, stop reasons, split history)."""
    return {
        "task": task_id,
        "goal": goal,
        "acs": list(acs),
        "withheld_grader_paths": withheld,
        "judge": judge_enabled,
        "iv": iv_enabled,
        "review": review_enabled,
        # Ticket 20 step 2c: the How-exploration setting (1 = greedy, the default).
        "how_explore": how_explore,
        # Ticket 20 step 2d: the run-level count of sequential How attempts (greedy still
        # honours the manager: > 1 means a retry actually happened).
        "sequential_attempts": _sequential_attempts(outcome.root),
        "claimed": outcome.claimed,
        "actual": score.passed,
        "quadrant": quad,
        "verified_quadrant": verified_quad,
        # Ticket 20 items 4-5: the run-level declaration + downgrade counters, the
        # weakening ratio, and the dilution flag. A diluted run's weakened claims never
        # count as verified (the caller computes ``verified_quadrant`` accordingly).
        "best_effort_declared": declared,
        "verification_downgrades": downgrades,
        "covenant_weakened": weakened,
        "covenant_nodes": nodes,
        "covenant_diluted": diluted,
        "calls": outcome.calls,
        "tree_wall_s": outcome.wall_s,
        "run_wall_s": run_wall_s,
        "budget": outcome.budget.to_dict(),
        # Ticket 20 step 2e: the RUN-level conservation invariant (initial/remaining/spent
        # + a computed ``ok``). The budget sub-object carries the same object; it is
        # surfaced here too so a reader can check the whole run at a glance.
        "accounting": outcome.budget.accounting(),
        "accounting_ok": bool(outcome.budget.accounting()["ok"]),
        "checkpoints": dict(outcome.checkpoints),
        "split_history": {
            node: [dataclasses.asdict(attempt) for attempt in attempts]
            for node, attempts in outcome.split_history.items()
        },
        "nodes": node_record(outcome.root, diluted=diluted),
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
             use_review: bool = True, use_manager: bool = True,
             how_explore: int = 1) -> dict:
    task = load_task(task_dir)
    root, grader_paths = build_root(task)

    workdir = out_dir / "work"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    # The genuinely-hidden set the run cannot see. The plan guard uses THIS; the leaf
    # write guard uses ``grader_paths`` (this set ∪ the visible-but-frozen UNTOUCHED list).
    withheld = stage_blind(workdir, task["files"])

    budget = Budget(calls=calls,
                    deadline_ts=default_deadline(time.time(), deadline_hours * 3600))
    model = LlamaServerRunner(server)
    judge = (lambda request: model_judge(model, request)) if use_judge else None
    iv = (lambda request: model_independent_test(model, request)) if use_iv else None
    review = (lambda request: model_review(model, request)) if use_review else None
    # Ticket 20 step 2b-ii: the REAL model-backed managing call. Without it a failed How
    # parks immediately; with it the node's structured record drives the four-way decision.
    manager = (lambda record: model_manager(model, record)) if use_manager else None
    # The higher per-leaf floor when the independent machinery is on (design §2).
    min_leaf_calls = (MIN_LEAF_CALLS_WITH_JUDGE if (use_judge and use_iv)
                      else MIN_LEAF_CALLS)

    tree = TaskTree(what=root.goal, why="blind v2 tree run", files=list(root.files))
    started = time.monotonic()
    outcome = asyncio.run(run_tree(
        model, root, tree, workdir, budget, root_grader_paths=grader_paths,
        root_withheld_paths=withheld,
        judge=judge, iv=iv, review=review, min_leaf_calls=min_leaf_calls,
        run_outdir=out_dir, manager=manager, how_explore=how_explore))
    wall = round(time.monotonic() - started, 1)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(outcome.claimed, score.passed)
    weakened, nodes = _covenant_counts(outcome.root)
    diluted = covenant_diluted(weakened, nodes)
    vquad = verified_quadrant(outcome.claimed, score.passed,
                              _tree_verified(outcome.root,
                                             allow_weakened=not diluted))

    record = build_record(
        task["task_id"], root.goal, outcome, withheld=withheld, produced=produced,
        score=score, quad=quad, run_wall_s=wall, judge_enabled=use_judge,
        iv_enabled=use_iv, review_enabled=use_review, acs=list(root.acs),
        verified_quad=vquad, how_explore=how_explore)

    print(f"== v2 tree: {task['task_id']} ==")
    print(f"[judge]  {'on' if use_judge else 'off (conservative baseline)'}")
    print(f"[iv]  {'on' if use_iv else 'off (own-test basis)'} "
          f"min_leaf_calls={min_leaf_calls}")
    print(f"[manager]  {'on (model-backed)' if use_manager else 'off (park-only default)'}")
    print(f"[explore]  how_explore={how_explore}: "
          f"{'greedy (sequential Hows, one candidate at a time)' if how_explore <= 1 else 'tournament (parallel candidates)'}")
    print(f"[acs]  {len(root.acs)} extracted from the request")
    print(f"[claim]  claimed={outcome.claimed} root={outcome.root.stop_reason} "
          f"calls={outcome.calls} budget_left={outcome.budget.calls}")
    print(f"[actual] grader_passed={score.passed} exit={score.exit}")
    print(f"[quadrant] {quad}  (tree_wall={outcome.wall_s}s run_wall={wall}s)")
    print(f"[verification] verified={_tree_verified(outcome.root)} -> {vquad}")
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
    parser.add_argument("--manager", action=argparse.BooleanOptionalAction, default=True,
                        help="wire the model-backed managing call into the failure loop "
                             "(default ON); --no-manager restores the safe park-only default")
    parser.add_argument("--how-explore", type=int, default=1, dest="how_explore",
                        help="How candidates a node may open in PARALLEL: 1 (default) is "
                             "GREEDY --- plan the Hows, take the top-ranked one, and fund "
                             "that single candidate while still honouring the manager for "
                             "SEQUENTIAL retries; N>1 restores the parallel tournament")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    task_dir = Path(args.task)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"v2tree-{ts}" / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    record = run_once(task_dir, out_dir, args.server, args.calls, args.deadline_hours,
                      use_judge=args.judge, use_iv=args.iv, use_review=args.review,
                      use_manager=args.manager, how_explore=args.how_explore)
    record_path = out_dir / "run.json"
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(f"[persist] {record_path}")
    return 0 if record["quadrant"] == "true-success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
