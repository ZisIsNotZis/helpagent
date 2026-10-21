#!/usr/bin/env python3
"""Render the N=25 head-to-head tables (read-only) from analyze_n25's data + raw rows."""
from __future__ import annotations
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/wave1/final/n25")
import analyze_n25 as an

A = json.load(open("/tmp/wave1/final/n25/analysis-n25-final.json"))
N = A["nmax"]
ours_rows, pi_rows = an.collect(N)


def band(t: str) -> str:
    if t.startswith("A-"):
        return "anchors"
    i = int(t.split("-")[1])
    if i <= 10: return "easy"
    if i <= 20: return "mid1"
    if i <= 30: return "mid2"
    return "tail"


def pt(rows, field):
    return an.per_task(rows, field)


oa, pa = pt(ours_rows, "actual"), pt(pi_rows, "actual")
oc, pc = pt(ours_rows, "claimed"), pt(pi_rows, "claimed")
ofs, pfs = pt(ours_rows, "false_success"), pt(pi_rows, "false_success")
tasks = sorted(oa)
bands = ["easy", "mid1", "mid2", "tail", "anchors"]

out = []
out += [f"### Per-task (ours N={N} · pi N={N})", "",
        "| task | band | ours act | pi act | ours clm | pi clm | ours false | pi false |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |"]
for t in tasks:
    out.append(f"| {t} | {band(t)} | {oa[t]*N:.0f}/{N} | {pa[t]*N:.0f}/{N} | "
               f"{oc[t]*N:.0f}/{N} | {pc[t]*N:.0f}/{N} | "
               f"{ofs[t]*N:.0f}/{N} | {pfs[t]*N:.0f}/{N} |")
out.append("")
out += [f"### Per-band (each cell = mean per-task actual, N={N}/task)", "",
        "| band | ours | pi |", "| --- | --- | --- |"]
for b in bands:
    ts = [t for t in tasks if band(t) == b]
    o = sum(oa[t] for t in ts)
    p = sum(pa[t] for t in ts)
    out.append(f"| {b} ({len(ts)} tasks) | {o:.2f}/{len(ts)} | {p:.2f}/{len(ts)} |")
out.append(f"| **total (40 tasks)** | **{sum(oa[t] for t in tasks):.3f}/40** | "
           f"**{sum(pa[t] for t in tasks):.3f}/40** |")
out.append("")
ours_tot = [v for _, v in A["ours_seed_totals"]]
pi_tot = [v for _, v in A["pi_seed_totals"]]
out += ["### Arm summary", "",
        "| metric | ours | pi |", "| --- | --- | --- |",
        f"| actual | {A['ours_actual_true']}/{A['ours_n_runs']} = "
        f"{100*A['ours_actual_true']/A['ours_n_runs']:.1f}% | "
        f"{A['pi_actual_true']}/{A['pi_n_runs']} = "
        f"{100*A['pi_actual_true']/A['pi_n_runs']:.1f}% |",
        f"| actual per 40-task run | mean {statistics.mean(ours_tot):.3f}, "
        f"sd {statistics.stdev(ours_tot):.3f} | mean {statistics.mean(pi_tot):.3f}, "
        f"sd {statistics.stdev(pi_tot):.3f} |",
        f"| claimed (not comparable) | {A['ours_claimed_true']}/{A['ours_n_runs']} | "
        f"{A['pi_claimed_true']}/{A['pi_n_runs']} |",
        f"| false success | {A['ours_false_success_true']}/{A['ours_n_runs']} = "
        f"{100*A['ours_false_success_true']/A['ours_n_runs']:.2f}% | "
        f"{A['pi_false_success_true']}/{A['pi_n_runs']} = "
        f"{100*A['pi_false_success_true']/A['pi_n_runs']:.2f}% |",
        f"| wall s/task (4-lane) | {A['ours_wall_per_task_mean']:.1f} | {A['pi_wall_per_task_mean']:.1f} |",
        f"| tokens/task (4-lane) | {A['ours_tokens_per_task_mean']:.0f} | unmeasured (pi carries no token counters) |",
        "| crashes / timeouts | 0 / 0 | 0 / 0 |", "",
        "Ours seed totals (1..25):", "`" + ", ".join(str(v) for v in ours_tot) + "`", "",
        "pi seed totals (1..25):", "`" + ", ".join(str(v) for v in pi_tot) + "`", ""]

Path("/tmp/wave1/final/n25/tables-n25.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
