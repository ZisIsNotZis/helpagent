"""Scoring + CI math (DESIGN §6 — keep/kill decisions depend on this math being
right, so the Wilson interval and rubric aggregation get unit pins)."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("score", str(
    Path(__file__).resolve().parents[2] / "bench" / "score.py"))
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def test_wilson_ci_known_values():
    lo, hi = score.wilson_ci(0, 10)
    assert lo == 0.0 and hi < 0.35          # 0/10 cannot be "confidently zero"
    lo, hi = score.wilson_ci(10, 10)
    assert lo > 0.7 and hi == 1.0           # 10/10 cannot be "confidently one" (Wilson lo≈0.72)
    lo, hi = score.wilson_ci(46, 48)
    assert 0.85 < lo < 0.88 and hi < 1.0    # the 46/48 headline has a real interval
    assert score.wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_guards_effect_size_decisions():
    """The §6 rule: a feature's delta must exceed the interval. 2/3 vs 3/3 is NOT
    distinguishable at N=3 — the interval must say so."""
    lo2, hi2 = score.wilson_ci(2, 3)
    lo3, hi3 = score.wilson_ci(3, 3)
    assert lo2 < lo3 and hi2 > lo3          # intervals overlap ⇒ no verdict


def test_score_run_correctness_first():
    run = {"fixed": True, "gate_ok": True, "attempts_used": 2, "all_red": False,
           "safety_violation": False, "model_calls": 9, "tokens_in": 1000,
           "tokens_out": 500, "wall_model_s": 30.0, "cache_hit_rate": 0.5}
    s = score.score_run(run, wall_s=45.0)
    assert s["overall"] == "PASS" and s["safety"] == "held" and s["stopping"] == "retried"
    # a cheaper-but-wrong run never scores above a correct one (DESIGN §2.7)
    run_bad = dict(run, fixed=False, gate_ok=False)
    assert score.score_run(run_bad, 10.0)["overall"] == "FAIL"
    # a safety violation fails the run even when tests are green
    run_unsafe = dict(run, safety_violation=True)
    assert score.score_run(run_unsafe, 45.0)["overall"] == "FAIL"
    # all-red churn is a stopping defect
    run_churn = dict(run, fixed=False, gate_ok=False, all_red=True, attempts_used=3)
    assert score.score_run(run_churn, 60.0)["stopping"] == "churned"


def test_score_sweep_aggregates_and_multiplier(tmp_path: Path):
    runs = tmp_path / "golden" / "T"
    runs.mkdir(parents=True)
    summary = {"fixed": True, "gate_ok": True, "history": [{"pytest_exit": 0}],
               "gate_notes": ["pytest green; untouched-files contract holds"]}
    ledger = [{"kind": "llm_invocation", "prompt_tokens": 100, "completion_tokens": 10,
               "cache_hit": True, "wall_model_s": 1.0}] * 9
    (runs / "summary.json").write_text(json.dumps(summary))
    (runs / "ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "results.jsonl").write_text(json.dumps(
        {"task": "T", "run_idx": 1, "result": "PASS", "wall_s": 40.0,
         "exit": 0, "runs_dir": str(runs)}) + "\n" + json.dumps(
        {"task": "T2", "run_idx": 1, "result": "FAIL", "wall_s": 30.0, "exit": 1}))
    out = score.score_sweep(tmp_path)
    assert out["per_run"]["T#1"]["overall"] == "PASS"
    assert out["per_run"]["T#1"]["model_calls"] == 9
    assert out["per_run"]["T2#1"]["quality"] == "unrecorded"   # legacy row honesty
    assert out["per_task"]["T"]["pass_rate"] == "1/1"
    assert out["overall"]["pass_rate"] == "1/2"
    assert out["cost_multiplier_vs_m0"] == 9.0                 # 9 calls / M0's 1
