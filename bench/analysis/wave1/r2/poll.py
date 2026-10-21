#!/usr/bin/env python3
"""R2 progress poll: per-arm runs / seeds / actual / claimed / false-success.

Reads only the already-persisted ``results.jsonl`` files under
``/tmp/wave1/final/r2/runs/**/``. Appends one checkpoint line per invocation to
``/tmp/wave1/final/r2/checkpoints.md`` (the task's required per-poll checkpoint).
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from datetime import datetime

BASE = "/tmp/wave1/final/r2"
ARMS = ["dev-only", "own-test-only", "own-iv", "own-review", "full"]


def main() -> int:
    note = sys.argv[1] if len(sys.argv) > 1 else ""
    rows = []
    for p in glob.glob(f"{BASE}/runs/*/*/*/results.jsonl"):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
    by_arm: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_arm[str(r["arm"])][str(r["task"])].append(r)
    total_runs = len(rows)
    lines = [f"## checkpoint {datetime.now().astimezone().isoformat(timespec='seconds')}"
             f"  (runs={total_runs}/600) {note}"]
    for arm in ARMS:
        per = by_arm.get(arm)
        if not per:
            lines.append(f"- {arm:<14} runs=0")
            continue
        n = sum(len(v) for v in per.values())
        seeds_min = min(len(v) for v in per.values())
        seeds_max = max(len(v) for v in per.values())
        flat = [r for v in per.values() for r in v]
        act = sum(1 for r in flat if r["actual"])
        clm = sum(1 for r in flat if r["claimed"])
        fs = sum(1 for r in flat if r["false_success"])
        lines.append(f"- {arm:<14} tasks={len(per)}/40 runs={n} seeds={seeds_min}..{seeds_max} "
                     f"actual={act}/{n} claimed={clm}/{n} false={fs}/{n}")
    out = "\n".join(lines) + "\n"
    print(out, end="")
    with open(f"{BASE}/checkpoints.md", "a", encoding="utf-8") as fh:
        fh.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
