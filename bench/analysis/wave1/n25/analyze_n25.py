#!/usr/bin/env python3
"""Head-to-head N<=17 analysis for the fix-wave-1 measurement (read-only; no repo code).

Reuses the frozen pre-registered decision rule and the exact CI method of the N=5 / N=9
analyses (task-clustered percentile bootstrap, fixed seed 20261013, B=20000):

  Delta = actual(ours) - actual(pi), paired by task, per-task means over each arm's seeds.
  M = 3 tasks.  Lo95(Delta) >= -M  -> ACHIEVED (parity within margin)
                Hi95(Delta) <  -M  -> BEHIND
                otherwise          -> INCONCLUSIVE
  BEAT (strict win) is a note: Lo95(Delta) > 0 (reported at N>=17).

Seeds are read from the frozen N=9 roots (reused, valid on 45ebb32 / :8834) plus the new
N=17 roots:

  ours  seeds 1..5   : /tmp/wave1/final/our-n5/<lane>/none/results.jsonl   (run_idx 1..5)
  ours  seeds 6..9   : /tmp/wave1/final/n9/our-extra/<lane>/none/results.jsonl (idx 1..4)
  ours  seeds 10..17 : /tmp/wave1/final/n17/our-extra/seed<n>/<lane>/results.jsonl
  ours  seeds 18..k : /tmp/wave1/final/n25/our-extra/seed<n>/<lane>/none/results.jsonl
  pi    seeds 1..9   : /tmp/wave1/final/n9/pi-n9/seed<n>/<lane>/results.jsonl
  pi    seeds 10..17 : /tmp/wave1/final/n17/pi-extra/seed<n>/<lane>/results.jsonl
  pi    seeds 18..k : /tmp/wave1/final/n25/pi-extra/seed<n>/<lane>/results.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BOOTSTRAP_SEED = 20261013
BOOTSTRAP_N = 20000
M = 3.0
TASKS_N = 40
LANES = ("lane1", "lane2", "lane3", "lane4")
PRIOR = Path("/tmp/wave1/final/our-n5")
N9 = Path("/tmp/wave1/final/n9")
N17 = Path("/tmp/wave1/final/n17")
N25 = Path("/tmp/wave1/final/n25")


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def read_our_seed(n: int) -> list[dict]:
    """The 40 rows of our arm for global seed ``n`` (1-indexed), or [] if absent."""
    rows: list[dict] = []
    if 1 <= n <= 5:
        for lane in LANES:
            for r in read_jsonl(PRIOR / lane / "none" / "results.jsonl"):
                if int(r["run_idx"]) == n:
                    r["seed"] = n
                    rows.append(r)
    elif 6 <= n <= 9:
        for lane in LANES:
            for r in read_jsonl(N9 / "our-extra" / lane / "none" / "results.jsonl"):
                if 5 + int(r["run_idx"]) == n:
                    r["seed"] = n
                    rows.append(r)
    elif 10 <= n <= 17:
        for lane in LANES:
            for r in read_jsonl(N17 / "our-extra" / f"seed{n}" / lane / "none" / "results.jsonl"):
                r["seed"] = n
                rows.append(r)
    elif n >= 18:
        for lane in LANES:
            for r in read_jsonl(N25 / "our-extra" / f"seed{n}" / lane / "none" / "results.jsonl"):
                r["seed"] = n
                rows.append(r)
    return rows


def read_pi_seed(n: int) -> list[dict]:
    """The 40 rows of the pi arm for global seed ``n`` (1-indexed), or [] if absent."""
    rows: list[dict] = []
    if 1 <= n <= 9:
        for lane in LANES:
            for r in read_jsonl(N9 / "pi-n9" / f"seed{n}" / lane / "results.jsonl"):
                r["seed"] = n
                rows.append(r)
    elif 10 <= n <= 17:
        for lane in LANES:
            for r in read_jsonl(N17 / "pi-extra" / f"seed{n}" / lane / "results.jsonl"):
                r["seed"] = n
                rows.append(r)
    elif n >= 18:
        for lane in LANES:
            for r in read_jsonl(N25 / "pi-extra" / f"seed{n}" / lane / "results.jsonl"):
                r["seed"] = n
                rows.append(r)
    return rows


def collect(nmax: int) -> tuple[list[dict], list[dict]]:
    ours = [r for n in range(1, nmax + 1) for r in read_our_seed(n)]
    pi = [r for n in range(1, nmax + 1) for r in read_pi_seed(n)]
    for r in ours:
        r.setdefault("false_success", bool(r.get("claimed")) and not bool(r.get("actual")))
    for r in pi:
        r.setdefault("false_success", bool(r.get("claimed")) and not bool(r.get("actual")))
    return ours, pi


def per_task(rows: list[dict], field: str) -> dict[str, float]:
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(1.0 if r[field] else 0.0)
    return {t: sum(v) / len(v) for t, v in g.items()}


def per_task_seed_counts(rows: list[dict]) -> dict[str, int]:
    g: dict[str, int] = defaultdict(int)
    for r in rows:
        g[str(r["task"])] += 1
    return dict(g)


def per_task_numeric(rows: list[dict], field: str) -> dict[str, float]:
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(float(r.get(field) or 0.0))
    return {t: sum(v) / len(v) for t, v in g.items()}


def seed_totals(rows: list[dict]) -> list[tuple[int, int]]:
    g: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        g[int(r["seed"])].append(r)
    out: list[tuple[int, int]] = []
    for s in sorted(g):
        rs = g[s]
        if len(rs) == TASKS_N:
            out.append((s, int(sum(1 for r in rs if r["actual"]))))
    return out


def bootstrap_delta(a_pt: dict[str, float], b_pt: dict[str, float],
                    tasks: list[str]) -> dict:
    diffs = [a_pt[t] - b_pt[t] for t in tasks]
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(tasks)
    boots = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(BOOTSTRAP_N))
    return {"delta_tasks": sum(diffs),
            "lo95": boots[int(0.025 * BOOTSTRAP_N)],
            "hi95": boots[int(0.975 * BOOTSTRAP_N) - 1],
            "a_mean_tasks": sum(a_pt[t] for t in tasks),
            "b_mean_tasks": sum(b_pt[t] for t in tasks),
            "n_tasks": n}


def verdict(d: dict) -> str:
    if d["lo95"] >= -M:
        return "ACHIEVED"
    if d["hi95"] < -M:
        return "BEHIND"
    return "INCONCLUSIVE"


def build(nmax: int) -> dict:
    ours_rows, pi_rows = collect(nmax)
    ours_pt = per_task(ours_rows, "actual")
    pi_pt = per_task(pi_rows, "actual")
    ours_fs = per_task(ours_rows, "false_success")
    pi_fs = per_task(pi_rows, "false_success")
    tasks = sorted(set(ours_pt) & set(pi_pt))
    d = bootstrap_delta(ours_pt, pi_pt, tasks)
    fs = bootstrap_delta(ours_fs, pi_fs, tasks)
    our_counts = per_task_seed_counts(ours_rows)
    pi_counts = per_task_seed_counts(pi_rows)
    o_tok = per_task_numeric(ours_rows, "total_tokens")
    o_wall = per_task_numeric(ours_rows, "run_wall_s")
    p_wall = per_task_numeric(pi_rows, "wall_s")
    ot = seed_totals(ours_rows)
    pt = seed_totals(pi_rows)
    return {
        "nmax": nmax,
        "paired_tasks": len(tasks),
        "our_seed_min_per_task": min(our_counts.values()) if our_counts else 0,
        "pi_seed_min_per_task": min(pi_counts.values()) if pi_counts else 0,
        "ours_actual_true": int(sum(1 for r in ours_rows if r["actual"])),
        "ours_n_runs": len(ours_rows),
        "pi_actual_true": int(sum(1 for r in pi_rows if r["actual"])),
        "pi_n_runs": len(pi_rows),
        "ours_claimed_true": int(sum(1 for r in ours_rows if r["claimed"])),
        "pi_claimed_true": int(sum(1 for r in pi_rows if r["claimed"])),
        "ours_false_success_true": int(sum(1 for r in ours_rows if r["false_success"])),
        "pi_false_success_true": int(sum(1 for r in pi_rows if r["false_success"])),
        "ours_seed_totals": ot,
        "pi_seed_totals": pt,
        "ours_seed_total_mean": statistics.mean([t for _, t in ot]) if ot else 0.0,
        "ours_seed_total_sd": statistics.stdev([t for _, t in ot]) if len(ot) > 1 else 0.0,
        "pi_seed_total_mean": statistics.mean([t for _, t in pt]) if pt else 0.0,
        "pi_seed_total_sd": statistics.stdev([t for _, t in pt]) if len(pt) > 1 else 0.0,
        "ours_tokens_per_task_mean": statistics.mean(o_tok.values()) if o_tok else 0.0,
        "ours_wall_per_task_mean": statistics.mean(o_wall.values()) if o_wall else 0.0,
        "pi_wall_per_task_mean": statistics.mean(p_wall.values()) if p_wall else 0.0,
        "delta": d,
        "false_success_delta": fs,
        "M": M,
        "verdict": verdict(d),
        "beat_strict_lo95_gt_0": d["lo95"] > 0,
        "per_task_actual": {"ours": ours_pt, "pi": pi_pt},
        "per_task_false_success": {"ours": ours_fs, "pi": pi_fs},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nmax", type=int, required=True, help="highest seed index to include")
    ap.add_argument("--out", default=str(N25 / "analysis-n25.json"))
    ap.add_argument("--checkpoint", default="",
                    help="append a one-line checkpoint to this markdown file")
    args = ap.parse_args()

    res = build(args.nmax)
    Path(args.out).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")

    if args.checkpoint:
        d = res["delta"]
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        line = (f"* {ts} — N={args.nmax}/arm; ours {res['ours_actual_true']}/"
                f"{res['ours_n_runs']} ({res['ours_seed_total_mean']:.3f}/40); pi "
                f"{res['pi_actual_true']}/{res['pi_n_runs']} "
                f"({res['pi_seed_total_mean']:.3f}/40); Δ={d['delta_tasks']:+.3f}; "
                f"task-clustered 95% CI [{d['lo95']:+.3f}, {d['hi95']:+.3f}]; "
                f"rule={res['verdict']} (M={M:g}).\n")
        with Path(args.checkpoint).open("a", encoding="utf-8") as fh:
            fh.write(line)

    print(json.dumps({
        "nmax": res["nmax"], "our_seed_min_per_task": res["our_seed_min_per_task"],
        "pi_seed_min_per_task": res["pi_seed_min_per_task"],
        "delta": res["delta"], "false_success_delta": res["false_success_delta"],
        "verdict": res["verdict"], "beat_strict_lo95_gt_0": res["beat_strict_lo95_gt_0"],
        "ours_actual": f"{res['ours_actual_true']}/{res['ours_n_runs']}",
        "pi_actual": f"{res['pi_actual_true']}/{res['pi_n_runs']}",
        "ours_false_success": f"{res['ours_false_success_true']}/{res['ours_n_runs']}",
        "pi_false_success": f"{res['pi_false_success_true']}/{res['pi_n_runs']}",
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
