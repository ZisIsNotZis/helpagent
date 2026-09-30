#!/usr/bin/env python3
"""The BARE baseline: no test-first, no gate, no judge, no independent test.

Owner question (2026-09-30): do the failures come from our forced flow, or would the
reference model fail the same way on its own? This driver gives the model the request
and the source and nothing else — no self-test requirement, no red-first rule, no
verification loop of any kind. It may edit files and say it is done.

    --calls 1   pure one-shot (single model call)
    --calls N   the model may keep editing, but with NO feedback from any test run

Scored afterwards by the task's own grader, outside the run (bench/external_score).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.external_score import external_score  # noqa: E402
from bench.v2_leaf import load_task, produced_files, quadrant  # noqa: E402
from harness.model import LlamaServerRunner  # noqa: E402
from harness.runner import llm_step  # noqa: E402
from harness.staging import stage_blind  # noqa: E402

QUESTION = (
    "You are given a repository and a request. Change the source files so the request is "
    "satisfied. You may edit one file per reply. Reply with the file path and its FULL new "
    "content. If you believe the request is already fully satisfied and nothing further is "
    "needed, reply with status 'unable' and comment 'done'."
)


def source_view(workdir: Path, files: dict[str, str]) -> dict[str, str]:
    out = {}
    for rel in sorted(files):
        path = workdir / rel
        if path.is_file():
            out[rel] = path.read_text()
    return out


async def run_bare(task_dir: Path, out_dir: Path, server: str, calls: int) -> dict:
    task = load_task(task_dir)
    workdir = out_dir / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    withheld = stage_blind(workdir, task["files"])
    model = LlamaServerRunner(server)
    written: list[str] = []
    bad = 0

    for step in range(1, calls + 1):
        artifacts = {"request": task["request"],
                     "files": "\n\n".join(f"### {rel}\n{c}" for rel, c in
                                          source_view(workdir, task["files"]).items())}
        try:
            env = await llm_step(model, "write_test", artifacts=artifacts, question=QUESTION)
        except Exception as exc:                      # a malformed reply is a wasted step
            bad += 1
            if bad >= 2:
                break
            continue
        if getattr(env, "status", "unable") != "ok":
            break
        path = getattr(env, "file_path", "") or ""
        content = getattr(env, "content", "") or ""
        if not path or not content or path not in task["files"]:
            continue
        (workdir / path).write_text(content)
        written.append(path)

    produced = produced_files(workdir)
    score = external_score(task_dir, produced, out_dir / "grade")
    return {
        "task": task["task_id"], "calls": calls, "steps_written": written,
        "claimed": None, "actual": score.passed, "malformed": bad,
        "quadrant": "bare-pass" if score.passed else "bare-fail",
        "grader_exit": score.exit, "grader_notes": score.notes[-4:],
        "produced": sorted(produced), "withheld": withheld,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--calls", type=int, default=1)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--server", default="http://127.0.0.1:8833")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = ROOT / "bench" / "runs" / f"bare-calls{args.calls}-{ts}"
    root.mkdir(parents=True, exist_ok=True)
    results = root / "results.jsonl"

    for name in args.tasks.split(","):
        for task_dir in (ROOT / "bench" / "corpus" / name, ROOT / "bench" / "anchor" / name):
            if not task_dir.is_dir():
                continue
            for idx in range(1, args.n + 1):
                t0 = time.monotonic()
                rec = asyncio.run(run_bare(task_dir, root / f"{name}-{idx}", args.server,
                                           args.calls))
                rec["run_idx"] = idx
                rec["wall_s"] = round(time.monotonic() - t0, 1)
                with results.open("a") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[bare{args.calls}] {name} #{idx}: "
                      f"actual={rec['actual']} wrote={len(rec['steps_written'])}",
                      flush=True)

    rows = [json.loads(l) for l in results.read_text().splitlines()]
    summary = {"runs": len(rows), "actual_pass": f"{sum(r['actual'] for r in rows)}/{len(rows)}",
               "per_task": {r["task"]: r["actual"] for r in rows}}
    (root / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
