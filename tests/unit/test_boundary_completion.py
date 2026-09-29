"""Boundary completion: rule evidence may add a repo file to the write set."""
import json
from pathlib import Path
from types import SimpleNamespace

from bench import golden_bugfix as gb
from harness.checks import CheckFinding


def _fake_llm(files_seen, outputs):
    calls = []

    def fake_step(_model, _kind, **kw):
        calls.append(json.loads(kw["artifacts"]["current_files"]))
        path, content = next(outputs)
        return SimpleNamespace(status="ok", file_path=path, content=content)

    return fake_step, calls


def _fake_check(tmp_path):
    async def fake_check(_workdir, rel, content, **_kw):
        (tmp_path / rel).write_text(content)
        return SimpleNamespace(ok=True, findings=[])
    return fake_check


def test_rule_finding_outside_boundary_extends_write_set(monkeypatch, tmp_path: Path):
    files = {"api/transport.py": "def send(u, p): pass\n",
             "api/client.py": "from api.transport import send\n"}
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    outputs = iter([("api/transport.py", "def send(u, p): pass\n"),
                    ("api/client.py", "def fetch(u):\n    return send(u, '')\n")])
    fake_step, calls = _fake_llm(files, outputs)
    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "check_write", _fake_check(tmp_path))
    # first attempt red with a rule finding naming client.py (outside boundary);
    # second attempt green
    red = SimpleNamespace(exit=1, verdict="failed",
                          excerpts=["E   TypeError: send() got an unexpected keyword argument 'timeout'"])
    results = iter([red, SimpleNamespace(exit=0, verdict="ok", excerpts=[])])
    monkeypatch.setattr(gb, "run_pytest", lambda _w: next(results))
    monkeypatch.setattr(gb, "diagnose_test_output", lambda excerpts, files_map: [
        CheckFinding(stage="rules", path="api/client.py", code="arity-signature-thread",
                     message="thread timeout")])
    events = []
    monkeypatch.setattr(gb, "note", lambda kind, **kw: events.append((kind, kw)))
    spec = SimpleNamespace(files_touched=["api/transport.py"], interfaces=[],
                           behavior="thread", implementation_notes="")
    fixed, _, _ = gb.step_implement(None, spec, tmp_path, files, 2,
                                    SimpleNamespace(record=lambda **_kw: None),
                                    boundary_completion=True)
    assert fixed
    assert ("boundary_completion", {"file": "api/client.py", "rule": "arity-signature-thread"}) in events
    assert "api/client.py" in calls[1]  # second prompt sees and may write the completed boundary


def test_completion_never_adds_test_files(monkeypatch, tmp_path: Path):
    (tmp_path / "a.py").write_text("def send(u, p): pass\n")
    outputs = iter([("a.py", "def send(u, p): pass\n")])
    fake_step, _ = _fake_llm({}, outputs)
    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "check_write", _fake_check(tmp_path))
    monkeypatch.setattr(gb, "run_pytest", lambda _w: SimpleNamespace(
        exit=1, verdict="failed", excerpts=["E   TypeError: send() got an unexpected keyword argument 't'"]))
    monkeypatch.setattr(gb, "diagnose_test_output", lambda excerpts, files_map: [
        CheckFinding(stage="rules", path="tests/test_x.py", code="arity-signature-thread",
                     message="thread")])
    events = []
    monkeypatch.setattr(gb, "note", lambda kind, **kw: events.append((kind, kw)))
    spec = SimpleNamespace(files_touched=["a.py"], interfaces=[], behavior="fix", implementation_notes="")
    gb.step_implement(None, spec, tmp_path, {"a.py": "def send(u, p): pass\n"}, 1,
                      SimpleNamespace(record=lambda **_kw: None), boundary_completion=True)
    assert not any(kind == "boundary_completion" for kind, _ in events)
