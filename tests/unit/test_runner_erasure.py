"""Erasure semantics (DESIGN §2.4, TEST_PLAN §3.4): a retry prompt contains the
honest failure summary + ground truth — never the failed attempt's text — while the
append-only ledger retains the failed attempt as evidence."""

import ast
import asyncio

import pytest

from harness import (
    EnvelopeSpec,
    FakeModelRunner,
    FailureSummary,
    SchemaViolation,
    compose_prompt,
    code_with_syntax_error,
    ledger_entries,
    llm_step,
    malformed_json,
    render_prompt,
    reset_ledger_for_tests,
)

GROUND_TRUTH = "SPEC: sessions expire after 1h — assert expires_at(3601) is expired"


def _broken_attempt_text() -> str:
    return code_with_syntax_error().body["content"]


def test_broken_code_respawned_with_excerpt_not_failed_text():
    """§4.7 + §2.4 interplay: a parse-broken write_test is respawned ONCE with the
    bounded broken excerpt + ground truth — never the failed attempt's comment or
    narrative; the ledger records repair_attempted/repair_ok."""
    reset_ledger_for_tests()
    fake = FakeModelRunner({"write_test": [
        code_with_syntax_error(),  # attempt 1: valid envelope, broken Python
        EnvelopeSpec(body={        # repair respawn: clean rewrite
            "status": "ok", "comment": "Rewrote the test file; parse is clean.",
            "file_path": "tests/test_auth.py",
            "content": "def test_expiry():\n    assert expires_at(3601) == 'expired'\n",
        })]})
    env1 = asyncio.run(llm_step(fake, "write_test", artifacts={"spec": GROUND_TRUTH},
                                question="Write the test file for AC-1."))
    assert ast.parse(env1.content)                      # repaired content parses
    calls = fake.calls("write_test")
    assert len(calls) == 2                              # outer + ONE repair respawn
    p2 = render_prompt(calls[1])
    assert "first parse error here" in p2               # broken excerpt injected (§4.7)
    assert GROUND_TRUTH in p2                           # ground truth re-injected
    assert "Wrote the test file." not in p2             # failed attempt's comment erased (§2.4a)
    kinds = [e["kind"] for e in ledger_entries()]
    assert "repair_attempted" in kinds and "repair_ok" in kinds
    assert kinds.count("llm_invocation") == 2


def test_after_repair_exhaustion_erasure_contract_holds():
    """When repair also fails (§4.7 → SchemaViolation), the ordinary erasure path
    takes over: the next retry sees the failure summary + ground truth, never the
    failed attempts' text."""
    reset_ledger_for_tests()
    broken = code_with_syntax_error()
    fake = FakeModelRunner({"write_test": [
        broken,
        broken,
        EnvelopeSpec(body={"status": "ok", "comment": "clean now",
                           "file_path": "tests/test_auth.py",
                           "content": "def test_expiry():\n    assert expires_at(3601) == 'expired'\n"}),
    ]})
    with pytest.raises(SchemaViolation, match="still fails to parse"):
        asyncio.run(llm_step(fake, "write_test", artifacts={"spec": GROUND_TRUTH},
                             question="Write the test file for AC-1."))
    kinds = [e["kind"] for e in ledger_entries()]
    assert "repair_failed" in kinds and "repair_ok" not in kinds
    summary = FailureSummary(step_type="write_test",
                             summary="write_test: content failed the Python parse; rewrite the complete file.",
                             missing=[])
    env3 = asyncio.run(llm_step(fake, "write_test", artifacts={"spec": GROUND_TRUTH},
                                question="Retry the test file write.", failure=summary))
    assert ast.parse(env3.content)
    p3 = render_prompt(fake.calls("write_test")[2])
    assert "failed the Python parse" in p3              # honest summary present
    assert GROUND_TRUTH in p3
    assert _broken_attempt_text() not in p3             # failed attempts' text erased
    assert 'assert expires_at(61)' not in p3


def test_retry_prompt_after_schema_violation_erases_raw_output():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"task_card": [
        malformed_json(),
        EnvelopeSpec(body={"status": "ok", "comment": "c", "task_class": "bugfix",
                           "goal": "Fix session expiry."})]})
    with pytest.raises(SchemaViolation):
        asyncio.run(llm_step(fake, "task_card", artifacts={"request": "fix expiry"},
                             question="Extract the goal."))
    summary = FailureSummary(step_type="task_card",
                             summary="task_card: output was malformed JSON; re-emit one envelope.",
                             missing=["valid JSON envelope"])
    env = asyncio.run(llm_step(fake, "task_card", artifacts={"request": "fix expiry"},
                               question="Retry.", failure=summary))
    assert env.goal == "Fix session expiry."
    prompt2 = render_prompt(fake.calls("task_card")[1])
    assert "malformed JSON" in prompt2
    assert '{"status": "ok", "comment": "partial' not in prompt2  # raw failed output erased
    kinds = [e["kind"] for e in ledger_entries()]
    assert "validation_failed" in kinds and kinds.count("llm_invocation") == 2


def test_failure_summary_never_enters_prompt_composer_from_attempt():
    """compose_prompt is a pure function of its arguments: no path can pull a failed
    attempt's text in — the only failure channel is FailureSummary."""
    broken = _broken_attempt_text()
    p = compose_prompt("write_test", {"spec": GROUND_TRUTH}, "retry",
                       failure=FailureSummary(step_type="write_test", summary="parse error"))
    assert "parse error" in p and broken not in p


def test_unable_alternative_flows_through_the_glue():
    from harness import unable as unable_helper
    fake = FakeModelRunner({"propose_probe": [unable_helper("no probe distinguishes the hypotheses")]})
    env = asyncio.run(llm_step(fake, "propose_probe", artifacts={}, question="Next probe?"))
    assert env.status == "unable"
    assert env.unable_reason == "no probe distinguishes the hypotheses"


def test_unknown_step_type_is_a_programmer_error():
    fake = FakeModelRunner({})
    with pytest.raises(KeyError, match="unknown step_type"):
        asyncio.run(llm_step(fake, "not_a_step", artifacts={}, question="q"))
    assert fake.total_calls == 0
