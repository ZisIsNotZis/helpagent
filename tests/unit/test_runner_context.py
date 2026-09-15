"""The validation context is what makes the reference checks fire (seam grounding,
boundary subset, ac_id ∈ map — ENVELOPE_SCHEMAS "grammar enum per call"). Without it
they silently skip: legal in tests, a silent-off gate in a run. The skip must be loud
in the append-only ledger (owner decision, ticket 01; M1's runner injects context
always — this is the safety net, not the fix)."""

import asyncio

from harness import (
    EnvelopeSpec,
    FakeModelRunner,
    ledger_entries,
    llm_step,
    reset_ledger_for_tests,
)

EXPAND_BODY = {"status": "ok", "comment": "c", "children": [
    {"seam_id": "seam-api", "what": "Add the check in backend/api/auth.py", "why": "w",
     "leaf": True, "est_rounds": 3}]}


def _kinds() -> list[str]:
    return [e["kind"] for e in ledger_entries()]


def test_context_sensitive_step_without_context_is_flagged_in_ledger():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"expand": [EnvelopeSpec(body=EXPAND_BODY)]})
    asyncio.run(llm_step(fake, "expand", artifacts={}, question="Fill children."))  # no context=
    assert "validation_context_missing" in _kinds()


def test_context_sensitive_step_with_context_is_not_flagged():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"expand": [EnvelopeSpec(body=EXPAND_BODY)]})
    asyncio.run(llm_step(fake, "expand", artifacts={}, question="Fill children.",
                         context={"candidate_seams": {"seam-api": ["backend/api/auth.py"]}}))
    assert "validation_context_missing" not in _kinds()


def test_non_sensitive_step_without_context_is_not_flagged():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"task_card": [EnvelopeSpec(body={
        "status": "ok", "comment": "c", "task_class": "bugfix", "goal": "Fix session expiry."})]})
    asyncio.run(llm_step(fake, "task_card", artifacts={}, question="Extract the goal."))
    assert "validation_context_missing" not in _kinds()
