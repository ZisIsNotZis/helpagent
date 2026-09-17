"""Minimal runner glue: the script-facing ``llm_step`` (KERNEL_API §3.1) plus the
deterministic prompt composer used by the erasure tests (DESIGN §2.4).

Scope tonight: schema validation of model output against the envelope library, the
``SchemaViolation`` path (recorded, then raised), a minimal append-only ledger, and
``compose_prompt``. The llama.cpp transport, grammar decoding, bounded re-ask, and
the full ledger/stats subsystem are later milestones (DESIGN §8 M1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from harness.envelopes import JUDGE_STEP_PREFIX, SCHEMAS, Envelope
from harness.normalize import normalize_payload

# Step types whose envelope validators consume a validation context (ENVELOPE_SCHEMAS
# §4/§6/§7/§9/§10: seam candidates + grounding, node_kind, boundary subset, ac_id ∈ map).
# Without a context those reference checks silently skip — legal for tests, a silent-off
# gate in a run. llm_step records the skip in the append-only ledger; M1's real runner
# must inject the context for these step types on every call.
CONTEXT_SENSITIVE_STEPS = frozenset({"expand", "draft_acs", "write_spec", "test_plan", "write_test"})

# Code-carrying steps: the envelope content is a whole file and goes through the
# tree-sitter parse-on-arrival + bounded repair respawn (DESIGN §4.7, harness/repair.py).
# write_test is the only content-emitting schema left (ENVELOPE_SCHEMAS §23).
CONTENT_STEPS = frozenset({"write_test"})

# ---------------------------------------------------------------------------
# Byte-stable prefix — scaffold + static standing knowledge only (DESIGN §2.7).
# ---------------------------------------------------------------------------

PREFIX = """\
You are the step executor inside the helpagent harness.
Return exactly ONE envelope as JSON for the requested step.
Every envelope has: status (ok|failed|blocked|unable), comment (self-summary, max 2 lines),
unable_reason (required iff status==unable). Payload fields appear only when status!=unable.
Do not invent ids, files, or symbols that were not injected below."""


@dataclass
class LLMRequest:
    """The composed request handed to the model runner (KERNEL_API §3.1)."""

    step_type: str
    artifacts: dict[str, str]
    question: str
    tools: list[str]
    fresh: bool
    prompt: str


@dataclass
class FailureSummary:
    """Honest failure summary of a prior round — the ONLY thing a retry sees of it
    (DESIGN §2.4 erasure: never the failed attempt's text)."""

    step_type: str
    summary: str
    missing: list[str] = field(default_factory=list)


class SchemaViolation(Exception):
    """Model output failed schema validation after recording (KERNEL_API §3.1)."""


# ---------------------------------------------------------------------------
# Minimal ledger stand-in — append-only; entries are stats/evidence, never injected
# into model context (DESIGN §2.4b, KERNEL_API §4.5). Full ledger is a later milestone.
# DECISION: module-level append-only list with note/entries only — no delete/edit API
# exists, which is the invariant TEST_PLAN §3.4 pins ("Ledger exposes append/query only").
# ---------------------------------------------------------------------------

_LEDGER: list[dict[str, Any]] = []


def note(kind: str, text: str = "", **fields: Any) -> None:
    """Append a typed event to the ledger (KERNEL_API §4.5 ledger.note)."""
    entry: dict[str, Any] = {"kind": kind, "text": text, **fields}
    _LEDGER.append(entry)


def ledger_entries() -> tuple[dict[str, Any], ...]:
    """Query-only read view over the append-only ledger."""
    return tuple(_LEDGER)


def reset_ledger_for_tests() -> None:
    """Test isolation helper — the ledger itself never deletes during a run."""
    _LEDGER.clear()


# ---------------------------------------------------------------------------
# Composition (deterministic; pure function of its arguments)
# ---------------------------------------------------------------------------


def compose_prompt(
    step_type: str,
    artifacts: dict[str, str],
    question: str,
    fresh: bool = False,
    failure: FailureSummary | None = None,
    role: str | None = None,
) -> str:
    """Byte-stable prefix + step suffix (DESIGN §4.3).

    ``fresh=True`` composes without author-context artifacts (KERNEL_API §3.1:
    reviewers, judges). DECISION: we cannot distinguish author-context artifacts from
    evidence within the artifacts dict, so a fresh session omits the artifacts block
    entirely; whatever the decider must see is injected through the question as
    ground truth.

    ``failure`` injects the honest failure summary + missing info — never the failed
    attempt's text (DESIGN §2.4a; KERNEL_API §3.3 compose(failure=...)).
    """
    parts: list[str] = [PREFIX]
    if step_type in CONTENT_STEPS:
        # FAIL_PATTERN (ticket 02): the 4B strips docstring quotes / wraps files in fences
        # when re-emitting a file seen in the artifacts. Weak phrasing does not survive
        # temp 0.2; the M0 runner's hard-rules block went 8/8 on the same model+file —
        # adopt it verbatim (byte-stable prefix stays stable for KV cache).
        parts.append(
            "Hard rules for the content field:\n"
            "- \"content\" REPLACES the whole file byte-for-byte. Include every line of "
            "the file: module docstring, imports, and all. Never truncate, never write "
            "\"...\" or placeholders, never wrap the content in markdown fences.\n"
            "- Change as little as possible: fix what the step asks and keep everything "
            "else exactly as it is. Do not restyle, rename, or reformat unrelated code.\n"
            "- Do not change the public API: keep function and class names, signatures, "
            "and module layout unchanged.\n"
            "- \"status\" describes YOUR edit, never the test results: \"ok\" = you are "
            "returning the complete new file as instructed, even if other tests still fail. "
            "Do not set \"failed\" just because the tests currently fail.")
    parts.append(f"STEP: {step_type}")
    if role:
        parts.append(f"ROLE: {role}")
    if fresh:
        parts.append("SESSION: fresh reviewer — no author-context artifacts are injected; "
                     "judge only from the evidence stated in the question.")
    elif artifacts:
        parts.append("GROUND TRUTH (injected artifacts):")
        for key in sorted(artifacts):
            parts.append(f"  {key}: {artifacts[key]}")
    parts.append(f"QUESTION: {question}")
    if failure is not None:
        parts.append("PRIOR ROUND FAILED — failure summary only (failed attempt's text erased, DESIGN §2.4):")
        parts.append(f"  step: {failure.step_type}")
        parts.append(f"  summary: {failure.summary}")
        if failure.missing:
            parts.append(f"  missing info: {'; '.join(failure.missing)}")
    parts.append("Respond with the one envelope for this step.")
    return "\n".join(parts)


def schema_for_step(step_type: str) -> type[Envelope]:
    """Registry lookup. Unknown step_type is a programmer error → immediate raise
    (KERNEL_API §3). ``judge_<aspect>`` step types resolve to the generic JudgeAspect
    entry; the per-run aspect enum is bound at decode time (ENVELOPE_SCHEMAS §18)."""
    if step_type in SCHEMAS:
        return SCHEMAS[step_type]
    if step_type.startswith(JUDGE_STEP_PREFIX):
        return SCHEMAS["judge_aspect"]
    raise KeyError(f"unknown step_type: {step_type!r}")


async def llm_step(
    model: Any,
    step_type: str,
    artifacts: dict[str, str],
    question: str,
    tools: list[str] | None = None,
    fresh: bool = False,
    failure: FailureSummary | None = None,
    context: dict[str, Any] | None = None,
    best_of_n: int = 1,
    repair: bool = True,
    role: str | None = None,
) -> Envelope:
    """One model invocation: compose → complete → validate → envelope.

    ``failure=`` carries the prior round's FailureSummary (erasure: only the summary
    is rendered, never the failed attempt's text). ``context=`` is the validation
    context for the "grammar enum per call" reference checks (seam_id ∈ candidates,
    ac_id ∈ map, files_touched ⊆ boundary) — the caller (script) injects it.

    ``best_of_n>1`` samples N candidates and the deterministic checker (schema
    validation) selects the first valid one (DESIGN §4.7). Each candidate is one
    model call and gets its own ``llm_invocation`` ledger note with token/cache
    counters (KERNEL_API §5 — counters only, never content).

    For CONTENT_STEPS the envelope content additionally goes through the tree-sitter
    parse-on-arrival + bounded repair respawn (DESIGN §4.7, harness/repair.py).
    ``repair=False`` marks a respawn — a respawn never recurses into repair, which is
    what makes §4.7's "ONE bounded respawn" structural rather than counter-based.

    DECISION (KERNEL_API §3.1 "SchemaViolation ... after bounded re-ask"): the bounded
    re-ask loop for schema violations is kernel retry machinery from a later milestone;
    tonight the glue records the violation in the ledger and raises immediately (the
    §4.7 repair respawn for parse failures is the one wired exception).
    """
    schema = schema_for_step(step_type)
    if step_type in CONTEXT_SENSITIVE_STEPS and context is None:
        note("validation_context_missing", step_type=step_type)
    prompt = compose_prompt(step_type, artifacts, question, fresh=fresh, failure=failure, role=role)
    request = LLMRequest(
        step_type=step_type,
        artifacts={k: str(v) for k, v in (artifacts or {}).items()},
        question=question,
        tools=list(tools or []),
        fresh=fresh,
        prompt=prompt,
    )
    best_of_n = max(1, int(best_of_n))

    async def _candidates() -> Any:
        """Real runners expose complete_n (batch); scripted fakes are fetched lazily
        so a valid first candidate costs one call. DECISION: asymmetry is safe — the
        selection rule (first valid) is identical on both sides."""
        if best_of_n > 1 and hasattr(model, "complete_n"):
            for out in await model.complete_n(request, best_of_n):
                yield out
        else:
            for _ in range(best_of_n):
                yield await model.complete(request)

    envelope: Envelope | None = None
    fallback: Envelope | None = None   # last schema-valid candidate whose content failed parse
    failure_message: str | None = None
    async for out in _candidates():
        metrics = getattr(model, "last_metrics", None)
        note(
            "llm_invocation",
            step_type=step_type,
            fresh=fresh,
            cache_hit=(metrics or {}).get("cache_hit"),
            prompt_tokens=(metrics or {}).get("prompt_tokens"),
            completion_tokens=(metrics or {}).get("completion_tokens"),
        )
        if isinstance(out, str):
            try:
                payload: Any = json.loads(out)
            except json.JSONDecodeError as exc:
                note("validation_failed", step_type=step_type, detail=f"malformed JSON at offset {exc.pos}")
                failure_message = (
                    f"{step_type}: output was malformed JSON — attempt erased, failure summary only"
                )
                continue
        else:
            payload = out
        # parameter-layer tolerance (DESIGN §4.7, owner policy 2026-09-17):
        # deterministic near-miss normalization BEFORE validation; every fire is a
        # first-class counter (frequent fire on one field = composer-bug signal)
        payload, tolerance_notes = normalize_payload(payload)
        for tn in tolerance_notes:
            note("tolerance_fired", step_type=step_type, **tn)
        try:
            envelope = schema.model_validate(payload, context=context)
            if (
                best_of_n > 1
                and step_type in CONTENT_STEPS
                and isinstance(getattr(envelope, "content", None), str)
            ):
                # DESIGN §4.7: the deterministic checker selects. For content steps, schema
                # validity alone is too weak a filter — a candidate echoing the artifact
                # block passes the grammar but can never run. Prefer the first candidate
                # that both validates AND parses; if none parses, fall through to the
                # repair path with the last schema-valid one (bounded respawn preserved).
                from harness.repair import parse_python  # lazy: repair imports runner

                ok, _node = parse_python(envelope.content)
                if not ok:
                    note("candidate_unparseable", step_type=step_type)
                    fallback, envelope = envelope, None
                    continue
            break
        except ValidationError as exc:
            # the full pydantic detail (incl. offending values) is ledger evidence —
            # append-only, never injected into a later prompt (DESIGN §2.4b)
            note("validation_failed", step_type=step_type, detail=str(exc))
            first_msg = exc.errors()[0]["msg"] if exc.errors() else "invalid envelope"
            failure_message = (
                f"{step_type}: schema violation: {first_msg} — attempt erased, failure summary only"
            )
    if envelope is None:
        if fallback is not None:
            envelope = fallback   # nothing parsed — the repair path still gets its one respawn
        else:
            raise SchemaViolation(failure_message or f"{step_type}: no candidates produced")

    if repair and envelope.status == "ok" and step_type in CONTENT_STEPS:
        from harness.repair import repair_code  # lazy: repair imports runner.llm_step

        repaired = await repair_code(envelope.content, model, step_type, question,
                                     context=context,
                                     ground_truth={k: str(v) for k, v in (artifacts or {}).items()})
        if repaired != envelope.content:
            envelope.content = repaired

    note("step_completed", step_type=step_type)
    return envelope
