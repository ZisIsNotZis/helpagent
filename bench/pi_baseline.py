#!/usr/bin/env python3
"""The mature-agent baseline: run the REAL PI CLI (headless) as the agent.

Owner question (twice): a full coding agent such as pi is not our minimal loop, so what
does IT do with the same small local model (Spark-X2.5-4B) on the same corpus tasks?
the hand-rolled list/read/write/run baseline that used to answer this for a
plain agent loop (measured
at 0/6). This driver answers it for pi itself, and it keeps the comparison honest:

1. the task is staged SOURCE-ONLY (``harness.staging.stage_blind``) into a temp workdir,
   exactly as ``bench.v2_leaf.build_spec`` does — the corpus's own tests and ``checks.py``
   are never in the workdir, so the grader stays the scorer and never the agent's tool;
2. pi is run headless in that workdir with the task's request text;
3. whatever pi produced is scored with the SAME external grader as the harness
   (:func:`bench.external_score.external_score`), and the result is placed in the same
   quadrant vocabulary (``bench.v2_leaf.quadrant``);
4. pi's behavioural trace is recorded (``--mode json``): turns, tool calls by name, every
   shell command, whether it wrote a test file, and its final message.

Isolation: pi is pointed at a TEMPORARY agent directory (``PI_CODING_AGENT_DIR``) holding
only a ``models.json`` for the local endpoint, so the owner's real ``~/.pi/agent`` is never
read or written. When ``bwrap`` is available the whole run is placed in a bubblewrap
sandbox with the host filesystem read-only and only the run root writable; ``--no-sandbox``
skips that and relies on the cwd + prompt instruction alone (recorded in the run record).

Config: ``~/.pi/agent/models.json`` was checked and does NOT define a ``local`` provider,
so this driver writes one for the temp agent dir:
``{"providers": {"local": {"baseUrl": "<--base-url>", "api": "openai-completions",
"apiKey": "local", "models": [{"id": "localhost"}]}}}``.

Usage:
  uv run python bench/pi_baseline.py \
      --tasks T-02-off-by-one,T-05-mutable-default,T-31-parameter-threading --n 1
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.external_score import external_score  # noqa: E402
from bench.v2_leaf import load_task, produced_files, quadrant  # noqa: E402
from harness.staging import stage_blind  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8833/v1"
DEFAULT_MODEL = "localhost"
DEFAULT_PROVIDER = "local"
DEFAULT_TIMEOUT_S = 900            # generous but finite (~15 min per task)

#: Ticket 26 ``--reasoning``: a temp models entry that DECLARES reasoning support, so pi
#: honours ``--thinking`` instead of clamping it to ``off`` (docs/rpc-commands.md: a model
#: without reasoning support advertises only ``["off"]``). The context window is pinned to
#: the 32768-token llama-server's real window, and the per-turn output limit to 8192 - a
#: quarter of the window, large enough for a verbose thinking block plus answer/tool call
#: while leaving ~24k tokens for the tool transcript. (The recorded 8192-total-context arm
#: truncated 9/10 tail runs on a thinking block; this removes that ceiling.)
REASONING_CONTEXT_WINDOW = 32768
REASONING_MAX_TOKENS = 8192

#: The claim-equivalent: pi has no claim gate, so its FINAL assistant message is the only
#: thing that can stand in for "the agent says it did the job". These markers are our
#: reading of that text, not pi's; the raw text is stored in the record so a reader can
#: judge for themselves. A negative marker (the agent says it did NOT do it) always wins.
_CLAIM_MARKER = re.compile(
    r"\b(fixed|resolved|done|complete[d]?|pass(?:es|ing|ed)?|works|working|"
    r"correct(?:ly|ed)?|success(?:ful|fully)?|verifie[sd]|implemented|added|updated|"
    r"changed)\b",
    re.IGNORECASE)
_NO_CLAIM_MARKER = re.compile(
    r"\b(could ?n[o']t|cannot|can ?n[o']t|unable|failed to|not able|"
    r"no changes|haven'?t|did ?n[o']t|sorry|give up)\b",
    re.IGNORECASE)

#: Model-config template written into the TEMP agent dir (never the owner's).
_MODELS_JSON = {
    "providers": {
        "local": {
            "baseUrl": DEFAULT_BASE_URL,
            "api": "openai-completions",
            "apiKey": "local",
            "models": [{"id": "localhost"}],
        }
    }
}

PI_PROMPT = (
    "You are a coding agent. Work in the current directory (the project root) and satisfy "
    "the request below. Stay inside the current directory: do not read or write outside it. "
    "Make whatever code changes are needed and verify your work. When the request is "
    "satisfied, stop.\n\nRequest:\n{request}\n"
)

#: Ticket 25 ``--ask-tests``: an EXPLICIT testing instruction appended to the base prompt,
#: so the owner can compare pi with and without one (the baseline run wrote no test).
PI_ASK_TESTS_SUFFIX = (
    "\nAlso WRITE one or more test files under tests/ that FAIL on the current (buggy) "
    "code and PASS once it is fixed, then RUN them (for example `python -m pytest -q`) "
    "and iterate until they pass.\n"
)


def find_pi() -> str | None:
    """The pi executable, resolved through symlinks so it survives a bwrap ro-bind."""
    found = shutil.which("pi")
    if not found:
        return None
    try:
        return str(Path(found).resolve())
    except OSError:                                    # pragma: no cover - fs error path
        return found


def write_agent_dir(agent_dir: Path, base_url: str, reasoning: bool = False) -> None:
    """A TEMP pi config directory: only the local provider, nothing of the owner's.

    With ``reasoning`` the temp model entry declares reasoning support so pi's ``--thinking``
    is honoured (otherwise it is clamped to ``off``) and pins the model's context window and
    output limit to the server's real 32768-token window.
    """
    agent_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(json.dumps(_MODELS_JSON))
    provider = payload["providers"]["local"]
    provider["baseUrl"] = base_url
    if reasoning:
        provider["models"] = [{
            "id": DEFAULT_MODEL,
            "reasoning": True,
            "contextWindow": REASONING_CONTEXT_WINDOW,
            "maxTokens": REASONING_MAX_TOKENS,
        }]
    (agent_dir / "models.json").write_text(json.dumps(payload, indent=1))


# --------------------------------------------------------------------------- trace


def parse_events(text: str) -> dict:
    """Behavioural summary of a pi ``--mode json`` stream.

    Counts turns and tool calls, lists every shell command and every file the model wrote
    or edited, flags a self-written test and whether pytest was invoked, and pulls the
    final assistant text. Tolerant: a truncated last line is ignored.
    """
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)

    turns = sum(1 for e in events if e.get("type") == "turn_start")
    starts = [e for e in events if e.get("type") == "tool_execution_start"]
    ends = {e.get("toolCallId"): e for e in events if e.get("type") == "tool_execution_end"}
    by_name = collections.Counter(e.get("toolName", "?") for e in starts)

    def _error_text(event: dict) -> str:
        result = event.get("result")
        if not isinstance(result, dict):
            return ""
        for part in result.get("content", []) or []:
            if isinstance(part, dict) and part.get("type") == "text":
                return str(part.get("text", ""))[:200]
        return ""

    failed: list[dict] = []
    for e in starts:
        done = ends.get(e.get("toolCallId"))
        if done is not None and done.get("isError"):
            failed.append({"tool": e.get("toolName"), "error": _error_text(done)})

    commands: list[str] = []
    touched: list[str] = []
    for e in starts:
        name = e.get("toolName")
        args = e.get("args") if isinstance(e.get("args"), dict) else {}
        if name == "bash" and isinstance(args.get("command"), str):
            commands.append(args["command"])
        elif name in ("write", "edit") and isinstance(args.get("path"), str):
            touched.append(args["path"])

    def _is_test(rel: str) -> bool:
        name = PurePosixPath(rel).name.lower()
        return name.startswith("test_") or name.endswith("_test.py")

    wrote_test = any(_is_test(p) for p in touched)
    ran_test = any(re.search(r"\bpytest\b", c) for c in commands)
    texts = _assistant_texts(events)
    return {
        "turns": turns,
        "tool_calls": sum(by_name.values()),
        "tool_calls_by_name": dict(by_name),
        "failed_tool_calls": failed,
        "commands": commands,
        "ran_command": bool(commands),
        "ran_pytest": ran_test,
        "files_touched": sorted({str(PurePosixPath(p)) for p in touched}),
        "wrote_test": wrote_test,
        "assistant_texts": texts,
        "final_text": texts[-1] if texts else "",
    }


def _assistant_texts(events: list[dict]) -> list[str]:
    """Every non-empty assistant text message, in order (the closing one last)."""
    texts: list[str] = []
    for e in events:
        if e.get("type") != "message_end":
            continue
        msg = e.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            part = _text_of(msg)
            if part:
                texts.append(part)
    return texts


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        return "".join(parts).strip()
    return ""


def _asserts_success(text: str) -> str:
    """The completion phrase this message asserts, or "" (a negative in the same message wins)."""
    if _NO_CLAIM_MARKER.search(text):
        return ""
    match = _CLAIM_MARKER.search(text)
    return match.group(0) if match else ""


def classify_claim(texts: list[str]) -> dict:
    """The claim-equivalent, derived DETERMINISTICALLY from pi's assistant messages.

    pi has no claim gate, so this is OUR reading, recorded with the matching quotes and
    both variants so a reader can audit it. ``asserted_success`` is true when any
    assistant message asserts the work succeeded without a negation in the same message
    (the agent believed it had done the job); ``strict_final`` requires that assertion in
    the CLOSING message, which a run cut off mid-action (T-02) does not have.
    """
    quotes = [t.strip().replace("\n", " ")[:160] for t in texts if _asserts_success(t)]
    strict = bool(_asserts_success(texts[-1])) if texts else False
    if quotes:
        reason = f"an assistant message asserts success: {quotes[-1]!r}"
    elif texts:
        reason = "no assistant message asserts success"
    else:
        reason = "no assistant message"
    return {"asserted_success": bool(quotes), "strict_final": strict,
            "claim_quotes": quotes[-3:], "claim_reason": reason}


# --------------------------------------------------------------------------- run


def _command(pi_bin: str, workdir: Path, prompt: str, base_url: str, model: str,
             provider: str, thinking: str, run_root: Path, agent_dir: Path,
             home: Path, sandbox: bool) -> tuple[list[str], dict, Path | None]:
    """The argv/env/cwd for one pi run, optionally wrapped in bwrap.

    Sandboxed: the host is read-only and ONLY ``run_root`` is writable; the temp agent
    dir and HOME live inside it. Unsandboxed: cwd is the workdir and the prompt tells the
    model to stay there (recorded as a limitation in the run record).
    """
    env = dict(os.environ)
    if sandbox:
        cmd = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--bind", str(run_root), str(run_root),
            "--die-with-parent",
            "--chdir", str(workdir),
            "--setenv", "PI_CODING_AGENT_DIR", str(agent_dir),
            "--setenv", "PI_SKIP_VERSION_CHECK", "1",
            "--setenv", "HOME", str(home),
            pi_bin,
        ]
        cwd = None
    else:
        cmd = [pi_bin]
        cwd = workdir
        env["PI_CODING_AGENT_DIR"] = str(agent_dir)
        env["PI_SKIP_VERSION_CHECK"] = "1"
        env["HOME"] = str(home)
    cmd += [
        "--mode", "json",
        prompt,
        "--model", model,
        "--provider", provider,
        "--no-session",
        "--thinking", thinking,
        "--no-approve",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
    ]
    return cmd, env, cwd


def _run(cmd: list[str], env: dict, cwd: Path | None, timeout_s: int) -> tuple[str, str, bool]:
    """Run bounded; on timeout kill the whole process group and return what we have."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=cwd, env=env, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout_s)
        return out or "", err or "", False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):  # pragma: no cover - race
            pass
        out, err = proc.communicate()
        return out or "", err or "", True


def run_once(task_dir: Path, out_dir: Path, args: argparse.Namespace,
             pi_bin: str) -> dict:
    """Stage one task source-only, run pi on it, and score what it produced."""
    task = load_task(task_dir)
    run_root = out_dir.parent          # holds the temp pi agent dir and HOME
    agent_dir, home = run_root / "agent", run_root / "home"
    if not agent_dir.exists():
        write_agent_dir(agent_dir, args.base_url, bool(getattr(args, "reasoning", False)))
    home.mkdir(parents=True, exist_ok=True)

    workdir = out_dir / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    withheld = stage_blind(workdir, task["files"])

    sandbox = bool(shutil.which("bwrap")) and not args.no_sandbox
    prompt = PI_PROMPT.format(request=task["request"].strip())
    if getattr(args, "ask_tests", False):
        prompt += PI_ASK_TESTS_SUFFIX
    cmd, env, cwd = _command(pi_bin, workdir, prompt, args.base_url, args.model,
                             args.provider, args.thinking, run_root, agent_dir, home,
                             sandbox)

    t0 = time.monotonic()
    out, err, timed_out = _run(cmd, env, cwd, args.timeout)
    wall_s = round(time.monotonic() - t0, 1)

    (out_dir / "events.jsonl").write_text(out)
    (out_dir / "stderr.txt").write_text(err)
    (out_dir / "prompt.txt").write_text(prompt)
    trace = parse_events(out)
    claim = classify_claim(trace["assistant_texts"])

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    quad = quadrant(claim["asserted_success"], score.passed)

    record = {
        "task": task["task_id"],
        "agent": "pi",
        "model": args.model,
        "provider": args.provider,
        "thinking": args.thinking,
        "reasoning": bool(getattr(args, "reasoning", False)),
        "ask_tests": bool(getattr(args, "ask_tests", False)),
        "sandbox": ("bwrap" if sandbox else "none (cwd + prompt only)"),
        "timed_out": timed_out,
        "timeout_s": args.timeout,
        "wall_s": wall_s,
        "withheld_grader_paths": withheld,
        "produced": sorted(produced),
        "own_test_files": sorted(p for p in produced
                                 if PurePosixPath(p).name.startswith("test_")),
        # claim-equivalent (our reading of pi's messages) + the raw evidence
        "claimed": claim["asserted_success"],
        "claimed_strict_final": claim["strict_final"],
        "claim_reason": claim["claim_reason"],
        "claim_quotes": claim["claim_quotes"],
        "final_text": trace["final_text"],
        # actual: the external grader
        "actual": score.passed,
        "quadrant": quad,
        "grader_exit": score.exit,
        "grader_notes": score.notes[-4:],
        "grader_restored": score.restored,
        "grader_shadowed": score.shadowed,
        # behaviour
        **{k: trace[k] for k in ("turns", "tool_calls", "tool_calls_by_name",
                                 "failed_tool_calls", "commands", "ran_command",
                                 "ran_pytest", "files_touched", "wrote_test")},
    }
    (out_dir / "rec.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tasks", default="all",
                    help="'all' for the whole corpus+anchor, or a comma-separated list of "
                         "task dir names (bench/corpus or bench/anchor)")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help="OpenAI-compatible endpoint for the temp models.json")
    ap.add_argument("--thinking", default="off")
    ap.add_argument("--reasoning", action=argparse.BooleanOptionalAction, default=False,
                    help="declare reasoning support on the temp model entry so --thinking "
                         "is honoured rather than clamped to off, and pin the model's "
                         "32768-token context window and output limit; OFF by default so "
                         "the recorded arms stay reproducible")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                    help="seconds per task; a timeout is an outcome, not a crash")
    ap.add_argument("--out", default="",
                    help="run root (ABSOLUTE /tmp path; default /tmp/pi-baseline-<ts>)")
    ap.add_argument("--no-sandbox", action="store_true",
                    help="do not wrap in bwrap; rely on cwd + prompt confinement only")
    ap.add_argument("--ask-tests", action="store_true",
                    help="append an explicit 'write and run your own tests' instruction to "
                         "the prompt, for the with/without-testing-instruction comparison")
    args = ap.parse_args()

    pi_bin = find_pi()
    if pi_bin is None:
        print("[pi] the `pi` executable was not found on PATH", flush=True)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(args.out or f"/tmp/pi-baseline-{ts}")
    if not root.is_absolute():
        print(f"[pi] --out must be an absolute path, got {root}", flush=True)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    results = root / "results.jsonl"

    # ``--tasks all`` sweeps the same corpus+anchor set the harness sweep uses; otherwise a
    # comma list selects exact task dir names from either tree.
    available = [p for base in (ROOT / "bench" / "corpus", ROOT / "bench" / "anchor")
                 for p in sorted(base.iterdir())
                 if p.is_dir() and p.name[:2] in ("T-", "A-")]
    if args.tasks.strip().lower() == "all":
        task_dirs = available
    else:
        want = {n.strip() for n in args.tasks.split(",") if n.strip()}
        task_dirs = [p for p in available if p.name in want]

    rows: list[dict] = []
    for task_dir in task_dirs:
        name = task_dir.name
        for idx in range(1, args.n + 1):
            rec = run_once(task_dir, root / f"{name}-{idx}", args, pi_bin)
            rows.append(rec)
            with results.open("a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            outcome = "TIMEOUT" if rec["timed_out"] else "done"
            print(f"[pi] {name} #{idx}: {outcome} claimed={rec['claimed']} "
                  f"actual={rec['actual']} quadrant={rec['quadrant']} "
                  f"turns={rec['turns']} tools={rec['tool_calls']} "
                  f"pytest={rec['ran_pytest']} test_file={rec['wrote_test']} "
                  f"wall={rec['wall_s']}s", flush=True)

    if rows:
        summary = {
            "agent": "pi", "model": args.model,
            "ask_tests": bool(getattr(args, "ask_tests", False)), "runs": len(rows),
            "timeouts": sum(1 for r in rows if r["timed_out"]),
            "actual_pass": f"{sum(r['actual'] for r in rows)}/{len(rows)}",
            "claimed_pass": f"{sum(r['claimed'] for r in rows)}/{len(rows)}",
            "per_task": {r["task"]: {"claimed": r["claimed"], "actual": r["actual"],
                                     "quadrant": r["quadrant"], "wall_s": r["wall_s"]}
                         for r in rows},
            "output_root": str(root),
        }
        (root / "summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary, indent=1))
    else:
        print("[pi] no task directories matched", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
