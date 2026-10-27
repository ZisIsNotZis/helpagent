"""Injection-first knowledge pack (docs/6_ARCHITECTURE.md §4.4, owner decision 2026-09-17:
injection-first, the model never self-initiates lookups).

Deterministic lookups over the task repo, rendered into ONE bounded artifact the
composer injects into implement-step inputs:

- SIGNATURES: every def/class line, per file — what exists and what it takes.
- CALLERS: for each name defined in the boundary, which OTHER files reference it
  — the cross-file call-site map (the locate-driven context FP-4's structural
  remedy promised; multi-file fixes fail when a caller is forgotten, T-31).
- CONSTANTS: module-level assignments (FP-7 — values live in constants).

Everything here is harness lookup (docs/6_ARCHITECTURE.md §2.1: never the model's job) and
bounded: the rendered block is capped, biggest sections first-come-first-served.
"""

from __future__ import annotations

import re

__all__ = ["build_knowledge"]

_MAX_LINES = 48

_DEF = re.compile(r"^\s*(?:def|class)\s+\w+", re.M)
_NAME = re.compile(r"^(?:def|class)\s+(\w+)", re.M)
_CONST = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*([^#\n]+)", re.M)


def _signatures(files: dict[str, str], boundary: set[str]) -> list[str]:
    lines: list[str] = []
    for rel in sorted(files):
        if rel not in boundary or not rel.endswith(".py"):
            continue
        for line in files[rel].splitlines():
            s = line.strip()
            if s.startswith("def ") or s.startswith("class "):
                lines.append(f"{rel}: {s[:90]}")
    return lines


def _callers(files: dict[str, str], boundary: set[str]) -> list[str]:
    """name -> files (outside the defining file) that reference it."""
    defined: dict[str, str] = {}
    for rel in sorted(files):
        if rel not in boundary or not rel.endswith(".py"):
            continue
        for m in _NAME.finditer(files[rel]):
            defined.setdefault(m.group(1), rel)
    out: list[str] = []
    for name, home in sorted(defined.items()):
        users = sorted(
            rel for rel, text in files.items()
            if rel != home and re.search(rf"\b{re.escape(name)}\s*\(", text)
        )
        if users:
            out.append(f"{name} (in {home}) <- called by: {', '.join(users)}")
    return out


def _constants(files: dict[str, str], boundary: set[str]) -> list[str]:
    lines: list[str] = []
    for rel in sorted(files):
        if rel not in boundary or not rel.endswith(".py"):
            continue
        for m in _CONST.finditer(files[rel]):
            lines.append(f"{rel}: {m.group(1)} = {m.group(2).strip()[:40]}")
    return lines


def build_knowledge(files: dict[str, str], boundary: list[str]) -> str:
    """Render the injection block (bounded; empty string when nothing applies —
    the composer injects only what exists, never filler)."""
    b = set(boundary)
    sections = [
        ("SIGNATURES", _signatures(files, b)),
        ("CALLERS", _callers(files, b)),
        ("CONSTANTS", _constants(files, b)),
    ]
    out: list[str] = []
    budget = _MAX_LINES
    for title, lines in sections:
        if not lines or budget <= 0:
            continue
        take = lines[:max(0, budget - 1)]   # the header costs one line too
        out.append(f"{title}:")
        out.extend(f"  {l}" for l in take)
        budget -= len(take) + 1
    return "\n".join(out)
