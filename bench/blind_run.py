#!/usr/bin/env python3
"""Blind sweep: what the run CLAIMED vs what the grader FOUND.

Owner direction 2026-09-29. The corpus tests never enter the run; after each run
the produced files are applied to a pristine task copy and scored by the task's
own ``checks.py``. The pair of facts (claim, verdict) is the honest measurement:

    claimed  actual  quadrant
    PASS     PASS    true success
    PASS     FAIL    FALSE SUCCESS  <- the number this harness must never grow
    FAIL     PASS    missed success
    FAIL     FAIL    honest failure

Usage:
  uv run python bench/blind_run.py --tasks T-02-off-by-one,T-31-parameter-threading --n 1
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.external_score import external_score  # noqa: E402
from harness.staging import is_test_path  # noqa: E402

CORPUS = ROOT / "bench" / "corpus"
ANCHOR = ROOT / "bench" / "anchor"


#: Directory names a run's own test tooling leaves behind: pytest's tmp_path retention
#: (``pytest-of-<user>/pytest-<n>/...``) and similar. They are NOT deliverables, and
#: handing them to the grader muddies the record (found 2026-10-03: a pi run left 12
#: ``pytest-of-z/...`` artifacts that were applied to the pristine copy; the verdict was
#: unchanged, but the contract "the run's produced files" must mean the run's work).
_TEMP_JUNK_PREFIXES = ("pytest-of-", "pytest-", ".pytest-")


def produced_files(workdir: Path) -> dict[str, str]:
    """Everything the run left behind, as the delivered repository."""
    out: dict[str, str] = {}
    for path in sorted(workdir.rglob("*")):
        rel_parts = path.relative_to(workdir).parts
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
            continue   # harness infrastructure (.git, .pytest_cache), not a deliverable
        if any(part.startswith(_TEMP_JUNK_PREFIXES) for part in rel_parts):
            continue   # pytest tmp_path retention, not a deliverable
        try:
            out[str(path.relative_to(workdir))] = path.read_text()
        # A file the run itself produced may be unreadable (e.g. a chmod-000 file a
        # test deliberately creates). Skipping it must not abort the whole
        # measurement, and the file is not a deliverable we can score anyway.
        except (UnicodeDecodeError, OSError):
            continue
    return out


def restore_deviations(produced: dict[str, str], deviations) -> tuple[dict[str, str], list[str]]:
    """Put every recorded write DEVIATION back before grading (FLOW §6, P1a).

    A deviation (a write outside the run's declared plan — a grader-owned/frozen/test
    path, a module-shadow path, or a path outside the write boundary) LANDED during the
    run, but the grader must see the same bytes it saw when such writes were refused. For
    each deviation the produced repository is restored to the snapshotted pre-run content
    (or the invented file is dropped), and the restore is recorded.

    ``deviations`` items are :class:`harness.leaf.WriteDeviation` (an object with ``path``,
    ``reason``, ``original``) or an equivalent mapping/model dump. Returns
    ``(produced, restores)``; the input dict is not mutated.
    """
    out = dict(produced)
    restores: list[str] = []
    seen: set[str] = set()
    for entry in deviations:
        if isinstance(entry, dict):
            path = entry.get("path", "")
            reason = entry.get("reason", "")
            original = entry.get("original")
        else:
            path = getattr(entry, "path", "")
            reason = getattr(entry, "reason", "")
            original = getattr(entry, "original", None)
        if not path or path in seen:
            continue
        seen.add(path)
        if original is None:
            if path in out:
                del out[path]
                restores.append(f"{path}: removed (a recorded write deviation: {reason})")
            else:
                restores.append(f"{path}: left absent (a recorded write deviation: {reason})")
        else:
            out[path] = original
            restores.append(
                f"{path}: restored from the recorded pre-run bytes (write deviation: "
                f"{reason})")
    return out, restores


def quadrant(claimed: bool, actual: bool) -> str:
    if claimed and actual:
        return "true-success"
    if claimed and not actual:
        return "false-success"
    if not claimed and actual:
        return "missed-success"
    return "honest-failure"


def verified_quadrant(claimed: bool, actual: bool, verified: bool) -> str:
    """The four-way separation the verification covenant requires (ticket 20).

    A claim whose evidence tier is ``none+reason`` is UNVERIFIED and must never be mixed
    into verified claims: ``verified`` is True only for a ``test``/``review`` tier. The
    scoring layer reads this separately so a verified success, an unverified success, a
    verified failure, and an unverified failure are distinguishable.
    """
    strength = "verified" if verified else "unverified"
    return f"{strength}-{'success' if actual else 'failure'}"


def run_once(task: Path, out_dir: Path, run_idx: int, server: str) -> dict:
    cmd = [sys.executable, str(ROOT / "bench" / "golden_bugfix.py"),
           "--task", str(task), "--blind", "--server", server]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    wall = round(time.monotonic() - t0, 1)
    (out_dir / f"{task.name}.run{run_idx}.log").write_text(
        proc.stdout + "\n===== STDERR =====\n" + proc.stderr)

    match = re.search(r"\[result\] (PASS|FAIL)", proc.stdout)
    claimed = match is not None and match.group(1) == "PASS"
    persist = re.search(r"\[persist\] (\S+)", proc.stdout)
    workdir = Path(persist.group(1)) / "work" if persist else None

    if workdir is None or not workdir.exists():
        return {"task": task.name, "run_idx": run_idx, "claimed": claimed, "actual": False,
                "quadrant": quadrant(claimed, False), "wall_s": wall,
                "grader_exit": None, "notes": ["no workdir persisted"],
                "produced": [], "self_tests": []}

    produced = produced_files(workdir)
    score = external_score(task, produced, out_dir / f"grade-{task.name}-{run_idx}")
    return {
        "task": task.name, "run_idx": run_idx,
        "claimed": claimed, "actual": score.passed,
        "quadrant": quadrant(claimed, score.passed),
        "wall_s": wall, "grader_exit": score.exit, "notes": score.notes[-3:],
        "produced": sorted(produced),
        "self_tests": sorted(rel for rel in produced if is_test_path(rel)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--server", default="http://127.0.0.1:8833")
    ap.add_argument("--corpus", default=str(CORPUS))
    args = ap.parse_args()

    roots = [Path(args.corpus)]
    if Path(args.corpus) == CORPUS:
        roots.append(ANCHOR)
    tasks = [p for r in roots if r.exists()
             for p in sorted(r.iterdir()) if p.is_dir() and p.name[:2] in ("T-", "A-")]
    if args.tasks != "all":
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.name in want]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "bench" / "runs" / f"blind-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results.jsonl"

    for task in tasks:
        for run_idx in range(1, args.n + 1):
            rec = run_once(task, out_dir, run_idx, args.server)
            with results.open("a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[blind] {rec['task']} #{run_idx}: claimed={rec['claimed']} "
                  f"actual={rec['actual']} -> {rec['quadrant']} ({rec['wall_s']}s)", flush=True)

    rows = [json.loads(line) for line in results.read_text().splitlines()]
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["quadrant"]] = tally.get(row["quadrant"], 0) + 1
    summary = {"per_task": {r["task"]: f"{r['actual']}" for r in rows},
               "quadrants": tally,
               "actual_pass_rate": f"{sum(r['actual'] for r in rows)}/{len(rows)}",
               "false_success_rate": f"{tally.get('false-success', 0)}/{len(rows)}"}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
