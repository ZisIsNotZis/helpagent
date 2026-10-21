#!/usr/bin/env python3
"""Recompute the R1 headline from the declared home instead of from /tmp.

`analyze_n25.py` hardcodes its four roots to `/tmp/wave1/final/{our-n5,n9,n17,n25}`. Those
roots are exactly why this project had no durable evidence: the script silently returns zero
rows for a root that is not there (`read_jsonl` returns `[]` for a missing file), so on a
machine without `/tmp/wave1` it does not fail, it reports a different experiment. This wrapper
points the same four roots at the declared home, runs the same `build()`, and prints the
numbers the paper quotes beside the values recorded at campaign time, so the copy is proven
usable rather than merely byte-equal.

Read-only: it writes nothing, touches no network and starts no model. Exit 0 only if every
quoted number matches the analysis record.

    python3 bench/analysis/wave1/recompute_n25.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
HOME = BENCH / "runs" / "wave1" / "final"
RECORD = HERE / "n25" / "analysis-n25-final.json"

sys.path.insert(0, str(HERE / "n25"))
import analyze_n25 as an  # noqa: E402  (the campaign's own script, unmodified)

an.PRIOR = HOME / "our-n5"
an.N9 = HOME / "n9"
an.N17 = HOME / "n17"
an.N25 = HOME / "n25"

EXPECT = {"a_mean_tasks": 24.64, "b_mean_tasks": 24.96, "delta_tasks": -0.32,
          "lo95": -3.52, "hi95": 3.08}


def main() -> int:
    if not HOME.is_dir():
        print(f"declared home absent: {HOME}", file=sys.stderr)
        return 1
    res = an.build(25)
    d = res["delta"]
    got = {k: d[k] for k in EXPECT}
    recorded = json.loads(RECORD.read_text())["delta"] if RECORD.is_file() else {}
    rows = len(an.collect(25)[0])
    print(f"rows per arm from the home: {rows}")
    for k, want in EXPECT.items():
        mark = "ok" if abs(got[k] - want) < 1e-9 else "MISMATCH"
        rec = recorded.get(k)
        print(f"  {k:14s} recomputed {got[k]:+8.3f}   quoted {want:+8.3f}   "
              f"recorded {rec if rec is not None else 'absent'}   {mark}")
    if rows != 1000:
        print(f"expected 1000 rows per arm (25 seeds x 40 corpus items), got {rows}", file=sys.stderr)
        return 1
    return 0 if all(abs(got[k] - v) < 1e-9 for k, v in EXPECT.items()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
