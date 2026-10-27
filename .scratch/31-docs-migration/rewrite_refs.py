#!/usr/bin/env python3
"""Rewrite the paper's `path:line` citations to `path#anchor` after the docs migration.

Every moved document keeps a map of its old sections in `.scratch/31-docs-migration/map-N.tsv`
(`oldpath, oldstartline, oldendline, newpath, newanchor`). This script reads those maps, builds
an old-section -> new-anchor lookup, and rewrites every reference in `docs/paper/*.md` that
points at a moved file. References into files that did not move (`bench/`, `harness/`,
`reproduce.py`, `.scratch/`) are left alone.

    python3 .scratch/31-docs-migration/rewrite_refs.py          # write
    python3 .scratch/31-docs-migration/rewrite_refs.py --check   # report only

It refuses to write anything if a reference lands in a moved file with no map entry: that would
be a fact silently losing its address.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAPDIR = Path(__file__).resolve().parent
PAPER = REPO / "docs" / "paper"
REF = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|txt|sha256|toml|cfg)):(\d+)(?:-(\d+))?")


def slug(heading: str) -> str:
    text = re.sub(r"^#+\s*", "", heading).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def sections(path: Path) -> list[tuple[int, int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    heads, fence = [], False
    for i, line in enumerate(lines, start=1):
        if re.match(r"^\s*(```|~~~)", line):
            fence = not fence
            continue
        m = None if fence else re.match(r"^(#+)\s+(.*)$", line)
        if m:
            heads.append((i, len(m.group(1)), slug(m.group(2))))
    out = []
    for idx, (start, level, name) in enumerate(heads):
        end = len(lines)
        for later, later_level, _ in heads[idx + 1:]:
            if later_level <= level:
                end = later - 1
                break
        out.append((start, end, name))
    return out


def load_maps() -> dict[tuple[str, int], tuple[str, str]]:
    table: dict[tuple[str, int], tuple[str, str]] = {}
    for tsv in sorted(MAPDIR.glob("map-*.tsv")):
        for line in tsv.read_text(encoding="utf-8").splitlines():
            cells = line.split("\t")
            if len(cells) != 5 or not cells[1].strip().isdigit():
                continue
            oldpath, oldstart, _oldend, newpath, anchor = (c.strip() for c in cells)
            table[(oldpath, int(oldstart))] = (newpath, anchor)
    return table


def main(argv: list[str]) -> int:
    check = "--check" in argv
    table = load_maps()
    moved = {old for old, _ in table}
    problems: list[str] = []
    changed = 0

    for md in sorted(PAPER.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        original = text

        def repl(m: re.Match[str]) -> str:
            nonlocal changed
            path, first = m.group(1), int(m.group(2))
            if path not in moved:
                return m.group(0)
            cands = [s for s in sections(REPO / path) if s[0] <= first <= s[1]]
            cands.sort(key=lambda s: s[1] - s[0])
            for start, _end, _name in cands:
                if (path, start) in table:
                    newpath, anchor = table[(path, start)]
                    changed += 1
                    return f"{newpath}#{anchor}"
            problems.append(f"{md.relative_to(REPO)}: {path}:{first} lands in no mapped section")
            return m.group(0)

        text = REF.sub(repl, text)
        if text != original and not check:
            md.write_text(text, encoding="utf-8")

    for p in problems:
        print(f"unmapped: {p}")
    print(f"refs rewritten {changed}, unmapped {len(problems)}{' (dry run)' if check else ''}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
