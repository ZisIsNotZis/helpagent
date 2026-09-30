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
model's own "the test is wrong" claim is never credited. Round 7 replaces the round-4
text-opinion FALSIFIER with an INDEPENDENT TEST (default ON, ``--no-iv`` to disable): a
fresh-context call writes its own test from the goal, the ACs, and the ORIGINAL and FINAL
source of the changed files (never the run's own test, never a grader path), and the
harness runs that test on private copies of the pre-run and final trees — it must FAIL on
the original and PASS on the final before the run may claim. The record says which modes
ran (``judge``, ``iv``) and carries every judge verdict and independent-test verdict.

Usage:
  uv run python bench/v2_leaf.py --task bench/corpus/T-31-parameter-threading \
      --calls 24 --deadline-hours 6 [--no-judge] [--no-iv]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.blind_run import produced_files, quadrant, verified_quadrant  # noqa: E402
from bench.external_score import (  # noqa: E402
    ExternalScore,
    external_score,
    untouched_paths,
)
from harness.budget import Budget, default_deadline  # noqa: E402
from harness.gate_report import JUNIT_FAMILY_ARGS  # noqa: E402
from harness.leaf import (  # noqa: E402
    REVIEW_ANGLE_PROMPTS,
    covenant_diluted,
    IndependentTestCandidate,
    IndependentTestRequest,
    JudgeRequest,
    JudgeVerdict,
    LeafOutcome,
    LeafSpec,
    ReviewRequest,
    ReviewVerdict,
    run_leaf,
)
from harness.model import LlamaServerRunner  # noqa: E402
from harness.runner import SchemaViolation, llm_step  # noqa: E402
from harness.staging import (  # noqa: E402
    PYTEST_ISOLATION_ARGS,
    PYTEST_ISOLATION_ENV,
    excluded_paths,
    source_only,
    stage_blind,
)

__all__ = ["build_parser", "build_record", "build_spec", "extract_acs", "load_task",
           "main", "model_independent_test", "model_judge", "model_review", "quadrant",
           "run_once"]

def _review_question(request: ReviewRequest) -> str:
    """The fresh-context REVIEW prompt (ticket 19 B). With ``fresh=True`` no artifacts are
    injected, so the evidence rides the question verbatim. The reviewer sees the goal, the
    NUMBERED ACs, and the ORIGINAL/FINAL source of the changed files — never a grader path
    and never the run's own test."""
    acs = _numbered_acs(request.acs)
    original = "\n".join(f"--- {rel} (ORIGINAL) ---\n{text}"
                          for rel, text in sorted(request.original.items())) or "(no source changed)"
    final = "\n".join(f"--- {rel} (FINAL) ---\n{text}"
                       for rel, text in sorted(request.final.items())) or "(no source changed)"
    angle = request.angle or "ac-correctness"
    instruction = REVIEW_ANGLE_PROMPTS.get(
        angle, "Check the final diff against the goal and the acceptance criteria.")
    return (
        "You are an INDEPENDENT reviewer. No test can carry verification for this node, so "
        "YOU grade ONE review ANGLE of the final diff. You did not write the code.\n"
        f"ANGLE: {angle}\n"
        f"WHAT TO CHECK: {instruction}\n"
        f"GOAL:\n{request.goal}\n\n"
        f"ACCEPTANCE CRITERIA (numbered):\n{acs}\n\n"
        f"ORIGINAL SOURCE (before):\n{original}\n\n"
        f"FINAL SOURCE (after):\n{final}\n\n"
        f"WHY REVIEW IS REQUIRED: {request.reason or 'no test could carry verification'}\n\n"
        "Return ONE grade --- exactly one of definitely-ok, probably-ok, uncertain, "
        "probably-problematic, definitely-problematic --- for THIS angle only. If you "
        "found a problem you MUST give a CONCRETE counterexample in 'evidence'; if you "
        "found none you MUST say so explicitly and name the concrete artifact you "
        "checked (a changed file, symbol, or test name). A bare approval is rejected."
    )


async def model_review(model: Any, request: ReviewRequest) -> ReviewVerdict:
    """The driver's DEFAULT reviewer (ticket 19 B): a FRESH-CONTEXT model call that reads
    the goal, the ACs, and the final diff and returns pass/fail WITH evidence. It reuses
    the §26 ``leaf_review`` envelope; the deterministic filter in
    :func:`harness.leaf.apply_review_filter` is applied by the leaf, not here."""
    env = await llm_step(model, "leaf_review", artifacts={},
                         question=_review_question(request), fresh=True)
    grade = getattr(env, "grade", "")
    raw = json.dumps({
        "status": env.status,
        "comment": getattr(env, "comment", ""),
        "grade": (grade if isinstance(grade, str) else ""),
        "evidence": (getattr(env, "evidence", "") if isinstance(getattr(env, "evidence", ""), str) else ""),
        "unable_reason": env.unable_reason or "",
    }, ensure_ascii=False)
    if env.status != "ok":
        return ReviewVerdict(angle=request.angle, grade="uncertain", evidence="",
                             detail=env.unable_reason or "review unavailable", raw=raw)
    evidence = getattr(env, "evidence", "") or env.comment
    return ReviewVerdict(angle=request.angle, grade=str(grade) or "uncertain",
                         evidence=evidence, detail=evidence, raw=raw)


DEFAULT_SERVER = "http://127.0.0.1:8833"

#: debug_judge ``blame`` → the judge's MULTI-LABEL verdict (ticket 19 A). ``both`` maps to
#: implementation+test (an ambiguous verdict is still never credited to the test alone).
_JUDGE_LABELS = {
    "code": {"implementation_wrong": True},
    "test": {"test_wrong": True},
    "spec": {"spec_wrong": True},
    "both": {"implementation_wrong": True, "test_wrong": True},
}

#: ``extract_acs`` splitting rules (deterministic, no model involved). A fenced code
#: block is example output, not a requirement, so it is skipped; a sentence boundary is
#: a terminal punctuation mark followed by an upper-case letter (so ``e.g.`` does not
#: split a sentence).
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.*)$")
_FENCE = re.compile(r"^\s*```")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


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


def extract_acs(request: str) -> list[str]:
    """Derive acceptance criteria from the task request DETERMINISTICALLY.

    One criterion per requirement sentence or bullet of ``request.md``: HTML comments,
    Markdown headers, and fenced example blocks are dropped; wrapped prose lines are
    reflowed into paragraphs and split on sentence boundaries; bullets are their own
    criteria; whitespace is collapsed and duplicates are removed while order is kept.
    The raw text is what the self-test, implement, judge, and independent test calls
    receive — and what the run record stores for audit.
    """
    text = _HTML_COMMENT.sub("", request or "")
    paragraphs: list[str] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        if buffer:
            paragraphs.append(" ".join(buffer))
            buffer.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not line or line.startswith("#"):
            flush()
            continue
        bullet = _BULLET.match(line)
        if bullet:
            flush()
            paragraphs.append(bullet.group(1).strip())
            continue
        buffer.append(line)
    flush()

    items: list[str] = []
    for paragraph in paragraphs:
        for sentence in _SENTENCE_BOUNDARY.split(paragraph):
            sentence = " ".join(sentence.split())
            if len(sentence) >= 3:
                items.append(sentence)
    acs: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        acs.append(item)
    return acs


def build_spec(task: dict) -> LeafSpec:
    """The blind leaf contract: source only in ``files``, grader paths withheld.

    Acceptance criteria are populated from the task request (``extract_acs``) so the
    self-test, implement, judge, and independent-test calls all have the requirement
    text to work with; before this the leaf passed ``acs=[]`` and every step was blind
    to what the task actually asked.

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
        acs=extract_acs(task["request"]),
        interfaces=[],
        grader_paths=grader_paths,
    )


def build_record(task_id: str, goal: str, outcome: LeafOutcome, *, withheld: list[str],
                 produced: dict[str, str], score: ExternalScore, quad: str,
                 run_wall_s: float, judge_enabled: bool = False,
                 iv_enabled: bool = False, review_enabled: bool = False,
                 acs: list[str] | None = None, verified_quad: str = "") -> dict:
    """Assemble the persisted run record. One place, so the JSON that lands in
    ``run.json`` and the shape the tests pin cannot drift apart — including the
    wasted escalations that used to live only in the process-global ledger, every
    judge verdict (raw + coerced), every independent-test verdict with its source and
    both gate reports, the claim basis, the acceptance criteria actually fed in, the
    grader restores/shadow refusals that neutralized run tampering, the leaf's own
    write-guard refusals, the gate report anomalies, the machine-readable grader
    report gate (ticket 17 F1), and the interpreter isolation applied to both pytest
    runs."""
    weakened = covenant_weakened(outcome)
    diluted = bool(outcome.claimed) and covenant_diluted(1 if weakened else 0, 1)
    verified = bool(outcome.verified) and not (diluted and weakened)
    claim_status = outcome.claim_status
    if diluted and weakened and claim_status.endswith("success"):
        claim_status = "unverified-success"
    return {
        "task": task_id,
        "goal": goal,
        "acs": list(acs or []),
        "withheld_grader_paths": withheld,
        "judge": judge_enabled,
        "iv": iv_enabled,
        "review": review_enabled,
        "claimed": outcome.claimed,
        "claimed_basis": outcome.claimed_basis,
        "verification_basis": outcome.verification_basis,
        # Ticket 20: the explicit verification record (ordered tier, written reason and
        # its deterministic check, the independent review verdicts, and any recorded
        # best-effort downgrade), plus the four-way claim status the scoring layer reads.
        # A COVENANT-DILUTED run records its weakened claims as unverified.
        "verified": verified,
        "claim_status": claim_status,
        "verification": (dataclasses.asdict(outcome.verification)
                         if outcome.verification is not None else None),
        # Ticket 20 items 4-5: the run-level best_effort/downgrade counters, the weighting
        # ratio, and the dilution flag, so an "everywhere best_effort" plan cannot stay a
        # silent escape.
        "best_effort_declared": bool(outcome.verification is not None
                                     and outcome.verification.best_effort),
        "verification_downgrades": (1 if outcome.verification is not None
                                    and outcome.verification.downgraded else 0),
        "covenant_weakened": weakened,
        "covenant_diluted": diluted,
        "review_score": (outcome.verification.review_score
                         if outcome.verification is not None else 0),
        "review_verdicts": [dataclasses.asdict(v) for v in outcome.review_verdicts],
        # Ticket 19 E/D: per-requirement artifact coverage and the declared test-case
        # contract failures that blocked a claim.
        "coverage": [dataclasses.asdict(c) for c in outcome.coverage],
        "coverage_missing": outcome.coverage_missing,
        # Ticket 19 round 2 (F2): the criteria that named no artifact and had no declared
        # discriminating test to carry them (a distinct claim blocker).
        "coverage_unresolved": outcome.coverage_unresolved,
        "test_case_problems": outcome.test_case_problems,
        "needs_user": outcome.needs_user,
        "actual": score.passed,
        "quadrant": quad,
        "verified_quadrant": verified_quad,
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
        "independent_test": outcome.independent_test,
        "independent_test_path": outcome.independent_test_path,
        "independent_test_node_ids": outcome.independent_test_node_ids,
        "independent_test_reason": outcome.independent_test_reason,
        "iv_attempts": outcome.iv_attempts,
        "iv_repairs": outcome.iv_repairs,
        # Ticket 17 rounds 10-11: the per-criterion discrimination evidence. For every
        # index it carries the explicit node ids (``selection``) plus the
        # original/final collected count and failures and the reason it failed (empty =
        # it discriminated). ``iv_criteria_count`` of 0 means no criteria were extracted
        # and the rule was skipped; ``iv_covered_indices`` discriminated,
        # ``iv_uncovered_indices`` had no matching node, and ``iv_shared_node_ids`` were
        # selected for more than one criterion.
        "iv_criteria_count": outcome.iv_criteria_count,
        "iv_criteria": [dataclasses.asdict(c) for c in outcome.iv_criteria],
        "iv_covered_indices": outcome.iv_covered_indices,
        "iv_uncovered_indices": outcome.iv_uncovered_indices,
        "iv_shared_node_ids": outcome.iv_shared_node_ids,
        "iv_original_gate": (dataclasses.asdict(outcome.iv_original_gate)
                              if outcome.iv_original_gate is not None else None),
        "iv_final_gate": (dataclasses.asdict(outcome.iv_final_gate)
                           if outcome.iv_final_gate is not None else None),
        "iv_verdicts": [dataclasses.asdict(v) for v in outcome.iv_verdicts],
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
        # Ticket 19 round 2 (F5): every envelope step that stayed malformed past its
        # bounded retries. A malformed step no longer ends the node.
        "malformed_steps": outcome.malformed_steps,
        # Ticket 19 round 3 (FIX 2): how many judge consultations ended in the
        # deterministic "attribution unavailable" fallback.
        "judge_unavailable": outcome.judge_unavailable,
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

    Ticket 19 round 3 (FIX 2): a weak model frequently cannot emit the §16 shape (a
    ``blame`` enum + a ``problem`` + 1–5 ranked ``fixes``) and every malformed judge used
    to be recorded as a wasted step. The call now falls back ONCE to the strictly simpler
    §12 ``failure_judge`` shape (a flat per-side problem list) before re-raising, so a
    systematic format slip still produces an attribution.
    """
    try:
        env = await llm_step(model, "debug_judge", artifacts={},
                             question=_judge_question(request), fresh=True)
    except SchemaViolation:
        return await _model_judge_fallback(model, request)
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
        reason = (env.unable_reason or "").strip()
        return JudgeVerdict(environment_broken=True, reason=reason,
                            evidence=reason, defect=reason, raw=raw)
    problem = getattr(env, "problem", "") or ""
    return JudgeVerdict(
        **_JUDGE_LABELS.get(getattr(env, "blame", ""), {"implementation_wrong": True}),
        reason=problem, evidence=problem, defect=problem, raw=raw)


#: §12 ``failure_judge`` ``Problem.side`` → the multi-label attribution (FIX 2). ``side``
#: has no environment member (§12 ``code``/``test``/``spec``); an ``unable`` envelope is
#: read as an environment attribution exactly like the §16 path.
_JUDGE_FALLBACK_SIDES = {"code": "implementation_wrong", "test": "test_wrong",
                         "spec": "spec_wrong"}


def _judge_fallback_question(request: JudgeRequest) -> str:
    """The simpler §12 prompt for the judge fallback: ask only for the attribution, not
    for ranked fixes."""
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
        "Return ONE problem: `side` is `code` for a wrong implementation, `test` for a "
        "wrong test, or `spec` for an ambiguous requirement; put the CONCRETE defect in "
        "`description` and the file/line or assertion you used in `evidence`."
    )


async def _model_judge_fallback(model: Any, request: JudgeRequest) -> JudgeVerdict:
    """The simpler §12 ``failure_judge`` fallback (FIX 2).

    A malformed §16 ``debug_judge`` is retried ONCE in the strictly simpler §12 shape; the
    flat ``problems`` list is mapped onto the multi-label verdict. A second failure is
    re-raised so the leaf records its deterministic "attribution unavailable" fallback
    rather than looping.
    """
    env = await llm_step(model, "failure_judge", artifacts={},
                         question=_judge_fallback_question(request), fresh=True)
    raw = json.dumps({
        "status": env.status,
        "comment": getattr(env, "comment", ""),
        "unable_reason": env.unable_reason or "",
    }, ensure_ascii=False)
    if env.status == "unable":
        reason = (env.unable_reason or "").strip()
        return JudgeVerdict(environment_broken=True, reason=reason,
                            evidence=reason, defect=reason, raw=raw)
    labels: dict[str, bool] = {}
    reasons: list[str] = []
    for problem in getattr(env, "problems", []) or []:
        label = _JUDGE_FALLBACK_SIDES.get(getattr(problem, "side", ""))
        if label:
            labels[label] = True
        description = getattr(problem, "description", "") or ""
        if description:
            reasons.append(description)
    if not labels:
        labels = {"implementation_wrong": True}
    reason = "; ".join(reasons)
    return JudgeVerdict(**labels, reason=reason, evidence=reason, defect=reason, raw=raw)


def _numbered_acs(acs: list[str]) -> str:
    """The criteria as ``AC<i>: ...`` lines — the stable index the coverage rule uses."""
    if not acs:
        return "(none given)"
    return "\n".join(f"AC{i}: {ac}" for i, ac in enumerate(acs, 1))


def _independent_test_question(request: IndependentTestRequest) -> str:
    """The fresh-context independent-test prompt. With ``fresh=True`` the runner injects
    no artifacts, so the evidence rides the question verbatim (DESIGN §2.4 / §10.1 step 5).
    It sees the goal, the NUMBERED ACs, and the ORIGINAL/FINAL source of the changed files
    — never the run's own test and never a grader path. It is asked for ONE DISTINCT test
    function per criterion, each named with its own criterion index (``test_ac1_...``,
    ``test_ac2_...``): the naming is the HINT the harness uses to derive each criterion's
    EXPLICIT node ids, but the rule is DISCRIMINATION — each criterion's node set must
    fail on the original and pass on the final (ticket 17 rounds 10-11), and no single
    test node may serve two criteria. On the ONE bounded repair (ticket 17 round 8) it
    also carries the rejected test and the verdict that rejected it, plus the offending
    criterion indices."""
    acs = _numbered_acs(request.acs)
    original = "\n".join(f"--- {rel} (ORIGINAL) ---\n{text}"
                          for rel, text in sorted(request.original.items())) or "(no source changed)"
    final = "\n".join(f"--- {rel} (FINAL) ---\n{text}"
                       for rel, text in sorted(request.final.items())) or "(no source changed)"
    repair = ""
    if request.repair_reason:
        if request.repair_reason == "independent-test-not-red":
            guidance = ("It PASSED against the ORIGINAL source, so it cannot detect the "
                        "goal at all; make it FAIL on the ORIGINAL source.")
        elif request.repair_reason == "independent-test-not-discriminating":
            offending = ", ".join(f"AC{i}" for i in request.offending_indices) or "the criteria"
            guidance = (f"Its tests for {offending} still PASS against the ORIGINAL "
                        "source, so they do not pin the goal. Make each one FAIL on the "
                        "ORIGINAL source and PASS on the FINAL source.")
        elif request.repair_reason == "independent-test-incomplete-coverage":
            missing = ", ".join(f"AC{i}" for i in request.offending_indices) or "the criteria"
            guidance = (f"It did not exercise every acceptance criterion. Add ONE test "
                        f"function for each MISSING criterion ({missing}), named "
                        "test_ac<i>_<short_name>.")
        elif request.repair_reason == "independent-test-shared-coverage":
            offending = ", ".join(f"AC{i}" for i in request.offending_indices) or "the criteria"
            guidance = (f"One test node serves several criteria ({offending}). Write a "
                        "SEPARATE test function for each — test_ac1_<name>, "
                        "test_ac2_<name>, ... — so no function name carries more than one "
                        "criterion index.")
        else:
            guidance = ("pytest did not collect/observe it; write a COLLECTIBLE pytest "
                        "file (name it test_*.py, no collection errors).")
        repair = (
            f"\nYOUR PREVIOUS TEST WAS REJECTED ({request.repair_reason}): "
            f"{request.repair_detail}\n{guidance}\n"
            f"PREVIOUS TEST:\n{request.previous_test}\n")
    return (
        "You are an INDEPENDENT verifier. You did not write the fix and you will never see "
        "the run's own test. Write your OWN pytest file that encodes the acceptance "
        "criteria as executable checks against the code under test.\n"
        f"GOAL:\n{request.goal}\n\n"
        f"ACCEPTANCE CRITERIA (numbered; write ONE test function per criterion):\n{acs}\n\n"
        f"ORIGINAL SOURCE (before the fix):\n{original}\n\n"
        f"FINAL SOURCE (after the fix):\n{final}\n"
        f"{repair}\n"
        "Write ONE pytest test function for EACH acceptance criterion above. Name each "
        "function with ITS OWN criterion index — test_ac1_<short_name>, "
        "test_ac2_<short_name>, and so on in order — and NEVER put more than one "
        "criterion index in a single function name (no test_ac1_ac2_<name>), so each "
        "criterion maps to its own distinct test node.\n"
        "Write a test that FAILS against the ORIGINAL source and PASSES against the FINAL "
        "source. Return a NEW test file path under tests/ and its complete content. Do not "
        "reference any file other than the source shown above."
    )


async def model_independent_test(model: Any, request: IndependentTestRequest
                                 ) -> IndependentTestCandidate:
    """The driver's DEFAULT independent test: a FRESH-CONTEXT model call that writes its
    own test (ticket 17 round 7). It sees only the blind evidence — goal, ACs, and the
    original/final source of the changed files — never the run's own test and never a
    grader path. It reuses the §10 ``write_test`` envelope (no new schema). The harness,
    not the model, decides the claim: the test must be red on the pre-run tree and green
    on the final tree."""
    env = await llm_step(model, "write_test", artifacts={},
                         question=_independent_test_question(request), fresh=True)
    if env.status != "ok" or not getattr(env, "file_path", "") or not getattr(env, "content", ""):
        raise ValueError(
            f"independent test call returned status={env.status!r} without a test file")
    raw = json.dumps({"status": env.status, "comment": env.comment,
                      "file_path": env.file_path}, ensure_ascii=False)
    return IndependentTestCandidate(path=env.file_path, content=env.content, raw=raw)


def covenant_weakened(outcome: LeafOutcome) -> bool:
    """True when the node's claim was covenant-weakened (ticket 20, items 4-5): it claimed
    at the ``none`` tier, or below its declared floor under a ``best_effort`` declaration."""
    record = outcome.verification
    return bool(record is not None and record.wrote_code
                and (record.downgraded or record.tier == "none"))


def run_once(task_dir: Path, out_dir: Path, server: str, calls: int,
             deadline_hours: float, use_judge: bool = True,
             use_iv: bool = True, use_review: bool = True) -> dict:
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
    # Default ON: a fresh-context independent test (red on the pre-run source, green on
    # the final source) that must approve before any claim. --no-iv is the own-test-only
    # basis (claimed_basis="own-test").
    iv = (lambda request: model_independent_test(model, request)) if use_iv else None
    # Default ON: the mandatory REVIEW-BASED verification seam (ticket 19 B), used only
    # when no test can carry verification.
    review = (lambda request: model_review(model, request)) if use_review else None
    started = time.monotonic()
    outcome = asyncio.run(run_leaf(model, spec, workdir, budget, judge=judge, iv=iv,
                                   review=review))
    wall = round(time.monotonic() - started, 1)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(outcome.claimed, score.passed)
    weakened = covenant_weakened(outcome)
    diluted = bool(outcome.claimed) and covenant_diluted(1 if weakened else 0, 1)
    vquad = verified_quadrant(outcome.claimed, score.passed,
                              bool(outcome.verified) and not (diluted and weakened))

    record = build_record(
        task["task_id"], spec.goal, outcome, withheld=withheld, produced=produced,
        score=score, quad=quad, run_wall_s=wall, judge_enabled=use_judge,
        iv_enabled=use_iv, review_enabled=use_review, acs=spec.acs, verified_quad=vquad)

    print(f"== v2 leaf: {task['task_id']} ==")
    print(f"[judge]  {'on' if use_judge else 'off (conservative baseline)'} "
          f"({len(outcome.judge_verdicts)} verdict(s))")
    print(f"[iv]  {'on' if use_iv else 'off (own-test basis)'} "
          f"({len(outcome.iv_verdicts)} verdict(s), {outcome.iv_attempts} attempt(s), "
          f"{outcome.iv_repairs} repair(s))")
    print(f"[acs]  {len(spec.acs)} extracted from the request")
    print(f"[claim]  claimed={outcome.claimed} basis={outcome.claimed_basis} "
          f"signal={outcome.signal} stop={outcome.stop_reason or 'n/a'} "
          f"exhausted={outcome.exhausted} ({outcome.exhaustion_reason or 'n/a'})")
    print(f"[actual] grader_passed={score.passed} exit={score.exit} "
          f"suspected_contaminated={score.suspected_contaminated_grade}")
    print(f"[quadrant] {quad}  (calls={outcome.calls} wall={outcome.wall_s}s)")
    print(f"[verification] basis={outcome.verification_basis} "
          f"tier={getattr(outcome.verification, 'tier', None)} "
          f"verified={outcome.verified} status={outcome.claim_status} -> {vquad}")
    print(f"[self_test] {outcome.self_test or 'none'}  withheld={len(withheld)} grader path(s)")
    return record


def build_parser() -> argparse.ArgumentParser:
    """The CLI parser, exposed so the judge/iv defaults can be pinned by a test."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="corpus task dir (has repo/)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--deadline-hours", type=float, default=6.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--judge", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent attribution judge (default ON); "
                             "--no-judge for the conservative baseline")
    parser.add_argument("--iv", action=argparse.BooleanOptionalAction, default=True,
                        help="run the independent test (red on original, green on final; "
                             "default ON); --no-iv for the own-test-only claim basis")
    parser.add_argument("--review", action=argparse.BooleanOptionalAction, default=True,
                        help="run the mandatory REVIEW-based verification when no test can "
                             "carry verification (default ON); --no-review stops honestly")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    task_dir = Path(args.task)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"v2leaf-{ts}" / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    record = run_once(task_dir, out_dir, args.server, args.calls, args.deadline_hours,
                      use_judge=args.judge, use_iv=args.iv, use_review=args.review)
    record_path = out_dir / "run.json"
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(f"[persist] {record_path}")
    return 0 if record["quadrant"] == "true-success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
