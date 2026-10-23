#!/usr/bin/env python3
"""Derive the interval-width quantities §3 of the preprint argues with, from committed rows.

    python3 bench/analysis/wave1/n25/interval_widths.py            # print the derivation
    python3 bench/analysis/wave1/n25/interval_widths.py --check    # does the record still match?
    python3 bench/analysis/wave1/n25/interval_widths.py --emit     # rewrite interval-widths.json

The campaign recorded these quantities in `docs/STATUS.md` §3 as prose ("the CI half-width is
about 3.3 tasks and is flat over N=17..25 ...") without a record of its own, so the preprint
listed them as numbers no committed command re-derives. They are derivable: they are the
campaign's own analyzer `analyze_n25.py` run at `N=17..25` over the committed projection, plus a
variance decomposition of the paired per-task differences at `N=25`:

  var(per-task mean difference) = between-task variance + within-task variance / N
  within share (%)            = (mean within-task variance / N) / var(per-task mean difference)
  asymptotic width (tasks)    = 2 * 1.96 * sqrt(40) * sqrt(between-task variance)
  half-width (tasks)          = full width at N=25 / 2
  estimate ACHIEVED needs     = half-width - M

What this file is: a *derived* record, not a campaign-time one. The campaign's own statement of
the same quantities stays in `docs/STATUS.md` §3, and `reproduce.py` compares this derivation
with that sentence digit for digit, so neither can drift silently.
`interval-widths.json` holds the numbers at the precision the paper quotes them, and `--check`
re-derives and diffs it.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PROJ = REPO / "bench" / "projection" / "wave1" / "final"
RECORD = HERE / "interval-widths.json"
N_RANGE = tuple(range(17, 26))
M = 3.0
TASKS = 40


def analyzer():
    """The campaign's own analyzer, with its four roots pointed at the committed projection."""
    sys.path.insert(0, str(HERE))
    import analyze_n25 as an  # noqa: PLC0415 — the campaign's script, unmodified

    an.PRIOR, an.N9, an.N17, an.N25 = PROJ / "our-n5", PROJ / "n9", PROJ / "n17", PROJ / "n25"
    return an


def compute() -> dict:
    an = analyzer()
    out: dict = {"source": "bench/projection/wave1/final", "n": {}}
    widths: dict[int, float] = {}
    for n in N_RANGE:
        res = an.build(n)
        d = res["delta"]
        width = d["hi95"] - d["lo95"]
        widths[n] = width
        out["n"][str(n)] = {"delta": round(d["delta_tasks"], 4), "lo95": round(d["lo95"], 4),
                            "hi95": round(d["hi95"], 4), "width": round(width, 2),
                            "runs": res["ours_n_runs"], "verdict": res["verdict"]}
    out["width_min"] = round(min(widths.values()), 2)
    out["width_max"] = round(max(widths.values()), 2)

    ours, pi = an.collect(max(N_RANGE))
    o = {(str(r["task"]), int(r["seed"])): 1.0 if r["actual"] else 0.0 for r in ours}
    p = {(str(r["task"]), int(r["seed"])): 1.0 if r["actual"] else 0.0 for r in pi}
    by_task: dict[str, list[float]] = defaultdict(list)
    for task, seed in sorted(set(o) & set(p)):
        by_task[task].append(o[(task, seed)] - p[(task, seed)])
    if len(by_task) != TASKS or min(len(v) for v in by_task.values()) != max(N_RANGE):
        raise SystemExit(f"interval_widths: unreadable input: {len(by_task)} paired tasks with "
                         f"{min((len(v) for v in by_task.values()), default=0)}.."
                         f"{max((len(v) for v in by_task.values()), default=0)} seeds, wanted "
                         f"{TASKS} tasks x {max(N_RANGE)} seeds")
    means = [statistics.mean(v) for v in by_task.values()]
    var_means = statistics.variance(means)
    within = statistics.mean(statistics.variance(v) for v in by_task.values())
    between = var_means - within / max(N_RANGE)

    out["half_width_at_n25"] = round(widths[max(N_RANGE)] / 2, 1)
    out["within_share_pct"] = round(100 * (within / max(N_RANGE)) / var_means, 1)
    out["asymptotic_width"] = round(2 * 1.96 * math.sqrt(len(means)) * math.sqrt(between), 1)
    out["needed_estimate"] = round(out["half_width_at_n25"] - M, 1)
    out["verdicts"] = sorted({v["verdict"] for v in out["n"].values()})
    return out


def show(res: dict) -> str:
    lines = [f"{'N':>3} {'delta':>7} {'lo95':>8} {'hi95':>7} {'width':>6} {'runs':>5}  verdict"]
    for n, row in res["n"].items():
        lines.append(f"{n:>3} {row['delta']:>7} {row['lo95']:>8} {row['hi95']:>7} "
                     f"{row['width']:>6} {row['runs']:>5}  {row['verdict']}")
    lines.append(f"width_min {res['width_min']}  width_max {res['width_max']}  "
                 f"half_width_at_n25 {res['half_width_at_n25']}  "
                 f"within_share_pct {res['within_share_pct']}  "
                 f"asymptotic_width {res['asymptotic_width']}  "
                 f"needed_estimate {res['needed_estimate']}  verdicts {res['verdicts']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    res = compute()
    if "--emit" in argv:
        RECORD.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"interval-widths.json: written — {len(res['n'])} N values, "
              f"width {res['width_min']}..{res['width_max']}")
        return 0
    if "--check" in argv:
        if not RECORD.is_file():
            print("interval-widths.json: absent — run with --emit to write it", file=sys.stderr)
            return 1
        recorded = json.loads(RECORD.read_text(encoding="utf-8"))
        if recorded != res:
            differed = sorted(set(recorded) | set(res))
            differed = [k for k in differed if recorded.get(k) != res.get(k)]
            print(f"interval-widths.json: stale — differs in {differed}", file=sys.stderr)
            return 1
        print(f"interval-widths.json: current — width {res['width_min']}..{res['width_max']} "
              f"over N={min(N_RANGE)}..{max(N_RANGE)}, verdicts {res['verdicts']}")
        return 0
    print(show(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
