"""Expand children must be complete; unable envelopes have no child payload."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from bench import golden_bugfix as gb
from harness.envelopes import Expand


def test_expand_rejects_missing_nested_child_why():
    payload = {"status": "ok", "comment": "split", "children": [
        {"seam_id": "seam-primary", "what": "fix", "leaf": True, "est_rounds": 1}]}
    with pytest.raises(ValidationError, match="child fill requires fields"):
        Expand.model_validate(payload)


@pytest.mark.parametrize("failure", ["unable", "invalid"])
def test_unavailable_expand_is_shaped_before_child_access(monkeypatch, tmp_path: Path,
                                                           failure: str):
    task = Path(__file__).resolve().parents[1] / "fixtures" / "mini_repo"
    monkeypatch.setattr(gb, "ROOT", tmp_path)
    monkeypatch.setattr(gb, "LlamaServerRunner", lambda *_: None)
    monkeypatch.setattr(gb, "pytest_exit", lambda *_: 1)
    monkeypatch.setattr(gb, "step_task_card", lambda *_: SimpleNamespace(
        status="ok", goal="fix", task_class="bugfix"))
    def fake_expand(*_a, **_kw):
        if failure == "invalid":
            raise gb.SchemaViolation("missing child why")
        return Expand.model_validate({
            "status": "unable", "comment": "cannot split", "unable_reason": "missing detail"})
    monkeypatch.setattr(gb, "step_expand", fake_expand)
    monkeypatch.setattr(gb, "step_spec", lambda *_a, **_kw: pytest.fail("must not write spec"))
    monkeypatch.setattr(sys, "argv", ["golden_bugfix.py", "--task", str(task)])
    assert gb.main() == 1
    summaries = list((tmp_path / "bench" / "runs").glob("*/golden/*/summary.json"))
    assert len(summaries) == 1
    assert json.loads(summaries[0].read_text())["reason"] == "expand_unavailable"
