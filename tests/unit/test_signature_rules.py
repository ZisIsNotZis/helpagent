"""Signature-arity rule: threaded parameters point at the def and its callers."""
from harness.checks import diagnose_test_output

EXCERPTS = [
    "FAILED tests/test_chain.py::test_transport_accepts_timeout",
    "E       TypeError: send() got an unexpected keyword argument 'timeout'",
    "E       TypeError: fetch() got an unexpected keyword argument 'timeout'",
]

FILES = {
    "api/transport.py": '"""HTTP transport."""\n\n\ndef send(url: str, payload: str) -> str:\n    return "ok"\n',
    "api/client.py": "from api.transport import send\n\n\ndef fetch(url, payload=\"\"):\n    return send(url, payload)\n",
    "api/service.py": "from api.client import fetch\n\n\ndef sync_record(record_id):\n    return fetch(f\"/records/{record_id}\")\n",
    "README.md": "docs\n",
}


def test_unexpected_kwarg_points_at_def_and_callers():
    findings = diagnose_test_output(EXCERPTS, FILES)
    codes = [(f.path, f.code) for f in findings]
    assert ("api/transport.py", "arity-signature-thread") in codes
    transport = next(f for f in findings if f.path == "api/transport.py")
    assert "'timeout'" in transport.message
    assert "api/client.py" in transport.message  # the caller must thread it


def test_definition_already_accepting_kwarg_is_not_flagged():
    fixed = dict(FILES, **{"api/transport.py": "def send(url, payload, timeout=1.0):\n    return 'ok'\n"})
    findings = diagnose_test_output(EXCERPTS, fixed)
    assert all(f.path != "api/transport.py" for f in findings)
    assert findings  # fetch still lacks it


def test_missing_positional_form_and_unrelated_typeerror_are_scoped():
    missing = diagnose_test_output(["E   TypeError: send() missing 1 required positional argument: 'payload'"], FILES)
    assert any(f.code == "arity-signature-thread" and f.path == "api/transport.py" for f in missing)
    unrelated = diagnose_test_output(["E   TypeError: unsupported operand type(s) for +"], FILES)
    assert unrelated == []
