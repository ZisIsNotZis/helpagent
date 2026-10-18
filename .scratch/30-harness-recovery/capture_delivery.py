"""Bind this package's exact baseline-to-worktree delta without staging any file."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parent.parent
SCOPED = ("docs/ROADMAP.md", "docs/FLOW.md", "harness/leaf.py",
          "tests/unit/test_v2_leaf.py", "tests/unit/test_own_test_setup.py")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def roadmap_baseline():
    """Apply only the captured pre-existing roadmap hunks in memory, checking context."""
    original = git("show", "HEAD:docs/ROADMAP.md").decode().splitlines(keepends=True)
    captured = (RECORD / "baseline.diff").read_text().splitlines(keepends=True)
    inside = False
    result = []
    position = 0
    for line in captured:
        if line.startswith("diff --git "):
            inside = line.startswith("diff --git a/docs/ROADMAP.md ")
            continue
        if not inside or line.startswith(("index ", "--- ", "+++ ")):
            continue
        if line.startswith("@@"):
            target = int(re.match(r"@@ -(\d+)", line).group(1)) - 1
            result.extend(original[position:target])
            position = target
        elif line.startswith(" "):
            assert original[position] == line[1:]
            result.append(line[1:])
            position += 1
        elif line.startswith("-"):
            assert original[position] == line[1:]
            position += 1
        elif line.startswith("+"):
            result.append(line[1:])
    result.extend(original[position:])
    return "".join(result)


baseline = json.loads((RECORD / "baseline.json").read_text())
assert git("rev-parse", "HEAD").decode().strip() == baseline["head"]
assert not git("diff", "--cached", "--name-only").strip()
protected = {p: h for p, h in baseline["files"].items() if p != "docs/ROADMAP.md"}
for p, h in protected.items():
    assert sha((ROOT / p).read_bytes()) == h, f"Pre-existing work changed: {p}"
roadmap = roadmap_baseline()
assert sha(roadmap.encode()) == baseline["files"]["docs/ROADMAP.md"]
patch = []
for p in SCOPED:
    if p == "docs/ROADMAP.md":
        before = roadmap
    elif p == "tests/unit/test_own_test_setup.py":
        before = ""
    else:
        before = git("show", f"HEAD:{p}").decode()
    after = (ROOT / p).read_text()
    patch.extend(difflib.unified_diff(before.splitlines(keepends=True),
                                    after.splitlines(keepends=True),
                                    fromfile=f"before/{p}" if before else "/dev/null",
                                    tofile=f"after/{p}"))
    if p.endswith(".py"):
        ast.parse(after, filename=p)
old = git("show", "HEAD:docs/ROADMAP.md").decode()
new = (ROOT / "docs/ROADMAP.md").read_text()
for prefix, width, count in (("| C", 3, 5), ("| **V", 4, 6)):
    def columns(text):
        return [line.split("|")[1:width] for line in text.splitlines()
                if line.startswith(prefix)]
    assert columns(old) == columns(new) and len(columns(new)) == count
(RECORD / "package.diff").write_text("".join(patch))
repair_patch = []
cycle1_files = {}
for p in SCOPED:
    previous = RECORD / "cycle1-snapshot" / p
    if not previous.is_file():
        continue
    cycle1_files[p] = sha(previous.read_bytes())
    repair_patch.extend(difflib.unified_diff(
        previous.read_text().splitlines(keepends=True),
        (ROOT / p).read_text().splitlines(keepends=True),
        fromfile=f"cycle1/{p}", tofile=f"repair/{p}"))
(RECORD / "cycle1-repair.diff").write_text("".join(repair_patch))
names = git("ls-files", "--modified", "--others", "--exclude-standard", "-z").decode().split("\0")
files = {p: sha((ROOT / p).read_bytes()) for p in names if p
         and (ROOT / p).is_file() and not p.startswith(".scratch/30-harness-recovery/")}
state = {"head": baseline["head"], "files": files}
report = {
    "package": "P1a: pristine own-test setup and assertion ownership",
    "baselineHead": baseline["head"],
    "baselineWorktreeHash": baseline["worktree_hash"],
    "worktreeHash": sha(json.dumps(state, sort_keys=True).encode()),
    "worktreeHashDefinition": "SHA256 of canonical JSON {head,files} for all dirty files outside ticket30",
    "changedFiles": {p: sha((ROOT / p).read_bytes()) for p in SCOPED},
    "packageDiff": {"path": str(RECORD.relative_to(ROOT) / "package.diff"),
                    "sha256": sha((RECORD / "package.diff").read_bytes())},
    "cycle1SnapshotSourceFiles": cycle1_files,
    "cycle1RepairDiff": {"path": str(RECORD.relative_to(ROOT) / "cycle1-repair.diff"),
                         "sha256": sha((RECORD / "cycle1-repair.diff").read_bytes())},
    "job2RepairDiff": {"path": str(RECORD.relative_to(ROOT) / "job2-repair.diff"),
                       "sha256": sha((RECORD / "job2-repair.diff").read_bytes())},
    "behavioralValidation": json.loads((RECORD / "validation-summary.json").read_text()),
    "independentReview": "cycle1 BLOCK; cycle2 pending, final allowed package review cycle",
    "protectedBaselineFiles": list(protected),
    "workRecordFiles": {str(p.relative_to(ROOT)): sha(p.read_bytes())
                        for p in sorted(RECORD.rglob("*"))
                        if p.is_file() and p != RECORD / "delivery.json"},
    "noStagedFiles": True,
}
(RECORD / "delivery.json").write_text(json.dumps(report, indent=2) + "\n")
print("PASS: protected baseline hashes, unchanged acceptance columns, AST parse, no staged files")
print("Baseline worktree:", baseline["worktree_hash"])
print("Current worktree:", report["worktreeHash"])
print("Package diff:", report["packageDiff"]["sha256"])
print("Cycle1 repair diff:", report["cycle1RepairDiff"]["sha256"])
print("Behavioral validation: validation-summary.json; independent review: cycle2 pending")
