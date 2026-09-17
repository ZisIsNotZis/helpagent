"""Minimal sandboxed exec (DESIGN §4.6, KERNEL_API §3.2 — M2 slice).

v0 scope, honestly bounded: allowlist + policy-blocked shaped results + output
shaping. NO container/network/filesystem policy yet — that is M4's tool-wrapper
milestone (DESIGN §4.6 "container, network policy"). What M2 guarantees:

- a model-provenance command outside the allowlist is a **policy-blocked shaped
  result**, never an exception, and never reaches the diagnose pipeline (§4.6);
- kernel/script provenance runs (script-provenance exec is trusted, DESIGN §4.1
  trust boundary), but the result is still shaped and byte-capped;
- output is ANSI-stripped and byte-capped; raw output belongs to the caller's
  artifact persistence (through the secret filter), not to this module.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from harness.runner import note

#: Commands a model-provenance call may run (per-script config in the full design;
#: one kernel-default set for M2). Everything else ⇒ policy-blocked.
DEFAULT_ALLOWLIST = frozenset({"pytest", "python", "python3", "ruff"})

#: Per-stream byte cap before shaping (raw output is archived by the caller).
_STREAM_CAP = 8_192

_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b\(B"
)
_FAILURE_MARKERS = ("FAILED", "ERROR", "error:", "assert", "Traceback", "E   ")


@dataclass
class ShapedResult:
    """A shaped execution result — data, never an exception leak (KERNEL_API §3.2)."""

    command: list[str]
    exit: int | None
    verdict: str                 # "ok" | "failed" | "policy_blocked" | "transport_error"
    excerpts: list[str] = field(default_factory=list)
    policy_blocked: bool = False
    duration_s: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.exit == 0 and not self.policy_blocked


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _shape(command: list[str], exit_code: int | None, stdout: str, stderr: str) -> ShapedResult:
    out = strip_ansi(stdout)[-_STREAM_CAP:]
    err = strip_ansi(stderr)[-_STREAM_CAP:]
    combined = (out + "\n" + err).splitlines()
    failures = [l for l in combined if any(m in l for m in _FAILURE_MARKERS)]
    excerpts = failures[:3] if failures else [l for l in combined if l.strip()][-10:]
    return ShapedResult(
        command=command,
        exit=exit_code,
        verdict="ok" if exit_code == 0 else "failed",
        excerpts=excerpts,
        stdout_tail=out,
        stderr_tail=err,
    )


async def exec(
    cmd: list[str],
    workdir: str | Path,
    provenance: str = "kernel",
    allowlist: frozenset[str] = DEFAULT_ALLOWLIST,
    timeout_s: float = 120.0,
) -> ShapedResult:
    """Run ``cmd`` in ``workdir``. A model-provenance command outside the allowlist
    returns a policy-blocked shaped result (routed to an allowlist request by the
    caller — NEVER an exception, NEVER a probe-failure count, DESIGN §4.6)."""
    wd = Path(workdir)
    cmd = [str(c) for c in cmd]
    if provenance == "model" and (not cmd or Path(cmd[0]).name not in allowlist):
        # first-class shaped result (DESIGN §4.6) — and a first-class STATS counter
        # (2026-09-17 owner alignment: policy_blocked is tracked, never silent)
        note("policy_blocked", command=cmd[0] if cmd else "")
        return ShapedResult(
            command=cmd,
            exit=None,
            verdict="policy_blocked",
            excerpts=[f"command {cmd[:1]!r} is not in the exec allowlist"],
            policy_blocked=True,
        )
    started = asyncio.get_event_loop().time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(wd),
            # FP-6: stale __pycache__ false-PASS — a same-length edit (e.g. `is`→`==`)
            # can reuse the previous source's cached .pyc, so pytest passes on broken
            # code. Bytecode writing is disabled for every exec'd command.
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return ShapedResult(
                command=cmd, exit=None, verdict="transport_error",
                excerpts=[f"timed out after {timeout_s}s"],
                stdout_tail="", stderr_tail="",
                duration_s=round(asyncio.get_event_loop().time() - started, 3),
            )
    except (OSError, FileNotFoundError) as exc:
        return ShapedResult(
            command=cmd, exit=None, verdict="transport_error",
            excerpts=[f"exec failed: {exc}"],
        )
    res = _shape(cmd, proc.returncode, out_b.decode(errors="replace"), err_b.decode(errors="replace"))
    res.duration_s = round(asyncio.get_event_loop().time() - started, 3)
    return res
