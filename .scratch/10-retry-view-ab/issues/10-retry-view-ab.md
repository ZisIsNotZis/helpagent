# 10 — Retry-view controlled comparison

Status: claimed
Owner: agent
Need-review: yes (scoped self-review)
Need-test-cases: yes (variant selection and propagation)

Objective: Test whether exposing the staged draft on retry improves quality versus showing the initial snapshot, without changing disk edits, budget, model, gates, or gear sequence. The shipped default remains `draft`; `--retry-view initial` is an experiment-only comparator, not a proposed product rollback mode.

Acceptance: freeze one revision, run both variants sequentially on a predefined retry-prone set at N=3 with the same reference model and arguments, reconcile every result row, inspect failure histories and calls, report uncertainty rather than infer benefit from tiny deltas. Preserve reproducible evidence. Do not edit the tree during sweeps.

Scope: T-27, T-28, T-29, T-31, T-32, T-34, A-02, T-33 and T-02 control. The difficult set contains persistent failures and a variable-success task; controls check multi-file and easy-task behavior. A pass on attempt 1 is not evidence for retry-view quality; analyze retry exposure separately.

- 2026-09-28 agent: starting clean `7841c2d`; added experimental `retry_view` argument to both tiered and golden flow. Unit tests and frozen sweep pending. Caveat: sequential A/B is not paired randomization; differences may still be sampling and server drift.
