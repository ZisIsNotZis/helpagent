#!/usr/bin/env python3
"""M1's deciding observation, as one runnable check.

M1 is accepted as: on a clean clone at the frozen tag, one command that starts no model and
no network prints the decisive numbers, and that output equals the paper's table. This script
is that sentence turned into an exit code, so nobody has to read the repository to believe it.

    python3 bench/checks/m1_acceptance.py [tag]

It does five things in a temporary directory, never in this working tree:

1. `git clone` this repository at `tag` — a clone carries only tracked files, so the untracked
   2 GB home `bench/runs/wave1/` is absent by construction and cannot be used.
2. Runs `python3 reproduce.py` inside the clone, with a clean environment, and requires exit 0.
3. Requires every `key value` line it printed to appear on one line of the paper's sources,
   which is how "the output equals the paper's table" stops being a reading and becomes a diff.
4. Requires the run to fail loudly: with one projection record deleted, with one truncated to
   zero rows, and with one short of the rows an arm needs, each must exit non-zero AND name the
   input it was missing, printing no number first. A silent short-home result is the trap this
   project already fell into.
5. Prints one summary line and exits 0 only if all of the above hold.

Read-only with respect to this working tree; it writes only into a `mktemp -d`.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "docs" / "paper"
KEYLINE = re.compile(r"^([a-z0-9_]+)\s+(\S+)$")


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def parse_keys(out: str) -> dict[str, str]:
    got = {}
    for line in out.splitlines():
        m = KEYLINE.match(line.strip())
        if m:
            got[m.group(1)] = m.group(2)
    return got


def paper_text() -> str:
    if not PAPER.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(PAPER.rglob("*.md")))


def main(argv: list[str]) -> int:
    tag = argv[1] if len(argv) > 1 else "preprint-v1"
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="m1-accept-"))
    try:
        clone = tmp / "clone"
        r = run(["git", "clone", "--quiet", "--branch", tag, "--single-branch",
                 str(REPO), str(clone)], cwd=tmp)
        if r.returncode != 0:
            print(f"FAIL clone at {tag}: {r.stderr.strip()}")
            return 1
        if (clone / "bench" / "runs" / "wave1").exists():
            failures.append("the clone carries the untracked home; the test would not prove independence")

        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp),
               "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}

        first = run([sys.executable, "reproduce.py"], cwd=clone, env=env)
        if first.returncode != 0:
            print(f"FAIL reproduce.py exit {first.returncode}\n{first.stdout}\n{first.stderr}")
            return 1
        keys = parse_keys(first.stdout)
        if len(keys) < 8:
            failures.append(f"reproduce.py printed only {len(keys)} recognisable key lines")

        text = paper_text()
        if not text:
            failures.append("docs/paper/ has no markdown to compare against")
        for k, v in sorted(keys.items()):
            hit = any(k in line and v in line for line in text.splitlines())
            if not hit:
                failures.append(f"paper does not quote {k} {v} on a single line")

        # loud failure: three ways of starving the run, each must be named, not averaged over
        proj = sorted(p for p in (clone / "bench" / "projection" / "wave1" / "final").rglob("*")
                      if p.is_file() and (p.name == "results.jsonl" or p.name == "run.json"))
        if not proj:
            failures.append("no bench/projection/wave1/final/* records to starve the run with")
        else:
            rows_file = next((p for p in proj if p.name == "results.jsonl"), proj[0])

            def drop_rows(path: Path) -> None:
                keep = path.read_text(encoding="utf-8").splitlines()[:-5]
                path.write_text("\n".join(keep) + "\n", encoding="utf-8")

            cases = [("missing", "missing", lambda p: p.unlink()),
                     ("zero-rows", "empty", lambda p: p.write_text("")),
                     ("short sample", "short", drop_rows)]
            for label, keyword, mutate in cases:
                work = tmp / f"case-{keyword}"
                shutil.copytree(clone, work)
                victim = work / "bench" / "projection" / "wave1" / "final" / rows_file.relative_to(
                    clone / "bench" / "projection" / "wave1" / "final")
                mutate(victim)
                got = run([sys.executable, "reproduce.py"], cwd=work, env=env)
                said = (got.stderr + got.stdout).strip()
                if got.returncode == 0:
                    failures.append(f"{label}: reproduce.py exited 0 on a starved tree")
                elif not said:
                    failures.append(f"{label}: failed with no named line")
                elif keyword not in said.lower() and victim.name not in said:
                    failures.append(f"{label}: failure line names neither {keyword!r} nor {victim.name}")
                elif parse_keys(got.stdout):
                    failures.append(f"{label}: printed numbers before failing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"m1 acceptance: FAIL ({len(failures)} reason(s)) at tag {tag}")
        return 1
    print(f"m1 acceptance: OK — {tag}: {len(keys)} keys reproduced from tracked bytes only, "
          f"every one quoted by the paper, and a starved tree fails loudly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
