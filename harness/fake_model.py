"""FakeModelRunner — the deterministic scripted model runner.

Stands in for ``harness/model/runner.py`` and implements the same protocol:
``async complete(request) -> envelope-output``. The kernel's ``llm()`` primitive calls
it identically; scripts cannot tell the difference. Canned responses are keyed FIFO
per step_type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.envelopes import SCHEMAS  # noqa: F401  (re-exported for fixture authoring)

#: A spec with ``step_type=None`` inherits the key it is scripted under.
EnvelopeSpecStep = str | None


@dataclass
class EnvelopeSpec:
    """One canned response, or a built-in misbehavior."""

    step_type: EnvelopeSpecStep = None
    body: Any = None  # valid envelope payload dict OR raw_text when kind=="raw"
    kind: str = "ok"  # Literal["ok", "raw"]


@dataclass
class CallRecord:
    """What the kernel asked for, per call. ``prompt`` carries the composed prompt — erasure assertions inspect it``)."""

    step_type: str
    artifacts: dict
    question: str
    tools: list
    fresh: bool
    prompt: str


def render_prompt(record: CallRecord) -> str:
    """The composed prompt for a recorded call (erasure test surface)."""
    return record.prompt


def _spec_for(step_type: str, item: EnvelopeSpec | dict | Exception) -> EnvelopeSpec | Exception:
    if isinstance(item, EnvelopeSpec):
        if item.step_type is None:
            return EnvelopeSpec(step_type=step_type, body=item.body, kind=item.kind)
        return item
    if isinstance(item, dict):
        return EnvelopeSpec(step_type=step_type, body=item)
    return item  # Exception — raised as-is when dequeued


#: Ticket 26: the leaf's SOURCE write got its own step type (``implement_write``) so the
#: prompt no longer says "STEP: write_test" while asking for a source fix. Unit tests that
#: were written before that change script ONE interleaved write sequence under
#: ``write_test`` (the old step type for both), so the double serves both step types from
#: that single queue and records the call under BOTH names — the scripts and their
#: call-count assertions keep meaning exactly what they meant.
_SCRIPT_ALIASES = {"implement_write": "write_test"}


def _queue_key(step_type: str) -> str:
    return _SCRIPT_ALIASES.get(step_type, step_type)


class FakeModelRunner:
    """Scripted FIFO per step_type; exhausted ⇒ AssertionError (a test that expected
    more calls than the script made is itself a failure)."""

    def __init__(self, script: dict[str, list[EnvelopeSpec | dict | Exception]]) -> None:
        self._queues: dict[str, list[EnvelopeSpec | Exception]] = {
            step_type: [_spec_for(step_type, item) for item in items]
            for step_type, items in script.items()
        }
        self._calls: dict[str, list[CallRecord]] = {}
        #: Counted once per ``complete`` call (``_calls`` may hold the same record under an
        #: alias name too, so summing it would double-count).
        self._n_complete = 0

    async def complete(self, request: Any) -> dict | str:
        """Same protocol as the real model runner. Returns the raw decoded output —
        a payload dict (kind="ok") or raw text (kind="raw") — deliberately WITHOUT
        schema validation: the kernel's schema-validation invariant is what is under
        test."""
        record = CallRecord(
            step_type=request.step_type,
            artifacts=dict(request.artifacts),
            question=request.question,
            tools=list(request.tools),
            fresh=request.fresh,
            prompt=request.prompt,
        )
        self._n_complete += 1
        self._calls.setdefault(request.step_type, []).append(record)
        key = _queue_key(request.step_type)
        if key != request.step_type:
            self._calls.setdefault(key, []).append(record)
        queue = self._queues.get(key)
        if not queue:
            raise AssertionError(
                f"FakeModelRunner script exhausted for step_type={request.step_type!r} "
                f"(call #{len(self._calls[request.step_type])} beyond the scripted sequence)"
            )
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, EnvelopeSpec), f"bad scripted item for {request.step_type!r}: {item!r}"
        if item.kind == "raw":
            return item.body  # raw text — bypasses formatting for malformed cases
        return dict(item.body)

    def calls(self, step_type: str) -> list[CallRecord]:
        return list(self._calls.get(step_type, []))

    @property
    def total_calls(self) -> int:
        return self._n_complete


# ---------------------------------------------------------------------------
# Built-in misbehavior helpers
# ---------------------------------------------------------------------------


def ok_edit(path: str, content: str) -> EnvelopeSpec:
    """``implement`` envelope: whole-file edit + self-summary. DECISION: the Implement
    schema (ENVELOPE_SCHEMAS §11) carries no file contents — changes travel via the
    trajectory git snapshots — so ``content`` is deliberately not represented in the
    envelope body; the helper keeps the signature."""
    return EnvelopeSpec(body={
        "status": "ok",
        "comment": f"Edited {path}; tests run green (self-summary).",
        "tests_run": ["python -m pytest"],
    })


def unable(reason: str) -> EnvelopeSpec:
    """The grammar-enforced ``unable: reason`` alternative (DESIGN §2.2/§4.7)."""
    return EnvelopeSpec(body={
        "status": "unable",
        "comment": "Cannot proceed; reason recorded.",
        "unable_reason": reason,
    })


def malformed_json() -> EnvelopeSpec:
    """kind="raw": output truncated mid-JSON — parse fails kernel-side."""
    return EnvelopeSpec(kind="raw", body='{"status": "ok", "comment": "partial')


def schema_violation(missing: str = "self_summary") -> EnvelopeSpec:
    """Valid-JSON-shaped output missing a mandatory field (default: the mandatory
    self-summary). Works for any step_type: a status=ok envelope without payload
    fields violates every schema in the library."""
    body: dict = {"status": "ok", "comment": "attempting the step"}
    if missing == "self_summary":
        body.pop("comment")
    elif missing in body:
        body.pop(missing)
    return EnvelopeSpec(body=body)


def code_with_syntax_error() -> EnvelopeSpec:
    """Valid envelope whose string field carries broken Python (ENVELOPE_SCHEMAS §10
    WriteTest content) — caught by the post-generation parse tier (DESIGN §4.7)."""
    broken = "def test_expiry():\n    assert expires_at(61) == 'expired' :\n"
    return EnvelopeSpec(body={
        "status": "ok",
        "comment": "Wrote the test file.",
        "file_path": "tests/test_auth.py",
        "content": broken,
    })
