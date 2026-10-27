"""Tree-sitter parse-on-arrival + the bounded repair respawn (docs/6_ARCHITECTURE.md §4.7)."""

import asyncio

import pytest

from harness import (
    EnvelopeSpec,
    FakeModelRunner,
    FailureSummary,
    SchemaViolation,
    ledger_entries,
    llm_step,
    reset_ledger_for_tests,
)
from harness.repair import broken_excerpt, parse_python

BROKEN = (
    "def test_lockout_window():\n"         # 1
    "    user = make_user()\n"             # 2
    "    for _ in range(5):\n"             # 3
    "        login(user, wrong=True)\n"    # 4
    "    assert is_locked(user)\n"         # 5
    "    assert window(user) == 900\n"     # 6
    "    assert reset_on_success(user)\n"  # 7
    "\n"                                   # 8
    "def test_success_resets():\n"         # 9
    "    user = make_user(locked=True)\n"  # 10
    "    login(user, wrong=False)\n"       # 11
    "    assert not is_locked(user) :\n"   # 12  <- stray colon: syntax error
    "    assert count(user) == 0\n"        # 13
)
FIXED = BROKEN.replace("assert not is_locked(user) :", "assert not is_locked(user)")


def _spec(content: str, comment: str) -> EnvelopeSpec:
    return EnvelopeSpec(body={"status": "ok", "comment": comment,
                              "file_path": "tests/test_lockout.py", "content": content})


def test_parse_python_flags_and_locates_the_first_error():
    ok, node = parse_python(BROKEN)
    assert not ok and node is not None
    assert node.start_point[0] == 11  # 0-based row of line 12
    ok2, node2 = parse_python(FIXED)
    assert ok2 and node2 is None


def test_broken_excerpt_is_bounded_and_marked():
    _, node = parse_python(BROKEN)
    excerpt = broken_excerpt(BROKEN, node)
    assert "12 |" in excerpt and "first parse error here" in excerpt
    assert "13 |" in excerpt          # +radius reaches line 13
    assert " 1 |" not in excerpt      # -radius stops at line 7 — line 1 is outside


def test_repair_respawn_flow():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"write_test": [
        _spec(BROKEN, "Wrote the lockout tests."),
        _spec(FIXED, "Rewrote the lockout tests; parse clean."),
    ]})
    env = asyncio.run(llm_step(fake, "write_test",
                               artifacts={"spec": "AC-1 lockout window"},
                               question="Write the lockout tests."))
    assert env.content == FIXED
    calls = fake.calls("write_test")
    assert len(calls) == 2                      # outer + exactly ONE respawn
    p2 = calls[1].prompt
    assert "first parse error here" in p2       # bounded broken excerpt (§4.7)
    assert "12 |" in p2
    assert "AC-1 lockout window" in p2          # ground truth re-injected
    assert "Wrote the lockout tests." not in p2  # failed attempt's comment erased (§2.4a)
    kinds = [e["kind"] for e in ledger_entries()]
    assert "repair_attempted" in kinds and "repair_ok" in kinds
    assert kinds.count("llm_invocation") == 2   # outer + respawn


def test_repair_exhaustion_then_erasure_contract_holds():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"write_test": [
        _spec(BROKEN, "attempt one"),
        _spec(BROKEN, "attempt two"),
        _spec(FIXED, "attempt three"),
    ]})
    with pytest.raises(SchemaViolation, match="still fails to parse"):
        asyncio.run(llm_step(fake, "write_test", artifacts={"spec": "AC-1"},
                             question="Write the lockout tests."))
    kinds = [e["kind"] for e in ledger_entries()]
    assert "repair_failed" in kinds and "repair_ok" not in kinds
    # ordinary erasure retry: summary + ground truth, never the failed text
    env = asyncio.run(llm_step(fake, "write_test", artifacts={"spec": "AC-1"},
                               question="Retry.",
                               failure=FailureSummary(step_type="write_test",
                                                      summary="content unparseable; rewrite complete file.")))
    assert env.content == FIXED
    p3 = fake.calls("write_test")[2].prompt
    assert "content unparseable" in p3
    assert "attempt one" not in p3 and "attempt two" not in p3
    assert "def test_lockout_window" not in p3
