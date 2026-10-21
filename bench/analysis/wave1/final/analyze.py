#!/usr/bin/env python3
"""Head-to-head analysis for the fix-wave-1 measurement (read-only; no repo code touched).

Reads one or more v2_measure / pi_baseline results.jsonl files, computes the per-arm
summary, the paired per-task difference Delta (in tasks out of 40) and a task-clustered
bootstrap 95% CI with a fixed seed, plus the per-seed run-to-run spread of our arm.

Usage:
  python analyze.py --ours <a.jsonl> [<b.jsonl> ...] --pi <p.jsonl> [<q.jsonl> ...] \
                    --out /tmp/wave1/final/analysis.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BOOTSTRAP_SEED = 20261013
BOOTSTRAP_N = 20000


def load(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def per_task(rows: list[dict], field: str) -> dict[str, float]:
    """Per-task mean of a boolean field (1.0/0.0)."""
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(1.0 if r[field] else 0.0)
    return {t: sum(v) / len(v) for t, v in g.items()}


def per_task_numeric(rows: list[dict], field: str) -> dict[str, float]:
    """Per-task mean of a numeric field (cost columns)."""
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(float(r[field]))
    return {t: sum(v) / len(v) for t, v in g.items()}


def arm_block(rows: list[dict]) -> dict:
    n = len(rows)
    out = {"n_runs": n, "n_tasks": len({str(r["task"]) for r in rows})}
    for f in ("actual", "claimed", "false_success"):
        v = [1.0 if r[f] else 0.0 for r in rows]
        out[f] = {"true": int(sum(v)), "n": n, "rate": sum(v) / n if n else 0.0,
                  "sd": statistics.stdev(v) if n > 1 else 0.0}
        pt = per_task(rows, f)
        out[f]["per_task"] = pt
    walls = per_task_numeric(rows, "_wall")
    toks = per_task_numeric(rows, "_tok")
    out["wall_s_per_task"] = {"mean": statistics.mean(walls.values()),
                              "sd": statistics.stdev(walls.values()),
                              "min": min(walls.values()), "max": max(walls.values())}
    out["tokens_per_task"] = {"mean": statistics.mean(toks.values()),
                              "sd": statistics.stdev(toks.values()),
                              "min": min(toks.values()), "max": max(toks.values())}
    # per-seed 40-task totals, when the arm was run with repeated seeds
    seeds = range(1, max((int(r.get("run_idx", 1)) for r in rows), default=1) + 1)
    totals = []
    for s in seeds:
        rs = [r for r in rows if int(r.get("run_idx", 1)) == s]
        if len(rs) == out["n_tasks"]:
            totals.append(int(sum(1 for r in rs if r["actual"])))
    out["per_seed_actual_totals"] = totals
    if len(totals) > 1:
        out["per_seed_total_mean"] = statistics.mean(totals)
        out["per_seed_total_sd"] = statistics.stdev(totals)
    return out


def bootstrap_delta(ours_pt: dict[str, float], pi_pt: dict[str, float],
                    tasks: list[str]) -> dict:
    diffs = [ours_pt[t] - pi_pt[t] for t in tasks]
    delta = sum(diffs)
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(tasks)
    boots = []
    for _ in range(BOOTSTRAP_N):
        boots.append(sum(diffs[rng.randrange(n)] for _ in range(n)))
    boots.sort()
    lo = boots[int(0.025 * BOOTSTRAP_N)]
    hi = boots[int(0.975 * BOOTSTRAP_N) - 1]
    wins = [t for t, d in zip(tasks, diffs) if d > 0]
    losses = [t for t, d in zip(tasks, diffs) if d < 0]
    return {"delta_tasks": delta, "lo95": lo, "hi95": hi,
            "ours_mean": sum(ours_pt[t] for t in tasks),
            "pi_mean": sum(pi_pt[t] for t in tasks),
            "win_tasks": wins, "loss_tasks": losses,
            "n_tasks": len(tasks)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", nargs="+", required=True)
    ap.add_argument("--pi", nargs="+", default=[])
    ap.add_argument("--pi-label", default="pi")
    ap.add_argument("--ours-label", default="ours")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    ours_rows = load(args.ours)
    for r in ours_rows:
        r["_wall"] = float(r.get("run_wall_s") or 0.0)
        r["_tok"] = float(r.get("total_tokens") or 0.0)
    ours = arm_block(ours_rows)
    result: dict = {"ours_label": args.ours_label, "ours": ours,
                    "ours_sources": args.ours}

    if args.pi:
        pi_rows = load(args.pi)
        for r in pi_rows:
            r["_wall"] = float(r.get("wall_s") or 0.0)
            r["_tok"] = float(r.get("total_tokens") or 0.0)
            if "false_success" not in r:
                r["false_success"] = bool(r.get("claimed")) and not bool(r.get("actual"))
        pi = arm_block(pi_rows)
        result["pi_label"] = args.pi_label
        result["pi"] = pi
        result["pi_sources"] = args.pi
        tasks = sorted(set(ours["actual"]["per_task"]) & set(pi["actual"]["per_task"]))
        result["paired_tasks"] = len(tasks)
        result["delta_run_level"] = (ours["actual"]["rate"] * 40
                                     - pi["actual"]["rate"] * 40)
        result["delta_task_clustered"] = bootstrap_delta(
            ours["actual"]["per_task"], pi["actual"]["per_task"], tasks)
        result["false_success_delta"] = bootstrap_delta(
            ours["false_success"]["per_task"], pi["false_success"]["per_task"], tasks)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
