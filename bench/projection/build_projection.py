#!/usr/bin/env python3
"""Rebuild `bench/projection/wave1/` from the untracked 2 GB home.

This is a maintainer recipe, not part of the reproduce path: it reads
`bench/runs/wave1/final/`, which a clean clone does not have. `reproduce.py` reads only what
this script wrote. Run from the repository root:

    python3 bench/projection/build_projection.py            # write the projection
    python3 bench/projection/build_projection.py --check     # recompute and diff, write nothing

Every field kept is a field a campaign analyzer reads; every field dropped is one none does.
The arithmetic that turns these rows into the paper's numbers is still the campaign's own
(`bench/analysis/wave1/{n25,r2,r3}/`), executed unmodified by `reproduce.py`.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = REPO / "bench" / "runs" / "wave1" / "final"
PROJ = REPO / "bench" / "projection" / "wave1" / "final"

# --- R1 (`n25/analyze_n25.py`) -------------------------------------------------------------
# `read_our_seed`/`read_pi_seed` filter on run_idx; `build` reads task, actual, claimed and the
# numeric means; `collect` derives false_success from claimed/actual.
R1_PATTERNS = (
    "our-n5/*/none/results.jsonl",
    "n9/our-extra/*/none/results.jsonl",
    "n9/pi-n9/*/*/results.jsonl",
    "n17/our-extra/*/*/none/results.jsonl",
    "n17/pi-extra/*/*/results.jsonl",
    "n25/our-extra/*/*/none/results.jsonl",
    "n25/pi-extra/*/*/results.jsonl",
)
R1_FIELDS = ("task", "run_idx", "actual", "claimed", "total_tokens", "run_wall_s", "wall_s")

# --- R2 (`r2/r2_analyze.py`) ---------------------------------------------------------------
# `arm_block`/`paired_delta` read task, arm, actual, claimed, false_success, quadrant and the
# three cost fields; `stage_signals` reads iv_verdicts[].approved, independent_test_reason,
# review_verdicts (presence only), claimed_basis, self_test (presence only), stop_reason.
R2_GLOB = "r2/runs/*/*/*/results.jsonl"
R2_FIELDS = ("task", "arm", "run_idx", "actual", "claimed", "false_success", "quadrant",
             "total_tokens", "model_calls", "run_wall_s", "claimed_basis", "self_test",
             "stop_reason", "independent_test_reason")

# --- R3 (`r3/analyze.py`, `r3/supp.py`) ----------------------------------------------------
# Both walk `run.json["nodes"]` and read `candidates[].how_case` and `allocation.forced`, plus
# actual, claimed, calls, run_wall_s. `analyze.py` also counts `trajectory.jsonl` presence.
R3_ARMS = ("leaf", "tree-greedy", "tree-tournament")
R3_FIELDS = ("task", "actual", "claimed", "calls", "run_wall_s")


def slim_row(row: dict, fields: tuple[str, ...]) -> dict:
    return {k: row[k] for k in fields if k in row}


def slim_r2_row(row: dict) -> dict:
    out = slim_row(row, R2_FIELDS)
    iv = row.get("iv_verdicts")
    # `stage_signals` reads the list twice: truthiness, then `all(v.get("approved"))`.
    out["iv_verdicts"] = ([{"approved": bool(v.get("approved"))} for v in iv] if iv
                          else ([] if iv is not None else None))
    # Read only for truthiness.
    out["review_verdicts"] = bool(row.get("review_verdicts"))
    return out


def slim_nodes(node: object) -> dict | None:
    """The node tree reduced to what `walk()` is asked for: how_case counts and forced flags."""
    if not isinstance(node, dict):
        return None
    out: dict = {}
    cands = [({"how_case": c["how_case"]} if c.get("how_case") else {})
             for c in (node.get("candidates") or []) if isinstance(c, dict)]
    if cands:
        out["candidates"] = cands
    forced = (node.get("allocation") or {}).get("forced")
    if forced:
        out["allocation"] = {"forced": forced}
    kids = [k for k in (slim_nodes(c) for c in (node.get("children") or [])) if k is not None]
    if kids:
        out["children"] = kids
    return out


def slim_run_json(row: dict) -> dict:
    out = slim_row(row, R3_FIELDS)
    nodes = slim_nodes(row.get("nodes"))
    if nodes is not None:
        out["nodes"] = nodes
    return out


def write_jsonl(dst: Path, rows: list[dict]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def build(root: Path) -> list[tuple[str, int]]:
    """Write the projection under ``root``; return (relative path, row count) per file."""
    written: list[tuple[str, int]] = []
    for pat in R1_PATTERNS:
        for src in sorted(HOME.glob(pat)):
            rows = read_jsonl(src)
            dst = root / src.relative_to(HOME)
            write_jsonl(dst, [slim_row(r, R1_FIELDS) for r in rows])
            written.append((str(dst.relative_to(root)), len(rows)))
    for src in sorted(HOME.glob(R2_GLOB)):
        rows = read_jsonl(src)
        dst = root / src.relative_to(HOME)
        write_jsonl(dst, [slim_r2_row(r) for r in rows])
        written.append((str(dst.relative_to(root)), len(rows)))
    for arm in R3_ARMS:
        for src in sorted((HOME / "r3" / arm).glob("*/run.json")):
            row = json.loads(src.read_text(encoding="utf-8"))
            dst = root / src.relative_to(HOME)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(slim_run_json(row), sort_keys=True) + "\n", encoding="utf-8")
            written.append((str(dst.relative_to(root)), 1))
            # Presence marker only: `analyze.py` counts the file, never opens it. The 200 KB of
            # transcript per run is not read by any analyzer.
            if (src.parent / "trajectory.jsonl").is_file():
                (dst.parent / "trajectory.jsonl").write_bytes(b"")
                written.append((str((dst.parent / "trajectory.jsonl").relative_to(root)), 0))
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="rebuild into a temp directory and diff every file against the commit")
    args = ap.parse_args()
    if not HOME.is_dir():
        print(f"declared home absent: {HOME} (needs the 2 GB untracked home)", file=sys.stderr)
        return 1
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = build(Path(tmp))
            bad = 0
            for rel, _ in fresh:
                if not (PROJ / rel).is_file():
                    print(f"missing in projection: {rel}")
                    bad += 1
                elif not filecmp.cmp(Path(tmp) / rel, PROJ / rel, shallow=False):
                    print(f"differs from a fresh build: {rel}")
                    bad += 1
            known = {rel for rel, _ in fresh}
            for got in PROJ.rglob("*"):
                rel = str(got.relative_to(PROJ))
                if got.is_file() and rel not in known:
                    print(f"stale file in projection: {rel}")
                    bad += 1
            print(f"check: files={len(fresh)} mismatched={bad}")
            return 0 if bad == 0 else 1
    if PROJ.exists():
        shutil.rmtree(PROJ)
    written = build(PROJ)
    files = sum(1 for p in PROJ.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in PROJ.rglob("*") if p.is_file())
    print(f"wrote {len(written)} files ({files} on disk), {size} bytes, under {PROJ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
