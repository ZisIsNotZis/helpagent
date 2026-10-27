"""Integration tier: real llama.cpp server on :8833 with the design's
reference model Spark-X2.5-4B-Q4_K_M. Marked slow — outside the unit gate
(pyproject testpaths stays unit+contract); run explicitly with
`uv run pytest tests/integration -m slow -q`. Skips cleanly when the server is down."""

import asyncio

import pytest

from harness import ledger_entries
from harness.model import LlamaServerRunner
from harness.repair import parse_python, repair_code
from harness.runner import llm_step

pytestmark = [pytest.mark.slow]


def _runner() -> LlamaServerRunner:
    runner = LlamaServerRunner()
    if not runner.health_check():
        pytest.skip("llama-server :8833 not healthy")
    return runner


def test_health():
    assert _runner().health_check()


def test_real_whole_file_edit_through_llm_step():
    runner = _runner()
    env = asyncio.run(llm_step(
        runner, "write_test",
        artifacts={
            "spec": "AC-1: divide(1, 0) raises MinirepoError (never ZeroDivisionError)",
            "patterns": "pytest style; imports: from minirepo.calc import divide; "
                        "from minirepo.errors import MinirepoError",
        },
        question="Write the complete pytest file tests/test_calc.py with exactly one test: "
                 "divide(1, 0) raises MinirepoError, using pytest.raises.",
        context={}),
    )
    assert env.status == "ok"
    ok, node = parse_python(env.content)
    assert ok, f"model content did not parse: {env.content!r}"
    assert "MinirepoError" in env.content and "pytest.raises" in env.content
    # the invocation note carries token/cache counters (docs/7_INTERFACE.md §5: no content)
    invocations = [e for e in ledger_entries() if e["kind"] == "llm_invocation"]
    assert invocations and invocations[-1]["prompt_tokens"] > 0
    assert invocations[-1]["completion_tokens"] > 0
    assert isinstance(invocations[-1]["cache_hit"], float)


def test_real_repair_respawn():
    runner = _runner()
    broken = (
        "import pytest\n"
        "from minirepo.calc import divide\n"
        "from minirepo.errors import MinirepoError\n"
        "\n"
        "def test_divide_by_zero_raises_minirepo_error():\n"
        "    with pytest.raises(MinirepoError)\n"   # missing colon — trivial syntax error
        "        divide(1, 0)\n"
    )
    fixed = asyncio.run(repair_code(broken, runner, "write_test",
                                    question="Write the divide-by-zero test file."))
    ok, node = parse_python(fixed)
    assert ok, f"repair did not parse: {fixed!r}"
    assert "pytest.raises(MinirepoError)" in fixed and "divide(1, 0)" in fixed
