# Parity-forensics independent verification (verbatim artifact) + executed re-run

> **Header.** This file is the independent-verification artifact produced by reviewer session `804aa75a-7008-4acb-a720-ea11227212da`, copied verbatim below except for this header and the appended "Shell-capable re-run" section. (1) The verifier environment had no shell/execution tools, so every "passes the withheld suite" verdict on a **DISCARDED** revision below is a **Tier-B reconstruction** (the recovered source evaluated against the withheld test source), whereas the **DELIVERED**-revision failures are **Tier-A raw grader output** quoted from the run records' own `delivery` events. (2) A shell-capable re-run using the reproduction commands in the document is still **REQUIRED** before any parity claim is published; that re-run has now been **executed and appended at the end of this document**. (3) The artifact's **Correction 2** on T-28 — that `documented_api_missing` is neither necessary nor sufficient for the grader — is **accepted** and has been passed to the fix worker (the re-run corroborates its surviving limb on `1bfbf536` and, as noted below, refutes its paired `052a375a` example).

---

I have completed the independent verification. No shell/execution tool exists in this reviewer environment, so I verified from the persisted record (trajectory envelopes, delivered work trees, the grader's applied copies, and the run's own recorded grader verdicts) and supply exact re-run commands. Here is the deliverable artifact (returned in full because no write tool is available to me):

---

# Independent verification of parity-forensics §5 D1 and the T-14 negative claim

Target: `.scratch/28-three-requirements/issues/parity-forensics.md` §2.1 (lines 67–107), §2.2 (136–189), §2.3 (191–247), §2.4 (265–304), §5 D1 (464–477).
Scope: read-only. No code, test or doc file was modified.

## 0. Method and its one real limitation (read this before the verdicts)

The assigned method was "apply each reconstructed revision to a pristine copy and run the withheld suite via `bench/external_score.py`". **This reviewer environment has no shell/execution tool** (only file read/search): I could not run `python3`, `pytest` or `sha256sum`. I therefore used a two-tier method and I label the tier of every claim:

* **Tier A — raw grader output (not re-executed by me):** the run's own `delivery` event, which records what `bench/external_score.py::external_score` returned for the bytes actually delivered (exit code, failing test ids, notes). This is machine-produced raw output about the delivered revision, quoted verbatim below.
* **Tier B — reconstruction + exact semantics (not executed):** for the *discarded* revisions I recovered the full `implement_write` envelope content from `trajectory.jsonl`, cross-checked it three ways for the final write of each task (envelope text == delivered `work/...` file == the grader's applied copy under `<run>/grade/<task>/repo/...`), and derived the withheld-suite verdict by evaluating that source against the withheld test source read from the pristine corpus. Every failure at issue is a deterministic import/attribute/format/SQL-parameterisation outcome (`AttributeError`, `strptime` `ValueError`, `sqlite3.ProgrammingError`, `KeyError`), not a judgement call, so the derived verdict is robust — but it is not a pytest run by me.
* **Not verifiable by either tier:** the recorded `sha256`/byte-count strings (no hashing tool). I verified content identity *textually*, not by hash. The reproduction script in §5 lets a shell-capable reviewer confirm every number, including hashes.

Revisions were reconstructed from the persisted per-step envelope, and the source of the reconstruction is verified: for each delivered revision the persisted envelope text is byte-identical in content to the delivered work tree and to the grader's applied copy — e.g. T-28 envelope (seq 622/623 region, sha `a801efc3…`) == `bench/runs/v2sweep-20261011T070710Z/T-28-plugin-registry-scaffold-1/work/plugins/registry.py` == `…/grade/T-28-plugin-registry-scaffold/repo/plugins/registry.py`; T-17 sha `3ae7dd6f…` == `…/work/logparse/parser.py` == `…/grade/T-17-log-hour-format/repo/logparse/parser.py`; T-07 sha `82a15f89…` == `…/work/contacts/store.py` == `…/grade/T-07-f-string-sql/repo/contacts/store.py`. So the envelope content in `trajectory.jsonl` is a faithful record of the written bytes.

Convention: in these runs the `model_call` event is the write request and `source_write` is the next seq. I use the `model_call` seq as "write seq", matching the forensics document.

---

## 1. T-28-plugin-registry-scaffold — **CONFIRMED** (with two corrections that strengthen it)

Run: `bench/runs/v2sweep-20261011T070710Z`, task dir `T-28-plugin-registry-scaffold-1`.

Withheld suite (`bench/corpus/T-28-plugin-registry-scaffold/repo/tests/test_plugins.py`, 4 tests) uses only module-level names:
```python
from plugins import registry

def test_register_and_get():
    registry.register("greet", lambda: "hi")
    assert registry.get("greet")() == "hi"
def test_get_unknown_raises():
    with pytest.raises(KeyError): registry.get("nope")
def test_register_duplicate_rejected():
    registry.register("dup", lambda: 1)
    with pytest.raises(ValueError): registry.register("dup", lambda: 2)
def test_run_passes_args():
    registry.register("add", lambda a, b: a + b)
    assert registry.run("add", 2, 3) == 5
```

Every written revision (all 6 writes):

| write seq (attempt) | sha256 (recorded) | bytes | module-level surface | withheld suite |
| --- | --- | --- | --- | --- |
| 582 (n=1) | `88f26d23…` | 570 | `Registry` class only | fail 4/4 (Tier B) |
| 597 (n=2) | `88f26d23…` (noop) | 570 | unchanged | fail 4/4 |
| **611 (n=3)** | **`a801efc3…`** | 1442 | `Registry` class only | **fail 4/4 — DELIVERED** |
| 622 (n=4) | `e8484d8b…` | 916 | `registry = Registry()` + `register/get/run` functions | **pass 4/4 (Tier B)** |
| 634 (n=5) | `052a375a…` | 1502 | `registry = Registry()` only | **pass 4/4 (Tier B)** |
| 645 (n=6) | `1bfbf536…` | 1472 | module-level `register/get/run` each building a **new** `Registry()` | fail 3/4 (Tier B) |

Delivered revision is unambiguous: `delivered_best_evidence` (seq 670) restores `{rank: 1, tier: "review", attempt: 2}` whose bytes are `a801efc3…` (the n=3 write) — confirmed by the identical text in `work/plugins/registry.py` and `grade/…/repo/plugins/registry.py` (no module-level `register/get/run`, no module-level `registry`).

**Raw grader output on the delivered bytes (Tier A), `delivery` event seq 674:**
```json
{"event": "delivery", "grader_passed": false, "grader_exit": 1,
 "grader_notes": ["           FAILED tests/test_plugins.py::test_get_unknown_raises - AttributeError: modul...",
                  "           FAILED tests/test_plugins.py::test_register_duplicate_rejected - AttributeErr...",
                  "           FAILED tests/test_plugins.py::test_run_passes_args - AttributeError: module '...",
                  "           4 failed in 0.02s",
                  "[contract] OK (5 untouched paths byte-identical)", "result: FAIL"],
 "claimed": false, "stop_reason": "attempts"}
```
The first deviation point in §2.1 is reproduced exactly: `best_evidence_revision` (seq 619, `{rank: 1, tier: "review", attempt: 2}`) is immediately followed one event later by `documented_api_missing` (seq 620) declaring that same revision non-compliant.

**Why `e8484d8b…` passes (the reconstructed discarded revision, Tier B)** — full content (this is the revision §2.1 cites):
```python
"""Plugin registry module.

Plugins can register a callable under a name, look it up, and run it with arguments.
Registering the same name twice must be rejected, and looking up an unknown name must raise KeyError.
"""


class Registry:
    def __init__(self):
        self._registry = {}

    def register(self, name, fn):
        if name in self._registry:
            raise ValueError(f"Plugin name '{name}' is already registered.")
        self._registry[name] = fn

    def get(self, name):
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Plugin '{name}' is not registered.")

    def run(self, name, *args):
        fn = self.get(name)
        return fn(*args)


registry = Registry()


def register(name, fn):
    registry.register(name, fn)


def get(name):
    return registry.get(name)


def run(name, *args):
    return registry.run(name, *args)
```
All four withheld tests pass on it: module-level `register/get/run` exist and share one instance, so `register("dup", …)` twice raises `ValueError`, `get("nope")` raises `KeyError`, `run("add", 2, 3) == 5`.

**Correction 1 (strengthens the claim).** §2.1 (line 79) names only attempt 4 as the passing revision. The n=5 revision (`052a375a…`, write seq 634, **written after** the fail-4/4 snapshot was recorded) also passes 4/4: its module-level `registry = Registry()` *instance* satisfies `from plugins import registry` + `registry.register/get/run` (attribute lookup on the module returns the bound methods of the instance). The harness held a grader-passing revision written later than the snapshot it delivered, and discarded it too.

**Correction 2 (finding, P2 — affects the remedy, not the verdict).** §5 D1's minimal change ("capture the revision that clears a check the current best fails") is not a sound proxy for the withheld grader on this task, in *both* directions:
* `052a375a…` (n=5) **fails** the deterministic check — `documented_api_missing` fires at seq 642 right after n=5's reviews ("…exposes them only as methods of Registry") — yet **passes** the withheld suite 4/4.
* `1bfbf536…` (n=6, seq 645) **clears** the check (no `documented_api_missing` event follows n=6's reviews at seqs 649–654) yet **fails** the withheld suite (its module-level `register/get/run` each construct a fresh `Registry()`, so `registry.get("greet")` raises `KeyError` inside `test_register_and_get`; `registry.register("dup", …)` twice never raises).
`documented_api_missing` therefore neither implies nor is implied by the grader verdict here. If D1 is implemented as "deliver the last revision that clears the check", T-28 stays lost (n=6 is delivered). The fix must capture the clearing revision while still preferring the recorded best (n=4), and must not treat check-clearing as grader-passing.

Other §2.1 statements checked and reproduced: attempts 3–6 all run in mode `M1` (seqs 610, 621, 633, 644); the n=4 reviews were refused by `review_not_grant_calibre` (seq 630), leaving the passing revision at rank 0; delivery is the restored rank-1 review snapshot.

## 2. T-17-log-hour-format — **CONFIRMED**

Run: `bench/runs/v2sweep-20261011T065821Z`, task dir `T-17-log-hour-format-1`.

Withheld suite `bench/corpus/T-17-log-hour-format/repo/tests/test_parser.py`:
```python
def test_afternoon_hour_is_parse():
    ts = parse_ts("[2025-06-01 14:30:00] INFO boot ok")
    assert ts == datetime(2025, 6, 1, 14, 30, 0)
def test_morning_hour_unchanged():
    ts = parse_ts("[2025-06-01 09:15:00] WARN slow disk")
    assert ts == datetime(2025, 6, 1, 9, 15, 0)
```

| write seq (attempt) | sha256 (recorded) | bytes | `parse_ts` slice | withheld suite |
| --- | --- | --- | --- | --- |
| 1219 (n=1) | `77cc9fd7…` | 371 | `line[1:1 + STAMP_LEN]` + `%H` | **pass 2/2 (Tier B)** |
| **1228 (n=2)** | **`3ae7dd6f…`** | 366 | `line[:STAMP_LEN]` + `%H` | **fail 2/2 — DELIVERED** |
| 1240 (n=3) | `77cc9fd7…` | 371 | as n=1 | **pass 2/2** |
| 1251 (n=4) | `f1ed6518…` | 371 | `line[0:1 + STAMP_LEN]` (`line[0:20]`) + `%H` | fail 2/2 |
| 1257 (n=5) | `f1ed6518…` (noop) | 371 | unchanged | fail 2/2 |
| 1265 (n=6) | `77cc9fd7…` | 371 | as n=1 | **pass 2/2** |
| 1273 (n=7, terminal) | `77cc9fd7…` | 371 | as n=1 | **pass 2/2** |

So the correct revision was written **four** times (1219, 1240, 1265, 1273) and the delivered bytes are the one-off wrong revision of seq 1228. Delivered identity verified three ways (`work/logparse/parser.py` == `grade/…/repo/logparse/parser.py` == the seq-1228 envelope):
```python
def parse_ts(line: str) -> datetime:
    stamp = line[:STAMP_LEN]              # "[2025-06-01 14:30:0" -> strptime ValueError
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
```

**Raw grader output on the delivered bytes (Tier A), `delivery` event seq 1297:**
```json
{"event": "delivery", "grader_passed": false, "grader_exit": 1,
 "grader_notes": ["           =========================== short test summary info ============================",
                  "           FAILED tests/test_parser.py::test_afternoon_hour_is_parse - ValueError: time ...",
                  "           FAILED tests/test_parser.py::test_morning_hour_unchanged - ValueError: time d...",
                  "           2 failed in 0.04s",
                  "[contract] OK (5 untouched paths byte-identical)", "result: FAIL"],
 "claimed": false, "stop_reason": "ladder"}
```

**Why the terminal (and thrice-repeated) revision passes (Tier B)** — full content of `77cc9fd7…`:
```python
"""Parse structured lines from the service log.

Line shape: "<YYYY-MM-DD HH:MM:SS> <LEVEL> <message>"
"""

from datetime import datetime

STAMP_LEN = 19  # "YYYY-MM-DD HH:MM:SS"


def parse_ts(line: str) -> datetime:
    stamp = line[1:1 + STAMP_LEN]
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")


def level(line: str) -> str:
    return line[22:26].strip()
```
`line[1:20]` is exactly the bracketed 19-char stamp of the withheld fixtures, and `%H` parses both 14:30 and 09:15 → 2 passed.

Delivery selection matches §2.2: `delivered_best_evidence` (seq 1294) records `{rank: 2, tier: "own-test", attempt: 1}` with reason "the last-written revision had weaker evidence (rank 0)…", i.e. the model's own bad fixture (self-test written at seq 1215: `line = "2023-10-26 14:30:00 INFO message"`, no brackets) outranked four correct revisions. No discrepancy found in §2.2 (its "write seq" column uses the `model_call` seq, as here). **Verdict: CONFIRMED.**

## 3. T-07-f-string-sql — **CONFIRMED**

Run: `bench/runs/v2sweep-20261009T114754Z`, task dir `T-07-f-string-sql-1`.

Withheld suite `bench/corpus/T-07-f-string-sql/repo/tests/test_store.py`: `test_add_and_find_plain_name` (plain name) and `test_name_with_apostrophe_round_trips` (`add_contact(conn, "Tim O'Brien", …)` then `find_email(conn, "Tim O'Brien")`). Both call sites in `contacts/store.py` must be parameterised.

| write seq (attempt) | sha256 (recorded) | bytes | `add_contact` | `find_email` | withheld suite |
| --- | --- | --- | --- | --- | --- |
| 40 (n=1) | `ee45fb88…` | 703 | `VALUES (?, ?)`, `(name, email)` | `name = ?`, `(name,)` | **pass 2/2 (Tier B)** |
| 49 (n=2) | `ee45fb88…` (noop) | 703 | unchanged | unchanged | **pass 2/2** |
| 56 (n=3) | `039c8b91…` | 696 | `VALUES (? , ?)`, `(name, email)` | `name = ?` with **no parameters** → `ProgrammingError` | fail 2/2 |
| 62 (n=4) | `0ee3867d…` | 722 | `VALUES (?, ?)` | `"…name = ?".replace("=", "=")`, `(name,)` (no-op replace) | **pass 2/2** |
| 68 (n=5) | `f33772f8…` | 704 | `VALUES (?, ?)` | `name = ?`, `(name,)` | **pass 2/2** |
| **75 (n=6, terminal)** | **`82a15f89…`** | 726 | `VALUES (?, ?)`, `(name, email)` | **reverted to f-string** | **fail 1/2 — DELIVERED** |

Delivered identity verified three ways; the graded copy `grade/T-07-f-string-sql/repo/contacts/store.py` reads exactly:
```python
def add_contact(conn: sqlite3.Connection, name: str, email: str) -> None:
    conn.execute(
        "INSERT INTO contacts (name, email) VALUES (?, ?)",
        (name, email),
    )

def find_email(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(f"SELECT email FROM contacts WHERE name = '{name}'").fetchone()
    return row[0] if row else None
```

**Raw grader output on the delivered bytes (Tier A), `delivery` event seq 98:**
```json
{"event": "delivery", "grader_passed": false, "grader_exit": 1,
 "grader_notes": ["           contacts/store.py:23: OperationalError",
                  "           =========================== short test summary info ============================",
                  "           FAILED tests/test_store.py::test_name_with_apostrophe_round_trips - sqlite3.O...",
                  "           1 failed, 1 passed in 0.02s",
                  "[contract] OK (4 untouched paths byte-identical)", "result: FAIL"],
 "claimed": false, "stop_reason": "ladder"}
```

**Passing discarded revision (Tier B)** — full content of `ee45fb88…` (write seq 40), which differs from the delivered revision only in `find_email`:
```python
"""Contact book backed by sqlite3 (in-memory per connection)."""

import sqlite3

_SCHEMA = "CREATE TABLE contacts (name TEXT PRIMARY KEY, email TEXT NOT NULL)"


def connect() -> sqlite3.Connection:
    """Open an in-memory contacts database with the schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute(_SCHEMA)
    return conn


def add_contact(conn: sqlite3.Connection, name: str, email: str) -> None:
    conn.execute("INSERT INTO contacts (name, email) VALUES (?, ?)", (name, email))


def find_email(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT email FROM contacts WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None
```

"4 of 6 revisions pass" is exactly right (n=1, n=2 noop, n=4, n=5 pass; n=3 and n=6 fail), and the doc's row-by-row table matches my reconstruction on every row.

**Finding (P2 — attribution, not the claim).** §5 D1's Effect line (line 474) claims "+1 on `6b224f5` (T-07)" from D1's mechanism. In this run **no deterministic contract check was failing at all**: `failure_report` (seq 97) ends with `"documented_api_missing": []`, `"regressions": []`, `"unverifiable": []`; the only reds were the run's own malformed test (`assert conn.execute("SELECT email FROM contacts WHERE name = 'O'Brien'")` — unparseable SQL, red on every revision) and the IV test. So neither limb of D1's minimal change can fire here: there is no failing deterministic check to clear, and the run's own test was red on the passing revision too (nothing about the passing revision "clears" anything). T-07's recovery follows from **D2** (credit `test_wrong` from the traceback → repair the own test → the correct draft survives), which §5 D2 itself credits with "T-07 +1 (`6b224f5`)" at line 487. D1 and D2 therefore double-count T-07; D1 should cite T-28 + T-17 only (+2), with the 6b224f5 T-07 gain attributed to D2. This does not weaken the confirmed pivotal claim (a grader-passing revision existed and was discarded); it changes which fix earns the point.

## 4. T-14-add-export-sorting, `6b224f5` — negative claim **CONFIRMED** (no passing revision)

Run: `bench/runs/v2sweep-20261009T114754Z`, task dir `T-14-add-export-sorting-1`.

Withheld suite `bench/corpus/T-14-add-export-sorting/repo/tests/test_export.py` requires **both** the documented stable case-insensitive order and the documented tuple+formatting return:
```python
def test_rows_are_customer_ordered_case_insensitive_and_stable():
    out = export_rows(ROWS)
    assert [r[0] for r in out] == ["Acme", "ACME corp", "acme corp", "Borealis", "northwind"]
def test_totals_are_formatted_with_two_decimals():
    assert export_rows([{"customer": "a", "total": 7}]) == [("a", "7.00")]
```

| write seq (attempt) | sha256 (recorded) | bytes | body | ordering test | totals test |
| --- | --- | --- | --- | --- | --- |
| 223 (n=1) | `6e3a55dc…` | 495 | `return sorted(rows, key=lower)` **+ dead tuple-comprehension** | fail | fail |
| 232 (n=2) | `6e3a55dc…` (noop) | 495 | unchanged | fail | fail |
| 239 (n=3) | `df2eb91a…` | 406 | identical to the pristine (comprehension, no sort) | fail | **pass** |
| 246 (n=4) | `0c9ec444…` | 403 | `return sorted(rows, key=lambda r: r["customer"].lower())` | fail | fail |
| 256 (n=5) | `df2eb91a…` (noop) | 406 | unchanged | fail | **pass** |
| **263 (n=6, terminal)** | **`d1e228b5…`** | 472 | `return sorted(rows, …)` + dead tuple-comprehension | fail | fail |

Delivered `reporting/export.py` confirmed in the grader's applied copy `grade/T-14-add-export-sorting/repo/reporting/export.py`:
```python
    return sorted(rows, key=lambda r: r["customer"].lower())
    
    return [(r["customer"], f"{r['total']:.2f}") for r in rows]
```

**Raw grader output on the delivered bytes (Tier A), `delivery` event seq 273:**
```json
{"event": "delivery", "grader_passed": false, "grader_exit": 1,
 "grader_notes": ["           =========================== short test summary info ============================",
                  "           FAILED tests/test_export.py::test_rows_are_customer_ordered_case_insensitive_and_stable",
                  "           FAILED tests/test_export.py::test_totals_are_formatted_with_two_decimals - As...",
                  "           2 failed in 0.04s", "[contract] OK (4 untouched paths byte-identical)", "result: FAIL"],
 "claimed": false, "stop_reason": "spec-bubble"}
```
No revision of the six returns tuples *and* sorts → **no passing revision; the negative claim holds** (content-side loss confirmed).

**Discrepancy 1 (P2, wording).** §2.4 (line 267) says "all six written revisions fail the grader (`test_totals_are_formatted_with_two_decimals`, and the ordering test on some)". That is inverted: the **ordering** test fails on all four distinct revisions, while the **totals** test fails on three of four (the pristine-identical revision `df2eb91a…` passes it). Verdict unaffected.

**Discrepancy 2 (P2, process characterisation).** §2.4 says "The run's own test was **correct** — seq 213 writes `reporting/test_export.py` asserting the tuple form", and that "the only feedback was the model's own test (which it also had, and ignored) and the judge". The persisted record shows the harness **deleted two of that test's three nodes before the first attempt**: `own_test_partition` (seq 216/219) classifies `test_export_rows_keeps_submitted_order_for_case_only_differences` and `test_export_rows_formats_totals_with_two_decimals` as `symptom`, and `own_test_symptom_dropped` (seq 220) sets `"removed": true` for both. Those were exactly the nodes pinning the documented return shape the model then destroyed. So the model was never asked about the deleted documented behaviour by its own test either — which strengthens, not weakens, the "documented behaviour deleted with no deterministic flag" finding in §2.4/D4, but the doc's phrasing as written overstates what the run's own test still covered at attempt time. §2.4 also correctly reproduces that the end was a `spec-bubble` after the judge blamed the spec while naming a source defect (seq 268–270).

## 5. Reproduction (a shell-capable reviewer gets these numbers exactly)

Paste-able; uses the campaign's own instrument, with the reconstructed revisions verbatim. Each case applies one revision to a pristine corpus copy and runs the withheld suite through `bench/external_score.py` (including the T-17 untouched-file contract and the report gate).

```bash
cd /home/z/vibe/helpagent
mkdir -p /tmp/d1check

# --- T-28 (the revision §2.1 cites; expect passed=True, 4 passed) ---
cat > /tmp/d1check/T28_e8484d8b.py <<'EOF'
"""Plugin registry module.

Plugins can register a callable under a name, look it up, and run it with arguments.
Registering the same name twice must be rejected, and looking up an unknown name must raise KeyError.
"""


class Registry:
    def __init__(self):
        self._registry = {}

    def register(self, name, fn):
        if name in self._registry:
            raise ValueError(f"Plugin name '{name}' is already registered.")
        self._registry[name] = fn

    def get(self, name):
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Plugin '{name}' is not registered.")

    def run(self, name, *args):
        fn = self.get(name)
        return fn(*args)


registry = Registry()


def register(name, fn):
    registry.register(name, fn)


def get(name):
    return registry.get(name)


def run(name, *args):
    return registry.run(name, *args)
EOF

# --- T-28 n=5 variant (expect passed=True; fails documented_api_missing, passes the grader) ---
sed -e 's/^def register(name, fn):/def _unused_register(name, fn):/' \
    -e 's/^def get(name):/def _unused_get(name):/' \
    -e 's/^def run(name, \*args):/def _unused_run(name, *args):/' \
    /tmp/d1check/T28_e8484d8b.py > /tmp/d1check/T28_052a375a.py   # keep only `registry = Registry()`

# --- T-28 n=6 variant (expect passed=False, 3 failed; clears the check, fails the grader) ---
cat >> /tmp/d1check/T28_1bfbf536.py <<'EOF'
"""Plugin registry module."""
class Registry:
    def __init__(self): self._plugins = {}
    def register(self, name, fn):
        if name in self._plugins: raise ValueError("dup")
        self._plugins[name] = fn
    def get(self, name):
        try: return self._plugins[name]
        except KeyError: raise KeyError(name)
    def run(self, name, *args): return self.get(name)(*args)
def register(name, fn): return Registry().register(name, fn)   # fresh instance
def get(name): return Registry().get(name)                      # fresh instance
def run(name, *args): return Registry().run(name, *args)
registry = Registry()
EOF

# --- T-17 correct terminal revision (expect passed=True, 2 passed) ---
cat > /tmp/d1check/T17_77cc9fd7.py <<'EOF'
"""Parse structured lines from the service log.

Line shape: "<YYYY-MM-DD HH:MM:SS> <LEVEL> <message>"
"""

from datetime import datetime

STAMP_LEN = 19  # "YYYY-MM-DD HH:MM:SS"


def parse_ts(line: str) -> datetime:
    stamp = line[1:1 + STAMP_LEN]
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")


def level(line: str) -> str:
    return line[22:26].strip()
EOF

# --- T-07 correct attempt-1 revision (expect passed=True, 2 passed) ---
cat > /tmp/d1check/T07_ee45fb88.py <<'EOF'
"""Contact book backed by sqlite3 (in-memory per connection)."""

import sqlite3

_SCHEMA = "CREATE TABLE contacts (name TEXT PRIMARY KEY, email TEXT NOT NULL)"


def connect() -> sqlite3.Connection:
    """Open an in-memory contacts database with the schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute(_SCHEMA)
    return conn


def add_contact(conn: sqlite3.Connection, name: str, email: str) -> None:
    conn.execute("INSERT INTO contacts (name, email) VALUES (?, ?)", (name, email))


def find_email(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT email FROM contacts WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None
EOF

# --- T-07 n=3 variant (expect passed=False: `name = ?` with no parameters) ---
sed -i 's|("SELECT email FROM contacts WHERE name = ?", (name,))|("SELECT email FROM contacts WHERE name = ?")|' \
    /tmp/d1check/T07_039c8b91.py 2>/dev/null; cp /tmp/d1check/T07_ee45fb88.py /tmp/d1check/T07_039c8b91.py
sed -i 's|("SELECT email FROM contacts WHERE name = ?", (name,))|("SELECT email FROM contacts WHERE name = ?")|' \
    /tmp/d1check/T07_039c8b91.py

# --- T-14 n=1/n=4/n=6 (delivered) and n=3 pristine-identical (expect passed=False for all) ---
python3 - <<'PY'
from pathlib import Path
p = Path("bench/corpus/T-14-add-export-sorting/repo/reporting/export.py")
body = p.read_text()
Path("/tmp/d1check/T14_df2eb91a.py").write_text(body)                       # pristine-identical: order fails, totals passes
Path("/tmp/d1check/T14_d1e228b5.py").write_text(body.replace(
    'return [(r["customer"], f"{r[\'total\']:.2f}") for r in rows]',
    'return sorted(rows, key=lambda r: r["customer"].lower())\n    \n'
    '    return [(r["customer"], f"{r[\'total\']:.2f}") for r in rows]'))
PY

python3 - <<'PY'
from pathlib import Path
from bench.external_score import external_score
cases = [
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "T28_e8484d8b.py"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "T28_052a375a.py"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "T28_1bfbf536.py"),
    ("T-17-log-hour-format",          "logparse/parser.py",    "T17_77cc9fd7.py"),
    ("T-17-log-hour-format",          "logparse/parser.py",    "T17_delivered_3ae7dd6f.py"),
    ("T-07-f-string-sql",             "contacts/store.py",     "T07_ee45fb88.py"),
    ("T-07-f-string-sql",             "contacts/store.py",     "T07_039c8b91.py"),
    ("T-14-add-export-sorting",       "reporting/export.py",   "T14_df2eb91a.py"),
    ("T-14-add-export-sorting",       "reporting/export.py",   "T14_d1e228b5.py"),
]
for task, rel, src in cases:
    rev = Path("/tmp/d1check", src)
    if not rev.exists():
        print(f"{task:34s} {src:28s} SKIPPED (write the delivered/file variant first)"); continue
    out = external_score(Path("bench/corpus") / task, {rel: rev.read_text()},
                         Path("/tmp/d1check/work"))
    print(f"{task:34s} {src:28s} passed={out.passed!s:5s} exit={out.exit} notes={out.notes[-3:]}")
PY
```
The delivered-file variants are the ones already on disk and can be run directly without reconstruction:
`bench/runs/v2sweep-20261011T070710Z/T-28-plugin-registry-scaffold-1/work/plugins/registry.py`,
`bench/runs/v2sweep-20261011T065821Z/T-17-log-hour-format-1/work/logparse/parser.py`,
`bench/runs/v2sweep-20261009T114754Z/T-07-f-string-sql-1/work/contacts/store.py`,
`bench/runs/v2sweep-20261009T114754Z/T-14-add-export-sorting-1/work/reporting/export.py` (all must return `passed=False`).
Expected table: T-28 `e8484d8b` True/4 passed · T-28 `052a375a` True · T-28 `1bfbf536` False/3 failed · T-28 delivered(a801efc3) False/4 failed · T-17 `77cc9fd7` True/2 passed · T-17 delivered False/2 failed · T-07 `ee45fb88` True/2 passed · T-07 `039c8b91` False/2 failed · T-07 delivered False/1 failed 1 passed · T-14 `df2eb91a` False/1 failed 1 passed · T-14 `d1e228b5` False/2 failed.

## 6. Verdict summary

| Claim (forensics §) | Verdict | Basis |
| --- | --- | --- |
| T-28: a grader-passing revision existed in the run and a failing one was delivered (§2.1, §5 D1) | **CONFIRMED** | delivered = `a801efc3…`, raw grader "4 failed"; passing revisions `e8484d8b…` and (extra, doc did not name it) `052a375a…` (Tier B) |
| T-17: 4 of 7 revisions pass, delivered snapshot fails, terminal passes (§2.2, §5 D1) | **CONFIRMED** | delivered = `3ae7dd6f…`, raw grader "2 failed"; `77cc9fd7…` written at seqs 1219/1240/1265/1273 (Tier B) |
| T-07: 4 of 6 revisions pass, delivered one fails (§2.3, §5 D1) | **CONFIRMED** | delivered = `82a15f89…`, raw grader "1 failed, 1 passed"; `ee45fb88…`/`0ee3867d…`/`f33772f8…` pass (Tier B) |
| T-14 `6b224f5`: no revision passes (only claimed content-side loss) (§2.4, §3) | **CONFIRMED** | delivered = `d1e228b5…`, raw grader "2 failed"; all four distinct revisions mis-handle the documented tuple/format contract (Tier B) |
| D1's remedy attribution: "+1 on `6b224f5` (T-07)" from D1 | **Contradicted as stated** (P2) | no deterministic contract check was failing in that run (`documented_api_missing: []`, seq 97) and the failing red was the run's own malformed test → the gain belongs to D2 (which claims it too) |
| D1's remedy safety: "capture the revision that clears the check" ⇒ grader-passing | **Contradicted on T-28** (P2) | `052a375a…` fails the check yet passes the grader; `1bfbf536…` clears the check yet fails the grader |

Overall: **the pivotal D1 claim is substantiated on all three tasks** — this harness discarded grader-passing revisions and delivered failing ones, exactly where §5 D1 says. Two P2 corrections (one strengthening T-28, one re-attributing T-07) and two P2 wording corrections in §2.4 (which test fails on which revision; the harness's own `own_test_symptom_dropped` at seq 220 deleted the nodes that pinned the documented behaviour) should be folded in before the fix is scoped, but none of them changes a verdict.

## 7. Residual risks of this verification
1. **No execution on my side.** The withheld-suite verdicts for the discarded revisions are derived from exact source semantics, not from a pytest run I performed. The failures involved are deterministic language/interpreter outcomes, and the reproduction script in §5 lets anyone confirm every number; until it is run in a shell, treat the discarded-revision column as strongly-evidenced, not executed.
2. **Sha256 values were not recomputed** (no hashing tool); reconstruction fidelity rests on the three-way textual identity check documented in §0 plus the harness's own recorded `sha256`/`bytes`.
3. **One revision per task was reconstructed by content equality only** (e.g. T-28 `052a375a…` and T-07 `0ee3867d…`/`f33772f8…` alternates): their exact bytes come from the envelope, and the T-07 `052a375a`-style variant ordering in the script (§5) must be run to confirm the derived pass/fail.
4. **Task-count projections** ("26 → 28/40", "+1 on `6b224f5`") are predictions about a fix that does not exist yet; I verified only that a passing revision existed and was discarded, not the fix's realised effect.
5. The run-level "N=1, ±2 tasks" noise band in §4 is untouched by this review; even with the three tasks recovered, single-run deltas remain inside that band.

---

## Shell-capable re-run (executed)

The Tier-B reconstruction above is now backed by an actual execution on a shell-capable host. Each discarded revision was recovered verbatim from the run's own `trajectory.jsonl` (the `model_call` / `implement_write` envelope's `files[].content`), written to a file named by its sha256 prefix, applied to a **pristine** corpus copy, and the withheld suite run through `bench/external_score.py` (which internally runs `checks.py verify`: pytest + the untouched-file contract + the report gate). Before running, each of the three **delivered** revisions was confirmed byte-identical by sha256 to both its `work/...` file and its `grade/.../repo/...` applied copy on disk:

```
a801efc38667ec52e336a703e94e0ca029c5b0f62318c980b30b047600ce04e6  v2sweep-20261011T070710Z/T-28-plugin-registry-scaffold-1/work/plugins/registry.py
3ae7dd6f0921c159d60c637050df73569c06a1e486038391dddaaa405e080d77  v2sweep-20261011T065821Z/T-17-log-hour-format-1/work/logparse/parser.py
82a15f898aafdf1309c8b5918db01d5a5a6149370599d27bf1c2b9bab54f4734  v2sweep-20261009T114754Z/T-07-f-string-sql-1/work/contacts/store.py
```

All reconstructed revisions were recovered from their trajectory records; **no seq/run was missing**, so the STOP condition ("record exactly which seq/run is missing") did not fire. Every reconstructed file's sha256 prefix matched the recorded `source_write.sha256` and the artifact's table.

### Exact commands (run from `/home/z/vibe/helpagent`)

```bash
# 1. reconstruct every implement_write revision from the run records
python3 - <<'PY'
import json, hashlib
from pathlib import Path
TASKS = {
    'T-28-plugin-registry-scaffold': ('v2sweep-20261011T070710Z','T-28-plugin-registry-scaffold-1','plugins/registry.py'),
    'T-17-log-hour-format':          ('v2sweep-20261011T065821Z','T-17-log-hour-format-1','logparse/parser.py'),
    'T-07-f-string-sql':             ('v2sweep-20261009T114754Z','T-07-f-string-sql-1','contacts/store.py'),
}
out = Path('/tmp/d1check2'); out.mkdir(parents=True, exist_ok=True)
for task,(run,d,rel) in TASKS.items():
    for line in (Path('bench/runs')/run/d/'trajectory.jsonl').read_text().splitlines():
        if not line.strip(): continue
        e = json.loads(line)
        if e.get('kind')=='model_call' and e.get('step_type')=='implement_write':
            for f in (e.get('envelope') or {}).get('files') or []:
                c = f['content']; h = hashlib.sha256(c.encode()).hexdigest()[:8]
                (out/f"{task}__{h}.py").write_text(c)
PY

# 2. apply each revision to a pristine corpus copy and run the withheld suite
python3 - <<'PY'
from pathlib import Path
from bench.external_score import external_score
CORPUS = Path("bench/corpus"); WORK = Path("/tmp/d1check2/work")
CASES = [
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "88f26d23", "n=1/n=2 (class only)"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "e8484d8b", "n=4 discarded PASS-claim"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "052a375a", "n=5 discarded artifact-claims-pass"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "1bfbf536", "n=6 terminal"),
    ("T-28-plugin-registry-scaffold", "plugins/registry.py",   "a801efc3", "n=3 DELIVERED"),
    ("T-17-log-hour-format",          "logparse/parser.py",    "77cc9fd7", "n=1/3/6/7 PASS-claim"),
    ("T-17-log-hour-format",          "logparse/parser.py",    "f1ed6518", "n=4/n=5"),
    ("T-17-log-hour-format",          "logparse/parser.py",    "3ae7dd6f", "n=2 DELIVERED"),
    ("T-07-f-string-sql",             "contacts/store.py",     "ee45fb88", "n=1/n=2 PASS-claim"),
    ("T-07-f-string-sql",             "contacts/store.py",     "039c8b91", "n=3"),
    ("T-07-f-string-sql",             "contacts/store.py",     "0ee3867d", "n=4"),
    ("T-07-f-string-sql",             "contacts/store.py",     "f33772f8", "n=5"),
    ("T-07-f-string-sql",             "contacts/store.py",     "82a15f89", "n=6 DELIVERED"),
]
for task, rel, h, label in CASES:
    out = external_score(CORPUS/task, {rel: Path(f"/tmp/d1check2/{task}__{h}.py").read_text()}, WORK)
    print(f"{task:32s} {h} {label:32s} passed={out.passed!s:5s} exit={out.exit}")

# 3. (for the discrepancy case) full pytest output on the applied copy
#    cd /tmp/d1check2/detail/<task>__<rev>/<task>/repo && python3 -m pytest -q tests
PY
```

### Results — executed verdict per revision

`external_score.passed` is the full grader verdict (pytest + untouched-file contract + report gate). "artifact Tier-B" is what the document above *predicted*.

| task | revision (write seq) | artifact Tier-B claim | executed `external_score` | executed pytest |
| --- | --- | --- | --- | --- |
| T-28 | `88f26d23` (582/597) | fail 4/4 | fail | 4 failed |
| T-28 | `e8484d8b` (622) | pass 4/4 | **pass** | **4 passed** |
| T-28 | `052a375a` (634) | pass 4/4 | **fail — contradicts artifact** | **4 failed** |
| T-28 | `1bfbf536` (645) | fail 3/4 | fail | 3 failed, 1 passed |
| T-28 | `a801efc3` (611, **DELIVERED**) | fail 4/4 | fail | 4 failed |
| T-17 | `77cc9fd7` (1219/1240/1265/1273) | pass 2/2 | **pass** | **2 passed** |
| T-17 | `f1ed6518` (1251/1257) | fail 2/2 | fail | 2 failed |
| T-17 | `3ae7dd6f` (1228, **DELIVERED**) | fail 2/2 | fail | 2 failed |
| T-07 | `ee45fb88` (40/49) | pass 2/2 | **pass** | **2 passed** |
| T-07 | `039c8b91` (56) | fail 2/2 | fail | 2 failed |
| T-07 | `0ee3867d` (62) | pass 2/2 | **pass** | **2 passed** |
| T-07 | `f33772f8` (68) | pass 2/2 | **pass** | **2 passed** |
| T-07 | `82a15f89` (75, **DELIVERED**) | fail 1/2 | fail | 1 failed, 1 passed |

### Raw output

Key cases, `bench/external_score.py` (`checks.py verify` output):

```
== T-28 e8484d8b (n=4 discarded) ==   external_score.passed=True exit=0
== checks: T-28-plugin-registry-scaffold ==
[tests]    OK (python -m pytest in repo/)
[contract] OK (5 untouched paths byte-identical)
result: PASS

== T-28 052a375a (n=5 discarded) ==   external_score.passed=False exit=1
           FAILED tests/test_plugins.py::test_get_unknown_raises - AttributeError: modul...
           FAILED tests/test_plugins.py::test_register_duplicate_rejected - AttributeErr...
           FAILED tests/test_plugins.py::test_run_passes_args - AttributeError: module '...
           4 failed in 0.03s
[contract] OK (5 untouched paths byte-identical)
result: FAIL

== T-28 a801efc3 (n=3 DELIVERED) ==   external_score.passed=False exit=1
           FAILED tests/test_plugins.py::test_get_unknown_raises - AttributeError: modul...
           FAILED tests/test_plugins.py::test_register_duplicate_rejected - AttributeErr...
           FAILED tests/test_plugins.py::test_run_passes_args - AttributeError: module '...
           4 failed in 0.02s
[contract] OK (5 untouched paths byte-identical)
result: FAIL

== T-17 77cc9fd7 (n=1/3/6/7) ==        external_score.passed=True exit=0
[tests]    OK (python -m pytest in repo/)
[contract] OK (5 untouched paths byte-identical)
result: PASS

== T-17 3ae7dd6f (n=2 DELIVERED) ==    external_score.passed=False exit=1
           FAILED tests/test_parser.py::test_afternoon_hour_is_parse - ValueError: time ...
           FAILED tests/test_parser.py::test_morning_hour_unchanged - ValueError: time d...
           2 failed in 0.05s
[contract] OK (5 untouched paths byte-identical)
result: FAIL

== T-07 ee45fb88 (n=1) ==              external_score.passed=True exit=0
[tests]    OK (python -m pytest in repo/)
[contract] OK (4 untouched paths byte-identical)
result: PASS

== T-07 82a15f89 (n=6 DELIVERED) ==    external_score.passed=False exit=1
           contacts/store.py:23: OperationalError
           FAILED tests/test_store.py::test_name_with_apostrophe_round_trips - sqlite3.O...
           1 failed, 1 passed in 0.02s
[contract] OK (4 untouched paths byte-identical)
result: FAIL
```

Full pytest output for the T-28 n=5 discrepancy (`052a375a`), run directly in the applied copy:

```
$ (cd /tmp/d1check2/detail/T-28-plugin-registry-scaffold__052a375a/T-28-plugin-registry-scaffold/repo && python3 -m pytest -q tests)
FFFF                                                                     [100%]
________________________________ FAILURES _________________________________
____________________________ test_register_and_get _____________________________

    def test_register_and_get():
>       registry.register("greet", lambda: "hi")
        ^^^^^^^^^^^^^^^^^
E       AttributeError: module 'plugins.registry' has no attribute 'register'. Did you mean: 'registry'?

tests/test_plugins.py:9: AttributeError
___________________________ test_get_unknown_raises ____________________________

    def test_get_unknown_raises():
        with pytest.raises(KeyError):
>           registry.get("nope")
            ^^^^^^^^^^^^
E           AttributeError: module 'plugins.registry' has no attribute 'get'

tests/test_plugins.py:15: AttributeError
_______________________ test_register_duplicate_rejected _______________________

    def test_register_duplicate_rejected():
>       registry.register("dup", lambda: 1)
        ^^^^^^^^^^^^^^^^^
E       AttributeError: module 'plugins.registry' has no attribute 'register'. Did you mean: 'registry'?

tests/test_plugins.py:19: AttributeError
_____________________________ test_run_passes_args _____________________________

    def test_run_passes_args():
>       registry.register("add", lambda a, b: a + b)
        ^^^^^^^^^^^^^^^^^
E       AttributeError: module 'plugins.registry' has no attribute 'register'. Did you mean: 'registry'?

tests/test_plugins.py:25: AttributeError
=========================== short test summary info ============================
FAILED tests/test_plugins.py::test_register_and_get - AttributeError: module ...
FAILED tests/test_plugins.py::test_get_unknown_raises - AttributeError: modul...
FAILED tests/test_plugins.py::test_register_duplicate_rejected - AttributeErr...
FAILED tests/test_plugins.py::test_run_passes_args - AttributeError: module '...
4 failed in 0.03s
```

### Discrepancy: the artifact's Correction 1 on T-28 is REFUTED by execution

The artifact's Correction 1 claims the T-28 n=5 revision `052a375a` (write seq 634) also passes the withheld suite 4/4, because its module-level `registry = Registry()` instance would satisfy `from plugins import registry` + `registry.register/get/run`. Executed, `052a375a` **fails 4/4**. The reason is Python name resolution: `from plugins import registry` binds the **submodule object** `plugins.registry`, not the module-level `registry` variable defined inside it, so the imported module has no top-level `register`/`get`/`run` and every test raises `AttributeError: module 'plugins.registry' has no attribute 'register'`. Only the n=4 revision `e8484d8b`, which defines module-level `register/get/run` functions over a single shared `registry` instance, passes — and it does so 4/4.

Consequences for the artifact:

* **Correction 1 does not stand.** There is exactly one passing discarded T-28 revision (`e8484d8b`), not two. This does **not** affect the pivotal T-28 claim: a grader-passing revision (`e8484d8b`) demonstrably existed in the run and the failing revision `a801efc3` was delivered (both re-confirmed by execution).
* **Correction 2 is half-confirmed.** Its surviving limb is reproduced: `1bfbf536` (n=6) clears `documented_api_missing` yet fails the grader (3 failed, 1 passed), so `documented_api_missing` is not sufficient for a grader pass, and `052a375a` also fails the check — but since `052a375a` fails **both** the check and the grader, the artifact's "fails the check yet passes the grader" counterexample is wrong. The accepted conclusion (the check is neither necessary nor sufficient for the grader) still holds on the `1bfbf536` limb alone, and Correction 2 remains the finding passed to the fix worker.

The refuted Correction 1 changes no verdict: the pivotal T-28 result (`e8484d8b` passes, `a801efc3` delivered and fails) and all T-17/T-07 results reproduce exactly; only the artifact's count of passing T-28 revisions is corrected from two to one.
