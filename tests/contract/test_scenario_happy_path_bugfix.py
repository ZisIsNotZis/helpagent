"""Contract test — the happy-path bugfix scenario executed against
FakeModelRunner over a stubbed task tree. This is docs/7_INTERFACE.md's executable form for
the golden flow: understand → plan (clean trial split) → DAG validated → spec → AC map
authored+decided → parallel code+tests → gate → run summary."""

import asyncio
import json

from harness import (
    CheckResults,
    EnvelopeSpec,
    FakeModelRunner,
    RunSummary,
    TaskTree,
    llm_step,
    reset_ledger_for_tests,
)

REQUEST = ("Sessions expire after 60s instead of 1h — fix the computation. "
           "No new dependencies; public API stays backward compatible.")

CANDIDATE_SEAMS = {
    "seam-1": {"files": ["middleware/auth.py"], "rationale": "central expiry enforcement point"},
}
BOUNDARY = {"middleware/auth.py"}

SCRIPT: dict[str, list[EnvelopeSpec | dict]] = {
    "task_card": [EnvelopeSpec(body={
        "status": "ok", "comment": "Goal extracted; constraints and scope inline.",
        "task_class": "bugfix", "goal": REQUEST})],
    "find_ambiguities": [EnvelopeSpec(body={
        "status": "ok", "comment": "No blocking ambiguities; trial split was stable.",
        "items": []})],
    "expand": [EnvelopeSpec(body={
        "status": "ok", "comment": "One leaf along the central enforcement seam.",
        "children": [{"seam_id": "seam-1",
                      "what": "Fix the expiry computation in middleware/auth.py",
                      "why": "Central enforcement point for all routes",
                      "leaf": True, "est_rounds": 4}]})],
    "split_review": [EnvelopeSpec(body={
        "status": "ok", "comment": "Split is clean: one leaf, one artifact, one area.",
        "ok": True, "issues": []})],
    "draft_acs": [EnvelopeSpec(body={
        "status": "ok", "comment": "One deterministic AC derived from the frozen spec.",
        "acs": [{"ac_id": "AC-1", "statement": "A 1h session is valid; a 2h-old session is expired",
                 "check_kind": "test", "check_hint": "pytest tests/test_auth.py"}]})],
    "gate_decide": [EnvelopeSpec(body={
        "status": "ok", "comment": "Accept: reason describes reality; gate meaning preserved.",
        "decision": "accept", "reason_is_real": True, "weakens_gate": False,
        "meaning_preserved": True})],
    "write_spec": [EnvelopeSpec(body={
        "status": "ok", "comment": "Spec: expiry = session start + 1h, evaluated per request.",
        "interfaces": [{"name": "expires_at",
                        "signature": "def expires_at(session: Session) -> datetime",
                        "contract": "Returns session.start + 1h; never raises for live sessions."}],
        "behavior": "TTL is 3600 seconds from session.start; comparison in UTC.",
        "implementation_notes": "Change the TTL constant in middleware/auth.py only.",
        "files_touched": ["middleware/auth.py"]})],
    "spec_review": [EnvelopeSpec(body={
        "status": "ok", "comment": "Spec reviewed fresh: no blocking issues.",
        "ok": True, "issues": []})],
    "test_plan": [EnvelopeSpec(body={
        "status": "ok", "comment": "One case per AC edge: fresh-valid, stale-expired.",
        "cases": [{"case_id": "TC-1", "ac_id": "AC-1", "kind": "unit",
                   "description": "fresh session valid; 2h-old session expired"}]})],
    "write_test": [EnvelopeSpec(body={
        "status": "ok", "comment": "Wrote the complete test file for TC-1/AC-1.",
        "file_path": "tests/test_auth.py",
        "content": "def test_expiry():\n    assert expires_at(age_s=3600) is not None\n"
                   "    assert expires_at(age_s=7200) is None\n"})],
    "implement": [EnvelopeSpec(body={
        "status": "ok", "comment": "TTL constant corrected; tests green on the canonical command.",
        "tests_run": ["python -m pytest tests/test_auth.py"]})],
    "run_summary": [EnvelopeSpec(body={
        "status": "ok", "comment": "Run complete: bug fixed, gate green.",
        "outcome": "complete", "what_was_done": "Fixed the session TTL computation.",
        "what_changed": "middleware/auth.py", "what_remains": "Nothing open."})],
}


async def happy_path_bugfix(model: FakeModelRunner, tree: TaskTree) -> tuple[RunSummary, dict]:
    """The golden bugfix flow (docs/6_ARCHITECTURE.md §4.1) against the six-primitive-shaped surface.
    The script owns flow topology; every semantic decision stays harness-side."""
    envelopes: dict[str, object] = {}
    # -- understand --
    card = await llm_step(model, "task_card", artifacts={"request": REQUEST},
                          question="Extract: goal, constraints, out-of-scope.")
    amb = await llm_step(model, "find_ambiguities", artifacts={"task_card": card.model_dump()},
                         question="List high-risk ambiguities that block a correct plan.")
    assert amb.items == []  # stable: split cleanly, no forced choices
    # -- plan (propose-validate) --
    plan = await llm_step(model, "expand",
                          artifacts={"card": card.model_dump(), "candidates": json.dumps(CANDIDATE_SEAMS)},
                          question="Fill child tasks along the candidate seams.",
                          context={"candidate_seams": CANDIDATE_SEAMS})
    review = await llm_step(model, "split_review",
                            artifacts={"plan": plan.model_dump()},
                            question="Fresh-context review of this split.")
    assert review.ok and review.issues == []
    findings = tree.validate_dag()
    assert findings.ok, findings.items
    seam_files = CANDIDATE_SEAMS[plan.children[0].seam_id]["files"]
    leaf = tree.insert_ticket(tree.root, plan.children[0].what, files=seam_files)
    # -- gate definition: authored by draft_acs, decided by fresh gate_decide --
    acs = await llm_step(model, "draft_acs", artifacts={"node": json.dumps(tree.snapshot())},
                         question="Author the leaf's AC map from the frozen spec.",
                         context={"node_kind": "leaf"})
    verdict = await llm_step(model, "gate_decide",
                             artifacts={"map": json.dumps([a.model_dump() for a in acs.acs])},
                             question=f"Decide this proposed gate map: "
                                      f"{json.dumps([a.model_dump() for a in acs.acs])}",
                             fresh=True)
    assert verdict.decision == "accept"
    assert not leaf.set_ac_test_map([a.model_dump() for a in acs.acs]).items  # frozen after accept
    # -- spec, then parallel code+tests against the map --
    spec = await llm_step(model, "write_spec", artifacts={"card": card.model_dump()},
                          question="Write the professional spec within the leaf boundary.",
                          context={"boundary_files": BOUNDARY})
    spec_rev = await llm_step(model, "spec_review", artifacts={"spec": spec.model_dump()},
                              question="Review the spec fresh-context.", fresh=True)
    assert spec_rev.ok
    plan_tests = await llm_step(model, "test_plan",
                                artifacts={"map": json.dumps([a.model_dump() for a in acs.acs]),
                                           "spec": spec.model_dump()},
                                question="Enumerate concrete cases per AC.",
                                context={"ac_map": {a.ac_id for a in acs.acs}})
    assert {c.ac_id for c in plan_tests.cases} == {a.ac_id for a in acs.acs}  # full coverage
    test_env = await llm_step(model, "write_test",
                              artifacts={"case": plan_tests.cases[0].model_dump()},
                              question="Write the complete test file for TC-1.")
    envelopes["write_test"] = test_env
    impl = await llm_step(model, "implement", artifacts={"spec": spec.model_dump()},
                          question="Implement within the boundary; run the canonical tests.")
    envelopes["implement"] = impl
    # -- gate: deterministic results; closure decided by kernel code, not the model --
    gate_results = CheckResults(verdicts={"pytest tests/test_auth.py": "pass"})
    assert leaf.close(gate_results)
    tree.refresh_status()
    # -- run summary from ground truth --
    summary = await llm_step(model, "run_summary",
                             artifacts={"tree": json.dumps(tree.snapshot()),
                                        "implement_report": impl.model_dump()},
                             question="Summarize what was done, what changed, what remains.")
    return summary, envelopes


def test_scenario_happy_path_bugfix():
    reset_ledger_for_tests()
    fake = FakeModelRunner(SCRIPT)
    tree = TaskTree("Fix session expiry", files=list(BOUNDARY))
    summary, envelopes = asyncio.run(happy_path_bugfix(fake, tree))

    # call counts per step_type match the script's topology — exactly one call each
    expected = dict.fromkeys(SCRIPT, 1)
    actual = {step: len(fake.calls(step)) for step in SCRIPT}
    assert actual == expected, actual
    assert fake.total_calls == len(SCRIPT)

    # the tree closes: leaf done with a green gate, mapless root closed on (c) alone
    assert tree.root.status == "done"
    assert tree.root.children[0].status == "done"
    assert not tree.has_work()

    # every model-authored artifact carries the mandatory self-summary (docs/6_ARCHITECTURE.md §4.2)
    assert summary.outcome == "complete" and summary.comment
    assert envelopes["write_test"].comment
    assert envelopes["implement"].comment
    # the gate decision ran fresh (proposer ≠ decider), without author context
    assert fake.calls("gate_decide")[0].fresh
