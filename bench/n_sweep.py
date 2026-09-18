#!/usr/bin/env python3
"""N-repeated-runs sweep (DESIGN §6: per-task pass RATE, not single-run pass/fail —
run-to-run sampling noise at temp 0.2 is measured, M0 finding).

Usage: uv run python bench/n_sweep.py [--n 3] [--tasks T-01,...|all]
Incremental: each run appends one line to bench/runs/n-sweep-<ts>/results.jsonl;
re-running skips (task, run_idx) pairs already present, so an interrupted sweep
resumes where it stopped."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "bench" / "corpus"
MINI = ROOT / "tests" / "fixtures" / "mini_repo"


def tasks() -> list[Path]:
    out = [MINI] + sorted(p for p in CORPUS.iterdir() if p.is_dir() and p.name.startswith("T-"))
    return out


def run_once(task: Path, workdir: Path, run_idx: int, golden_args: str = "") -> dict:
    cmd = [sys.executable, str(ROOT / "bench" / "golden_bugfix.py"), "--task", str(task)]
    cmd += shlex.split(golden_args)
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    wall = round(time.monotonic() - t0, 1)
    m = re.search(r"\[result\] (PASS|FAIL)", r.stdout)
    result = m.group(1) if m else "CRASH"
    m_dir = re.search(r"\[persist\] (\S+)", r.stdout)
    runs_dir = m_dir.group(1) if m_dir else ""
    # keep the golden stdout/stderr: the failed-attempt excerpts live ONLY here
    # (erasure wipes the work tree; the ledger holds no content) — without this
    # log, every FAIL is undiagnosable after the fact
    (workdir / f"{task.name}.run{run_idx}.log").write_text(
        r.stdout + "\n===== STDERR =====\n" + r.stderr)
    return {"result": result, "wall_s": wall, "exit": r.returncode, "runs_dir": runs_dir}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--only", default="", help="comma list of task dir names to (re)run")
    ap.add_argument("--golden-args", default="",
                    help="extra args passed through to golden_bugfix.py (script-variant A/B)")
    ap.add_argument("--corpus", default=str(CORPUS),
                    help="task tree (default: bench/corpus); pass bench/anchor for anchors")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "bench" / "runs" / f"n-sweep-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    corpus_path = Path(args.corpus)
    all_tasks = [MINI] + sorted(p for p in corpus_path.iterdir()
                                if p.is_dir() and (p.name.startswith("T-") or p.name.startswith("A-")))
    if args.tasks != "all":
        want = set(args.tasks.split(","))
        all_tasks = [t for t in all_tasks if t.name in want]
    if args.only:
        want = set(args.only.split(","))
        all_tasks = [t for t in all_tasks if t.name in want]

    done: set[tuple[str, int]] = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            try:
                rec = json.loads(line)
                done.add((rec["task"], rec["run_idx"]))
            except Exception:
                pass

    for task in all_tasks:
        for run_idx in range(1, args.n + 1):
            if (task.name, run_idx) in done:
                print(f"[skip] {task.name} #{run_idx}", flush=True)
                continue
            rec = {"task": task.name, "run_idx": run_idx,
                   **run_once(task, out_dir, run_idx, args.golden_args)}
            with results_path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[run] {task.name} #{run_idx}: {rec['result']} ({rec['wall_s']}s)", flush=True)

    # aggregate
    agg: dict[str, dict[str, int]] = {}
    for line in results_path.read_text().splitlines():
        rec = json.loads(line)
        a = agg.setdefault(rec["task"], {"pass": 0, "total": 0})
        a["total"] += 1
        a["pass"] += rec["result"] == "PASS"
    table = {k: f"{v['pass']}/{v['total']}" for k, v in sorted(agg.items())}
    summary = {"per_task": table,
               "overall": f"{sum(v['pass'] for v in agg.values())}/{sum(v['total'] for v in agg.values())}"}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
