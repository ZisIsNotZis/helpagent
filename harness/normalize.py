"""Parameter-layer tolerance (DESIGN §4.7, owner policy 2026-09-17).

Intent-legible small errors — enum near-misses, case slips, stray whitespace —
are normalized deterministically BEFORE schema validation, so an operationally
correct answer is not discarded over a parameter slip. Two hard rules:

- **Evidence-gated registry.** An alias enters ENUM_ALIASES only with a
  reproducible run reference (same discipline as FAIL_PATTERNS) — never ad-hoc.
- **Never past the parameter layer.** A value with no deterministic mapping
  (e.g. `check_kind="REQUIRED"` — the model echoing prompt prose) is NOT
  normalized; validation rejects it and the ordinary erasure + retry path
  governs. The kernel never guesses semantics.

Every normalization fires a `tolerance_fired` ledger counter (step_type, field,
from→to): frequent fire on one field is a composer-bug signal, the same reading
as info-miss retries.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

__all__ = ["ENUM_ALIASES", "normalize_payload"]

#: field name → the schema's own Literals (ENVELOPE_SCHEMAS §0/§2/§6). Case
#: slips of a canonical value itself ("OK" → "ok") are also tolerance-foldable;
#: this table is the drift-guard reconciliation point.
ENUM_CANONICALS: dict[str, tuple[str, ...]] = {
    "status": ("ok", "failed", "blocked", "unable"),
    "check_kind": ("test", "script-assertion", "subjective"),
    "task_class": ("bugfix", "feature", "port", "scaffold", "refactor"),
}

#: field name → {model-said → canonical}. Canonical values are guarded against
#: schema drift by tests/unit/test_normalize.py (every canonical must be
#: accepted by the corresponding Literal).
ENUM_ALIASES: dict[str, dict[str, str]] = {
    # envelope status (ENVELOPE_SCHEMAS §0: every schema carries status)
    "status": {
        "success": "ok", "succeeded": "ok", "fine": "ok",
        "failure": "failed", "error": "failed", "fail": "failed",
        "block": "blocked",
    },
    # ACEntry.check_kind (ENVELOPE_SCHEMAS §6)
    "check_kind": {
        "tests": "test", "pytest": "test", "unit-test": "test", "unit_test": "test",
        "script_assertion": "script-assertion", "assertion": "script-assertion",
        "script": "script-assertion",
        "judge": "subjective", "manual": "subjective",
    },
    # TaskCard.task_class (ENVELOPE_SCHEMAS §2) — FP-5 family (case/spacing slips
    # only; the CLASS wobble itself is a routing problem, see FAIL_PATTERNS FP-5)
    "task_class": {
        "bug_fix": "bugfix", "bug-fix": "bugfix", "bug": "bugfix",
        "add-feature": "feature", "add_feature": "feature", "new-feature": "feature",
    },
}


def _iter_dicts(node: Any) -> Iterator[dict]:
    """Yield every dict in the payload tree (envelopes are small; recursion is
    bounded by pydantic-level size caps downstream)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_dicts(v)


def normalize_payload(payload: Any) -> tuple[Any, list[dict]]:
    """Apply the parameter-layer tolerance. Returns (normalized_payload, notes)
    where each note is {field, from, to} (the caller adds step_type and ledgers
    it as `tolerance_fired`). Non-dict payloads pass through untouched."""
    notes: list[dict] = []
    if not isinstance(payload, dict):
        return payload, notes
    for d in _iter_dicts(payload):
        for field_name, aliases in ENUM_ALIASES.items():
            raw = d.get(field_name)
            if not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if candidate != raw:
                d[field_name] = candidate
                notes.append({"field": field_name, "from": raw, "to": candidate})
                raw = candidate
            lowered = candidate.lower()
            if lowered in aliases:
                canonical = aliases[lowered]
            elif lowered in ENUM_CANONICALS.get(field_name, ()):
                canonical = lowered   # canonical value with a case slip ("OK" → "ok")
            else:
                continue              # unmapped ⇒ NOT guessed; validation rejects
            if candidate != canonical:
                d[field_name] = canonical
                notes.append({"field": field_name, "from": candidate, "to": canonical})
    return payload, notes
