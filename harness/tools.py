"""Tool wrapper registry (docs/6_ARCHITECTURE.md §4.6, docs/7_INTERFACE.md §3.2 — M4).

Registry mapping command → output shaper. Common tools get hand-written structured
summaries; rare tools fall through to the generic shaper. Shaping is
provenance-independent (kernel and model outputs deserve the same small context);
the SANDBOX is provenance-dependent and lives in :mod:`harness.exec`.

Contract per docs/7_INTERFACE.md §3.2: ``{exit, verdict, n_failures, excerpts,
suggested_next_action}`` — always ANSI-stripped, byte-capped, deduped; raw output
belongs to the caller's artifact persistence (through the secret filter), never to
this module. "Show more" is a help query, not a rerun.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

__all__ = ["REGISTRY", "ShapedOutput", "shape_for"]


@dataclass
class ShapedOutput:
    """The tool-specific slice of a shaped result (docs/7_INTERFACE.md §3.2)."""

    n_failures: int | None = None
    excerpts: list[str] = field(default_factory=list)
    suggested_next_action: str = ""


Shaper = Callable[[int, str, str], ShapedOutput]   # (exit_code, stdout, stderr) -> ShapedOutput

_SUMMARY_PASSED = re.compile(r"(\d+) passed")
_SUMMARY_FAILED = re.compile(r"(\d+) failed")
_SUMMARY_ERROR = re.compile(r"(\d+) error")
_FAILED_ID = re.compile(r"^(FAILED|[EF])\s{1,4}(\S+::\S+)")
_E_LINE = re.compile(r"^(E\s{2,}.+)$")
_RUFF_LINE = re.compile(r"^.+?:\d+:\d+: (\w+) (.*)$")
_MYPY_LINE = re.compile(r"^.+?:\d+: error: (.*)$")


def _cap(lines: list[str], n: int) -> list[str]:
    """First n non-empty, deduped, ANSI-free-by-convention lines (input is already
    stripped/capped by exec; this only dedupes and bounds)."""
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= n:
            break
    return out


def shape_pytest(exit_code: int, out: str, err: str) -> ShapedOutput:
    """pytest: verdict + failure count + failing test ids + first assertions."""
    text = out + "\n" + err
    n_failed = int(_SUMMARY_FAILED.search(text).group(1)) if _SUMMARY_FAILED.search(text) else 0
    n_error = int(_SUMMARY_ERROR.search(text).group(1)) if _SUMMARY_ERROR.search(text) else 0
    n_failures = n_failed + n_error if (n_failed or n_error) else (0 if exit_code == 0 else None)
    ids: list[str] = []
    e_lines: list[str] = []
    for line in text.splitlines():
        m = _FAILED_ID.match(line.strip())
        if m:
            ids.append(m.group(2))
        elif _E_LINE.match(line.strip()):
            e_lines.append(line.strip())
    excerpts = [f"FAILED {tid}" for tid in ids[:3]] + e_lines[:3]
    action = ""
    if n_failures:
        first = ids[0] if ids else ""
        action = f"run pytest -x {'-q ' + first if first else '-q'} to see the first failure in isolation"
    return ShapedOutput(n_failures=n_failures, excerpts=_cap(excerpts, 6), suggested_next_action=action)


def shape_ruff(exit_code: int, out: str, err: str) -> ShapedOutput:
    """ruff concise findings: ``path:line:col: CODE message``."""
    findings = [m.group(0).strip() for line in (out + "\n" + err).splitlines()
                if (m := _RUFF_LINE.match(line.strip()))]
    n = len(findings)
    action = "run ruff check --fix <path> for auto-fixable findings" if n and exit_code != 0 else ""
    return ShapedOutput(n_failures=n or (0 if exit_code == 0 else None),
                        excerpts=_cap(findings, 6), suggested_next_action=action)


def shape_mypy(exit_code: int, out: str, err: str) -> ShapedOutput:
    """mypy default text errors: ``path:line: error: message``."""
    errors = [m.group(0).strip() for line in (out + "\n" + err).splitlines()
              if (m := _MYPY_LINE.match(line.strip()))]
    n = len(errors)
    action = "read the first error excerpt; type errors in untouched callers are real (finding-level)" \
        if n else ""
    return ShapedOutput(n_failures=n or (0 if exit_code == 0 else None),
                        excerpts=_cap(errors, 6), suggested_next_action=action)


def shape_git(exit_code: int, out: str, err: str) -> ShapedOutput:
    """git: status/diff/log verdicts — counts, not dumps."""
    text = out + "\n" + err
    lines = [l for l in text.splitlines() if l.strip()]
    if exit_code != 0:
        return ShapedOutput(n_failures=1, excerpts=_cap(lines, 3),
                            suggested_next_action="git failed — check the excerpt, never retry blindly")
    return ShapedOutput(n_failures=0, excerpts=_cap(lines, 3),
                        suggested_next_action="")


def shape_generic(exit_code: int, out: str, err: str) -> ShapedOutput:
    """Generic fallback (docs/7_INTERFACE.md §3.2): nonzero exit → stderr tail + first
    error-pattern match; zero exit → head lines. The caller caps bytes."""
    text = out + "\n" + err
    lines = text.splitlines()
    if exit_code == 0:
        return ShapedOutput(n_failures=0, excerpts=_cap(lines, 6))
    markers = ("error", "Error", "ERROR", "Traceback", "failed", "FATAL")
    hits = [l for l in lines if any(m in l for m in markers)]
    excerpts = hits[:3] if hits else [l for l in lines if l.strip()][-3:]
    return ShapedOutput(n_failures=None, excerpts=_cap(excerpts, 6),
                        suggested_next_action="")


REGISTRY: dict[str, Shaper] = {
    "pytest": shape_pytest,
    "py.test": shape_pytest,
    "ruff": shape_ruff,
    "mypy": shape_mypy,
    "git": shape_git,
}


def shape_for(cmd: list[str]) -> Shaper:
    """Registry lookup by argv shape: ``python -m pytest`` resolves to the pytest
    shaper (module-invocation form); otherwise the argv[0] basename. Unknown →
    generic fallback — every command gets a shaped result."""
    if not cmd:
        return shape_generic
    parts = [str(c) for c in cmd]
    base = PurePosixPath(parts[0]).name
    if base in ("python", "python3", str(__import__("sys").executable.split("/")[-1])):
        if len(parts) >= 3 and parts[1] == "-m" and parts[2] in REGISTRY:
            return REGISTRY[parts[2]]
        return shape_generic
    return REGISTRY.get(base, shape_generic)
