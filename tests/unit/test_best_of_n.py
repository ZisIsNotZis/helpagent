"""Best-of-N at decision points (DESIGN §4.7): sample N, deterministic checker
selects — here the checker is schema validation, first valid candidate wins."""

import asyncio

import pytest

from harness import (
    EnvelopeSpec,
    FakeModelRunner,
    SchemaViolation,
    ledger_entries,
    compose_prompt,
    llm_step,
    malformed_json,
    reset_ledger_for_tests,
)

GOOD_1 = {"status": "ok", "comment": "c", "task_class": "bugfix", "goal": "Fix session expiry."}
GOOD_2 = {"status": "ok", "comment": "c2", "task_class": "bugfix", "goal": "Different plan."}


def test_first_valid_candidate_wins_and_losers_are_ledgered():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"task_card": [malformed_json(), GOOD_1, GOOD_2]})
    env = asyncio.run(llm_step(fake, "task_card", artifacts={}, question="q", best_of_n=3))
    assert env.goal == "Fix session expiry."
    assert fake.total_calls == 2  # lazy fetch: stops at the first valid candidate
    kinds = [e["kind"] for e in ledger_entries()]
    assert kinds.count("llm_invocation") == 2
    assert kinds.count("validation_failed") == 1


def test_all_candidates_invalid_raises():
    reset_ledger_for_tests()
    fake = FakeModelRunner({"task_card": [malformed_json(), malformed_json()]})
    with pytest.raises(SchemaViolation, match="malformed JSON"):
        asyncio.run(llm_step(fake, "task_card", artifacts={}, question="q", best_of_n=2))
    assert fake.total_calls == 2
    kinds = [e["kind"] for e in ledger_entries()]
    assert kinds.count("llm_invocation") == 2 and kinds.count("validation_failed") == 2


def test_batch_runner_completes_n_is_preferred():
    class BatchRunner:
        def __init__(self) -> None:
            self.seen_n: int | None = None

        async def complete_n(self, request, n: int) -> list[str]:
            self.seen_n = n
            return ['{"status": "ok", "comment": "c", "task_class": "bugfix", "goal": "g"}']

        async def complete(self, request):  # pragma: no cover — must not be called
            raise AssertionError("complete() called although complete_n exists")

    runner = BatchRunner()
    env = asyncio.run(llm_step(runner, "task_card", artifacts={}, question="q", best_of_n=3))
    assert env.goal == "g"
    assert runner.seen_n == 3


GOOD = {"status": "ok", "comment": "c", "file_path": "tests/test_x.py",
        "content": "def test_x():\n    assert True\n"}
ECHO = {"status": "ok", "comment": "c", "file_path": "tests/test_x.py",
        "content": "  current_file_auth_config_py: \"\"\"Service-wide settings.\"\"\"\n"}  # artifact echo — parses? no: line 1 is an expression-ish label... use real garbage

def test_best_of_n_prefers_first_candidate_that_parses():
    """Schema validity alone is too weak a filter for content steps: a candidate
    wrapping the file in markdown fences passes the grammar but can never run.
    The selector must prefer the first candidate that validates AND parses
    (owner finding while re-verifying M1 end-to-end; see ticket 02)."""
    reset_ledger_for_tests()
    fenced = {"status": "ok", "comment": "c", "file_path": "tests/test_x.py",
              "content": "```python\ndef test_x():\n    assert True\n```\n"}
    fake = FakeModelRunner({"write_test": [EnvelopeSpec(body=fenced), EnvelopeSpec(body=GOOD)]})
    env = asyncio.run(llm_step(fake, "write_test", artifacts={}, question="q", best_of_n=2))
    assert env.content == GOOD["content"]
    assert "candidate_unparseable" in [e["kind"] for e in ledger_entries()]


def test_all_candidates_unparseable_falls_back_to_repair_respawn():
    reset_ledger_for_tests()
    bad1 = {"status": "ok", "comment": "c", "file_path": "t.py",
            "content": "```python\nx = 1\n```\n"}
    bad2 = {"status": "ok", "comment": "c", "file_path": "t.py",
            "content": "Here is the fixed file:\nx = 1\n"}
    fixed = {"status": "ok", "comment": "rewrote", "file_path": "t.py",
             "content": "def test_ok():\n    assert True\n"}
    fake = FakeModelRunner({"write_test": [EnvelopeSpec(body=bad1), EnvelopeSpec(body=bad2),
                                           EnvelopeSpec(body=fixed)]})
    env = asyncio.run(llm_step(fake, "write_test", artifacts={}, question="q", best_of_n=2))
    assert env.content == fixed["content"]
    kinds = [e["kind"] for e in ledger_entries()]
    assert kinds.count("candidate_unparseable") == 2 and "repair_ok" in kinds


def test_content_steps_carry_fidelity_instruction_in_prompt():
    """The composer carries the M0-proven hard-rules block (ticket 02 FAIL_PATTERN:
    docstring-strip survived weak phrasing at temp 0.2)."""
    p = compose_prompt("write_test", {"f": "x = 1"}, "q")
    assert "Hard rules for the content field" in p and "module docstring" in p
    p2 = compose_prompt("task_card", {"request": "r"}, "q")
    assert "Hard rules for the content field" not in p2
