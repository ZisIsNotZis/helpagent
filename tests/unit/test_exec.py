"""Minimal sandboxed exec: allowlist +
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


# ---------------------------------------------------------------- M4 sandbox


def test_path_scoping_blocks_by_path_not_argv0(tmp_path: Path):
    """: the sandbox denies by PATH, not by argv[0] — /etc is hidden
    (tmpfs over the ro base), so an allowlisted python cannot read host secrets,
    and the failure is a shaped result, never an exception."""
    res = _run(["python3", "-c", "open('/etc/passwd').read()"], tmp_path, provenance="model")
    assert not res.ok and res.verdict == "failed"
    assert "root:" not in (res.stdout_tail + res.stderr_tail)   # content never leaked


def test_network_denied_inside_sandbox(tmp_path: Path):
    """DESIGN §4.6 network policy: even an ALLOWLISTED command cannot reach the
    network inside the sandbox (defense in depth beyond the allowlist)."""
    res = _run(["python3", "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)"],
               tmp_path, provenance="model")
    assert not res.ok and res.verdict == "failed"


def test_writes_outside_workdir_are_read_only(tmp_path: Path):
    res = _run(["python3", "-c", "open('/usr/evil-marker', 'w').write('x')"],
               tmp_path, provenance="model")
    assert not res.ok and res.verdict == "failed"
    assert not Path("/usr/evil-marker").exists()


def test_workdir_stays_writable_inside_sandbox(tmp_path: Path):
    res = _run(["python3", "-c", "open('made_by_model.py', 'w').write('ok')"],
               tmp_path, provenance="model")
    assert res.ok and (tmp_path / "made_by_model.py").read_text() == "ok"


def test_sandbox_unavailable_is_policy_blocked_never_unsandboxed(tmp_path: Path, monkeypatch):
    """Kernel invariant: a model-provenance command NEVER runs unsandboxed. If
    bwrap is missing, the outcome is a policy-blocked shaped result."""
    import harness.exec as ex

    monkeypatch.setattr(ex, "_find_bwrap", lambda: None)
    res = _run(["python3", "-c", "print('should never run')"], tmp_path, provenance="model")
    assert res.policy_blocked is True and res.exit is None
    assert "sandbox" in res.excerpts[0]


def test_registry_shaping_reaches_exec_results(tmp_path: Path):
    (tmp_path / "t_a.py").write_text("def test_a():\n    assert 1 == 2\n")
    res = _run(["python3", "-m", "pytest", "-q", "t_a.py"], tmp_path, provenance="model")
    assert res.n_failures == 1
    assert res.suggested_next_action.startswith("run pytest -x")
    assert any("test_a" in e for e in res.excerpts)
