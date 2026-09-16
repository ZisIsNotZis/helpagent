"""Minimal sandboxed exec (TEST_PLAN §3.2 spirit, DESIGN §4.6): allowlist +
policy-blocked shaped results (never exceptions), ANSI-stripped byte-capped
output, kernel-provenance runs. Container/network policy is M4 — these tests
pin the M2 contract only."""

import asyncio
from pathlib import Path

from harness.exec import ShapedResult, exec, strip_ansi


def _run(cmd, workdir, **kw):
    return asyncio.run(exec(cmd, workdir, **kw))


def test_allowlisted_command_runs_and_is_shaped(tmp_path: Path):
    (tmp_path / "t_pass.py").write_text("def test_ok():\n    assert True\n")
    res = _run(["python3", "-m", "pytest", "-q", "t_pass.py"], tmp_path, provenance="model")
    assert res.ok and res.exit == 0 and res.verdict == "ok"
    assert res.policy_blocked is False
    assert "1 passed" in (res.stdout_tail + res.stderr_tail)


def test_model_provenance_outside_allowlist_is_policy_blocked_never_exception(tmp_path: Path):
    # curl would "run" a network call if executed — it must be blocked as DATA
    res = _run(["curl", "http://example.invalid"], tmp_path, provenance="model")
    assert res.policy_blocked is True and res.exit is None and res.verdict == "policy_blocked"
    assert "allowlist" in res.excerpts[0]


def test_kernel_provenance_runs_outside_allowlist(tmp_path: Path):
    # script/kernel provenance is trusted (DESIGN §4.1 trust boundary)
    res = _run(["bash", "-c", "echo hi"], tmp_path, provenance="kernel")
    assert res.ok and "hi" in res.stdout_tail


def test_failure_shape_carries_failure_excerpts(tmp_path: Path):
    (tmp_path / "t_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    res = _run(["python3", "-m", "pytest", "-q", "t_bad.py"], tmp_path, provenance="model")
    assert not res.ok and res.verdict == "failed"
    assert any("assert" in e or "FAILED" in e for e in res.excerpts)


def test_output_is_ansi_stripped_and_capped(tmp_path: Path):
    script = "print('x' * 40000); print('tail \\033[31mred\\033[0m mark')"
    (tmp_path / "noisy.py").write_text(script)
    res = _run(["python3", "noisy.py"], tmp_path, provenance="kernel")
    assert "\x1b[" not in (res.stdout_tail + res.stderr_tail)
    assert len(res.stdout_tail) <= 8192
    assert "tail red mark" in res.stdout_tail          # tail kept; head legitimately capped out


def test_transport_error_is_shaped_not_raised(tmp_path: Path):
    res = _run(["definitely-not-a-real-binary-xyz"], tmp_path, provenance="kernel")
    assert res.verdict == "transport_error" and res.exit is None


def test_strip_ansi_direct():
    assert strip_ansi("\x1b[1;32mok\x1b[0m") == "ok"
