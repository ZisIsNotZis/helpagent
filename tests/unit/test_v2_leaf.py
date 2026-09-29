"""Leaf-loop mechanics pinned with the scripted fake model (no live server, no network).

Every invariant in ticket 17 — and the fix-round policy that makes a false success
impossible — maps to a named case here. The whole file runs against
:class:`harness.fake_model.FakeModelRunner` and a scripted test runner, so
`uv run pytest -q` never touches a model server.

Fix-round policy covered:
- the run's own test must be RED ON ARRIVAL (run before implementing; green ⇒ re-ask
  once then ``no-red-target``; ``red=True`` is never emitted without observing it);
- ``exit == 0`` is the only green: ``exit=None`` (transport) and policy-blocked are red;
- a test may be replaced only with an INDEPENDENT judge's attribution, and the
  replacement must itself be red on arrival;
- a replacement is a real attempt, so an identical repeated rewrite is refused as
  ``wasted`` and the ladder advances;
- stop accounting is explicit (``stop_reason``), spec attribution yields ``bubble``
  with ``needs_parent``, and wasted escalations surface on the outcome and the record.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from harness.attempts import Attempt
from harness.budget import Budget
from harness.exec import ShapedResult
from harness.fake_model import FakeModelRunner, schema_violation
from harness.gate_report import GateReport
from harness.leaf import (
    LADDER,
    Escalation,
    IndependentTestCandidate,
    IndependentTestRequest,
    IndependentTestVerdict,
    JudgeRequest,
    JudgeVerdict,
    LeafOutcome,
    LeafSpec,
    apply_judge_filter,
    escalate,
    evaluate_independent_test,
    run_leaf,
)
from harness.runner import ledger_entries, reset_ledger_for_tests

_FAR_FUTURE = 2_000_000_000.0


# --------------------------------------------------------------------------- helpers


def write_env(path: str, content: str, comment: str = "edit the source", status: str = "ok") -> dict:
    return {"status": status, "comment": comment, "file_path": path, "content": content}


SELF_TEST = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert result() == 42\n")
SELF_TEST_ALT = write_env("tests/test_leaf_alt.py", "def test_goal():\n    assert result() == 0\n")


def impl(content: str = "def result():\n    return 42\n", path: str = "pkg/calc.py",
         comment: str = "fix the source") -> dict:
    return write_env(path, content, comment=comment)


def blocked(comment: str = "the test is wrong",
            path: str = "pkg/calc.py") -> dict:
    return write_env(path, "def result():\n    return 7\n", comment=comment, status="blocked")


def judge_blames_test(request: JudgeRequest) -> JudgeVerdict:
    """A structured judge verdict that passes the deterministic filter: it names the
    failing test function and one of its assertions (`result() == 42`)."""
    return JudgeVerdict(
        attribution="tests",
        defect="test_goal asserts result() == 42, which pins the wrong expectation",
        raw="tests",
    )


def scripted_red_gate() -> GateReport:
    """The scripted seam's RED machine-readable gate report (an observed, trustworthy
    red: pytest produced a report that says the test failed)."""
    return GateReport(report_path="(scripted)", process_exit=1, canary="scripted",
                      expected_files=(), n_tests=1, n_failed=1, n_errors=0,
                      passed_ids=(), failed_ids=("scripted::test_goal",), missing=(),
                      observed=True, anomaly="tests-failed", detail="1 failure(s)")


def iv_candidate(path: str = "tests/test_independent.py",
                 content: str = "from pkg.calc import result\n\n\ndef test_goal():\n    assert result() == 42\n"):
    """A deterministic independent-test candidate for mechanics tests."""
    return IndependentTestCandidate(path=path, content=content)


def iv_source() -> str:
    return "from pkg.calc import result\n\n\ndef test_goal():\n    assert result() == 42\n"


def iv_env(path: str = "tests/test_independent.py", content: str | None = None) -> dict:
    return {"status": "ok", "comment": "wrote the independent test", "file_path": path,
            "content": content or iv_source()}


def transport() -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=None,
                        verdict="transport_error", excerpts=["timed out after 120s"])


def policy_blocked() -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=None,
                        verdict="policy_blocked", policy_blocked=True,
                        excerpts=["command is not in the exec allowlist"])


def scripted_gate() -> GateReport:
    """The scripted seam's GREEN machine-readable gate report.

    Production reports come from the real pytest run (``--junitxml`` into a private
    directory plus a per-run canary, ticket 17 F1). The scripted seam stands in for a
    green gate so these mechanics tests keep pinning the LOOP rather than pytest's XML
    writer; the real gate is pinned by the forgery tests at the end of this file.
    """
    return GateReport(report_path="(scripted)", process_exit=0, canary="scripted",
                      expected_files=(), n_tests=1, n_failed=0, n_errors=0,
                      passed_ids=("scripted::test",), failed_ids=(), missing=(),
                      observed=True)


class ScriptedTests:
    """A deterministic ``run_tests`` seam: one result per call, last repeats.

    An item may be an exit code or a full :class:`ShapedResult` (so transport-error
    and policy-blocked shapes are scriptable). An exit code of 0 carries a green
    :func:`scripted_gate` report and any non-zero code carries an observed RED
    :func:`scripted_red_gate` (ticket 17 F1) — the loop then sees an ``observed`` red
    exactly as it does for a real failing pytest run, and so does the independent
    test's red-on-original gate.
    """

    def __init__(self, results, excerpts=None):
        self._results = list(results)
        self._excerpts = excerpts or {}
        self.calls = 0

    def __call__(self, workdir) -> ShapedResult:
        item = self._results[self.calls] if self.calls < len(self._results) else self._results[-1]
        self.calls += 1
        if isinstance(item, ShapedResult):
            return item
        code = item
        excerpts = [] if code == 0 else self._excerpts.get(
            code, ["FAILED tests/test_leaf_self.py::test_goal", "E AssertionError: still red"])
        return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=code,
                            verdict="ok" if code == 0 else "failed", excerpts=list(excerpts),
                            gate=scripted_gate() if code == 0 else scripted_red_gate())


def make_spec(files=None, grader=(), goal="make result() return 42") -> LeafSpec:
    return LeafSpec(
        goal=goal,
        files=files if files is not None else {"pkg/calc.py": "def result():\n    return 0\n"},
        acs=["result() returns 42"],
        interfaces=["result() -> int"],
        grader_paths=tuple(grader),
    )


def stage(tmp_path, files) -> None:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def run_leaf_sync(model, spec, workdir, budget, **kw):
    reset_ledger_for_tests()
    return asyncio.run(run_leaf(model, spec, workdir, budget, **kw))


def ledger_kinds() -> list[str]:
    return [entry["kind"] for entry in ledger_entries()]


# ------------------------------------------------------------------- the target


def test_red_self_test_is_kept_as_the_target(tmp_path):
    """Regression pin for the v1 dead-step / dropped-test defect: the run's own test
    is RUN on arrival, observed red, and KEPT as the target."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl("def result():\n    return 1\n"),
                                            impl("def result():\n    return 1\n")]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test == "tests/test_leaf_self.py"
    assert (tmp_path / "tests/test_leaf_self.py").exists()        # KEPT, never dropped
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]
    assert out.claimed is False
    assert "self_test_written" in ledger_kinds()


def test_green_on_arrival_reasks_once_then_stops_no_red_target(tmp_path):
    """A test that passes on arrival does not exercise the failure: re-ask ONCE, and
    if the replacement is green too, stop honestly — never claim a green from it."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0]))

    assert out.claimed is False
    assert out.signal == "honest-failure"
    assert out.stop_reason == "no-red-target"
    assert out.self_test is None
    assert out.attempts == []
    assert len(model.calls("write_test")) == 2          # exactly one re-ask


def test_green_on_arrival_reask_red_keeps_the_new_target(tmp_path):
    """The one re-ask is only rejected when it is green too: a red replacement becomes
    the kept target and the loop proceeds to a normal green."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 1, 0]))

    assert out.self_test == "tests/test_leaf_alt.py"
    assert out.claimed is True and out.signal == "green"
    assert (tmp_path / "tests/test_leaf_alt.py").read_text() == SELF_TEST_ALT["content"]


def test_claimed_requires_the_runs_own_test_exit_zero(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True
    assert out.signal == "green"
    assert out.stop_reason == "green"
    assert out.attempts[-1].outcome == "pass"


def test_model_comment_cannot_fake_a_green_claim(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl(comment="tests run green, all good"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.signal != "green"


def test_exit_none_and_policy_blocked_are_both_red(tmp_path):
    """exit==0 is the ONLY green; a transport error and a policy-blocked result are red."""
    spec = make_spec()

    for name, shape in (("transport", transport()), ("policy_blocked", policy_blocked())):
        work = tmp_path / name
        stage(work, spec.files)
        model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
        out = run_leaf_sync(model, spec, work,
                            Budget(calls=2, deadline_ts=_FAR_FUTURE),
                            run_tests=ScriptedTests([1, shape]))
        assert out.claimed is False, name
        assert out.signal != "green", name
        assert out.attempts[-1].outcome == "fail", name


# --------------------------------------------------------------- the blind gate


def test_grader_paths_never_enter_prompts_and_cannot_be_written(tmp_path):
    grader = ("tests/test_chain.py",)
    spec = make_spec(grader=grader)
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("tests/test_chain.py", "def test_cheat():\n    assert True\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=1, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    # Parameter-layer tolerance (live-run finding): the grader's names are withheld,
    # so the model naturally reuses them; the path is a parameter and is relocated.
    assert out.self_test == "tests/test_chain_leaf.py"
    assert (tmp_path / out.self_test).exists()
    assert not (tmp_path / "tests/test_chain.py").exists()
    assert out.claimed is False
    assert "self_test_relocated" in ledger_kinds()
    assert "tolerance_fired" in ledger_kinds()
    for record in model.calls("write_test"):
        assert "tests/test_chain.py" not in record.prompt


def test_self_test_may_not_overwrite_an_existing_path(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("pkg/calc.py", "def result():\n    return 99\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=1, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test == "tests/calc_leaf.py"          # relocated, never overwritten
    assert (tmp_path / "pkg/calc.py").read_text() == spec.files["pkg/calc.py"]
    assert "self_test_relocated" in ledger_kinds()


def test_non_test_self_test_path_is_relocated_into_tests(tmp_path):
    """A self-test must be a test path; a non-test path is a naming slip, so it is
    normalized into tests/ rather than killing the node."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("pkg/helper.py", "x = 1\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=1, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test == "tests/helper_leaf.py"
    assert not (tmp_path / "pkg/helper.py").exists()
    assert (tmp_path / out.self_test).exists()
    assert "tolerance_fired" in ledger_kinds()


def test_implement_cannot_write_a_test_or_grader_path(tmp_path):
    grader = ("tests/test_chain.py",)
    spec = make_spec(grader=grader)
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        write_env("tests/test_leaf_self.py", "def test_goal():\n    assert False\n"),
        write_env("tests/test_chain.py", "def test_cheat():\n    assert True\n"),
        impl(),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]
    assert not (tmp_path / "tests/test_chain.py").exists()
    assert out.claimed is True


# -------------------------------------------------------- escalation / exhaust


def test_repeat_escalation_is_refused_recorded_wasted_and_ladder_advances(tmp_path):
    spec = make_spec({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"})
    stage(tmp_path, spec.files)
    same = write_env("a.py", "x = 0\n", comment="try again")
    model = FakeModelRunner({"write_test": [SELF_TEST] + [same] * 8})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1] * 12))

    kinds = ledger_kinds()
    assert "escalation_wasted" in kinds
    assert out.wasted_escalations                            # surfaced on the outcome
    assert len(out.layers_used) >= 2                         # the ladder still advances
    assert model.total_calls < 9                             # never 9 identical retries (T-31)


def test_escalate_refuses_identical_repeat_and_empty_l4():
    base = Attempt(node_id="leaf", layer="implementation", strategy="L1-resample",
                   claimed_delta="try again", failure_signature="sig",
                   touched_files=["a.py"], outcome="fail", verdict="same")
    repeat = base.model_copy()
    decision = escalate([base, repeat], 0)
    assert decision.wasted is True and decision.strategy == LADDER[0]

    # L4 rule diagnosis must surface something; nothing new is not executed.
    assert escalate([base, repeat], 3, excerpts=["nothing a rule can use"]).wasted is True
    # A different rung is not a repeat, so it runs.
    assert escalate([base, repeat], 1).wasted is False

    # An unverified "undecided" novelty claim does not earn a same-rung retry.
    undecided = base.model_copy(update={"verdict": "undecided", "claimed_delta": "brand new"})
    assert escalate([undecided], 0).wasted is True


def test_node_exhaustion_needs_three_layers_and_keeps_ladder_moving(tmp_path):
    spec = make_spec({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"})
    stage(tmp_path, spec.files)
    same = write_env("a.py", "x = 0\n", comment="same idea")
    model = FakeModelRunner({"write_test": [SELF_TEST] + [same] * 8})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1] * 12))

    assert out.exhausted is True
    assert out.signal == "exhausted"
    assert out.stop_reason == "attempts"
    assert set(out.layers_used) >= {"sampling", "implementation", "spec"}
    assert "same-verdict tail" in out.exhaustion_reason


def test_exhaustion_refuses_while_a_structural_lever_is_untried(tmp_path):
    """Two same-verdict failures on one layer are NOT a dead end: the leaf must not
    claim exhaustion while re-split / parent-spec remain untried."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    same = write_env("pkg/calc.py", "def result():\n    return 1\n", comment="same")
    model = FakeModelRunner({"write_test": [SELF_TEST, same, same, same]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.exhausted is False
    assert out.signal == "honest-failure" and out.stop_reason == "calls"
    assert out.exhaustion_reason == "call-budget"


# ------------------------------------------------------------------------- stops


def test_call_budget_and_deadline_stops_are_distinguishable(tmp_path):
    spec = make_spec()
    budget_dir, deadline_dir = tmp_path / "budget", tmp_path / "deadline"
    stage(budget_dir, spec.files)
    stage(deadline_dir, spec.files)

    budget_model = FakeModelRunner({"write_test": [SELF_TEST]})
    budget_run = run_leaf_sync(budget_model, spec, budget_dir,
                               Budget(calls=1, deadline_ts=_FAR_FUTURE),
                               run_tests=ScriptedTests([1]), now=lambda: 100.0)

    deadline_model = FakeModelRunner({"write_test": [SELF_TEST]})
    deadline_run = run_leaf_sync(deadline_model, spec, deadline_dir,
                                 Budget(calls=9, deadline_ts=50.0),
                                 run_tests=ScriptedTests([1]), now=lambda: 100.0)

    assert budget_run.signal == "honest-failure"
    assert budget_run.stop_reason == "calls"
    assert budget_run.exhaustion_reason == "call-budget"
    assert deadline_run.signal == "handover"
    assert deadline_run.stop_reason == "deadline"
    assert deadline_run.exhaustion_reason == "deadline"
    assert budget_run.signal != deadline_run.signal


def test_expired_deadline_before_step_1_writes_nothing(tmp_path):
    """The deadline is checked BEFORE the first call: an already-expired budget hands
    over and touches neither the model nor the workdir."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({})
    before = sorted(p.name for p in tmp_path.iterdir())

    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=50.0),
                        run_tests=ScriptedTests([1]), now=lambda: 100.0)

    assert out.signal == "handover"
    assert out.stop_reason == "deadline"
    assert out.calls == 0
    assert model.total_calls == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert "self_test_written" not in ledger_kinds()


# ---------------------------------------------------------------------- judging


def test_test_wrong_claim_without_independent_judge_is_not_credited(tmp_path):
    """judge=None ⇒ the model's own "the test is wrong" claim is never credited: no
    rewrite, the failure is treated as an implementation failure and escalates."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), blocked(), blocked()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        judge=None, run_tests=ScriptedTests([1] * 6))

    assert out.test_rewrites == 0
    assert out.own_test_mutated is False
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]
    assert "test_blame_uncredited" in ledger_kinds()
    assert "escalation_wasted" in ledger_kinds()             # ladder still advances
    assert out.claimed is False


def test_judge_tests_rewrites_the_test_and_later_green_is_green_after_rewrite(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert result() == 0\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})

    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        return JudgeVerdict(attribution="tests", raw="tests",
                            defect="test_goal asserts result() == 42, the wrong expectation")

    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1, 1, 0]))

    assert seen and seen[0].test_path == "tests/test_leaf_self.py"
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == repaired["content"]
    assert (tmp_path / "pkg/calc.py").read_text() == impl()["content"]  # only the real impl
    assert out.attempts[0].layer == "tests"                  # the repair, not a fake progress
    assert "tests" in out.layers_used
    assert out.test_rewrites == 1
    assert out.own_test_mutated is True
    # Finding 3: a green after the run REPLACED its own test is never a claim — the
    # implementation satisfied a substituted test, so the outcome is unverified.
    assert out.claimed is False
    assert out.signal == "green-after-test-rewrite"
    assert out.stop_reason == "green-after-test-rewrite"
    assert out.claimed_basis == "own-test"


def test_rewrite_green_on_arrival_is_rejected_as_no_red_target(tmp_path):
    """A judge-authorized replacement must itself be RED ON ARRIVAL; a vacuous green
    rewrite is not a target and cannot become a success."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "no-red-target"
    assert out.test_rewrites == 1
    assert out.own_test_mutated is True


def test_repeated_identical_test_rewrite_is_refused_wasted_and_ladder_advances(tmp_path):
    """A judge-authorized rewrite is a real attempt: an identical repeat is refused as
    ``wasted`` and the ladder moves on (the no-repeat invariant must not be bypassed)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert result() == 0\n")
    model = FakeModelRunner({"write_test": [
        SELF_TEST, blocked(), repaired, blocked(), repaired, impl(comment="try", content="def result():\n    return 1\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1] * 6))

    assert len(out.wasted_escalations) == 1
    assert out.wasted_escalations[0].strategy == LADDER[0]
    assert "escalation_wasted" in ledger_kinds()
    assert "implementation" in out.layers_used               # the ladder advanced past L1
    assert out.test_rewrites == 2
    assert out.own_test_mutated is True


def test_insufficient_calls_for_a_multi_call_escalation_stops_cleanly(tmp_path):
    """A judge + rewrite is a multi-call escalation: with no calls left the leaf stops
    with stop_reason ``calls`` and never lets a BudgetError escape mid-run."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked()]})

    judge_calls: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        judge_calls.append(request)
        return judge_blames_test(request)

    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1] * 4))

    assert out.stop_reason == "calls"
    assert out.signal == "honest-failure"
    assert judge_calls == []                                 # not even started
    assert len(model.calls("write_test")) == 2               # self-test + the blocked attempt


def test_spec_attribution_yields_bubble_needs_parent_and_stops(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked()]})

    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        judge=lambda request: "spec", run_tests=ScriptedTests([1]))

    assert out.signal == "bubble"
    assert out.needs_parent is True
    assert out.stop_reason == "spec-bubble"
    assert out.claimed is False
    assert out.calls < 20                                   # does not burn the rest
    assert "spec" in out.layers_used
    assert "spec_bubbled_up" in ledger_kinds()
    assert out.questions and out.questions[-1].state == "open"
    assert len(model.calls("write_test")) == 2              # self-test + the blocked attempt


# ------------------------------------------------------------------ M1 / M2 mode


def test_m2_runs_first_then_m1_after_a_repeat(tmp_path):
    spec = make_spec({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"})
    stage(tmp_path, spec.files)
    same = write_env("a.py", "x = 0\n", comment="same idea")
    model = FakeModelRunner({"write_test": [SELF_TEST] + [same] * 8})
    run_leaf_sync(model, spec, tmp_path,
                  Budget(calls=20, deadline_ts=_FAR_FUTURE),
                  run_tests=ScriptedTests([1] * 12))

    modes = [entry["mode"] for entry in ledger_entries() if entry["kind"] == "leaf_attempt"]
    assert modes[0] == "M2"
    assert "M1" in modes


# ----------------------------------------------------------- persistence record


def test_wasted_escalations_surface_in_the_persisted_record(tmp_path):
    """Wasted escalations must be visible on the outcome AND in the persisted run
    record (bench/v2_leaf.py run.json), not only in the process-global ledger."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="call-budget",
        layers_used=["sampling"], stop_reason="calls",
        wasted_escalations=[Escalation("L1-resample", "sampling", True, "identical attempt refused")],
        test_rewrites=0, own_test_mutated=False, needs_parent=False)
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)

    assert record["stop_reason"] == "calls"
    assert record["wasted_escalations"][0]["strategy"] == "L1-resample"
    assert record["own_test_mutated"] is False and record["test_rewrites"] == 0
    json.dumps(record)                                       # must persist as JSON


# ----------------------------------------------------------- scripted-only proof


def test_mechanics_run_entirely_on_the_scripted_fake_model(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert isinstance(model, FakeModelRunner)
    assert out.claimed is True
    assert model.total_calls == 2          # self-test + one implementation


def test_leafspec_is_frozen_and_grader_paths_default_empty():
    spec = LeafSpec(goal="g", files={}, acs=[], interfaces=[])
    assert spec.grader_paths == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.goal = "changed"  # type: ignore[misc]


def test_v2_driver_quadrant_mapping():
    from bench.v2_leaf import quadrant

    assert quadrant(True, True) == "true-success"
    assert quadrant(True, False) == "false-success"
    assert quadrant(False, True) == "missed-success"
    assert quadrant(False, False) == "honest-failure"


def test_v2_driver_stages_a_source_only_blind_spec(tmp_path):
    """The driver hands the leaf a source-only view and withholds the grader suite."""
    from bench.v2_leaf import build_spec, load_task

    task_dir = tmp_path / "T-x"
    (task_dir / "repo" / "pkg").mkdir(parents=True)
    (task_dir / "repo" / "pkg" / "calc.py").write_text("x = 1\n")
    (task_dir / "repo" / "tests").mkdir()
    (task_dir / "repo" / "tests" / "test_grader.py").write_text("def test_g():\n    assert True\n")
    (task_dir / "request.md").write_text("fix the thing")

    spec = build_spec(load_task(task_dir))
    assert spec.goal == "fix the thing"
    assert "tests/test_grader.py" not in spec.files
    assert spec.grader_paths == ("tests/test_grader.py",)
    # acceptance criteria are derived from the request (round 7)
    assert spec.acs == ["fix the thing"]


def test_extract_acs_is_deterministic_over_prose_and_bullets():
    """One criterion per requirement sentence / bullet: comments and headers dropped,
    bullets and sentences split, whitespace collapsed, duplicates removed in order."""
    from bench.v2_leaf import extract_acs

    request = (
        "<!-- ANCHOR TASK — ignore me -->\n"
        "# Instructions\n"
        "Sessions must expire after an hour. Several products never show up at all.\n"
        "- simple words\n"
        "- contractions (it's a word)\n"
        "1. numbers are words\n"
        "- simple words\n"
    )
    assert extract_acs(request) == [
        "Sessions must expire after an hour.",
        "Several products never show up at all.",
        "simple words",
        "contractions (it's a word)",
        "numbers are words",
    ]
    assert extract_acs("") == []


def test_extract_acs_reflows_wrapped_prose_and_skips_fenced_examples():
    """Wrapped request lines are one sentence, not fragments; a fenced example block is
    example output, not a requirement."""
    from bench.v2_leaf import extract_acs

    request = (
        "The listing looks short — with 4 items per page I only ever get 3, and every\n"
        "page is missing its last item. It smells like an off-by-one.\n"
        "```text\n"
        "123: 1\n"
        "agent: 1\n"
        "```\n"
    )
    assert extract_acs(request) == [
        "The listing looks short — with 4 items per page I only ever get 3, and every page is missing its last item.",
        "It smells like an off-by-one.",
    ]


def test_policy_blocked_with_exit_zero_is_red(tmp_path):
    """Verification crack (closed): a crafted policy_blocked result that also carried
    exit=0 was scored green, contradicting ShapedResult.ok. It must never be green."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    crafted = ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=0,
                           verdict="policy_blocked", policy_blocked=True,
                           excerpts=["blocked by sandbox policy"])
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([crafted, 1]))

    assert out.claimed is False
    assert out.signal != "green"


def test_self_test_transport_error_is_not_recorded_as_a_red(tmp_path):
    """red=True is only emitted for an OBSERVED red; a transport error leaves no
    bogus target behind and stops honestly."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([transport()]))

    assert out.claimed is False
    assert out.stop_reason == "self-test"
    assert out.self_test is None
    assert not (tmp_path / "tests" / "test_leaf_self.py").exists()
    assert "self_test_written" not in ledger_kinds()


def test_rewrite_green_on_arrival_leaves_no_bogus_target_on_disk(tmp_path):
    """A weakened (vacuous) replacement that is green on arrival must not survive as
    a delivered artifact."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,                                  # red on arrival: a real target
        blocked(comment="the test is wrong"),
        write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n",
                  comment="rewrote the test"),
    ]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        run_tests=ScriptedTests([1, 0]),
        judge=judge_blames_test,
    )

    assert out.claimed is False
    assert out.stop_reason == "no-red-target"
    assert out.test_rewrites == 1
    assert not (tmp_path / "tests" / "test_leaf_self.py").exists()


# ------------------------------------------------------- malformed-output robustness
# A model failure is DATA, not a crash: every envelope request is retried a bounded
# number of times and a persistent malformed output stops the run as malformed-output.


def test_malformed_self_test_envelope_is_retried_then_stops_malformed_output(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [schema_violation()] * 3})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.signal == "honest-failure"
    assert out.stop_reason == "malformed-output"
    assert "malformed-output" in out.exhaustion_reason
    assert len(model.calls("write_test")) == 3          # 1 attempt + 2 retries
    assert "envelope_malformed" in ledger_kinds()
    assert "self_test_written" not in ledger_kinds()


def test_malformed_envelope_recovers_on_a_bounded_retry(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [schema_violation(), SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert len(model.calls("write_test")) == 3          # malformed + retry + implement
    assert "envelope_malformed" in ledger_kinds()


def test_a_raising_model_never_crashes_the_leaf(tmp_path):
    class ModelBoom(RuntimeError):
        pass

    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [ModelBoom("transport dropped")] * 3})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.stop_reason == "malformed-output"
    assert out.claimed is False
    assert len(model.calls("write_test")) == 3


def test_malformed_implement_envelope_stops_malformed_output(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, *[schema_violation()] * 3]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.self_test == "tests/test_leaf_self.py"          # the red target is kept
    assert out.stop_reason == "malformed-output"
    assert len(model.calls("write_test")) == 4                 # self-test + 3 implement tries


def test_malformed_judge_output_is_retried_then_stops_malformed_output(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked()]})
    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        raise ValueError("judge output was not a verdict")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=9, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1] * 4))

    assert out.stop_reason == "malformed-output"
    assert out.claimed is False
    assert len(seen) == 3                                      # 1 attempt + 2 retries


def test_malformed_test_rewrite_is_retried_then_stops_malformed_output(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), *[schema_violation()] * 3]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1] * 6))

    assert out.stop_reason == "malformed-output"
    assert out.test_rewrites == 0
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]


def test_malformed_output_with_no_budget_for_a_retry_stops_calls(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [schema_violation()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=1, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.stop_reason == "calls"
    assert len(model.calls("write_test")) == 1


# ------------------------------------------------ independent judge: the deterministic
# filter. `tests` is honoured ONLY when the defect names the failing test function or
# an assertion/expectation; anything else is coerced to implementation and recorded.


def test_apply_judge_filter_domain_and_coercion():
    request = JudgeRequest(
        goal="g", failure="FAILED tests/test_x.py::test_goal\nE AssertionError",
        test_path="tests/test_x.py",
        test_content="def test_goal():\n    assert result() == 42\n", files={})

    # honoured: names the failing test function
    assert apply_judge_filter(JudgeVerdict(attribution="tests", defect="test_goal is wrong"),
                              request).attribution == "tests"
    # honoured: names the assertion expectation
    kept = apply_judge_filter(JudgeVerdict(attribution="tests", defect="the test asserts result() == 42 wrongly"),
                              request)
    assert kept.attribution == "tests" and kept.coerced is False
    # coerced: a vibe with no anchor / an empty defect
    vibes = apply_judge_filter(JudgeVerdict(attribution="tests", defect="the test is just wrong"), request)
    assert vibes.attribution == "implementation" and vibes.coerced is True
    assert vibes.coercion_reason
    assert apply_judge_filter(JudgeVerdict(attribution="tests", defect="   "), request).attribution == "implementation"
    # a bare expected value with no test/assertion reference is NOT enough
    assert apply_judge_filter(JudgeVerdict(attribution="tests", defect="the code returns 0, not 42"),
                              request).attribution == "implementation"
    # spec / environment pass through untouched
    assert apply_judge_filter(JudgeVerdict(attribution="spec", defect="the AC contradicts"),
                              request).attribution == "spec"
    assert apply_judge_filter(JudgeVerdict(attribution="environment"), request).attribution == "environment"
    # alias is canonicalized; an unknown label is coerced
    assert apply_judge_filter(JudgeVerdict(attribution="test", defect="test_goal is wrong"),
                              request).attribution == "tests"
    unknown = apply_judge_filter(JudgeVerdict(attribution="banana"), request)
    assert unknown.attribution == "implementation" and unknown.coerced is True


def test_vibe_tests_attribution_is_coerced_and_the_source_fix_is_credited(tmp_path):
    """A judge that says "the test is wrong" without naming the test/assertion is NOT
    credited: the source fix is taken as the implementation path and can still green."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), impl(comment="fixed the source")]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(attribution="tests", defect="the test is wrong"),
        run_tests=ScriptedTests([1, 0]))

    assert out.test_rewrites == 0
    assert out.claimed is True and out.signal == "green"
    coerced = out.attempts[0].judge
    assert coerced is not None and coerced.attribution == "implementation"
    assert coerced.coerced is True
    assert "judge_coerced" in ledger_kinds()
    assert out.judge_verdicts[-1].coerced is True


def test_honoured_tests_verdict_is_recorded_on_the_repair_attempt(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert result() == 0\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1, 1, 0]))

    verdict = out.attempts[0].judge
    assert verdict is not None and verdict.attribution == "tests" and verdict.coerced is False
    assert out.judge_verdicts[0].attribution == "tests"
    # the per-attempt verdict must survive JSON persistence (run record)
    json.dumps([a.model_dump(mode="json") for a in out.attempts])


def test_run_record_records_judge_and_iv_modes_and_every_verdict():
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=True, signal="green", attempts=[], calls=4, wall_s=1.0,
        self_test="tests/test_x.py", questions=[], exhausted=False, exhaustion_reason="",
        layers_used=["spec"], stop_reason="green", test_rewrites=0, own_test_mutated=False,
        claimed_basis="own-test+independent-test",
        independent_test=iv_source(),
        independent_test_path="tests/test_independent.py",
        independent_test_node_ids=["tests/test_independent.py::test_goal"],
        iv_original_gate=scripted_red_gate(),
        iv_final_gate=scripted_gate(),
        iv_verdicts=[IndependentTestVerdict(
            approved=True, path="tests/test_independent.py", content=iv_source(),
            node_ids=("tests/test_independent.py::test_goal",),
            original_gate=scripted_red_gate(), final_gate=scripted_gate())],
        judge_verdicts=[JudgeVerdict(attribution="tests", defect="test_x is wrong",
                                     raw="r", coerced=True, coercion_reason="filter")])
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[],
                          restored=["conftest.py: kept pristine (grader-owned; nothing to restore)"])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0, judge_enabled=True,
                          iv_enabled=True, acs=["result() returns 42"])

    assert record["judge"] is True
    assert record["iv"] is True
    assert record["acs"] == ["result() returns 42"]
    assert record["claimed_basis"] == "own-test+independent-test"
    assert record["judge_verdicts"][0]["attribution"] == "tests"
    assert record["judge_verdicts"][0]["coerced"] is True
    assert record["independent_test"] == iv_source()
    assert record["independent_test_node_ids"] == ["tests/test_independent.py::test_goal"]
    assert record["iv_original_gate"]["anomaly"] == "tests-failed"
    assert record["iv_final_gate"]["anomaly"] == ""
    assert record["iv_verdicts"][0]["approved"] is True
    assert record["grader_restored"]                      # restores land in the record
    json.dumps(record)


def test_judge_request_never_exposes_a_grader_path(tmp_path):
    """The blind gate holds for the judge too: the grader's withheld paths can never
    appear in the goal, the run's own test, the failing output, or the source view."""
    grader = ("tests/test_chain.py",)
    spec = make_spec(grader=grader)
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked()]})
    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        return JudgeVerdict(attribution="implementation", defect="the source is wrong")

    run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                  judge=judge, run_tests=ScriptedTests([1]))

    assert seen
    blob = "\n".join([seen[0].test_content, seen[0].failure, *seen[0].files.values()])
    assert "tests/test_chain.py" not in blob
    assert seen[0].acs == spec.acs
    assert "pkg/calc.py" in seen[0].files


def test_driver_judge_defaults_on_and_no_judge_disables_the_baseline():
    from bench.v2_leaf import build_parser

    assert build_parser().parse_args(["--task", "t"]).judge is True
    assert build_parser().parse_args(["--task", "t", "--judge"]).judge is True
    assert build_parser().parse_args(["--task", "t", "--no-judge"]).judge is False


def test_driver_model_judge_maps_the_debug_judge_envelope():
    """The default judge reuses the §16 debug_judge envelope (no new schema) and
    reads an ``unable`` verdict as an environment attribution."""
    from bench.v2_leaf import model_judge

    model = FakeModelRunner({"debug_judge": [
        {"status": "ok", "comment": "judged", "blame": "test",
         "problem": "test_goal asserts the wrong value",
         "fixes": [{"rank": 1, "approach": "fix the test", "how": "assert 0"}]},
        {"status": "unable", "comment": "cannot judge", "unable_reason": "no interpreter"},
    ]})
    request = JudgeRequest(goal="g", failure="f", test_path="tests/test_x.py",
                           test_content="def test_goal():\n    assert True\n", files={},
                           acs=["AC-1"])

    verdict = asyncio.run(model_judge(model, request))
    assert verdict.attribution == "tests" and "test_goal" in verdict.defect
    assert model.calls("debug_judge")[0].fresh is True          # fresh context
    assert model.calls("debug_judge")[0].artifacts == {}
    unable = asyncio.run(model_judge(model, request))
    assert unable.attribution == "environment" and unable.defect == "no interpreter"


def test_driver_independent_test_prompt_carries_the_repair_evidence():
    """Round 8: the bounded repair is the SAME fresh-context producer, and the rejected
    test plus its verdict ride the question (the driver never sees a grader path)."""
    from bench.v2_leaf import _independent_test_question

    base = IndependentTestRequest(goal="g", acs=["a"], original={"pkg/x.py": "orig"},
                                  final={"pkg/x.py": "fixed"})
    assert "REJECTED" not in _independent_test_question(base)

    repaired = dataclasses.replace(
        base, previous_test="def test_goal():\n    assert True\n",
        repair_reason="independent-test-not-red", repair_detail="it passed on the original")
    question = _independent_test_question(repaired)
    assert "REJECTED (independent-test-not-red)" in question
    assert "it passed on the original" in question
    assert "def test_goal()" in question


# ------------------------------------------------ independent test (ticket 17 round 7)
# claimed=True additionally requires a fresh-context INDEPENDENT TEST, checked
# DETERMINISTICALLY on private copies: it must FAIL on the pre-run source (red on
# original) and PASS on the final source (green on final). The run's workdir never
# holds the test, the run never sees it, and a rejection is the next attempt's failure
# context (never a claim).


def test_claim_requires_the_independent_test_red_original_green_final(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    # gate order: self-test red, impl green, IV red-on-original, IV green-on-final
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 1, 0]))

    assert out.claimed is True
    assert out.claimed_basis == "own-test+independent-test"
    assert out.stop_reason == "green" and out.signal == "green"
    assert [v.approved for v in out.iv_verdicts] == [True]
    assert out.independent_test == iv_source()
    assert out.independent_test_path == "tests/test_independent.py"
    assert out.independent_test_node_ids == ["scripted::test"]
    assert out.iv_original_gate is not None and out.iv_original_gate.anomaly == "tests-failed"
    assert out.iv_final_gate is not None and out.iv_final_gate.green is True
    assert "independent_test_verdict" in ledger_kinds()
    # the independent test saw the changed-file source, never the run's own test
    assert seen and seen[0].original == {"pkg/calc.py": "def result():\n    return 0\n"}
    assert seen[0].final == {"pkg/calc.py": impl()["content"]}
    assert seen[0].acs == spec.acs


def test_independent_test_rejection_is_the_next_attempt_failure_context(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl("def result():\n    return 1\n"),
        impl("def result():\n    return 1\n"),
    ]})
    # gate order: self-test red, impl green, IV red-original, IV RED-final (still wrong)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, 1, 1]))

    assert out.claimed is False
    assert out.stop_reason in ("calls", "attempts")   # the loop continued, then stopped
    assert out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert out.independent_test_reason.startswith("independent-test-red-on-final")
    assert "independent-test" in out.exhaustion_reason
    rejected = [a for a in out.attempts if a.claimed_delta.startswith("independent test:")]
    assert rejected and rejected[0].outcome == "fail"
    # the failing IV output became the next implementation's failure context
    impl_calls = model.calls("write_test")
    assert "independent test rejected" in impl_calls[2].artifacts["failure_output"]


def test_vacuous_independent_test_is_rejected_as_not_red(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    # gate order: self-test red, impl green, IV GREEN-original (vacuous)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.claimed is False
    assert out.iv_verdicts[-1].reason == "independent-test-not-red"
    assert out.stop_reason == "calls"


def test_unobserved_independent_test_keeps_claimed_false(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, transport()]))

    assert out.claimed is False
    assert out.iv_verdicts[-1].reason == "independent-test-unobserved"


def test_independent_test_runs_in_a_private_copy_never_the_run_workdir(tmp_path):
    """The independent test is kept out of the run's view: its two gates run in private
    copies (never the workdir), the copies hold the IV test and NEVER the run's own test,
    and nothing the IV writes lands in the run's tree."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen_dirs: list[Path] = []
    seen_files: list[list[str]] = []

    class RecordingGate:
        def __init__(self, codes):
            self._codes = list(codes)
            self.calls = 0

        def __call__(self, workdir) -> ShapedResult:
            workdir = Path(workdir)
            seen_dirs.append(workdir)
            seen_files.append(sorted(p.relative_to(workdir).as_posix()
                                     for p in workdir.rglob("*") if p.is_file()))
            code = self._codes[min(self.calls, len(self._codes) - 1)]
            self.calls += 1
            return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=code,
                                verdict="ok" if code == 0 else "failed", excerpts=[],
                                gate=scripted_gate() if code == 0 else scripted_red_gate())

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=RecordingGate([1, 0, 1, 0]))

    assert out.claimed is True
    # the run's own gate ran in the workdir; the two IV gates ran in private copies
    assert seen_dirs[0] == tmp_path and seen_dirs[1] == tmp_path
    assert seen_dirs[2] != tmp_path and tmp_path not in seen_dirs[2].parents
    assert seen_dirs[3] != tmp_path and tmp_path not in seen_dirs[3].parents
    assert "tests/test_independent.py" in seen_files[2]
    assert "tests/test_leaf_self.py" not in seen_files[2]
    assert not (tmp_path / "tests" / "test_independent.py").exists()


def test_malformed_independent_test_output_keeps_claimed_false(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest):
        seen.append(request)
        raise ValueError("independent test output was not a test file")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=9, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "malformed-output"
    assert out.claimed_basis == "own-test"
    assert len(seen) == 3            # 1 attempt + 2 retries


def test_unaffordable_independent_test_keeps_claimed_false(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    started: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        started.append(request)
        return iv_candidate()

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "calls"
    assert started == []             # not even started
    assert out.claimed_basis == "own-test"


def test_no_iv_producer_claims_on_the_own_test_with_basis_own_test(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.claimed_basis == "own-test"
    assert out.iv_verdicts == []


def test_independent_test_request_never_exposes_a_grader_path_or_the_own_test(tmp_path):
    grader = ("tests/test_chain.py",)
    spec = make_spec(grader=grader)
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                  iv=iv, run_tests=ScriptedTests([1, 0, 1, 0]))

    assert seen
    blob = "\n".join([*seen[0].original.values(), *seen[0].final.values(), *seen[0].acs])
    assert "tests/test_chain.py" not in blob
    assert "test_leaf_self" not in blob          # the run's own test is never shown
    assert "pkg/calc.py" in seen[0].final


def test_evaluate_independent_test_real_gate_approves_red_original_green_final():
    """The real report gate, twice: the same test is red on the pre-run tree and green
    on the final tree, so the verdict approves and records the passed node ids."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    verdict = asyncio.run(evaluate_independent_test(
        iv_candidate(), original, final, leaf_mod._default_run_tests))

    assert verdict.approved is True and verdict.reason == ""
    assert verdict.original_gate is not None and verdict.original_gate.anomaly == "tests-failed"
    assert verdict.final_gate is not None and verdict.final_gate.green is True
    assert any("test_goal" in nid for nid in verdict.node_ids)


def test_evaluate_independent_test_real_gate_rejects_a_vacuous_test():
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    vacuous = IndependentTestCandidate(path="tests/test_independent.py",
                                       content="def test_goal():\n    assert True\n")
    verdict = asyncio.run(evaluate_independent_test(
        vacuous, original, dict(original), leaf_mod._default_run_tests))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-not-red"


def test_evaluate_independent_test_real_gate_rejects_red_on_final():
    """The real gate: the test is red on the original AND still red on the final (the
    fix did not satisfy it), so the verdict rejects with ``independent-test-red-on-final``
    and the loop may continue with that output."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    verdict = asyncio.run(evaluate_independent_test(
        iv_candidate(), original, dict(original), leaf_mod._default_run_tests))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-red-on-final"
    assert verdict.original_gate is not None and verdict.original_gate.anomaly == "tests-failed"
    assert verdict.final_gate is not None and verdict.final_gate.anomaly == "tests-failed"


def test_iv_safe_path_relocates_a_non_test_landing_spot():
    from harness.leaf import _iv_safe_path

    assert _iv_safe_path("tests/test_independent.py") == "tests/test_independent.py"
    assert _iv_safe_path("test_independent.py") == "test_independent.py"
    assert _iv_safe_path("../evil.py") == "tests/test_independent.py"
    assert _iv_safe_path("pkg/helper.py") == "tests/test_independent.py"
    assert _iv_safe_path("") == "tests/test_independent.py"


# ---------------------------------------------- independent test file / repair (round 8)
# The blind measurement found ``independent-test-unobserved`` was a HARNESS defect: the
# model named its test ``tests/verify_pagination.py``, which the staging rule accepts as
# a ``tests/`` path but pytest's collection rule never runs. The harness, not the model,
# now decides the collected file name (recording the relocation + ``tolerance_fired``),
# and a defective verdict (vacuous / uncollected) earns exactly ONE bounded re-ask with
# the verdict as evidence. Both costs are counted on the outcome and in the run record.


def test_iv_relocates_a_non_collectible_tests_path_and_still_approves():
    """The exact live defect: ``tests/verify_pagination.py`` is never collected by
    pytest, so the harness could not observe the test and punished the run with
    ``independent-test-unobserved`` for its own naming rule. The normalized file is
    written at a collectible path, is really collected, and the verdict approves."""
    import harness.leaf as leaf_mod
    from harness.leaf import _iv_safe_path

    assert _iv_safe_path("tests/verify_pagination.py") == "tests/test_independent.py"
    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    candidate = IndependentTestCandidate(
        path="tests/verify_pagination.py",
        content="from pkg.calc import result\n\n\ndef test_goal():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        candidate, original, final, leaf_mod._default_run_tests))

    assert verdict.approved is True
    assert verdict.requested_path == "tests/verify_pagination.py"
    assert verdict.path == "tests/test_independent.py"
    assert verdict.relocated is True
    assert verdict.final_gate is not None and verdict.final_gate.green is True
    # the relocated file was actually COLLECTED (its node id is in the report)
    assert verdict.node_ids and all("tests/test_independent.py" in nid for nid in verdict.node_ids)


def test_iv_relocation_is_recorded_and_never_lands_in_the_run_workdir(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        return iv_candidate(path="tests/verify_pagination.py")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 1, 0]))

    assert out.claimed is True
    assert out.independent_test_path == "tests/test_independent.py"
    assert out.iv_verdicts[-1].requested_path == "tests/verify_pagination.py"
    assert out.iv_verdicts[-1].relocated is True
    assert out.iv_attempts == 1 and out.iv_repairs == 0
    assert any("not collectible -> tests/test_independent.py" in r for r in out.refusals)
    kinds = ledger_kinds()
    assert "independent_test_relocated" in kinds
    assert "tolerance_fired" in kinds
    # the independent test never enters the run's workdir (neither name)
    assert not (tmp_path / "tests" / "test_independent.py").exists()
    assert not (tmp_path / "tests" / "verify_pagination.py").exists()


def test_vacuous_iv_triggers_exactly_one_repair_then_approves(tmp_path):
    """A test that also passes on the pristine source cannot discriminate: it earns ONE
    re-ask carrying the rejected test and verdict as evidence, and can then approve."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        if request.repair_reason:
            return iv_candidate()
        return IndependentTestCandidate(path="tests/test_vacuous.py",
                                        content="def test_goal():\n    assert True\n")

    # self red(1), impl green(0), IV original GREEN(0) -> vacuous, repair original red(1),
    # repair final green(0) -> approved
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 0, 1, 0]))

    assert out.claimed is True
    assert out.claimed_basis == "own-test+independent-test"
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert [v.reason for v in out.iv_verdicts] == ["independent-test-not-red", ""]
    assert [v.approved for v in out.iv_verdicts] == [False, True]
    # both the first and the repaired verdict are recorded
    assert len(out.iv_verdicts) == 2 and out.independent_test == iv_source()
    # the repair carried the rejected test and the verdict as evidence
    assert len(seen) == 2
    assert seen[1].repair_reason == "independent-test-not-red"
    assert seen[1].previous_test == "def test_goal():\n    assert True\n"
    assert seen[1].repair_detail
    assert "independent_test_repair" in ledger_kinds()


def test_uncollected_iv_triggers_one_repair_then_approves(tmp_path):
    """``independent-test-unobserved`` also earns exactly one repair; if the repaired
    test is observable and red-on-original, it can approve."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    # IV original unobserved (transport), repair original red, repair final green
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, transport(), 1, 0]))

    assert out.claimed is True
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert out.iv_verdicts[0].reason == "independent-test-unobserved"
    assert out.iv_verdicts[1].approved is True
    assert seen[1].repair_reason == "independent-test-unobserved"


def test_iv_repair_that_fails_again_keeps_claimed_false(tmp_path):
    """ONE repair only: if the re-asked test is defective again the verdict stands, the
    run stays unclaimed, and the loop continues (here it stops cleanly on the budget)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        return IndependentTestCandidate(path="tests/test_vacuous.py",
                                        content="def test_goal():\n    assert True\n")

    # self red(1), impl green(0), IV original green(0), repair original green(0)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 0, 0]))

    assert out.claimed is False
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert [v.approved for v in out.iv_verdicts] == [False, False]
    assert out.iv_verdicts[-1].reason == "independent-test-not-red"
    assert out.independent_test_reason.startswith("independent-test-not-red")
    assert "independent-test" in out.exhaustion_reason
    assert "independent_test_repair" in ledger_kinds()


def test_iv_red_on_final_is_a_fix_failure_and_is_not_repaired(tmp_path):
    """``independent-test-red-on-final`` means the FIX did not satisfy the test, not that
    the test is defective: it is never repaired and the loop continues with it."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 1, 1]))

    assert out.claimed is False
    assert out.iv_attempts == 1 and out.iv_repairs == 0
    assert out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert len(seen) == 1                       # no repair was requested


def test_run_record_reports_iv_attempts_and_repairs(tmp_path):
    """The cost of the independent-test mechanism is measurable: the persisted run
    record carries ``iv_attempts`` and ``iv_repairs``."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        if request.repair_reason:
            return iv_candidate()
        return IndependentTestCandidate(path="tests/test_vacuous.py",
                                        content="def test_goal():\n    assert True\n")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 0, 1, 0]))
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])
    record = build_record("T-x", "goal", out, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0, iv_enabled=True)

    assert record["iv_attempts"] == 2
    assert record["iv_repairs"] == 1
    assert len(record["iv_verdicts"]) == 2
    json.dumps(record)


# -------------------------------------------------- write-target shape (finding 2)
# A schema-valid envelope whose file_path is an existing directory or under an existing
# file used to raise IsADirectoryError / FileExistsError OUTSIDE the bounded request
# wrapper and crashed the real driver. The shape is a parameter: the self-test is
# normalized; an un-normalizable source write stops honestly with a distinct reason.


@pytest.mark.parametrize("shape", ["pkg", "pkg/", ".", "pkg/calc.py/x.py"])
def test_implementation_with_a_bad_target_shape_stops_honestly(tmp_path, shape):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        write_env(shape, "def result():\n    return 42\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.signal == "honest-failure"
    assert out.stop_reason == "write-shape"
    assert "write_shape_refused" in ledger_kinds()


def test_self_test_with_a_directory_shaped_target_is_normalized(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("pkg/", "def test_goal():\n    assert result() == 42\n"),
        impl(),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.self_test is not None and out.self_test.startswith("tests/")
    assert (tmp_path / out.self_test).read_text().startswith("def test_goal")
    assert out.claimed is True                 # the loop completed; no crash
    assert "self_test_relocated" in ledger_kinds()


def test_driver_iv_defaults_on_and_no_iv_disables_the_check():
    from bench.v2_leaf import build_parser

    assert build_parser().parse_args(["--task", "t"]).iv is True
    assert build_parser().parse_args(["--task", "t", "--iv"]).iv is True
    assert build_parser().parse_args(["--task", "t", "--no-iv"]).iv is False


def test_driver_model_independent_test_maps_the_write_test_envelope():
    """The default independent test reuses the §10 write_test envelope (no new schema),
    runs with a FRESH context, and carries the goal, ACs, and the original/final changed
    source — never the run's own test."""
    from bench.v2_leaf import model_independent_test

    model = FakeModelRunner({"write_test": [iv_env()]})
    request = IndependentTestRequest(
        goal="make result() return 42", acs=["result() returns 42"],
        original={"pkg/calc.py": "def result():\n    return 0\n"},
        final={"pkg/calc.py": "def result():\n    return 42\n"})

    candidate = asyncio.run(model_independent_test(model, request))
    assert candidate.path == "tests/test_independent.py"
    assert candidate.content == iv_source()
    call = model.calls("write_test")[0]
    assert call.fresh is True                       # fresh context
    assert call.artifacts == {}
    assert "ORIGINAL" in call.question and "FINAL" in call.question
    assert "result() returns 42" in call.question


def test_driver_model_independent_test_rejects_an_unusable_envelope():
    """An ``unable`` independent-test envelope is malformed (never a claim): the driver
    raises so the leaf's bounded request stops honestly instead of trusting it."""
    from bench.v2_leaf import model_independent_test

    model = FakeModelRunner({"write_test": [
        {"status": "unable", "comment": "cannot", "unable_reason": "no interpreter"}]})
    request = IndependentTestRequest(goal="g", acs=[], original={}, final={})

    with pytest.raises(ValueError):
        asyncio.run(model_independent_test(model, request))


def test_v2_driver_survives_a_bad_write_target_shape(tmp_path, monkeypatch):
    """Finding 2 through the driver: ``run_once`` returns a record (no crash) when the
    implementation envelope names an existing directory as its target."""
    import harness.leaf as leaf_mod
    from bench import v2_leaf
    from bench.external_score import ExternalScore

    task_dir = tmp_path / "T-shape"
    (task_dir / "repo" / "pkg").mkdir(parents=True)
    (task_dir / "repo" / "pkg" / "calc.py").write_text("def result():\n    return 0\n")
    (task_dir / "request.md").write_text("make result() return 42")

    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        write_env("pkg", "def result():\n    return 42\n"),   # existing directory at the target
    ]})
    monkeypatch.setattr(v2_leaf, "LlamaServerRunner", lambda server: model)
    monkeypatch.setattr(leaf_mod, "_default_run_tests", ScriptedTests([1]))
    monkeypatch.setattr(v2_leaf, "external_score",
                        lambda *a, **k: ExternalScore(passed=False, exit=1))

    record = v2_leaf.run_once(task_dir, tmp_path / "out", "http://server",
                              calls=6, deadline_hours=1.0, use_judge=False,
                              use_iv=False)

    assert record["stop_reason"] == "write-shape"
    assert record["claimed"] is False
    assert record["quadrant"] == "honest-failure"


def test_v2_driver_iv_mode_changes_the_claim_basis(tmp_path, monkeypatch):
    """Ticket 17 round 7 through the driver: with ``--iv`` (the default) a green claim
    carries ``own-test+independent-test`` and the independent test ran; with ``--no-iv``
    the basis is the run's own test alone."""
    import harness.leaf as leaf_mod
    from bench import v2_leaf
    from bench.external_score import ExternalScore

    task_dir = tmp_path / "T-iv"
    (task_dir / "repo" / "pkg").mkdir(parents=True)
    (task_dir / "repo" / "pkg" / "calc.py").write_text("def result():\n    return 0\n")
    (task_dir / "request.md").write_text("make result() return 42")

    monkeypatch.setattr(v2_leaf, "external_score",
                        lambda *a, **k: ExternalScore(passed=True, exit=0))
    approved = IndependentTestVerdict(
        approved=True, path="tests/test_independent.py", content=iv_source(),
        node_ids=("tests/test_independent.py::test_goal",),
        original_gate=scripted_red_gate(), final_gate=scripted_gate())
    monkeypatch.setattr(leaf_mod, "evaluate_independent_test",
                        lambda candidate, original, final, run_tests: approved)

    # The IV call is a third fresh write_test envelope; the run's own gate is scripted.
    model_on = FakeModelRunner({"write_test": [SELF_TEST, impl(), iv_env()]})
    monkeypatch.setattr(leaf_mod, "_default_run_tests", ScriptedTests([1, 0]))
    monkeypatch.setattr(v2_leaf, "LlamaServerRunner", lambda server: model_on)
    rec_on = v2_leaf.run_once(task_dir, tmp_path / "on", "http://s", calls=6,
                              deadline_hours=1.0, use_judge=False, use_iv=True)
    assert rec_on["claimed"] is True
    assert rec_on["claimed_basis"] == "own-test+independent-test"
    assert rec_on["independent_test"] == iv_source()
    assert rec_on["iv_original_gate"]["anomaly"] == "tests-failed"
    assert rec_on["iv_final_gate"]["anomaly"] == ""
    assert model_on.calls("write_test")[-1].fresh is True       # fresh-context IV call

    model_off = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    monkeypatch.setattr(leaf_mod, "_default_run_tests", ScriptedTests([1, 0]))
    monkeypatch.setattr(v2_leaf, "LlamaServerRunner", lambda server: model_off)
    rec_off = v2_leaf.run_once(task_dir, tmp_path / "off", "http://s", calls=6,
                               deadline_hours=1.0, use_judge=False, use_iv=False)
    assert rec_off["claimed"] is True
    assert rec_off["claimed_basis"] == "own-test"
    assert rec_off["iv"] is False
    assert rec_off["iv_verdicts"] == []


# ------------------------------------------ round 5: one owned-path definition


def test_run_written_conftest_is_refused_and_never_reaches_the_gate(tmp_path):
    """Attack 3B reproduced: staging decided "grader-owned" by ``is_test_path`` only, so
    a run-written ``conftest.py`` with a ``pytest_sessionfinish`` hook was accepted and
    made the LEAF's own pytest exit 0 (a manufactured ``claimed=True``). The write is now
    refused as test infrastructure, recorded, and never runs the gate."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    hook = ("import pytest\n\n\ndef pytest_sessionfinish(session, exitstatus):\n"
            "    session.exitstatus = 0\n")
    conftest = write_env("conftest.py", hook, comment="make the gate green")
    model = FakeModelRunner({"write_test": [SELF_TEST, conftest, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert not (tmp_path / "conftest.py").exists()          # refused, never written
    assert any("conftest.py" in r for r in out.refusals)
    assert any("infrastructure" in r for r in out.refusals)
    assert "implement_refused" in ledger_kinds()
    # only the self-test red and the real implementation green drove the gate
    assert out.claimed is True and out.signal == "green"


def test_leaf_refuses_a_module_shadow_source_write(tmp_path):
    """Attack 3A through the leaf: a run may not land a top-level module that shadows an
    interpreter import. The write is refused (recorded) and the escalation continues."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    shadow = write_env("json.py", "import sys\nsys.exit(0)\n", comment="make the grader pass")
    model = FakeModelRunner({"write_test": [SELF_TEST, shadow, impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 0]))

    assert not (tmp_path / "json.py").exists()
    assert any("json.py" in r for r in out.refusals)
    assert any("module-shadow" in r for r in out.refusals)
    assert "implement_refused" in ledger_kinds()


def test_leaf_gate_refuses_to_run_with_a_shadow_file_in_the_tree(tmp_path):
    """The leaf's own gate is isolated two ways: PYTHONSAFEPATH removes the implicit
    cwd prepend, and the gate refuses to run at all when the tree holds an import
    shadow (which the workdir being on PYTHONPATH would otherwise make decisive)."""
    import harness.leaf as leaf_mod

    (tmp_path / "json.py").write_text(
        "import pathlib, sys\npathlib.Path('shadowed.txt').write_text('x')\nsys.exit(0)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_red.py").write_text("def test_red():\n    assert False\n")

    res = asyncio.run(leaf_mod._default_run_tests(tmp_path))

    assert res.exit == 1                                   # never a forged 0
    assert not (tmp_path / "shadowed.txt").exists()        # the shadow never executed
    assert res.gate is not None and res.gate.anomaly == "shadow-file-present"


def test_leaf_gate_lets_a_legit_test_import_its_package(tmp_path):
    """Verification round-6 finding R3: with the import root declared explicitly, a
    run-written test under tests/ can import the package it tests (it could not while
    PYTHONSAFEPATH was the only knob)."""
    import harness.leaf as leaf_mod

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 42\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "from pkg.calc import result\n\ndef test_ok():\n    assert result() == 42\n")

    res = asyncio.run(leaf_mod._default_run_tests(tmp_path))

    assert res.exit == 0 and res.gate is not None and res.gate.green


# ------------------------------------------------- round 5: run-record audit


def test_run_record_records_refusals_and_the_isolation_env():
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=2, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="calls",
        layers_used=[], stop_reason="calls",
        refusals=["json.py: a module-shadow path (would shadow an interpreter import)"])
    score = ExternalScore(passed=False, exit=1, shadowed=["json.py"],
                          isolation={"PYTHONSAFEPATH": "1",
                                     "PYTEST_ADDOPTS": "-p no:cacheprovider"})

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)

    assert record["refusals"] == outcome.refusals
    assert record["grader_shadowed"] == ["json.py"]
    assert record["isolation"]["env"]["PYTHONSAFEPATH"] == "1"
    assert record["isolation"]["grader_env"]["PYTHONSAFEPATH"] == "1"
    assert "no:cacheprovider" in record["isolation"]["pytest_args"]
    json.dumps(record)


# --------------------------------------- round 5: attack 3A end to end (driver)


def test_end_to_end_shadow_module_wrong_fix_is_not_a_true_success(tmp_path, monkeypatch):
    """The driver case an adversarial pass demonstrated: a wrong fix whose only other
    change is a run-authored ``json.py`` must not reach the true-success quadrant. The
    leaf refuses the shadow write and the external grader would refuse it too, so the
    real source bug stands and the run reports honestly."""
    import harness.leaf as leaf_mod
    from bench import v2_leaf

    task_dir = (Path(__file__).resolve().parents[2] / "bench" / "corpus"
                / "T-31-parameter-threading")
    shadow = write_env("json.py", "import sys\nsys.exit(0)\n", comment="make the grader pass")
    wrong = write_env("api/transport.py", "def send(url, payload):\n    return \"ok\"\n",
                      comment="change the transport")
    model = FakeModelRunner({"write_test": [SELF_TEST, shadow, *([wrong] * 5)]})
    monkeypatch.setattr(v2_leaf, "LlamaServerRunner", lambda server: model)
    monkeypatch.setattr(leaf_mod, "_default_run_tests", ScriptedTests([1]))

    record = v2_leaf.run_once(task_dir, tmp_path / "out", "http://server",
                              calls=6, deadline_hours=1.0, use_judge=False,
                              use_iv=False)

    assert record["claimed"] is False
    assert record["actual"] is False
    assert record["quadrant"] != "true-success"
    assert any("json.py" in r for r in record["refusals"])
    assert not (tmp_path / "out" / "work" / "json.py").exists()


# ---------------------------- round 6: the gate is a machine-readable pytest report (F1)
# The adversarial pass forged a green with run-authored code: ``import atexit, os`` plus
# ``atexit.register(lambda: os._exit(0))`` made BOTH pytest runs exit 0 with no test
# summary, and the run reached claimed=True AND actual=True with the bug untouched. The
# exit status is no longer evidence: the leaf's own gate requires a JUnit report with the
# expected test files AND a per-run random canary, so a forged green is RED.

T31 = Path(__file__).resolve().parents[2] / "bench" / "corpus" / "T-31-parameter-threading"


def _forged_workdir(tmp_path: Path, *, kill_at_import: bool) -> Path:
    """A workdir whose own test imports a source that kills pytest with exit 0."""
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "__init__.py").write_text("")
    guard = ("import os\nos._exit(0)\n" if kill_at_import else
             "import atexit, os\natexit.register(lambda: os._exit(0))\n")
    (tmp_path / "pkg" / "calc.py").write_text(guard + "\n\ndef result():\n    return 42\n")
    (tmp_path / "test_leaf_self.py").write_text(
        "from pkg import calc\n\n\ndef test_goal():\n    assert calc.result() == 41\n")
    return tmp_path


def test_leaf_gate_rejects_a_forged_exit_zero_from_run_code(tmp_path):
    """The atexit forgery through the REAL gate: the process lies (exit 0) while the
    run's own test fails. The report catches the failure, so the gate is RED."""
    import harness.leaf as leaf_mod

    work = _forged_workdir(tmp_path / "atexit", kill_at_import=False)
    res = asyncio.run(leaf_mod._default_run_tests(work))

    assert res.gate.process_exit == 0                  # the forgery worked on the process
    assert res.exit != 0                               # ... the report overrode it
    assert leaf_mod._is_green(res) is False
    assert res.gate.green is False
    assert res.gate.observed is True                   # a real report: a real red
    assert res.gate.anomaly == "tests-failed"
    assert not (work / "tests").joinpath("report.xml").exists()


def test_leaf_gate_is_unobserved_when_run_code_destroys_the_report(tmp_path):
    """``os._exit(0)`` at import kills pytest before the report is written: no
    machine-readable evidence, so nothing greens and nothing is a red target."""
    import harness.leaf as leaf_mod

    work = _forged_workdir(tmp_path / "import", kill_at_import=True)
    res = asyncio.run(leaf_mod._default_run_tests(work))

    assert res.exit != 0
    assert leaf_mod._is_green(res) is False
    assert res.gate.anomaly == "report-missing"
    assert res.gate.observed is False
    assert res.gate.structural_anomaly is True


def test_leaf_never_claims_when_run_code_forges_the_gate(tmp_path):
    """F1 end to end with the real gate: the run's ``os._exit(0)`` source kills the gate
    process, the leaf records ``gate_report_anomaly`` and never claims."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    evil = "import os\nos._exit(0)\n\n\ndef result():\n    return 42\n"
    model = FakeModelRunner({"write_test": [
        write_env("test_leaf_self.py",
                  "from pkg import calc\n\n\ndef test_goal():\n    assert calc.result() == 42\n"),
        impl(evil, comment="fix the source"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE))

    assert out.claimed is False
    assert out.signal != "green"
    assert out.gate_anomalies and out.gate_anomalies[0].startswith("report-missing")
    assert "gate_report_anomaly" in ledger_kinds()
    assert all(a.outcome == "fail" for a in out.attempts)


def test_an_exit_zero_without_a_report_is_not_green():
    """The exit status alone must never green a gate, even at the seam level."""
    import harness.leaf as leaf_mod

    bare = ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=0, verdict="ok",
                        excerpts=[])
    assert leaf_mod._is_green(bare) is False


# --------------------------- round 6: the corpus UNTOUCHED set is grader-owned (F2)
# The grader restores owned_paths(rel) OR the corpus task's UNTOUCHED list, but the leaf
# guarded only owned_paths, so a run could green by writing a frozen source file the
# grader then restored — a false success.

def test_t31_untouched_files_are_grader_paths_and_the_write_is_refused(tmp_path):
    from bench.v2_leaf import build_spec, load_task

    spec = build_spec(load_task(T31))
    assert "api/__init__.py" in spec.grader_paths           # the UNTOUCHED set (F2)
    assert "README.md" in spec.grader_paths
    assert "tests/test_chain.py" in spec.grader_paths       # ... plus the staged-owned paths

    stage(tmp_path, spec.files)
    frozen = (tmp_path / "api" / "__init__.py").read_text()
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        write_env("api/__init__.py", "# rewritten by the run\n", comment="touch a frozen file"),
        impl(path="api/transport.py", content="def send(url, payload, timeout=1.0):\n    return 1\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert (tmp_path / "api" / "__init__.py").read_text() == frozen   # never written
    assert any("api/__init__.py" in r and "grader-owned" in r for r in out.refusals)
    assert "implement_refused" in ledger_kinds()
    assert out.claimed is True                     # the real source fix still greens


# ------------------------------- round 6: two more crash shapes become honest refusals (F3)
# Schema-valid file_path values crashed the real driver: an embedded NUL byte (ValueError
# from write_text / Path.is_dir) and an over-long file name (OSError ENAMETOOLONG). Both
# are now the honest write-shape refusal path.

NUL_PATH = "pkg/calc\x00.py"
LONG_PATH = "pkg/" + "a" * 300 + ".py"


@pytest.mark.parametrize("path", [NUL_PATH, LONG_PATH])
def test_implementation_write_with_an_unusable_name_stops_write_shape(tmp_path, path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, write_env(path, "def result():\n    return 42\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.signal == "honest-failure"
    assert out.stop_reason == "write-shape"
    assert "write_shape_refused" in ledger_kinds()
    assert any("unwritable path" in r for r in out.refusals)


@pytest.mark.parametrize("path", ["tests/test_\x00self.py", "tests/" + "a" * 300 + ".py"])
def test_self_test_with_an_unusable_name_stops_write_shape(tmp_path, path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env(path, "def test_goal():\n    assert result() == 42\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.stop_reason == "write-shape"
    assert out.self_test is None
    assert "write_shape_refused" in ledger_kinds()


def test_write_converts_filesystem_refusals_instead_of_crashing(tmp_path):
    """The second half of F3: ``_write`` never leaks a ValueError/OSError."""
    from harness.leaf import WriteShapeRefused, _write

    with pytest.raises(WriteShapeRefused) as nul:
        _write(tmp_path, NUL_PATH, "x = 1\n")
    assert nul.value.path == NUL_PATH
    assert "unwritable path" in nul.value.detail
    with pytest.raises(WriteShapeRefused):
        _write(tmp_path, LONG_PATH, "x = 1\n")


# ------------------------------------------- round 6: sweep flags / run-record evidence

def test_sweep_exposes_and_forwards_the_judge_and_iv_flags(tmp_path, monkeypatch):
    """An A/B measurement must run unattended: the sweep exposes --judge/--no-judge and
    --iv/--no-iv and forwards both to the driver."""
    from bench import v2_sweep

    parser = v2_sweep.build_parser()
    assert parser.parse_args([]).judge is True and parser.parse_args([]).iv is True
    off = parser.parse_args(["--no-judge", "--no-iv"])
    assert off.judge is False and off.iv is False

    corpus = tmp_path / "corpus" / "T-99-pinned"
    (corpus / "repo").mkdir(parents=True)
    (tmp_path / "anchor").mkdir()
    monkeypatch.setattr(v2_sweep, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(v2_sweep, "ANCHOR", tmp_path / "anchor")
    monkeypatch.setattr(v2_sweep, "ROOT", tmp_path)
    seen: list[dict] = []

    def fake_run_once(task_dir, out_dir, server, calls, deadline_hours, **kw):
        seen.append(kw)
        return {"task": task_dir.name, "claimed": False, "actual": False, "signal": "x",
                "quadrant": "honest-failure", "stop_reason": "calls", "calls": 0,
                "run_wall_s": 0.1}

    monkeypatch.setattr(v2_sweep, "run_once", fake_run_once)
    monkeypatch.setattr("sys.argv", ["v2_sweep", "--tasks", "all"])
    assert v2_sweep.main() == 0
    assert seen == [{"use_judge": True, "use_iv": True}]

    seen.clear()
    monkeypatch.setattr("sys.argv", ["v2_sweep", "--tasks", "all", "--no-judge", "--no-iv"])
    assert v2_sweep.main() == 0
    assert seen == [{"use_judge": False, "use_iv": False}]


def test_run_record_records_the_gate_report_evidence():
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record
    from harness.gate_report import GateReport

    gate = GateReport(report_path="/tmp/private/report.xml", process_exit=0, canary="tok",
                      expected_files=("tests/test_chain.py",), n_tests=5, n_failed=4,
                      n_errors=0, passed_ids=("tests/test_chain.py::test_ok",),
                      failed_ids=("tests/test_chain.py::test_bad",), missing=(),
                      observed=True, anomaly="tests-failed", detail="4 failure(s)")
    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=2, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="calls",
        layers_used=[], stop_reason="calls",
        gate_anomalies=["report-missing: no machine-readable pytest report"])
    score = ExternalScore(passed=False, exit=0, notes=[], work_root="", applied=[],
                          skipped=[], report_gate=gate, suspected_contaminated_grade=True)

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)

    assert record["gate_anomalies"] == outcome.gate_anomalies
    assert record["grader_report_gate"]["anomaly"] == "tests-failed"
    assert record["grader_report_gate"]["expected_files"] == ("tests/test_chain.py",)
    assert record["grader_suspected_contaminated_grade"] is True
    assert record["isolation"]["report_dir"].startswith("private mkdtemp")
    json.dumps(record)
