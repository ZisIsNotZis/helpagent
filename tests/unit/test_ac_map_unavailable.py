"""A missing leaf AC map must fail cleanly, not crash or bypass the gate."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import golden_bugfix as gb


@pytest.mark.parametrize("failure", ["unable", "schema"])
def test_step_acs_unavailable_is_shaped(monkeypatch, failure):
    def fake_step(*_a, **_kw):
        if failure == "schema":
            raise gb.SchemaViolation("draft_acs: malformed map")
        return SimpleNamespace(status="unable", unable_reason="cannot map")

    monkeypatch.setattr(gb, "llm_step", fake_step)
    monkeypatch.setattr(gb, "note", lambda *_a, **_kw: None)
    acs, verdict, decides = gb.step_acs(None, "leaf", SimpleNamespace(interfaces=[], behavior="fix"))
    assert (acs, verdict, decides) == (None, None, 0)


def test_main_fails_cleanly_without_leaf_map(monkeypatch, tmp_path: Path, capsys):
    task = Path(__file__).resolve().parents[1] / "fixtures" / "mini_repo"
    monkeypatch.setattr(gb, "ROOT", tmp_path)
    monkeypatch.setattr(gb, "LlamaServerRunner", lambda *_: None)
    monkeypatch.setattr(gb, "pytest_exit", lambda *_: 1)
    monkeypatch.setattr(gb, "step_task_card", lambda *_: SimpleNamespace(status="ok", goal="fix", task_class="bugfix"))
    monkeypatch.setattr(gb, "step_expand", lambda *_a, **_kw: SimpleNamespace(status="ok", children=[
        SimpleNamespace(what="fix", why="bug", est_rounds=1)]))
    monkeypatch.setattr(gb, "step_spec", lambda *_a, **_kw: SimpleNamespace(
        interfaces=[], files_touched=["calc.py"]))
    monkeypatch.setattr(gb, "step_acs", lambda *_: (None, None, 0))
    monkeypatch.setattr(gb, "step_implement", lambda *_a, **_kw: pytest.fail("must not implement without AC map"))
    monkeypatch.setattr(sys, "argv", ["golden_bugfix.py", "--task", str(task)])
    assert gb.main() == 1
    assert "AC map unavailable" in capsys.readouterr().out
    summaries = list((tmp_path / "bench" / "runs").glob("*/golden/*/summary.json"))
    assert len(summaries) == 1
    assert json.loads(summaries[0].read_text())["reason"] == "ac_map_unavailable"
