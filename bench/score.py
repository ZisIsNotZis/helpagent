#!/usr/bin/env python3
"""Scoring + cost metrics (DESIGN §6, milestone 5 — "feature gating possible,
honestly priced").

Rubric components per run (deterministic — no LLM judge, §6):
- quality:       PASS/FAIL via the gate (correctness first, DESIGN §2.7 — a
                 cheaper-but-wrong run never scores above a correct one).
- verification:  gate ran + attempts/rollbacks recorded (red→green evidence).
- safety:        untouched-files contract held (gate notes; conflicts recorded).
- stopping:      attempts_used vs cap; all-red churn is a stopping defect.
- cost:          model calls, prompt/completion tokens, wall_s, model-wall share,
                 cache-hit rate (llm_invocation counters, dual-lane per §1.6).

Aggregation per task over N runs: pass rate + Wilson 95% CI (the minimum
effect-size rule compares deltas against this interval — §6, §2.6). The
§9.10 multiplier: pipeline calls per PASS vs the M0 baseline (by construction
1 call/task unless M0 artifacts carry counters).

Usage: uv run python bench/score.py <sweep_dir>  → writes <sweep_dir>/scores.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: M0 baseline calls per task (run_m0.py constructs ONE llm() call per attempt;
#: no per-run counters persisted in the M0 era — documented, not assumed silent).
M0_BASELINE_CALLS_PER_TASK = 1.0


def wilson_ci(passes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — the §6 confidence interval for small N."""
    if total == 0:
        return (0.0, 0.0)
    p = passes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_run(run_dir: Path) -> dict:
    """Rubric components from one golden run dir (summary + ledger)."""
    summary = json.loads((run_dir / "summary.json").read_text())
    ledger = json.loads((run_dir / "ledger.json").read_text())
    calls = [e for e in ledger if e.get("kind") == "llm_invocation"]
    tokens_in = sum(e.get("prompt_tokens") or 0 for e in calls)
    tokens_out = sum(e.get("completion_tokens") or 0 for e in calls)
    wall_model = sum(e.get("wall_model_s") or 0.0 for e in calls)
    cache_hits = sum(1 for e in calls if e.get("cache_hit"))
    history = summary.get("history", [])
    attempts_used = len(history)
    all_red = bool(history) and all(a.get("pytest_exit", 1) != 0 for a in history)
    gate_notes = summary.get("gate_notes", [])
    safety_violation = any("untouched-files contract violated" in n for n in gate_notes)
    return {
        "fixed": bool(summary.get("fixed")),
        "gate_ok": bool(summary.get("gate_ok")),
        "attempts_used": attempts_used,
        "all_red": all_red,
        "safety_violation": safety_violation,
        "model_calls": len(calls),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "wall_model_s": round(wall_model, 1),
        "cache_hit_rate": round(cache_hits / len(calls), 3) if calls else None,
    }


def score_run(run: dict, wall_s: float | None) -> dict:
    """The §6 rubric over one run's components. Overall stays correctness-first:
    PASS requires gate_ok AND fixed AND no safety violation (§2.7)."""
    gate_green = run["gate_ok"] and run["fixed"] and not run["safety_violation"]
    return {
        "overall": "PASS" if gate_green else "FAIL",
        "quality": "green" if gate_green else "red",
        "verification": "ok" if run["attempts_used"] > 0 or gate_green else "none",
        "safety": "violation" if run["safety_violation"] else "held",
        "stopping": "churned" if run["all_red"] else ("clean" if run["attempts_used"] <= 1 else "retried"),
        "model_calls": run["model_calls"],
        "tokens": run["tokens_in"] + run["tokens_out"],
        "wall_s": round(wall_s, 1) if wall_s is not None else None,
        "wall_model_s": run["wall_model_s"],
        "cache_hit_rate": run["cache_hit_rate"],
    }


def score_sweep(sweep_dir: Path) -> dict:
    """Aggregate one n-sweep dir: per-run rubric rows + per-task pass rates with
    Wilson CIs + the §9.10 cost multiplier over PASSing runs."""
    results = [json.loads(l) for l in (sweep_dir / "results.jsonl").read_text().splitlines()]
    per_run: dict[str, dict] = {}
    per_task: dict[str, list[dict]] = {}
    for row in results:
        rd = row.get("runs_dir") or ""
        task = row["task"]
        if rd and (Path(rd) / "summary.json").exists():
            run = load_run(Path(rd))
            scored = score_run(run, row.get("wall_s"))
            scored["result"] = row["result"]
            scored["run_idx"] = row["run_idx"]
            per_run[f"{task}#{row['run_idx']}"] = scored
            per_task.setdefault(task, []).append(scored)
        else:
            # pre-M5 era rows: the gate verdict exists, per-component evidence
            # was not persisted — report the verdict, components honestly unknown
            per_run[f"{task}#{row['run_idx']}"] = {
                "overall": row.get("result", "CRASH"), "quality": "unrecorded",
                "verification": "unrecorded", "safety": "unrecorded",
                "stopping": "unrecorded", "model_calls": None, "tokens": None,
                "wall_s": row.get("wall_s"), "wall_model_s": None,
                "cache_hit_rate": None, "result": row.get("result", "CRASH"),
                "run_idx": row["run_idx"],
            }
            per_task.setdefault(task, []).append(per_run[f"{task}#{row['run_idx']}"])
    tasks: dict[str, dict] = {}
    passing_calls = [r["model_calls"] for rs in per_task.values() for r in rs
                     if r["overall"] == "PASS" and r["model_calls"]]
    for task, rs in sorted(per_task.items()):
        passes = sum(1 for r in rs if r["overall"] == "PASS")
        lo, hi = wilson_ci(passes, len(rs))
        tasks[task] = {
            "pass_rate": f"{passes}/{len(rs)}",
            "ci95": [round(lo, 3), round(hi, 3)],
            "mean_calls": round(sum(r["model_calls"] or 0 for r in rs) / len(rs), 1),
            "mean_tokens": round(sum(r["tokens"] or 0 for r in rs) / len(rs), 1),
            "mean_wall_s": round(sum(r["wall_s"] or 0 for r in rs) / len(rs), 1),
        }
    total = sum(len(rs) for rs in per_task.values())
    total_pass = sum(1 for rs in per_task.values() for r in rs if r["overall"] == "PASS")
    lo, hi = wilson_ci(total_pass, total)
    multiplier = None
    if passing_calls:
        mean_calls_pass = sum(passing_calls) / len(passing_calls)
        multiplier = round(mean_calls_pass / M0_BASELINE_CALLS_PER_TASK, 1)
    return {
        "per_run": per_run,
        "per_task": tasks,
        "overall": {"pass_rate": f"{total_pass}/{total}", "ci95": [round(lo, 3), round(hi, 3)]},
        "cost_multiplier_vs_m0": multiplier,
        "m0_baseline_calls_per_task": M0_BASELINE_CALLS_PER_TASK,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    sweep_dir = Path(sys.argv[1])
    out = score_sweep(sweep_dir)
    (sweep_dir / "scores.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out["overall"], ensure_ascii=False))
    print("multiplier vs M0 (calls/PASS):", out["cost_multiplier_vs_m0"])
    for task, s in out["per_task"].items():
        print(f"  {task:34s} {s['pass_rate']:6s} ci95={s['ci95']} "
              f"calls={s['mean_calls']:5.1f} tokens={s['mean_tokens']:8.1f} wall={s['mean_wall_s']:6.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
