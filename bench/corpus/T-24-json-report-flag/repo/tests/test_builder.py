"""Output-mode tests."""

import json

from report.builder import build_report


def test_legacy_text_mode():
    out = build_report([["a", 1]])
    assert out.startswith("DAILY REPORT")


def test_json_mode_returns_document():
    doc = json.loads(build_report([["a", 1], ["b", 2]], as_json=True))
    assert doc == {"rows": [["a", 1], ["b", 2]]}
