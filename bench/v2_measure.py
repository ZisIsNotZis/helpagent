#!/usr/bin/env python3
"""Measurement driver: multi-seed arms with variance, stage ablations, single-lane
wall-clock + token accounting, and a head-to-head table against the pi reference.

This module adds MEASUREMENT only. It never re-implements a claim: every run goes
through :func:`bench.v2_leaf.run_once`, which routes the one grant through
:func:`harness.leaf.claim_decision`. The driver's whole job is to call it, read the
already-persisted evidence, and aggregate.

Three things it measures, all on the same task subset:

1. **Multi-seed repeats.** ``--n`` (>=3 for a real spread) repeats each task; the arm
   is reported as a mean plus spread for actual / claimed / false-success, seconds/task
   and tokens/task. There is no RNG seed to pin: each repeat is an independent stochastic
   sample of the served model (temperature 0.2), which is exactly the variance we want.
2. **Stage ablation.** ``--ablate NAME`` runs the arm with a named verification stage
   disabled (see :data:`ABLATIONS`; the exact disabled set is printed and recorded).
3. **Single-lane wall clock.** ``--wall-clock`` runs ONE sequential pass per task
   (n=1, no concurrency anywhere in this driver) and reports seconds/task and
   tokens/task — the honest per-lane cost, not a fan-out number.

The merged output prints our arm(s) beside the pi reference
(``bench/runs/evidence/pi-maxed-20261006``) on the same tasks, so parity can be read
without leaving the tool.

Verification-mode stage table (which ``--verify`` values disable what; the modes live in
:data:`harness.leaf.VERIFICATION_MODES`):

  ==========  =========  =================  ========
  --verify    own-test   independent-test   review
  ==========  =========  =================  ========
  full        on         on                 on
  test        on         OFF                OFF
  review      OFF        OFF                on
  raw         OFF        OFF                OFF
  ==========  =========  =================  ========

Usage:
  uv run python bench/v2_measure.py --tasks T-01-ttl-seconds-ms,T-02-off-by-one --n 3
  uv run python bench/v2_measure.py --tasks T-01-ttl-seconds-ms --ablate review
  uv run python bench/v2_measure.py --tasks T-01-ttl-seconds-ms --wall-clock
  uv run python bench/v2_measure.py --tasks all --ablate none,independent-test,review --n 3
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.v2_leaf import DEFAULT_SERVER, run_once  # noqa: E402
from harness.leaf import VERIFICATION_MODES  # noqa: E402

CORPUS = ROOT / "bench" / "corpus"
ANCHOR = ROOT / "bench" / "anchor"
PI_REFERENCE_DEFAULT = ROOT / "bench" / "runs" / "evidence" / "pi-maxed-20261006"

#: The pi evidence bands, in the order the reference README measures them. A task measured
#: in two bands (A-01) keeps the LATER row, matching ``tests/unit/test_pi_maxed_evidence``.
PI_BANDS: tuple[str, ...] = ("easy", "mid1", "mid2", "tail", "anchors")


@dataclass(frozen=True)
class Ablation:
    """One arm: the seams it feeds :func:`run_once` plus the stages it switches OFF.

    ``disabled`` is the human-readable truth of the arm, derived from the leaf's own
    mode table rather than asserted here; it is printed and written into the record so a
    reader never has to infer what "ablate review" meant.
    """

    name: str
    verify_mode: str
    use_judge: bool
    use_iv: bool
    use_review: bool
    disabled: tuple[str, ...]
    note: str = ""


#: The ablation switch. Each name turns off the named stage while leaving the rest of the
#: full pipeline intact — EXCEPT ``own-test``: the leaf derives its self-test loop from
#: ``verification_mode`` (``run_self_test = mode in ("full", "test")``), so the only
#: selector that skips the own test is ``raw``, which also drops the independent test, the
#: review and the claim gate. That coupling is documented here rather than hidden.
ABLATIONS: dict[str, Ablation] = {
    "none": Ablation("none", "full", True, True, True, ()),
    "independent-test": Ablation("independent-test", "full", True, False, True,
                                 ("independent-test",)),
    "review": Ablation("review", "full", True, True, False, ("review",)),
    "own-test": Ablation("own-test", "raw", False, False, False,
                         ("own-test", "independent-test", "review"),
                         note=("raw is the only leaf selector that skips the self-test; it "
                               "also disables the independent test, the review and the claim "
                               "gate (harness/leaf.py mode table). --verify review is the "
                               "nearest alternative (own-test and independent-test off, the "
                               "graded-review loop still runs)")),
}

#: What each ``--verify`` value disables, quoted from the leaf's mode table. Kept next to
#: the ablation switch so the two never drift in the usage note.
VERIFY_MODE_STAGES: dict[str, tuple[str, ...]] = {
    "full": (),
    "test": ("independent-test", "review"),
    "review": ("own-test", "independent-test"),
    "raw": ("own-test", "independent-test", "review"),
}


# ---------------------------------------------------------------------------
# aggregation / variance math (the part the unit tests pin)
# ---------------------------------------------------------------------------

def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; 0.0 for an empty sequence (an arm that ran nothing is not NaN)."""
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (ddof=1); 0.0 for fewer than two samples.

    Sample (not population) is the honest spread of an observed arm, and the n<2 guard
    keeps a single-seed arm from producing a fake error bar.
    """
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def rate_summary(flags: Sequence[bool]) -> dict[str, float | int]:
    """Counts, rate and sample spread of a boolean per-run metric."""
    values = [1.0 if bool(f) else 0.0 for f in flags]
    return {"n": len(values), "true": int(sum(values)), "rate": mean(values),
            "sd": stdev(values)}


def per_task_means(rows: Sequence[dict], field: str) -> dict[str, float]:
    """Mean of ``field`` over the seeds of each task (the per-task arm number)."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(str(row["task"]), []).append(float(row[field]))
    return {task: mean(vals) for task, vals in grouped.items()}


def spread(values: Sequence[float]) -> dict[str, float]:
    """Mean / sample-sd / min / max of a series (the cost columns' error bar)."""
    return {"n": len(values), "mean": mean(values), "sd": stdev(values),
            "min": min(values) if values else 0.0, "max": max(values) if values else 0.0}


def arm_summary(rows: Sequence[dict]) -> dict[str, Any]:
    """Per-arm mean and spread for actual / claimed / false-success, plus cost/task.

    ``rate`` is the fraction of RUNS that passed; ``task_rate_sd`` is the spread of the
    per-task rates across the task subset (the corpus-level error bar), and ``per_task``
    holds each task's own rate so a single lucky task cannot hide inside the mean.
    """
    tasks = sorted({str(r["task"]) for r in rows})
    out: dict[str, Any] = {"n_runs": len(rows), "n_tasks": len(tasks), "tasks": tasks}
    for name in ("actual", "claimed", "false_success"):
        base = rate_summary([bool(r[name]) for r in rows])
        task_rates = list(per_task_means(rows, name).values())
        base["task_rate_sd"] = stdev(task_rates)
        base["per_task"] = per_task_means(rows, name)
        out[name] = base
    out["wall_s_per_task"] = spread(list(per_task_means(rows, "run_wall_s").values()))
    out["tokens_per_task"] = spread(list(per_task_means(rows, "total_tokens").values()))
    return out


# ---------------------------------------------------------------------------
# evidence readers
# ---------------------------------------------------------------------------

def read_token_usage(trajectory: Path) -> dict[str, int]:
    """Sum the llama.cpp token counters over every ``model_call`` in a trajectory.

    Tokens are read from the persisted trajectory (``metrics.prompt_tokens`` /
    ``metrics.completion_tokens`` on each ``model_call``), not recomputed from the
    prompts: the server's own usage counters are the honest cost. ``prompt_tokens``
    includes the cached prefix the server still counted for the request.
    """
    prompt = completion = calls = 0
    if trajectory.is_file():
        for line in trajectory.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn tail line is not a run failure
            if event.get("kind") != "model_call":
                continue
            metrics = event.get("metrics") or {}
            prompt += int(metrics.get("prompt_tokens") or 0)
            completion += int(metrics.get("completion_tokens") or 0)
            calls += 1
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion, "model_calls": calls}


def load_pi_reference(root: Path) -> dict[str, dict]:
    """pi reference rows keyed by task id; a task in two bands keeps the later row."""
    by_task: dict[str, dict] = {}
    for band in PI_BANDS:
        path = root / band / "results.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                by_task[str(row["task"])] = row
    return by_task


def discover_tasks(tasks_arg: str) -> list[Path]:
    """Corpus + anchor task dirs, filtered by the exact ``--tasks`` names (or ``all``)."""
    tasks = [p for root in (CORPUS, ANCHOR) for p in sorted(root.iterdir())
             if p.is_dir() and p.name[:2] in ("T-", "A-")]
    if tasks_arg != "all":
        want = set(tasks_arg.split(","))
        tasks = [t for t in tasks if t.name in want]
    return tasks


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _pct(rate: float) -> str:
    return f"{rate * 100:5.1f}%"


def render_arm(arm: Ablation, summary: dict[str, Any]) -> str:
    """One arm's block: the stage switch, then mean/spread per metric."""
    disabled = ",".join(arm.disabled) or "none"
    lines = [
        f"arm={arm.name}  verify={arm.verify_mode}  "
        f"judge={'on' if arm.use_judge else 'off'} "
        f"iv={'on' if arm.use_iv else 'off'} "
        f"review={'on' if arm.use_review else 'off'}  disabled=[{disabled}]",
        f"  runs={summary['n_runs']} tasks={summary['n_tasks']}",
    ]
    for name, label in (("actual", "actual "), ("claimed", "claimed"),
                        ("false_success", "false-success")):
        stat = summary[name]
        lines.append(
            f"  {label:<14} {stat['true']}/{stat['n']} ({_pct(stat['rate'])}) "
            f"sd={stat['sd']:.3f} task_rate_sd={stat['task_rate_sd']:.3f}")
    for key, label in (("wall_s_per_task", "seconds/task "),
                       ("tokens_per_task", "tokens/task  ")):
        stat = summary[key]
        lines.append(
            f"  {label} mean={stat['mean']:.1f} sd={stat['sd']:.1f} "
            f"[{stat['min']:.1f}..{stat['max']:.1f}]")
    return "\n".join(lines)


def render_merged(arms: dict[str, Sequence[dict]], pi: dict[str, dict],
                  tasks: Sequence[str]) -> str:
    """Our arm(s) and the pi reference side by side, one row per task.

    Our cells show ``actual/claimed`` counts over the seeds; the pi cell shows its single
    recorded ``actual/claimed`` plus wall seconds. Tasks without a pi row are marked
    ``n/a`` (never silently compared to zero).
    """
    header = ["task"]
    for name in arms:
        header += [f"{name}:act", f"{name}:claim", f"{name}:s"]
    header += ["pi:act", "pi:claim", "pi:s"]
    rows = [" | ".join(header), "-" * 20]
    for task in tasks:
        cells = [task]
        for rows_for_arm in arms.values():
            mine = [r for r in rows_for_arm if str(r["task"]) == task]
            if not mine:
                cells += ["-", "-", "-"]
                continue
            act = sum(1 for r in mine if r["actual"])
            claim = sum(1 for r in mine if r["claimed"])
            wall = mean([float(r["run_wall_s"]) for r in mine])
            cells += [f"{act}/{len(mine)}", f"{claim}/{len(mine)}", f"{wall:.0f}"]
        ref = pi.get(task)
        if ref is None:
            cells += ["n/a", "n/a", "n/a"]
        else:
            cells += ["1/1" if ref["actual"] else "0/1",
                      "1/1" if ref["claimed"] else "0/1",
                      f"{float(ref.get('wall_s') or 0):.0f}"]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--n", type=int, default=None,
                    help="seeds (repeats) per task; default 3, or 1 in --wall-clock mode")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--calls", type=int, default=24)
    ap.add_argument("--deadline-hours", type=float, default=6.0)
    ap.add_argument("--ablate", default="none",
                    help="comma-separated arm(s): " + ",".join(ABLATIONS))
    ap.add_argument("--wall-clock", action="store_true",
                    help="ONE sequential lane: n=1 per task, report seconds/task and "
                         "tokens/task (no concurrency anywhere in this driver)")
    ap.add_argument("--pi-reference", default=str(PI_REFERENCE_DEFAULT))
    ap.add_argument("--out", default="",
                    help="output root (default bench/runs/measure-<utc timestamp>)")
    return ap


def _resolve_arm(name: str) -> Ablation:
    if name not in ABLATIONS:
        raise SystemExit(f"unknown --ablate value {name!r}; choose from "
                         f"{','.join(ABLATIONS)}")
    return ABLATIONS[name]


def _run_arm(arm: Ablation, tasks: list[Path], args: argparse.Namespace,
             root: Path, n: int) -> list[dict]:
    """Sequentially run every (task, seed) of one arm; never raises on a task crash."""
    results = root / arm.name / "results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for task in tasks:
        for idx in range(1, n + 1):
            out_dir = root / arm.name / f"{task.name}-{idx}"
            t0 = time.monotonic()
            try:
                record = run_once(task, out_dir, args.server, args.calls,
                                  args.deadline_hours, use_judge=arm.use_judge,
                                  use_iv=arm.use_iv, use_review=arm.use_review,
                                  verify_mode=arm.verify_mode)
            except Exception as exc:  # noqa: BLE001 - keep the measurement recoverable
                record = {"task": task.name, "claimed": False, "actual": False,
                          "quadrant": "honest-failure", "signal": "crashed",
                          "stop_reason": f"crash:{type(exc).__name__}",
                          "grader_notes": [str(exc)[:200]], "calls": 0,
                          "run_wall_s": round(time.monotonic() - t0, 1)}
                (out_dir / "crash.txt").write_text(str(exc))
            record["run_idx"] = idx
            record["arm"] = arm.name
            # The measured cost fields (not part of the leaf record): the whole-run wall
            # time, the server's token counters, and the derived false-success flag.
            record["run_wall_s"] = round(float(record.get("run_wall_s") or 0.0), 1)
            record.update(read_token_usage(out_dir / "trajectory.jsonl"))
            record["false_success"] = bool(record["claimed"]) and not bool(record["actual"])
            rows.append(record)
            with results.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[{arm.name}] {task.name} #{idx}: claimed={record['claimed']} "
                  f"actual={record['actual']} -> {record['quadrant']} "
                  f"({record.get('calls')} calls, {record['run_wall_s']}s, "
                  f"{record['total_tokens']} tokens, stop={record.get('stop_reason')})",
                  flush=True)
    return rows


def main() -> int:
    args = build_parser().parse_args()
    arm_names = [a.strip() for a in args.ablate.split(",") if a.strip()]
    arms = [_resolve_arm(name) for name in arm_names]
    n = args.n if args.n is not None else (1 if args.wall_clock else 3)
    if args.wall_clock and args.n is not None and args.n != 1:
        print(f"[measure] --wall-clock is one lane; using the requested n={args.n} repeats "
              f"(still sequential)", file=sys.stderr)
    if n < 1:
        raise SystemExit("--n must be >= 1")

    tasks = discover_tasks(args.tasks)
    if not tasks:
        print("no tasks matched", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(args.out) if args.out else ROOT / "bench" / "runs" / f"measure-{ts}"
    root.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    rows_by_arm: dict[str, list[dict]] = {}
    summaries: dict[str, dict] = {}
    for arm in arms:
        print(f"== arm {arm.name}: verify={arm.verify_mode} "
              f"disabled=[{','.join(arm.disabled) or 'none'}] n={n} "
              f"tasks={len(tasks)} ==", flush=True)
        rows = _run_arm(arm, tasks, args, root, n)
        rows_by_arm[arm.name] = rows
        summary = arm_summary(rows)
        summary["arm"] = _ablation_dict(arm)
        summaries[arm.name] = summary
        (root / arm.name).mkdir(parents=True, exist_ok=True)
        (root / arm.name / "summary.json").write_text(
            json.dumps(summary, indent=1, ensure_ascii=False))

    # ---- pi reference, same tasks -------------------------------------------------
    pi = load_pi_reference(Path(args.pi_reference))
    task_names = [t.name for t in tasks]
    merged = {
        "tasks": task_names,
        "pi_reference": args.pi_reference,
        "arms": {name: [{"task": r["task"], "run_idx": r["run_idx"],
                         "claimed": bool(r["claimed"]), "actual": bool(r["actual"]),
                         "false_success": bool(r["false_success"]),
                         "run_wall_s": r["run_wall_s"], "total_tokens": r["total_tokens"]}
                        for r in rows] for name, rows in rows_by_arm.items()},
        "pi": {t: pi.get(t) for t in task_names},
    }
    (root / "summary.json").write_text(json.dumps(
        {"n": n, "wall_clock": bool(args.wall_clock), "tasks": task_names,
         "arms": summaries,
         "lane_wall_s": round(time.monotonic() - started, 1)}, indent=1,
        ensure_ascii=False))
    (root / "merged.json").write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    (root / "merged.md").write_text(render_merged(rows_by_arm, pi, task_names) + "\n")

    print()
    for arm in arms:
        print(render_arm(arm, summaries[arm.name]))
        print()
    print(f"== merged: our arm(s) vs pi reference ({args.pi_reference}) ==")
    print(render_merged(rows_by_arm, pi, task_names))
    print()
    print(f"[measure] n={n} wall_clock={bool(args.wall_clock)} "
          f"lane_wall_s={round(time.monotonic() - started, 1)} out={root}")
    return 0


def _ablation_dict(arm: Ablation) -> dict[str, Any]:
    return {"name": arm.name, "verify_mode": arm.verify_mode, "use_judge": arm.use_judge,
            "use_iv": arm.use_iv, "use_review": arm.use_review,
            "disabled": list(arm.disabled), "note": arm.note}


if __name__ == "__main__":
    raise SystemExit(main())
