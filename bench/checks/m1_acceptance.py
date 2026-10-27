#!/usr/bin/env python3
"""M1's deciding observation, as one runnable check.

M1 is accepted as: on a clean clone at the frozen tag, one command that starts no model and
no network prints the decisive numbers, and that output equals the paper's table. This script
is that sentence turned into an exit code, so nobody has to read the repository to believe it.

    python3 bench/checks/m1_acceptance.py [tag]

It does five things in a temporary directory, never in this working tree, once per revision
(default: the frozen tag `preprint-v1` and `HEAD`):

1. `git clone` this repository and detach at the revision — a clone carries only tracked files,
   so the untracked 2 GB home `bench/runs/wave1/` is absent by construction and cannot be used.
2. Runs `python3 reproduce.py` inside the clone, with a clean environment, and requires exit 0.
3. Requires every `key value` line it printed to appear on one line of that revision's paper
   sources, which is how "the output equals the paper's table" stops being a reading and becomes
   a diff. Comparing against the revision's own paper, not the working tree's, is what lets the
   same command check the frozen acceptance revision and the tip.
4. Requires the run to fail loudly: with one projection record deleted, with one truncated to
   zero rows, and with one short of the rows an arm needs, each must exit non-zero AND name the
   input it was missing, printing no number first. A silent short-home result is the trap this
   project already fell into.
5. Prints one summary line and exits 0 only if all of the above hold for every revision.

The default therefore proves the revision a reader reproduces and the current tip in one run: a
later paper edit cannot regress the tree while this check stays green on the old tag alone.

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


def paper_text(root: Path) -> str:
    paper = root / "docs" / "paper"
    if not paper.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(paper.rglob("*.md")))


def check_revision(rev: str, tmp: Path) -> tuple[int, list[str]]:
    """Check one revision against its own tracked bytes; return (keys, failures)."""
    failures: list[str] = []
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", rev)
    clone = tmp / f"clone-{slug}"
    try:
        r = run(["git", "clone", "--quiet", "--no-checkout", str(REPO), str(clone)], cwd=tmp)
        if r.returncode != 0:
            return 0, [f"clone: {r.stderr.strip()}"]
        r = run(["git", "checkout", "--quiet", "--detach", rev], cwd=clone)
        if r.returncode != 0:
            return 0, [f"checkout {rev}: {r.stderr.strip()}"]
        if (clone / "bench" / "runs" / "wave1").exists():
            failures.append("the clone carries the untracked home; the test would not prove independence")

        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp),
               "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}

        first = run([sys.executable, "reproduce.py"], cwd=clone, env=env)
        if first.returncode != 0:
            return 0, [f"reproduce.py exit {first.returncode}: {first.stdout.strip()} {first.stderr.strip()}"]
        keys = parse_keys(first.stdout)
        if len(keys) < 8:
            failures.append(f"reproduce.py printed only {len(keys)} recognisable key lines")

        text = paper_text(clone)
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
                work = tmp / f"case-{slug}-{keyword}"
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
        shutil.rmtree(clone, ignore_errors=True)
    return len(keys), failures


def main(argv: list[str]) -> int:
    revs = [argv[1]] if len(argv) > 1 else ["preprint-v1", "HEAD"]
    tmp = Path(tempfile.mkdtemp(prefix="m1-accept-"))
    try:
        dirty = run(["git", "status", "--porcelain", "--", "docs/paper",
                     "bench/projection", "reproduce.py"], cwd=REPO).stdout.strip()
        if dirty:
            print("NOTE uncommitted changes under the paper or its numbers; HEAD is what is checked")
        results = {rev: check_revision(rev, tmp) for rev in revs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failures = [f"{rev}: {reason}" for rev, (_keys, reasons) in results.items() for reason in reasons]
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"m1 acceptance: FAIL ({len(failures)} reason(s)) at {', '.join(revs)}")
        return 1
    counts = ", ".join(f"{rev} {keys} keys" for rev, (keys, _r) in results.items())
    print(f"m1 acceptance: OK — {counts} reproduced from tracked bytes only, every one quoted by "
          f"its revision's paper, and a starved tree fails loudly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
