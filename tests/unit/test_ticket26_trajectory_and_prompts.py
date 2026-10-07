"""Ticket 26 — full trajectory capture, and the model-facing text that T-01 exposed.

Two classes of invariant, both from the 2026-10-06 owner review of the T-01 run:

1. EVIDENCE: the trajectory must record what the model saw, what it answered, what the
   harness executed and what came back — completely, and without ever changing a run.
2. MODEL-FACING TEXT: the run must tell the model which files it MAY write, which are
   frozen and why, when a named artifact is still untouched, and exactly what a refused
   write means (T-01's model got "implement refused: grader-owned path" six times, with no
   file name, and repeated the same frozen target).
"""

from __future__ import annotations

import json

import pytest

from harness.attempts import Attempt
from harness.envelopes import SCHEMAS, ImplementWrite
from harness.leaf import (
    Escalation,
    LeafSpec,
    _implement_artifacts,
    _implement_question,
    _mode,
    _refusal_feedback,
)
from harness.telemetry import (
    clear_sinks,
    jsonable_envelope,
    jsonl_sink,
    record,
    set_sink,
)


def _spec(tmp_path) -> LeafSpec:
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 1\n")
    return LeafSpec(
        goal="the total is computed wrongly",
        files={"pkg/calc.py": "def result():\n    return 1\n", "README.md": "docs\n"},
        acs=["the total must be right"],
        interfaces=[],
        grader_paths=("README.md",),
    )


# ---------------------------------------------------------------------------
# 1. the write envelope
# ---------------------------------------------------------------------------


def test_implement_write_accepts_one_or_many_files():
    one = SCHEMAS["implement_write"].model_validate(
        {"status": "ok", "comment": "c", "files": [{"file_path": "a.py", "content": "x = 1\n"}]})
    assert [f.file_path for f in one.files] == ["a.py"]
    two = SCHEMAS["implement_write"].model_validate(
        {"status": "ok", "comment": "c",
         "files": [{"file_path": "a.py", "content": "x = 1\n"},
                   {"file_path": "b.py", "content": "y = 2\n"}]})
    assert [f.file_path for f in two.files] == ["a.py", "b.py"]


def test_single_file_shape_is_promoted_not_refused():
    """Parameter-layer tolerance: file_path+content IS a one-element files list."""
    env = SCHEMAS["implement_write"].model_validate(
        {"status": "ok", "comment": "c", "file_path": "a.py", "content": "x = 1\n"})
    assert [f.file_path for f in env.files] == ["a.py"]
    assert env.files[0].content == "x = 1\n"


def test_the_step_type_is_not_write_test():
    """The prompt used to read "STEP: write_test" while asking for a source fix."""
    from harness.runner import STEP_DISPLAY

    assert "implement_write" in SCHEMAS
    assert STEP_DISPLAY["implement_write"] == "implement"


# ---------------------------------------------------------------------------
# 2. what the model is told
# ---------------------------------------------------------------------------


def test_artifacts_name_the_writable_and_frozen_files(tmp_path):
    spec = _spec(tmp_path)
    arts = _implement_artifacts(spec, tmp_path, Escalation("L1-resample", "sampling", False, "x"),
                                [], [], None, "M2", {})
    assert "pkg/calc.py" in arts["writable_files"]
    assert "README.md" not in arts["writable_files"]
    assert "README.md" in arts["frozen_files"]
    assert "byte-identical" in arts["frozen_files"]
    assert "untouched_required_artifacts" in arts


def test_refusal_feedback_names_the_file_the_reason_and_what_may_be_written(tmp_path):
    spec = _spec(tmp_path)
    text = _refusal_feedback([("README.md", "grader-owned path")], spec)
    assert "README.md" in text          # T-01: the old message had no file name at all
    assert "grader-owned path" in text
    assert "pkg/calc.py" in text        # what it MAY write instead
    assert "status=blocked" in text


def test_a_refused_write_keeps_the_draft_and_changes_the_wording():
    refused = Attempt(node_id="leaf", layer="implementation", strategy="L1-resample",
                      claimed_delta="tried", outcome="fail", touched_files=[], refused=True)
    assert _mode([refused]) == "M2"     # nothing on disk to erase
    question = _implement_question("M2", Escalation("L1-resample", "sampling", False, "x"),
                                   last_refused=True)
    assert "REFUSED" in question
    assert "writable_files" in question
    assert "as your only intelligence" not in question


def test_the_prompt_no_longer_promises_a_single_file_fix():
    question = _implement_question("M2", Escalation("L1-resample", "sampling", False, "x"))
    assert "ONE implementation file" not in question
    assert "may need more than one file" in question


# ---------------------------------------------------------------------------
# 3. the trajectory itself
# ---------------------------------------------------------------------------


def test_jsonable_envelope_never_raises_on_a_non_ok_envelope():
    """A status!=ok envelope keeps the REQUIRED sentinel in its payload, which json mode
    refuses — instrumentation must not raise (it once ate a whole call budget)."""
    env = SCHEMAS["write_test"].model_validate(
        {"status": "unable", "comment": "c", "unable_reason": "no ground truth"})
    dumped = jsonable_envelope(env)
    assert dumped is not None
    json.dumps(dumped, default=str)     # JSON-safe by construction


def test_record_swallows_a_broken_sink():
    def _broken(_event: dict) -> None:
        raise RuntimeError("disk on fire")

    set_sink(_broken)
    try:
        record("test_event", value=1)   # must not raise
    finally:
        clear_sinks()


def test_jsonl_sink_writes_one_object_per_event(tmp_path):
    path = tmp_path / "trajectory.jsonl"
    set_sink(jsonl_sink(path))
    try:
        record("first", payload={"a": 1})
        record("second", payload=None)
    finally:
        clear_sinks()
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["kind"] for line in lines] == ["first", "second"]
    assert lines[0]["payload"] == {"a": 1}
    assert lines[0]["seq"] < lines[1]["seq"]


def test_a_model_call_is_recorded_with_prompt_and_raw_answer(tmp_path):
    """The single most important record: what the model was shown and what it answered."""
    import asyncio

    from harness.fake_model import FakeModelRunner
    from harness.runner import llm_step

    fake = FakeModelRunner({"write_test": [{"status": "ok", "comment": "c",
                                            "file_path": "a.py", "content": "x = 1\n"}]})
    path = tmp_path / "trajectory.jsonl"
    set_sink(jsonl_sink(path))
    try:
        asyncio.run(llm_step(fake, "write_test", artifacts={"goal": "g"}, question="write it"))
    finally:
        clear_sinks()
    calls = [json.loads(line) for line in path.read_text().splitlines()
             if json.loads(line)["kind"] == "model_call"]
    assert len(calls) == 1
    assert calls[0]["step_type"] == "write_test"
    assert "write it" in calls[0]["question"]
    assert calls[0]["prompt"]
    assert calls[0]["status"] == "ok"
    assert calls[0]["envelope"]["file_path"] == "a.py"
