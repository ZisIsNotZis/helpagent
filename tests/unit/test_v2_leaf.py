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

import pytest

from harness.attempts import Attempt
from harness.budget import Budget
from harness.exec import ShapedResult
from harness.fake_model import FakeModelRunner
from harness.leaf import (
    LADDER,
    Escalation,
    JudgeRequest,
    LeafOutcome,
    LeafSpec,
    escalate,
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


def transport() -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=None,
                        verdict="transport_error", excerpts=["timed out after 120s"])


def policy_blocked() -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=None,
                        verdict="policy_blocked", policy_blocked=True,
                        excerpts=["command is not in the exec allowlist"])


class ScriptedTests:
    """A deterministic ``run_tests`` seam: one result per call, last repeats.

    An item may be an exit code or a full :class:`ShapedResult` (so transport-error
    and policy-blocked shapes are scriptable).
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
                            verdict="ok" if code == 0 else "failed", excerpts=list(excerpts))


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
                        Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test is None
    assert not (tmp_path / "tests/test_chain.py").exists()
    assert out.claimed is False
    assert out.stop_reason == "self-test"
    for record in model.calls("write_test"):
        assert "tests/test_chain.py" not in record.prompt


def test_self_test_may_not_overwrite_an_existing_path(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("pkg/calc.py", "def result():\n    return 99\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test is None
    assert (tmp_path / "pkg/calc.py").read_text() == spec.files["pkg/calc.py"]
    assert "self_test_refused" in ledger_kinds()


def test_non_test_self_test_path_is_refused(tmp_path):
    """A self-test must be a test path (harness.staging.is_test_path); a plain source
    path is refused even when it does not exist yet."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        write_env("pkg/helper.py", "x = 1\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.self_test is None
    assert not (tmp_path / "pkg/helper.py").exists()
    assert out.stop_reason == "self-test"
    assert "self_test_refused" in ledger_kinds()


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

    def judge(request: JudgeRequest) -> str:
        seen.append(request)
        return "tests"

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
    assert out.claimed is True and out.signal == "green-after-test-rewrite"
    assert out.stop_reason == "green"


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
                        judge=lambda request: "tests", run_tests=ScriptedTests([1, 0]))

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
                        judge=lambda request: "tests", run_tests=ScriptedTests([1] * 6))

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

    def judge(request: JudgeRequest) -> str:
        judge_calls.append(request)
        return "tests"

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
        judge=lambda request: "tests",
    )

    assert out.claimed is False
    assert out.stop_reason == "no-red-target"
    assert out.test_rewrites == 1
    assert not (tmp_path / "tests" / "test_leaf_self.py").exists()
