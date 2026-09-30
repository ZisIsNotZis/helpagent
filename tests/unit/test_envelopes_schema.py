"""Envelope schema invariants — TEST_PLAN §3.1 + the grammar pairs from
ENVELOPE_SCHEMAS §0–§23."""

import asyncio

import pytest
from typing import get_args
from pydantic import ValidationError

from harness import (
    SCHEMAS,
    Envelope,
    FakeModelRunner,
    SchemaViolation,
    llm_step,
    reset_ledger_for_tests,
    ledger_entries,
    schema_violation,
)


# ---------------------------------------------------------------------------
# §3.1 pinned invariants
# ---------------------------------------------------------------------------


def test_envelope_rejects_missing_self_summary():
    """Feed schema_violation() → llm() raises SchemaViolation; ledger records
    validation_failed; no artifact written (no step_completed event, no envelope)."""
    reset_ledger_for_tests()
    fake = FakeModelRunner({"task_card": [schema_violation()]})
    with pytest.raises(SchemaViolation):
        asyncio.run(llm_step(fake, "task_card", artifacts={"request": "fix the bug"}, question="Extract goal"))
    kinds = [e["kind"] for e in ledger_entries()]
    assert "validation_failed" in kinds
    assert "step_completed" not in kinds  # nothing was produced/committed


def test_unable_alternative_is_in_every_envelope_schema():
    """Iterate the per-leaf-type schema library; assert each has a discriminant
    accepting `unable: reason` — and that the unable alternative actually parses."""
    assert len(SCHEMAS) == 26
    for step_type, model in SCHEMAS.items():
        assert issubclass(model, Envelope), step_type
        values = get_args(model.model_fields["status"].annotation)
        assert "unable" in values, step_type
        assert "unable_reason" in model.model_fields, step_type
        env = model.model_validate(
            {"status": "unable", "comment": "cannot proceed", "unable_reason": "missing ground truth"}
        )
        assert env.status == "unable" and env.unable_reason == "missing ground truth"


VALID_PAYLOADS = {
    "fix_plan": {"steps": ["locate the env lookup", "return env before default", "keep default types"]},
    "task_card": {"task_class": "bugfix", "goal": "Fix session expiry."},
    "find_ambiguities": {"items": []},
    "revise_task_card": {"changed": ["goal"],
                         "card": {"status": "ok", "comment": "c", "task_class": "bugfix", "goal": "g"},
                         "because": "b"},
    "expand": {"children": [{"seam_id": "seam-1", "what": "w", "why": "y", "leaf": True, "est_rounds": 4}]},
    "split_review": {"ok": True, "issues": []},
    "draft_acs": {"acs": []},
    "write_spec": {"interfaces": [], "behavior": "b", "implementation_notes": "n", "files_touched": []},
    "spec_review": {"ok": True, "issues": []},
    "test_plan": {"cases": []},
    "write_test": {"file_path": "tests/test_auth.py", "content": "def test_ok():\n    pass\n"},
    "implement": {"tests_run": ["python -m pytest"]},
    "failure_judge": {"problems": []},
    "identify_bugs": {"bugs": []},
    "propose_probe": {"command": "python -m pytest -x", "expected_info": "e", "why": "w",
                      "confident_enough": False},
    "interpret_probe": {"fact": "f", "implies": "i", "lesson": None},
    "debug_judge": {"blame": "code", "problem": "p",
                    "fixes": [{"rank": 1, "approach": "a", "how": "h"}]},
    "fix_attempt": {"status": "fixed", "tests_run": ["pytest"], "new_issues": []},
    "judge_aspect": {"aspect": "spec-match", "target_ac_id": "AC-1", "verdict": "pass",
                     "confidence": "high", "evidence": "diff shows the guard added"},
    "run_summary": {"outcome": "complete", "what_was_done": "d", "what_changed": "c", "what_remains": "r"},
    "gate_decide": {"decision": "accept", "reason_is_real": True, "weakens_gate": False,
                    "meaning_preserved": True},
    "propose_growth": {"trigger": "new-bug", "evidence_refs": ["ledger:fp-1"],
                       "nodes": [{"kind": "ticket", "what": "w", "why": "y"}], "reason": "r"},
    "lesson": {"line": "l", "topic_key": ["python", "iterator"], "provenance_task_id": "N-1",
               "provenance_ref": "ledger:fp-1"},
    "plan_node": {
        "goal": "fix session expiry",
        "behavior": "expiry is computed from the ttl config",
        "implementation_notes": "read the ttl in seconds",
        "files": ["middleware/auth.py"],
        "acs": [{"ac_id": "AC-1", "statement": "sessions expire per ttl",
                 "check_kind": "test", "check_hint": "tests/test_auth.py::test_expiry"}],
        "interfaces": [{"name": "expire()", "signature": "expire() -> None",
                         "contract": "expires the session"}],
        "test_cases": [{"ac_id": "AC-1", "file": "tests/test_auth.py",
                         "names": ["test_ac1_expiry"]}],
        "children": [{"what": "fix the expiry computation", "why": "it uses seconds",
                      "kind": "leaf", "files": ["middleware/auth.py"],
                      "acs": [{"ac_id": "AC-1", "statement": "sessions expire per ttl",
                               "check_kind": "test", "check_hint": "tests/test_auth.py::test_expiry"}],
                      "interfaces": [], "est_calls": 3}],
    },
    "leaf_review": {"verdict": "pass", "evidence": "middleware/auth.py:42 implements AC-1"},
    "verify": {"reason": "no test can pin this timing-dependent warning and no reviewer was available"},
}


def test_envelope_round_trip():
    """Every schema: build a valid instance → serialize → parse → equal; and the
    unable alternative parses for each."""
    assert set(VALID_PAYLOADS) == set(SCHEMAS)
    for step_type, model in SCHEMAS.items():
        payload = {"status": "ok", "comment": "step self-summary", **VALID_PAYLOADS[step_type]}
        env = model.model_validate(payload)
        again = model.model_validate(env.model_dump())
        assert again == env, step_type
        unable_env = model.model_validate(
            {"status": "unable", "comment": "c", "unable_reason": "r"}
        )
        assert unable_env.status == "unable"


# ---------------------------------------------------------------------------
# Base conventions (§0)
# ---------------------------------------------------------------------------


def test_unable_branch_forbids_payload_fields():
    from harness import TaskCard
    with pytest.raises(ValidationError, match="forbids payload"):
        TaskCard.model_validate({"status": "unable", "comment": "c", "unable_reason": "r", "goal": "g"})
    with pytest.raises(ValidationError, match="REQUIRED iff"):
        TaskCard.model_validate({"status": "unable", "comment": "c"})
    with pytest.raises(ValidationError, match="forbidden unless"):
        TaskCard.model_validate({"status": "ok", "comment": "c", "goal": "g", "unable_reason": "r"})


def test_comment_is_mandatory_self_summary():
    from harness import TaskCard
    with pytest.raises(ValidationError):
        TaskCard.model_validate({"status": "ok", "goal": "g"})
    with pytest.raises(ValidationError):
        TaskCard.model_validate({"status": "ok", "comment": "", "goal": "g"})


# ---------------------------------------------------------------------------
# Per-schema bounds and conditional pairs
# ---------------------------------------------------------------------------


def test_expand_children_bounds_and_seam_context():
    from harness import Expand

    def child(seam="seam-1"):
        return {"seam_id": seam, "what": "w", "why": "y", "leaf": True, "est_rounds": 4}

    with pytest.raises(ValidationError):
        Expand.model_validate({"status": "ok", "comment": "c", "children": []})  # 0 < 1
    with pytest.raises(ValidationError):
        Expand.model_validate({"status": "ok", "comment": "c", "children": [child() for _ in range(16)]})
    Expand.model_validate({"status": "ok", "comment": "c", "children": [child() for _ in range(15)]})
    # est_rounds 1–10
    with pytest.raises(ValidationError):
        Expand.model_validate({"status": "ok", "comment": "c",
                               "children": [{**child(), "est_rounds": 11}]})
    # seam_id ∈ injected candidate set — only when the context is injected
    ctx = {"candidate_seams": {"seam-1": {"files": ["middleware/auth.py"]}}}
    with pytest.raises(ValidationError, match="candidate cuts"):
        Expand.model_validate({"status": "ok", "comment": "c", "children": [child("seam-9")]}, context=ctx)
    Expand.model_validate({"status": "ok", "comment": "c", "children": [child()]}, context=ctx)
    # without context the seam check is the decoder grammar's job, not the schema's
    Expand.model_validate({"status": "ok", "comment": "c", "children": [child("seam-9")]})


def test_split_and_spec_review_ok_implies_no_issues():
    from harness import SpecReview, SplitReview
    issue = {"kind": "overlap", "target": "parent", "description": "d"}
    with pytest.raises(ValidationError, match="issues=="):
        SplitReview.model_validate({"status": "ok", "comment": "c", "ok": True, "issues": [issue]})
    # converse allowed: ok==False with empty issues is uninformative, not illegal
    SplitReview.model_validate({"status": "ok", "comment": "c", "ok": False, "issues": []})
    SplitReview.model_validate({"status": "ok", "comment": "c", "ok": True, "issues": []})
    sissue = {"severity": "minor", "location": "expires_at", "description": "d"}
    with pytest.raises(ValidationError, match="issues=="):
        SpecReview.model_validate({"status": "ok", "comment": "c", "ok": True, "issues": [sissue]})


def test_draft_acs_rules():
    from harness import DraftACs

    def ac(ac_id="AC-1", kind="test", hint=None):
        return {"ac_id": ac_id, "statement": "s", "check_kind": kind, "check_hint": hint}

    with pytest.raises(ValidationError):
        DraftACs.model_validate({"status": "ok", "comment": "c", "acs": [ac("AC-1234")]})  # pattern
    with pytest.raises(ValidationError, match="check_hint"):
        DraftACs.model_validate({"status": "ok", "comment": "c", "acs": [ac(kind="subjective")]})
    with pytest.raises(ValidationError, match="unique"):
        DraftACs.model_validate({"status": "ok", "comment": "c", "acs": [ac(), ac()]})
    with pytest.raises(ValidationError, match="at most 10 items"):
        DraftACs.model_validate({"status": "ok", "comment": "c", "acs": [ac(f"AC-{n}") for n in range(11)]})
    # empty map: invalid for a leaf (context), valid for internal / without context
    with pytest.raises(ValidationError, match="leaf"):
        DraftACs.model_validate({"status": "ok", "comment": "c", "acs": []}, context={"node_kind": "leaf"})
    DraftACs.model_validate({"status": "ok", "comment": "c", "acs": []}, context={"node_kind": "internal"})
    DraftACs.model_validate({"status": "ok", "comment": "c", "acs": []})


def test_test_case_ac_id_validated_against_injected_map():
    from harness import TestPlan
    case = lambda ac: {"case_id": "TC-1", "ac_id": ac, "kind": "unit", "description": "d"}
    ctx = {"ac_map": {"AC-1"}}
    with pytest.raises(ValidationError, match="AC test map"):
        TestPlan.model_validate({"status": "ok", "comment": "c", "cases": [case("AC-2")]}, context=ctx)
    TestPlan.model_validate({"status": "ok", "comment": "c", "cases": [case("AC-1")]}, context=ctx)
    # bad case_id pattern
    with pytest.raises(ValidationError):
        TestPlan.model_validate({"status": "ok", "comment": "c",
                                 "cases": [{**case("AC-1"), "case_id": "TC-1234"}]})


def test_write_spec_files_touched_narrows_boundary():
    from harness import WriteSpec
    payload = {"status": "ok", "comment": "c", "interfaces": [], "behavior": "b",
               "implementation_notes": "n", "files_touched": ["middleware/auth.py"]}
    ctx = {"boundary_files": {"middleware/auth.py", "auth/config.py"}}
    WriteSpec.model_validate(payload, context=ctx)
    wide = {**payload, "files_touched": ["middleware/auth.py", "utils/other.py"]}
    with pytest.raises(ValidationError, match="narrow the leaf boundary"):
        WriteSpec.model_validate(wide, context=ctx)
    with pytest.raises(ValidationError, match="at most 10 items"):
        WriteSpec.model_validate({**payload, "files_touched": [f"f{i}.py" for i in range(11)]})


def test_gate_decide_pairs():
    from harness import GateDecide
    base = {"status": "ok", "comment": "c", "reason_is_real": True, "meaning_preserved": True}
    with pytest.raises(ValidationError, match="weakens_gate==True"):
        GateDecide.model_validate({**base, "decision": "accept", "weakens_gate": True})
    with pytest.raises(ValidationError, match="explanation"):
        GateDecide.model_validate({**base, "decision": "reject", "weakens_gate": False})
    ok = GateDecide.model_validate({**base, "decision": "reject", "weakens_gate": True,
                                    "explanation": "deterministic check is feasible"})
    assert ok.decision == "reject"


def test_fix_attempt_blocked_iff_and_keywords_pattern():
    from harness import FixAttempt
    base = {"status": "fixed", "comment": "c", "tests_run": ["pytest"], "new_issues": []}
    FixAttempt.model_validate(base)
    with pytest.raises(ValidationError, match="blocked_kind and blocked_reason"):
        FixAttempt.model_validate({**base, "status": "blocked"})
    with pytest.raises(ValidationError, match="forbidden"):
        FixAttempt.model_validate({**base, "blocked_kind": "technical", "blocked_reason": "r"})
    blocked = FixAttempt.model_validate({**base, "status": "blocked",
                                         "blocked_kind": "design-question",
                                         "blocked_reason": "needs a D9 decision"})
    assert blocked.blocked_kind == "design-question"
    with pytest.raises(ValidationError):
        FixAttempt.model_validate({**base, "new_issues": [{"keywords": "Bad Term", "description": "d",
                                                           "blocked": False}]})
    FixAttempt.model_validate({**base, "new_issues": [{"keywords": "session expiry-ttl ttl_2",
                                                       "description": "d", "blocked": False}]})


def test_lesson_topic_key_rules():
    from harness import Lesson
    base = {"line": "l", "provenance_task_id": "N-1", "provenance_ref": "ledger:fp-1"}
    with pytest.raises(ValidationError):
        Lesson.model_validate({**base, "topic_key": []})  # 0 terms
    with pytest.raises(ValidationError):
        Lesson.model_validate({**base, "topic_key": [f"t{i}" for i in range(7)]})  # 7 terms
    with pytest.raises(ValidationError, match="stopword"):
        Lesson.model_validate({**base, "topic_key": ["the", "python"]})
    with pytest.raises(ValidationError, match="a-z0-9_-"):
        Lesson.model_validate({**base, "topic_key": ["Python"]})  # non-normalized case
    Lesson.model_validate({**base, "topic_key": ["python", "iterator", "gotcha"]})


def test_debug_judge_ranks_unique_contiguous():
    from harness import DebugJudge
    base = {"status": "ok", "comment": "c", "blame": "code", "problem": "p"}

    def fixes(*ranks):
        return [{"rank": r, "approach": "a", "how": "h"} for r in ranks]

    DebugJudge.model_validate({**base, "fixes": fixes(1, 2)})
    with pytest.raises(ValidationError, match="contiguous"):
        DebugJudge.model_validate({**base, "fixes": fixes(2)})
    with pytest.raises(ValidationError, match="unique"):
        DebugJudge.model_validate({**base, "fixes": fixes(1, 1)})
    with pytest.raises(ValidationError):
        DebugJudge.model_validate({**base, "fixes": fixes(1, 2, 3, 4, 5, 6)})  # cap 5
    with pytest.raises(ValidationError):
        DebugJudge.model_validate({**base, "fixes": []})  # min 1


def test_judge_aspect_rules():
    from harness import JudgeAspect, build_judge_aspect_model
    base = {"status": "ok", "comment": "c", "aspect": "spec-match", "target_ac_id": "AC-1",
            "confidence": "high"}
    with pytest.raises(ValidationError, match="evidence"):
        JudgeAspect.model_validate({**base, "verdict": "fail", "evidence": ""})
    ctx = {"ac_map": {"AC-1"}}
    with pytest.raises(ValidationError, match="AC map"):
        JudgeAspect.model_validate({**base, "verdict": "pass", "evidence": "e",
                                    "target_ac_id": "AC-2"}, context=ctx)
    per_run = build_judge_aspect_model(["spec-match", "test-meaningfulness"])
    env = per_run.model_validate({**base, "verdict": "pass", "evidence": "e"})
    assert env.aspect == "spec-match"
    with pytest.raises(ValidationError):
        per_run.model_validate({**base, "aspect": "no-corner-cutting", "verdict": "pass", "evidence": "e"})


def test_check_kind_enum_closed():
    from harness import DraftAC
    with pytest.raises(ValidationError):
        DraftAC.model_validate({"ac_id": "AC-1", "statement": "s", "check_kind": "vibes"})
    entry = DraftAC.model_validate({"ac_id": "AC-1", "statement": "s", "check_kind": "script-assertion",
                                    "check_hint": "assert sessions.expire()"})
    assert entry.check_kind == "script-assertion"


def test_fix_plan_schema_round_trip_and_bounds():
    """fix_plan (ticket 05 A/B): registry resolves; 2-8 steps enforced; unable
    alternative available like every envelope."""
    from harness.envelopes import SCHEMAS
    from pydantic import ValidationError

    assert SCHEMAS["fix_plan"].__name__ == "FixPlan"
    ok = SCHEMAS["fix_plan"].model_validate({
        "status": "ok", "comment": "3 steps",
        "steps": ["add env lookup first", "return default after", "keep types"]})
    assert ok.steps[0].startswith("add env")
    with pytest.raises(ValidationError):
        SCHEMAS["fix_plan"].model_validate({"status": "ok", "comment": "1 step", "steps": ["only"]})
    with pytest.raises(ValidationError):
        SCHEMAS["fix_plan"].model_validate({
            "status": "ok", "comment": "9 steps", "steps": [f"s{i}" for i in range(9)]})
    un = SCHEMAS["fix_plan"].model_validate(
        {"status": "unable", "comment": "c", "unable_reason": "unclear contract"})
    assert un.status == "unable"
