#!/usr/bin/env python3
"""The REAL agent baseline: a plain, pi-like tool loop in a sandbox.

Owner correction (2026-09-30): the earlier "bare" driver was not a bare agent — it had a
single write action and no feedback. This is the honest comparison: the model gets the
request and a small tool set (list, read, write, run), sees every tool result, and decides
its own steps, exactly as an ordinary coding agent does. The ONLY things withheld are the
grader's own tests and test infrastructure (``stage_blind``), so it cannot cheat.

One action per turn, in the existing (already validated) write envelope:
  status=ok      file_path="ls"                  -> list repository files
  status=ok      file_path="read:<path>"         -> show a file
  status=ok      file_path="write:<path>"        -> write content (full file)
  status=ok      file_path="run:<command>"       -> run a command in the sandbox
  status=unable  comment="done"                  -> the model declares it is finished

Scored afterwards by the task's own grader, outside the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.external_score import external_score  # noqa: E402
from bench.v2_leaf import load_task, produced_files, quadrant  # noqa: E402
from harness.exec import exec as k_exec  # noqa: E402
from harness.staging import is_test_path, shadowing_path, stage_blind  # noqa: E402
from urllib.request import Request, urlopen  # noqa: E402

SYSTEM = (
    "You are a coding agent working in a repository. Reply with exactly ONE action.\n"
    "ACTION: ls                     (list the repository files)\n"
    "ACTION: read <path>            (show a file)\n"
    "ACTION: write <path>           (then the FULL new file content on the following lines)\n"
    "ACTION: run <command>          (run it; only python3 commands are allowed)\n"
    "ACTION: done                   (the request is satisfied and you are finished)\n"
    "Take one concrete step at a time and check your work. Do not explain; emit actions."
)


def ask(server: str, system: str, user: str) -> str:
    """A plain chat call with NO schema constraint: the baseline must not inherit our
    kernel's envelope shape (that is exactly what made the first attempt invalid)."""
    body = json.dumps({
        "model": "local",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2, "max_tokens": 1200,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = Request(f"{server}/v1/chat/completions", data=body,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def parse_action(text: str) -> tuple[str, str, str]:
    """(action, argument, payload) from a free-form reply. Tolerant on purpose."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.upper().startswith("ACTION:"):
            continue
        rest = stripped.split(":", 1)[1].strip()
        verb, _, argument = rest.partition(" ")
        verb = verb.lower()
        payload = ""
        if verb == "write":
            payload = "\n".join(lines[i + 1:]).strip("\n")
        return verb, argument.strip(), payload
    return "", "", ""
ALLOWED_RUN = re.compile(r"^python3\s+(-m\s+pytest|[^\s]*\.py|[^\s]+\.py)(\s|$)")


def _clip(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...[{len(text) - limit} more chars]"


def _files(workdir: Path) -> list[str]:
    return sorted(str(p.relative_to(workdir)) for p in workdir.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts
                  and not p.name.endswith(".pyc") and not str(p.relative_to(workdir)).startswith(".git"))


VERIFY_NUDGE = ("\nBefore you emit ACTION: done you MUST have (1) written a test that fails on "
                "the current code, (2) run it with ACTION: run python3 -m pytest -q, and "
                "(3) seen it pass after your change. Do not finish otherwise.")


async def run_agent(task_dir: Path, out_dir: Path, server: str, turns: int,
                    nudge: bool = False) -> dict:
    task = load_task(task_dir)
    workdir = out_dir / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    withheld = stage_blind(workdir, task["files"])

    transcript: list[str] = []
    actions: list[str] = []

    for turn in range(1, turns + 1):
        user = (f"Request:\n{task['request']}\n\nTranscript so far:\n"
                + ("\n".join(transcript[-14:]) or "(nothing yet)"))
        try:
            reply = ask(server, SYSTEM + (VERIFY_NUDGE if nudge else ""), user)
        except Exception as exc:
            transcript.append(f"turn {turn}: the transport failed ({type(exc).__name__})")
            continue
        verb, argument, payload = parse_action(reply)
        actions.append(f"{verb} {argument}"[:60])

        if verb == "done" or not verb:
            break
        if verb == "ls":
            result = "\n".join(_files(workdir)) or "(empty)"
        elif verb == "read":
            file = workdir / argument
            result = file.read_text() if file.is_file() else f"(no such file: {argument})"
        elif verb == "write":
            target = argument
            problem = ""
            if not target or target.startswith("/") or ".." in Path(target).parts:
                problem = "refused: path must be inside the repository"
            elif is_test_path(target) and target in set(withheld):
                problem = "refused: that path is not yours to write"
            elif shadowing_path(target):
                problem = "refused: that file name would shadow an interpreter import"
            if problem:
                result = problem
            else:
                file = workdir / target
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(payload)
                result = f"wrote {target} ({len(payload)} bytes)"
        elif verb == "run":
            command = argument
            if not ALLOWED_RUN.match(command):
                result = "refused: only python3 commands are allowed"
            else:
                res = await k_exec(command.split(), workdir, provenance="agent")
                result = f"exit={res.exit}\n" + _clip("\n".join(res.excerpts or []))
        else:
            result = "unknown action; use ls / read / write / run / done"

        transcript.append(f"turn {turn} action: {verb} {argument}\nresult: {_clip(result, 800)}")

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    return {
        "task": task["task_id"], "turns": turns, "actions": actions,
        "actual": score.passed, "quadrant": "agent-pass" if score.passed else "agent-fail",
        "grader_exit": score.exit, "grader_notes": score.notes[-4:],
        "produced": sorted(produced), "withheld": withheld,
        "own_tests": [p for p in produced if is_test_path(p)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--turns", type=int, default=12)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--server", default="http://127.0.0.1:8833")
    ap.add_argument("--verify-nudge", action="store_true")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = "nudge" if args.verify_nudge else "plain"
    root = ROOT / "bench" / "runs" / f"agent-{tag}-turns{args.turns}-{ts}"
    root.mkdir(parents=True, exist_ok=True)
    results = root / "results.jsonl"

    for name in args.tasks.split(","):
        for task_dir in (ROOT / "bench" / "corpus" / name, ROOT / "bench" / "anchor" / name):
            if not task_dir.is_dir():
                continue
            for idx in range(1, args.n + 1):
                t0 = time.monotonic()
                rec = asyncio.run(run_agent(task_dir, root / f"{name}-{idx}", args.server,
                                            args.turns, nudge=args.verify_nudge))
                rec["run_idx"] = idx
                rec["wall_s"] = round(time.monotonic() - t0, 1)
                with results.open("a") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[agent] {name} #{idx}: actual={rec['actual']} "
                      f"turns={len(rec['actions'])} tests={len(rec['own_tests'])}", flush=True)

    rows = [json.loads(l) for l in results.read_text().splitlines()]
    summary = {"runs": len(rows), "turns": args.turns,
               "actual_pass": f"{sum(r['actual'] for r in rows)}/{len(rows)}",
               "per_task": {r["task"]: r["actual"] for r in rows}}
    (root / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
