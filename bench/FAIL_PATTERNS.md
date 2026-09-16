# FAIL_PATTERNS — harness/model failure classes found by the benchmark loop

DESIGN §6 process: every run → entry here → harness fix → re-run → score must move
or the feature dies. Each entry: pattern, evidence (task/run), fix layer, status.

| id | pattern | evidence | fix layer | status |
| --- | --- | --- | --- | --- |
| FP-1 | **Docstring-quote strip on re-emission.** The 4B re-emits a file seen in the artifacts with `"""` quotes dropped → line-1 parse error. Near-deterministic at temp 0.2 (4/4 replicas). | M1 owner verification, T-01; run captures 20260916 | composer: hard-rules block for content steps ("module docstring, imports, and all" — M0-proven wording) | **CLOSED** — A/B: weak phrasing 0/4 → M0 wording first-call green |
| FP-2 | **Status-semantics confusion.** The model reports the tests' current state (failed) as its own operation status → a correct fix sits in the envelope, discarded by the router. Deterministic: all N best-of-n candidates identical. | M2 sweep, T-02 (canonical fix `end = start + per_page` present in 5 discarded candidates) | composer: status rule ("status describes YOUR edit, never the test results") | **CLOSED** — T-02 first-attempt green post-fix |
| FP-3 | **Grounding false positive on prose abbreviations.** "e.g"/"i.e" match the file-token shape → ungrounded-reference rejection of a legitimate plan. | M2 sweep, T-07 (expand died on `e.g`) | kernel: abbreviation whitelist in the grounding validator | **CLOSED** — T-07 green post-fix |
| FP-4 | **Cross-file import synthesis.** Fix requires adding an import from a module that is only *shown*, not named by the failing test. First sample fails; best-of-n=3 usually recovers. | M2, mini_repo (NameError: MinirepoError; errors.py visible in current_files) | composer mitigation (best_of_n=3 on implement); structural fix = locate-driven context injection (C3/C4, M3) | **MITIGATED** — structural fix owned by M3 |
| FP-5 | **task_class wobble.** Same bugfix classified bugfix/scaffold/refactor across runs. Harmless in the single-path golden script; wrong under the TASK_TAXONOMY pipeline-routing table. | golden runs, task_card outputs | routing: task_class is grammar-constrained per-call; needs A2-stage example pinning or enum+rationale form | **OPEN** — blocks nothing until pipeline routing is implemented (M3+) |

Rules: a pattern enters this file only with a reproducible run reference; it leaves only
with a green re-run after the fix (evidence in bench/runs/). Composition-layer fixes
belong in the colocated prompt rules (DESIGN §4.1), not in per-task scripts.
