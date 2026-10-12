"""Measurement driver math + wiring (bench/v2_measure.py).

Pins the aggregation/variance math (mean, sample sd, rate summaries, per-task rates and
arm summaries) with hand-computed values, the ablation switch's exact stage mapping, the
token reader, the pi-reference merge, and the CLI forwarding of seeds + ablation seams.
No live server is touched: ``run_once`` is monkeypatched, exactly as the v2_sweep tests do.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from bench import v2_measure
from harness.leaf import VERIFICATION_MODES


# ---------------------------------------------------------------------------
# aggregation / variance math
# ---------------------------------------------------------------------------

def test_mean_handles_empty_and_average():
    assert v2_measure.mean([]) == 0.0
    assert v2_measure.mean([1.0, 2.0, 3.0]) == 2.0


def test_stdev_is_the_sample_spread_and_guards_one_sample():
    assert v2_measure.stdev([]) == 0.0
    assert v2_measure.stdev([5.0]) == 0.0
    assert v2_measure.stdev([1.0, 3.0]) == pytest.approx(math.sqrt(2.0))
    # sample sd of [1,1,0,0] is sqrt(1/3)
    assert v2_measure.stdev([1.0, 1.0, 0.0, 0.0]) == pytest.approx(math.sqrt(1 / 3))


def test_rate_summary_counts_and_spread():
    stat = v2_measure.rate_summary([True, True, False, False])
    assert stat["n"] == 4 and stat["true"] == 2 and stat["rate"] == 0.5
    assert stat["sd"] == pytest.approx(math.sqrt(1 / 3))
    empty = v2_measure.rate_summary([])
    assert empty == {"n": 0, "true": 0, "rate": 0.0, "sd": 0.0}


def test_per_task_means_averages_the_seeds_per_task():
    rows = [{"task": "A", "x": 10.0}, {"task": "A", "x": 20.0},
            {"task": "B", "x": 30.0}]
    assert v2_measure.per_task_means(rows, "x") == {"A": 15.0, "B": 30.0}


def test_arm_summary_reports_rate_and_task_spread_with_hand_computed_values():
    rows = [
        {"task": "A", "actual": True, "claimed": True, "false_success": False,
         "run_wall_s": 10.0, "total_tokens": 100.0},
        {"task": "A", "actual": False, "claimed": True, "false_success": True,
         "run_wall_s": 20.0, "total_tokens": 200.0},
        {"task": "B", "actual": True, "claimed": True, "false_success": False,
         "run_wall_s": 30.0, "total_tokens": 300.0},
        {"task": "B", "actual": True, "claimed": True, "false_success": False,
         "run_wall_s": 40.0, "total_tokens": 400.0},
    ]
    summary = v2_measure.arm_summary(rows)

    assert summary["n_runs"] == 4 and summary["n_tasks"] == 2
    assert summary["actual"]["rate"] == 0.75
    assert summary["actual"]["per_task"] == {"A": 0.5, "B": 1.0}
    assert summary["actual"]["task_rate_sd"] == pytest.approx(math.sqrt(0.125))

    assert summary["claimed"]["rate"] == 1.0 and summary["claimed"]["sd"] == 0.0

    assert summary["false_success"]["rate"] == 0.25
    assert summary["false_success"]["per_task"] == {"A": 0.5, "B": 0.0}
    assert summary["false_success"]["task_rate_sd"] == pytest.approx(math.sqrt(0.125))

    # seconds/task: A=15, B=35 -> mean 25, sample sd 14.142
    assert summary["wall_s_per_task"]["mean"] == pytest.approx(25.0)
    assert summary["wall_s_per_task"]["sd"] == pytest.approx(math.sqrt(200.0))
    # tokens/task: A=150, B=350 -> mean 250, sample sd 141.421
    assert summary["tokens_per_task"]["mean"] == pytest.approx(250.0)
    assert summary["tokens_per_task"]["sd"] == pytest.approx(100 * math.sqrt(2.0))


def test_single_seed_arm_has_no_fake_error_bar():
    rows = [{"task": "A", "actual": True, "claimed": False, "false_success": False,
             "run_wall_s": 5.0, "total_tokens": 50.0}]
    summary = v2_measure.arm_summary(rows)
    assert summary["actual"]["rate"] == 1.0
    assert summary["actual"]["sd"] == 0.0
    assert summary["actual"]["task_rate_sd"] == 0.0


# ---------------------------------------------------------------------------
# ablation switch
# ---------------------------------------------------------------------------

def test_ablation_names_and_disabled_stages_are_exact():
    assert set(v2_measure.ABLATIONS) == {"none", "own-test", "independent-test", "review"}
    none = v2_measure.ABLATIONS["none"]
    assert (none.verify_mode, none.use_judge, none.use_iv, none.use_review) == (
        "full", True, True, True)
    assert none.disabled == ()

    # The two clean single-stage ablations: only the named stage is switched off.
    iv = v2_measure.ABLATIONS["independent-test"]
    assert (iv.verify_mode, iv.use_judge, iv.use_iv, iv.use_review) == (
        "full", True, False, True)
    assert iv.disabled == ("independent-test",)

    rev = v2_measure.ABLATIONS["review"]
    assert (rev.verify_mode, rev.use_judge, rev.use_iv, rev.use_review) == (
        "full", True, True, False)
    assert rev.disabled == ("review",)

    # own-test is coupled: raw is the only leaf selector that skips the self-test, and it
    # also disables the independent test, the review, and the claim gate. The note records
    # the coupling instead of hiding it.
    own = v2_measure.ABLATIONS["own-test"]
    assert own.verify_mode == "raw"
    assert (own.use_judge, own.use_iv, own.use_review) == (False, False, False)
    assert set(own.disabled) == {"own-test", "independent-test", "review"}
    assert "raw" in own.note


def test_verify_mode_stage_table_covers_every_leaf_mode():
    assert set(v2_measure.VERIFY_MODE_STAGES) == set(VERIFICATION_MODES)
    assert v2_measure.VERIFY_MODE_STAGES["full"] == ()
    assert set(v2_measure.VERIFY_MODE_STAGES["test"]) == {"independent-test", "review"}
    assert set(v2_measure.VERIFY_MODE_STAGES["review"]) == {"own-test", "independent-test"}
    assert set(v2_measure.VERIFY_MODE_STAGES["raw"]) == {
        "own-test", "independent-test", "review"}


def test_parser_defaults_to_three_seeds_and_the_full_arm():
    parser = v2_measure.build_parser()
    args = parser.parse_args([])
    assert args.n is None and args.ablate == "none" and args.wall_clock is False
    assert args.tasks == "all"


# ---------------------------------------------------------------------------
# evidence readers
# ---------------------------------------------------------------------------

def test_read_token_usage_sums_the_model_call_counters(tmp_path):
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text("\n".join([
        json.dumps({"kind": "run_start"}),
        json.dumps({"kind": "model_call", "metrics": {"prompt_tokens": 100,
                                                      "completion_tokens": 20}}),
        json.dumps({"kind": "model_call", "metrics": {"prompt_tokens": 50,
                                                      "completion_tokens": 5}}),
    ]) + "\n")
    assert v2_measure.read_token_usage(traj) == {
        "prompt_tokens": 150, "completion_tokens": 25, "total_tokens": 175,
        "model_calls": 2}
    assert v2_measure.read_token_usage(tmp_path / "missing.jsonl")["total_tokens"] == 0


def test_load_pi_reference_keeps_the_later_band_for_a_duplicated_task(tmp_path):
    for band, rows in (("easy", [{"task": "T-01", "actual": True, "claimed": True,
                                  "wall_s": 10.0}]),
                       ("anchors", [{"task": "A-01", "actual": False, "claimed": True,
                                     "wall_s": 20.0}]),
                       ("tail", [{"task": "A-01", "actual": False, "claimed": False,
                                  "wall_s": 5.0}])):
        d = tmp_path / band
        d.mkdir()
        (d / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ref = v2_measure.load_pi_reference(tmp_path)
    assert ref["T-01"]["actual"] is True
    # tail precedes anchors in PI_BANDS order, so the anchors row is the later one.
    assert ref["A-01"]["wall_s"] == 20.0


def test_render_merged_puts_our_arm_beside_pi_and_marks_missing_reference():
    arms = {"none": [
        {"task": "T-01", "actual": True, "claimed": True, "run_wall_s": 10.0},
        {"task": "T-01", "actual": False, "claimed": True, "run_wall_s": 30.0},
    ]}
    pi = {"T-01": {"actual": True, "claimed": True, "wall_s": 106.1}}
    text = v2_measure.render_merged(arms, pi, ["T-01", "T-02"])
    assert "none:act" in text and "pi:act" in text
    assert "T-01 | 1/2 | 2/2 | 20 | 1/1 | 1/1 | 106" in text
    assert "T-02 | - | - | - | n/a | n/a | n/a" in text


# ---------------------------------------------------------------------------
# driver wiring
# ---------------------------------------------------------------------------

def _stage_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus" / "T-99-pinned"
    (corpus / "repo").mkdir(parents=True)
    (tmp_path / "anchor").mkdir()


def test_main_runs_every_arm_and_seed_sequentially_and_merges_pi(tmp_path, monkeypatch,
                                                                 capsys):
    _stage_corpus(tmp_path)
    monkeypatch.setattr(v2_measure, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(v2_measure, "ANCHOR", tmp_path / "anchor")
    monkeypatch.setattr(v2_measure, "ROOT", tmp_path)

    seen: list[dict] = []

    def fake_run_once(task_dir, out_dir, server, calls, deadline_hours, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trajectory.jsonl").write_text(json.dumps(
            {"kind": "model_call", "metrics": {"prompt_tokens": 10,
                                               "completion_tokens": 2}}) + "\n")
        seen.append(kw)
        return {"task": task_dir.name, "claimed": True, "actual": True,
                "quadrant": "true-success", "signal": "green", "stop_reason": "green",
                "calls": 1, "run_wall_s": 7.5}

    monkeypatch.setattr(v2_measure, "run_once", fake_run_once)

    # one band of pi evidence, same task, so the merge has a reference row
    band = tmp_path / "pi" / "easy"
    band.mkdir(parents=True)
    (band / "results.jsonl").write_text(json.dumps(
        {"task": "T-99-pinned", "actual": True, "claimed": True, "wall_s": 99.0}) + "\n")

    out = tmp_path / "out"
    monkeypatch.setattr("sys.argv", [
        "v2_measure", "--tasks", "all", "--n", "2",
        "--ablate", "none,independent-test,review,own-test",
        "--pi-reference", str(tmp_path / "pi"), "--out", str(out)])
    assert v2_measure.main() == 0

    # 4 arms x 1 task x 2 seeds, all sequential.
    assert len(seen) == 8
    expected = [
        {"use_judge": True, "use_iv": True, "use_review": True, "verify_mode": "full"},
        {"use_judge": True, "use_iv": False, "use_review": True, "verify_mode": "full"},
        {"use_judge": True, "use_iv": True, "use_review": False, "verify_mode": "full"},
        {"use_judge": False, "use_iv": False, "use_review": False, "verify_mode": "raw"},
    ]
    assert seen == [kw for kw in expected for _ in range(2)]

    # per-arm summaries and token accounting landed on disk; merge carries the pi row.
    summary = json.loads((out / "summary.json").read_text())
    assert summary["n"] == 2 and summary["wall_clock"] is False
    assert set(summary["arms"]) == {"none", "independent-test", "review", "own-test"}
    none_rows = [json.loads(line) for line in
                 (out / "none" / "results.jsonl").read_text().splitlines()]
    assert len(none_rows) == 2
    assert none_rows[0]["total_tokens"] == 12 and none_rows[0]["false_success"] is False
    merged = json.loads((out / "merged.json").read_text())
    assert merged["pi"]["T-99-pinned"]["wall_s"] == 99.0
    assert (out / "merged.md").read_text().count("pi:act") == 1
    assert "arm=none" in capsys.readouterr().out


def test_wall_clock_defaults_to_a_single_lane(tmp_path, monkeypatch):
    _stage_corpus(tmp_path)
    monkeypatch.setattr(v2_measure, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(v2_measure, "ANCHOR", tmp_path / "anchor")
    monkeypatch.setattr(v2_measure, "ROOT", tmp_path)
    calls: list[int] = []

    def fake_run_once(task_dir, out_dir, server, calls_n, deadline_hours, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        calls.append(calls_n)
        return {"task": task_dir.name, "claimed": False, "actual": False,
                "quadrant": "honest-failure", "signal": "x", "stop_reason": "calls",
                "calls": 0, "run_wall_s": 3.0}

    monkeypatch.setattr(v2_measure, "run_once", fake_run_once)
    out = tmp_path / "out"
    monkeypatch.setattr("sys.argv", [
        "v2_measure", "--tasks", "all", "--wall-clock", "--out", str(out)])
    assert v2_measure.main() == 0
    assert calls == [24]  # one lane, one pass
    summary = json.loads((out / "summary.json").read_text())
    assert summary["wall_clock"] is True and summary["n"] == 1


def test_unknown_ablation_is_refused(tmp_path, monkeypatch):
    _stage_corpus(tmp_path)
    monkeypatch.setattr(v2_measure, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(v2_measure, "ANCHOR", tmp_path / "anchor")
    monkeypatch.setattr("sys.argv",
                        ["v2_measure", "--tasks", "all", "--ablate", "nonsense"])
    with pytest.raises(SystemExit):
        v2_measure.main()
