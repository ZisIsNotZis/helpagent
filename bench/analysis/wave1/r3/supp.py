"""Supplementary reads of the r3 run records (mechanism breakdown, per-task firing,
fired-subset delta, cost). Read-only; writes nothing. The primary statistics are the
design's own §5.4 script, whose output is analysis-r3.txt."""
import json, os
from pathlib import Path

ROOT = Path("/tmp/wave1/final/r3")
DECOMP = ["T-31-parameter-threading", "T-33-serializer-contract",
          "T-28-plugin-registry-scaffold", "T-21-swallowed-corruption",
          "T-34-expression-tokenizer", "T-32-sliding-window-limiter",
          "T-03-wrong-comparison", "T-11-wrong-exception-type",
          "T-12-str-enum-compare"]
FORCED = ["T-14-add-export-sorting", "T-26-plan-dataclass-port", "T-02-off-by-one",
          "T-20-average-truncation", "T-06-tz-naive-compare"]


def walk(node):
    if not isinstance(node, dict):
        return
    yield node
    for c in node.get("children") or []:
        yield from walk(c)


def load(arm):
    rows = {}
    for p in sorted((ROOT / arm).glob("*/run.json")):
        task, _, seed = p.parent.name.rpartition("-")
        r = json.loads(p.read_text())
        cases, forced = {}, 0
        for nd in walk(r.get("nodes")):
            for c in nd.get("candidates") or []:
                k = c.get("how_case") or "unknown"
                cases[k] = cases.get(k, 0) + 1
            if (nd.get("allocation") or {}).get("forced"):
                forced += 1
        rows[(task, int(seed))] = dict(actual=bool(r["actual"]), claimed=bool(r["claimed"]),
                                       calls=int(r["calls"]), wall=float(r.get("run_wall_s") or 0),
                                       cases=cases, forced=forced,
                                       fired=cases.get("decomposed-How", 0) > 0)
    return rows


arms = {a: load(a) for a in ("leaf", "tree-greedy", "tree-tournament")}

print("== per-task mechanism firing (decomposed-How runs out of 5 seeds) ==")
print(f"{'task':34s} {'group':10s} {'greedy':>8s} {'tourn':>8s}  how_case mixes (greedy | tournament)")
for t in DECOMP + FORCED:
    g = [v for (tt, _), v in arms["tree-greedy"].items() if tt == t]
    n = [v for (tt, _), v in arms["tree-tournament"].items() if tt == t]
    gf = sum(1 for v in g if v["fired"])
    nf = sum(1 for v in n if v["fired"])
    gc, nc = {}, {}
    for v in g:
        for k, c in v["cases"].items():
            gc[k] = gc.get(k, 0) + c
    for v in n:
        for k, c in v["cases"].items():
            nc[k] = nc.get(k, 0) + c
    grp = "DECOMP" if t in DECOMP else "FORCED"
    print(f"{t:34s} {grp:10s} {gf:8d} {nf:8d}  {gc} | {nc}")

print("\n== guard: allocation.forced nodes and forced-leaf how_case, per task ==")
for t in FORCED:
    for a in ("tree-greedy", "tree-tournament"):
        runs = [v for (tt, _), v in arms[a].items() if tt == t]
        fl = sum(1 for v in runs if "forced-leaf" in v["cases"])
        fnode = sum(v["forced"] for v in runs)
        print(f"  {t:34s} {a:16s} forced-leaf-case runs={fl}/5  forced-nodes={fnode}")

print("\n== fired-subset delta (tasks where the arm's mechanism actually decomposed) ==")
for a in ("tree-greedy", "tree-tournament"):
    fired_tasks = [t for t in DECOMP + FORCED
                   if any(v["fired"] for (tt, _), v in arms[a].items() if tt == t)]
    print(f"{a}: tasks with >=1 decomposed-How run: {len(fired_tasks)} -> {fired_tasks}")
    for t in fired_tasks:
        lr = [v["actual"] for (tt, _), v in arms["leaf"].items() if tt == t]
        tr = [v["actual"] for (tt, _), v in arms[a].items() if tt == t]
        print(f"    {t:34s} leaf={sum(lr)/len(lr):.2f} {a}={sum(tr)/len(tr):.2f}")

print("\n== cost ==")
for a, rows in arms.items():
    n = len(rows)
    print(f"{a:16s} runs={n} actual={sum(v['actual'] for v in rows.values())}/{n} "
          f"claimed={sum(v['claimed'] for v in rows.values())}/{n} "
          f"false_success={sum(1 for v in rows.values() if v['claimed'] and not v['actual'])} "
          f"mean_calls={sum(v['calls'] for v in rows.values())/n:.1f} "
          f"total_calls={sum(v['calls'] for v in rows.values())} "
          f"mean_wall_s={sum(v['wall'] for v in rows.values())/n:.0f} "
          f"total_wall_s={sum(v['wall'] for v in rows.values()):.0f}")

print("\n== leaf token capture (tree arms have no trajectory.jsonl) ==")
for a in arms:
    tdirs = list((ROOT / a).glob("*/trajectory.jsonl"))
    print(f"{a:16s} trajectory.jsonl present in {len(tdirs)}/{len(arms[a])} runs")
