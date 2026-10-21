#!/usr/bin/env python3
"""Check that the committed projection is the campaign's own rows, not a retyped summary.

Needs the untracked home `bench/runs/wave1/final/`; a reader without it checks the projection
against the committed records instead (`python3 reproduce.py`). For every projection file this
compares, against the home file at the same relative path:

* the row count, and the multiset of `(run_idx, task)` — for `run.json`, the run's own
  `task` and the `task-seed` directory name;
* every kept field's value, byte for byte after JSON round-trip;
* the two reduced fields semantically: `iv_verdicts` by its `approved` sequence,
  `review_verdicts` by truthiness, `nodes` by the `(how_case, forced)` sequence `walk()` sees;
* the `trajectory.jsonl` presence marker against the home file's existence.

    python3 bench/analysis/wave1/fix/verify_projection.py        # ok files=472 rows=2810 mismatches=0
    python3 bench/analysis/wave1/fix/verify_projection.py --proj /copy/of/projection
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HOME = REPO / "bench" / "runs" / "wave1" / "final"
PROJ = REPO / "bench" / "projection" / "wave1" / "final"

R1_FIELDS = ("task", "run_idx", "actual", "claimed", "total_tokens", "run_wall_s", "wall_s")
R2_FIELDS = ("task", "arm", "run_idx", "actual", "claimed", "false_success", "quadrant",
             "total_tokens", "model_calls", "run_wall_s", "claimed_basis", "self_test",
             "stop_reason", "independent_test_reason")
R3_FIELDS = ("task", "actual", "claimed", "calls", "run_wall_s")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def walk(node):
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def shape(nodes) -> list[tuple]:
    """What `analyze.py` and `supp.py` read out of a node tree, as a comparable sequence."""
    return [(tuple(str(c.get("how_case")) for c in (nd.get("candidates") or [])),
             bool((nd.get("allocation") or {}).get("forced"))) for nd in walk(nodes)]


def field_report(want: object, got: object, where: str) -> list[str]:
    return [] if want == got else [f"{where}: {want!r} != {got!r}"]


def main() -> int:
    global PROJ
    ap = argparse.ArgumentParser()
    ap.add_argument("--proj", default=str(PROJ), help="projection root (default: the commit)")
    args = ap.parse_args()
    PROJ = Path(args.proj)
    if not HOME.is_dir():
        print(f"declared home absent: {HOME} (needs the untracked 2 GB home)", file=sys.stderr)
        return 1
    bad: list[str] = []
    files = rows = 0
    for proj in sorted(p for p in PROJ.rglob("*") if p.is_file()):
        rel = proj.relative_to(PROJ)
        home = HOME / rel
        files += 1
        if not home.is_file():
            bad.append(f"{rel}: not in the home")
            continue
        if proj.name == "trajectory.jsonl":
            if proj.stat().st_size:
                bad.append(f"{rel}: marker is not empty ({proj.stat().st_size} bytes)")
            continue
        if proj.name == "run.json":
            rows += 1
            got = json.loads(proj.read_text(encoding="utf-8"))
            src = json.loads(home.read_text(encoding="utf-8"))
            bad += field_report(src["task"], got["task"], f"{rel} task")
            bad += field_report(str(rel.parent.name).rpartition("-")[0], got["task"],
                                f"{rel} directory name vs task")
            for f in R3_FIELDS:
                bad += field_report(src.get(f), got.get(f), f"{rel} {f}")
            bad += field_report(shape(src.get("nodes")), shape(got.get("nodes")),
                                f"{rel} nodes (how_case, forced)")
            continue
        got_rows, src_rows = read_jsonl(proj), read_jsonl(home)
        rows += len(got_rows)
        is_r2 = str(rel).startswith("r2/")
        fields = R2_FIELDS if is_r2 else R1_FIELDS
        bad += field_report(len(src_rows), len(got_rows), f"{rel} row count")
        bad += field_report(Counter((r.get("run_idx"), r.get("task")) for r in src_rows),
                            Counter((r.get("run_idx"), r.get("task")) for r in got_rows),
                            f"{rel} (run_idx, task) multiset")
        for i, (g, s) in enumerate(zip(got_rows, src_rows)):
            for f in fields:
                bad += field_report(s.get(f), g.get(f), f"{rel}:{i + 1} {f}")
            if is_r2:
                bad += field_report([bool(v.get("approved")) for v in (s.get("iv_verdicts") or [])],
                                    [bool(v.get("approved")) for v in (g.get("iv_verdicts") or [])],
                                    f"{rel}:{i + 1} iv_verdicts approved")
                bad += field_report(bool(s.get("review_verdicts")),
                                    bool(g.get("review_verdicts")),
                                    f"{rel}:{i + 1} review_verdicts truthiness")
    for line in bad[:20]:
        print(line)
    print(f"{'ok' if not bad else 'MISMATCH'} files={files} rows={rows} "
          f"mismatches={len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
