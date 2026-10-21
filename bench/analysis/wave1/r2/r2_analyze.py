#!/usr/bin/env python3
"""R2 five-arm ladder analysis: arm table, per-arm quadrants/cost, incremental stage
contributions with a task-clustered bootstrap 95% CI, and the stage-signal join.

Reads the persisted ``results.jsonl`` rows produced by ``r2_lane.py`` (which reuses
``bench/v2_measure.py``'s ``_run_arm``) and writes JSON + a text report. Read-only on the
repo. No claim is re-implemented here: ``actual``/``claimed``/``false_success``/``quadrant``
come straight from the run record.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import random
import statistics
from collections import defaultdict

ARMS = ["dev-only", "own-test-only", "own-iv", "own-review", "full"]
LABEL = {
    "dev-only": "dev-only (raw)",
    "own-test-only": "+own-test",
    "own-iv": "+own-test+IV",
    "own-review": "+own-test+review",
    "full": "full",
}
BOOT_SEED = 20261013
BOOT_N = 10000
N_TASKS = 40

# (with-arm, without-arm, stage label) -- the incremental contribution to report.
PAIRS = [
    ("own-test-only", "dev-only", "own test"),
    ("own-iv", "own-test-only", "independent test (on top of own test)"),
    ("own-review", "own-test-only", "review (on top of own test)"),
    ("full", "own-iv", "review (on top of own test + IV)"),
    ("full", "own-review", "independent test (on top of own test + review)"),
    ("full", "dev-only", "all three stages together"),
]


def load(glob_pat: str) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(glob.glob(glob_pat)):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def per_task_rate(rows: list[dict], field: str) -> dict[str, float]:
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(1.0 if r[field] else 0.0)
    return {t: sum(v) / len(v) for t, v in g.items()}


def per_task_num(rows: list[dict], field: str) -> dict[str, float]:
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        g[str(r["task"])].append(float(r.get(field) or 0.0))
    return {t: sum(v) / len(v) for t, v in g.items()}


def boot_ci(values: list[float], n: int = BOOT_N, seed: int = BOOT_SEED) -> tuple[float, float]:
    """Percentile bootstrap 95% CI of the mean (resampling the 40 tasks)."""
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(rng.choices(values, k=k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def quadrant_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[str(r["quadrant"])] += 1
    return dict(out)


def arm_block(rows: list[dict]) -> dict:
    n = len(rows)
    block: dict = {"n_runs": n, "n_tasks": len({str(r["task"]) for r in rows})}
    for f in ("actual", "claimed", "false_success"):
        v = [1.0 if r[f] else 0.0 for r in rows]
        block[f] = {"true": int(sum(v)), "n": n, "rate": (sum(v) / n) if n else 0.0}
        block[f]["per_task"] = per_task_rate(rows, f)
    block["quadrants"] = quadrant_counts(rows)
    block["tokens_per_task"] = statistics.mean(
        per_task_num(rows, "total_tokens").values()) if rows else 0.0
    block["calls_per_task"] = statistics.mean(
        per_task_num(rows, "model_calls").values()) if rows else 0.0
    block["wall_s_per_task"] = statistics.mean(
        per_task_num(rows, "run_wall_s").values()) if rows else 0.0
    return block


def paired_delta(rows_a: list[dict], rows_b: list[dict], field: str) -> dict:
    """Per-task paired difference (with - without), in tasks out of N_TASKS + 95% CI."""
    pa, pb = per_task_rate(rows_a, field), per_task_rate(rows_b, field)
    tasks = sorted(set(pa) & set(pb))
    d = [pa[t] - pb[t] for t in tasks]
    mean_tasks = statistics.mean(d) * N_TASKS if d else 0.0
    lo, hi = boot_ci(d) if d else (0.0, 0.0)
    # task-level sign test (majority of the seeds decides the task) = exact McNemar
    b = sum(1 for t in tasks if pa[t] > pb[t])
    c = sum(1 for t in tasks if pa[t] < pb[t])
    return {"field": field, "n_tasks": len(tasks),
            "delta_tasks": mean_tasks, "lo95": lo * N_TASKS, "hi95": hi * N_TASKS,
            "tasks_up": b, "tasks_down": c,
            "mcnemar_exact_p": mcnemar_exact(b, c)}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p (binomial sign test on the discordant tasks)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def stage_signals(rows: list[dict]) -> dict:
    """Join each run's stage verdicts to the external grader verdict (record fields)."""
    out: dict = {}
    runs_iv = [r for r in rows if (r.get("iv_verdicts") or r.get("independent_test_reason"))]
    iv_approved = [r for r in runs_iv
                   if r.get("iv_verdicts") and all(v.get("approved") for v in r["iv_verdicts"])]
    iv_blocked = [r for r in runs_iv if r not in iv_approved]
    def on_basis(basis: str) -> list[dict]:
        """Runs whose granted CLAIM was carried by ``basis`` (claimed_basis is a stale
        default on non-claims, so the flag must be gated on claimed=True)."""
        return [r for r in rows if r["claimed"] and basis in (r.get("claimed_basis") or "")]

    out["iv"] = {
        "runs_where_iv_ran": len(runs_iv),
        "iv_approved": len(iv_approved),
        "iv_approved_grader_failed(false-approve)": sum(1 for r in iv_approved if not r["actual"]),
        "iv_blocked": len(iv_blocked),
        "iv_blocked_grader_passed(false-block)": sum(1 for r in iv_blocked if r["actual"]),
        "claimed_on_iv": len(on_basis("independent-test")),
        "claimed_on_iv_grader_failed(false-approve)": sum(
            1 for r in on_basis("independent-test") if not r["actual"]),
    }
    out["review"] = {
        "runs_where_review_ran": len([r for r in rows if r.get("review_verdicts")]),
        "claimed_on_review": len(on_basis("review")),
        "claimed_on_review_grader_failed(false-approve)": sum(
            1 for r in on_basis("review") if not r["actual"]),
    }
    out["own_test"] = {
        "runs_with_self_test": sum(1 for r in rows if r.get("self_test")),
        "claimed_on_own_test": len(on_basis("own-test")),
        "claimed_on_own_test_grader_failed(false-approve)": sum(
            1 for r in on_basis("own-test") if not r["actual"]),
    }
    out["stop_reasons"] = dict(sorted(
        {k: sum(1 for r in rows if str(r.get("stop_reason")) == k)
         for k in {str(r.get("stop_reason")) for r in rows}}.items(), key=lambda kv: -kv[1]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="/tmp/wave1/final/r2/runs/*/*/*/results.jsonl")
    ap.add_argument("--out", default="/tmp/wave1/final/r2/analysis.json")
    ap.add_argument("--text", default="/tmp/wave1/final/r2/analysis.txt")
    args = ap.parse_args()

    rows = load(args.glob)
    by_arm = {a: [r for r in rows if r["arm"] == a] for a in ARMS}
    report: dict = {"n_runs": len(rows), "ladder": {}, "pairs": {}, "signals": {}}

    for a in ARMS:
        report["ladder"][a] = arm_block(by_arm[a])
    for with_a, without_a, label in PAIRS:
        if not by_arm[with_a] or not by_arm[without_a]:
            continue
        report["pairs"][f"{with_a} - {without_a}"] = {
            "stage": label,
            **{f: paired_delta(by_arm[with_a], by_arm[without_a], f)
               for f in ("actual", "claimed", "false_success")},
        }
    for a in ARMS:
        report["signals"][a] = stage_signals(by_arm[a])

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)

    L: list[str] = []
    L.append(f"R2 ladder over {len(rows)} runs; bootstrap seed {BOOT_SEED}, "
             f"{BOOT_N} resamples over the 40 tasks")
    L.append("")
    L.append("arm                  runs  actual        claimed       false-succ    tok/task calls/task")
    for a in ARMS:
        b = report["ladder"][a]
        if not b["n_runs"]:
            L.append(f"{LABEL[a]:<20} 0")
            continue
        L.append(f"{LABEL[a]:<20} {b['n_runs']:>4}  "
                 f"{b['actual']['true']:>3}/{b['actual']['n']:<3} "
                 f"{b['actual']['rate']*100:5.1f}%  "
                 f"{b['claimed']['true']:>3}/{b['claimed']['n']:<3} "
                 f"{b['claimed']['rate']*100:5.1f}%   "
                 f"{b['false_success']['true']:>3} "
                 f"({b['false_success']['rate']*100:5.1f}%)  "
                 f"{b['tokens_per_task']:>8.0f} {b['calls_per_task']:>8.1f}")
    L.append("")
    L.append("arm quadrants (true-success/honest-failure/missed-success/false-success)")
    for a in ARMS:
        b = report["ladder"][a]
        if b["n_runs"]:
            q = b["quadrants"]
            L.append(f"  {LABEL[a]:<20} {q.get('true-success',0)}/{q.get('honest-failure',0)}/"
                     f"{q.get('missed-success',0)}/{q.get('false-success',0)}")
    L.append("")
    L.append("incremental contribution (with - without), paired per task, 40 tasks")
    L.append("pair                                          stage                          "
             "d_actual[95% CI]        d_claimed        d_false[95% CI]   McNemar p")
    for key, blk in report["pairs"].items():
        da, dc, df = blk["actual"], blk["claimed"], blk["false_success"]
        L.append(f"{key:<44} {blk['stage']:<30} "
                 f"{da['delta_tasks']:+5.2f} [{da['lo95']:+5.2f},{da['hi95']:+5.2f}]  "
                 f"{dc['delta_tasks']:+5.2f}          "
                 f"{df['delta_tasks']:+5.2f} [{df['lo95']:+5.2f},{df['hi95']:+5.2f}]  "
                 f"{da['mcnemar_exact_p']:.3f}")
    L.append("")
    L.append("stage signal quality (verdict joined to the external grader)")
    for a in ARMS:
        s = report["signals"][a]
        if not by_arm[a]:
            continue
        L.append(f"  {LABEL[a]}")
        for k, v in s.items():
            if k == "stop_reasons":
                continue
            L.append(f"    {k}: {v}")
    text = "\n".join(L) + "\n"
    with open(args.text, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
