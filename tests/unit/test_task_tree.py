"""Task-tree rules — TEST_PLAN §3.8 (all pure, plus two fake-model tests for the
propose≠decide and grounding rules)."""

import asyncio
import json

import pytest

from harness import (
    ArtifactRef,
    CheckResults,
    FakeModelRunner,
    SchemaViolation,
    StatusTransitionInvalid,
    TaskTree,
    EnvelopeSpec,
    llm_step,
    reset_ledger_for_tests,
)


def leaf_map(command: str, ac_id: str = "AC-1", kind: str = "test") -> dict:
    entry = {"ac_id": ac_id, "statement": "session expires per spec", "check_kind": kind,
             "check_hint": None, "command": None}
    if kind == "subjective":
        entry["check_hint"] = command
    else:
        entry["check_hint"] = command if kind == "test" else None
        entry["command"] = command
    return entry


def close_leaf(handle, command: str):
    handle.set_ac_test_map([leaf_map(command)])
    return handle.close(CheckResults(verdicts={command: "pass"}))


# ---------------------------------------------------------------------------
# AC map rules (KERNEL_API §4.2)
# ---------------------------------------------------------------------------


def test_leaf_ac_map_mandatory_internal_optional():
    t = TaskTree("Fix session expiry")
    leaf = t.insert_ticket(t.root, "Fix expiry computation")
    findings = leaf.set_ac_test_map([])  # leaf with empty map → findings
    assert findings.items and findings.items[0].kind == "empty-leaf-map"
    # and a leaf without a map cannot close
    assert not leaf.close(CheckResults())

    internal = t.insert_ticket(t.root, "Integration node")
    inner = t.insert_ticket(internal, "Inner leaf")
    assert not internal.set_ac_test_map([]).items  # internal with empty map → accepted
    assert close_leaf(inner, "pytest tests/test_inner.py")
    r = internal.close(CheckResults())  # closes on (c) alone
    assert r and r.reasons == []
    assert internal.status == "done"


def test_internal_ac_entry_must_resolve_to_descendant_check():
    t = TaskTree("Fix session expiry")
    leaf = t.insert_ticket(t.root, "Fix expiry computation")
    assert close_leaf(leaf, "pytest tests/test_calc.py")
    # internal entry naming a command no descendant owns
    findings = t.root.set_ac_test_map([
        {"ac_id": "AC-9", "statement": "integration view", "check_kind": "script-assertion",
         "command": "pytest tests/test_ghost.py"}])
    assert not findings.items
    r = t.root.close(CheckResults(verdicts={"pytest tests/test_ghost.py": "pass"}))
    assert not r
    assert any("resolves to no descendant check" in s and "test_ghost" in s for s in r.reasons)
    # fixed: entry resolving to the check a descendant already owns — references, not copies
    t.root.set_ac_test_map([
        {"ac_id": "AC-9", "statement": "integration view", "check_kind": "script-assertion",
         "command": "pytest tests/test_calc.py"}])
    assert t.root.close(CheckResults(verdicts={"pytest tests/test_calc.py": "pass"}))


# ---------------------------------------------------------------------------
# Closure gate (kernel code, never an llm() call)
# ---------------------------------------------------------------------------


def test_closure_gate_requires_three_conditions():
    fake = FakeModelRunner({})  # any model call would exhaust the script → AssertionError
    t = TaskTree("Fix session expiry")
    leaf = t.insert_ticket(t.root, "Fix expiry computation")
    leaf.set_ac_test_map([leaf_map("pytest tests/test_a.py", "AC-1"),
                          leaf_map("pytest tests/test_b.py", "AC-2")])
    # (a) AC-2's check has no verdict (missing test) → no close
    r = leaf.close(CheckResults(verdicts={"pytest tests/test_a.py": "pass"}))
    assert not r and any("test_b.py" in s for s in r.reasons)
    # (b) skipped/flaky is not a pass → no close
    r = leaf.close(CheckResults(verdicts={"pytest tests/test_a.py": "pass",
                                          "pytest tests/test_b.py": "skip"}))
    assert not r and any("verdict='skip'" in s for s in r.reasons)
    # (c) child open → no close (on an internal node)
    t2 = TaskTree("root2")
    child = t2.insert_ticket(t2.root, "Child")
    assert close_leaf(child, "pytest tests/test_a.py")
    t2.root.set_ac_test_map([{"ac_id": "AC-9", "statement": "integration",
                              "check_kind": "script-assertion",
                              "command": "pytest tests/test_a.py"}])
    other = t2.insert_ticket(t2.root, "Other child")  # open sibling
    r = t2.root.close(CheckResults(verdicts={"pytest tests/test_a.py": "pass"}))
    assert not r and any("children not closed" in s and other.id in s for s in r.reasons)
    # all three green → close — and the decision was kernel code, not an llm() call
    assert leaf.close(CheckResults(verdicts={"pytest tests/test_a.py": "pass",
                                             "pytest tests/test_b.py": "pass"}))
    assert leaf.status == "done"
    assert fake.total_calls == 0


def test_subjective_ac_closes_only_with_judge_verdict():
    t = TaskTree("root")
    leaf = t.insert_ticket(t.root, "L")
    leaf.set_ac_test_map([leaf_map("judge the UI", kind="subjective")])
    r = leaf.close(CheckResults(verdicts={}))
    assert not r and any("judge verdict" in s for s in r.reasons)
    assert leaf.close(CheckResults(), verdicts={"AC-1": "pass"})


# ---------------------------------------------------------------------------
# Cascade rules (DESIGN §4.8)
# ---------------------------------------------------------------------------


def test_reopen_done_parent_on_child_edit():
    t = TaskTree("Fix session expiry")
    leaf = t.insert_ticket(t.root, "Fix expiry computation", files=["middleware/auth.py"])
    assert close_leaf(leaf, "pytest tests/test_auth.py")
    t.refresh_status()
    assert t.root.status == "done"  # mapless internal closed on (c) alone
    t.insert_ticket(t.root, "Follow-up ticket from review")  # modify under done parent
    assert t.root.status == "in-progress"  # parent reopened, its AC map re-runs at close
    assert leaf.status == "stale"  # touched branch → descendants stale
    assert t.has_work()
    # root cannot close while the new child is open
    t.refresh_status()
    assert t.root.status == "in-progress"


def test_touched_branch_marks_children_stale():
    t = TaskTree("root")
    branch = t.insert_ticket(t.root, "Branch")
    l1 = t.insert_ticket(branch, "L1", files=["a.py"])
    l2 = t.insert_ticket(branch, "L2", files=["b.py"])
    for leaf, cmd in ((l1, "pytest tests/test_a.py"), (l2, "pytest tests/test_b.py")):
        assert close_leaf(leaf, cmd)
    t.refresh_status()
    assert branch.status == "done" and t.root.status == "done"
    t.insert_ticket(branch, "L3")  # edit the branch node
    assert branch.status == "in-progress"
    assert l1.status == "stale" and l2.status == "stale"  # all descendants stale
    assert t.root.status == "in-progress"  # parents re-validate upward
    assert t.has_work()
    # stale leaves cannot close until re-verified: no fresh green results → refused
    r = l1.close(CheckResults(verdicts={}))
    assert not r
    assert close_leaf(l1, "pytest tests/test_a.py")  # re-verified → closes
    assert l1.status == "done"


def test_status_transition_validation_at_commit():
    t = TaskTree("root")
    leaf = t.insert_ticket(t.root, "L")
    leaf.status = "done"  # pending → done bypasses the gate
    assert leaf.status == "done"  # observable between assignment and commit (KERNEL_API G4)
    assert t.snapshot()["status"] == "pending"  # committed state unchanged
    with pytest.raises(StatusTransitionInvalid):
        t.commit()
    committed_leaf = t.snapshot()["children"][0]
    assert committed_leaf["status"] == "pending"  # nothing applied
    t2 = TaskTree("root2")
    leaf2 = t2.insert_ticket(t2.root, "L")
    leaf2.status = "in-progress"
    t2.commit()
    leaf2.status = "done"
    t2.commit()
    assert leaf2.status == "done"


# ---------------------------------------------------------------------------
# DAG validation (KERNEL_API §4.1 — findings, never exceptions)
# ---------------------------------------------------------------------------


def test_dag_validation_rejects_orphan_duplicate_producer_cycle():
    # orphan input
    t1 = TaskTree("root")
    t1.insert_ticket(t1.root, "A", output=["art-a"])
    t1.insert_ticket(t1.root, "B", input=[ArtifactRef(artifact_id="ghost", producer_id="N-9")])
    f1 = t1.validate_dag()
    assert not f1.ok
    assert {f.kind for f in f1.items} == {"orphan-input"}
    # duplicate producer
    t2 = TaskTree("root")
    t2.insert_ticket(t2.root, "A", output=["x"])
    t2.insert_ticket(t2.root, "B", output=["x"])
    f2 = t2.validate_dag()
    assert {f.kind for f in f2.items} == {"duplicate-producer"}
    # cycle: ids are kernel-assigned in insertion order (root=N-1, A=N-2, B=N-3)
    t3 = TaskTree("root")
    t3.insert_ticket(t3.root, "A", output=["a"], input=[ArtifactRef(artifact_id="b", producer_id="N-3")])
    t3.insert_ticket(t3.root, "B", output=["b"], input=[ArtifactRef(artifact_id="a", producer_id="N-2")])
    f3 = t3.validate_dag()
    assert {f.kind for f in f3.items} == {"cycle"}
    # clean DAG → no findings
    t4 = TaskTree("root")
    t4.insert_ticket(t4.root, "A", output=["a"])
    t4.insert_ticket(t4.root, "B", input=[ArtifactRef(artifact_id="a", producer_id="N-2")], output=["b"])
    assert t4.validate_dag().ok


# ---------------------------------------------------------------------------
# Writer grouping (KERNEL_API §4.1 ready_leaves)
# ---------------------------------------------------------------------------


def test_file_overlap_serializes_writers():
    t = TaskTree("root")
    a = t.insert_ticket(t.root, "A", files=["calc.py"])
    b = t.insert_ticket(t.root, "B", files=["calc.py"])
    c = t.insert_ticket(t.root, "C", files=["docs.md"])
    # overlapping writers: one ready per group; disjoint leaf ready alongside
    assert [n.id for n in t.ready_leaves()] == [a.id, c.id]
    a.status = "in-progress"
    t.commit()
    assert [n.id for n in t.ready_leaves()] == [c.id]  # group locked by the in-progress writer
    assert close_leaf(a, "pytest tests/test_calc.py")
    t.refresh_status()
    assert [n.id for n in t.ready_leaves()] == [b.id, c.id]  # group freed → next writer ready
    # deps gate readiness: D consumes an artifact only C produces
    d = t.insert_ticket(t.root, "D", input=[ArtifactRef(artifact_id="doc", producer_id=c.id)])
    assert d.id not in [n.id for n in t.ready_leaves()]


# ---------------------------------------------------------------------------
# Propose ≠ decide + grounding (fake-model tests; TEST_PLAN §3.8)
# ---------------------------------------------------------------------------


def test_ac_map_is_decided_not_self_approved():
    """canned draft_acs proposes a subjective AC where a deterministic check is
    feasible → canned gate_decide rejects → the map is NOT frozen; the gate_decide
    call ran fresh=True, in a session without the author's context."""
    reset_ledger_for_tests()
    fake = FakeModelRunner({
        "draft_acs": [EnvelopeSpec(body={
            "status": "ok",
            "comment": "Authored one AC for the leaf.",
            "acs": [{"ac_id": "AC-1", "statement": "Session expiry behaves per spec",
                     "check_kind": "subjective", "check_hint": "judge whether expiry matches spec"}],
        })],
        "gate_decide": [EnvelopeSpec(body={
            "status": "ok",
            "comment": "Reject: a deterministic test is feasible; subjective inflation weakens the gate.",
            "decision": "reject", "reason_is_real": True, "weakens_gate": True,
            "meaning_preserved": False,
            "explanation": "pytest can assert expiry deterministically; the subjective check is not justified.",
        })],
    })
    t = TaskTree("Fix session expiry")
    leaf = t.insert_ticket(t.root, "Fix expiry computation", files=["middleware/auth.py"])
    author_context = "AUTHOR-WORKSPACE: draft notes and working transcript of the author"
    acs = asyncio.run(llm_step(
        fake, "draft_acs",
        artifacts={"node": json.dumps(t.snapshot()), "author_workspace": author_context},
        question="Author the AC map for this leaf from the frozen spec.",
        context={"node_kind": "leaf"}))
    verdict = asyncio.run(llm_step(
        fake, "gate_decide",
        artifacts={"map": json.dumps([a.model_dump() for a in acs.acs])},
        question=f"Validate the REASON for this proposed gate map: "
                 f"{json.dumps([a.model_dump() for a in acs.acs])}. Evidence refs resolve. "
                 f"Reviewer note: {acs.comment}",
        fresh=True))
    assert verdict.decision == "reject" and verdict.weakens_gate
    assert leaf.ac_test_map == []  # map not frozen — decided, not self-approved
    assert len(fake.calls("draft_acs")) == 1 and len(fake.calls("gate_decide")) == 1
    rec = fake.calls("gate_decide")[0]
    assert rec.fresh
    assert author_context not in rec.prompt  # no author context in the fresh session
    assert "AC-1" in rec.prompt  # the decider sees the proposed map via the question


def test_ungrounded_child_reference_rejected():
    """canned expand child whose `what` names a file outside the injected candidate
    scope + symbol DB → kernel rejects the child (enum-first rule on the free
    strings); an invented file cannot enter the plan."""
    fake = FakeModelRunner({"expand": [EnvelopeSpec(body={
        "status": "ok", "comment": "Proposed one child.",
        "children": [{"seam_id": "seam-1", "what": "Fix divide-by-zero in utils/sessions.py",
                      "why": "Central enforcement point for all routes", "leaf": True,
                      "est_rounds": 3}]})]})
    context = {"candidate_seams": {"seam-1": {"files": ["middleware/auth.py"],
                                              "rationale": "auth middleware seam"}},
               "known_symbols": set()}
    with pytest.raises(SchemaViolation, match="ungrounded reference"):
        asyncio.run(llm_step(fake, "expand", artifacts={"candidates": "injected above"},
                             question="Fill child tasks along the seams.", context=context))
    # control: a grounded child passes the same check
    fake2 = FakeModelRunner({"expand": [EnvelopeSpec(body={
        "status": "ok", "comment": "Proposed one child.",
        "children": [{"seam_id": "seam-1", "what": "Add expires_at check in middleware/auth.py",
                      "why": "Central enforcement point for all routes", "leaf": True,
                      "est_rounds": 3}]})]})
    env = asyncio.run(llm_step(fake2, "expand", artifacts={}, question="Fill child tasks.",
                               context=context))
    assert env.children[0].what.startswith("Add expires_at")


def test_numeric_tokens_are_not_file_references():
    """FP-10: '4.5' / '1.2.3' match the file-token shape but are values — the
    grounding check must not reject a child for naming a number (T-20 false
    positive, sweep 20260917T100148Z)."""
    fake = FakeModelRunner({"expand": [EnvelopeSpec(body={
        "status": "ok", "comment": "Proposed one child.",
        "children": [{"seam_id": "seam-1",
                      "what": "Make average return 4.5 for the [4, 5] case",
                      "why": "Mean of 4 and 5 is 4.5, not the truncated 1.2", "leaf": True,
                      "est_rounds": 2}]})]})
    context = {"candidate_seams": {"seam-1": {"files": ["ratings/stats.py"],
                                              "rationale": "stats seam"}},
               "known_symbols": set()}
    env = asyncio.run(llm_step(fake, "expand", artifacts={}, question="Fill child tasks.",
                               context=context))
    assert "4.5" in env.children[0].what


def test_request_named_file_is_grounded():
    """FP-10: a file the REQUEST names for creation (scaffold tasks) is grounded
    by definition — the composer injects request-named tokens into the scope
    (T-28 false positive, sweep 20260917T100148Z)."""
    from harness.envelopes import file_tokens

    assert file_tokens("create the module plugins/registry.py with register()") == {
        "plugins/registry.py"}
    fake = FakeModelRunner({"expand": [EnvelopeSpec(body={
        "status": "ok", "comment": "Proposed one child.",
        "children": [{"seam_id": "seam-1",
                      "what": "Create plugins/registry.py with register/get/run",
                      "why": "The request names this module as the deliverable", "leaf": True,
                      "est_rounds": 2}]})]})
    context = {"candidate_seams": {"seam-1": {"files": ["plugins/__init__.py"],
                                              "rationale": "plugin pkg seam"}},
               "grounding_files": {"plugins/__init__.py", "plugins/registry.py"},
               "known_symbols": set()}
    env = asyncio.run(llm_step(fake, "expand", artifacts={}, question="Fill child tasks.",
                               context=context))
    assert env.children[0].what.startswith("Create plugins")


def test_insert_attempt_makes_a_sibling():
    t = TaskTree("root")
    first = t.insert_ticket(t.root, "Attempt 1: hypothesis A")
    second = t.insert_attempt(first, "Attempt 2: hypothesis B")
    assert second.parent.id == t.root.id  # next hypothesis = new sibling (DESIGN §4.8)
    assert first.parent.id == second.parent.id
