#!/usr/bin/env python3
"""Recompute every decisive number the preprint quotes, from committed bytes alone.

    python3 reproduce.py

No network, no model server, no `/tmp/wave1`, no `bench/runs/wave1` (2 GB, untracked). The
inputs are `bench/projection/wave1/` (a field-reduced projection of the campaign rows; see
`bench/projection/README.md`); the arithmetic is the campaign's own analyzers in
`bench/analysis/wave1/`, executed unmodified, and every one of their outputs is compared with
the record committed beside it before a single number is printed:

  R1  bench/analysis/wave1/n25/analyze_n25.py   vs  n25/analysis-n25-final.json  (all keys)
  R2  bench/analysis/wave1/r2/r2_analyze.py     vs  r2/analysis.txt (bytes) + r2/analysis.json
  R3  bench/analysis/wave1/r3/analyze.py        vs  r3/analysis-r3.txt   (bytes)
      bench/analysis/wave1/r3/supp.py           vs  r3/supp-r3.txt       (bytes)

The `r1_width_*`, `r1_half_width`, `r1_within_share_pct`, `r1_asymptotic_width` and
`r1_needed_estimate` keys are one further R1 derivation: the same analyzer at N=17 and N=25, plus
a variance decomposition of the paired per-task differences at N=25. They have no JSON record of
their own; their criterion is the sentence that states them in `docs/2_GOAL.md#r1-capability-parity`, which
is read
here and compared digit for digit, so a record and a recomputation cannot drift apart silently.

Exit 0 only when every printed value equals the value recorded at campaign time. A missing
input, a zero-row input or a short sample stops the run with one named line naming the input
and the count it wanted, before any number is printed: the campaign's readers return `[]` for
an absent file, and a silently short home reports a different experiment (with `n17` absent,
R1 reads delta +0.06 over 680 rows instead of -0.320 over 1000).
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True  # the analyzers are read-only inputs; importing one must not
                                # leave a __pycache__ in the campaign's directory

REPO = Path(__file__).resolve().parent
PROJ = REPO / "bench" / "projection" / "wave1" / "final"
ANALYSIS = REPO / "bench" / "analysis" / "wave1"
R2_ARMS = ("dev-only", "own-test-only", "own-iv", "own-review", "full")
# R2 ran in four batches (`c1`..`c4`), each carrying all five arms; the 40 tasks x 3 seeds of
# an arm are spread over the batches.
R2_CELLS = ("c1", "c2", "c3", "c4")
R3_ARMS = ("leaf", "tree-greedy", "tree-tournament")
R3_SEEDS = (1, 2, 3, 4, 5)
R1_SEEDS, R1_TASKS, R1_ROWS = 25, 40, 1000
R2_ROWS_PER_ARM, R2_ROWS = 120, 600
R3_RUNS_PER_ARM = 70


class Fail(Exception):
    """A named stop: printed on one line, and nothing else is printed."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def need_file(path: Path, wanted: str) -> None:
    if not path.is_file():
        raise Fail(f"missing input: {rel(path)} — file not found, wanted {wanted}")


def need_rows(path: Path, rows: int, wanted: str, what: str) -> None:
    if rows == 0:
        raise Fail(f"empty input: {rel(path)} — 0 rows read, wanted {wanted}; {what}")


# --------------------------------------------------------------------------------------------
# R1 — preflight derives the expected input set from the analyzer's own reads
# --------------------------------------------------------------------------------------------
def r1_inputs() -> tuple[list[dict], list[dict], dict[str, int]]:
    sys.path.insert(0, str(ANALYSIS / "n25"))
    import analyze_n25 as an  # the campaign's own script, unmodified

    an.PRIOR, an.N9, an.N17, an.N25 = PROJ / "our-n5", PROJ / "n9", PROJ / "n17", PROJ / "n25"
    requested: dict[str, int] = {}
    original = an.read_jsonl

    def spy(path: Path) -> list[dict]:
        rows = original(path)
        requested[str(path)] = requested.get(str(path), 0) + len(rows)
        return rows

    an.read_jsonl = spy
    ours, pi = an.collect(R1_SEEDS)
    an.read_jsonl = original
    return ours, pi, requested


def preflight_r1() -> None:
    ours, pi, requested = r1_inputs()
    if not requested:
        raise Fail(f"empty input: {rel(PROJ)} — the R1 analysis read no file at all")
    per_seed: dict[tuple[str, int], int] = {}
    for row in ours:
        per_seed[("a", row["seed"])] = per_seed.get(("a", row["seed"]), 0) + 1
    for row in pi:
        per_seed[("b", row["seed"])] = per_seed.get(("b", row["seed"]), 0) + 1
    for path, rows in requested.items():
        if rows:
            continue
        present = Path(path).is_file()
        raise Fail(f"{'empty' if present else 'missing'} input: {rel(Path(path))} — "
                   f"{'0 rows read' if present else 'file not found'}, wanted the rows of one "
                   f"lane of one seed ({R1_TASKS} rows per seed across the four lanes)")
    for arm, label in (("a", "ours"), ("b", "pi")):
        total = sum(per_seed.get((arm, s), 0) for s in range(1, R1_SEEDS + 1))
        for seed in range(1, R1_SEEDS + 1):
            got = per_seed.get((arm, seed), 0)
            if got != R1_TASKS:
                raise Fail(f"short sample: R1 arm {arm} ({label}) seed {seed} — {got} rows, "
                           f"wanted {R1_TASKS} (40 tasks, four lanes); arm {arm} then has "
                           f"{total} of {R1_ROWS}")
        if total != R1_ROWS:
            raise Fail(f"short sample: R1 arm {arm} ({label}) — {total} rows, wanted {R1_ROWS} "
                       f"({R1_SEEDS} seeds x {R1_TASKS} tasks)")


def compute_r1() -> dict:
    sys.path.insert(0, str(ANALYSIS / "n25"))
    import analyze_n25 as an

    an.PRIOR, an.N9, an.N17, an.N25 = PROJ / "our-n5", PROJ / "n9", PROJ / "n17", PROJ / "n25"
    res = an.build(R1_SEEDS)
    record = json.loads((ANALYSIS / "n25" / "analysis-n25-final.json").read_text())
    differing = [k for k in record if _norm(res.get(k)) != _norm(record[k])]
    if differing:
        raise Fail("R1 recomputed from the projection differs from "
                   f"{rel(ANALYSIS / 'n25' / 'analysis-n25-final.json')} in {differing}")
    return res


def compute_widths() -> dict:
    """§3's interval-width argument, derived and gated against the record that states it.

    The campaign recorded these quantities as a sentence in `docs/2_GOAL.md` and never as a
    record of their own, so the draft used to list them as numbers no command re-derives. They
    are one analyzer run per N plus a variance decomposition; `interval_widths.py` in the
    campaign's analysis directory owns the arithmetic and `interval-widths.json` its digits.
    This function recomputes, requires the committed record to agree, and requires the record's
    sentence in `docs/2_GOAL.md` to agree digit for digit — a record and a recomputation cannot
    drift apart without stopping the run.
    """
    sys.path.insert(0, str(ANALYSIS / "n25"))
    import interval_widths as iw  # the derivation, kept beside the analyzer it runs

    got = iw.compute()
    record = ANALYSIS / "n25" / "interval-widths.json"
    if not record.is_file():
        raise Fail(f"missing input: {rel(record)} — file not found, wanted the width derivation")
    recorded = json.loads(record.read_text(encoding="utf-8"))
    if recorded != got:
        differing = sorted(k for k in set(recorded) | set(got) if recorded.get(k) != got.get(k))
        raise Fail(f"width derivation differs from {rel(record)} in {differing}")
    if got["verdicts"] != ["INCONCLUSIVE"]:
        raise Fail(f"width sweep no longer returns one verdict over N=17..25: {got['verdicts']}")
    stated = width_sentence()
    recomputed = [f"{got['half_width_at_n25']:.1f}", f"{got['n']['17']['width']:.2f}",
                  f"{got['n']['25']['width']:.2f}", f"{got['within_share_pct']:.1f}",
                  f"{got['asymptotic_width']:.1f}", f"{got['needed_estimate']:.1f}"]
    if stated != recomputed:
        raise Fail(f"R1 widths: recomputed {recomputed} but docs/2_GOAL.md states {stated}")
    return got


def width_sentence() -> list[str]:
    """The six numbers `docs/2_GOAL.md` states for the width argument, in its order.

    The campaign's own statement is the criterion, so it is read rather than trusted: the
    paragraph is found by its opening words and every backticked quantity in it is taken.
    """
    path = REPO / "docs" / "2_GOAL.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if "did not resolve it" in ln and "Why N=" in ln), None)
    if start is None:
        raise Fail(f"unreadable record: {rel(path)} no longer states why N did not resolve it")
    para: list[str] = []
    for ln in lines[start:]:
        if not ln.strip() and para:
            break
        para.append(ln)
    tokens = re.findall(r"`([^`]+)`", " ".join(para))
    stated = [t.strip("~+%") for t in tokens if re.fullmatch(r"[~+]?\d+(?:\.\d+)?%?", t)]
    if len(stated) != 6:
        raise Fail(f"unreadable record: {rel(path)} states {len(stated)} width numbers, "
                   f"wanted 6 (half-width, width at N=17, width at N=25, within share, "
                   f"asymptotic width, estimate needed): {stated}")
    return stated


def _norm(value: object) -> object:
    """JSON round-trip so tuples and lists compare equal (`seed_totals` is a list of pairs)."""
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value


# --------------------------------------------------------------------------------------------
# R2 — the campaign's analyzer runs as its own process, writing into a temp directory
# --------------------------------------------------------------------------------------------
def preflight_r2() -> None:
    per_arm: dict[str, int] = {}
    for cell in R2_CELLS:
        for arm in R2_ARMS:
            path = PROJ / "r2" / "runs" / cell / arm / arm / "results.jsonl"
            need_file(path, f"{R2_ROWS_PER_ARM // len(R2_CELLS)} rows of arm {arm}")
            with path.open(encoding="utf-8") as fh:
                rows = sum(1 for line in fh if line.strip())
            need_rows(path, rows,
                      f"{R2_ROWS_PER_ARM // len(R2_CELLS)} rows (its share of arm {arm}'s "
                      f"{R2_ROWS_PER_ARM})",
                      f"arm {arm} then has {per_arm.get(arm, 0)} of {R2_ROWS_PER_ARM}")
            per_arm[arm] = per_arm.get(arm, 0) + rows
    for arm in R2_ARMS:
        if per_arm[arm] != R2_ROWS_PER_ARM:
            raise Fail(f"short sample: R2 arm {arm} — {per_arm[arm]} rows, wanted "
                       f"{R2_ROWS_PER_ARM} (40 tasks x 3 seeds)")
    if sum(per_arm.values()) != R2_ROWS:
        raise Fail(f"short sample: R2 — {sum(per_arm.values())} rows, wanted {R2_ROWS} "
                   f"(5 arms x 120)")


def compute_r2(tmp: Path) -> dict:
    out, text = tmp / "r2.json", tmp / "r2.txt"
    pattern = str(PROJ / "r2" / "runs" / "*" / "*" / "*" / "results.jsonl")
    proc = subprocess.run(
        [sys.executable, str(ANALYSIS / "r2" / "r2_analyze.py"),
         "--glob", pattern, "--out", str(out), "--text", str(text)],
        cwd=str(REPO), capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0 or not out.is_file():
        raise Fail(f"R2 analyzer exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    recorded_text = (ANALYSIS / "r2" / "analysis.txt").read_text(encoding="utf-8")
    if text.read_text(encoding="utf-8") != recorded_text:
        raise Fail(f"R2 recomputed report differs from {rel(ANALYSIS / 'r2' / 'analysis.txt')}"
                   " — the recorded text is the criterion")
    got = json.loads(out.read_text(encoding="utf-8"))
    recorded = json.loads((ANALYSIS / "r2" / "analysis.json").read_text(encoding="utf-8"))
    if got != recorded:
        raise Fail(f"R2 recomputed JSON differs from {rel(ANALYSIS / 'r2' / 'analysis.json')}")
    return got


# --------------------------------------------------------------------------------------------
# R3 — run.json records are read by the campaign's analyzer from the projection directory
# --------------------------------------------------------------------------------------------
def r3_tasks() -> list[str]:
    """The 14 graded tasks, read out of `analyze.py` itself (its DECOMP and FORCED lists)."""
    tree = ast.parse((ANALYSIS / "r3" / "analyze.py").read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
                and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in node.value.elts)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = [e.value for e in node.value.elts]
    if "DECOMP" not in found or "FORCED" not in found:
        raise Fail(f"unreadable input: {rel(ANALYSIS / 'r3' / 'analyze.py')} — its DECOMP and "
                   "FORCED task lists are how the 14 graded tasks are named")
    return found["DECOMP"] + found["FORCED"]


def preflight_r3(tasks: list[str]) -> None:
    for arm in R3_ARMS:
        present = 0
        for task in tasks:
            for seed in R3_SEEDS:
                path = PROJ / "r3" / arm / f"{task}-{seed}" / "run.json"
                if not path.is_file():
                    raise Fail(f"missing input: {rel(path)} — file not found, wanted 1 run "
                               f"record; arm {arm} then has {present} of {R3_RUNS_PER_ARM} runs")
                present += 1
        if present != R3_RUNS_PER_ARM:
            raise Fail(f"short sample: R3 arm {arm} — {present} runs, wanted {R3_RUNS_PER_ARM} "
                       f"({len(tasks)} tasks x {len(R3_SEEDS)} seeds)")


def compute_r3() -> str:
    proc = subprocess.run([sys.executable, str(ANALYSIS / "r3" / "analyze.py")],
                          cwd=str(REPO), capture_output=True, text=True,
                          env={"R3": str(PROJ / "r3"), "PATH": "/usr/bin:/bin",
                               "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0:
        raise Fail(f"R3 analyzer exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    recorded = (ANALYSIS / "r3" / "analysis-r3.txt").read_text(encoding="utf-8")
    if proc.stdout != recorded:
        at = _first_diff(proc.stdout, recorded)
        raise Fail(f"R3 recomputed output differs from {rel(ANALYSIS / 'r3' / 'analysis-r3.txt')}"
                   f" at line {at}: {recorded.splitlines()[at - 1].strip()!r} recorded")
    return proc.stdout


def compute_r3_supp() -> str:
    """`supp.py` hardcodes one root; that single line is repointed, nothing else is touched."""
    path = ANALYSIS / "r3" / "supp.py"
    source = path.read_text(encoding="utf-8")
    literal = 'ROOT = Path("/tmp/wave1/final/r3")'
    if source.count(literal) != 1:
        raise Fail(f"unreadable input: {rel(path)} — expected exactly one "
                   f"`{literal}` line, found {source.count(literal)}")
    source = source.replace(literal, f"ROOT = Path({str(PROJ / 'r3')!r})")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(source, str(path), "exec"), {"__name__": "__main__", "__file__": str(path)})
    out = buf.getvalue()
    recorded = (ANALYSIS / "r3" / "supp-r3.txt").read_text(encoding="utf-8")
    if out != recorded:
        raise Fail(f"R3 supplementary output differs from {rel(ANALYSIS / 'r3' / 'supp-r3.txt')}")
    return out


def _first_diff(got: str, want: str) -> int:
    for i, (a, b) in enumerate(zip(got.splitlines(), want.splitlines()), start=1):
        if a != b:
            return i
    return min(len(got.splitlines()), len(want.splitlines())) + 1


# --------------------------------------------------------------------------------------------
# The interface: key order fixed by the paper, values formatted to its table
# --------------------------------------------------------------------------------------------
def graded_line(text: str, pattern: str, what: str) -> re.Match:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise Fail(f"unreadable output: {what} — no line matched {pattern!r}")
    return match


def main() -> int:
    try:
        preflight_r2()
        preflight_r3(r3_tasks())
        preflight_r1()

        r1 = compute_r1()
        widths = compute_widths()
        with tempfile.TemporaryDirectory() as tmp:
            r2 = compute_r2(Path(tmp))
        r3_text = compute_r3()
        supp_text = compute_r3_supp()

        d1 = r1["delta"]
        ladder = r2["ladder"]
        full_iv = r2["pairs"]["full - own-iv"]
        full_rev = r2["pairs"]["full - own-review"]
        counts = {}
        for arm in R3_ARMS:
            match = graded_line(supp_text, rf"^{re.escape(arm)}\s+runs=(\d+) actual=(\d+)/(\d+)",
                                f"supp.py cost line for {arm}")
            counts[arm] = (match.group(2), match.group(3))
            if arm in ("leaf", "tree-greedy"):
                m2 = graded_line(r3_text, rf"^{re.escape(arm)}\s+runs=\d+\s+mean_calls=([\d.]+)",
                                 f"analyze.py arm line for {arm}")
                counts[arm] += (m2.group(1),)

        lines = [
            ("r1_a_mean_tasks", f"{d1['a_mean_tasks']:.3f}"),
            ("r1_b_mean_tasks", f"{d1['b_mean_tasks']:.3f}"),
            ("r1_delta_tasks", f"{d1['delta_tasks']:.3f}"),
            ("r1_lo95", f"{d1['lo95']:.3f}"),
            ("r1_hi95", f"{d1['hi95']:.3f}"),
            ("r1_rows_per_arm", f"{r1['ours_n_runs']}"),
            ("r1_shortfall_tasks", f"{-d1['lo95'] - 3.0:.3f}"),
            ("r1_width_n17", f"{widths['n']['17']['width']:.2f}"),
            ("r1_width_n25", f"{widths['n']['25']['width']:.2f}"),
            ("r1_width_min", f"{widths['width_min']:.2f}"),
            ("r1_half_width", f"{widths['half_width_at_n25']:.1f}"),
            ("r1_within_share_pct", f"{widths['within_share_pct']:.1f}"),
            ("r1_asymptotic_width", f"{widths['asymptotic_width']:.1f}"),
            ("r1_needed_estimate", f"{widths['needed_estimate']:.1f}"),
            ("r3_leaf", f"{counts['leaf'][0]}/{counts['leaf'][1]}"),
            ("r3_tree_greedy", f"{counts['tree-greedy'][0]}/{counts['tree-greedy'][1]}"),
            ("r3_tree_tournament", f"{counts['tree-tournament'][0]}/{counts['tree-tournament'][1]}"),
            ("r3_leaf_mean_calls", counts["leaf"][2]),
            ("r3_tree_greedy_mean_calls", counts["tree-greedy"][2]),
            ("r2_arm_dev_only", _arm(ladder, "dev-only")),
            ("r2_arm_own_test", _arm(ladder, "own-test-only")),
            ("r2_arm_own_iv", _arm(ladder, "own-iv")),
            ("r2_arm_own_review", _arm(ladder, "own-review")),
            ("r2_arm_full", _arm(ladder, "full")),
            ("r2_full_minus_own_iv_correctness", f"{full_iv['actual']['delta_tasks']:+.2f}"),
            ("r2_full_minus_own_iv_ci", f"[{full_iv['actual']['lo95']:.2f},"
                                        f"{full_iv['actual']['hi95']:.2f}]"),
            ("r2_full_minus_own_iv_p", f"{full_iv['actual']['mcnemar_exact_p']:.3f}"),
            ("r2_full_minus_own_review_claimed", f"{full_rev['claimed']['delta_tasks']:+.2f}"),
            ("r2_full_minus_own_review_false", f"{full_rev['false_success']['delta_tasks']:+.2f}"),
        ]
    except Fail as exc:
        print(f"reproduce: {exc}", file=sys.stderr)
        return 1
    wanted = sys.argv[1:]
    if wanted:
        known = {key for key, _ in lines}
        missing = [key for key in wanted if key not in known]
        if missing:
            print(f"reproduce: unknown key: {', '.join(missing)} — printed keys are "
                  f"{', '.join(sorted(known))}", file=sys.stderr)
            return 1
        lines = [(key, value) for key, value in lines if key in wanted]
    for key, value in lines:
        print(f"{key} {value}")
    return 0


def _arm(ladder: dict, arm: str) -> str:
    block = ladder[arm]
    return f"{block['actual']['true']}/{block['n_runs']}"


if __name__ == "__main__":
    raise SystemExit(main())
