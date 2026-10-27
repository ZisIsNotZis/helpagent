"""Integrity guard for the maxed-config pi evidence (bench/runs/evidence/pi-maxed-20261006).

The fairness correction recorded in ``docs/2_GOAL.md`` section 8 rests on these files. If a
future edit silently changes them (a hand-edit, a partial re-run, a lost band) the headline
numbers in the docs stop matching the evidence; this test makes that failure loud.

It asserts only what the records themselves can witness: the row count and task coverage, that
every row's quadrant is consistent with its claimed/actual pair, and the two totals the docs
quote.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "bench" / "runs" / "evidence" / "pi-maxed-20261006"

BANDS = ("easy", "mid1", "mid2", "tail", "anchors")
REQUIRED_FIELDS = ("task", "claimed", "actual", "quadrant", "wall_s", "turns")

#: The capped ``tail`` band reached A-01 before its 1700 s limit, and the ``anchors`` band
#: measured it again. Both rows stay in the raw evidence; the tally uses the later one.
DUPLICATED_TASK = "A-01-word-count"


def _raw_rows(band: str) -> list[dict]:
    path = EVIDENCE / band / "results.jsonl"
    assert path.is_file(), f"missing evidence file: {path}"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _rows() -> list[dict]:
    """All rows, one per task: the later band wins for the one task measured twice."""
    by_task: dict[str, dict] = {}
    for band in BANDS:
        for row in _raw_rows(band):
            by_task[row["task"]] = row
    return list(by_task.values())


def _quadrant(claimed: bool, actual: bool) -> str:
    if claimed and actual:
        return "true-success"
    if claimed and not actual:
        return "false-success"
    if not claimed and actual:
        return "missed-success"
    return "honest-failure"


def test_evidence_exists_and_covers_all_forty_tasks() -> None:
    rows = _rows()
    tasks = [r["task"] for r in rows]
    assert len(tasks) == 40, f"expected 40 measured tasks, found {len(tasks)}"
    assert len(set(tasks)) == 40, "a task was measured twice in the maxed arm"


@pytest.mark.parametrize("band", BANDS)
def test_each_band_has_a_summary_consistent_with_its_rows(band: str) -> None:
    rows = _raw_rows(band)
    summary_path = EVIDENCE / band / "summary.json"
    if not summary_path.is_file():
        # The tail band hit its 1700 s cap mid-band and never wrote a summary; its rows are
        # still evidence, so require the rows and record why the summary is allowed to be gone.
        assert band == "tail", f"only the capped tail band may lack a summary (band={band})"
        assert len(rows) == 6, (
            "the capped tail band should carry its five finished tail rows plus the A-01 row it "
            "reached before the cap"
        )
        return
    summary = json.loads(summary_path.read_text())
    if "runs" in summary:
        assert summary["runs"] == len(rows)
    if "actual_pass" in summary:
        assert summary["actual_pass"] == f"{sum(1 for r in rows if r['actual'])}/{len(rows)}"


def test_the_task_measured_twice_agrees_with_itself() -> None:
    """A-01 ran in the capped tail band and again in the anchors band; both must fail."""
    hits = [r for band in BANDS for r in _raw_rows(band) if r["task"] == DUPLICATED_TASK]
    assert len(hits) == 2, f"expected 2 rows for {DUPLICATED_TASK}, found {len(hits)}"
    assert all(r["actual"] is False for r in hits), (
        "the two A-01 measurements disagree; re-read the note in the evidence README before "
        "quoting a per-task number"
    )


def test_every_row_is_self_consistent() -> None:
    for row in _rows():
        for field in REQUIRED_FIELDS:
            assert field in row, f"{row.get('task')} is missing {field}"
        assert isinstance(row["claimed"], bool)
        assert isinstance(row["actual"], bool)
        assert row["quadrant"] == _quadrant(row["claimed"], row["actual"]), (
            f"{row['task']}: quadrant {row['quadrant']!r} contradicts "
            f"claimed={row['claimed']} actual={row['actual']}"
        )


def test_headline_totals_quoted_in_the_docs() -> None:
    rows = _rows()
    actual = sum(1 for r in rows if r["actual"])
    false_success = sum(1 for r in rows if r["claimed"] and not r["actual"])
    assert actual == 27, f"docs quote 27/40 for the maxed arm; evidence says {actual}/40"
    assert false_success == 2, f"docs quote 2 false successes; evidence says {false_success}"
