#!/usr/bin/env python3
"""Blind sweep of the v2 leaf loop: claimed vs grader, one line per task.

Reuses ``bench/v2_leaf.run_once`` so the sweep and the single-task CLI cannot
drift. Wall-clock is the primary budget (DESIGN §10.2), so the sweep is a plain
sequential loop with a per-task deadline and no retries hidden from the record.

Usage:
  uv run python bench/v2_sweep.py --tasks T-02-off-by-one,T-31-parameter-threading --n 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.v2_leaf import DEFAULT_SERVER, run_once  # noqa: E402

CORPUS = ROOT / "bench" / "corpus"
ANCHOR = ROOT / "bench" / "anchor"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--calls", type=int, default=24)
    ap.add_argument("--deadline-hours", type=float, default=6.0)
    args = ap.parse_args()

    tasks = [p for root in (CORPUS, ANCHOR) for p in sorted(root.iterdir())
             if p.is_dir() and p.name[:2] in ("T-", "A-")]
    if args.tasks != "all":
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.name in want]
    if not tasks:
        print("no tasks matched", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = ROOT / "bench" / "runs" / f"v2sweep-{ts}"
    root.mkdir(parents=True, exist_ok=True)
    results = root / "results.jsonl"

    for task in tasks:
        for idx in range(1, args.n + 1):
            out_dir = root / f"{task.name}-{idx}"
            t0 = time.monotonic()
            try:
                record = run_once(task, out_dir, args.server, args.calls, args.deadline_hours)
            except Exception as exc:                       # keep the sweep recoverable
                record = {"task": task.name, "run_idx": idx, "claimed": False, "actual": False,
                          "quadrant": "honest-failure", "signal": "crashed",
                          "stop_reason": f"crash:{type(exc).__name__}",
                          "grader_notes": [str(exc)[:200]], "calls": 0,
                          "run_wall_s": round(time.monotonic() - t0, 1)}
                (out_dir / "crash.txt").write_text(str(exc))
            record["run_idx"] = idx
            with results.open("a") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[v2] {task.name} #{idx}: claimed={record['claimed']} "
                  f"actual={record['actual']} -> {record['quadrant']} "
                  f"({record.get('calls')} calls, {record.get('run_wall_s')}s, "
                  f"stop={record.get('stop_reason')})", flush=True)

    rows = [json.loads(line) for line in results.read_text().splitlines()]
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["quadrant"]] = tally.get(row["quadrant"], 0) + 1
    summary = {
        "tasks": len(tasks), "runs": len(rows),
        "actual_pass": f"{sum(bool(r['actual']) for r in rows)}/{len(rows)}",
        "claimed_pass": f"{sum(bool(r['claimed']) for r in rows)}/{len(rows)}",
        "quadrants": tally,
        "calls_total": sum(int(r.get("calls") or 0) for r in rows),
        "per_task": {r["task"]: r["quadrant"] for r in rows},
        "stop_reasons": sorted({str(r.get("stop_reason")) for r in rows}),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
