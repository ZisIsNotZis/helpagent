"""Experimental source ordering is deterministic and never widens the spec boundary."""
import json
from pathlib import Path
from types import SimpleNamespace

from bench import golden_bugfix as gb


def test_t31_dependency_order_ignores_tests_and_docs():
    task = gb.load_task(gb.ROOT / "bench" / "corpus" / "T-31-parameter-threading")
    assert gb.source_dependency_order(task["files"]) == [
        "api/transport.py", "api/client.py", "api/service.py", "exporter/bulk.py"]


def test_large_repo_or_cycle_disables_ordering():
    files = {f"m{i}.py": f"def f{i}(): pass\n" for i in range(9)}
    assert gb.source_dependency_order(files) == []
    assert gb.source_dependency_order({"a.py": "from b import f\ndef f(): pass\n",
                                       "b.py": "from a import f\ndef f(): pass\n"}) == []


def test_ordered_emit_rejects_file_outside_spec_boundary(monkeypatch, tmp_path: Path):
    files = {"a.py": "def a(): pass\n", "b.py": "from a import a\ndef b(): return a()\n"}
    for rel, content in files.items():
        (tmp_path / rel).write_text(content)
    prompts = []
    responses = iter(["b.py", "a.py"])

    def fake_step(_model, _kind, **kw):
        prompts.append((kw["context"]["boundary_files"], json.loads(kw["artifacts"]["current_files"])))
        return SimpleNamespace(status="ok", file_path=next(responses), content="def a(): return 1\n")

    async def fake_check(_workdir, rel, content, **_kw):
        (tmp_path / rel).write_text(content)
        return SimpleNamespace(ok=True, findings=[])

    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "check_write", fake_check)
    monkeypatch.setattr(gb, "run_pytest", lambda _w: SimpleNamespace(exit=0, verdict="ok", excerpts=[]))
    monkeypatch.setattr(gb, "note", lambda *_a, **_kw: None)
    spec = SimpleNamespace(files_touched=["a.py"], interfaces=[], behavior="fix", implementation_notes="")
    fixed, _, history = gb.step_implement(None, spec, tmp_path, files, 2,
                                          SimpleNamespace(record=lambda **_kw: None), ordered_files=True)
    assert fixed and history[0]["outcome"] == "outside-planned-file:b.py"
    assert prompts[0][0] == ["a.py"]
    assert (tmp_path / "b.py").read_text() == files["b.py"]
