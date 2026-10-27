"""Parameter-layer tolerance (docs/6_ARCHITECTURE.md §4.7, owner policy 2026-09-17).

Pin the contract: intent-legible near-misses (case slips, known aliases) are
normalized deterministically before validation with a ledger counter; unknown
values are NOT guessed — validation rejects and erasure+retry governs; the
alias registry stays schema-drift-guarded.
"""

from harness.envelopes import DraftACs
from harness.fake_model import EnvelopeSpec, FakeModelRunner
import asyncio

from harness.normalize import ENUM_ALIASES, normalize_payload
from harness.runner import (
    ledger_entries,
    llm_step,
    reset_ledger_for_tests,
    schema_for_step,
)
from harness.tree import ACEntry


def test_status_near_miss_is_folded_with_note():
    payload = {"status": "OK", "comment": "c"}
    out, notes = normalize_payload(payload)
    assert out["status"] == "ok"
    assert notes == [{"field": "status", "from": "OK", "to": "ok"}]


def test_check_kind_alias_and_case_fold():
    out, notes = normalize_payload({"check_kind": " Pytest "})
    assert out["check_kind"] == "test"
    assert [n["to"] for n in notes] == ["Pytest", "test"]   # whitespace then alias


def test_unknown_enum_value_is_never_guessed():
    """'REQUIRED' is the model echoing prompt prose (seen in run 20260917T063255,
    T-01) — no deterministic mapping ⇒ untouched; validation must still reject."""
    out, notes = normalize_payload({"check_kind": "REQUIRED"})
    assert out["check_kind"] == "REQUIRED" and notes == []
    try:
        ACEntry(ac_id="AC-1", statement="s", check_kind="REQUIRED")
        raise AssertionError("validation must reject an unmapped enum value")
    except Exception:
        pass


def test_valid_payload_is_untouched():
    payload = {"status": "ok", "comment": "c", "nested": {"check_kind": "subjective"}}
    out, notes = normalize_payload(payload)
    assert out == payload and notes == []


def test_nested_containers_are_reached():
    payload = {"acs": [{"ac_id": "AC-1", "statement": "s", "check_kind": "TESTS"}]}
    out, notes = normalize_payload(payload)
    assert out["acs"][0]["check_kind"] == "test" and notes


def test_alias_registry_is_schema_drift_guarded():
    """Canonicals must point into the schema Literals (docs/7_ENVELOPES.md §0/§2/§6).
    If a schema enum changes, this set is the reconciliation point."""
    from harness.normalize import ENUM_CANONICALS

    assert set(ENUM_CANONICALS["status"]) == {"ok", "failed", "blocked", "unable"}
    assert set(ENUM_CANONICALS["check_kind"]) == {"test", "script-assertion", "subjective"}
    assert set(ENUM_CANONICALS["task_class"]) == {
        "bugfix", "feature", "port", "scaffold", "refactor"}
    assert set(ENUM_ALIASES["status"].values()) <= set(ENUM_CANONICALS["status"])
    assert set(ENUM_ALIASES["check_kind"].values()) <= set(ENUM_CANONICALS["check_kind"])
    assert set(ENUM_ALIASES["task_class"].values()) <= set(ENUM_CANONICALS["task_class"])


def test_non_dict_payload_passes_through():
    out, notes = normalize_payload("raw text")
    assert out == "raw text" and notes == []


def test_end_to_end_tolerance_fires_in_llm_step():
    """The kernel path: a near-miss envelope from the (fake) model validates and
    the counter lands in the ledger — an operationally correct answer is not
    discarded over a parameter slip."""
    reset_ledger_for_tests()
    body = {"status": "OK", "comment": "near-miss tolerance",
            "acs": [{"ac_id": "AC-1", "statement": "s", "check_kind": "PYTEST"}]}
    fake = FakeModelRunner({"draft_acs": [EnvelopeSpec(step_type="draft_acs", body=body)]})
    env = asyncio.run(llm_step(fake, "draft_acs", {}, "q", context={"node_kind": "leaf"}))
    assert isinstance(env, DraftACs) and env.acs[0].check_kind == "test"
    kinds = [e["kind"] for e in ledger_entries()]
    assert "tolerance_fired" in kinds


def test_single_expand_seam_is_deterministically_filled():
    reset_ledger_for_tests()
    body = {"status": "ok", "comment": "split", "children": [
        {"what": "fix", "why": "bug", "leaf": True, "est_rounds": 1}]}
    fake = FakeModelRunner({"expand": [EnvelopeSpec(step_type="expand", body=body)]})
    env = asyncio.run(llm_step(fake, "expand", {}, "q", context={
        "candidate_seams": {"seam-primary": ["a.py"]}, "grounding_files": {"a.py"}}))
    assert env.children[0].seam_id == "seam-primary"
    assert any(e["kind"] == "tolerance_fired" and e["field"] == "children.seam_id"
               for e in ledger_entries())


def test_missing_seam_is_not_guessed_when_candidates_ambiguous():
    from harness.runner import SchemaViolation
    import pytest

    reset_ledger_for_tests()
    body = {"status": "ok", "comment": "split", "children": [
        {"what": "fix", "why": "bug", "leaf": True, "est_rounds": 1}]}
    fake = FakeModelRunner({"expand": [EnvelopeSpec(step_type="expand", body=body)]})
    with pytest.raises(SchemaViolation, match="child fill requires fields"):
        asyncio.run(llm_step(fake, "expand", {}, "q", context={
            "candidate_seams": {"a": ["a.py"], "b": ["b.py"]}}))
    assert not any(e["kind"] == "tolerance_fired" for e in ledger_entries())


def test_schema_registry_still_resolves():
    assert schema_for_step("draft_acs").__name__ == "DraftACs"
