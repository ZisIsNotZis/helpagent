#!/usr/bin/env python3
"""Check that every citation and every command in docs/paper/ resolves in this repository.

    python3 docs/paper/check_citations.py

What it checks, in the order it runs:

1. Every reference in ``docs/paper/*.md`` resolves. Three forms are accepted:
   - ``path:line`` (and ``path:line-line``) — a line number that the file has;
   - ``path#anchor`` — the slug of a heading in that file (see ``slug``), which is the
     preferred form everywhere outside the numbers table, because a heading survives an edit
     that shifts lines and a line number does not;
   - ``path §Heading`` — the heading text itself, still accepted from older prose.
2. Every row of every ``Number | Value | Source | Command`` table in ``numbers.md``:
   - the ``Source`` cell carries at least one reference and every reference resolves;
   - each numeric value in the ``Value`` cell appears in the text a citation covers — the
     cited lines, or the whole body of the cited section (so a value cannot drift away from
     the place that is supposed to carry it);
   - the ``Command`` cell is one of: a key printed by ``reproduce.py``, the bare entry point
     ``python3 reproduce.py`` (the value is then a field of a record the entry point compares in
     full), a command recorded in ``bench/analysis/wave1/NUMBERS.md``, or ``unknown``;
   - for a printed key, the row's value must appear in the value the entry point prints.
3. Every numeral in the prose of ``docs/paper/*.md`` (except ``numbers.md``, which is the
   oracle) appears in a ``Value`` cell of the numbers table. Identifiers, ``§N`` cross
   references, ``path:line`` citations and exit statuses are not quantities and are skipped;
   fenced code blocks are skipped.

``unknown`` rows are counted and printed, never silently accepted: a number with no committed
command that re-derives it is a gap the draft must name, and this script keeps the count
visible.

``preprint.md`` is not scanned here: it is a render of the files above, so its sentences are
the same sentences, and the thing worth checking about a render is that it is current —
``build_preprint.py --check`` does that.

Fails one line per problem, names the file and line, and prints
``citations resolved N unresolved M`` last. Exit 0 only when M is 0. No network, no model.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = Path(__file__).resolve().parent
NUMBERS = PAPER / "numbers.md"
# The render is derived from these sources; `build_preprint.py --check` guards it. Scanning it
# here would check the same sentences twice and inflate the resolved count with its own copies.
RENDER = PAPER / "preprint.md"
NUMBERS_TABLE = REPO / "bench" / "analysis" / "wave1" / "NUMBERS.md"
ENTRY = REPO / "reproduce.py"

# A file reference: path:line or path:line-line. The path is kept permissive and then resolved.
REF = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|txt|sha256|toml|cfg))\s*:\s*(\d+)(?:\s*-\s*(\d+))?")
# A heading anchor: path#slug. The slug is the heading lowercased with every run of characters
# that is not a letter, digit or space collapsed to one hyphen (`slug` below). A heading can be
# rewritten and the anchor either follows it or fails here; a line number would have gone
# silently wrong instead.
ANCHOR = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|txt|sha256|toml|cfg))#([a-z0-9][a-z0-9-]*)")
# A quantity in prose: not inside an identifier, a path, a citation, a section sign or a range.
NUM = re.compile(r"(?<![\w./:\-–—§])(\d+(?:[.,]\d+)*(?:/\d+)?)(?![\w./\-])")
# A section reference: path §Heading — resolved by heading, so editing the file cannot rot it.
SECTION = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.md)`?\s*§\s*([A-Za-z][A-Za-z ]+)")
# Section cross references, exit statuses: not quantities.
NOT_A_QUANTITY = re.compile(r"§\s*\d+|exit(?:s|ed)?[ =:]*\d+|\bexit code \d+")


def slug(heading: str) -> str:
    """The anchor a heading carries: lowercase, non-alphanumerics collapsed to one hyphen."""
    text = re.sub(r"^#+\s*", "", heading).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def norm(text: str) -> str:
    """Fold the way a value is written in prose and in a record line: ascii minus, no thousands
    separators, no space around a slash or between a sign and its digits. Other spacing stays, so
    two neighbouring numbers do not merge into one."""
    text = text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("`", "").replace(",", "")
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"([-+]) (\d)", r"\1\2", text)
    return text.strip()


def numerals(text: str) -> list[str]:
    return NUM.findall(text.replace("\u2212", "-"))


def quantities(text: str) -> list[str]:
    """Numbers with an optional sign, for comparing a value cell with a printed value."""
    text = text.replace("\u2212", "-").replace("`", "")
    text = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)   # thousands separators only
    return re.findall(r"[-+]?\d+(?:\.\d+)*(?:/\d+)?", text)


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def sections(path: Path) -> list[tuple[int, int, str]]:
    """Every heading in the file as (first line, last line, slug), the body being the lines up to
    the next heading of the same or a higher level. Line numbers are 1-based and inclusive."""
    lines = read_lines(path)
    heads: list[tuple[int, int, str]] = []
    fence = False
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
        for later_start, later_level, _ in heads[idx + 1:]:
            if later_level <= level:
                end = later_start - 1
                break
        out.append((start, end, name))
    return out


def resolve_anchor(ref: str, where: str) -> list[str] | None:
    m = ANCHOR.fullmatch(ref.strip())
    if not m:
        fail(f"{where}: not a path#anchor reference: {ref!r}")
        return None
    path, name = m.group(1), m.group(2)
    target = REPO / path
    if not target.is_file():
        fail(f"{where}: no such file: {path}")
        return None
    hits = [s for s in sections(target) if s[2] == name]
    if not hits:
        fail(f"{where}: {path} has no heading with anchor #{name}")
        return None
    if len(hits) > 1:
        fail(f"{where}: {path} has {len(hits)} headings with anchor #{name}; a heading must be unique")
        return None
    lines = read_lines(target)
    counts["resolved"] += 1
    return lines[hits[0][0] - 1:hits[0][1]]


def resolve(ref: str, where: str) -> None:
    m = REF.fullmatch(ref.strip())
    if not m:
        fail(f"{where}: not a path:line reference: {ref!r}")
        return None
    path, first, last = m.group(1), int(m.group(2)), m.group(3)
    target = (REPO / path)
    if not target.is_file():
        fail(f"{where}: no such file: {path}")
        return None
    lines = read_lines(target)
    limit = int(last) if last else first
    if not lines:
        fail(f"{where}: empty file: {path}")
        return None
    if first < 1 or limit > len(lines):
        fail(f"{where}: {path}:{first}{'-' + last if last else ''} is outside the file ({len(lines)} lines)")
        return None
    counts["resolved"] += 1
    return lines[first - 1:limit]


counts = {"resolved": 0, "unknown": 0, "rows": 0, "printed_key": 0, "record": 0, "analyzer": 0}


def split_row(line: str) -> list[str]:
    cells, cur, esc = [], [], False
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    for ch in body:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
            cur.append(ch)
        elif ch == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return [c.replace("\\|", "|") for c in cells]


def entry_point() -> tuple[dict[str, str], bool]:
    """Run the reproduce entry point once and return its printed key -> value map."""
    if not ENTRY.is_file():
        return {}, False
    try:
        run = subprocess.run([sys.executable, str(ENTRY)], cwd=REPO, capture_output=True,
                             text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        fail(f"reproduce.py: could not run the entry point: {exc}")
        return {}, False
    if run.returncode != 0:
        fail(f"reproduce.py: exit {run.returncode}: {run.stderr.strip().splitlines()[:1]}")
        return {}, False
    out = {}
    for line in run.stdout.splitlines():
        key, _, value = line.partition(" ")
        out[key] = value.strip()
    return out, True


def numbers_tables() -> list[list[str]]:
    rows = []
    in_table = False
    header_seen = False
    for line in read_lines(NUMBERS):
        if not line.startswith("|"):
            in_table, header_seen = False, False
            continue
        cells = split_row(line)
        if not header_seen:
            if [c.lower() for c in cells] == ["number", "value", "source", "command"]:
                in_table, header_seen = True, True
            continue
        if in_table:
            if set("".join(cells)) <= set("-: "):
                continue  # the separator row
            rows.append(cells)
    return rows


def check_numbers(printed: dict[str, str], have_entry: bool) -> None:
    recorded = norm(" ".join(read_lines(NUMBERS_TABLE)).replace("\\|", "|"))
    quoted: set[str] = set()
    rows = numbers_tables()
    if not rows:
        fail("numbers.md: no Number | Value | Source | Command table found")
        return
    for cells in rows:
        counts["rows"] += 1
        if len(cells) != 4:
            fail(f"numbers.md: row has {len(cells)} cells, wanted 4: {cells}")
            continue
        number, value, source, command = cells
        where = f"numbers.md [{number[:48]}]"
        # 1. sources resolve, and carry the value
        cited = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\."
                           r"(?:md|py|json|txt|sha256|toml|cfg)(?::\d+(?:-\d+)?|#[a-z0-9][a-z0-9-]*)",
                           source)
        if not cited:
            fail(f"{where}: Source cell cites nothing: {source!r}")
        lines: list[str] = []
        for ref in cited:
            if "#" in ref:
                lines.extend(resolve_anchor(ref, where) or [])
            else:
                lines.extend(resolve(ref, where) or [])
        flat = norm(" ".join(lines))
        for token in numerals(value):
            token = token.replace(",", "")
            if not re.search(r"(?<![\d.])" + re.escape(token) + r"(?!\d)", flat):
                fail(f"{where}: value {token} is not on any cited line: {source}")
        # 2. the command is one of the four forms
        cmd = command.strip().strip("`").replace("\\|", "|")
        key_form = re.fullmatch(r"python3 reproduce\.py ([a-z0-9_]+)", cmd)
        if cmd == "unknown":
            counts["unknown"] += 1
            continue
        if cmd == "python3 reproduce.py":
            counts["record"] += 1
            if not have_entry:
                fail(f"{where}: bare entry point used but reproduce.py is missing")
            continue
        if key_form:
            key = key_form.group(1)
            counts["printed_key"] += 1
            if not have_entry:
                fail(f"{where}: key {key} checked but reproduce.py is missing")
            elif key not in printed:
                fail(f"{where}: reproduce.py does not print the key {key!r}")
            else:
                quoted.add(key)
            continue
        if cmd and norm(cmd) in recorded:
            counts["analyzer"] += 1
            continue
        fail(f"{where}: Command is not a printed key, the bare entry point, a traceability-table "
             f"command or unknown: {cmd!r}")


    # every value the entry point prints is quoted by at least one row that names its key
    by_key: dict[str, list[list[str]]] = {}
    for cells in rows:
        if len(cells) != 4:
            continue
        m = re.fullmatch(r"python3 reproduce\.py ([a-z0-9_]+)", cells[3].strip().strip("`"))
        if m:
            by_key.setdefault(m.group(1), []).append(cells)
    for key, value in sorted(printed.items()):
        if key not in quoted:
            fail(f"reproduce.py prints {key} {value} but no row of numbers.md cites the key")
            continue
        want = printed[key]
        want_q = {q.lstrip("+") for q in quantities(want)}
        ok = any(q.lstrip("+") in want_q
                 for cells in by_key.get(key, []) for q in quantities(cells[1]))
        if not ok:
            fail(f"numbers.md: the rows citing {key} quote no value equal to the printed {want!r}")


def walk_refs() -> None:
    for md in sorted(PAPER.glob("*.md")):
        if md.name == RENDER.name:
            continue
        for lineno, line in enumerate(read_lines(md), start=1):
            for m in REF.finditer(line):
                ref = m.group(0).replace(" ", "")
                resolve(ref, f"{md.name}:{lineno}")
            for m in ANCHOR.finditer(line):
                resolve_anchor(m.group(0), f"{md.name}:{lineno}")
            for m in SECTION.finditer(line):
                resolve_section(m.group(1), m.group(2), f"{md.name}:{lineno}")


def resolve_section(path: str, heading: str, where: str) -> None:
    """A section reference names a heading, not a line number.

    The paper cites the node document for the interface it fixes. A line number there is exact
    until the next advance edits that file, and then the citation is silently wrong; a heading
    survives editing and is still checkable, so the reference names the heading and this checks
    that a heading of that name exists.
    """
    target = REPO / path
    if not target.is_file():
        fail(f"{where}: no such file: {path}")
        return
    heads = [re.sub(r"^#+\s*", "", ln).strip() for ln in read_lines(target) if ln.startswith("#")]
    want = heading.strip()
    if not any(h == want or h.startswith(want + " ") for h in heads):
        fail(f"{where}: {path} has no section {want!r}")
        return
    counts["resolved"] += 1


def prose_numerals() -> None:
    table: set[str] = set()
    for cells in numbers_tables():
        if len(cells) == 4:
            table.update(q.lstrip("+-").replace(",", "") for q in quantities(cells[1]))
    for md in sorted(PAPER.glob("*.md")):
        if md.name in (NUMBERS.name, RENDER.name):
            continue
        text = "\n".join(read_lines(md))
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = ANCHOR.sub(" ", text)
        text = NOT_A_QUANTITY.sub(" ", text)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in numerals(line):
                tok = token.replace(",", "")
                if tok not in table:
                    fail(f"{md.name}:{lineno}: numeral {token} has no row in numbers.md")


def main() -> int:
    printed, have_entry = entry_point()
    if have_entry:
        # A key named in the paper's prose must be a key the entry point prints, and a value
        # written beside it must be the value it prints: prose cannot name a number the
        # entry point does not produce.
        paper_text = "\n".join("\n".join(read_lines(md)) for md in sorted(PAPER.glob("*.md"))
                               if md.name not in (NUMBERS.name, RENDER.name))
        named = sorted(set(re.findall(r"\b(r[123]_[a-z0-9_]+)\b", paper_text)))
        if not named:
            fail("the paper names no reproduce key, so the output cannot be exactly its table")
        for key in named:
            if key not in printed:
                fail(f"the paper names the key {key!r}, which reproduce.py does not print")
            else:
                for value in re.findall(re.escape(key) + r"\s+([-+\d/.]+)", paper_text):
                    if norm(value) not in quantities(printed[key]) and norm(value) != norm(printed[key]):
                        fail(f"the paper states {key} {value}, reproduce.py prints {printed[key]}")
    walk_refs()
    check_numbers(printed, have_entry)
    prose_numerals()
    for line in problems:
        print(f"unresolved: {line}")
    print(f"rows {counts['rows']} (printed-key {counts['printed_key']}, "
          f"record {counts['record']}, analyzer {counts['analyzer']}, unknown {counts['unknown']})")
    print(f"citations resolved {counts['resolved']} unresolved {len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
