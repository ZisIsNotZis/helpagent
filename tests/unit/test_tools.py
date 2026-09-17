"""Tool wrapper registry (TEST_PLAN §3.2 shaping spirit, KERNEL_API §3.2 — M4).

Pin the registry contract: dispatch by argv shape (``python -m pytest`` form),
per-tool structured summaries (n_failures, excerpts, suggested_next_action),
generic fallback for unknown tools — every command gets a shaped result.
"""

from harness.tools import shape_for, shape_mypy, shape_pytest, shape_ruff


def test_dispatch_python_m_form():
    assert shape_for(["python3", "-m", "pytest", "-q"]).__name__ == "shape_pytest"
    assert shape_for(["/usr/bin/ruff", "check", "x.py"]).__name__ == "shape_ruff"
    assert shape_for(["mypy", "."]).__name__ == "shape_mypy"
    assert shape_for(["git", "status"]).__name__ == "shape_git"


def test_unknown_tool_falls_back_to_generic():
    assert shape_for(["frobnicate", "--turbo"]).__name__ == "shape_generic"
    assert shape_for([]).__name__ == "shape_generic"


def test_pytest_shaper_counts_and_excerpts():
    out = shape_pytest(1, "FAILED tests/test_calc.py::test_a - assert\n"
                           "E       assert 1 == 2\n"
                           "1 failed, 2 passed in 0.1s\n", "")
    assert out.n_failures == 1
    assert out.excerpts[0] == "FAILED tests/test_calc.py::test_a"
    assert "pytest -x" in out.suggested_next_action


def test_pytest_shaper_green_is_zero_failures():
    out = shape_pytest(0, "3 passed in 0.2s\n", "")
    assert out.n_failures == 0 and out.suggested_next_action == ""


def test_mypy_shaper_finding_level():
    out = shape_mypy(1, 'caller.py:3: error: Argument 1 has incompatible type "int"  [arg-type]\n', "")
    assert out.n_failures == 1 and "caller.py:3" in out.excerpts[0]


def test_ruff_shaper_concise_findings():
    out = shape_ruff(1, "mod.py:1:1: F401 `os` imported but unused\n", "")
    assert out.n_failures == 1 and "F401" in out.excerpts[0]


def test_generic_shaper_marks_and_tail():
    from harness.tools import shape_generic
    out = shape_generic(1, "", "Traceback (most recent call last):\n  boom\n")
    assert out.excerpts and "Traceback" in out.excerpts[0]
    ok = shape_generic(0, "line1\nline2\n", "")
    assert ok.n_failures == 0 and ok.excerpts[0] == "line1"
