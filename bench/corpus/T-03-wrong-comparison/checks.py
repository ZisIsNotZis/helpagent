#!/usr/bin/env python3
"""Deterministic checks for T-03-wrong-comparison. Python stdlib only.

Contract (see bench/corpus/README.md):
  (a) the task repo's pytest suite must pass (exit 0), and
  (b) the untouched-files contract: every path in UNTOUCHED must be byte-identical
      to its pre-run state (SHA-256 at snapshot time vs at verify time).

Usage:
  python checks.py snapshot              # BEFORE the run: hash UNTOUCHED -> baseline file
  python checks.py verify [--baseline F] # AFTER the run: pytest + byte-identity

Exit codes: 0 all green - 1 check failure - 2 setup/usage error (e.g. no baseline).
The baseline file (.untouched.baseline.json) is a runtime artifact, not corpus content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TASK_ID = "T-03-wrong-comparison"
TASK_DIR = Path(__file__).resolve().parent
REPO_DIR = TASK_DIR / "repo"
DEFAULT_BASELINE = TASK_DIR / ".untouched.baseline.json"

# Paths (relative to the task dir) that a correct run must not modify byte-for-byte.
# The one file the minimal fix touches (repo/billing/plans.py) is deliberately absent.
UNTOUCHED = [
    "repo/README.md",
    "repo/pyproject.toml",
    "repo/billing/__init__.py",
    "repo/tests/test_plans.py",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(baseline: Path) -> int:
    records: dict[str, str] = {}
    for rel in UNTOUCHED:
        path = TASK_DIR / rel
        if not path.is_file():
            print(f"snapshot: MISSING {rel}", file=sys.stderr)
            return 2
        records[rel] = sha256_file(path)
    baseline.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"snapshot: hashed {len(records)} untouched paths -> {baseline.name}")
    return 0


def run_pytest() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", **os.environ},  # owner finding: stale __pycache__ false-PASS
    )
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-8:])
    return proc.returncode == 0, tail


def verify(baseline: Path) -> int:
    if not baseline.is_file():
        print(
            f"verify: no baseline at {baseline.name}; run `python checks.py snapshot` first",
            file=sys.stderr,
        )
        return 2

    print(f"== checks: {TASK_ID} ==")
    failures = 0

    # (a) pytest gate
    tests_ok, tail = run_pytest()
    print(f"[tests]    {'OK' if tests_ok else 'FAIL'} (python -m pytest in repo/)")
    if not tests_ok:
        failures += 1
        for line in tail.splitlines():
            print(f"           {line}")

    # (b) untouched-files contract
    expected = json.loads(baseline.read_text(encoding="utf-8"))
    violations: list[str] = []
    for rel, want in expected.items():
        path = TASK_DIR / rel
        if not path.is_file():
            violations.append(f"{rel} MISSING (deleted or renamed)")
        else:
            got = sha256_file(path)
            if got != want:
                violations.append(f"{rel} MODIFIED (sha256 {want[:12]}.. -> {got[:12]}..)")
    for rel in UNTOUCHED:
        if rel not in expected:
            violations.append(f"{rel} NOT IN BASELINE (stale snapshot)")

    contract_ok = not violations
    print(f"[contract] {'OK' if contract_ok else 'FAIL'} ({len(expected)} untouched paths byte-identical)")
    for v in violations:
        print(f"           {v}")
    if not contract_ok:
        failures += 1

    print(f"result: {'PASS' if failures == 0 else 'FAIL'}")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"Deterministic checks for {TASK_ID}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="hash UNTOUCHED paths into the baseline file")
    snap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ver = sub.add_parser("verify", help="run pytest + compare against the baseline")
    ver.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    if args.cmd == "snapshot":
        return snapshot(args.baseline)
    return verify(args.baseline)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
