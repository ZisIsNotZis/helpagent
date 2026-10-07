"""Complete run telemetry — everything a run sees, emits, and does (owner direction 2026-10-06).

Owner direction: the run's trail must be kept in FULL, always — what the model was shown,
what it answered, what the model reasoned about, what the harness did with it, and what came
back. This is evidence, not a debug aid: ``T-01`` proved the gap (six refusals, a judge
diagnosis, and a delivered no-op file, with no way to read what the model had actually been
shown or had answered).

One JSONL file per run, written in order:

- ``run_start``      — task, staged source files, withheld grader paths, write-forbidden
  paths, acceptance criteria, planned tests/reviews.
- ``model_call``     — EVERY model invocation: rendered prompt, artifacts, question, raw
  response text, parsed envelope (or the schema error), tolerance normalizations, token
  counters, wall time.
- ``model_output_repaired`` — when the parse/repair respawn changed the emitted content.
- ``harness_event``  — every event the leaf emits (attempts, refusals, gates, judge/review/
  independent-test verdicts, coverage, claim decision, stops).
- ``source_write`` / ``source_write_refused``, ``test_run`` — the execution side: which
  bytes landed (sha256 + size + whether they differ from the baseline; the content itself
  rides the ``model_call`` record) and what every test command printed.
- ``delivery``       — the files handed to the grader, whether each differs from the
  pristine source, and the grader's verdict.

Design: a process-global sink list; a driver installs one writer per run
(:func:`jsonl_sink`); :func:`record` appends one JSON object per event and flushes. A sink
that raises is swallowed — evidence capture must never break a run. No dependency on the
model, the network, or the repository, so it is safe to call from anywhere.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

__all__ = ["record", "set_sink", "clear_sinks", "jsonl_sink", "active",
           "jsonable_envelope"]

_sinks: list[Callable[[dict[str, Any]], None]] = []
_seq = 0
_start = time.time()


def set_sink(sink: Callable[[dict[str, Any]], None]) -> None:
    """Install one writer. A driver calls this once per run."""
    _sinks.append(sink)


def clear_sinks() -> None:
    """Drop every writer (a driver's ``finally``)."""
    _sinks.clear()


def active() -> bool:
    """True when something is listening (lets callers skip expensive payload building)."""
    return bool(_sinks)


def _jsonable(value: Any) -> Any:
    """Best-effort JSON: paths, sets and dataclasses become strings, never an error."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except Exception:  # noqa: BLE001 - evidence must never raise
            pass
    return repr(value)


def jsonable_envelope(envelope: Any) -> Any:
    """A JSON-safe view of an envelope that NEVER raises.

    An envelope whose ``status != ok`` keeps the required-field sentinel
    (:data:`harness.envelopes.REQUIRED`) in its payload fields, and pydantic's json mode
    refuses to serialize that sentinel (``PydanticSerializationError``). Instrumentation
    runs inside the harness's own ``try`` blocks, so raising here would change control
    flow (it once consumed a whole call budget as "retries") — hence the three-step
    fallback down to ``repr``.
    """
    try:
        return envelope.model_dump(mode="json")
    except Exception:  # noqa: BLE001 - sentinel / unknown type in a non-ok envelope
        try:
            return envelope.model_dump()
        except Exception:  # noqa: BLE001 - never raise from telemetry
            return repr(envelope)


def record(kind: str, **data: Any) -> None:
    """Append one event to every installed sink. Never raises."""
    global _seq
    _seq += 1
    event = {"seq": _seq, "t": round(time.time() - _start, 4), "kind": kind}
    event.update({k: _jsonable(v) for k, v in data.items()})
    for sink in list(_sinks):
        try:
            sink(event)
        except Exception:  # noqa: BLE001 - a broken sink must not break a run
            continue


def jsonl_sink(path: Path) -> Callable[[dict[str, Any]], None]:
    """A sink that appends one JSON object per line and flushes immediately.

    Flushed per record on purpose: a run killed by a deadline still leaves everything
    written up to that point on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8")

    def _sink(event: dict[str, Any]) -> None:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        handle.flush()

    return _sink
