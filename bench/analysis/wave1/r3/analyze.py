import json, os, random
from math import comb
from pathlib import Path

ROOT = Path(os.environ["R3"])
BOOT_N, BOOT_SEED = 10_000, 20261013
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


def how_cases(nodes):
    out = {}
    for nd in walk(nodes):
        for c in nd.get("candidates") or []:
            k = c.get("how_case") or "unknown"
            out[k] = out.get(k, 0) + 1
    return out


def read_arm(name):
    rows = {}
    for p in sorted((ROOT / name).glob("*/run.json")):
        task, _, seed = p.parent.name.rpartition("-")
        r = json.loads(p.read_text())
        nodes = r.get("nodes")
        rows[(task, int(seed))] = {
            "actual": bool(r["actual"]), "claimed": bool(r["claimed"]),
            "calls": int(r["calls"]), "wall": float(r.get("run_wall_s") or 0.0),
            "how_cases": how_cases(nodes),
            "forced_nodes": sum(1 for nd in walk(nodes)
                               if (nd.get("allocation") or {}).get("forced")),
            "fired": how_cases(nodes).get("decomposed-How", 0) > 0,
        }
    return rows


def rate(rows, tasks, field="actual"):
    out = {}
    for t in tasks:
        vals = [v[field] for (tt, _), v in rows.items() if tt == t]
        out[t] = sum(vals) / len(vals) if vals else float("nan")
    return out


def false_success(rows):
    return {k: bool(v["claimed"]) and not v["actual"] for k, v in rows.items()}


def boot(d, n=BOOT_N, seed=BOOT_SEED, alpha=0.05):
    d = [x for x in d if x == x]
    if not d:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    m = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return sum(d) / len(d), m[int(alpha / 2 * n)], m[int((1 - alpha / 2) * n) - 1]


def mcnemar(pairs):
    b = sum(1 for a, c in pairs if c and not a)
    c_ = sum(1 for a, c in pairs if a and not c)
    n = b + c_
    if n == 0:
        return b, c_, 1.0
    return b, c_, min(1.0, sum(comb(n, i) for i in range(min(b, c_) + 1)) * 0.5 ** n * 2)


arms = {n: read_arm(n) for n in ("leaf", "tree-greedy", "tree-tournament")}
for n, r in arms.items():
    print(f"{n:16s} runs={len(r)}  "
          f"mean_calls={sum(v['calls'] for v in r.values())/max(1, len(r)):.1f}  "
          f"mean_wall_s={sum(v['wall'] for v in r.values())/max(1, len(r)):.0f}  "
          f"false_success={sum(false_success(r).values())}")
for n in ("tree-greedy", "tree-tournament"):
    r, cases = arms[n], {}
    for v in r.values():
        for k, c in v["how_cases"].items():
            cases[k] = cases.get(k, 0) + c
    print(f"{n:16s} decomposition_fired_runs={sum(1 for v in r.values() if v['fired'])}  "
          f"forced_leaf_nodes={sum(v['forced_nodes'] for v in r.values())}  "
          f"how_cases={cases}")

for arm in ("tree-greedy", "tree-tournament"):
    print(f"\n=== {arm} vs leaf ===")
    for label, tasks in (("DECOMPOSABLE", DECOMP), ("FORCED-LEAF (overhead)", FORCED)):
        if not any(any(tt == t for tt, _ in arms["leaf"]) for t in tasks):
            print(f"{label}: no leaf runs found; skipped")
            continue
        lrate, trate = rate(arms["leaf"], tasks), rate(arms[arm], tasks)
        mean, lo, hi = boot([trate[t] - lrate[t] for t in tasks])
        lfalse, tfalse = false_success(arms["leaf"]), false_success(arms[arm])
        keys = sorted(k for k in set(arms["leaf"]) & set(arms[arm]) if k[0] in tasks)
        fdiff = boot([float(tfalse.get(k, False)) - float(lfalse.get(k, False))
                      for k in keys])
        b, c_, p = mcnemar([(arms["leaf"][k]["actual"], arms[arm][k]["actual"])
                            for k in keys])
        print(f"{label:22s} n_tasks={len(tasks)} mean_d={mean:+.3f} "
              f"95%CI=[{lo:+.3f},{hi:+.3f}] tree-only-fix={b} leaf-only-fix={c_} "
              f"McNemar_p={p:.3f} false_success_d={fdiff[0]:+.3f} "
              f"(CI [{fdiff[1]:+.3f},{fdiff[2]:+.3f}])")
        for t in tasks:
            print(f"    {t:34s} leaf={lrate[t]:.2f} tree={trate[t]:.2f} "
                  f"d={trate[t]-lrate[t]:+.2f}")
