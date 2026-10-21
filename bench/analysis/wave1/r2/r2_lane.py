#!/usr/bin/env python3
"""R2 five-arm stage-ladder lane runner (measurement only; the repo is never modified).

Runs ONE arm over ONE task chunk by handing ``bench/v2_measure.py``'s OWN machinery
(:data:`ABLATIONS` / :class:`Ablation` / ``_run_arm`` / ``arm_summary`` / ``render_arm``)
the seam set for that arm. Every run therefore still goes through
``bench.v2_leaf.run_once`` -> ``harness.leaf.run_leaf`` -> the single ``claim_decision``
gate, exactly as ``bench/v2_measure.py --ablate`` does.

Why this driver exists (recorded, per the task's ``do NOT modify code`` fallback rule):
the cumulative ladder needs the ``verify=test`` arm (own test only, no independent test,
no review). At revision 45ebb32 ``bench/v2_measure.py``'s ``ABLATIONS`` table has no such
selector -- its ``own-test`` entry maps to ``verify=raw``, which turns off the self-test
AND the independent test AND the review AND the claim gate (``harness/leaf.py`` mode
table). The other four arms are reused verbatim from ``ABLATIONS`` by key; only the
missing ``verify=test`` arm is synthesised here.

Arms (derived from the code, not asserted):

  ================  =======  =====  ====  ======  ============================
  arm               verify   judge  iv    review  source
  ================  =======  =====  ====  ======  ============================
  dev-only          raw      off    off   off     ABLATIONS["own-test"]
  own-test-only     test     on     off   off     SYNTHESISED (no ABLATIONS key)
  own-iv            full     on     on    off     ABLATIONS["review"]
  own-review        full     on     off   on      ABLATIONS["independent-test"]
  full              full     on     on    on      ABLATIONS["none"]
  ================  =======  =====  ====  ======  ============================

Usage:
  uv run python /tmp/wave1/final/r2/r2_lane.py --arm full \
      --tasks T-01-ttl-seconds-ms,T-02-off-by-one --n 3 --out /tmp/wave1/final/r2/runs/c1/full
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/z/vibe/helpagent")
sys.path.insert(0, str(ROOT))

import bench.v2_measure as M  # noqa: E402

B = M.ABLATIONS


def _reused(key: str, name: str) -> M.Ablation:
    """Reuse one ``ABLATIONS`` entry verbatim, under a name that says what RUNS."""
    a = B[key]
    return M.Ablation(name=name, verify_mode=a.verify_mode, use_judge=a.use_judge,
                      use_iv=a.use_iv, use_review=a.use_review, disabled=a.disabled,
                      note=f"reused verbatim from bench.v2_measure.ABLATIONS[{key!r}]"
                           f" (disabled={'/'.join(a.disabled) or 'none'})")


#: own-test only (``--verify test``). No ``ABLATIONS`` entry at 45ebb32; see the module
#: docstring. ``run_once(mode='test')`` forces ``use_iv = use_review = False`` and leaves
#: the judge as passed (True), per ``bench/v2_leaf.py::run_once``.
OWN_TEST_ONLY = M.Ablation(
    name="own-test-only", verify_mode="test", use_judge=True, use_iv=False,
    use_review=False, disabled=M.VERIFY_MODE_STAGES["test"],
    note="SYNTHESISED: no ABLATIONS selector at 45ebb32; verify=test -> self-test loop "
         "only (independent test and review forced off, judge stays on)")

LADDER: dict[str, M.Ablation] = {
    "dev-only": _reused("own-test", "dev-only"),
    "own-test-only": OWN_TEST_ONLY,
    "own-iv": _reused("review", "own-iv"),
    "own-review": _reused("independent-test", "own-review"),
    "full": _reused("none", "full"),
}


def _head_sha() -> str:
    """The frozen revision this run root belongs to (bench/v2_measure.py records none)."""
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001 - a missing sha must not abort a measurement
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(LADDER))
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--server", default="http://127.0.0.1:8834")
    ap.add_argument("--calls", type=int, default=24)
    ap.add_argument("--deadline-hours", type=float, default=6.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    arm = LADDER[args.arm]
    tasks = M.discover_tasks(args.tasks)
    if not tasks:
        print(f"no tasks matched {args.tasks!r}", file=sys.stderr)
        return 2
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    (root / "arm.json").write_text(json.dumps({
        "arm": M._ablation_dict(arm),
        "tasks": [t.name for t in tasks],
        "n": args.n, "calls": args.calls, "deadline_hours": args.deadline_hours,
        "server": args.server, "repo_head": _head_sha(),
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=1, ensure_ascii=False))

    rows = M._run_arm(arm, tasks, args, root, args.n)
    summary = M.arm_summary(rows)
    summary["arm"] = M._ablation_dict(arm)
    (root / arm.name).mkdir(parents=True, exist_ok=True)
    (root / arm.name / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False))
    print(M.render_arm(arm, summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
