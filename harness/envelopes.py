"""Grammar-target output contracts for every ``llm_step`` (ENVELOPE_SCHEMAS.md §0–§23).

Every model invocation returns exactly one envelope; schemas are *selected* by the
harness, never authored by the model (DESIGN §4.2). This module is the pydantic v2
form of the grammar: enums, patterns, list caps, and the conditional pairs the doc
marks "grammar-enforced".

The §0 grammar branches on ``status`` with one alternative each: the ``ok`` branch
requires the payload fields, the ``unable`` branch requires ``unable_reason`` and
forbids payload fields. Faithful translation: payload fields carry the ``REQUIRED``
sentinel default (absent ⇒ parse succeeds) and :meth:`Envelope._grammar_branch`
enforces presence on the ok branch / absence on the unable branch.

Reference checks that need run-time context (``seam_id`` ∈ injected candidates,
``ac_id`` ∈ the leaf's AC map, ``files_touched`` ⊆ boundary, child grounding, leaf-map
mandatory) run only when a ``context`` dict is passed to ``model_validate`` — the doc's
"grammar enum per call". Without a context they are skipped (the real runner binds them
at decode time via the generated grammar).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Literal, Self, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class _Missing:
    """Sentinel for 'payload field required on the ok branch' (§0 grammar branch)."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "REQUIRED"


REQUIRED = _Missing()


def req(**kwargs: object) -> Any:  # returns a pydantic FieldInfo with the sentinel default
    """Field with the REQUIRED sentinel default + the doc's bounds."""
    return Field(default=REQUIRED, **kwargs)  # type: ignore[call-overload]


#: Deterministic stopword list for Lesson topic keys (ENVELOPE_SCHEMAS §22 "no
#: stopwords (deterministic)"; DESIGN §4.4 "term sanity: 1–6 normalized terms, no
#: stopwords"). Minimal closed set; matcher is exact-term presence until measured.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "of", "to",
        "in", "on", "for", "with", "at", "by", "from", "as", "is", "are", "was", "were",
        "be", "been", "it", "its", "this", "that", "these", "those", "not", "no", "do",
        "does", "did", "can", "cannot", "could", "should", "would", "will", "shall",
        "may", "might", "must", "you", "your", "we", "our",
    }
)

_TOPIC_TERM = re.compile(r"^[a-z0-9_-]+$")
#: File-path-shaped tokens inside free strings — used by the grounding check on
#: ``expand`` children (ENVELOPE_SCHEMAS §4: "any file path or symbol they name must
#: appear in the injected candidate scope or the symbol DB").
_FILE_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9_]+")


def file_tokens(text: str) -> set[str]:
    """Path-shaped tokens in free text (the grounding validator's own tokenizer,
    exposed for composers: request-named files enter the grounding scope, FP-10)."""
    return set(_FILE_TOKEN.findall(text or ""))


def _candidate_files(ctx: dict) -> set[str]:
    """Union of injected candidate-cut file scopes (ENVELOPE_SCHEMAS §4: each cut
    carries ``{seam_id, files, rationale}``)."""
    files: set[str] = set(ctx.get("grounding_files") or ())
    seams = ctx.get("candidate_seams")
    if seams:
        for scope in seams.values():
            if isinstance(scope, dict):
                files.update(scope.get("files") or ())
            elif isinstance(scope, (list, tuple, set)):
                files.update(scope)
    return files


class NestedModel(BaseModel):
    """Base for the NESTED payload models (children of an envelope, §0).

    Nested models do NOT inherit :class:`Envelope`'s REQUIRED-sentinel grammar guard, and
    pydantic does not enforce presence for a field whose default IS the sentinel (the
    default satisfies pydantic's own required check). So a payload that omits a :func:`req`
    field validates, leaves the sentinel in place, and the sentinel later reaches harness
    code and crashes the whole run (ticket 20 step 2b-iii: a ``ChildPlan`` without ``what``
    reached :func:`harness.node.decomposition_signature` and killed three of six live runs).
    This base makes every nested model reject a missing REQUIRED field at DECODE time, so
    the kernel's bounded repair re-asks the model instead of losing the run.
    """

    model_config = ConfigDict(extra="forbid")

    #: Label used in the schema-violation message; defaults to the class name. Set it on a
    #: subclass to keep a historical message stable (e.g. "child fill").
    _missing_label: ClassVar[str] = ""

    @model_validator(mode="after")
    def _all_required_fields_present(self) -> Self:
        missing = sorted(
            name for name in type(self).model_fields
            if getattr(self, name, None) is REQUIRED
        )
        if missing:
            label = type(self)._missing_label or type(self).__name__
            raise ValueError(
                f"{label} requires fields: {missing} (ENVELOPE_SCHEMAS §0)")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """Keep the GENERATED GRAMMAR in step with the runtime guard (ENVELOPE_SCHEMAS §0).

        A :func:`req` field's DEFAULT is the sentinel, so pydantic does not list it as
        ``required`` in the JSON schema. The server's constrained-decoding grammar is
        generated from that schema, so it treated those fields as OPTIONAL and the model
        omitted them — the sentinel then reached harness code and crashed the run. Marking
        every sentinel field ``required`` makes the decode grammar demand exactly what the
        runtime guard enforces (ticket 20 step 2b-iii).
        """
        json_schema = handler(core_schema)
        required = list(json_schema.get("required", []))
        for name, info in cls.model_fields.items():
            if info.default is REQUIRED and name not in required:
                required.append(name)
        if required:
            json_schema["required"] = sorted(required)
        return json_schema


class Envelope(BaseModel):
    """Base conventions, fixed for every envelope (ENVELOPE_SCHEMAS §0).

    ``comment`` is the mandatory self-summary field (DESIGN §4.2) — presence is
    enforced; the "≤2 lines" prose limit stays a form/rendering concern, not a bound.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "failed", "blocked", "unable"]
    comment: str = Field(min_length=1)
    unable_reason: str | None = None

    @field_validator("unable_reason")
    @classmethod
    def _reason_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("unable_reason must be non-empty when present")
        return v

    @model_validator(mode="after")
    def _grammar_branch(self) -> Self:
        """ENVELOPE_SCHEMAS §0: the grammar branches on status — the ok branch requires
        the payload fields; the unable branch requires ``unable_reason`` and forbids
        payload fields (one grammar alternative each)."""
        base = {"status", "comment", "unable_reason"}
        if self.status == "unable":
            payload = set(self.model_fields_set) - base
            if payload:
                raise ValueError(
                    f"unable branch forbids payload fields (ENVELOPE_SCHEMAS §0): {sorted(payload)}"
                )
            if not (self.unable_reason and self.unable_reason.strip()):
                raise ValueError("unable_reason REQUIRED iff status=='unable' (ENVELOPE_SCHEMAS §0)")
        else:
            if self.unable_reason is not None:
                raise ValueError("unable_reason is forbidden unless status=='unable' (REQUIRED iff unable)")
            missing = sorted(
                name for name in type(self).model_fields
                if name not in base and getattr(self, name, None) is REQUIRED
            )
            if missing:
                raise ValueError(
                    f"payload fields are required unless status=='unable' (ENVELOPE_SCHEMAS §0 ok-branch): "
                    f"{missing}"
                )
        return self

    @classmethod
    def _unset(cls, obj: object) -> bool:
        """True when a payload field is absent (unable branch / missing on ok branch)."""
        return obj is REQUIRED


# ---------------------------------------------------------------------------
# §1 task_card
# ---------------------------------------------------------------------------


class TaskCard(Envelope):
    task_class: Literal["bugfix", "feature", "port", "scaffold", "refactor"] = req()
    goal: str = req(min_length=1)  # kernel validates non-empty goal (§1)


# ---------------------------------------------------------------------------
# §2 find_ambiguities
# ---------------------------------------------------------------------------


class Ambiguity(NestedModel):

    kind: Literal["needs-user", "self-answerable"] = req()
    topic: Literal["requirement", "domain", "environment", "conflict"] = req()
    question: str = req(min_length=1)


class FindAmbiguities(Envelope):
    items: list[Ambiguity] = req(max_length=5)  # 0–5 items (§2)


#: Alias for the same schema (task shorthand); the doc's class name is FindAmbiguities.
Ambiguities = FindAmbiguities


# ---------------------------------------------------------------------------
# §3 revise_task_card
# ---------------------------------------------------------------------------


class ReviseTaskCard(Envelope):
    changed: list[Literal["goal", "task_class"]] = req(min_length=1)
    card: TaskCard = req()  # full revised payload, re-validated like §1
    because: str = req(min_length=1)


# ---------------------------------------------------------------------------
# §4 expand
# ---------------------------------------------------------------------------


class ChildFill(NestedModel):
    _missing_label = "child fill"

    seam_id: str = req(min_length=1)
    what: str = req(min_length=1)
    why: str = req(min_length=1)
    leaf: bool = req()
    est_rounds: int = req(ge=1, le=10)  # drives per-step budget = estimate × 1.5 (§4)

    @field_validator("seam_id")
    @classmethod
    def _seam_in_candidates(cls, v: str, info: ValidationInfo) -> str:
        """§4: seam_id MUST be one of the injected candidate_cuts ids — grammar enum
        per call. Enforced only when the candidate set is injected at validation time
        (not stored on the model)."""
        candidates = (info.context or {}).get("candidate_seams")
        if candidates is not None and v not in candidates:
            raise ValueError(f"seam_id {v!r} is not among the injected candidate cuts (ENVELOPE_SCHEMAS §4)")
        return v

    @field_validator("what", "why")
    @classmethod
    def _grounded_references(cls, v: str, info: ValidationInfo) -> str:
        """§4 enum-first applied to the two free strings: any file path named in
        ``what``/``why`` must appear in the injected candidate scope or the symbol DB,
        else the child is rejected as ungrounded. Symbol-level grounding is left to
        split_review per §4 ("Behaviors stay free text"); this check covers file tokens
        deterministically. Runs only when a grounding context is injected."""
        ctx = info.context or {}
        if not ("candidate_seams" in ctx or "grounding_files" in ctx or "known_symbols" in ctx):
            return v
        allowed = _candidate_files(ctx) | set(ctx.get("known_symbols") or ())
        for tok in _FILE_TOKEN.findall(v or ""):
            # abbreviations like "e.g" / "i.e" match the token shape but are prose,
            # not file references (owner finding, T-07 false positive)
            if tok.lower().rstrip(".") in {"e.g", "i.e", "etc", "vs", "fig", "no", "cf"}:
                continue
            # numeric literals ("4.5", "1.2.3") match the token shape but are values,
            # not file references (owner-run false positive, T-20 / FP-10)
            if re.fullmatch(r"\d+(?:\.\d+)+", tok):
                continue
            if tok not in allowed:
                raise ValueError(
                    f"ungrounded reference {tok!r}: not in injected candidate scope or symbol DB "
                    "(ENVELOPE_SCHEMAS §4)"
                )
        return v


class Expand(Envelope):
    # 1–15 children per layer (§4: taxonomy default is 5–15; per-class config, not a
    # bound — a small seam list legitimately yields fewer, hence 1 as the hard floor).
    children: list[ChildFill] = req(min_length=1, max_length=15)


# ---------------------------------------------------------------------------
# §5 split_review
# ---------------------------------------------------------------------------


class SplitIssue(NestedModel):

    kind: Literal["overlap", "missing-piece", "wrong-seam", "too-big", "unclear-ac"] = req()
    target: str = req(min_length=1)  # child id or "parent" — kernel resolves post-hoc (§24)
    description: str = req(min_length=1)


class SplitReview(Envelope):
    ok: bool = req()
    issues: list[SplitIssue] = req(max_length=5)  # 0–5

    @model_validator(mode="after")
    def _ok_implies_no_issues(self) -> Self:
        # §5: ok==True ⇒ issues==[] (grammar-enforced pair). The converse (ok==False
        # with empty issues) is not forbidden by the doc — a reviewer may report
        # failure without structured findings.
        if self._unset(self.ok) or self._unset(self.issues):
            return self  # unable branch: payload absent
        if self.ok and self.issues:
            raise ValueError("SplitReview ok==True requires issues==[] (ENVELOPE_SCHEMAS §5)")
        return self


# ---------------------------------------------------------------------------
# §6 draft_acs
# ---------------------------------------------------------------------------


class DraftAC(NestedModel):

    ac_id: str = req(pattern=r"^AC-[0-9]{1,3}$")
    statement: str = req(min_length=1)
    check_kind: Literal["test", "script-assertion", "subjective"] = req()
    check_hint: str | None = None

    @model_validator(mode="after")
    def _subjective_needs_hint(self) -> Self:
        # §6: subjective entries must carry check_hint (feeds the judge panel).
        if self.check_kind == "subjective" and not (self.check_hint or "").strip():
            raise ValueError("check_kind=='subjective' requires check_hint (ENVELOPE_SCHEMAS §6)")
        return self


class DraftACs(Envelope):
    # 0–10; EMPTY LIST = "this node has no map" — valid only for an internal node.
    # A LEAF returning empty is invalid (leaf maps are mandatory, §6) — enforced when
    # the validation context carries node_kind.
    acs: list[DraftAC] = req(max_length=10)

    @field_validator("acs")
    @classmethod
    def _leaf_map_mandatory(cls, v: list[DraftAC], info: ValidationInfo) -> list[DraftAC]:
        node_kind = (info.context or {}).get("node_kind")
        if node_kind == "leaf" and not v:
            raise ValueError("a leaf's AC map is mandatory; empty list is only valid for internal nodes "
                             "(ENVELOPE_SCHEMAS §6)")
        return v

    @model_validator(mode="after")
    def _unique_ac_ids(self) -> Self:
        if self._unset(self.acs):
            return self  # unable branch: payload absent
        ids = [a.ac_id for a in self.acs]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate ac_id entries (§6 ids unique): {dupes}")
        return self


# ---------------------------------------------------------------------------
# §7 write_spec
# ---------------------------------------------------------------------------


class Interface(NestedModel):

    name: str = req(min_length=1)  # LSP-checked against injected ground truth (kernel post-hoc, §24)
    signature: str = req(min_length=1)
    contract: str = req(min_length=1)


class WriteSpec(Envelope):
    interfaces: list[Interface] = req(max_length=8)  # 0–8
    behavior: str = req(min_length=1)  # the SHARED CONTRACT — routed to both sides
    implementation_notes: str = req(min_length=1)  # IMPLEMENTER-ONLY
    files_touched: list[str] = req(max_length=10)  # 0–10 paths — NARROWING of the leaf boundary

    @field_validator("files_touched")
    @classmethod
    def _within_boundary(cls, v: list[str], info: ValidationInfo) -> list[str]:
        """§7: files_touched ⊆ seam file scope (narrowing only). Enforced when the
        leaf boundary is injected at validation time."""
        boundary = (info.context or {}).get("boundary_files")
        if boundary is not None:
            outside = [p for p in v if p not in boundary]
            if outside:
                raise ValueError(f"files_touched must narrow the leaf boundary; outside it: {outside}")
        return v


# ---------------------------------------------------------------------------
# §8 spec_review
# ---------------------------------------------------------------------------


class SpecIssue(NestedModel):

    severity: Literal["blocking", "minor"] = req()
    location: str = req(min_length=1)  # kernel resolves post-hoc (§24)
    description: str = req(min_length=1)


class SpecReview(Envelope):
    ok: bool = req()
    issues: list[SpecIssue] = req(max_length=6)  # 0–6; ok==True ⇒ issues==[]

    @model_validator(mode="after")
    def _ok_implies_no_issues(self) -> Self:
        if self._unset(self.ok) or self._unset(self.issues):
            return self  # unable branch: payload absent
        if self.ok and self.issues:
            raise ValueError("SpecReview ok==True requires issues==[] (ENVELOPE_SCHEMAS §8)")
        return self


# ---------------------------------------------------------------------------
# §9 test_plan
# ---------------------------------------------------------------------------


class TestCase(NestedModel):

    case_id: str = req(pattern=r"^TC-[0-9]{1,3}$")
    ac_id: str = req(min_length=1)
    kind: Literal["unit", "api", "e2e", "script"] = req()
    description: str = req(min_length=1)

    @field_validator("ac_id")
    @classmethod
    def _ac_in_map(cls, v: str, info: ValidationInfo) -> str:
        """§9: ac_id MUST exist in the leaf's AC test map — grammar enum per call.
        Coverage of every ac_id ("every ac_id covered at least once") is the script's
        queue_test_writing concern, not a schema bound."""
        ac_map = (info.context or {}).get("ac_map")
        if ac_map is not None and v not in ac_map:
            raise ValueError(f"ac_id {v!r} not present in the leaf's AC test map (ENVELOPE_SCHEMAS §9)")
        return v


class TestPlan(Envelope):
    # DECISION: the doc states no list cap for cases (§9; §23 quotes "~600 tok at 12
    # cases" — a budget note, not a bound). Only the TC-id pattern bounds the space.
    cases: list[TestCase] = req()


# ---------------------------------------------------------------------------
# §10 write_test
# ---------------------------------------------------------------------------


class WriteTest(Envelope):
    file_path: str = req(min_length=1)  # path scope: kernel post-hoc (§24)
    content: str = req(min_length=1)  # complete file — whole-file, never diffs (§10)


class FileContent(NestedModel):
    file_path: str = req(min_length=1)
    content: str = req(min_length=1)


class ImplementWrite(Envelope):
    """§11b: the leaf's SOURCE write — the complete new content of the files to change.

    Ticket 26 (owner direction 2026-10-06). Two defects this replaces:

    1. the leaf used to issue this step as ``write_test`` (the self-test schema), so the
       prompt read "STEP: write_test" while asking for a source fix; it now has its own
       step type and its own schema;
    2. it carried exactly ONE file, and the question said so ("Emit the complete new
       content of ONE implementation file"), which is false for a multi-site fix such as
       T-31 (four call sites) — the run could never land two files in one revision.
       ``files`` accepts up to 10, bounded by the leaf write boundary the caller injects.

    Parameter-layer tolerance (owner policy): a well-formed single-file answer
    (``file_path`` + ``content``) is the same intent as a one-element ``files`` list, so it
    is promoted rather than refused — the field is a parameter, the intent is not.
    """

    files: list[FileContent] = req(min_length=1, max_length=10)

    @model_validator(mode="before")
    @classmethod
    def _accept_single_file(cls, data: object) -> object:
        if isinstance(data, dict) and "files" not in data and "file_path" in data:
            path, content = data.get("file_path"), data.get("content")
            if isinstance(path, str) and isinstance(content, str):
                promoted = dict(data)
                promoted["files"] = [{"file_path": path, "content": content}]
                promoted.pop("file_path", None)
                promoted.pop("content", None)
                return promoted
        return data


# ---------------------------------------------------------------------------
# §11 implement
# ---------------------------------------------------------------------------


class Implement(Envelope):
    # status ok = implementer confirmed tests green itself; the gate re-verifies regardless
    tests_run: list[str] = req()  # no cap stated in the doc → uncapped


# ---------------------------------------------------------------------------
# §12 failure_judge
# ---------------------------------------------------------------------------


class Problem(NestedModel):

    side: Literal["code", "test", "spec"] = req()
    description: str = req(min_length=1)
    evidence: str = req(min_length=1)  # kernel validates non-empty (§12)
    confidence: Literal["low", "medium", "high"] = req()


class FailureJudge(Envelope):
    problems: list[Problem] = req(max_length=6)  # 0–6


# ---------------------------------------------------------------------------
# §13 identify_bugs
# ---------------------------------------------------------------------------


class Bug(NestedModel):

    symptom: str = req(min_length=1)
    evidence: str = req(min_length=1)
    location: str = req(min_length=1)  # must resolve — kernel post-hoc (§24)
    severity: Literal["critical", "major", "minor"] = req()
    reproducible: bool = req()


class IdentifyBugs(Envelope):
    bugs: list[Bug] = req(max_length=8)  # 0–8; empty list = explicit "no bugs"


# ---------------------------------------------------------------------------
# §14 propose_probe
# ---------------------------------------------------------------------------


class ProposeProbe(Envelope):
    command: str = req(min_length=1)  # free string — LEGAL: harness sandboxes it (§14)
    expected_info: str = req(min_length=1)
    why: str = req(min_length=1)
    confident_enough: bool = req()


# ---------------------------------------------------------------------------
# §22 lesson — defined before §15 which embeds it
# ---------------------------------------------------------------------------


class Lesson(NestedModel):
    """§22 fill-in form — embedded via InterpretProbe.lesson. Topic key is 1–6
    normalized AND-terms (deterministic matcher — exact term presence); provenance is
    mandatory (governance pipeline, DESIGN §4.4)."""

    line: str = req(min_length=1)
    topic_key: list[str] = req(min_length=1, max_length=6)
    provenance_task_id: str = req(min_length=1)
    provenance_ref: str = req(min_length=1)  # must resolve in ledger — kernel post-hoc (§24)

    @field_validator("topic_key")
    @classmethod
    def _term_sanity(cls, v: list[str]) -> list[str]:
        for term in v:
            if not _TOPIC_TERM.fullmatch(term):
                raise ValueError(f"topic term {term!r} must match ^[a-z0-9_-]+$ (ENVELOPE_SCHEMAS §22)")
            if term in STOPWORDS:
                raise ValueError(f"topic term {term!r} is a stopword (ENVELOPE_SCHEMAS §22)")
        return v


class LessonEnvelope(Envelope):
    """§22 as a STANDALONE step: the doc's `class Lesson(Base)` is the fill-in form
    (embedded via §15), but a standalone llm_step returns an envelope — so the form
    rides in the standard §0 envelope with its `unable` alternative (DESIGN §4.7:
    every envelope schema includes it)."""

    line: str = req(min_length=1)
    topic_key: list[str] = req(min_length=1, max_length=6)
    provenance_task_id: str = req(min_length=1)
    provenance_ref: str = req(min_length=1)

    @field_validator("topic_key")
    @classmethod
    def _term_sanity(cls, v: list[str]) -> list[str]:
        for term in v:
            if not _TOPIC_TERM.fullmatch(term):
                raise ValueError(f"topic term {term!r} must match ^[a-z0-9_-]+$ (ENVELOPE_SCHEMAS §22)")
            if term in STOPWORDS:
                raise ValueError(f"topic term {term!r} is a stopword (ENVELOPE_SCHEMAS §22)")
        return v


# ---------------------------------------------------------------------------
# §15 interpret_probe
# ---------------------------------------------------------------------------


class InterpretProbe(Envelope):
    fact: str = req(min_length=1)
    implies: str = req(min_length=1)
    lesson: Lesson | None = None  # §22 fill-in form; only when a real lesson emerged


# ---------------------------------------------------------------------------
# §16 debug_judge
# ---------------------------------------------------------------------------


class RankedFix(NestedModel):

    rank: int = req(ge=1, le=5)  # grammar-enforced range (§16)
    approach: str = req(min_length=1)
    how: str = req(min_length=1)


class DebugJudge(Envelope):
    blame: Literal["code", "test", "spec", "both"] = req()
    problem: str = req(min_length=1)
    fixes: list[RankedFix] = req(min_length=1, max_length=5)  # 1–5

    @model_validator(mode="after")
    def _ranks_unique_contiguous(self) -> Self:
        # §16 kernel validates: ranks unique/contiguous.
        if self._unset(self.fixes):
            return self  # unable branch: payload absent
        ranks = [f.rank for f in self.fixes]
        if len(set(ranks)) != len(ranks):
            raise ValueError("RankedFix ranks must be unique (ENVELOPE_SCHEMAS §16)")
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("RankedFix ranks must be contiguous starting at 1 (ENVELOPE_SCHEMAS §16)")
        return self


# ---------------------------------------------------------------------------
# §17 fix_attempt
# ---------------------------------------------------------------------------


class NewIssue(NestedModel):

    keywords: str = req(pattern=r"^[a-z0-9_-]+( [a-z0-9_-]+){0,3}$")  # 1–4 space-separated terms
    description: str = req(min_length=1)
    blocked: bool = req()


class FixAttempt(Envelope):
    # DECISION: §17 lists Literal["fixed","failed","blocked"], but DESIGN §4.7 and
    # require the grammar-enforced `unable: reason` alternative in
    # EVERY envelope schema — so "unable" stays legal here (the §17 "ok"-equivalent
    # is spelled "fixed"); blocked_kind/blocked_reason remain iff status=="blocked".
    status: Literal["fixed", "failed", "blocked", "unable"] = req()
    blocked_kind: Literal["design-question", "technical"] | None = None  # REQUIRED iff blocked
    blocked_reason: str | None = None  # REQUIRED iff blocked — content for D9 authoring
    tests_run: list[str] = req()  # no cap stated in the doc → uncapped
    new_issues: list[NewIssue] = req(max_length=4)  # 0–4

    @model_validator(mode="after")
    def _blocked_iff(self) -> Self:
        if self._unset(self.status):
            return self  # unable branch: payload absent
        blocked = self.status == "blocked"
        kind_set = self.blocked_kind is not None
        reason_set = self.blocked_reason is not None and bool(self.blocked_reason.strip())
        if blocked and not (kind_set and reason_set):
            raise ValueError("status=='blocked' requires blocked_kind and blocked_reason (ENVELOPE_SCHEMAS §17)")
        if not blocked and (kind_set or reason_set):
            raise ValueError("blocked_kind/blocked_reason are forbidden unless status=='blocked' (REQUIRED iff)")
        return self


# ---------------------------------------------------------------------------
# §18 judge_<aspect>
# ---------------------------------------------------------------------------


class JudgeAspect(Envelope):
    """One shape for all aspects (§18); ``aspect`` is an echo field instantiated as a
    grammar enum over ``run_config.judge_aspects`` per run. The registry holds this
    generic instantiation (aspect as a plain string); per-run enums are generated with
    :func:`build_judge_aspect_model` — the real runner binds them at decode time."""

    aspect: str = req(min_length=1)
    target_ac_id: str = req(pattern=r"^AC-[0-9]{1,3}$")
    verdict: Literal["pass", "fail"] = req()
    confidence: Literal["low", "medium", "high"] = req()
    evidence: str = req()  # kernel validates non-empty on fail (§18)

    @field_validator("target_ac_id")
    @classmethod
    def _target_in_map(cls, v: str, info: ValidationInfo) -> str:
        ac_map = (info.context or {}).get("ac_map")
        if ac_map is not None and v not in ac_map:
            raise ValueError(f"target_ac_id {v!r} not present in the leaf's AC map (ENVELOPE_SCHEMAS §18)")
        return v

    @model_validator(mode="after")
    def _evidence_on_fail(self) -> Self:
        if self._unset(self.verdict) or self._unset(self.evidence):
            return self  # unable branch: payload absent
        if self.verdict == "fail" and not self.evidence.strip():
            raise ValueError("verdict=='fail' requires non-empty evidence (ENVELOPE_SCHEMAS §18)")
        return self


def build_judge_aspect_model(aspects: Sequence[str]) -> type[JudgeAspect]:
    """Per-run instantiation: the aspect echo field becomes a closed enum over the
    run's configured judge aspects (ENVELOPE_SCHEMAS §18)."""
    values = tuple(aspects)
    if not values:
        raise ValueError("judge_aspects config must not be empty")
    return type("JudgeAspectEnum", (JudgeAspect,), {"__annotations__": {"aspect": Literal[values]}})


# ---------------------------------------------------------------------------
# §19 run_summary
# ---------------------------------------------------------------------------


class RunSummary(Envelope):
    outcome: Literal["complete", "partial", "parked-needs-user"] = req()
    what_was_done: str = req(min_length=1)
    what_changed: str = req(min_length=1)
    what_remains: str = req(min_length=1)


# ---------------------------------------------------------------------------
# §20 gate_decide
# ---------------------------------------------------------------------------


class GateDecide(Envelope):
    decision: Literal["accept", "reject"] = req()
    reason_is_real: bool = req()
    weakens_gate: bool = req()
    meaning_preserved: bool = req()
    explanation: str | None = None  # REQUIRED on reject; proposer gets it back

    @model_validator(mode="after")
    def _gate_pairs(self) -> Self:
        if self._unset(self.decision) or self._unset(self.weakens_gate):
            return self  # unable branch: payload absent
        if self.decision == "reject" and not (self.explanation and self.explanation.strip()):
            raise ValueError("decision=='reject' requires explanation (ENVELOPE_SCHEMAS §20)")
        if self.weakens_gate and self.decision != "reject":
            # grammar pair: gate-easing proposals are structurally suspect (DESIGN §4.8)
            raise ValueError("weakens_gate==True requires decision=='reject' (ENVELOPE_SCHEMAS §20)")
        return self


# ---------------------------------------------------------------------------
# §21 propose_growth
# ---------------------------------------------------------------------------


class ProposedNode(NestedModel):

    kind: Literal["ticket", "decision"] = req()  # decision ⇒ marked needs-user (D9 rule)
    what: str = req(min_length=1)
    why: str = req(min_length=1)


class ProposeGrowth(Envelope):
    trigger: Literal["new-bug", "design-question"] = req()
    evidence_refs: list[str] = req(min_length=1, max_length=6)  # 1–6 ledger/trajectory refs
    nodes: list[ProposedNode] = req(min_length=1, max_length=6)  # 1–6
    reason: str = req(min_length=1)


# ---------------------------------------------------------------------------
# §23 plan_node — the fused decompose+specify call (ticket 18, DESIGN §10.1)
# ---------------------------------------------------------------------------


class DeclaredTest(NestedModel):
    """One PLANNED test point (ENVELOPE_SCHEMAS §23; tickets 19 D, 22 round 3): the test
    FILE, the test FUNCTION NAMES, and (optionally) WHAT the test verifies, for one
    acceptance criterion. The harness verifies mechanically from the report that the file
    exists and every name is a collected, passing node id; a missing file/name is a
    distinct repairable failure."""

    ac_id: str = req(pattern=r"^AC-[0-9]{1,3}$")
    file: str = req(min_length=1)
    names: list[str] = req(min_length=1, max_length=8)
    #: Ticket 22 round 3: what the test verifies (the observable/behaviour it pins).
    verifies: str = ""


class ChildPlan(NestedModel):
    """One child of a decomposition (ENVELOPE_SCHEMAS §23): goal + boundary + ACs +
    the PLAN's two verification LISTS + a budget weight. ``what``/``why``/``kind``/
    ``est_calls`` are REQUIRED; ``files``/``acs``/``interfaces``/``planned_tests``/
    ``planned_reviews`` default to empty (a leaf child's AC map is enforced by
    :func:`harness.node.validate_decomposition`, not here).

    Ticket 22 round 3: the spec-time policy is NOT an enum. A node declares a LIST of
    planned TESTS (``planned_tests``) and/or a LIST of planned REVIEWS
    (``planned_reviews``); both, either, or neither may be given. When NEITHER is given
    the node must state a ``verification_reason``. ``best_effort`` is an optional
    PLAN-LEVEL fallback with its own plan-level reason."""

    what: str = req(min_length=1)                 # child goal (one line)
    why: str = req(min_length=1)
    kind: Literal["leaf", "internal"] = req()
    files: list[str] = Field(default_factory=list)   # leaf write boundary; [] for pure internal
    acs: list[DraftAC] = Field(default_factory=list)  # leaf: mandatory; internal: integration view
    interfaces: list[Interface] = Field(default_factory=list)
    #: Ticket 22 round 3: the test points this node INTENDS to write (file + names +
    #: which criterion + what it verifies). Empty = no test is planned for this node.
    planned_tests: list[DeclaredTest] = Field(default_factory=list)
    est_calls: int = Field(ge=1, le=8)            # budget-allocation weight
    #: Ticket 22 round 3: the review ANGLES this node INTENDS to run (drawn from the
    #: closed per-level registry). Empty = no review is planned for this node.
    planned_reviews: list[str] = Field(default_factory=list)
    #: Ticket 22 round 3: REQUIRED iff both lists are empty — the planner must say why
    #: no test and no review can carry this node's claim.
    verification_reason: str = ""
    best_effort: bool = False
    best_effort_reason: str = ""

    @model_validator(mode="after")
    def _reason_when_no_plan(self) -> Self:
        """Ticket 22 round 3: NEITHER list is legal only WITH a written reason."""
        if not self.planned_tests and not self.planned_reviews \
                and not (self.verification_reason or "").strip():
            raise ValueError(
                "a child with neither planned_tests nor planned_reviews requires a "
                "verification_reason (ENVELOPE_SCHEMAS §23, ticket 22 round 3)")
        return self


class PlanNode(Envelope):
    """The fused per-node decompose+specify envelope — ONE call per node (§23).

    ``children == []`` declares this node a LEAF (its own ``acs`` are then mandatory and
    must be non-empty); a non-empty list declares it INTERNAL, with ``acs`` as the
    integration view over descendant checks.

    Ticket 19 D/F: a node declares its expected test cases (``planned_tests``) and the
    guidance tells the planner to split by REQUIREMENT/acceptance criterion, not by file
    (two requirements may legitimately change the same file; the tree serializes
    overlapping writers).
    """

    goal: str = req(min_length=1)                 # THIS node's goal
    behavior: str = req(min_length=1)             # shared contract (both sides)
    implementation_notes: str = req(min_length=1)
    files: list[str] = req(max_length=10)         # THIS node's write boundary
    acs: list[DraftAC] = req(max_length=10)       # THIS node's AC map (leaf mandatory)
    interfaces: list[Interface] = req(max_length=8)
    planned_tests: list[DeclaredTest] = Field(default_factory=list, max_length=10)  # 22 r3
    # Ticket 22 round 3: the review ANGLES this node INTENDS to run (closed per-level
    # registry); empty = no review is planned. ``verification_reason`` is REQUIRED iff
    # both lists are empty; ``best_effort`` is an optional weaker-tier fallback with a
    # plan-level reason.
    planned_reviews: list[str] = Field(default_factory=list)   # closed per-level set
    verification_reason: str = ""
    best_effort: bool = False
    best_effort_reason: str = ""
    #: Ticket 20 step 2a: the How this decomposition belongs to. A per-How
    #: decomposition call is BOUND to one How id; ``""`` keeps the legacy unbound
    #: call (single-leaf / pre-How tree) valid.
    how_id: str = Field(default="", pattern=r"^(HOW-[0-9]{1,3})?$")
    children: list[ChildPlan] = req(max_length=15)  # [] ⇒ this node is a LEAF

    @model_validator(mode="after")
    def _reason_when_no_plan(self) -> Self:
        """Ticket 22 round 3: NEITHER list is legal only WITH a written reason (the
        ``unable`` branch carries no payload, so it is exempt)."""
        if self.status == "unable":
            return self
        if not self.planned_tests and not self.planned_reviews \
                and not (self.verification_reason or "").strip():
            raise ValueError(
                "a node with neither planned_tests nor planned_reviews requires a "
                "verification_reason (ENVELOPE_SCHEMAS §23, ticket 22 round 3)")
        return self


# ---------------------------------------------------------------------------
# §28 how_list — the How axis: N ranked approaches for one node (ticket 20 step 2a)
# ---------------------------------------------------------------------------


class HowEntry(NestedModel):
    """One ranked HOW for a node (ENVELOPE_SCHEMAS §28).

    ``text`` is a short paragraph of HOW this would be done, ``reason`` why it is worth
    a look. The model does NOT name or rank them: a live measurement showed it writing
    ``approach_1`` where the schema demanded ``HOW-1``, which silently discarded every
    How. The HARNESS now assigns the id (``HOW-<i>``) and the rank from the LIST ORDER,
    and derives the prior from that rank - so identity, priority and the scheduler hint
    are all framework-owned, never model output.
    """

    _missing_label = "how entry"

    text: str = req(min_length=1)
    reason: str = req(min_length=1)


class HowList(Envelope):
    """The FIRST planning step of a node: N ranked HOWs (ENVELOPE_SCHEMAS §28;
    ticket 20 step 2a).

    The Hows are the DIVERSITY AXIS: one call lists the candidate approaches IN PRIORITY
    ORDER, then each How the budget lets the node explore gets its own per-How
    decomposition bound to its harness-assigned id. Order is the rank, and the rank
    keys the deterministic prior table.
    """

    hows: list[HowEntry] = req(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _entries_distinct(self) -> Self:
        """Only what the MODEL is responsible for: distinct approaches in priority order.

        Ids and ranks are assigned by the harness from the list order, so there is no
        model-supplied identity to validate here (and no way for a bad id to lose the
        whole planning step).
        """
        if self._unset(self.hows):
            return self  # unable branch: payload absent
        texts = [h.text.strip() for h in self.hows]
        if len(set(texts)) != len(texts):
            raise ValueError("How texts must be distinct (ENVELOPE_SCHEMAS §28)")
        return self


# ---------------------------------------------------------------------------
# §29 manager_decision — the node's managing call: ONE decision + reason (ticket 20
# step 2b-ii)
# ---------------------------------------------------------------------------


class ManagerDecisionEnvelope(Envelope):
    """The node's MANAGING CALL decision after a How failed or exhausted (ENVELOPE_SCHEMAS
    §29; ticket 20 step 2b-ii).

    A FRESH-CONTEXT call over the node's STRUCTURED RECORD (`harness.how.NodeRecordView`:
    the How list with statuses, each failure's evidence and reason, the untried Hows, and
    any test deviations) returns exactly ONE ``decision`` from the closed four
    (``harness.how.MANAGER_DECISIONS``) plus a REQUIRED ``reason``. The node's manager —
    not the framework — owns the move; automatic advance is allowed only after an
    ``infeasible`` feasibility review (``harness.how.decide_after_failure``).
    """

    decision: Literal["continue-with-next-how", "author-a-new-how",
                      "request-feasibility-review", "escalate-or-park"] = req()
    reason: str = req(min_length=1)


# ---------------------------------------------------------------------------
# Registry: {step_type: model} — the per-leaf-type schema library (DESIGN §4.2:
# selected, never authored by the model). ``judge_<aspect>`` step types resolve via
# the runner's wildcard prefix to the generic JudgeAspect entry.
# ---------------------------------------------------------------------------

class FixPlan(Envelope):
    """Guided decomposition for implement (DESIGN §2.2 owner-approved variant,
    ticket 05 A/B): before emitting a fix, the model lists 2-8 ordered steps.
    The harness feeds the plan back into the implement call - the STRUCTURE of
    the thinking is harness-decomposed, the filling stays with the model."""

    steps: list[str] = req(min_length=2, max_length=8)


class LeafReview(Envelope):
    """Review-based verification of the final diff for ONE review ANGLE (tickets 19 B /
    20, ENVELOPE_SCHEMAS §26).

    Used ONLY when no test can carry verification (the own test could not be made red, a
    judge-attributed test could not be repaired into a discriminator, or the test path is
    unwritable). A fresh-context reviewer sees the goal, the acceptance criteria and the
    final diff for ONE predefined angle (ticket 20, item 1); ``grade`` is one of the five
    ORDINAL grades and ``evidence`` carries either a CONCRETE COUNTEREXAMPLE or the
    explicit statement that the angle found none. The harness's deterministic filter
    rejects a POSITIVE grade whose evidence does not name a changed artifact.
    """

    grade: Literal["definitely-ok", "probably-ok", "uncertain",
                   "probably-problematic", "definitely-problematic"] = req()
    evidence: str = req(min_length=1)


class VerifyRecord(Envelope):
    """The WRITTEN ``none+reason`` justification (ticket 20, ENVELOPE_SCHEMAS §27).

    Used ONLY when a node wrote code and neither a discriminating test nor an independent
    review can carry its claim. ``reason`` states why testing or reviewing was not
    possible or not warranted; the harness checks it deterministically (non-empty, a
    minimum length, and it must name the activity and the why), so a terse or off-topic
    answer cannot carry a claim. A ``none+reason`` claim is recorded as UNVERIFIED.
    """

    reason: str = req(min_length=1)


SCHEMAS: dict[str, type[Envelope]] = {
    "task_card": TaskCard,  # §1
    "fix_plan": FixPlan,  # §2.2 guided implement (ticket 05 A/B)
    "leaf_review": LeafReview,  # §26 review-based verification (ticket 19 B)
    "find_ambiguities": FindAmbiguities,  # §2
    "revise_task_card": ReviseTaskCard,  # §3
    "expand": Expand,  # §4
    "split_review": SplitReview,  # §5
    "draft_acs": DraftACs,  # §6
    "write_spec": WriteSpec,  # §7
    "spec_review": SpecReview,  # §8
    "test_plan": TestPlan,  # §9
    "write_test": WriteTest,  # §10
    "implement": Implement,  # §11
    "implement_write": ImplementWrite,  # §11b (the leaf's source write; see the class doc)
    "failure_judge": FailureJudge,  # §12
    "identify_bugs": IdentifyBugs,  # §13
    "propose_probe": ProposeProbe,  # §14
    "interpret_probe": InterpretProbe,  # §15
    "debug_judge": DebugJudge,  # §16
    "fix_attempt": FixAttempt,  # §17
    "judge_aspect": JudgeAspect,  # §18 (wildcard judge_<aspect> — see runner.schema_for_step)
    "run_summary": RunSummary,  # §19
    "gate_decide": GateDecide,  # §20
    "propose_growth": ProposeGrowth,  # §21
    "lesson": LessonEnvelope,  # §22 (standalone step; embedded form is Lesson)
    "plan_node": PlanNode,  # §23 (fused decompose+specify, ticket 18; per-How in 20)
    "verify": VerifyRecord,  # §27 (written none+reason justification, ticket 20)
    "how_list": HowList,  # §28 (the How axis, ticket 20 step 2a)
    "manager_decision": ManagerDecisionEnvelope,  # §29 (the node's managing call, ticket 20 step 2b-ii)
}

JUDGE_STEP_PREFIX = "judge_"
