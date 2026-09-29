"""Check pipeline + the ``check_write`` primitive (DESIGN §4.5, KERNEL_API §3.4 — M3).

The kernel-owned work-tree write path: every model-implication file mutation goes
through :func:`check_write`, which applies the §4.5 ladder — formatter → autofixer
(≤2 passes, survivor rule) → tree-sitter parse → project-wide type check → rule
library → intent check tier 1 — auto-fixes the trivial, and rolls back what cannot
stand. Reliability gates cost (DESIGN §2.7, owner decision 2026-09-17).

Verdict semantics (KERNEL_API §3.4 reading, recorded as the M3 DECISION):

- ``rolled_back`` (ok=False): parse survivor (the work tree must never hold a
  non-parsing file — parse repair belongs to the §4.7 generation-time path) or an
  intent violation (a source-intent write into a test file is gate-easing,
  structurally suspect, §4.8). Bytes restored to the pre-write state; the model's
  file view never diverges from disk (§2.4c).
- ``escalated`` (ok=True): findings alive after the last allowed fix pass or new
  type findings — the write STAYS, findings travel back as the shaped summary the
  script composes the retry from (§4.5 "escalate to model only survivors").
  pytest still judges behavior downstream.
- ``auto_fixed`` / ``clean`` (ok=True): committed.

Slice boundaries (ticket 03, none silent):
- Whole-file writes only (bounded-region stitching is M9 file-splitting).
- Scoped tests are the script's stage (test policy belongs to the script until the
  M4 session runner); the rule library consumes test output via
  :func:`diagnose_test_output`, which the script calls after running its suite.
- Rollback is exact byte-restore (per-file restore is precise for whole-file v1);
  harness-git reset stays kernel-internal per KERNEL_API §4.5 DECISION.

Type-check scoping (TEST_PLAN §3.3 ``type_check_filters_at_finding_level``): the
baseline is computed pre-write and findings are diffed at FINDING level — a caller
broken in an untouched file survives, pre-existing untouched-file noise never
blocks. The cheaper touched-files-only scoping is unsound (DESIGN §4.5) and the
config type rejects it structurally.
"""

from __future__ import annotations

import difflib
import re
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harness.artifacts import filter_secrets
from harness.exec import exec as k_exec
from harness.repair import broken_excerpt, parse_python
from harness.runner import note

__all__ = [
    "AutofixFn",
    "CheckConfig",
    "CheckFinding",
    "WriteResult",
    "check_write",
    "diagnose_test_output",
]

#: One auto-fix invocation: (workdir, repo-relative path, pass number) ->
#: (file changed, findings collected after the pass). The default is the ruff
#: pair; tests inject scripted fixers to pin the survivor/oscillation rules
#: deterministically (TEST_PLAN §3.3 tool-fight case).
AutofixFn = Callable[[Path, str, int], Awaitable[tuple[bool, list["CheckFinding"]]]]


class CheckConfig(BaseModel):
    """Pipeline configuration. ``scope_mode`` deliberately has ONE legal value:
    touched-files-only type scoping is unsound (DESIGN §4.5 — whole-file rewrites
    break callers in untouched files), so a config attempting invocation-level
    scoping is a validation error, not a runtime footgun."""

    model_config = ConfigDict(extra="forbid")

    max_autofix_passes: int = Field(default=2, ge=0, le=5)
    scope_mode: Literal["finding_level"] = "finding_level"
    stages: tuple[str, ...] = ("autofix", "parse", "typecheck", "rules")


class CheckFinding(BaseModel):
    """One shaped finding — data a retry summary is composed from, never raw."""

    model_config = ConfigDict(extra="forbid")

    stage: str                    # autofix | parse | typecheck | rules
    path: str
    line: int | None = None
    code: str                     # tool code or rule id (e.g. "FP-4-nameerror-source")
    message: str
    fixable: bool = False
    excerpt: str = ""             # bounded; for escalation summaries only


class WriteResult(BaseModel):
    """Shaped result of one write through the pipeline (KERNEL_API §3.4)."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    verdict: Literal["clean", "auto_fixed", "escalated", "rolled_back"]
    findings: list[CheckFinding] = Field(default_factory=list)
    fix_passes_used: int = 0
    diff: str = ""                # secret-filtered at the boundary (§4.2)
    diff_redactions: int = 0
    rolled_back: bool = False


def _finding_key(f: CheckFinding) -> tuple:
    return (f.path, f.line, f.code, f.message)


# ---------------------------------------------------------------------------
# collection helpers (ruff / mypy) — kernel-provenance exec, shaped degradation
# ---------------------------------------------------------------------------

_LINT_LINE = re.compile(r"^(.+?):(\d+):(\d+): (\w+) (.*)$")
_TYPE_LINE = re.compile(r"^(.+?):(\d+): error: (.*)$")


async def _run_tool(cmd: list[str], workdir: Path) -> tuple[int, str]:
    res = await k_exec(cmd, workdir, provenance="kernel", timeout_s=120.0)
    out = res.stdout_tail if res.exit == 0 else (res.stdout_tail + res.stderr_tail)
    return (res.exit if res.exit is not None else 2), out


async def _collect_lint(workdir: Path, path: str) -> list[CheckFinding]:
    # FP-9: the rule set is PINNED to the correctness set (E9 syntax + F pyflakes).
    # Ruff's evolving defaults grew style rules (DTZ007 flagged the CORRECT T-17 fix
    # — naive datetimes by design) and redirected the model into breaking logic.
    # The ladder serves the task contract, not tool opinion; widen only with
    # evidence (FAIL_PATTERNS discipline).
    code, out = await _run_tool(
        ["ruff", "check", "--no-cache", "--select", "E9,F", "--output-format", "concise", path],
        workdir,
    )
    if code >= 2:
        note("lint_unavailable", detail=out[-160:])
        return []
    findings: list[CheckFinding] = []
    for line in out.splitlines():
        m = _LINT_LINE.match(line.strip())
        if m:
            fpath, line_no, _col, rcode, msg = m.groups()
            findings.append(
                CheckFinding(
                    stage="autofix", path=fpath, line=int(line_no), code=rcode,
                    message=msg[:200], fixable=False,
                )
            )
    return findings


async def _collect_types(workdir: Path) -> list[CheckFinding]:
    """Project-wide mypy; the caller does the finding-level filtering. The cache
    lives OUTSIDE the workdir — a .mypy_cache inside would be untracked dirt that
    boot_recover would (rightly) wipe and detect_external_edits would flag."""
    with tempfile.TemporaryDirectory(prefix="helpagent-mypy-") as cache:
        code, out = await _run_tool(
            ["mypy", "--no-error-summary", "--hide-error-context",
             "--ignore-missing-imports", f"--cache-dir={cache}", "."],
            workdir,
        )
    if code >= 2:
        note("typecheck_unavailable", detail=out[-160:])
        return []
    findings = []
    for line in out.splitlines():
        m = _TYPE_LINE.match(line.strip())
        if m:
            fpath, line_no, msg = m.groups()
            findings.append(
                CheckFinding(
                    stage="typecheck", path=fpath, line=int(line_no),
                    code="mypy-error", message=msg[:200], fixable=False,
                )
            )
    return findings


async def _ruff_autofix(workdir: Path, path: str, pass_no: int) -> tuple[bool, list[CheckFinding]]:
    """Default fixer. ``pass_no == 0`` is the collect-only inventory (no format,
    no fix) that seeds the re-appearance detector; pass 1 runs formatter + fixer;
    later passes run the fixer only."""
    if pass_no == 0:
        return False, await _collect_lint(workdir, path)
    if pass_no == 1:
        await _run_tool(["ruff", "format", "--no-cache", "--quiet", path], workdir)
    await _run_tool(["ruff", "check", "--no-cache", "--fix", "--quiet", "--select", "E9,F", path], workdir)
    return True, await _collect_lint(workdir, path)


# ---------------------------------------------------------------------------
# rule library (DESIGN §4.4/§4.5 — deterministic, trajectory-grown, idiom-carrying)
# ---------------------------------------------------------------------------

_NAMEERROR = re.compile(r"NameError: name '(\w+)' is not defined")
_IMPORT_FAIL = re.compile(r"(?:ImportError|ModuleNotFoundError).{0,80}?['\"]([\w.]+)['\"]")
_TYPER_KWARG = re.compile(r"TypeError: (\w+)\(\) got an unexpected keyword argument '(\w+)'")
_TYPER_MISSING = re.compile(r"TypeError: (\w+)\(\) missing (\d+) required positional argument")
_FUNC_DEF = re.compile(rf"^(?:\s*)def (\w+)\s*\(([^)]*)", re.M)


def diagnose_test_output(
    excerpts: Sequence[str], repo_files: Mapping[str, str]
) -> list[CheckFinding]:
    """Rule library over scoped-test output (called by the script after pytest).
    Each rule carries the corrected idiom to inject (§4.4). The first family is
    FP-4: cross-file name resolution is a lookup — harness work, never left to
    the model (FP-4 CLOSED by these rules; see FAIL_PATTERNS.md)."""
    findings: list[CheckFinding] = []
    for excerpt in excerpts:
        m = _NAMEERROR.search(excerpt)
        if m:
            name = m.group(1)
            for rel, text in repo_files.items():
                if re.search(rf"^(?:class|def)\s+{re.escape(name)}\b", text, re.M):
                    findings.append(
                        CheckFinding(
                            stage="rules", path=rel, code="FP-4-nameerror-source",
                            message=f"{name} is defined in {rel} — add the import "
                                    "(its full source is in current_files)",
                        )
                    )
                    break
            else:
                findings.append(
                    CheckFinding(
                        stage="rules", path="", code="FP-4-nameerror-unresolved",
                        message=f"{name} is not defined anywhere in the repo — "
                                "the name itself may be misspelled",
                    )
                )
            continue
        m = _IMPORT_FAIL.search(excerpt)
        if m:
            mod = m.group(1)
            rel = mod.replace(".", "/") + ".py"
            if rel in repo_files:
                findings.append(
                    CheckFinding(
                        stage="rules", path=rel, code="FP-4-import-source",
                        message=f"module {mod} lives at {rel} — import from there",
                    )
                )
            else:
                findings.append(
                    CheckFinding(
                        stage="rules", path="", code="FP-4-import-external",
                        message=f"module {mod} is not part of this repo — check the "
                                "dependency list / install requirements",
                    )
                )
            continue
        # Signature-arity family (T-31): a threaded parameter failed at a call —
        # point at the defining function and note the callers that must thread it.
        kw = _TYPER_KWARG.search(excerpt) or _TYPER_MISSING.search(excerpt)
        if kw:
            name, keyword = kw.group(1), (kw.group(2) if kw.lastindex and kw.lastindex >= 2 and "keyword" in excerpt else "")
            if not keyword:
                keyword = kw.group(2)
            for rel, text in repo_files.items():
                for fm in _FUNC_DEF.finditer(text):
                    if fm.group(1) != name:
                        continue
                    params = fm.group(2)
                    if keyword and keyword in params:
                        continue  # the defining signature already accepts it
                    callers = sorted(
                        caller for caller, ctext in repo_files.items()
                        if caller != rel and re.search(rf"\b{name}\s*\(", ctext)
                    )
                    hint = (f"{name} in {rel} does not accept '{keyword or 'the new required argument'}' "
                            f"— update its def signature")
                    if callers:
                        hint += f"; callers {', '.join(callers)} must thread it through their own signatures"
                    findings.append(CheckFinding(
                        stage="rules", path=rel, code="arity-signature-thread",
                        message=hint[:200],
                    ))
                    break
                else:
                    continue
                break
    return findings


# ---------------------------------------------------------------------------
# intent check tier 1 (deterministic; §4.5)
# ---------------------------------------------------------------------------

_TEST_PATH = re.compile(r"(^|/)(tests?/|test_|_test\.py$)")


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


# ---------------------------------------------------------------------------
# the primitive
# ---------------------------------------------------------------------------


async def check_write(
    workdir: Path,
    path: str,
    content: str,
    *,
    intent: Literal["source", "test"] | None = None,
    config: CheckConfig | None = None,
    autofix: AutofixFn | None = None,
) -> WriteResult:
    """Run the §4.5 ladder over one whole-file write. Owns the write: the caller
    never writes first. See the module docstring for verdict semantics."""
    cfg = config or CheckConfig()
    workdir = Path(workdir)

    # path guard: repo-relative, no traversal — a write outside the workdir is a
    # policy matter, and policy outcomes are shaped results, never exceptions
    target = (workdir / path).resolve()
    if not target.is_relative_to(workdir.resolve()):
        f = CheckFinding(stage="rules", path=path, code="policy-path-escape",
                         message="write path escapes the workdir")
        note("write_rolled_back", file=path, reason="path-escape")
        return WriteResult(ok=False, verdict="rolled_back", findings=[f], rolled_back=True)

    pre_bytes: bytes | None = None
    if target.exists():
        pre_bytes = target.read_bytes()

    # finding-level baseline (pre-write project state) — the price of the sound
    # scoping is one extra mypy invocation on the pre-write tree (recorded DECISION)
    pre_keys: set[tuple] = set()
    if "typecheck" in cfg.stages and target.suffix == ".py":
        pre_keys = {_finding_key(f) for f in await _collect_types(workdir)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    written_bytes = target.read_bytes()   # what the write itself landed — fixer deltas measure against this

    findings: list[CheckFinding] = []
    fix_passes = 0
    oscillators: list[CheckFinding] = []
    if "autofix" in cfg.stages:
        fixer = autofix or _ruff_autofix
        # pass 0 = collect-only inventory: seeds the re-appearance detector so a
        # finding that goes away under one fixer and comes back under another is
        # recognized as a SURVIVOR, not a new bug (DESIGN §4.5 tool-fight rule)
        ever_keys: set[tuple] = set()
        last_keys: set[tuple] = set()
        for pass_no in range(0, cfg.max_autofix_passes + 1):
            _changed, after = await fixer(workdir, path, pass_no)
            keys_now = {_finding_key(f) for f in after}
            oscillators = [f for f in after
                           if _finding_key(f) in (ever_keys - last_keys)]
            if pass_no > 0:
                fix_passes = pass_no
                findings = after
            else:
                ever_keys |= keys_now
            if oscillators:
                note("tool_fight_survivor", file=path,
                     codes=sorted({f.code for f in oscillators}))
                break
            if not after and pass_no > 0:
                break
            ever_keys |= keys_now
            last_keys = keys_now
    else:
        findings = await _collect_lint(workdir, path)

    final = target.read_text()
    parse_broken = False
    if "parse" in cfg.stages and target.suffix == ".py":
        ok, err_node = parse_python(final)
        if not ok:
            parse_broken = True
            findings.append(
                CheckFinding(
                    stage="parse", path=path,
                    line=(err_node.start_point[0] + 1) if err_node is not None else None,
                    code="syntax-error", message="tree-sitter parse error",
                    excerpt=broken_excerpt(final, err_node) if err_node is not None else "",
                )
            )

    if "typecheck" in cfg.stages and target.suffix == ".py":
        for f in await _collect_types(workdir):
            if _finding_key(f) not in pre_keys:
                findings.append(f)

    intent_violation = False
    if "rules" in cfg.stages and intent == "source" and _is_test_path(path):
        intent_violation = True
        findings.append(
            CheckFinding(stage="rules", path=path, code="intent-test-write",
                         message="source-intent write into a test file — gate-easing "
                                 "is structurally suspect (DESIGN §4.8)")
        )

    diff_text, redactions = filter_secrets(
        "".join(difflib.unified_diff(
            (pre_bytes.decode(errors="replace").splitlines(keepends=True) if pre_bytes else []),
            final.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
    )

    rolled_back = parse_broken or intent_violation
    if rolled_back:
        if pre_bytes is None:
            target.unlink()
        else:
            target.write_bytes(pre_bytes)
        verdict = "rolled_back"
        ok = False
        note("write_rolled_back", file=path,
             reason="parse" if parse_broken else "intent")
    elif findings:
        verdict = "escalated"   # survivors: write stays, script composes the retry
        ok = True
    elif fix_passes > 0 and target.read_bytes() != written_bytes:
        verdict = "auto_fixed"  # the FIXER changed bytes, not the write itself
        ok = True
    else:
        verdict = "clean"
        ok = True

    note("check_verdict", verdict=verdict, file=path, n_findings=len(findings),
         fix_passes=fix_passes)
    if not rolled_back:
        note("write_committed", files=[path])
    return WriteResult(
        ok=ok, verdict=verdict, findings=findings, fix_passes_used=fix_passes,
        diff=diff_text, diff_redactions=redactions, rolled_back=rolled_back,
    )
