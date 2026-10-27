#!/usr/bin/env python3
"""Check that `docs/` obeys the level scheme this repository files its documentation under.

    python3 bench/checks/docs_layout.py

The rule (`AGENTS.md`, and `docs/9_IMPLEMENTATION.md#docs-and-the-work-record`): documentation is
filed by level, `<N>_<NAME>.md`, one home per meaning; inside each file the content is zoned
`# EXPLICIT`, `# CONFIRMED`, `# INFERRED` — where it came from, in that order, only the zones that
have content; a document is referenced by `path#anchor`, never by line number, because a line
number is a derived fact stored by hand.

What this check fails on, one named line per problem:

1. a file in `docs/` that is neither a level document nor in an exempt tree (`docs/paper/` is the
   deliverable and renders itself; `docs/mockups/` is an artifact);
2. a level document whose H1 zones are missing, unknown, out of order, or emptied of text;
3. two headings in one file with the same anchor, which would make `path#anchor` ambiguous;
4. a markdown reference `path:line` anywhere in `docs/`, `AGENTS.md`, `README.md` or
   `CONTRIBUTING.md` — the form this repository migrated away from;
5. a referenced `.md` file that does not exist.

No network, no model, exit 0 only when nothing is wrong.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
EXEMPT_DIRS = {DOCS / "paper": "the deliverable: it renders itself and its numbers are checked against the entry point",
               DOCS / "mockups": "an artifact, not a document"}
ZONES = ["EXPLICIT", "CONFIRMED", "INFERRED"]
LEVEL = re.compile(r"^\d_[A-Z][A-Z0-9_]*\.md$")
HEAD = re.compile(r"^(#+)\s+(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
# A line number is a derived fact stored by hand: it rots the moment a document is edited. The
# rule this check enforces is about documents; a code file may still be cited by line, because a
# symbol does not always name the place a fact sits.
MD_LINE_REF = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.md:\d+")
# A path, not a prose mention: only a reference containing a separator is resolved.
MD_REF = re.compile(r"[A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.md(?![\w-])")

problems: list[str] = []


def slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.strip().lower()).strip("-")


def scan(path: Path) -> list[tuple[int, int, str]]:
    """(line number, level, heading) for every heading outside a fence."""
    out, fence = [], False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            fence = not fence
            continue
        m = None if fence else HEAD.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def check_level_doc(path: Path) -> None:
    heads = scan(path)
    h1 = [(n, text) for n, level, text in heads if level == 1]
    # `0_STAGING.md` is a list of facts with no home yet, not a level document: its first H1 names
    # the file and carries no provenance, so it is the one title a zone check tolerates.
    title_only = path.name == "0_STAGING.md" and h1 and h1[0][1] not in ZONES
    zones = h1[1:] if title_only else h1
    names = [text for _n, text in zones]
    if not zones:
        if not title_only:
            problems.append(f"{path.relative_to(REPO)}: no zone heading")
        return
    unknown = [n for n in names if n not in ZONES]
    if unknown:
        problems.append(f"{path.relative_to(REPO)}: H1 heading(s) that are not a zone: {unknown}")
    order = [ZONES.index(n) for n in names if n in ZONES]
    if order != sorted(order):
        problems.append(f"{path.relative_to(REPO)}: zones out of order: {names}")
    if len(set(order)) != len(order):
        problems.append(f"{path.relative_to(REPO)}: a zone appears twice: {names}")
    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, (line, text) in enumerate(zones):
        end = zones[idx + 1][0] - 1 if idx + 1 < len(zones) else len(lines)
        if not any(ln.strip() for ln in lines[line:end]):
            problems.append(f"{path.relative_to(REPO)}:{line}: zone {text} has no content")
    seen: dict[str, int] = {}
    for line, _level, text in heads:
        s = slug(text)
        if s in seen:
            problems.append(f"{path.relative_to(REPO)}:{line}: anchor #{s} repeats the one at line {seen[s]}")
        seen[s] = line


def check_refs(path: Path) -> None:
    fence = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            fence = not fence
        if fence:
            continue
        where = f"{path.relative_to(REPO)}:{i}"
        for m in MD_LINE_REF.finditer(line):
            problems.append(f"{where}: line reference {m.group(0)!r} — use path#anchor")
        for m in MD_REF.finditer(line):
            ref = m.group(0)
            if ref.startswith(("http", "/")):
                continue
            if not (REPO / ref).is_file():
                problems.append(f"{where}: references a file that does not exist: {ref}")


def main() -> int:
    for path in sorted(DOCS.iterdir()):
        if path.is_dir():
            if path not in EXEMPT_DIRS:
                problems.append(f"docs/{path.name}/: not a level directory and not exempt")
            continue
        if path.suffix != ".md":
            continue
        if not LEVEL.match(path.name):
            problems.append(f"docs/{path.name}: not a level document (wanted <N>_<NAME>.md)")
            continue
        check_level_doc(path)
    for path in [REPO / "AGENTS.md", REPO / "README.md", REPO / "CONTRIBUTING.md"]:
        if not path.is_file():
            problems.append(f"{path.name}: missing")
    for path in sorted(REPO.rglob("*.md")):
        rel = path.relative_to(REPO)
        if str(rel).split("/")[0] in {"node_modules", "build", "dist"} or path.parts[-2:-1] == (".venv",):
            continue
        if any(part in {".venv", "runs", ".pytest_cache"} for part in rel.parts):
            continue
        if str(rel).startswith((".scratch/", "bench/runs/")) or DOCS / "paper" in path.parents:
            continue          # the work record, the untracked home, and the paper's own checker
        check_refs(path)
    for path in [REPO / "AGENTS.md", REPO / "README.md", REPO / "CONTRIBUTING.md"]:
        if path.is_file():
            check_refs(path)
    for p in problems:
        print(f"fail: {p}")
    print(f"docs layout: {len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
