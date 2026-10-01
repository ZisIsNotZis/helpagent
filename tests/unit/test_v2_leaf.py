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
    VERIFICATION_TIERS,
    DeclaredTestCase,
    Escalation,
    IndependentTestCandidate,
    IndependentTestRequest,
    IndependentTestVerdict,
    JudgeRequest,
    JudgeVerdict,
    LeafOutcome,
    LeafSpec,
    ReviewRequest,
    ReviewVerdict,
    VerificationRecord,
    _criterion_unresolved,
    _declared_test_case_problems,
    _requirement_coverage,
    apply_judge_filter,
    apply_review_filter,
    escalate,
    evaluate_independent_test,
    run_leaf,
    verification_reason_problem,
)
from harness.runner import SchemaViolation, ledger_entries, reset_ledger_for_tests

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
    red: pytest produced a report that says the test failed).

    The failing node name carries ``ac1`` so the round-11 node map can derive an explicit
    node id from this first full-file report for the single-criterion ``make_spec``
    fixtures; production reports carry the real candidate's node names."""
    return GateReport(report_path="(scripted)", process_exit=1, canary="scripted",
                      expected_files=(), n_tests=1, n_failed=1, n_errors=0,
                      passed_ids=(), failed_ids=("scripted::test_ac1",), missing=(),
                      observed=True, anomaly="tests-failed", detail="1 failure(s)")


def iv_candidate(path: str = "tests/test_independent.py",
                 content: str = "from pkg.calc import result\n\n\ndef test_ac1_goal():\n    assert result() == 42\n"):
    """A deterministic independent-test candidate for mechanics tests.

    The function name carries the criterion index (``test_ac1_``) so the round-11 node
    map derives an AC1 node id for it and it discriminates for the single-criterion
    ``make_spec`` fixtures."""
    return IndependentTestCandidate(path=path, content=content)


def iv_source() -> str:
    return "from pkg.calc import result\n\n\ndef test_ac1_goal():\n    assert result() == 42\n"


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
    writer; the real discrimination gate is pinned by the tests at the end of this file.
    """
    return GateReport(report_path="(scripted)", process_exit=0, canary="scripted",
                      expected_files=(), n_tests=1, n_failed=0, n_errors=0,
                      passed_ids=("scripted::test_ac1",), failed_ids=(), missing=(),
                      observed=True)


def _gate_report(iv_path: str, passed=(), failed=(), *, green=True) -> GateReport:
    """A scripted report whose node ids all belong to the independent test file."""
    return GateReport(report_path="(scripted)", process_exit=0 if green else 1,
                      canary="scripted", expected_files=(),
                      n_tests=len(passed) + len(failed), n_failed=len(failed), n_errors=0,
                      passed_ids=tuple(passed), failed_ids=tuple(failed), missing=(),
                      observed=True, anomaly="" if green else "tests-failed",
                      detail="" if green else "1 failure(s)")


def _iv_file_in(workdir: Path) -> str:
    """The independent test file in a private ISOLATION copy (the only non-canary test)."""
    from harness.staging import is_test_path

    for path in sorted(Path(workdir).rglob("*.py")):
        rel = path.relative_to(workdir).as_posix()
        if is_test_path(rel) and not path.name.startswith("test_gate_canary_"):
            return rel
    return "tests/test_independent.py"


def _retag(node_id: str, iv_path: str) -> str:
    """Rewrite a scripted node id's file part to the independent test's real path."""
    suffix = node_id.split("::", 1)[1] if "::" in node_id else node_id
    return f"{iv_path}::{suffix}"


class ScriptedTests:
    """A deterministic ``run_tests`` seam: one result per call, last repeats.

    An item may be an exit code or a full :class:`ShapedResult` (so transport-error
    and policy-blocked shapes are scriptable). An exit code of 0 carries a green
    :func:`scripted_gate` report and any non-zero code carries an observed RED
    :func:`scripted_red_gate` (ticket 17 F1) — the loop then sees an ``observed`` red
    exactly as it does for a real failing pytest run, and so does the independent
    test's red-on-original gate.

    Round 11 adds the per-criterion EXPLICIT node-id calls (``node_ids`` kwarg). A
    node-id call models pytest running exactly those node ids: an integer item
    (green/red at file level) mirrors to the requested node ids, and a
    :class:`ShapedResult` item keeps only the requested nodes it actually reports (so a
    report that names only AC1 collects nothing for AC2 and is ``incomplete-coverage``).
    This keeps the loop mechanics sequences unchanged while the real-gate tests pin the
    discrimination semantics.
    """

    def __init__(self, results, excerpts=None):
        self._results = list(results)
        self._excerpts = excerpts or {}
        self.calls = 0
        self.selections: list[tuple[str, ...] | None] = []
        self._index = 0
        self._last: object | None = None

    def __call__(self, workdir, node_ids=None) -> ShapedResult:
        self.calls += 1
        self.selections.append(tuple(node_ids) if node_ids is not None else None)
        if node_ids is not None:
            return self._selected(workdir, node_ids)
        item = (self._results[self._index] if self._index < len(self._results)
                else self._results[-1])
        self._index += 1
        self._last = item
        return self._as_result(item, workdir)

    def _as_result(self, item: object, workdir: Path | None = None) -> ShapedResult:
        if isinstance(item, ShapedResult):
            return item
        excerpts = [] if item == 0 else self._excerpts.get(
            item, ["FAILED tests/test_leaf_self.py::test_goal", "E AssertionError: still red"])
        gate = scripted_gate() if item == 0 else scripted_red_gate()
        if workdir is not None:
            # production reports name the test file that actually ran; keep the fake
            # faithful so the harness's independent-test scoping sees its own nodes
            iv = _iv_file_in(workdir)
            gate = dataclasses.replace(
                gate, passed_ids=tuple(_retag(nid, iv) for nid in gate.passed_ids),
                failed_ids=tuple(_retag(nid, iv) for nid in gate.failed_ids))
        return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=item,
                            verdict="ok" if item == 0 else "failed", excerpts=list(excerpts),
                            gate=gate)

    def _selected(self, workdir: Path, node_ids) -> ShapedResult:
        iv = _iv_file_in(workdir)
        base = self._last
        if isinstance(base, int):
            green = base == 0
            nodes = tuple(node_ids)
            return ShapedResult(
                command=["python3", "-m", "pytest", "-q"], exit=base,
                verdict="ok" if green else "failed",
                excerpts=[] if green else [f"FAILED {n}" for n in nodes],
                gate=_gate_report(iv, passed=nodes if green else (),
                                  failed=() if green else nodes, green=green))
        gate = getattr(base, "gate", None)
        if gate is None:
            return self._as_result(base, workdir)
        requested = set(node_ids)
        passed = tuple(nid for nid in gate.passed_ids if nid in requested)
        failed = tuple(nid for nid in gate.failed_ids if nid in requested)
        return dataclasses.replace(base, gate=_gate_report(
            iv, passed=passed, failed=failed, green=gate.green))


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
# Ticket 19 round 2, F5: a model failure is DATA, not a crash AND not a stop. Every
# envelope request is retried a bounded number of times; a persistent malformed output
# consumes its calls, is recorded, and the node CONTINUES (bounded by the call budget /
# attempt cap / ladder stops). The old ``malformed-output`` stop was superseded.


def test_malformed_self_test_envelope_is_retried_then_the_node_continues(tmp_path):
    """F5: a persistently malformed self-test no longer ends the node — it is retried
    (each try spends a call) until the CALL BUDGET is the stop."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [schema_violation()] * 3})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.stop_reason == "calls"                 # the budget, not malformed-output
    assert len(model.calls("write_test")) == 9         # it consumed the budget, never crashed
    assert "self-test" in out.malformed_steps
    assert "envelope_malformed" in ledger_kinds()
    assert "envelope_malformed_step" in ledger_kinds()
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

    assert out.stop_reason == "calls"                 # F5: no crash and no malformed stop
    assert out.claimed is False
    assert len(model.calls("write_test")) == 9


def test_malformed_implement_envelope_does_not_end_the_node(tmp_path):
    """F5: a malformed implement envelope is recorded and the loop continues; the red
    target is kept and the node stops only on the call budget."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, *[schema_violation()] * 3]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=9, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1]))

    assert out.self_test == "tests/test_leaf_self.py"          # the red target is kept
    assert out.claimed is False
    assert out.stop_reason == "calls"                          # not malformed-output
    assert "implement" in out.malformed_steps


def test_malformed_judge_output_is_recorded_and_the_node_continues(tmp_path):
    """F5 + round-3 FIX 2: a malformed judge is retried a BOUNDED number of times (one
    retry, not the generic envelope budget), recorded, and the run keeps going with the
    deterministic ``attribution unavailable`` fallback instead of stopping or looping."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked()]})
    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        raise ValueError("judge output was not a verdict")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=9, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1] * 4))

    assert out.stop_reason == "calls"
    assert out.claimed is False
    assert len(seen) == 2                       # 1 attempt + 1 bounded retry (FIX 2)
    assert out.judge_unavailable == 1           # recorded deterministic fallback
    assert "judge" in out.malformed_steps
    assert "judge_unavailable" in ledger_kinds()


def test_plain_text_judge_verdict_is_parsed_by_the_fallback(tmp_path):
    """FIX 2: a plain-text judge answer is parsed deterministically for its attribution
    word, so prose is not silently discarded as implementation-only."""
    from harness.leaf import _as_verdict

    assert _as_verdict("the failing test asserts the wrong value").test_wrong is True
    assert _as_verdict("the source code has an off-by-one").implementation_wrong is True
    assert _as_verdict("the specification is ambiguous").spec_wrong is True
    assert _as_verdict("the sandbox harness is broken").environment_broken is True
    # no attribution word stays raw and is coerced to implementation by the filter
    assert _as_verdict("banana").attribution == "banana"


def test_malformed_test_rewrite_is_recorded_and_the_node_continues(tmp_path):
    """F5: a malformed test rewrite is recorded; the own test is left intact and the node
    keeps implementing rather than stopping."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), *[schema_violation()] * 3]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1] * 6))

    assert out.claimed is False
    assert out.stop_reason == "calls"                          # not malformed-output
    assert out.test_rewrites == 0
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]
    assert "test-rewrite" in out.malformed_steps


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


def test_driver_model_judge_falls_back_to_the_simpler_failure_judge_shape():
    """FIX 2: a malformed §16 debug_judge is retried ONCE in the simpler §12
    failure_judge shape, so a systematic format slip still yields an attribution instead
    of a wasted malformed step."""
    from bench.v2_leaf import model_judge

    model = FakeModelRunner({
        "debug_judge": [schema_violation()],
        "failure_judge": [{
            "status": "ok", "comment": "judged",
            "problems": [{"side": "test",
                          "description": "test_goal asserts the wrong value",
                          "evidence": "tests/test_x.py::test_goal", "confidence": "high"}],
        }],
    })
    request = JudgeRequest(goal="g", failure="f", test_path="tests/test_x.py",
                           test_content="def test_goal():\n    assert True\n", files={},
                           acs=["AC-1"])

    verdict = asyncio.run(model_judge(model, request))
    assert verdict.test_wrong is True and "wrong value" in verdict.reason
    assert model.calls("debug_judge") and model.calls("failure_judge")


def test_driver_model_judge_fallback_that_also_fails_reraises():
    """FIX 2: when BOTH shapes stay malformed the driver re-raises, so the leaf records
    its deterministic fallback rather than the driver looping."""
    from bench.v2_leaf import model_judge

    model = FakeModelRunner({"debug_judge": [schema_violation()],
                             "failure_judge": [schema_violation()]})
    request = JudgeRequest(goal="g", failure="f", test_path="tests/test_x.py",
                           test_content="def test_goal():\n    assert True\n", files={},
                           acs=["AC-1"])
    with pytest.raises(SchemaViolation):
        asyncio.run(model_judge(model, request))


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
    assert out.independent_test_node_ids == ["tests/test_independent.py::test_ac1"]
    assert out.iv_original_gate is not None and out.iv_original_gate.anomaly == "tests-failed"
    assert out.iv_final_gate is not None and out.iv_final_gate.green is True
    assert "independent_test_verdict" in ledger_kinds()
    # the independent test saw the changed-file source, never the run's own test
    assert seen and seen[0].original == {"pkg/calc.py": "def result():\n    return 0\n"}
    assert seen[0].final == {"pkg/calc.py": impl()["content"]}
    assert seen[0].acs == spec.acs


def test_independent_test_rejection_is_recorded_but_no_longer_vetoes(tmp_path):
    """Ticket 19 C: the independent test is an EXTRA LABEL, never the veto. A red-on-final
    independent test is recorded on the outcome, yet the run's own discriminating test
    still carries the claim (``claimed_basis="own-test"``); the loop no longer burns
    attempts rejecting correct work."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl(),
    ]})
    # gate order: self-test red, impl green, IV red-original, IV RED-final (still wrong)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, 1, 1]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.claimed_basis == "own-test"
    assert out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert out.independent_test_reason.startswith("independent-test-red-on-final")


def test_vacuous_independent_test_is_rejected_as_not_red(tmp_path):
    """Ticket 19 C: a vacuous independent test is recorded with its reason, but the run's
    own discriminating test still carries the claim."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    # gate order: self-test red, impl green, IV GREEN-original (vacuous)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.claimed is True and out.claimed_basis == "own-test"
    assert out.iv_verdicts[-1].reason == "independent-test-not-red"


def test_unobserved_independent_test_is_a_label_not_a_veto(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, transport()]))

    assert out.claimed is True and out.claimed_basis == "own-test"
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
            self._inner = ScriptedTests(codes)

        def __call__(self, workdir, node_ids=None) -> ShapedResult:
            workdir = Path(workdir)
            seen_dirs.append(workdir)
            seen_files.append(sorted(p.relative_to(workdir).as_posix()
                                     for p in workdir.rglob("*") if p.is_file()))
            return self._inner(workdir, node_ids=node_ids)

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


def test_malformed_independent_test_output_is_recorded_as_a_label(tmp_path):
    """Ticket 19 C: an independent test that cannot be produced is recorded, but it does
    not stand between the run and a claim authorised by its own discriminating test."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest):
        seen.append(request)
        raise ValueError("independent test output was not a test file")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=9, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.claimed_basis == "own-test"
    assert out.iv_verdicts == []
    assert len(seen) == 3            # 1 attempt + 2 retries


def test_unaffordable_independent_test_leaves_the_own_test_basis(tmp_path):
    """Ticket 19 C: when the independent label cannot be afforded, the own-test claim
    still stands (the label was never the gate)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    started: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        started.append(request)
        return iv_candidate()

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.claimed_basis == "own-test"
    assert started == []             # not even started


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
    """The real report gate: the whole file is red on the pre-run tree and green on the
    final tree, and its explicit AC1 node id discriminates, so the verdict approves and
    records the independent test's passed node ids."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    verdict = asyncio.run(evaluate_independent_test(
        iv_candidate(), original, final, leaf_mod._default_run_tests, criteria_count=1))

    assert verdict.approved is True and verdict.reason == ""
    assert verdict.original_gate is not None and verdict.original_gate.anomaly == "tests-failed"
    assert verdict.final_gate is not None and verdict.final_gate.green is True
    assert any("test_ac1_goal" in nid for nid in verdict.node_ids)
    assert verdict.criteria_count == 1
    assert verdict.covered_indices == (1,) and verdict.uncovered_indices == ()


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
        content="from pkg.calc import result\n\n\ndef test_ac1_goal():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        candidate, original, final, leaf_mod._default_run_tests, criteria_count=1))

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


def test_iv_repair_that_fails_again_is_recorded_before_the_claim(tmp_path):
    """ONE repair only: if the re-asked test is defective again the verdict stands — and
    ticket 19 C records it as a label without blocking the own-test claim."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        return IndependentTestCandidate(path="tests/test_vacuous.py",
                                        content="def test_goal():\n    assert True\n")

    # self red(1), impl green(0), IV original green(0), repair original green(0)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 0, 0]))

    assert out.claimed is True and out.claimed_basis == "own-test"
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert [v.approved for v in out.iv_verdicts] == [False, False]
    assert out.iv_verdicts[-1].reason == "independent-test-not-red"
    assert out.independent_test_reason.startswith("independent-test-not-red")
    assert "independent_test_repair" in ledger_kinds()


def test_iv_red_on_final_is_a_fix_failure_and_is_not_repaired(tmp_path):
    """``independent-test-red-on-final`` means the FIX did not satisfy the test, not that
    the test is defective: it is never repaired. Ticket 19 C records it as a label."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([1, 0, 1, 1]))

    assert out.claimed is True and out.claimed_basis == "own-test"
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


# -------------------- acceptance-criteria discrimination (ticket 17 round 10)
# Round 9 made coverage a NAME check, and the adversarial pass proved that only proved
# the criterion was NAMED: a real test plus ``test_ac2_placeholder``/``test_ac3_placeholder``
# (each asserting True), one function carrying all indices, or a parametrize ids=[...]
# all approved while the criterion was never exercised. The rule is now PER-CRITERION
# DISCRIMINATION: for every index 1..N the SAME EXPLICIT node ids runs on the
# original and final tree, and must collect an independent-test node, FAIL on the
# original (a placeholder is green there and is rejected) and PASS on the final. A
# green-on-original set is ``independent-test-not-discriminating``, one with no node is
# ``independent-test-incomplete-coverage``, and one node mapped to several criteria is
# ``independent-test-shared-coverage``; all are repairable once with the offending
# indices, and the name convention is only the hint that makes the node map work.


def _green_gate(*node_names: str) -> GateReport:
    """A scripted GREEN report whose passed node ids are exactly ``node_names``."""
    return GateReport(report_path="(scripted)", process_exit=0, canary="scripted",
                      expected_files=(), n_tests=len(node_names), n_failed=0, n_errors=0,
                      passed_ids=tuple(node_names), failed_ids=(), missing=(), observed=True)


def _green_result(*node_names: str) -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=0,
                        verdict="ok", excerpts=[], gate=_green_gate(*node_names))


def _red_gate(*node_names: str) -> GateReport:
    """A scripted observed RED report whose failed node ids are exactly ``node_names``."""
    return GateReport(report_path="(scripted)", process_exit=1, canary="scripted",
                      expected_files=(), n_tests=len(node_names), n_failed=len(node_names),
                      n_errors=0, passed_ids=(), failed_ids=tuple(node_names), missing=(),
                      observed=True, anomaly="tests-failed",
                      detail=f"{len(node_names)} failure(s)")


def _red_result(*node_names: str) -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=1,
                        verdict="failed", excerpts=[f"FAILED {n}" for n in node_names],
                        gate=_red_gate(*node_names))


def _two_acs_spec() -> LeafSpec:
    return dataclasses.replace(make_spec(),
                               acs=["result() returns 42", "result() is stable"])


def test_criterion_node_map_is_boundary_aware_and_scoped():
    """Round 11: the index -> node-id map comes from the first full-file report with a
    boundary-aware node-NAME match (``ac1`` never matches ``ac12``/``ac10``) scoped to
    the independent test file; a node used for several criteria is detected as shared;
    every count is scoped to the file, and the verdict reason follows the documented
    priority (a structural shared-coverage defect wins)."""
    from harness.leaf import (
        CriterionEvidence,
        _classify_criteria,
        _criterion_evidence,
        _criterion_node_map,
        _iv_scoped_ids,
        _node_criterion_indices,
        _shared_node_ids,
    )

    iv = "tests/test_independent.py"
    canary = "tests/test_gate_canary_deadbeef.py::test_gate_canary_deadbeef"
    # boundary-aware: ac12/ac10 never match criterion 1, and another file never counts
    assert _node_criterion_indices(f"{iv}::test_ac1_ok", iv) == (1,)
    assert _node_criterion_indices(f"{iv}::test_ac12_thing", iv) == (12,)
    assert _node_criterion_indices("tests/other.py::test_ac1_x", iv) == ()
    assert _node_criterion_indices(f"{iv}::test_ac1_ac2_ac3_combined", iv) == (1, 2, 3)

    seed = _gate_report(iv, passed=(f"{iv}::test_ac1_ok", canary),
                        failed=(f"{iv}::test_ac12_thing", f"{iv}::test_ac2_ok"),
                        green=False)
    assert _criterion_node_map(seed, iv, 2) == {
        1: (f"{iv}::test_ac1_ok",), 2: (f"{iv}::test_ac2_ok",)}
    assert _iv_scoped_ids(seed, iv) == ((f"{iv}::test_ac1_ok",),
                                        (f"{iv}::test_ac12_thing", f"{iv}::test_ac2_ok"))

    # one node selected for two criteria is the shared-coverage defect
    shared_seed = _gate_report(iv, failed=(f"{iv}::test_ac1_ac2_goal",), green=False)
    mapping = _criterion_node_map(shared_seed, iv, 2)
    assert mapping == {1: (f"{iv}::test_ac1_ac2_goal",),
                       2: (f"{iv}::test_ac1_ac2_goal",)}
    assert _shared_node_ids(mapping) == {f"{iv}::test_ac1_ac2_goal": (1, 2)}

    # no matching node is incomplete-coverage; a collected-but-green set is
    # not-discriminating; a red set that stays red is red-on-final
    assert _criterion_evidence(2, (), None, None, iv).reason == "incomplete-coverage"
    green = _gate_report(iv, passed=(f"{iv}::test_ac2_placeholder",))
    ev = _criterion_evidence(2, (f"{iv}::test_ac2_placeholder",), green, green, iv)
    assert ev.reason == "not-discriminating" and ev.original_failures == 0
    red = _gate_report(iv, failed=(f"{iv}::test_ac2_ok",), green=False)
    green_ok = _gate_report(iv, passed=(f"{iv}::test_ac2_ok",))
    ev = _criterion_evidence(2, (f"{iv}::test_ac2_ok",), red, green_ok, iv)
    assert ev.reason == "" and ev.original_failures == 1 and ev.final_failures == 0
    assert _criterion_evidence(2, (f"{iv}::test_ac2_ok",), red, red, iv).reason == "red-on-final"

    # priority: a structural shared-coverage defect outranks the others; a reparable
    # test defect outranks a fix failure.
    crit = (CriterionEvidence(1, "ac1", 1, 1, 1, 1, "shared-coverage", ""),
            CriterionEvidence(2, "ac2", 0, 0, 0, 0, "incomplete-coverage", ""),
            CriterionEvidence(3, "ac3", 1, 1, 1, 1, "red-on-final", ""))
    assert _classify_criteria(crit) == ("independent-test-shared-coverage", (1,))
    assert _classify_criteria((crit[1],)) == ("independent-test-incomplete-coverage", (2,))
    assert _classify_criteria((crit[2],)) == ("independent-test-red-on-final", (3,))
    assert _classify_criteria(()) == ("", ())


def test_incomplete_coverage_rejects_and_one_repair_can_approve(tmp_path):
    """A green test that names only AC1 of two criteria is rejected with
    ``independent-test-incomplete-coverage`` (listing the uncovered index); the ONE
    bounded re-ask that names the missing criterion then approves."""
    spec = _two_acs_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    ac1 = "tests/test_independent.py::test_ac1_ok"
    ac2 = "tests/test_independent.py::test_ac2_ok"
    # self red(1), impl green(0), IV orig red(ac1,ac2), IV final green ac1 ONLY,
    # repair orig red(ac1,ac2), repair final green ac1+ac2
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([
                            1, 0, _red_result(ac1, ac2), _green_result(ac1),
                            _red_result(ac1, ac2), _green_result(ac1, ac2),
                        ]))

    assert out.claimed is True
    assert out.claimed_basis == "own-test+independent-test"
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert [v.reason for v in out.iv_verdicts] == [
        "independent-test-incomplete-coverage", ""]
    assert out.iv_verdicts[0].covered_indices == (1,)
    assert out.iv_verdicts[0].uncovered_indices == (2,)
    assert out.iv_verdicts[1].covered_indices == (1, 2)
    assert out.iv_verdicts[1].uncovered_indices == ()
    # the repair carried the offending index as evidence
    assert len(seen) == 2 and seen[1].repair_reason == "independent-test-incomplete-coverage"
    assert seen[1].offending_indices == (2,)
    assert "AC2" in seen[1].repair_detail
    assert "independent_test_repair" in ledger_kinds()


def test_shared_coverage_rejects_and_one_repair_can_approve(tmp_path):
    """Finding A through the loop: one node id that serves both criteria is rejected as
    ``independent-test-shared-coverage`` (listing the shared ids), and the ONE bounded
    re-ask that supplies distinct per-criterion nodes then approves."""
    spec = _two_acs_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    seen: list[IndependentTestRequest] = []

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        seen.append(request)
        return iv_candidate()

    shared = "tests/test_independent.py::test_ac1_ac2_goal"
    ac1 = "tests/test_independent.py::test_ac1_ok"
    ac2 = "tests/test_independent.py::test_ac2_ok"
    # self red(1), impl green(0), IV orig red(shared), IV final green(shared),
    # repair orig red(ac1,ac2 distinct), repair final green(ac1,ac2 distinct)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=iv, run_tests=ScriptedTests([
                            1, 0, _red_result(shared), _green_result(shared),
                            _red_result(ac1, ac2), _green_result(ac1, ac2),
                        ]))

    assert out.claimed is True
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert [v.reason for v in out.iv_verdicts] == [
        "independent-test-shared-coverage", ""]
    assert out.iv_verdicts[0].shared_node_ids == (shared,)
    assert out.iv_verdicts[0].offending_indices == (1, 2)
    assert out.iv_verdicts[1].covered_indices == (1, 2)
    # the repair named the shared-coverage reason and the offending indices
    assert len(seen) == 2 and seen[1].repair_reason == "independent-test-shared-coverage"
    assert seen[1].offending_indices == (1, 2)


def test_incomplete_coverage_after_repair_is_recorded_on_the_outcome(tmp_path):
    """ONE repair only. Ticket 19 C: the incomplete-coverage verdict stays recorded as a
    label while the own-test claim stands; the coverage evidence is on the outcome."""
    spec = _two_acs_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    ac1 = "tests/test_independent.py::test_ac1_ok"
    ac2 = "tests/test_independent.py::test_ac2_ok"
    ac1_only = _green_result(ac1)

    # self red(1), impl green(0), IV orig red(ac1,ac2), IV final green ac1,
    # repair orig red(ac1,ac2), repair final green ac1 (still missing ac2)
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([
                            1, 0, _red_result(ac1, ac2), ac1_only,
                            _red_result(ac1, ac2), ac1_only]))

    assert out.claimed is True and out.claimed_basis == "own-test"
    assert out.iv_attempts == 2 and out.iv_repairs == 1
    assert out.iv_verdicts[-1].reason == "independent-test-incomplete-coverage"
    assert out.independent_test_reason.startswith("independent-test-incomplete-coverage")
    assert out.iv_criteria_count == 2
    assert out.iv_covered_indices == [1] and out.iv_uncovered_indices == [2]


def test_empty_acceptance_criteria_cannot_claim_on_the_test_basis(tmp_path):
    """Ticket 19 round 2 (F2): with no extracted acceptance criteria the run may NOT claim
    on the test basis alone. Without a reviewer there is no claim route, so it stops with
    the distinct ``no-acceptance-criteria`` reason."""
    spec = dataclasses.replace(make_spec(), acs=[])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "no-acceptance-criteria"
    assert "no_acceptance_criteria_claim_blocked" in ledger_kinds()


def test_empty_acceptance_criteria_forces_review_and_claims_with_evidence(tmp_path):
    """F2: with a reviewer, an empty criteria list goes through review (grounded evidence,
    F1) and may claim on that basis."""
    spec = dataclasses.replace(make_spec(), acs=[])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_approving_review, run_tests=ScriptedTests([1, 0]))

    assert out.verification_basis == "review"
    assert out.claimed is True and out.claimed_basis == "review"
    assert out.stop_reason == "green"
    assert "review_verification" in ledger_kinds()


def test_evaluate_independent_test_real_gate_rejects_incomplete_coverage():
    """The real report gate: a green test with one criterion missing is rejected by the
    deterministic node-id check, with the uncovered index recorded."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    candidate = IndependentTestCandidate(
        path="tests/test_independent.py",
        content="from pkg.calc import result\n\n\ndef test_ac1_goal():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        candidate, original, final, leaf_mod._default_run_tests, criteria_count=2))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-incomplete-coverage"
    assert verdict.covered_indices == (1,) and verdict.uncovered_indices == (2,)
    assert verdict.offending_indices == (2,)
    assert verdict.final_gate is not None and verdict.final_gate.green is True
    # the per-criterion evidence is carried on the verdict
    assert [(c.index, c.reason) for c in verdict.criteria] == [
        (1, ""), (2, "incomplete-coverage")]


def test_real_gate_rejects_placeholders_that_only_name_the_criterion():
    """The round-10 attack: a real AC1 test plus ``test_ac2_placeholder`` and
    ``test_ac3_placeholder`` (each asserting True). The whole file is green on the final
    source, but the placeholder node sets are green on the ORIGINAL too, so they cannot
    discriminate and the claim is rejected with the offending indices listed."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\n"
               "def test_ac1_goal():\n    assert result() == 42\n\n\n"
               "def test_ac2_placeholder():\n    assert True\n\n\n"
               "def test_ac3_placeholder():\n    assert True\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=3))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-not-discriminating"
    assert verdict.offending_indices == (2, 3)
    assert [c.index for c in verdict.criteria if not c.reason] == [1]
    assert verdict.final_gate is not None and verdict.final_gate.green is True


def test_real_gate_rejects_a_shared_index_test_as_repairable():
    """Finding A (round 11): one genuinely discriminating test renamed to carry EVERY
    index (``test_ac1_ac2_ac3_goal``) used to be selected for every criterion and approve
    them all. "One test per criterion" is now enforced: the node id is mapped to every
    criterion and rejected as ``independent-test-shared-coverage`` (repairable, listing
    the shared node id and the offending indices)."""
    import harness.leaf as leaf_mod
    from harness.leaf import _IV_REPAIRABLE

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\n"
               "def test_ac1_ac2_ac3_goal():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=3))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-shared-coverage"
    assert verdict.reason in _IV_REPAIRABLE                 # repairable once
    assert verdict.offending_indices == (1, 2, 3)
    assert verdict.shared_node_ids == (
        "tests/test_independent.py::test_ac1_ac2_ac3_goal",)
    assert verdict.final_gate is not None and verdict.final_gate.green is True


def test_real_gate_rejects_an_index_colliding_name():
    """Finding C (round 11): ``-k ac1`` was a case-sensitive SUBSTRING match, so a
    criterion could be "covered" by ``test_ac12_thing``. The node map matches the index
    token boundary-aware, so a file whose only test is ``test_ac12_thing`` has no node
    for AC1 and is ``independent-test-incomplete-coverage`` — never an approval."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\n"
               "def test_ac12_thing():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=1))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-incomplete-coverage"
    assert verdict.uncovered_indices == (1,)
    assert verdict.final_gate is not None and verdict.final_gate.green is True


def test_real_gate_accepts_distinct_per_criterion_tests():
    """Genuinely distinct per-criterion tests still approve: three test functions, each
    named with its OWN index, each red on the original and green on the final, map to
    three disjoint node ids."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\n"
               "def test_ac1_goal():\n    assert result() == 42\n\n\n"
               "def test_ac2_goal():\n    assert result() == 42\n\n\n"
               "def test_ac3_goal():\n    assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=3))

    assert verdict.approved is True
    assert verdict.covered_indices == (1, 2, 3)
    assert verdict.shared_node_ids == ()
    assert {nid.rsplit("::", 1)[-1] for nid in verdict.node_ids} == {
        "test_ac1_goal", "test_ac2_goal", "test_ac3_goal"}


def test_real_gate_class_based_test_without_an_indexed_node_name_is_incomplete():
    """Round 11 pins the boundary rule: the junit node NAME of a class method is the
    method name only (the class is not in the report) and only a boundary-aware index
    token in that name maps a criterion. A ``TestAC1::test_thing`` therefore has no node
    for AC1 and is ``independent-test-incomplete-coverage`` — not a silent approval, and
    not a crash."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\nclass TestAC1:\n"
               "    def test_thing(self):\n        assert result() == 42\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=1))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-incomplete-coverage"
    assert verdict.uncovered_indices == (1,)


def test_default_gate_passes_explicit_node_ids_and_never_a_dash_k(tmp_path, monkeypatch):
    """Round 11 pins the SELECTION EXPLICITNESS: a criterion's gate command carries the
    explicit ``path::nodeid`` arguments plus the canary node id — never a ``-k`` term,
    which could match unrelated names."""
    import harness.leaf as leaf_mod

    captured: dict[str, list[str]] = {}

    async def fake_exec(cmd, cwd, **kwargs):
        captured["cmd"] = list(cmd)
        return ShapedResult(command=list(cmd), exit=1, verdict="failed", excerpts=[])

    monkeypatch.setattr(leaf_mod, "k_exec", fake_exec)
    (tmp_path / "tests").mkdir()
    node = "tests/test_independent.py::test_ac1_goal"

    asyncio.run(leaf_mod._default_run_tests(tmp_path, node_ids=(node,)))
    cmd = captured["cmd"]
    assert node in cmd
    assert not any(arg == "-k" or arg.startswith("-k") for arg in cmd)
    assert any(arg.startswith("tests/test_gate_canary_")
               and "::test_gate_canary_" in arg for arg in cmd)

    asyncio.run(leaf_mod._default_run_tests(tmp_path))
    whole = captured["cmd"]
    assert not any(arg == "-k" or arg.startswith("-k") for arg in whole)
    assert node not in whole


def test_real_gate_accepts_a_parametrized_discriminating_test():
    """A ``@pytest.mark.parametrize`` whose ids carry the indices discriminates for every
    index: each ``[ac<i>]`` parameter node is its own explicit node id, which is red on
    the original and green on the final."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("import pytest\nfrom pkg.calc import result\n\n\n"
               "@pytest.mark.parametrize('expected', [42, 42, 42], ids=['ac1', 'ac2', 'ac3'])\n"
               "def test_thing(expected):\n    assert result() == expected\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=3))

    assert verdict.approved is True
    assert verdict.covered_indices == (1, 2, 3)
    assert len(verdict.node_ids) == 3


def test_independent_test_prompt_numbers_criteria_and_asks_one_test_per_criterion():
    """The prompt carries the NUMBERED criteria and the naming convention the coverage
    rule checks; on the coverage repair it carries the uncovered indices."""
    from bench.v2_leaf import _independent_test_question

    request = IndependentTestRequest(goal="g", acs=["first req", "second req"],
                                     original={}, final={})
    question = _independent_test_question(request)
    assert "AC1: first req" in question and "AC2: second req" in question
    assert "ONE test function per criterion" in question
    assert "test_ac1_" in question and "test_ac2_" in question

    repaired = dataclasses.replace(
        request, previous_test="def test_ac1_first(): ...\n",
        repair_reason="independent-test-incomplete-coverage",
        repair_detail="no test node is selected for AC2", offending_indices=(2,))
    repair_q = _independent_test_question(repaired)
    assert "REJECTED (independent-test-incomplete-coverage)" in repair_q
    assert "AC2" in repair_q and "test_ac" in repair_q

    not_discriminating = dataclasses.replace(
        request, previous_test="def test_ac2_second(): ...\n",
        repair_reason="independent-test-not-discriminating",
        repair_detail="the AC2 selection still PASSES on the pre-run source",
        offending_indices=(2,))
    nd_q = _independent_test_question(not_discriminating)
    assert "REJECTED (independent-test-not-discriminating)" in nd_q
    assert "AC2" in nd_q and "FAIL on the" in nd_q

    shared = dataclasses.replace(
        request, previous_test="def test_ac1_ac2_goal(): ...\n",
        repair_reason="independent-test-shared-coverage",
        repair_detail="the node serves AC1 and AC2", offending_indices=(1, 2))
    shared_q = _independent_test_question(shared)
    assert "REJECTED (independent-test-shared-coverage)" in shared_q
    assert "AC1" in shared_q and "AC2" in shared_q
    assert "SEPARATE test function" in shared_q


def test_run_record_carries_the_per_criterion_discrimination_evidence():
    """The persisted run record carries the criteria count and, for EVERY index, the
    selection's original/final collected count and failures plus the reason it failed
    (ticket 17 round 10)."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record
    from harness.leaf import CriterionEvidence

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=3, wall_s=1.0,
        self_test="tests/test_x.py", questions=[], exhausted=False,
        exhaustion_reason="independent-test not discriminating",
        layers_used=[], stop_reason="calls", iv_criteria_count=2,
        iv_criteria=[
            CriterionEvidence(1, "ac1", 1, 1, 1, 0, "", ""),
            CriterionEvidence(2, "ac2", 1, 0, 1, 0, "not-discriminating",
                              "the AC2 selection still PASSES on the pre-run source")],
        iv_covered_indices=[1], iv_uncovered_indices=[],
        independent_test_reason="independent-test-not-discriminating: the selection for AC2")
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[],
                          skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0, iv_enabled=True,
                          acs=["a", "b"])

    assert record["iv_criteria_count"] == 2
    assert record["iv_covered_indices"] == [1]
    assert record["iv_uncovered_indices"] == []
    assert [(c["index"], c["original_failures"], c["reason"])
            for c in record["iv_criteria"]] == [
        (1, 1, ""), (2, 0, "not-discriminating")]
    assert record["independent_test_reason"].startswith(
        "independent-test-not-discriminating")
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
                        lambda candidate, original, final, run_tests, **kw: approved)

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
    # Ticket 19 E: the request names the client's fetch() (and both call sites) but the
    # run touched only the transport, so per-requirement artifact coverage refuses the
    # claim — the design answer to the T-31 false success.
    assert out.claimed is False
    assert any("fetch" in m for m in out.coverage_missing)


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


# ------------------------- ticket 18 round 4: a bare 'unable' self-test cannot crash
# The §0 grammar leaves the payload fields at the REQUIRED (_Missing) sentinel on the
# unable branch; the sentinel used to reach Path(...) and raise TypeError out of the
# loop. It must take the ordinary honest self-test refusal instead.

BARE_UNABLE = {"status": "unable", "comment": "cannot write a test",
               "unable_reason": "no interpreter available"}


def test_bare_unable_self_test_envelope_is_refused_not_a_crash(tmp_path):
    """A bare ``unable`` self-test envelope carries no file_path (its value is the
    REQUIRED sentinel), so it takes the honest ``self-test`` refusal — never a crash."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [BARE_UNABLE]})

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1]))

    assert out.claimed is False
    assert out.stop_reason == "self-test"
    assert out.signal == "honest-failure"
    assert out.self_test is None
    assert "self_test_unavailable" in ledger_kinds()
    assert any("status=unable" in r for r in out.refusals)


def test_bare_unable_implementation_envelope_is_refused_not_a_crash(tmp_path):
    """The same non-string sentinel on an implementation envelope is a plain refusal
    (``no file_path``), not a crash out of the write guard."""
    from harness.leaf import _write_candidate

    spec = make_spec()
    stage(tmp_path, spec.files)
    from harness.envelopes import REQUIRED

    class _Envelope:
        status = "ok"
        file_path = REQUIRED          # the §0 sentinel, not a string

    wrote, rel, refusal, shape = _write_candidate(_Envelope(), spec, tmp_path, None, {})
    assert wrote is False and rel == "" and not shape
    assert "no file_path" in refusal


# ------------------------------------------- round 6: sweep flags / run-record evidence

def test_sweep_exposes_and_forwards_the_judge_and_iv_flags(tmp_path, monkeypatch):
    """An A/B measurement must run unattended: the sweep exposes --judge/--no-judge,
    --iv/--no-iv and --review/--no-review and forwards all three to the driver."""
    from bench import v2_sweep

    parser = v2_sweep.build_parser()
    assert parser.parse_args([]).judge is True and parser.parse_args([]).iv is True
    assert parser.parse_args([]).review is True
    off = parser.parse_args(["--no-judge", "--no-iv", "--no-review"])
    assert off.judge is False and off.iv is False and off.review is False

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
    assert seen == [{"use_judge": True, "use_iv": True, "use_review": True}]

    seen.clear()
    monkeypatch.setattr("sys.argv", ["v2_sweep", "--tasks", "all", "--no-judge", "--no-iv",
                                     "--no-review"])
    assert v2_sweep.main() == 0
    assert seen == [{"use_judge": False, "use_iv": False, "use_review": False}]


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


# ===========================================================================
# ticket 19: proactive MULTI-LABEL attribution, review-based verification,
# declared test cases, and per-requirement artifact coverage
# ===========================================================================

from harness.attempts import judge_labels  # noqa: E402


def test_judge_verdict_is_multilabel_with_a_dominant_summary():
    """Ticket 19 A: the verdict carries four independent labels plus reason/evidence; the
    legacy single ``attribution`` is the dominant SUMMARY (spec > environment > test >
    implementation)."""
    both = JudgeVerdict(implementation_wrong=True, test_wrong=True, reason="both are wrong")
    assert judge_labels(both) == ("test_wrong", "implementation_wrong")
    assert both.attribution == "tests" and both.reason == "both are wrong"
    spec = JudgeVerdict(attribution="spec")
    assert spec.spec_wrong is True and spec.attribution == "spec"
    env = JudgeVerdict(attribution="environment")
    assert env.environment_broken is True and env.attribution == "environment"


def test_proactive_judge_fires_once_on_the_kth_red_code_changing_attempt(tmp_path):
    """Ticket 19 A: the judge is consulted when the run's own test REPORTS RED — after K=2
    consecutive red attempts that materially changed the code — not only when the model
    volunteers a blame."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n"),
        impl("def result():\n    return 3\n"),
    ]})
    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        return JudgeVerdict(implementation_wrong=True, reason="still wrong")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1, 1, 1, 1]))

    assert len(seen) == 1                       # exactly once, at the K-th red
    request = seen[0]
    # the judge carries the evidence the owner direction names: goal, ACs, the run's own
    # test source, the failing output, and the current diff of the changed files.
    assert request.goal == spec.goal
    assert request.acs == spec.acs
    assert "def test_goal" in request.test_content
    assert request.test_path == "tests/test_leaf_self.py"
    assert "FAILED" in request.failure or "AssertionError" in request.failure
    assert request.files["pkg/calc.py"] == "def result():\n    return 2\n"
    assert "judge_triggered" in ledger_kinds()
    assert out.judge_verdicts and out.judge_verdicts[0].implementation_wrong
    assert out.claimed is False


def test_spec_wrong_dominates_and_bubbles_to_the_parent(tmp_path):
    """Ticket 19 A: spec_wrong dominates — the node stops and bubbles, because an
    implementation and a test are meaningless against a wrong spec."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"), impl("def result():\n    return 2\n")]})

    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(spec_wrong=True, implementation_wrong=True,
                                           reason="the requirement contradicts the code"),
        run_tests=ScriptedTests([1, 1, 1]))

    assert out.signal == "bubble" and out.needs_parent is True
    assert out.stop_reason == "spec-bubble" and out.claimed is False
    assert "spec_bubbled_up" in ledger_kinds()


def test_environment_broken_parks_needs_user_without_burning_budget(tmp_path):
    """Ticket 19 A: environment_broken means we cannot fix it in-process — park honestly
    (needs-user) instead of burning the budget on more attempts."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"), impl("def result():\n    return 2\n")]})

    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(environment_broken=True, reason="no interpreter"),
        run_tests=ScriptedTests([1, 1, 1]))

    assert out.stop_reason == "environment" and out.needs_user is True
    assert out.claimed is False and out.needs_parent is False
    assert out.calls < 20
    assert "environment_broken" in ledger_kinds()


# ------------------------------------------------------------- review-based verification


def _approving_review(request: ReviewRequest) -> ReviewVerdict:
    changed = next(iter(request.final), "pkg/calc.py")
    return ReviewVerdict(grade="definitely-ok", evidence=f"{changed}:1 implements the goal",
                         detail="ok")


def test_no_red_target_switches_to_review_and_claims_with_evidence(tmp_path):
    """Ticket 19 B/C: when the own test cannot be made red on arrival, the node switches to
    REVIEW-based verification and may claim on a passing review with evidence."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_approving_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.verification_basis == "review"
    assert out.claimed is True and out.claimed_basis == "review"
    assert out.stop_reason == "green"
    assert out.review_verdict is not None and out.review_verdict.approved
    assert "review_verification" in ledger_kinds() and "review_verdict" in ledger_kinds()


def test_apply_review_filter_requires_a_changed_artifact_not_a_bare_line():
    """Ticket 19 B / round 2 (F1): a pass is honoured only with a CHANGED file (or a symbol
    in a changed file's final text). A bare line reference is coerced, and a zero-change
    diff can never claim by any route."""
    request = ReviewRequest(goal="g", acs=["a"], original={"pkg/calc.py": "x"},
                            final={"pkg/calc.py": "y"})
    good = apply_review_filter(
        ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:1 implements AC-1"), request)
    assert good.approved is True and good.coerced is False
    # F1: a bare line reference names no changed artifact and is no longer enough
    line = apply_review_filter(
        ReviewVerdict(grade="definitely-ok", evidence="line 3 satisfies the requirement"), request)
    assert line.approved is False and line.coerced is True
    vibes = apply_review_filter(ReviewVerdict(grade="definitely-ok", evidence="looks good"), request)
    assert vibes.approved is False and vibes.coerced is True
    # a symbol that occurs in a changed file's final text is accepted
    request2 = ReviewRequest(goal="g", acs=["a"], original={"pkg/calc.py": "def compute_total():\n    return 1\n"},
                             final={"pkg/calc.py": "def compute_total():\n    return 7\n"})
    symbol = apply_review_filter(
        ReviewVerdict(grade="definitely-ok", evidence="`compute_total` now returns 7"), request2)
    assert symbol.approved is True
    # F1 zero-change pin: an UNCHANGED tree can NEVER claim, path or line reference alike
    no_op = ReviewRequest(goal="g", acs=["a"], original={}, final={})
    assert apply_review_filter(
        ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:1 fixes AC-1"),
        no_op).approved is False
    assert apply_review_filter(
        ReviewVerdict(grade="definitely-ok", evidence="line 1 is fine"), no_op).approved is False


def test_review_without_evidence_cannot_claim(tmp_path):
    """The driver's review must carry evidence: an unevidenced pass is coerced and the
    node never claims from it."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT] + [impl()] * 4})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        review=lambda request: ReviewVerdict(grade="definitely-ok", evidence=""),
                        run_tests=ScriptedTests([0, 0, 0, 1, 1, 1]))

    assert out.claimed is False
    assert out.review_verdict is not None and out.review_verdict.coerced is True


def test_repaired_test_that_cannot_discriminate_switches_to_review(tmp_path):
    """Ticket 19 B: the judge says the test is wrong, but the bounded repair still cannot
    produce a discriminating test (it greens on arrival) — review becomes mandatory."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_approving_review,
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.verification_basis == "review"
    assert out.claimed is True and out.claimed_basis == "review"
    assert out.test_rewrites == 1


def test_unwritable_self_test_path_switches_to_review(tmp_path, monkeypatch):
    """Ticket 19 C2: when the test path is declared unwritable, a review verdict with
    evidence is the claim route."""
    import harness.leaf as leaf_mod

    real_write = leaf_mod._write

    def refusing_write(workdir, rel, content):
        if rel.endswith("test_leaf_self.py"):
            raise leaf_mod.WriteShapeRefused(rel, "unwritable path (OSError: read-only)")
        return real_write(workdir, rel, content)

    monkeypatch.setattr(leaf_mod, "_write", refusing_write)
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_approving_review, run_tests=ScriptedTests([0]))

    assert out.verification_basis == "review"
    assert out.claimed is True and out.claimed_basis == "review"


# ------------------------------------------------- declared test-case contract (ticket 19 D)


def test_declared_test_case_present_and_passing_allows_the_claim(tmp_path):
    spec = dataclasses.replace(
        make_spec(),
        test_cases=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_ac1",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.test_case_problems == []


def test_declared_test_case_missing_is_a_repairable_failure_and_blocks_the_claim(tmp_path):
    spec = dataclasses.replace(
        make_spec(),
        test_cases=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl(), SELF_TEST]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "test-cases"
    assert out.test_case_problems and "test_goal" in out.test_case_problems[0]
    assert "test_case_repair" in ledger_kinds()


def test_declared_test_case_name_check_is_boundary_aware():
    """A declared ``test_ac1`` must NOT be satisfied by a collected ``test_ac1_extra``."""
    report = GateReport(report_path="(scripted)", process_exit=0, canary="c", expected_files=(),
                        n_tests=1, n_failed=0, n_errors=0,
                        passed_ids=("tests/test_x.py::test_ac1_extra",), failed_ids=(),
                        missing=(), observed=True)
    problems = _declared_test_case_problems(
        report, (DeclaredTestCase("AC-1", "tests/test_x.py", ("test_ac1",)),))
    assert problems and "not collected" in problems[0]


# ----------------------------------------- per-requirement artifact coverage (ticket 19 E)


def test_requirement_artifact_coverage_blocks_a_claim_when_the_named_file_is_untouched(tmp_path):
    """Ticket 19 E: a criterion whose named file is untouched was not implemented — the
    node may not claim (the T-31 answer)."""
    spec = dataclasses.replace(make_spec(), acs=["pkg/calc.py must return 42"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl(path="pkg/other.py", content="x = 1\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert any("pkg/calc.py" in m for m in out.coverage_missing)
    assert "requirement_uncovered" in ledger_kinds()


def test_requirement_coverage_records_symbols_and_flags_unresolvable_text(tmp_path):
    """Ticket 19 E / round 2 (F2): a resolvable criterion records its symbol; a criterion
    that names NO artifact is flagged ``unresolved`` — it is NOT silently skipped."""
    spec = dataclasses.replace(make_spec(), acs=["result() returns 42", "the widget is blue"])
    stage(tmp_path, spec.files)
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 1\n")
    baseline = {"pkg/calc.py": "def result():\n    return 0\n"}
    coverage = _requirement_coverage(spec, tmp_path, baseline)
    assert coverage[0].ok and "result" in coverage[0].symbols
    assert not _criterion_unresolved(coverage[0])
    assert not coverage[1].files and not coverage[1].symbols
    assert _criterion_unresolved(coverage[1])


def test_driver_review_defaults_on_and_maps_the_leaf_review_envelope():
    """Ticket 19 B driver wiring: ``--review`` is ON by default and the default reviewer
    reads the §26 ``leaf_review`` envelope into a :class:`ReviewVerdict`."""
    from bench.v2_leaf import build_parser, model_review

    assert build_parser().parse_args(["--task", "x"]).review is True
    assert build_parser().parse_args(["--task", "x", "--no-review"]).review is False

    model = FakeModelRunner({"leaf_review": [
        {"status": "ok", "comment": "reviewed", "grade": "definitely-ok",
         "evidence": "pkg/calc.py:1 implements AC-1"},
        {"status": "unable", "comment": "cannot review", "unable_reason": "no source"},
    ]})
    request = ReviewRequest(goal="g", acs=["a"], original={"pkg/calc.py": "x"},
                            final={"pkg/calc.py": "y"}, angle="ac-correctness")
    verdict = asyncio.run(model_review(model, request))
    assert verdict.approved is True and verdict.grade == "definitely-ok"
    assert verdict.angle == "ac-correctness" and "pkg/calc.py:1" in verdict.evidence
    assert model.calls("leaf_review")[0].fresh is True
    unable = asyncio.run(model_review(model, request))
    assert unable.approved is False and unable.grade == "uncertain"


def test_run_record_carries_the_verification_basis_and_coverage():
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record
    from harness.leaf import RequirementCoverage

    outcome = LeafOutcome(
        claimed=True, signal="green", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="",
        layers_used=[], stop_reason="green", verification_basis="review",
        claimed_basis="review",
        review_verdicts=[ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:1 fixes AC-1")],
        coverage=[RequirementCoverage(1, "c", files=("pkg/calc.py",), symbols=("result",))])
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0, review_enabled=True)

    assert record["verification_basis"] == "review"
    assert record["claimed_basis"] == "review"
    assert record["review"] is True
    assert record["review_verdicts"][0]["grade"] == "definitely-ok"
    assert record["review_verdicts"][0]["angle"] == ""
    assert record["coverage"][0]["files"] == ("pkg/calc.py",)
    json.dumps(record)


def test_no_red_target_consults_the_judge_immediately(tmp_path):
    """Ticket 19 A: the judge is called immediately when the own test cannot be made red on
    arrival — here it attributes the failure to the spec, so the node bubbles."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(spec_wrong=True, reason="the goal is wrong"),
        run_tests=ScriptedTests([0, 0]))

    assert out.signal == "bubble" and out.needs_parent is True
    assert out.stop_reason == "spec-bubble"
    assert out.judge_verdicts and out.judge_verdicts[0].spec_wrong


def test_no_red_target_environment_verdict_parks_needs_user(tmp_path):
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(environment_broken=True, reason="no interpreter"),
        run_tests=ScriptedTests([0, 0]))

    assert out.stop_reason == "environment" and out.needs_user is True


def test_declared_case_repair_must_still_discriminate(tmp_path):
    """Ticket 19 D: a repaired own test must be RED on the pristine source (a private copy)
    so a declared-case repair cannot smuggle a weakened test into a claim."""
    from harness.leaf import _repaired_test_is_red_on_pristine

    spec = dataclasses.replace(make_spec(), acs=["result() returns 42"])
    stage(tmp_path, spec.files)
    calls: list[Path] = []

    def runner(workdir, node_ids=None):
        workdir = Path(workdir)
        calls.append(workdir)
        if workdir != tmp_path:                     # the private pristine copy
            return ShapedResult(command=[], exit=1, verdict="failed",
                                excerpts=["FAILED"], gate=scripted_red_gate())
        return ShapedResult(command=[], exit=0, verdict="ok", gate=scripted_gate())

    assert asyncio.run(_repaired_test_is_red_on_pristine(
        runner, spec, "tests/test_leaf_self.py", "def test_goal():\n    assert True\n")) is True
    assert calls and calls[0] != tmp_path          # ran in a private copy, never the workdir


def test_review_blocks_the_claim_until_it_passes(tmp_path):
    """Ticket 19 B: when no test can carry verification, the node may NOT claim until a
    review PASSES. A failing review becomes the next attempt's context; only the passing
    review closes the node (basis ``review``)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, SELF_TEST_ALT,                       # both green on arrival: no red target
        impl("def result():\n    return 1\n"),          # attempt 1
        impl("def result():\n    return 42\n"),         # attempt 2
    ]})
    # One fresh call per DECLARED ANGLE (ticket 20 item 1); the default implementation
    # set is the two critical angles, so attempt 1 grades both bad and attempt 2 both good.
    verdicts = [
        ReviewVerdict(grade="definitely-problematic",
                      evidence="pkg/calc.py:1 returns 1, not 42", detail="AC-1 unmet"),
        ReviewVerdict(grade="probably-problematic",
                      evidence="pkg/calc.py:1 breaks the contract", detail="contract unmet"),
        ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:2 returns 42 for AC-1"),
        ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:2 keeps the contract"),
    ]

    def review(request: ReviewRequest) -> ReviewVerdict:
        return verdicts.pop(0)

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        review=review, run_tests=ScriptedTests([0, 0, 0, 0]))

    assert out.verification_basis == "review"
    assert out.claimed is True and out.claimed_basis == "review"
    assert [v.approved for v in out.review_verdicts] == [False, False, True, True]
    assert out.review_verdict is not None and out.review_verdict.approved
    assert "review_verdict" in ledger_kinds()


def test_requirement_coverage_two_call_sites_requires_both(tmp_path):
    """Ticket 19 E / T-31: the request names TWO call sites; a run that changed only one may
    NOT claim. Touching both clears the coverage gate."""
    spec = dataclasses.replace(
        make_spec({"pkg/calc.py": "def result():\n    return 0\n",
                   "pkg/other.py": "def helper():\n    return 0\n"},
                  goal="thread the timeout through pkg/calc.py and pkg/other.py"),
        acs=["thread the timeout through pkg/calc.py and pkg/other.py"])

    # only one of the two named files is touched -> coverage is missing pkg/other.py
    work = tmp_path / "one"
    stage(work, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl(path="pkg/calc.py", content="def result():\n    return 1\n")]})
    out = run_leaf_sync(model, spec, work, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))
    assert out.claimed is False
    assert any("pkg/other.py" in m for m in out.coverage_missing)
    assert out.coverage[0].missing == ("pkg/other.py",)

    # both named files touched -> the coverage gate clears and the run claims
    work = tmp_path / "both"
    stage(work, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl(path="pkg/calc.py", content="def result():\n    return 1\n"),
        impl(path="pkg/other.py", content="def helper():\n    return 1\n"),
    ]})
    out = run_leaf_sync(model, spec, work, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 0]))
    assert out.claimed is True and out.stop_reason == "green"
    assert out.coverage_missing == []


def test_run_record_carries_the_attribution_labels(tmp_path):
    """The run record persists the multi-label attribution (the four booleans) so a
    consumer can audit what the judge decided."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record
    from harness.leaf import RequirementCoverage

    outcome = LeafOutcome(
        claimed=True, signal="green", attempts=[], calls=3, wall_s=1.0,
        self_test="tests/test_x.py", questions=[], exhausted=False, exhaustion_reason="",
        layers_used=[], stop_reason="green", claimed_basis="own-test",
        judge_verdicts=[JudgeVerdict(implementation_wrong=True, test_wrong=True,
                                     reason="both wrong", evidence="pkg/calc.py:1")],
        coverage=[RequirementCoverage(1, "c", files=("pkg/calc.py",), symbols=("result",))])
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0, judge_enabled=True)

    labels = record["judge_verdicts"][0]
    assert labels["implementation_wrong"] is True and labels["test_wrong"] is True
    assert labels["spec_wrong"] is False and labels["environment_broken"] is False
    assert labels["reason"] == "both wrong" and labels["evidence"] == "pkg/calc.py:1"
    assert record["claimed_basis"] == "own-test"
    json.dumps(record)


# ===========================================================================
# Ticket 19 round 2 — the adversarial fixes (F1–F5)
# ===========================================================================


def _pristine_distinguishing_runner(tmp_path, *, pristine_red: bool,
                                    own_test_node="tests/test_leaf_self.py::test_goal"):
    """A run_tests seam for the unresolved-criterion tests.

    On the workdir (``tmp_path``) the run's own test is RED then GREEN; in the private
    pristine copy (used by :func:`harness.leaf._declared_case_discriminates`) the declared
    test is RED (a real discriminator) or GREEN (a placeholder that asserts True)."""
    state = {"n": 0}

    def runner(workdir, node_ids=None):
        if Path(workdir) != tmp_path:
            return (_red_result(own_test_node) if pristine_red
                    else _green_result(own_test_node))
        state["n"] += 1
        return (_red_result(own_test_node) if state["n"] == 1
                else _green_result(own_test_node))

    return runner


def test_unresolved_criterion_is_carried_by_a_discriminating_declared_test(tmp_path):
    """F2/F4: a criterion that names NO artifact is not skipped — a declared test that is
    RED on the pristine source carries it, so the node may claim."""
    spec = dataclasses.replace(
        make_spec(),
        acs=["thread the timeout through the result and helper call sites"],
        test_cases=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        run_tests=_pristine_distinguishing_runner(tmp_path, pristine_red=True))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.coverage_unresolved == []
    assert _criterion_unresolved(out.coverage[0])


def test_unresolved_criterion_without_a_declared_test_cannot_claim(tmp_path):
    """F2 + round-3 FIX 1: with no declared discriminating test to carry it and NO
    reviewer injected, an unresolvable criterion is an honest stop with a distinct,
    recorded reason — never a ladder burn."""
    spec = dataclasses.replace(
        make_spec(), acs=["thread the timeout through the result and helper call sites"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, *[impl()] * 6]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
        run_tests=_pristine_distinguishing_runner(tmp_path, pristine_red=True))

    assert out.claimed is False
    assert out.stop_reason == "criterion-unresolved"
    assert out.coverage_unresolved and "AC1" in out.coverage_unresolved[0]
    assert "criterion_unresolved" in ledger_kinds()


def test_blocked_criterion_routes_to_review_and_claims_with_evidence(tmp_path):
    """FIX 1: an unresolvable criterion enters the owner's REVIEW path; a grounded review
    pass on the changed diff then allows the claim on ``verification_basis=review`` while
    the blocker stays recorded for audit."""
    spec = dataclasses.replace(
        make_spec(), acs=["thread the timeout through the result and helper call sites"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        review=_approving_review,
        run_tests=_pristine_distinguishing_runner(tmp_path, pristine_red=True))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.verification_basis == "review" and out.claimed_basis == "review"
    assert out.coverage_unresolved and "AC1" in out.coverage_unresolved[0]
    assert out.review_verdict is not None and out.review_verdict.approved
    assert "criterion_unresolved" in ledger_kinds()
    assert "review_verification" in ledger_kinds() and "review_verdict" in ledger_kinds()


def test_blocked_declared_test_case_routes_to_review_and_claims(tmp_path):
    """FIX 1: a declared test case that survives the bounded repair and cannot carry the
    claim enters the REVIEW path, where a grounded pass allows the claim on the review
    basis (the declared-case defect stays recorded)."""
    spec = dataclasses.replace(
        make_spec(),
        test_cases=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl(), SELF_TEST]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
        review=_approving_review, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.verification_basis == "review" and out.claimed_basis == "review"
    assert out.test_case_problems and "test_goal" in out.test_case_problems[0]
    assert "review_verification" in ledger_kinds() and "review_verdict" in ledger_kinds()


def test_malformed_judge_is_consulted_at_most_once_per_attempt(tmp_path):
    """FIX 2: the volunteer-blame site and the proactive site in the SAME attempt share
    one bounded judge consultation, so a malformed judge costs at most
    ``JUDGE_RETRIES + 1`` calls per attempt instead of twice that."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl(comment="the test is wrong"),
        impl(comment="the test is wrong"),
    ]})
    seen: list[JudgeRequest] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        seen.append(request)
        raise ValueError("judge output was not a verdict")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1] * 6))

    assert out.claimed is False
    # two attempts, each consulting the judge once with one bounded retry
    assert len(seen) == 4
    assert out.judge_unavailable == 2


def test_blocked_criterion_review_without_grounded_evidence_cannot_claim(tmp_path):
    """FIX 1 does not loosen F1: a review pass whose evidence names no changed artifact is
    coerced to a fail by the deterministic filter, so the blocker still cannot claim."""
    spec = dataclasses.replace(
        make_spec(), acs=["thread the timeout through the result and helper call sites"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, *[impl()] * 4]})

    def ungrounded(request: ReviewRequest) -> ReviewVerdict:
        return ReviewVerdict(grade="definitely-ok", evidence="looks good to me")

    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        review=ungrounded,
        run_tests=_pristine_distinguishing_runner(tmp_path, pristine_red=True))

    assert out.claimed is False
    assert out.coverage_unresolved and "AC1" in out.coverage_unresolved[0]
    assert out.review_verdicts and out.review_verdicts[0].coerced is True


def test_unresolved_criterion_with_a_placeholder_declared_test_cannot_claim(tmp_path):
    """F4: a placeholder declared test (green on the pristine source) does not discriminate
    and cannot carry an unresolvable criterion."""
    spec = dataclasses.replace(
        make_spec(),
        acs=["thread the timeout through the result and helper call sites"],
        test_cases=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, *[impl()] * 6]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
        run_tests=_pristine_distinguishing_runner(tmp_path, pristine_red=False))

    assert out.claimed is False
    assert out.stop_reason == "criterion-unresolved"
    assert out.coverage_unresolved and "AC1" in out.coverage_unresolved[0]
    assert "criterion_unresolved" in ledger_kinds()


def test_comment_only_edit_is_not_a_change(tmp_path):
    """F3: a criterion's named file is NOT covered by a comment-only edit."""
    spec = dataclasses.replace(make_spec(), acs=["pkg/calc.py must return 42"])
    stage(tmp_path, spec.files)
    (tmp_path / "pkg" / "calc.py").write_text(
        "# a brand new comment\ndef result():\n    return 0\n")
    baseline = {"pkg/calc.py": "def result():\n    return 0\n"}
    coverage = _requirement_coverage(spec, tmp_path, baseline)
    assert not coverage[0].ok and "pkg/calc.py" in coverage[0].missing


def test_symbol_that_only_moved_in_a_comment_is_not_covered(tmp_path):
    """F3: a symbol that already existed is not 'covered' by a comment-only edit."""
    spec = dataclasses.replace(make_spec(), acs=["result() returns 42"])
    stage(tmp_path, spec.files)
    (tmp_path / "pkg" / "calc.py").write_text(
        "def result():\n    return 0\n# result() is covered now\n")
    baseline = {"pkg/calc.py": "def result():\n    return 0\n"}
    coverage = _requirement_coverage(spec, tmp_path, baseline)
    assert "result" in coverage[0].symbols
    assert "result" in coverage[0].missing


def test_changed_files_ignore_comments_and_whitespace(tmp_path):
    """F3: the node diff is compared with comments and whitespace stripped."""
    from harness.leaf import _changed_files

    (tmp_path / "pkg").mkdir(parents=True)
    baseline = {"pkg/calc.py": "def result():\n    return 0\n"}
    (tmp_path / "pkg" / "calc.py").write_text("# note\ndef result():\n\n    return 0\n")
    assert _changed_files(tmp_path, baseline) == {}      # comment/whitespace only
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 1\n")
    assert "pkg/calc.py" in _changed_files(tmp_path, baseline)


def test_review_of_a_no_op_diff_cannot_claim(tmp_path):
    """F1+F3: review cannot carry a diff that changed nothing, even with a concrete line
    reference to an unchanged file — and a COMMENT-ONLY edit is not a change."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    # both self tests green on arrival ⇒ review; the implement adds only a comment.
    model = FakeModelRunner({"write_test": [
        SELF_TEST, SELF_TEST_ALT,
        impl(content="# a meaningless comment\ndef result():\n    return 0\n")]})
    seen: list[ReviewRequest] = []

    def review(request: ReviewRequest) -> ReviewVerdict:
        seen.append(request)
        return ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:1 implements the goal")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=review, run_tests=ScriptedTests([0, 0, 0]))

    assert seen and seen[0].final == {}                 # comment-only ⇒ nothing changed
    assert out.claimed is False
    assert out.review_verdict is not None and out.review_verdict.coerced


def test_malformed_steps_are_recorded_on_the_run_record():
    """F5: the persisted run record carries every malformed step."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=4, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="",
        layers_used=[], stop_reason="calls", malformed_steps=["self-test", "implement"])
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="missed-success", run_wall_s=1.0)
    assert record["malformed_steps"] == ["self-test", "implement"]
    json.dumps(record)


# ===========================================================================
# ticket 20: the verification covenant (ordered tiers, checked reason, reviews)
# ===========================================================================


def verify_env(reason: str, status: str = "ok") -> dict:
    return {"status": status, "comment": "justify", "reason": reason}


GOOD_REASON = ("no test can pin this timing-dependent warning and no reviewer was "
               "available to check the diff")


class ScriptedReview:
    """A stateful reviewer: one verdict per call, the last repeating."""

    def __init__(self, verdicts):
        self._verdicts = list(verdicts)
        self.calls = 0

    def __call__(self, request: ReviewRequest) -> ReviewVerdict:
        verdict = self._verdicts[min(self.calls, len(self._verdicts) - 1)]
        self.calls += 1
        return verdict(request) if callable(verdict) else verdict


def _passing_review(request: ReviewRequest) -> ReviewVerdict:
    changed = next(iter(request.final), "pkg/calc.py")
    return ReviewVerdict(grade="definitely-ok", evidence=f"{changed}:1 implements the goal")


def _rejecting_review(request: ReviewRequest) -> ReviewVerdict:
    return ReviewVerdict(grade="probably-problematic", detail="the goal is not met")


def test_verification_tier_order_is_test_review_none():
    """The ORDERED tier list, and the deterministic check on the ``none+reason`` text."""
    assert VERIFICATION_TIERS == ("test", "review", "none")
    # empty / too short / off-topic all fail
    assert verification_reason_problem("") != ""
    assert verification_reason_problem("too short") != ""
    assert verification_reason_problem("nothing to say here at all really") != ""
    # names the activity but not WHY
    assert verification_reason_problem("we did not run a test for this helper function") != ""
    # says WHY but names no activity
    assert verification_reason_problem("cannot fix this properly right now, sorry about that") != ""
    # names the activity AND the why: accepted
    assert verification_reason_problem(
        "testing is not possible because the clock value is only injected in production") == ""
    assert verification_reason_problem(GOOD_REASON) == ""


def test_none_reason_must_be_substantive_not_boilerplate_or_a_restatement():
    """Ticket 20 item 4 / round-1 gap 1: a 24+ character sentence that merely mentions
    testing and a why is NOT enough. Boilerplate/template, a generic keyword soup with no
    artifact, and a restatement of the goal are all rejected; a named observation passes."""
    goal = "make result() return 42"
    acs = ["result() returns 42"]
    boilerplate = ("no test can carry verification for this node and no independent "
                   "review is available")
    assert verification_reason_problem(boilerplate, goal=goal, acs=acs) != ""
    generic = "testing and reviewing are not possible for this change"
    assert verification_reason_problem(generic, goal=goal, acs=acs) != ""
    restatement = "testing is not possible because make result() return 42"
    assert verification_reason_problem(restatement, goal=goal, acs=acs) != ""
    substantive = ("no test can pin the timing-dependent warning that only occurs under "
                   "load in production")
    assert verification_reason_problem(substantive, goal=goal, acs=acs) == ""
    assert "boilerplate" in verification_reason_problem(boilerplate)
    assert "restates" in verification_reason_problem(restatement, goal=goal, acs=acs)


def test_discriminating_own_test_claims_at_the_test_tier_verified(tmp_path):
    """The strong-evidence route: a red-on-arrival own test that greens unmodified claims
    at the ``test`` tier and is a VERIFIED success."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.verification is not None and out.verification.wrote_code is True
    assert out.verification.tier == "test"
    assert out.verification.verified is True and out.verification.reason == ""
    assert out.verified is True and out.claim_status == "verified-success"


def test_review_tier_claim_records_the_independent_review(tmp_path):
    """A claim on the review route carries a ``review`` tier and every independent verdict."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.verified is True and out.claim_status == "verified-success"
    assert out.verification.tier == "review" and out.verification.verified is True
    # Ticket 20 item 1: the default implementation review runs the two CRITICAL angles.
    assert out.verification.review_angles == ("ac-correctness", "contract-compat")
    assert len(out.verification.reviews) == 2
    assert out.verification.review_score == 12     # 3*(+2) + 3*(+2)
    assert out.verification.reviews[0].evidence


def test_review_angles_run_one_call_per_declared_angle_and_combine_by_weight(tmp_path):
    """Ticket 20 items 1-3: ``review_angles`` runs ONE fresh call per angle (a different
    angle each), and the weighted score decides. A negative grade is an ACTION ITEM: the
    node keeps working instead of claiming."""
    from harness.leaf import combine_review_verdicts, weighted_review_score

    spec = dataclasses.replace(
        make_spec(),
        review_angles=("ac-correctness", "contract-compat", "maintainability"))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, SELF_TEST_ALT,
        impl("def result():\n    return 1\n"),
        impl("def result():\n    return 42\n"),
    ]})
    # attempt 1: ac-correctness bad, contract-compat ok, maintainability bad; attempt 2: all ok
    review = ScriptedReview([
        ReviewVerdict(grade="probably-problematic", evidence="pkg/calc.py:1 returns 1"),
        ReviewVerdict(grade="definitely-ok", evidence="pkg/calc.py:1 keeps the contract"),
        ReviewVerdict(grade="probably-problematic", evidence="pkg/calc.py:1 is unreadable"),
        _passing_review, _passing_review, _passing_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        review=review, run_tests=ScriptedTests([0, 0, 0, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert review.calls == 6                      # 3 angles x 2 attempts
    assert [v.approved for v in out.review_verdicts] == [False, True, False, True, True, True]
    assert out.verification.review_angles == (
        "ac-correctness", "contract-compat", "maintainability")
    assert out.verification.review_score == 14    # 3*2 + 3*2 + 1*2
    assert out.verification.tier == "review"
    # The aggregation is itself pinned: a negative grade blocks the claim, and a missing
    # CRITICAL angle blocks it even when every present angle is positive.
    ok, score, why = combine_review_verdicts(
        [ReviewVerdict(angle="ac-correctness", grade="definitely-ok"),
         ReviewVerdict(angle="contract-compat", grade="probably-problematic")],
        ("ac-correctness", "contract-compat"), "implementation")
    assert ok is False and why
    ok2, _score2, why2 = combine_review_verdicts(
        [ReviewVerdict(angle="maintainability", grade="definitely-ok")],
        ("maintainability",), "implementation")
    assert ok2 is False and "critical" in why2
    assert weighted_review_score(
        [ReviewVerdict(angle="maintainability", grade="definitely-ok")]) == 2


def test_critical_angle_definitely_problematic_vetoes_regardless_of_the_average():
    """Ticket 20 item 3: a ``definitely-problematic`` grade on a CRITICAL angle vetoes the
    candidate even though the weighted average stays positive."""
    from harness.leaf import combine_review_verdicts, critical_review_veto

    verdicts = [ReviewVerdict(angle="ac-correctness", grade="definitely-problematic",
                              evidence="pkg/calc.py returns the wrong value"),
                ReviewVerdict(angle="maintainability", grade="definitely-ok"),
                ReviewVerdict(angle="contract-compat", grade="definitely-ok")]
    veto = critical_review_veto(verdicts, "implementation")
    assert veto and "ac-correctness" in veto
    ok, score, why = combine_review_verdicts(
        verdicts, ("ac-correctness", "contract-compat", "maintainability"),
        "implementation")
    assert ok is False and "critical" in why
    assert score > 0     # the veto overrides a POSITIVE weighted average


def test_review_angle_registry_weights_and_critical_set_are_predefined():
    """Ticket 20 items 1-3: the CLOSED angle set per level, the predefined weights (an
    accuracy-style angle weighs more than a maintainability-style one), and the critical
    veto set live in one place and are what the aggregation uses."""
    from harness.leaf import (CRITICAL_REVIEW_ANGLES, REVIEW_ANGLES_BY_LEVEL,
                              REVIEW_ANGLE_WEIGHTS, effective_review_angles)

    assert REVIEW_ANGLES_BY_LEVEL["plan"] == (
        "constraint-conflict", "dependency-availability",
        "architecture-consistency", "cost")
    assert REVIEW_ANGLES_BY_LEVEL["implementation"] == (
        "ac-correctness", "contract-compat", "edge-and-error", "regression-risk",
        "input-safety", "maintainability")
    assert REVIEW_ANGLES_BY_LEVEL["integration"] == (
        "end-to-end-behaviour", "interface-alignment", "regression")
    assert REVIEW_ANGLE_WEIGHTS["ac-correctness"] > REVIEW_ANGLE_WEIGHTS["maintainability"]
    assert REVIEW_ANGLE_WEIGHTS["contract-compat"] > REVIEW_ANGLE_WEIGHTS["cost"]
    assert CRITICAL_REVIEW_ANGLES["implementation"] == ("ac-correctness", "contract-compat")
    assert CRITICAL_REVIEW_ANGLES["plan"] == ("constraint-conflict",)
    # an empty declaration defaults to the level's critical angles; out-of-domain angles
    # are dropped; the declared in-domain angles are kept in order.
    assert effective_review_angles((), "implementation") == (
        "ac-correctness", "contract-compat")
    assert effective_review_angles((), "integration") == ("end-to-end-behaviour",)
    assert effective_review_angles(("maintainability",), "implementation") == (
        "maintainability",)
    assert effective_review_angles(("cost",), "implementation") == (
        "ac-correctness", "contract-compat")


def test_driver_review_prompt_is_angle_specific_and_demands_a_grade():
    """Ticket 20 items 1-2: each angle has its own fixed prompt template, and the prompt
    requires a concrete counterexample or an explicit \"found none\" statement plus one of
    the five ordinal grades."""
    from bench.v2_leaf import _review_question

    request = ReviewRequest(goal="g", acs=["a"], original={"pkg/calc.py": "x"},
                            final={"pkg/calc.py": "y"}, angle="edge-and-error")
    question = _review_question(request)
    assert "edge-and-error" in question and "edge cases" in question
    assert "definitely-problematic" in question and "definitely-ok" in question
    assert "counterexample" in question and "found none" in question


def test_repeated_review_angle_is_a_recorded_deviation_not_extra_evidence(tmp_path):
    """Ticket 20 item 1: a repeated angle is deduped and recorded as a deviation; it does
    not buy an extra independent review."""
    spec = dataclasses.replace(
        make_spec(),
        review_angles=("ac-correctness", "ac-correctness", "contract-compat"))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.verification.review_angles == ("ac-correctness", "contract-compat")
    assert len(out.verification.reviews) == 2
    assert "review_angle_repeated" in ledger_kinds()


def test_best_effort_none_reason_claims_unverified(tmp_path):
    """Items 2-3: no test, no reviewer, ``best_effort`` + a substantive written reason
    claims at the ``none+reason`` tier and is recorded as an UNVERIFIED success."""
    spec = dataclasses.replace(
        make_spec(), best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({
        "write_test": [SELF_TEST, SELF_TEST_ALT, impl()],
        "verify": [verify_env(GOOD_REASON)]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.stop_reason == "unverified"
    assert out.signal == "unverified" and out.claimed_basis == "reason"
    assert out.verified is False and out.claim_status == "unverified-success"
    assert out.verification.tier == "none"
    assert out.verification.reason == GOOD_REASON and out.verification.reason_ok is True
    assert out.verification.best_effort is True and out.verification.downgraded is True
    assert "verification_reason_mode" in ledger_kinds()
    assert "leaf_unverified_claim" in ledger_kinds()


def test_best_effort_invalid_reason_blocks_the_claim(tmp_path):
    """Item 2: a terse/off-topic reason is CHECKED, not decorative — no claim, honest stop."""
    spec = dataclasses.replace(
        make_spec(), best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({
        "write_test": [SELF_TEST, SELF_TEST_ALT, impl()],
        "verify": [verify_env("nope")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verified is False and out.claim_status == "unverified-failure"
    assert out.verification.tier == "none"
    assert out.verification.reason == "nope"
    assert out.verification.reason_problem != ""
    assert "verification_claim_blocked" in ledger_kinds()


def test_best_effort_missing_reason_envelope_blocks_the_claim(tmp_path):
    """An ``unable`` verify envelope yields no reason ⇒ the same honest stop."""
    spec = dataclasses.replace(
        make_spec(), best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({
        "write_test": [SELF_TEST, SELF_TEST_ALT, impl()],
        "verify": [{"status": "unable", "comment": "cannot", "unable_reason": "no reason"}]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.reason == "" and out.verification.reason_problem != ""


def test_best_effort_boilerplate_reason_blocks_the_claim(tmp_path):
    """Ticket 20 item 4: a boilerplate ``none+reason`` no longer carries an unverified
    claim (the round-1 hole) --- the claim gate refuses it."""
    spec = dataclasses.replace(
        make_spec(), best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({
        "write_test": [SELF_TEST, SELF_TEST_ALT, impl()],
        "verify": [verify_env("no test can carry verification for this node and no "
                              "independent review is available")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.reason_problem != ""
    assert "verification_claim_blocked" in ledger_kinds()


def test_best_effort_cannot_lower_the_floor_more_than_one_tier(tmp_path):
    """Ticket 20 item 5: best_effort may lower the floor at most one tier, so a ``test``
    requirement can never be satisfied by a ``none+reason`` claim."""
    spec = dataclasses.replace(
        make_spec(), verification_required="test", best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({
        "write_test": [SELF_TEST, SELF_TEST_ALT, impl()],
        "verify": [verify_env("no test can pin the timing-dependent warning in prod")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.tier == "none" and out.verification.verified is False


def test_best_effort_without_a_plan_level_reason_cannot_downgrade(tmp_path):
    """Ticket 20 item 5: best_effort is a PLAN-TIME opt-in that must carry a plan-level
    reason; without one it is not a valid downgrade."""
    spec = dataclasses.replace(make_spec(), verification_required="test",
                               best_effort=True)   # no best_effort_reason
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.tier == "review" and out.verification.downgraded is False


def test_no_reviewer_without_best_effort_keeps_the_conservative_stop(tmp_path):
    """Item 4: ``best_effort`` is the ONLY opt-in to ``reason`` mode; absent it, no
    reviewer keeps the pre-ticket-20 honest stop."""
    spec = make_spec()          # best_effort defaults False
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([0, 0]))

    assert out.claimed is False and out.stop_reason == "no-red-target"
    assert out.verification_basis == "test"     # never entered review/reason mode
    assert out.verification is None             # no code was written


def test_required_test_met_only_by_review_without_best_effort_blocks(tmp_path):
    """Item 4: the declared tier is ENFORCED — a review-tier claim cannot satisfy a
    ``test`` requirement without the recorded best-effort downgrade."""
    spec = dataclasses.replace(make_spec(), verification_required="test")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.tier == "review"
    assert out.verified is True and out.claim_status == "verified-failure"
    assert out.verification.downgraded is False


def test_required_test_with_best_effort_records_the_downgrade(tmp_path):
    """Item 4: with ``best_effort`` the weaker VERIFIED (review) tier is allowed, and the
    downgrade declaration + reason are recorded."""
    spec = dataclasses.replace(
        make_spec(), verification_required="test", best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.verification.required == "test" and out.verification.tier == "review"
    assert out.verified is True and out.claim_status == "verified-success"
    assert out.verification.downgraded is True
    assert "test" in out.verification.downgrade_reason
    assert "verification_downgraded" in ledger_kinds()


def test_run_record_carries_the_verification_record_and_status():
    """Item 3: the persisted record carries the record, the verified flag, the four-way
    claim status, and the separate verified-quadrant."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=True, signal="unverified", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="",
        layers_used=[], stop_reason="unverified", verified=False,
        claim_status="unverified-success",
        verification=VerificationRecord(
            wrote_code=True, tier="none", reason=GOOD_REASON,
            review_angles=("ac-correctness", "contract-compat"), review_score=0,
            required="test", best_effort=True, downgraded=True,
            downgrade_reason="best_effort: the required tier 'test' could not be met"))
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0,
                          verified_quad="unverified-success")
    assert record["verified"] is False
    assert record["claim_status"] == "unverified-success"
    assert record["verification"]["tier"] == "none"
    assert record["verification"]["reason"] == GOOD_REASON
    assert record["verification"]["required"] == "test"
    assert record["verified_quadrant"] == "unverified-success"
    assert record["best_effort_declared"] is True
    assert record["verification_downgrades"] == 1
    # Ticket 20 item 4: a one-node run whose only claim is covenant-weakened is DILUTED,
    # and its weakened claim is excluded from the verified counts.
    assert record["covenant_weakened"] is True and record["covenant_diluted"] is True
    assert record["verification"]["review_angles"] == ("ac-correctness", "contract-compat")
    assert record["review_score"] == 0
    json.dumps(record)


def test_verified_quadrant_separates_unverified_claims():
    """Item 3: the scoring layer can separate the four outcomes."""
    from bench.blind_run import verified_quadrant

    assert verified_quadrant(True, True, True) == "verified-success"
    assert verified_quadrant(True, True, False) == "unverified-success"
    assert verified_quadrant(True, False, True) == "verified-failure"
    assert verified_quadrant(True, False, False) == "unverified-failure"


def test_review_route_is_upgraded_to_the_test_tier_by_an_independent_test(tmp_path):
    """Item 7: the independent test is the strong-evidence route — an approved
    red-on-pristine/green-on-final test upgrades a review-mode claim to the test tier."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([0, 0, 0, 1, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.iv_verdicts[-1].approved is True
    assert out.claimed_basis == "review+independent-test"
    assert out.verification.tier == "test" and out.verified is True
    assert out.claim_status == "verified-success"


# ===========================================================================
# ticket 21: the per-criterion LEDGER, the evidence-backed FAILURE REPORT, and
# a loop that USES the report (targeted rework / the review path)
# ===========================================================================


def test_criterion_ledger_is_built_from_observed_checks_only():
    """Ticket 21 item 1: the ledger classifies each criterion from OBSERVED evidence —
    an untouched named artifact is VIOLATED (``artifact-coverage``), a discriminating
    independent test is SATISFIED (``independent-test``), the own-test node names the
    failing check (``own-test``), and a criterion nothing could carry is UNVERIFIABLE
    with the reason. Model prose is never an input."""
    from harness.leaf import (
        LEDGER_STATES,
        CriterionEvidence,
        RequirementCoverage,
        build_criterion_ledger,
    )

    spec = dataclasses.replace(
        make_spec(), acs=["pkg/calc.py must return 42", "result() is stable",
                          "the widget is blue"])
    coverage = [
        RequirementCoverage(1, spec.acs[0], files=("pkg/calc.py",),
                            missing=("pkg/calc.py",)),
        RequirementCoverage(2, spec.acs[1], symbols=("result",)),
    ]
    iv = (CriterionEvidence(2, "tests/test_independent.py::test_ac2_ok", 1, 1, 1, 0),)
    own = _green_gate("tests/test_leaf_self.py::test_ac1_goal")
    entries = build_criterion_ledger(
        spec, coverage=coverage, own_test_gate=own, iv_criteria=iv, iv_ran=True,
        own_test_discriminating=True)
    by_id = {e.ac_id: e for e in entries}

    assert [e.state for e in entries] == ["violated", "satisfied", "unverifiable"]
    assert all(e.state in LEDGER_STATES for e in entries)
    assert by_id["AC-1"].check == "artifact-coverage"
    assert "untouched" in by_id["AC-1"].evidence
    assert by_id["AC-2"].check == "independent-test"
    assert "pre-run source" in by_id["AC-2"].evidence
    assert by_id["AC-3"].state == "unverifiable"
    assert "no discriminating check" in by_id["AC-3"].evidence


def test_non_claiming_run_emits_a_ledger_that_names_the_violated_check(tmp_path):
    """Ticket 21 items 1-2/4: a run that does NOT claim still carries its evidence — the
    ledger names the VIOLATED criterion, its failing check, and the failing node id, so
    the stop is never just ``attempts``."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 1]))

    assert out.claimed is False
    assert out.evidence_gap is False                 # there IS concrete evidence
    assert out.failure_report is not None
    assert len(out.failure_report.violated) == 1
    rule = out.failure_report.violated[0]
    assert rule.ac_id == "AC-1" and rule.state == "violated"
    assert rule.check == "own-test" and rule.route == "rework"
    assert "test_ac1" in rule.evidence
    assert "criterion_ledger" in ledger_kinds() and "failure_report" in ledger_kinds()


def test_violated_criterion_becomes_the_next_attempts_targeted_context(tmp_path):
    """Ticket 21 item 3: a VIOLATED criterion is the next attempt's TARGETED failure
    context (rework at that requirement) instead of a blind retry."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n")]})
    run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
                  run_tests=ScriptedTests([1, 1, 1]))

    second_implement = model.calls("write_test")[2]
    assert "AC-1 is VIOLATED by own-test" in second_implement.artifacts["failure_output"]


def test_ran_out_without_criterion_evidence_is_an_evidence_gap(tmp_path):
    """Ticket 21 item 2: a run that runs out with NOTHING but unverifiable criteria — no
    check it could point at — is recorded as an EVIDENCE GAP, a distinct visible state."""
    spec = dataclasses.replace(make_spec(),
                               acs=["the widget is blue", "the widget is round"])
    stage(tmp_path, spec.files)
    red = _red_result("tests/test_leaf_self.py::test_goal")   # no AC index in the name
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([red]))

    assert out.claimed is False and out.stop_reason == "calls"
    assert all(e.state == "unverifiable" for e in out.ledger)
    assert out.evidence_gap is True
    assert out.failure_report is not None and out.failure_report.evidence_gap is True
    assert "GIVE-UP WITHOUT EVIDENCE" in out.failure_report.evidence_gap_reason
    assert out.failure_report.routes() == {"AC-1": "unresolved", "AC-2": "unresolved"}
    assert "no discriminating check" in out.ledger[0].evidence


def test_unverifiable_criterion_routes_to_the_review_path(tmp_path):
    """Ticket 21 item 3: an UNVERIFIABLE criterion (one no test can carry) is routed to
    the existing REVIEW path — the owner's "another agent confirms" — and the route each
    criterion took is recorded on the ledger."""
    spec = dataclasses.replace(make_spec(), acs=["the widget is blue"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        review=_passing_review,
        run_tests=ScriptedTests([
            _red_result("tests/test_leaf_self.py::test_goal"),
            _green_result("tests/test_leaf_self.py::test_goal")]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.ledger[0].state == "satisfied"
    assert out.ledger[0].check.startswith("review:")
    assert out.ledger[0].route == "review"
    assert "review_verification" in ledger_kinds()


def test_unverifiable_without_a_reviewer_records_the_unresolved_route(tmp_path):
    """Ticket 21 item 3: with no reviewer to confirm an unverifiable criterion, the route
    is recorded as ``unresolved`` — the honest terminal state, never a silent claim."""
    spec = dataclasses.replace(make_spec(),
                               acs=["the widget is blue", "the widget is round"])
    stage(tmp_path, spec.files)
    red = _red_result("tests/test_leaf_self.py::test_goal")
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([red]))

    assert out.claimed is False
    assert {e.route for e in out.ledger} == {"unresolved"}


def test_no_code_run_that_ran_out_is_an_evidence_gap(tmp_path):
    """Ticket 21 item 2: a run that wrote NO code and ran out has a ledger with no
    concrete row at all — the clearest give-up without evidence."""
    spec = dataclasses.replace(make_spec(),
                               acs=["the widget is blue", "the widget is round"])
    stage(tmp_path, spec.files)
    refused = write_env("tests/test_sneaky.py", "def test_x():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, refused]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=2, deadline_ts=_FAR_FUTURE),
        run_tests=ScriptedTests([
            _red_result("tests/test_leaf_self.py::test_goal")]))

    assert out.claimed is False and out.stop_reason == "calls"
    assert out.verification is None                 # no code was written
    assert all(e.state == "unverifiable" for e in out.ledger)
    assert out.evidence_gap is True
    assert out.failure_report is not None and out.failure_report.evidence_gap is True


def test_evidence_gap_needs_a_ran_out_stop_not_any_non_claim():
    """Ticket 21 item 2: the EVIDENCE-GAP state is reserved for a "ran out" stop with no
    concrete criterion evidence — a no-red-target honest failure is NOT a gap."""
    from harness.leaf import EVIDENCE_GAP_STOPS

    assert "attempts" in EVIDENCE_GAP_STOPS and "ladder" in EVIDENCE_GAP_STOPS
    assert "no-red-target" not in EVIDENCE_GAP_STOPS


def test_run_record_carries_the_ledger_and_failure_report():
    """Ticket 21 items 2/4: the persisted record carries the ledger, the failure report,
    and the distinct evidence-gap flag so both directions are checkable at a glance."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record
    from harness.leaf import CriterionLedgerEntry, FailureReport

    ledger = [CriterionLedgerEntry(ac_id="AC-1", statement="s", state="violated",
                                   check="own-test", evidence="node x fails",
                                   route="rework")]
    report = FailureReport(stop_reason="attempts", criteria=tuple(ledger))
    outcome = LeafOutcome(
        claimed=False, signal="exhausted", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=True, exhaustion_reason="tail",
        layers_used=[], stop_reason="attempts", ledger=ledger, failure_report=report)
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[],
                          skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)

    assert record["ledger"][0]["state"] == "violated"
    assert record["ledger"][0]["check"] == "own-test"
    assert record["ledger"][0]["route"] == "rework"
    assert record["failure_report"]["stop_reason"] == "attempts"
    assert record["failure_report"]["criteria"][0]["evidence"] == "node x fails"
    assert record["evidence_gap"] is False
    json.dumps(record)
