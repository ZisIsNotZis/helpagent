"""An unable run-summary has no payload and cannot invalidate the decided gate."""
from harness.envelopes import RunSummary
from bench import golden_bugfix as gb


def test_unable_summary_is_shaped_not_subscripted(monkeypatch):
    events = []
    monkeypatch.setattr(gb, "note", lambda kind, **kw: events.append((kind, kw)))
    summary = RunSummary.model_validate({"status": "unable", "comment": "cannot summarize",
                                         "unable_reason": "missing detail"})
    assert gb.summary_fields(summary, False) == (
        "parked-needs-user", "Run summary unavailable (unable); gate_ok=False")
    assert gb.summary_fields(summary, True) == (
        "partial", "Run summary unavailable (unable); gate_ok=True")
    assert events == [("run_summary_unavailable", {"status": "unable"})] * 2


def test_valid_summary_uses_payload(monkeypatch):
    monkeypatch.setattr(gb, "note", lambda *_a, **_kw: None)
    summary = RunSummary.model_validate({"status": "ok", "comment": "done", "outcome": "complete",
                                         "what_was_done": "fixed", "what_changed": "code", "what_remains": "nothing"})
    assert gb.summary_fields(summary, True) == ("complete", "fixed")
