#!/usr/bin/env python3
"""R2 resume wrapper (measurement only; the repo is never modified).

Same command shape and same machinery as ``r2_lane.py`` (which drives
``bench.v2_measure._run_arm`` -> ``bench.v2_leaf.run_once``), with ONE addition: a
(task, seed) cell already present in the arm's ``results.jsonl`` is SKIPPED instead of
re-run. ``bench.v2_measure._run_arm`` always iterates every (task, seed) and appends, so
re-running a killed job with the stock driver would duplicate completed cells; this
wrapper exists solely to finish the 220 cells the dead worker left unrun, without
touching already-persisted measurements.

Row shape, per-cell ``out_dir`` layout, token accounting and the ``false_success``
derivation are copied verbatim from ``bench.v2_measure._run_arm`` so resumed rows are
indistinguishable from the originals.

Usage:
  uv run python /tmp/wave1/final/r2/r2_resume.py --arm full \
      --tasks T-11-...,T-12-... --n 3 --out /tmp/wave1/final/r2/runs/c2/full
  ... --dry-run   # list the missing cells only, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/z/vibe/helpagent")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/tmp/wave1/final/r2")

import bench.v2_measure as M  # noqa: E402
import r2_lane  # noqa: E402  (provides LADDER: the identical five-arm definitions)


def existing_cells(results: Path) -> set[tuple[str, int]]:
    done: set[tuple[str, int]] = set()
    if results.is_file():
        for line in results.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((str(r["task"]), int(r["run_idx"])))
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(r2_lane.LADDER))
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--server", default="http://127.0.0.1:8834")
    ap.add_argument("--calls", type=int, default=24)
    ap.add_argument("--deadline-hours", type=float, default=6.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    arm = r2_lane.LADDER[args.arm]
    tasks = M.discover_tasks(args.tasks)
    if not tasks:
        print(f"no tasks matched {args.tasks!r}", file=sys.stderr)
        return 2
    root = Path(args.out)
    results = root / arm.name / "results.jsonl"
    done = existing_cells(results)
    missing = [(t, idx) for t in tasks for idx in range(1, args.n + 1)
               if (t.name, idx) not in done]
    print(f"[resume] arm={arm.name} tasks={len(tasks)} present={len(done)} "
          f"missing={len(missing)}", flush=True)
    if args.dry_run:
        for t, idx in missing:
            print(f"  missing {t.name} #{idx}")
        return 0

    root.mkdir(parents=True, exist_ok=True)
    results.parent.mkdir(parents=True, exist_ok=True)
    if not (root / "arm.json").is_file():  # c4 was never started; keep r2_lane's shape
        (root / "arm.json").write_text(json.dumps({
            "arm": M._ablation_dict(arm), "tasks": [t.name for t in tasks],
            "n": args.n, "calls": args.calls, "deadline_hours": args.deadline_hours,
            "server": args.server, "repo_head": r2_lane._head_sha(),
            "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resumed_by": "r2_resume.py",
        }, indent=1, ensure_ascii=False))
    (root / "resume.json").write_text(json.dumps({
        "arm": arm.name, "resumed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "present_before": len(done), "missing_cells": [f"{t.name}#{i}" for t, i in missing],
        "repo_head": r2_lane._head_sha(), "server": args.server,
    }, indent=1, ensure_ascii=False))

    for task, idx in missing:
        out_dir = root / arm.name / f"{task.name}-{idx}"
        t0 = time.monotonic()
        try:
            record = M.run_once(task, out_dir, args.server, args.calls,
                                args.deadline_hours, use_judge=arm.use_judge,
                                use_iv=arm.use_iv, use_review=arm.use_review,
                                verify_mode=arm.verify_mode)
        except Exception as exc:  # noqa: BLE001 - keep the measurement recoverable
            out_dir.mkdir(parents=True, exist_ok=True)
            record = {"task": task.name, "claimed": False, "actual": False,
                      "quadrant": "honest-failure", "signal": "crashed",
                      "stop_reason": f"crash:{type(exc).__name__}",
                      "grader_notes": [str(exc)[:200]], "calls": 0,
                      "run_wall_s": round(time.monotonic() - t0, 1)}
            (out_dir / "crash.txt").write_text(str(exc))
        record["run_idx"] = idx
        record["arm"] = arm.name
        record["run_wall_s"] = round(float(record.get("run_wall_s") or 0.0), 1)
        record.update(M.read_token_usage(out_dir / "trajectory.jsonl"))
        record["false_success"] = bool(record["claimed"]) and not bool(record["actual"])
        with results.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{arm.name}] {task.name} #{idx}: claimed={record['claimed']} "
              f"actual={record['actual']} -> {record['quadrant']} "
              f"({record.get('calls')} calls, {record['run_wall_s']}s, "
              f"{record['total_tokens']} tokens, stop={record.get('stop_reason')})",
              flush=True)

    all_rows = [json.loads(l) for l in results.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    summary = M.arm_summary(all_rows)
    summary["arm"] = M._ablation_dict(arm)
    (root / arm.name / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False))
    print(M.render_arm(arm, summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
