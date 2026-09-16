"""Typed artifact store (DESIGN §4.2, KERNEL_API §4.6).

- Typed: pydantic Artifact, validated on write.
- Bounded: a hard size cap; overflow on code artifacts raises SplitWindowRequired —
  the pre-declared split path — and NEVER truncates (DESIGN §4.2 "Code output
  overflow never truncates").
- Secret filter at the store boundary: every artifact's content is filtered BEFORE
  persistence; the filter returns the redacted form and a count — the secret itself
  is never logged anywhere (DESIGN §4.2, ticket-01 discipline).
- Producer linkage: an artifact carries its producing node id; the tree's attach
  enforces the single-producer rule (KERNEL_API §4.6 single-producer validation).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Hard content cap in characters (DESIGN §4.2 "Bounded: hard size caps").
SIZE_CAP = 32_000

# Kinds that carry executable/code content — the split-window path applies to them
# (ENVELOPE_SCHEMAS §10: write_test is "the only content-emitting schema left").
CODE_KINDS = frozenset({"file", "code", "write_test", "implement"})


class SplitWindowRequired(Exception):
    """Raised when a code artifact exceeds SIZE_CAP. Never truncates; the caller
    must take the pre-declared split-window path (DESIGN §4.2, ENVELOPE_SCHEMAS §10)."""


# -- secret filter ------------------------------------------------------------
# Deterministic patterns; every match is replaced with [REDACTED]. The patterns
# themselves are not secrets. NOTE: never log matched text — only counts.

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                      # AWS access key id
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),                   # GitHub PAT
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),                 # sk- style API tokens
    re.compile(                                               # PEM private key blocks
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.S,
    ),
    re.compile(r"(?i)\b(password|passwd|secret|token)\s*[=:]\s*\S+"),   # password= ...
    re.compile(r"\b\w+://[^/\s:]+:[^@\s/]+@\S+"),             # scheme://user:pass@host
)


def filter_secrets(content: str) -> tuple[str, int]:
    """Redact secret-shaped substrings. Returns (filtered_content, redaction_count).
    Never logs, returns, or stores the matched secret text itself."""
    n = 0
    out = content
    for pat in _SECRET_PATTERNS:
        out, k = pat.subn("[REDACTED]", out)
        n += k
    return out, n


# -- artifact -----------------------------------------------------------------


class Artifact(BaseModel):
    """One persisted artifact (KERNEL_API §4.6). ``content`` is ALREADY
    secret-filtered — the store filters at the boundary before validation."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)  # the producer — linkage is a schema field
    kind: str = Field(min_length=1)
    content: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    redactions: int = 0  # how many secret-shaped substrings the boundary redacted

    @field_validator("content")
    @classmethod
    def _bounded(cls, v: str, info: Any) -> str:
        # The cap is enforced by the store (which knows the artifact kind and raises
        # SplitWindowRequired); the validator is the last-resort backstop for
        # non-code kinds only — code overflow must never reach here truncated.
        kind = (info.data or {}).get("kind", "")
        if kind not in CODE_KINDS and len(v) > SIZE_CAP:
            raise ValueError(
                f"artifact content exceeds SIZE_CAP ({len(v)} > {SIZE_CAP}) — "
                "non-code artifacts have no split path (DESIGN §4.2)"
            )
        return v


class ArtifactStore:
    """Append-only store. ``put`` applies the secret filter at the boundary and
    enforces the size cap for code kinds. Single-producer enforcement lives with
    the tree (``TaskTree.attach``) — the store is deliberately producer-agnostic."""

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self.total_redactions = 0

    def put(
        self, artifact_id: str, node_id: str, kind: str, content: str
    ) -> Artifact:
        if artifact_id in self._artifacts:
            raise ValueError(f"artifact {artifact_id!r} already exists (append-only)")
        if kind in CODE_KINDS and len(content) > SIZE_CAP:
            # Never truncate: raise the pre-declared split path (DESIGN §4.2).
            raise SplitWindowRequired(
                f"code artifact {artifact_id!r} is {len(content)} chars > cap {SIZE_CAP}; "
                "take the split-window path (ENVELOPE_SCHEMAS §10)"
            )
        filtered, n = filter_secrets(content)
        art = Artifact(
            artifact_id=artifact_id, node_id=node_id, kind=kind, content=filtered, redactions=n
        )
        self._artifacts[artifact_id] = art
        self.total_redactions += n
        return art

    def get(self, artifact_id: str) -> Artifact:
        return self._artifacts[artifact_id]

    def __contains__(self, artifact_id: str) -> bool:
        return artifact_id in self._artifacts

    def __len__(self) -> int:
        return len(self._artifacts)
