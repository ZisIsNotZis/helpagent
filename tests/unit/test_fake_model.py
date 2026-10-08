"""FakeModelRunner contract —: FIFO per step_type, exhaustion ⇒
AssertionError, call records, misbehavior helpers."""

import asyncio

import pytest

from harness import (
    EnvelopeSpec,
    FakeModelRunner,
    code_with_syntax_error,
    malformed_json,
    ok_edit,
    render_prompt,
    schema_violation,
    unable,
)
from harness.runner import LLMRequest


def req(step_type: str, question: str = "q", fresh: bool = False, tools=None):
    return LLMRequest(step_type=step_type, artifacts={"spec": "ground truth"},
                      question=question, tools=list(tools or []), fresh=fresh,
                      prompt=f"PREFIX\nQUESTION: {question}")


def test_fifo_consumed_per_step_type():
    fake = FakeModelRunner({
        "task_card": [
            EnvelopeSpec(body={"status": "ok", "comment": "first", "task_class": "bugfix", "goal": "g1"}),
            EnvelopeSpec(body={"status": "ok", "comment": "second", "task_class": "bugfix", "goal": "g2"}),
        ],
        "find_ambiguities": [EnvelopeSpec(body={"status": "ok", "comment": "c", "items": []})],
    })
    first = asyncio.run(fake.complete(req("task_card")))
    amb = asyncio.run(fake.complete(req("find_ambiguities")))
    second = asyncio.run(fake.complete(req("task_card")))
    assert first["comment"] == "first" and second["comment"] == "second"  # FIFO, not LIFO
    assert amb["items"] == []
    assert [c.question for c in fake.calls("task_card")] == ["q", "q"]
    assert fake.total_calls == 3


def test_exhaustion_raises_assertion():
    fake = FakeModelRunner({"task_card": [
        EnvelopeSpec(body={"status": "ok", "comment": "only", "task_class": "bugfix", "goal": "g"})]})
    asyncio.run(fake.complete(req("task_card")))
    with pytest.raises(AssertionError, match="exhausted"):
        asyncio.run(fake.complete(req("task_card")))
    # unknown step_type (never scripted) is exhaustion too
    with pytest.raises(AssertionError, match="exhausted"):
        asyncio.run(fake.complete(req("run_summary")))


def test_scripted_exception_passthrough():
    boom = RuntimeError("budget backend exploded")
    fake = FakeModelRunner({"task_card": [boom]})
    with pytest.raises(RuntimeError):
        asyncio.run(fake.complete(req("task_card")))
    assert len(fake.calls("task_card")) == 1  # the failed call is still recorded


def test_raw_kind_bypasses_formatting():
    fake = FakeModelRunner({"task_card": [malformed_json()]})
    out = asyncio.run(fake.complete(req("task_card")))
    assert isinstance(out, str) and out.startswith('{"status": "ok", "comment": "partial')


def test_calls_record_artifacts_question_tools_fresh():
    fake = FakeModelRunner({"run_summary": [EnvelopeSpec(body={
        "status": "ok", "comment": "c", "outcome": "complete", "what_was_done": "d",
        "what_changed": "c", "what_remains": "r"})]})
    asyncio.run(fake.complete(req("run_summary", question="summarize", fresh=True, tools=["pytest"])))
    rec = fake.calls("run_summary")[0]
    assert rec.artifacts == {"spec": "ground truth"}
    assert rec.question == "summarize"
    assert rec.tools == ["pytest"]
    assert rec.fresh is True
    assert render_prompt(rec) == rec.prompt and "summarize" in rec.prompt


def test_plain_dict_and_step_type_inheritance():
    fake = FakeModelRunner({"task_card": [{"status": "ok", "comment": "c", "task_class": "port",
                                           "goal": "g"}]})
    out = asyncio.run(fake.complete(req("task_card")))
    assert out["task_class"] == "port"
    assert fake.calls("task_card")[0].step_type == "task_card"


def test_misbehavior_helpers_shapes():
    u = unable("no probe distinguishes the hypotheses")
    assert u.body == {"status": "unable", "comment": "Cannot proceed; reason recorded.",
                      "unable_reason": "no probe distinguishes the hypotheses"}
    sv = schema_violation()
    assert sv.kind == "ok" and "comment" not in sv.body and sv.body["status"] == "ok"
    sv2 = schema_violation(missing="goal")
    assert "goal" not in sv2.body and "comment" in sv2.body
    oe = ok_edit("calc.py", "NEW = 1")
    assert oe.body["status"] == "ok" and "calc.py" in oe.body["comment"]
    cse = code_with_syntax_error()
    assert cse.body["file_path"].endswith(".py") and ":\n" in cse.body["content"]
