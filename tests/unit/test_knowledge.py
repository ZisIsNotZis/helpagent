"""Injection-first knowledge pack (docs/6_ARCHITECTURE.md §4.4, M6).

Pin: deterministic extraction (signatures / cross-file callers / constants),
bounded rendering, empty-when-nothing-applies, and the T-31 use case — the
call-site map must surface BOTH forgotten callers of a threaded parameter.
"""

from harness.knowledge import build_knowledge

FILES = {
    "api/client.py": (
        "from api.transport import send\n\n\n"
        "def fetch(url: str, payload: str = \"\", timeout: float = 1.0) -> str:\n"
        "    return send(url, payload, timeout=timeout)\n"),
    "api/transport.py": (
        "DEADLINE = 1.0\n\n\n"
        "def send(url: str, payload: str) -> str:\n"
        "    return f\"200:{url}\"\n"),
    "api/service.py": (
        "from api.client import fetch\n\n\n"
        "def sync_record(record_id: str) -> str:\n"
        "    return fetch(f\"/records/{record_id}\")\n"),
    "exporter/bulk.py": (
        "from api.client import fetch\n\n\n"
        "def export_all(ids: list) -> list:\n"
        "    return [fetch(f\"/export/{i}\") for i in ids]\n"),
    "docs/notes.md": "# notes\nfetch is used everywhere.\n",
}
BOUNDARY = sorted(FILES)


def test_signatures_listed_per_boundary_file():
    out = build_knowledge(FILES, BOUNDARY)
    assert "def fetch(url: str" in out
    assert "def send(url: str" in out
    assert "class " not in out or "class" in FILES["api/client.py"]


def test_callers_surface_cross_file_references():
    """The T-31 case: fetch() has TWO callers in OTHER files — both must appear,
    with the defining file named, so a fix cannot forget one."""
    out = build_knowledge(FILES, BOUNDARY)
    assert "fetch (in api/client.py) <- called by: api/service.py, exporter/bulk.py" in out


def test_constants_listed_with_values():
    out = build_knowledge(FILES, BOUNDARY)
    assert "DEADLINE = 1.0" in out


def test_non_py_and_out_of_boundary_excluded():
    out = build_knowledge(FILES, BOUNDARY)
    assert "notes.md" not in out   # non-py: no signatures/constants from it


def test_render_is_bounded():
    big = {f"f{i}.py": "\n".join(f"def fn{i}_{j}(x):\n    pass\n" for j in range(30))
           for i in range(10)}
    out = build_knowledge(big, sorted(big))
    assert len(out.splitlines()) <= 48


def test_empty_when_nothing_applies():
    assert build_knowledge({}, []) == ""
    out = build_knowledge({"a.txt": "hello"}, ["a.txt"])
    assert out == ""
