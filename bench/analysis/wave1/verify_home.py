#!/usr/bin/env python3
"""Verify the declared home of the wave-1 campaign bytes against its committed manifest.

The campaign's decisive numbers are computed from run records that `git` cannot hold: 53 270
files, 1 996 009 173 bytes. They live at `bench/runs/wave1/` (gitignored, declared, stated
owner in `.gitignore` and in `AGENTS.md`) and are pinned by `bench/manifests/wave1.sha256`, one
line per file, paths relative to that home.

This script re-hashes every file and reports three counts, so a partial or drifted home cannot
pass as a whole one:

  ok        files whose bytes equal their manifest entry
  mismatch  files whose bytes differ from their manifest entry
  missing   manifest entries with no file on disk

It also checks that the tracked copies under `bench/analysis/wave1/` are byte-identical to the
home's originals, because those copies have a git home and the original does not.

Read-only. No network, no model, no repo import. Exit 0 only when mismatch and missing are both
zero and the analysis copies all match.

    python3 bench/analysis/wave1/verify_home.py [--quiet]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2]
HOME = BENCH / "runs" / "wave1"
MANIFEST = BENCH / "manifests" / "wave1.sha256"
ANALYSIS = BENCH / "analysis" / "wave1"

# tracked copy -> path inside the home that it must equal
ANALYSIS_PAIRS = {
    "final/analyze.py": "final/analyze.py",
    "final/run_our_arm.sh": "final/run_our_arm.sh",
    "final/tables.txt": "final/tables.txt",
    "final/analysis-vs-reference.txt": "final/analysis-vs-reference.txt",
    "final/our_lanes.txt": "final/our_lanes.txt",
    "final/pi_lanes.txt": "final/pi_lanes.txt",
    "final/pi_probe_lanes.txt": "final/pi_probe_lanes.txt",
    "n25/analyze_n25.py": "final/n25/analyze_n25.py",
    "n25/assemble.py": "final/n25/assemble.py",
    "n25/render_tables.py": "final/n25/render_tables.py",
    "n25/run_n25.sh": "final/n25/run_n25.sh",
    "n25/run_n25_seg.sh": "final/n25/run_n25_seg.sh",
    "n25/run_wallclock.sh": "final/n25/run_wallclock.sh",
    "n25/poll_n25.sh": "final/n25/poll_n25.sh",
    "n25/final-summary.txt": "final/n25/final-summary.txt",
    "n25/tables-n25.md": "final/n25/tables-n25.md",
    "n25/analysis-n25-final.json": "final/n25/analysis-n25-final.json",
    "r2/r2_analyze.py": "final/r2/r2_analyze.py",
    "r2/r2_lane.py": "final/r2/r2_lane.py",
    "r2/r2_resume.py": "final/r2/r2_resume.py",
    "r2/poll.py": "final/r2/poll.py",
    "r2/job.sh": "final/r2/job.sh",
    "r2/job_resume.sh": "final/r2/job_resume.sh",
    "r2/run_queue.sh": "final/r2/run_queue.sh",
    "r2/resume_queue.sh": "final/r2/resume_queue.sh",
    "r2/autopoll.sh": "final/r2/autopoll.sh",
    "r2/analysis.json": "final/r2/analysis.json",
    "r2/analysis.txt": "final/r2/analysis.txt",
    "r2/queue.txt": "final/r2/queue.txt",
    "r2/resume_queue.txt": "final/r2/resume_queue.txt",
    "r3/analyze.py": "final/r3/analyze.py",
    "r3/supp.py": "final/r3/supp.py",
    "r3/lane.sh": "final/r3/lane.sh",
    "r3/analysis-r3.txt": "final/r3/analysis-r3.txt",
    "r3/supp-r3.txt": "final/r3/supp-r3.txt",
    "r3/jobs.txt": "final/r3/jobs.txt",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    for raw in text.split("\n"):
        if not raw:
            continue
        escaped = raw.startswith("\\")
        if escaped:
            raw = raw[1:]
        sha, sep, name = raw.partition("  ")
        if not sep:
            continue
        if escaped:  # coreutils escapes \n and \\ in the name field only
            name = name.replace("\\n", "\n").replace("\\\\", "\\")
        entries[name] = sha
    return entries


def main() -> int:
    quiet = "--quiet" in sys.argv[1:]
    if not MANIFEST.is_file():
        print(f"manifest absent: {MANIFEST}", file=sys.stderr)
        return 2
    if not HOME.is_dir():
        print(f"declared home absent: {HOME}", file=sys.stderr)
        print("the campaign bytes are not on this machine; nothing can be verified", file=sys.stderr)
        return 1

    entries = read_manifest(MANIFEST)
    ok = mismatch = missing = 0
    bad: list[str] = []
    for name, want in entries.items():
        p = HOME / name
        if not p.is_file():
            missing += 1
            bad.append(f"missing  {name}")
        elif digest(p) == want:
            ok += 1
        else:
            mismatch += 1
            bad.append(f"mismatch {name}")

    on_disk = sum(1 for p in HOME.rglob("*") if p.is_file())
    unlisted = on_disk - ok - mismatch

    copy_ok = copy_bad = 0
    copy_failures: list[str] = []
    for local, home_rel in sorted(ANALYSIS_PAIRS.items()):
        src = ANALYSIS / local
        want = entries.get(home_rel)
        if not src.is_file():
            copy_failures.append(f"absent   analysis/{local}")
            copy_bad += 1
        elif want is None:
            copy_failures.append(f"unpinned analysis/{local} (no manifest entry for {home_rel})")
            copy_bad += 1
        elif digest(src) != want:
            copy_failures.append(f"differs  analysis/{local} != {home_rel}")
            copy_bad += 1
        else:
            copy_ok += 1

    if not quiet:
        print(f"home      {HOME}")
        print(f"manifest  {MANIFEST}  ({len(entries)} entries)")
        print(f"files on disk {on_disk}   manifest entries {len(entries)}   unlisted on disk {unlisted}")
        for line in bad[:20]:
            print("  " + line)
        for line in copy_failures[:20]:
            print("  " + line)
    print(f"ok {ok}  mismatch {mismatch}  missing {missing}  analysis-copies-ok {copy_ok}  analysis-copies-bad {copy_bad}")
    return 0 if (mismatch == 0 and missing == 0 and copy_bad == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
