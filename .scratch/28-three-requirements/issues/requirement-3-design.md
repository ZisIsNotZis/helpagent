# Requirement 3 design — decomposition / multi-approach / step-splitting

READ-ONLY investigation. No code was modified, no model was run. This file is the only
output. Revision inspected: `45ebb32` (`git rev-parse --short HEAD`). Every claim below
names a file:line or a run record on disk.

**Question.** Does ANY decomposition / step-splitting / multi-approach mechanism in the
CURRENT code plausibly and measurably help on this corpus? If yes, what is the exact
runnable experiment? If no, say so plainly.

## 0. Verdict up front

1. **Four toggles exist today** (§1). Exactly **one** is the default: greedy single-How
   with node-into-children splitting enabled and the forced-leaf guard at 3 files / 3 ACs.
2. **None of the four has ever been measured on `45ebb32`.** The only decomposition
   measurements on record are from `66e9708` (2026-09-30, six tasks, N=1) and they are
   negative (§3).
3. **The guard structurally forbids decomposition on 21 of the 35 corpus tasks** (§4.1):
   `files <= 3 AND acs <= 3` forces a leaf. Two of the five tasks the forensics predicted
   would benefit (T-14, T-26) are in that set. Only **14/35** tasks can even reach a
   child split.
4. **A positive delta is plausible on 2–4 tasks only** (T-31, T-33, weakly T-28/T-21).
   Everywhere else the arm comparison measures planning overhead, not decomposition.
5. **The experiment is runnable as written** (§5) with a bash loop over the existing
   per-task drivers plus a self-contained analysis script — **but** a multi-task tree
   sweep driver and tree token capture do not exist, and the forced-leaf thresholds are
   not tunable without a code change (§7).
6. **Honest expectation: negative or inconclusive.** The prior measurement
   (tree actual 1/6 vs leaf 6/12 at ~5× the calls) and STATUS §3/§1a predict that this
   mechanism buys calls, not fixes. The experiment is worth running only as a bounded,
   pre-registered falsification of that expectation.

---

## 1. What decomposition toggles exist TODAY, and what each does

| # | toggle | where (file:line) | what it actually does | default | CLI-tunable |
| --- | --- | --- | --- | --- | --- |
| 1 | **greedy single-How** | `harness/tree_run.py:1429` (`greedy = ctx.how_explore <= 1`); funding path `harness/tree_run.py:1460-1470`; field default `harness/tree_run.py:869`; `run_tree` param `harness/tree_run.py:2336`; CLI default `bench/v2_tree.py:536` | Plan a ranked How list (ONE `how_list` call, `harness/tree_run.py:1134`), take the top-ranked How, reserve the whole node pool for that ONE candidate, run it in its own isolated copy. A second candidate opens only on manager-driven sequential retry. | **YES** (`how_explore=1`) | `--how-explore 1` |
| 2 | **parallel candidate tournament** (`how_explore > 1`) | `harness/tree_run.py:1426` (`parallel_limit = min(max(1, ctx.how_explore), budget_cap)`); winner chosen by `harness/how.py:523` (`pick`) over `harness/how.py:493` (`select_key`); budget ceiling `harness/how.py:727` (`how_exploration_limit`); CLI `bench/v2_tree.py:536` | Open up to N How candidates in parallel, each with its own decomposition + isolated copy, and pick the winner by the deterministic `(tests, review, rank, cost)` key — never a model vote. | no | `--how-explore N` (N≥2) |
| 3 | **node-into-children splitting** | plan: `harness/node.py:596` (`plan_node`) → `harness/node.py:206` (`decomposition_from_envelope`), gated by `harness/node.py:308` (`validate_decomposition`); applied at `harness/tree_run.py:1488-1502` (`decomp.children` non-empty → `harness/tree_run.py:1237` `_apply_decomposition` → `harness/tree_run.py:2144` `_attempt_internal`); repeat-refusal `harness/node.py:498` (`SplitHistory.accept`); node-level gate `harness/tree_run.py:1918` (`spec.kind == "internal" and depth < ctx.depth_cap and can_decompose(...)`); `harness/node.py:449` (`can_decompose`) | ONE `plan_node` call per How returns children. Each child is a node with its own goal/files/ACs and its own write boundary (`harness/tree_run.py:736` `leaf_spec_from`); children recurse via `run_node`; ≥2 writing descendants require a machine-verified integration verdict (`harness/tree_run.py:802`, `harness/tree_run.py:982`). | **enabled** (on for any node the guard allows) | no on/off flag; splitting is always ATTEMPTED unless the guard (§1.4) forces a leaf |
| 4 | **forced-leaf thresholds** | constants `harness/tree_run.py:169-170` (`FORCED_LEAF_MAX_FILES = 3`, `FORCED_LEAF_MAX_ACS = 3`); decision `harness/tree_run.py:1341` `_allocation_guard`, lines `1359-1360` (`small = files <= 3 and acs <= 3`; `forced = would and small`); applied `harness/tree_run.py:1475-1487` | A deterministic ALLOCATION guard, not a model decision: if the node's OWN `spec.files` ≤ 3 AND `spec.acs` ≤ 3, a decomposition that would create children is REFUSED and the How runs as a single monolithic leaf. Both must hold to force. The comment at `harness/tree_run.py:166-168` says the numbers are "EXPECTED TO BE TUNED from measurements". | **active, 3 / 3** | no (module constants only) |
| 4b | (adjacent, not decomposition) sequential How retries | `harness/tree_run.py:177` (`SEQUENTIAL_HOW_LIMIT = 3`), `harness/tree_run.py:1427-1428` | Greedy is sequential, not inert: a failed How goes to the manager, which may say `continue-with-next-how` / `author-a-new-how`. Costs calls, changes no structure. | active (manager ON by default) | `--no-manager` disables the retry driver |

**How the four combine at the root.** `bench/v2_tree.py:176` (`build_root`) declares the
root `kind="internal"` with `files = source_only(task["files"])` — i.e. **every source file
of the task, including `README.md` and every `__init__.py`** — and `acs = extract_acs(...)`.
So toggle 4's file count is the whole repo's source surface, not the plan's declared files.
A root that clears the guard: `how_list` (1 call) → `plan_node` (1–2 calls) → one of four
`how_case` outcomes, recorded per candidate at `harness/tree_run.py:1480/1498/1504/1515`:
`forced-leaf`, `decomposed-How`, `leaf-How` (zero children), `fallback-leaf-How` (unusable
plan). Only `decomposed-How` actually exercises toggle 3.

---

## 2. Which is the default

The default is **greedy single-How + node-into-children + the 3/3 forced-leaf guard**
(toggles 1, 3, 4). Evidence:

* `harness/tree_run.py:869` — `_TreeContext.how_explore: int = 1`.
* `harness/tree_run.py:2336` — `run_tree(..., how_explore: int = 1)`.
* `bench/v2_tree.py:536` — `--how-explore` default `1`.
* `harness/tree_run.py:1429` — `greedy = ctx.how_explore <= 1`.
* `harness/tree_run.py:169-170` — the guard constants, applied unconditionally at
  `harness/tree_run.py:1475`.
* `harness/tree_run.py:1918` — decomposition is attempted (not forced off) whenever the
  node is internal, within depth cap, and can fund two leaves.
* `bench/v2_tree.py:534-535` — `--manager` default ON (the sequential retry driver).

The tournament (toggle 2) is **not** the default and is documented as opt-in at
`harness/tree_run.py:1424-1429` and `bench/v2_tree.py:508-509`.

---

## 3. What has NEVER been measured on `45ebb32`

`find bench -type d -name 'v2tree-*'` returns exactly six directories, all evidence runs
dated `20260930T*` under `bench/runs/evidence/` — i.e. **before** `66e9708` ("greedy-by-
default Hows, sequential retries, forced-leaf guard", 2026-09-30 20:09 +0800), and long
before `45ebb32` (2026-10-13). No `how_explore` key appears in any record under
`bench/runs/` (`grep -rl how_explore bench/runs/` → empty), so no run has ever been
persisted through the tree driver on the current revision.

| toggle | measured anywhere? | measured on `45ebb32`? |
| --- | --- | --- |
| 1 greedy single-How (tree) | YES, once: `66e9708` commit message A/B — greedy tree on T-02 parked at **22 calls / 70 s** while a paired plain leaf **fixed** it in **11 calls / 29 s**; a T-05 tree run was a **false success** | **never** |
| 2 tournament (`how_explore>1`) | YES, at the pre-`2c` revision: ticket 20 / `.scratch/20-how-scaling/issues/20-how-scaling.md:125-146` — 6 tasks, N=1, **actual 1/6**, 231 calls, 1670 s (mean 278 s, ~38 calls) vs leaf-only **6/12** at ~7 calls, ~20 s; recorded in STATUS §3 as "works, but ~5× the calls and wall time for fewer fixes" | **never** |
| 3 node-into-children splitting | ONLY as part of the same 6-task run (the planner did emit children; `20-how-scaling.md:120-124` retracts ticket 18's "the planner never decomposes" as a grammar artifact). **No arm isolates decomposition from the How axis.** | **never** |
| 4 forced-leaf thresholds | **never** — `harness/tree_run.py:166-168` states the numbers are expected to be tuned from measurements; no such measurement exists in `bench/runs/`, `docs/STATUS.md` §3, or any `.scratch/20-how-scaling` record | **never** |

The historical record in one table (`bench/runs/evidence/v2tree-20260930T*/T-*/run.json`,
revision `66e9708`, N=1, 48-call budget):

| task | claimed | actual | quadrant | calls | stop | guard fields present? |
| --- | --- | --- | --- | --- | --- | --- |
| T-02-off-by-one | F | F | honest-failure | 47 | parked (`calls`) | no (`allocation` absent) |
| T-05-mutable-default | F | F | honest-failure | 25 | parked (`ladder`) | no |
| T-14-add-export-sorting | F | F | honest-failure | 49 | parked (`verification-required`) | no |
| T-20-average-truncation | T | T | true-success | 14 | closed (`green`) | no |
| T-31-parameter-threading | F | F | honest-failure | 42 | parked (`ladder`) | no |
| T-33-serializer-contract | F | F | honest-failure | 54 | parked (`calls`) | no |

**Conclusion:** the current tree configuration (`45ebb32`) has never been run against the
corpus at all. Every historical verdict describes a different code revision.

---

## 4. Where a positive delta is even plausible

### 4.1 The measured guard table (this revision)

Derived by calling the drivers' own functions (command in §5.6, run read-only, no model):

* `files` = `len(source_only(task["files"]))` — exactly what `bench/v2_tree.py:176`
  (`build_root`) hands the root `NodeSpec`, and therefore exactly what
  `harness/tree_run.py:1356` counts.
* `acs` = `len(extract_acs(task["request"]))` — `harness/tree_run.py:1357`.

| task | files | acs | guard verdict (files≤3 AND acs≤3 → forced) |
| --- | --- | --- | --- |
| T-01-ttl-seconds-ms | 4 | 3 | CAN DECOMPOSE |
| T-03-wrong-comparison | 3 | 5 | CAN DECOMPOSE |
| T-05-mutable-default | 3 | 4 | CAN DECOMPOSE |
| T-07-f-string-sql | 3 | 4 | CAN DECOMPOSE |
| T-09-add-rate-limit-hook | 3 | 4 | CAN DECOMPOSE |
| T-11-wrong-exception-type | 4 | 3 | CAN DECOMPOSE |
| T-12-str-enum-compare | 4 | 3 | CAN DECOMPOSE |
| T-17-log-hour-format | 3 | 4 | CAN DECOMPOSE |
| T-21-swallowed-corruption | 4 | 3 | CAN DECOMPOSE |
| T-28-plugin-registry-scaffold | 2 | 4 | CAN DECOMPOSE |
| T-31-parameter-threading | 7 | 3 | CAN DECOMPOSE |
| T-32-sliding-window-limiter | 3 | 4 | CAN DECOMPOSE |
| T-33-serializer-contract | 5 | 3 | CAN DECOMPOSE |
| T-34-expression-tokenizer | 3 | 5 | CAN DECOMPOSE |
| **T-14-add-export-sorting** | **3** | **3** | **FORCED-LEAF** |
| **T-26-plan-dataclass-port** | **3** | **3** | **FORCED-LEAF** |
| T-02, T-04, T-06, T-08, T-10, T-13, T-15, T-16, T-18, T-19, T-20, T-22, T-23, T-24, T-25, T-27, T-29, T-30, T-35 | 3 | ≤3 | FORCED-LEAF (19 more) |

Totals: **14 can decompose / 21 forced.** Note that `README.md` and `__init__.py` count as
"files", which is why T-14 and T-26 land at exactly 3 and are forced despite being
multi-behaviour requests (`.scratch/28-three-requirements/issues/verification-decomposition-forensics.md`
§4.4 predicted a delta on both).

### 4.2 The plausible-delta set

Forensics §4.4 names T-31, T-33, T-28, T-14, T-26 as the multi-part tail. Cross-referenced
with §4.1:

| task | forensics shape | guard today | plausible? |
| --- | --- | --- | --- |
| T-31-parameter-threading | 3 ACs / 4 real files; `send()`→`fetch()`→service+bulk | can decompose (7) | **yes** — the one genuinely multi-file chain |
| T-33-serializer-contract | serializer contract with a frozen base | can decompose (5) | **weak** — already fixed by the coverage gate (STATUS §4.4/§8f) |
| T-28-plugin-registry-scaffold | module API documented in the repo README | can decompose (acs=4) | **weak** — failure is "delivered nothing", arguably a planning/attempt defect, not a split defect |
| T-14-add-export-sorting | two documented behaviours in one request | **FORCED** | no — needs a threshold change first |
| T-26-plan-dataclass-port | dataclass port must keep dict access | **FORCED** | no — needs a threshold change first |
| T-21-swallowed-corruption | 4 files / 3 ACs | can decompose | control (both bands) |

**Plain statement.** On this corpus only **two** tasks (T-31, T-33) have a multi-file body
that a child split could address, and the forensics' other three candidates are either
already fixed by a deterministic gate or blocked by the guard. Everything else in the
corpus is a single-artifact bugfix or a small contract addition that the monolithic leaf
already passes (STATUS §8g: the `full` leaf arm fixes 26/40; nothing about
T-31/T-33 suggests a child boundary the model cannot already write in one attempt —
`leaf.py` writes every file in the envelope per attempt, forensics §4.3).

---

## 5. The exact runnable experiment

### 5.1 Arms

| arm | what runs | command driver |
| --- | --- | --- |
| **B0 monolithic leaf** | today's leaf (`harness/leaf.py::run_leaf` straight from the CLI) — one write unit, no planning, no children | `bench/v2_leaf.py` |
| **B1 tree, greedy** | default tree: `how_list` + top How + guard + node-into-children | `bench/v2_tree.py --how-explore 1` |
| **B2 tree, tournament** | same tree but parallel candidates picked by `harness/how.py::pick` | `bench/v2_tree.py --how-explore 3` |

B0 is the exact object R3 must beat. B1 isolates "planning + the guard + children". B2
isolates "multi-approach exploration" on top of B1. There is no fourth runnable arm: the
forced-leaf thresholds have no CLI/env override (§1.4, §7.3), so a threshold sweep is out
of this task's READ-ONLY authority.

### 5.2 Task set (14 tasks)

| group | tasks | why |
| --- | --- | --- |
| decomposable tail (R3 hypothesis) | `T-31-parameter-threading T-33-serializer-contract T-28-plugin-registry-scaffold T-21-swallowed-corruption T-34-expression-tokenizer T-32-sliding-window-limiter` | the multi-part/tail candidates among the 14 tasks the guard lets decompose (§4.1) |
| forced-leaf, forensics' predicted beneficiaries | `T-14-add-export-sorting T-26-plan-dataclass-port` | shows the guard blocks the hypothesis; measures overhead only |
| forced-leaf controls | `T-02-off-by-one T-20-average-truncation T-06-tz-naive-compare` | T-02 is the historical loss, T-20 the historical win; guard binds → expect ~0 |
| decomposable easy/mid regression controls | `T-03-wrong-comparison T-11-wrong-exception-type T-12-str-enum-compare` | the leaf passes these; the tree must not regress them |

### 5.3 Commands (bash, one lane, equal budget)

```sh
cd /home/z/vibe/helpagent
test "$(git rev-parse --short HEAD)" = "45ebb32" || echo "WARNING: not the pinned revision"
git status --porcelain --untracked-files=no   # must print nothing (one writer, clean tree)
curl -fsS --max-time 3 http://127.0.0.1:8834/health   # must answer {"status":"ok"}

R3=bench/runs/r3-$(date -u +%Y%m%dT%H%M%SZ)
TASKS="T-31-parameter-threading T-33-serializer-contract T-28-plugin-registry-scaffold \
T-21-swallowed-corruption T-34-expression-tokenizer T-32-sliding-window-limiter \
T-14-add-export-sorting T-26-plan-dataclass-port \
T-02-off-by-one T-20-average-truncation T-06-tz-naive-compare \
T-03-wrong-comparison T-11-wrong-exception-type T-12-str-enum-compare"
N=5            # independent stochastic repeats; LlamaServerRunner has NO seed
CALLS=48       # equal TOTAL call budget for every arm (leaf default is 24, tree 48)
DEADLINE=1     # equal wall deadline, hours, for every arm
SRV=http://127.0.0.1:8834   # the 32k server; the 8k server throttles T-31 (STATUS §1a/§8)

# ---- B0: monolithic leaf ----
for t in $TASKS; do for i in $(seq 1 $N); do
  mkdir -p $R3/leaf
  uv run python bench/v2_leaf.py --task bench/corpus/$t --server $SRV \
     --calls $CALLS --deadline-hours $DEADLINE --verify full \
     --out $R3/leaf/$t-$i > $R3/leaf/$t-$i.log 2>&1 || true
done; done

# ---- B1: tree greedy (default) ----
for t in $TASKS; do for i in $(seq 1 $N); do
  mkdir -p $R3/tree-greedy
  uv run python bench/v2_tree.py --task bench/corpus/$t --server $SRV \
     --calls $CALLS --deadline-hours $DEADLINE --how-explore 1 \
     --out $R3/tree-greedy/$t-$i > $R3/tree-greedy/$t-$i.log 2>&1 || true
done; done

# ---- B2: tree tournament ----
for t in $TASKS; do for i in $(seq 1 $N); do
  mkdir -p $R3/tree-tournament
  uv run python bench/v2_tree.py --task bench/corpus/$t --server $SRV \
     --calls $CALLS --deadline-hours $DEADLINE --how-explore 3 \
     --out $R3/tree-tournament/$t-$i > $R3/tree-tournament/$t-$i.log 2>&1 || true
done; done
```

Both drivers write `<out>/run.json` (`bench/v2_leaf.py:972-973`, `bench/v2_tree.py:555-556`)
and both carry `task`, `claimed`, `actual`, `quadrant`, `calls`, `run_wall_s` — so the
loop above produces the pairing key from the directory name `<task>-<seed>`. `|| true` is
required: both `main()` functions exit 1 on a non-`true-success` quadrant
(`bench/v2_leaf.py:975`, `bench/v2_tree.py:558`), which would abort a `set -e` loop.

Arm parity held constant: judge, independent test and review are ON for both drivers
(`bench/v2_leaf.py:943-952`; `bench/v2_tree.py:527-536`), and `--server`, `--calls` and
`--deadline-hours` are passed identically, so the only difference between B0 and B1/B2 is
the tree structure. The one known spec-level asymmetry: the leaf root declares the review
angles `ac-correctness` + `contract-compat` (`bench/v2_leaf.py:318`) while the tree root
declares `end-to-end-behaviour` + `interface-alignment` (`bench/v2_tree.py:203`); a
difference between arms on a review-carried claim must be attributed with that in mind.

### 5.4 Analysis command (self-contained, writes nothing)

Run in the same shell as §5.3 so `$R3` is set (or export it in the environment):

```sh
cd /home/z/vibe/helpagent
R3=$R3 python3 - <<'PYEOF'
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
PYEOF
```

The `DECOMP` / `FORCED` lists are the §5.6 comparison groups. Validated: this script was
executed against synthetic run roots (14 tasks × 5 seeds × 3 arms) and against a real
`bench/runs/evidence/v2tree-20260930T105620Z/T-31-parameter-threading/run.json` record and
runs as written. It reads only `run.json`, writes nothing, and is self-contained (`python3`
suffices; it imports no repo module).

### 5.5 Metrics

| metric | source | available for all arms? |
| --- | --- | --- |
| **grader actual pass rate** (primary) | `run.json:actual` (`bench/external_score.external_score` on a pristine copy) | YES |
| claimed / false success | `run.json:claimed`, `actual` | YES |
| model calls | `run.json:calls` | YES |
| wall seconds | `run.json:run_wall_s` | YES |
| tokens | leaf: `run.json` has none, but `<out>/trajectory.jsonl` exists (`bench/v2_leaf.py:846`) and `bench/v2_measure.py:186` (`read_token_usage`) sums it | **NO for tree arms** — `bench/v2_tree.py` never installs a telemetry sink, so no `trajectory.jsonl` is written (§7.2). Use calls as the cost proxy for tree arms and state the gap. |
| mechanism actually executed | tree `run.json` → `nodes[].candidates[].how_case`, `nodes[].allocation.forced` (`bench/v2_tree.py:212-304`) | tree arms only (leaf arms have no guard) |

### 5.6 Decision rule (pre-registered, with error bars)

Precondition gate — the run is **invalid as a decomposition test** unless all of the
following hold:

* the pinned revision is checked out and `git status --porcelain --untracked-files=no` is
  empty (one writer, no concurrent code edit);
* every arm has 14 × N runs paired by `(task, seed)`;
* ≥1 tree run has `decomposed-How` in `how_cases` on ≥3 of the 9 decomposable tasks. If
  `decomposition_fired_runs == 0`, the only measurable difference is planning overhead:
  report **"decomposition never executed at these thresholds"** and stop (that is a valid
  negative finding, not an inconclusive experiment).

Primary statistic — the paired per-task difference `d_t = rate_tree(t) − rate_leaf(t)`:

* **decomposable comparison** (9 tasks: T-31, T-33, T-28, T-21, T-34, T-32, T-03, T-11, T-12);
* **forced-leaf overhead comparison** (5 tasks: T-14, T-26, T-02, T-20, T-06), where the
  decomposition arm cannot fire, so the delta measures the cost of `how_list` + `plan_node`.

Report mean `d̄`, a 95 % percentile bootstrap CI (10 000 resamples of the tasks, seed
20261013) and an exact McNemar on the discordant `(task, seed)` pairs.

* **positive information** iff the decomposable CI lower bound > 0 **and** the false-success
  CI upper bound ≤ 0 **and** the forced-leaf comparison is not significantly negative;
* **negative information** iff the decomposable CI upper bound < 0, or the false-success CI
  lower bound > 0, or the forced-leaf CI upper bound < 0;
* **zero / inconclusive** iff the CI includes 0 — reported as "inconclusive on this corpus",
  never as "the stage adds nothing" (the historical run-to-run spread is ±3 tasks,
  STATUS §8e).

Power, stated honestly: with 9 decomposable tasks the detectable paired difference at 95 %
is roughly ±0.4 tasks-worth of rate, i.e. the experiment can only see an effect that moves
several tasks. A 1-task shift on this corpus will land inside the CI and must be reported
as inconclusive.

### 5.7 Cost (bounded)

14 tasks × 5 seeds × 3 arms = 210 runs. Leaf runs historically cost ~7–15 calls and
~20–90 s; tree runs cost ~38 calls and ~280 s at these settings (ticket 20 record). Budget:
≈ 1–2 h for B0, ≈ 5–6 h for B1, ≈ 8–12 h for B2 on one lane — ≈ 15–20 h total, with the
per-run deadline of 1 h as the hard stop. A first pass at `N=3` on the same task set
(≈ 9–12 h) is a legitimate cost reduction; do not read a 3-seed CI as tighter than it is.

---

## 6. Honest expected outcome

Stated BEFORE the run:

* **Forced-leaf tasks (5 in the set, 21 in the corpus):** expected delta **≤ 0**, at the
  cost of 2–3 extra planning calls (`how_list` + `plan_node`) per run. This is measured
  overhead, not decomposition. The prior measurement at `66e9708` agrees: greedy tree on
  T-02 parked at 22 calls / 70 s where a paired leaf fixed it at 11 calls / 29 s.
* **Decomposable tasks (9 in the set, 14 in the corpus):** the prior measurement
  (ticket 20, six tasks, N=1: tree actual **1/6** at ~38 calls / 278 s mean vs leaf
  **6/12** at ~7 calls / 20 s) and the STATUS §3/§1a pattern ("structure that costs calls
  without adding information loses") predict **zero to negative**. The only mechanism with
  a story for a positive delta is a requirement-level child split on T-31/T-33 — and the
  2026-09-30 T-31 tree run decomposed into children and still parked.
* **The tournament (B2) is the most likely to be clearly negative:** `how_explore=3`
  triples sampling of the *same* 4B on the *same* prompt, so the candidates add sampling
  variance, not information, while consuming the budget the leaf spends iterating toward
  the fix.

**Plain statement (as required):** on the current code and this corpus, no decomposition /
multi-approach / step-splitting mechanism is expected to produce a measurable positive
delta. The honest prediction is a **negative result**, weakly bounded by the possibility of
a positive on T-31/T-33 that a 14-task, 5-seed design would very likely report as
inconclusive. Running the experiment is justified only as a bounded, pre-registered
falsification that closes R3 with a measurement instead of an opinion — and it is the only
existing way to measure the forced-leaf thresholds, which have never been measured at all.

If the result is negative, the correct R3 wording is: **"structural superiority
(C4/R3) is refuted on this corpus: the monolithic leaf matches or beats the tree at a
fraction of the cost."** If it is inconclusive, the wording is "R3 inconclusive on this
corpus", with the guard table (§4.1) as the structural explanation.

---

## 7. What is missing — the STOP conditions

The tree CAN be run against the corpus by the current drivers, one task at a time:
`bench/v2_tree.py --help` parses and `main` runs one task (`bench/v2_tree.py:544-558`).
What does NOT exist:

1. **No multi-task / multi-seed tree sweep driver.** `bench/v2_tree.py` runs ONE task and
   writes one `run.json` (`bench/v2_tree.py:446` `run_once`, `bench/v2_tree.py:544-558` `main`);
   `bench/v2_measure.py` cannot drive the tree at all — it imports and calls
   `bench.v2_leaf.run_once` only (`bench/v2_measure.py:60`, `bench/v2_measure.py:346`) and
   its `ABLATIONS` table knows nothing about `how_explore`. The experiment therefore uses
   the bash loop in §5.3. A `bench/v2_tree_sweep.py` (or a `--driver tree` in
   `v2_measure`) is the missing piece for a first-class sweep; it is out of READ-ONLY scope.
2. **No token capture for tree runs.** `bench/v2_tree.py` never calls
   `harness.telemetry.set_sink` (contrast `bench/v2_leaf.py:846` and `:866`), so no
   `trajectory.jsonl` is written for a tree run (confirmed: the six evidence `v2tree-*`
   directories contain `run.json` only). The token metric is unavailable for B1/B2; a
   one-line `set_sink(jsonl_sink(out_dir/"trajectory.jsonl"))` in
   `bench/v2_tree.py::run_once` fixes it.
3. **The forced-leaf thresholds are not parameterizable.** `FORCED_LEAF_MAX_FILES` /
   `FORCED_LEAF_MAX_ACS` are module constants with no CLI flag or env read
   (`harness/tree_run.py:169-170`; `_allocation_guard` at `harness/tree_run.py:1341` reads
   them directly). Therefore the threshold sweep — the ONLY way to test T-14 and T-26, the
   two forensics-predicted beneficiaries the guard blocks (§4.1) — **cannot be run as
   written**. It needs a one-line parameterization (e.g. constructor/CLI plumbing), which
   is a code change and outside this task's authority. Until then, the threshold value is
   untested and the R3 design can only measure the guard's *fixed* 3/3 effect.
4. **No paired-CI / McNemar helper in the repo.** `bench/v2_measure.py` has only
   `mean`/`stdev` (`bench/v2_measure.py:123-128`); the analysis in §5.4 is a self-contained
   `python3 -` heredoc that adds no file.

Suggested follow-up (for a future writer, NOT done here): (a) add
`bench/v2_tree_sweep.py` reusing `v2_measure`'s `arm_summary`/`read_token_usage`; (b) set
the telemetry sink in `bench/v2_tree.py::run_once`; (c) make `FORCED_LEAF_MAX_FILES/ACS`
parameters with the 3/3 default preserved, then sweep {3,6,99} × {3,6,99} on the 9
decomposable tasks. Only (c) can test T-14/T-26.

---

## 8. Evidence index

Code (revision `45ebb32`): `harness/tree_run.py:169-170,177,802,869,982,1134,1182,1237,
1341,1356-1360,1380,1426-1429,1475-1517,1918,2144,2336`; `harness/node.py:130,167,206,308,
449,486,498,596`; `harness/how.py:187,242,493,523,727`; `bench/v2_tree.py:176,212-304,386,
446,508-509,519-558`; `bench/v2_leaf.py:186,288-320,845-846,866,939-975`; `bench/
v2_measure.py:60,95-122,123-128,186,309-332,346`.

Measured records: `bench/runs/evidence/v2tree-20260930T{103839,104645,104946,105513,105620,
110120}Z/T-*/run.json`; `.scratch/20-how-scaling/issues/20-how-scaling.md:120-146,173`;
`docs/STATUS.md` §1a, §3 (row "competitive How exploration"), §8e, §8f/§8g (T-31, T-33,
T-14, T-26, T-28 outcomes); `.scratch/28-three-requirements/issues/
verification-decomposition-forensics.md` §4.1-§4.5; `.scratch/28-three-requirements/issues/
ablation-protocol.md` §2.2, §6, §8 (items 3 and 7).

Guard table command (§4.1 / §5.6, read-only, no model):

```sh
uv run python - <<'EOF'
import sys; sys.path.insert(0, '.')
from pathlib import Path
from bench.v2_leaf import load_task, extract_acs
from harness.staging import source_only
for d in sorted(Path('bench/corpus').iterdir()):
    if not d.is_dir() or not d.name.startswith('T-'):
        continue
    t = load_task(d)
    files, acs = len(source_only(t['files'])), len(extract_acs(t['request']))
    print(f"{d.name:34s} files={files:2d} acs={acs:2d} "
          f"{'FORCED-LEAF' if files <= 3 and acs <= 3 else 'CAN DECOMPOSE'}")
EOF
```
