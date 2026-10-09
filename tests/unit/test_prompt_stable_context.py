"""C1/C2 — the run-invariant stable context block and the bounded source view.

C1: the artifacts that are byte-identical across the calls of one run (goal, constraints,
file listings, the source view) are emitted ONCE, as a byte-stable prefix, and are NOT
re-rendered a second time from the per-step artifacts. C2: only the files the plan declares
are injected in full; every other source file is injected as a compact index (path, line
count, docstring first line, top-level def/class names with line numbers).
"""

from __future__ import annotations

from pathlib import Path

from harness.leaf import (
    LeafSpec,
    _declared_source_files,
    _implement_artifacts,
    _self_test_artifacts,
    Escalation,
)
from harness.runner import STABLE_ARTIFACT_KEY, STABLE_COVERED_KEYS, compose_prompt


def _spec() -> LeafSpec:
    return LeafSpec(
        goal="the picker crashes when stock is empty",
        files={
            "inventory/pick.py": (
                '"""Picking helpers."""\n\n\ndef pick(stock):\n    return stock[0]\n'),
            "inventory/audit.py": (
                '"""Audit log."""\n\n\nclass Audit:\n    pass\n'),
            "README.md": "docs\n",
        },
        acs=["the picker must return the NONE sentinel"],
        interfaces=[],
        grader_paths=("README.md",),
    )


def test_stable_block_is_emitted_once_and_artifact_duplicates_are_not_rerendered():
    arts = _self_test_artifacts(_spec())
    assert STABLE_ARTIFACT_KEY in arts
    prompt = compose_prompt("write_test", arts, "write the test")
    # the stable block is present exactly once
    assert prompt.count(arts[STABLE_ARTIFACT_KEY]) == 1
    # a covered artifact key is not rendered as a second GROUND TRUTH line
    for key in STABLE_COVERED_KEYS:
        if key in arts and key != STABLE_ARTIFACT_KEY:
            assert f"\n  {key}: " not in prompt


def test_stable_block_forms_a_byte_stable_prefix_across_steps():
    spec = _spec()
    first = compose_prompt("write_test", _self_test_artifacts(spec), "write the test")
    second = compose_prompt("implement", _self_test_artifacts(spec), "fix the source")
    stable = _self_test_artifacts(spec)[STABLE_ARTIFACT_KEY]
    assert stable in first and stable in second
    # the two calls share the byte-identical prefix up to and including the stable block
    assert first.index(stable) == second.index(stable)


def test_undeclared_source_files_are_indexed_not_injected_in_full(tmp_path: Path):
    spec = _spec()
    for rel, text in spec.files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    # the plan names inventory.pick (the goal's "picker" is not a module name, so the
    # declared set is driven by an acceptance criterion that names the module)
    named = LeafSpec(goal="fix the picker", files=spec.files,
                     acs=["inventory.pick.pick must return the sentinel"],
                     interfaces=[], grader_paths=("README.md",))
    declared = _declared_source_files(named, spec.files)
    assert "inventory/pick.py" in declared
    assert "inventory/audit.py" not in declared
    arts = _implement_artifacts(named, tmp_path, Escalation("L1-resample", "sampling", False, "x"),
                                [], [], None, "M2", {})
    stable = arts[STABLE_ARTIFACT_KEY]
    assert "=== inventory/pick.py (full) ===" in stable
    # the undeclared file is a compact index row: path, line count, docstring, symbols
    assert "inventory/audit.py (5 lines) doc: Audit log." in stable
    assert "Audit@4" in stable


def test_no_declared_file_falls_back_to_the_full_view(tmp_path: Path):
    spec = _spec()
    for rel, text in spec.files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    arts = _implement_artifacts(spec, tmp_path, Escalation("L1-resample", "sampling", False, "x"),
                                [], [], None, "M2", {})
    stable = arts[STABLE_ARTIFACT_KEY]
    assert "=== inventory/pick.py (full) ===" in stable
    assert "=== inventory/audit.py (full) ===" in stable
