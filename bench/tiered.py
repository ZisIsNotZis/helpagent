#!/usr/bin/env python3
"""Tiered flow (DESIGN §8.1, owner decision 2026-09-18) — the §9.10 verdict
executed: difficulty is DISCOVERED by escalating, never predicted.

Gears (one kernel, shared deterministic safety nets — check_write ladder,
sandbox, untouched contract — which cost zero model calls):
  gear 0: direct whole-file fix (≤3 attempts), no planning machinery
  gear 1: gear 0 + fix_plan enumeration before each emit (+1 call/attempt)
  gear 2: the full golden flow (task_card → expand → spec → AC map → implement)

Escalation: a gear hands over when its gate is red. --gear N overrides the
ladder (the autonomy dial). Every gear persists its own evidence dir; the
results row records the gear that closed the task.

Usage:
  uv run python bench/tiered.py [--n 3] [--tasks a,b|all] [--gear N]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gb", ROOT / "bench" / "golden_bugfix.py")
gb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gb)

SERVER = "http://127.0.0.1:8833"


def load_model(server: str):
    return gb.LlamaServerRunner(server)


def run_gear(gear: int, task_dir: Path, runs_dir: Path, model) -> dict:
    """One gear attempt over one task. Returns the result row."""
    gb.reset_ledger_for_tests()
    task = gb.load_task(task_dir)
    task_id = task["task_id"]
    runs = runs_dir / f"gear{gear}" / task_id
    runs.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    if gear == 2:
        sys.argv = ["golden_bugfix.py", "--task", str(task_dir)]
        rc = gb.main()
        return {"task": task_id, "gear": 2, "result": "PASS" if rc == 0 else "FAIL",
                "wall_s": round(time.monotonic() - t0, 1), "runs_dir": str(runs.parent.parent / task_id)}

    work, trajectory = gb.stage_workdir(runs, task_id, task["files"])
    baseline = trajectory.file_hashes()
    harness_written: set[str] = set()
    creatable = gb.file_tokens(task["request"]) - set(task["files"])
    boundary_all = sorted(set(task["files"]) | creatable)
    spec_shim = SimpleNamespace(
        files_touched=boundary_all, interfaces=[], behavior=task["request"],
        implementation_notes="")
    green = False
    history: list[dict] = []
    with gb.lock(work):
        gb.boot_recover(work, note=gb.note)
        fixed, fix_summary, history = gb.step_implement(
            model, spec_shim, work, task["files"], attempts=3,
            trajectory=trajectory, request=task["request"], creatable=creatable)
        if fixed:
            harness_written.add(fix_summary)
        gate_ok, gate_notes = gb.gate(work, trajectory, baseline, harness_written)
        green = bool(gate_ok and fixed)
        ledger_dump = json.dumps(gb.ledger_entries(), indent=1, ensure_ascii=False)
        (runs / "ledger.json").write_text(ledger_dump)
        (runs / "summary.json").write_text(json.dumps({
            "task": task_id, "gear": gear, "fixed": fixed, "gate_ok": gate_ok,
            "history": history, "gate_notes": gate_notes}, indent=1, ensure_ascii=False))
        trajectory.to_json() and (runs / "trajectory.json").write_text(trajectory.to_json())
    calls = sum(1 for e in gb.ledger_entries() if e.get("kind") == "llm_invocation")
    return {"task": task_id, "gear": gear, "result": "PASS" if green else "FAIL",
            "wall_s": round(time.monotonic() - t0, 1), "calls": calls,
            "attempts": len(history), "runs_dir": str(runs)}


def run_tiered(task_dir: Path, runs_dir: Path, model, gear_override: int | None) -> dict:
    """The ladder: gear 0 → 1 → 2 until one closes the task."""
    start_gear = gear_override if gear_override is not None else 0
    last = None
    for gear in range(start_gear, 3):
        row = run_gear(gear, task_dir, runs_dir, model)
        last = row
        print(f"  [gear {gear}] {row['task']}: {row['result']} ({row['wall_s']}s)", flush=True)
        if row["result"] == "PASS":
            return row
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--gear", type=int, default=None, help="force a gear (override)")
    ap.add_argument("--server", default=SERVER)
    args = ap.parse_args()

    model = load_model(args.server)
    tasks = sorted(p for p in (ROOT / "bench" / "corpus").iterdir()
                   if p.is_dir() and (p.name.startswith("T-") or p.name.startswith("A-")))
    tasks += sorted(p for p in (ROOT / "bench" / "anchor").iterdir()
                    if p.is_dir() and p.name.startswith("A-"))
    if args.tasks != "all":
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.name in want]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = ROOT / "bench" / "runs" / f"tiered-{ts}"
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    print(f"[tiered] {len(tasks)} tasks x {args.n} -> {out}", flush=True)

    for task in tasks:
        for run_idx in range(1, args.n + 1):
            row = run_tiered(task, out, model, args.gear)
            row["run_idx"] = run_idx
            with results.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    agg: dict[str, dict] = {}
    for line in results.read_text().splitlines():
        r = json.loads(line)
        a = agg.setdefault(r["task"], {"pass": 0, "total": 0, "gears": []})
        a["total"] += 1
        a["pass"] += r["result"] == "PASS"
        if r["result"] == "PASS":
            a["gears"].append(r["gear"])
    total = sum(a["total"] for a in agg.values())
    passed = sum(a["pass"] for a in agg.values())
    gear_hist: dict[int, int] = {}
    for a in agg.values():
        for g in a["gears"]:
            gear_hist[g] = gear_hist.get(g, 0) + 1
    summary = {"per_task": {k: f"{v['pass']}/{v['total']}" for k, v in sorted(agg.items())},
               "overall": f"{passed}/{total}", "closing_gear_histogram": gear_hist}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps({"overall": summary["overall"], "gears": gear_hist}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
