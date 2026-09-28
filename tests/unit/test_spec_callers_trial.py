"""The optional spec-time map reports imports, not inferred semantic calls."""
from bench import golden_bugfix as gb


def test_t31_importers_surface_both_branches():
    files = gb.load_task(gb.ROOT / "bench" / "corpus" / "T-31-parameter-threading")["files"]
    result = gb.module_importers(files)
    assert "api/transport.py <- imported by: api/client.py" in result
    assert "api/client.py <- imported by: api/service.py, exporter/bulk.py" in result
    assert "tests/" not in result


def test_t33_map_respects_frozen_base_request():
    files = gb.load_task(gb.ROOT / "bench" / "corpus" / "T-33-serializer-contract")["files"]
    result = gb.module_importers(files)
    assert "serialize/base.py <- imported by: serialize/json_ser.py, serialize/pickle_ser.py" in result
    assert "tests/" not in result


def test_bad_syntax_does_not_crash_map():
    assert gb.module_importers({"a.py": "def broken(\n", "b.py": "from a import f\n"}) == (
        "- a.py <- imported by: b.py")


def test_spec_receives_map_only_when_enabled(monkeypatch):
    seen = []
    monkeypatch.setattr(gb, "llm_step", lambda *_a, **kw: seen.append(kw) or object())
    files = {"a.py": "def f(): pass\n", "b.py": "from a import f\n"}
    monkeypatch.setattr(gb, "SPEC_CALLERS", False)
    gb.step_spec(None, "fix", files, "", request="propagate")
    assert "repo_importers" not in seen[-1]["artifacts"]
    monkeypatch.setattr(gb, "SPEC_CALLERS", True)
    gb.step_spec(None, "fix", files, "", request="propagate")
    assert "a.py <- imported by: b.py" in seen[-1]["artifacts"]["repo_importers"]
    assert "include relevant importers" in seen[-1]["question"]
