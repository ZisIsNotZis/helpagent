"""Regression: staged draft, not original corpus, is the next attempt's input."""
import json
import sys
from pathlib import Path

import pytest
from types import SimpleNamespace

from bench import golden_bugfix as gb
from bench import tiered


@pytest.mark.parametrize("retry_view,second", [("draft", "draft-one"), ("initial", "original")])
def test_attempt_sees_selected_snapshot_and_exhaustion_restores(monkeypatch, tmp_path: Path,
                                                                 retry_view: str, second: str):
    file = tmp_path / "impl.py"
    file.write_text("original")
    initial = {"impl.py": "original"}
    prompts = []
    outputs = iter(["draft-one", "draft-two"])

    def fake_step(_model, _kind, **kw):
        prompts.append(json.loads(kw["artifacts"]["current_files"]))
        return SimpleNamespace(status="ok", file_path="impl.py", content=next(outputs))

    async def fake_check(_workdir, path, content, **_kw):
        (tmp_path / path).write_text(content)
        return SimpleNamespace(ok=True, findings=[])

    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "check_write", fake_check)
    monkeypatch.setattr(gb, "run_pytest", lambda _w: SimpleNamespace(exit=1, verdict="failed", excerpts=["still red"]))
    monkeypatch.setattr(gb, "diagnose_test_output", lambda *_: [])
    monkeypatch.setattr(gb, "note", lambda *_a, **_kw: None)
    trajectory = SimpleNamespace(record=lambda **_kw: None)
    spec = SimpleNamespace(files_touched=["impl.py"], interfaces=[], behavior="fix", implementation_notes="")
    acc = set()
    fixed, _, history = gb.step_implement(None, spec, tmp_path, initial, 2, trajectory,
                                           harness_written_acc=acc, retry_view=retry_view)
    assert not fixed and len(history) == 2
    assert prompts == [{"impl.py": "original"}, {"impl.py": second}]
    assert [h["staged_delta"] for h in history] == [[], ["impl.py"]]
    assert file.read_text() == "original"
    assert acc == set()


def test_multifile_attempt_sees_prior_edit_and_keeps_both_on_green(monkeypatch, tmp_path: Path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text("original")
    prompts = []
    outputs = iter([("a.py", "draft-a"), ("b.py", "draft-b")])

    def fake_step(_model, _kind, **kw):
        prompts.append(json.loads(kw["artifacts"]["current_files"]))
        path, content = next(outputs)
        return SimpleNamespace(status="ok", file_path=path, content=content)

    async def fake_check(_workdir, path, content, **_kw):
        (tmp_path / path).write_text(content)
        return SimpleNamespace(ok=True, findings=[])

    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "check_write", fake_check)
    monkeypatch.setattr(gb, "run_pytest", lambda _w: SimpleNamespace(
        exit=0 if (tmp_path / "b.py").read_text() == "draft-b" else 1,
        verdict="ok", excerpts=["still red"]))
    monkeypatch.setattr(gb, "diagnose_test_output", lambda *_: [])
    monkeypatch.setattr(gb, "note", lambda *_a, **_kw: None)
    spec = SimpleNamespace(files_touched=["a.py", "b.py"], interfaces=[], behavior="fix", implementation_notes="")
    acc = set()
    fixed, _, _ = gb.step_implement(None, spec, tmp_path, {"a.py": "original", "b.py": "original"},
                                    2, SimpleNamespace(record=lambda **_kw: None), harness_written_acc=acc)
    assert fixed
    assert prompts[1]["a.py"] == "draft-a"
    assert (tmp_path / "a.py").read_text() == "draft-a"
    assert acc == {"a.py", "b.py"}


def test_tiered_gear_zero_calls_current_implement_contract(monkeypatch, tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "request.md").write_text("fix impl.py")
    (task_dir / "repo").mkdir()
    (task_dir / "repo" / "impl.py").write_text("original")
    called = []

    def fake_implement(*args, **kwargs):
        called.append(kwargs)
        return False, "red", []

    monkeypatch.setattr(tiered.gb, "step_implement", fake_implement)
    monkeypatch.setattr(tiered.gb, "gate", lambda *_: (False, ["red"]))
    row = tiered.run_gear(0, task_dir, tmp_path / "runs", None, retry_view="initial")
    assert row["result"] == "FAIL"
    assert len(called) == 1
    assert "accumulate" not in called[0]
    assert isinstance(called[0]["harness_written_acc"], set)
    assert called[0]["retry_view"] == "initial"


def test_tiered_repeats_get_distinct_evidence_directories(monkeypatch, tmp_path: Path):
    (tmp_path / "bench" / "corpus" / "T-01-example").mkdir(parents=True)
    (tmp_path / "bench" / "anchor").mkdir()
    seen = []

    def fake_run(task, runs_dir, model, gear, retry_view="draft"):
        seen.append(runs_dir)
        return {"task": task.name, "gear": 0, "result": "FAIL", "wall_s": 0.0}

    monkeypatch.setattr(tiered, "ROOT", tmp_path)
    monkeypatch.setattr(tiered, "load_model", lambda *_: None)
    monkeypatch.setattr(tiered, "run_tiered", fake_run)
    monkeypatch.setattr(sys, "argv", ["tiered.py", "--n", "2", "--tasks", "T-01-example"])
    assert tiered.main() == 0
    assert len(seen) == 2
    assert seen[0].name == "run-1" and seen[1].name == "run-2"
    assert seen[0] != seen[1]
