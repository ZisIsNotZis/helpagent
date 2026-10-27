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
    BEST_EVIDENCE_ORDER,
    BEST_EVIDENCE_RANKS,
    LADDER,
    VERIFICATION_TIERS,
    ClaimDecision,
    CriterionLedgerEntry,
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
    WriteDeviation,
    _criterion_unresolved,
    _declared_test_case_problems,
    _evidence_is_grant_calibre,
    _gate_blocks_as_red,
    _judge_incoherence,
    _own_test_collectible,
    _requirement_coverage,
    _restore_deliverable_files,
    _review_request,
    _snapshot_deliverable_files,
    _source_revision_fingerprint,
    _unparseable_source,
    apply_judge_filter,
    apply_review_filter,
    claim_decision,
    deterministic_greens,
    iv_verdict_is_non_discriminating,
    pristine_red_is_discriminating,
    reconciled_check_may_be_dropped,
    reconciliation_ruling,
    escalate,
    evaluate_independent_test,
    run_leaf,
    verification_reason_problem,
)
from harness.leaf import IndependentTestVerdict
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


def make_spec(files=None, grader=(), goal="make result() return 42", *,
              planned_tests=(), planned_reviews=("ac-correctness", "contract-compat"),
              best_effort=False, best_effort_reason="") -> LeafSpec:
    return LeafSpec(
        goal=goal,
        files=files if files is not None else {"pkg/calc.py": "def result():\n    return 0\n"},
        acs=["result() returns 42"],
        interfaces=["result() -> int"],
        grader_paths=tuple(grader),
        # Ticket 22 round 3: every node declares its verification as TWO LISTS. The unit
        # fixtures default to BOTH (reviews planned) exactly as the legacy ``either``
        # policy did, with a concrete reason.
        planned_tests=tuple(planned_tests),
        planned_reviews=tuple(planned_reviews),
        verification_reason="prefer a discriminating own test for the returned value",
        best_effort=best_effort,
        best_effort_reason=best_effort_reason,
    )


def dtc(file="tests/test_leaf_self.py", names=("test_ac1",), ac_id="AC-1"):
    """A DECLARED test point fixture matching the scripted gate's collected node id."""
    return DeclaredTestCase(ac_id, file, tuple(names))


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


def test_self_test_prompt_forbids_asserting_the_reported_symptom(tmp_path):
    """P3a/FIX 1 (T-01): the goal/acceptance lines may DESCRIBE the current broken
    behaviour, so the self-test prompt must tell the model to assert the DESIRED end
    state — the reported symptom is not the requirement. The rule rides BOTH the
    artifacts and the question, survives the green-on-arrival re-ask, and does not remove
    any existing artifact."""
    from harness.leaf import (
        _RETRY_SELF_TEST_QUESTION,
        _SELF_TEST_DESIRED_STATE_RULE,
        _SELF_TEST_QUESTION,
        _retry_self_test_artifacts,
        _self_test_artifacts,
    )

    spec = make_spec()
    arts = _self_test_artifacts(spec)
    assert arts["test_target_rule"] == _SELF_TEST_DESIRED_STATE_RULE
    # the existing artifacts are not removed
    assert {"goal", "acceptance_criteria", "interfaces", "repo_files"} <= set(arts)
    # the rule states both halves: the lines may describe the broken behaviour, and the
    # test must assert the DESIRED end state (never the reported symptom)
    assert "DESCRIBE THE CURRENT BROKEN" in _SELF_TEST_DESIRED_STATE_RULE
    assert "DESIRED end state" in _SELF_TEST_DESIRED_STATE_RULE
    assert "never the reported symptom" in _SELF_TEST_DESIRED_STATE_RULE
    assert _SELF_TEST_DESIRED_STATE_RULE in _SELF_TEST_QUESTION
    assert _SELF_TEST_DESIRED_STATE_RULE in _RETRY_SELF_TEST_QUESTION
    retry = _retry_self_test_artifacts(spec, "tests/test_leaf_self.py",
                                       "def test_goal():\n    assert True\n")
    assert retry["test_target_rule"] == _SELF_TEST_DESIRED_STATE_RULE
    assert "previous_test_content" in retry
    # the rule actually reaches the model call (not merely the helper's return value)
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl("def result():\n    return 1\n")]})
    run_leaf_sync(model, spec, tmp_path, Budget(calls=2, deadline_ts=_FAR_FUTURE),
                  run_tests=ScriptedTests([1]))
    call = model.calls("write_test")[0]
    assert call.artifacts["test_target_rule"] == _SELF_TEST_DESIRED_STATE_RULE
    assert _SELF_TEST_DESIRED_STATE_RULE in call.question


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


def test_implement_writes_to_a_test_or_grader_path_land_as_deviations(tmp_path):
    """docs/6_FLOW.md §6 (P1a): an implementation write to the run's OWN test or a grader path is
    NO LONGER refused — it LANDS and is recorded as a deviation, and the driver restores
    the run's own test and drops the invented grader file before grading."""
    from bench.blind_run import produced_files, restore_deviations

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
                        run_tests=ScriptedTests([1, 1, 1, 0]))

    tested = "tests/test_leaf_self.py"
    # both off-plan writes LANDED and are recorded as deviations ...
    assert (tmp_path / tested).read_text() == "def test_goal():\n    assert False\n"
    assert (tmp_path / "tests/test_chain.py").exists()
    assert any(d.path == tested for d in out.deviations)
    assert any(d.path == "tests/test_chain.py" and "grader-owned" in d.reason
               for d in out.deviations)
    # ... and the driver restores the run's own test and drops the invented grader file.
    restored, restores = restore_deviations(produced_files(tmp_path), out.deviations)
    assert restored[tested] == SELF_TEST["content"]
    assert "tests/test_chain.py" not in restored
    assert any(tested in r and "restored" in r for r in restores)
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


def test_repaired_test_green_under_review_claims_on_the_review(tmp_path):
    """Ticket 23 item 2 (supersedes the ticket-21 check for a REVIEWS-ONLY plan): when the
    plan declares no tests, the run's own test is ADVISORY. A judge-authorized replacement
    that greens on arrival switches the run to review; with NO independent verification to
    agree with, the review itself carries the claim — the advisory test's rewrite can no
    longer block it."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    vacuous = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), vacuous, impl()]})
    out = run_leaf_sync(model, spec, tmp_path,
                        Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_passing_review,
                        run_tests=ScriptedTests([1, 0, 0, 0]))

    assert out.test_rewrites == 1 and out.own_test_mutated is True
    assert out.verification_basis == "review"
    assert spec.planned_tests == ()
    assert out.claimed is True and out.claimed_basis in ("review", "review+independent-test")


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
    """A judge-authorized rewrite is a real attempt: an identical repeat is refused. P3c/
    FIX 2 makes the refusal VISIBLE (``test_repair_unavailable``) and advances the ladder
    instead of crediting the unchanged test (the no-repeat invariant must not be
    bypassed)."""
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

    # the first repair changed the test (credited); the identical repeat did NOT
    assert out.test_rewrites == 1
    assert out.own_test_mutated is True
    assert "test_repair_unavailable" in ledger_kinds()
    assert "implementation" in out.layers_used               # the ladder advanced past L1


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
    # ticket 25: the single-leaf root reason leans toward at least one review angle
    assert spec.planned_reviews == ("ac-correctness", "contract-compat")
    assert "PREFER AT LEAST ONE REVIEW ANGLE" in spec.verification_reason


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
    assert out.stop_reason == "self-test-unverified"
    assert out.state == "uncertain"
    assert out.self_test is None
    assert out.own_test_gate is None
    assert out.own_test_discriminating == []
    assert (tmp_path / "tests" / "test_leaf_self.py").read_text() == SELF_TEST["content"]
    assert "self_test_written" not in ledger_kinds()
    assert "self_test_unverified" in ledger_kinds()


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


def test_empty_acceptance_criteria_cannot_claim_on_any_basis(tmp_path):
    """Ticket 21 round 3 (fix B): with no extracted acceptance criteria NO basis can
    carry the claim — not the run's own test and not a review. An empty criteria list
    would otherwise produce an EMPTY ledger presented as ``verified-success``. The run
    enters review (the existing F2 route) but the claim gate blocks it on every path."""
    spec = dataclasses.replace(make_spec(), acs=[])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_approving_review, run_tests=ScriptedTests([1, 0]))

    assert out.verification_basis == "review"
    assert out.claimed is False
    assert out.stop_reason == "no-acceptance-criteria"
    assert out.ledger == []
    assert "no_acceptance_criteria_claim_blocked" in ledger_kinds()


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


def test_run_written_conftest_lands_is_a_deviation_and_is_restored_before_grading(tmp_path):
    """Attack 3B, ported to docs/6_FLOW.md §6 (P1a): a run-written ``conftest.py`` with a
    ``pytest_sessionfinish`` hook is NO LONGER refused — it lands, is recorded as a
    DEVIATION (test infrastructure), and the driver restores it before grading, so the
    grader never sees the run's hook."""
    from bench.blind_run import produced_files, restore_deviations

    spec = make_spec()
    stage(tmp_path, spec.files)
    hook = ("import pytest\n\n\ndef pytest_sessionfinish(session, exitstatus):\n"
            "    session.exitstatus = 0\n")
    conftest = write_env("conftest.py", hook, comment="make the gate green")
    model = FakeModelRunner({"write_test": [SELF_TEST, conftest, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=5, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 0]))

    assert (tmp_path / "conftest.py").exists()              # landed, never refused
    assert any(d.path == "conftest.py" and "infrastructure" in d.reason
               for d in out.deviations)
    assert any("conftest.py" in a.deviations for a in out.attempts)
    conftest_dev = next(d for d in out.deviations if d.path == "conftest.py")
    restored, restores = restore_deviations(produced_files(tmp_path), out.deviations)
    assert conftest_dev.created and "conftest.py" not in restored
    assert any("conftest.py" in r and "removed" in r for r in restores)
    # the real implementation still drove the gate to green
    assert out.claimed is True and out.signal == "green"


def test_leaf_records_a_module_shadow_source_write_as_a_deviation(tmp_path):
    """Attack 3A, ported to docs/6_FLOW.md §6 (P1a): a run-authored top-level module that shadows an
    interpreter import is no longer refused at write time — it lands and is recorded as a
    DEVIATION (the gate still refuses to RUN with a shadow in the tree, and the driver
    restores it before grading)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    shadow = write_env("json.py", "import sys\nsys.exit(0)\n", comment="make the grader pass")
    model = FakeModelRunner({"write_test": [SELF_TEST, shadow, impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 0]))

    assert (tmp_path / "json.py").exists()                  # landed, never refused
    assert any(d.path == "json.py" and "module-shadow" in d.reason
               for d in out.deviations)
    assert any("json.py" in a.deviations for a in out.attempts)
    assert "write_deviation_recorded" in ledger_kinds()


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


def test_run_record_records_deviations_refusals_and_the_isolation_env():
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=2, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="calls",
        layers_used=[], stop_reason="calls",
        refusals=["json.py: a module-shadow path (would shadow an interpreter import)"],
        deviations=[WriteDeviation("json.py", "a module-shadow path", None)])
    score = ExternalScore(passed=False, exit=1, shadowed=["json.py"],
                          isolation={"PYTHONSAFEPATH": "1",
                                     "PYTEST_ADDOPTS": "-p no:cacheprovider"})

    restore_line = "json.py: removed (a recorded write deviation: a module-shadow path)"
    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0,
                          deviation_restores=[restore_line])

    assert record["refusals"] == outcome.refusals
    # docs/6_FLOW.md §6 (P1a): the deviation is persisted with its snapshotted original (None = the
    # run created it) and the driver's restore is recorded.
    assert record["deviations"] == [
        {"path": "json.py", "reason": "a module-shadow path", "original": None}]
    assert record["deviation_restores"] == [restore_line]
    assert record["grader_shadowed"] == ["json.py"]
    assert record["isolation"]["env"]["PYTHONSAFEPATH"] == "1"
    assert record["isolation"]["grader_env"]["PYTHONSAFEPATH"] == "1"
    assert "no:cacheprovider" in record["isolation"]["pytest_args"]
    json.dumps(record)


# --------------------------------------- round 5: attack 3A end to end (driver)


def test_end_to_end_shadow_module_wrong_fix_is_not_a_true_success(tmp_path, monkeypatch):
    """The driver case an adversarial pass demonstrated, ported to docs/6_FLOW.md §6 (P1a): a wrong
    fix whose only other change is a run-authored ``json.py`` must not reach the
    true-success quadrant. The shadow write LANDS and is recorded as a deviation, then the
    driver restores it before grading, so the real source bug stands and the run reports
    honestly."""
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
    # the shadow write is recorded as a deviation and was restored out of the graded
    # repository before the external grader saw it.
    assert any(d["path"] == "json.py" for d in record["deviations"])
    assert any("json.py" in r for r in record["deviation_restores"])
    assert "json.py" not in record["produced"]


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

def test_t31_untouched_files_are_grader_paths_and_the_write_is_a_deviation(tmp_path):
    """docs/6_FLOW.md §6 (P1a): the corpus ``UNTOUCHED`` files stay in ``grader_paths`` (for the
    deviation record, the coverage exemption, and the external grader's restore), but they
    are NO LONGER a write guard: a write to ``api/__init__.py`` LANDS and is recorded as a
    deviation, then restored before grading."""
    from bench.blind_run import produced_files, restore_deviations
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
                        run_tests=ScriptedTests([1, 1, 0]))

    # the frozen write LANDED (never refused) and is recorded as a deviation ...
    assert (tmp_path / "api" / "__init__.py").read_text() == "# rewritten by the run\n"
    frozen_dev = next(d for d in out.deviations if d.path == "api/__init__.py")
    assert "grader-owned" in frozen_dev.reason and frozen_dev.original == frozen
    assert "implement_refused" not in ledger_kinds()
    # ... and the driver restores the frozen bytes before grading.
    restored, restores = restore_deviations(produced_files(tmp_path), out.deviations)
    assert restored["api/__init__.py"] == frozen
    assert any("api/__init__.py" in r and "restored" in r for r in restores)
    # Ticket 19 E: the request names the client's fetch() (and both call sites) but the
    # run touched only the transport, so per-requirement artifact coverage refuses the
    # claim — the design answer to the T-31 false success.
    assert out.claimed is False
    assert any("fetch" in m for m in out.coverage_missing)


# --------------------------- docs/6_FLOW.md §6 (P1a): allow + record + restore instead of refuse


def test_off_plan_write_lands_is_recorded_and_restores_before_grading(tmp_path):
    """PROBE (a)/(c) at the write seam: a write to a grader/frozen path LANDS and is
    recorded as a deviation carrying its pre-run bytes; ``restore_deviations`` puts those
    bytes back before grading. The mechanical shape refusal still refuses."""
    from bench.blind_run import produced_files, restore_deviations
    from harness.leaf import _write_one

    spec = make_spec(grader=("frozen/keep.py",))
    stage(tmp_path, {**spec.files, "frozen/keep.py": "KEEP = 1\n"})
    baseline: dict[str, str | None] = {}
    deviations: list[WriteDeviation] = []

    wrote, rel, reason, shape, _noop = _write_one(
        "frozen/keep.py", "KEEP = 2\n", spec, tmp_path, None, baseline, deviations)

    assert wrote and rel == "frozen/keep.py" and not shape
    assert reason and "grader-owned" in reason
    assert deviations[0].path == "frozen/keep.py"
    assert deviations[0].original == "KEEP = 1\n" and not deviations[0].created
    assert (tmp_path / "frozen" / "keep.py").read_text() == "KEEP = 2\n"   # landed

    produced, restores = restore_deviations(produced_files(tmp_path), deviations)
    assert produced["frozen/keep.py"] == "KEEP = 1\n"
    assert any("frozen/keep.py" in r and "restored" in r for r in restores)

    # PROBE (c): the mechanical shape refusal still refuses — a directory at the target.
    (tmp_path / "adir").mkdir()
    wrote2, _rel2, _reason2, shape2, _noop2 = _write_one("adir", "X = 1\n", spec, tmp_path,
                                                       None, {}, [])
    assert not wrote2 and shape2


def test_no_op_write_is_flagged_and_gives_the_next_attempt_the_excerpt(tmp_path):
    """P3a/FIX 3 (T-01): emitting bytes that are already on disk changes nothing. The
    write still lands (never refused), is recorded as ``noop_write``, flagged on the
    Attempt, and the next attempt is told plainly that it emitted the bytes already on
    disk (the failure output it also carries says what the test expects)."""
    from harness.leaf import _NOOP_WRITE_EXCERPT

    spec = make_spec()
    stage(tmp_path, spec.files)
    same = impl("def result():\n    return 1\n")
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        same,                       # attempt 1: a real change (baseline is ``return 0``)
        same,                       # attempt 2 (M2 keeps the draft): identical bytes on disk
        impl("def result():\n    return 2\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 1, 1]))

    assert out.attempts[0].noop is False          # attempt 1 changed the revision
    assert out.attempts[1].noop is True           # attempt 2 re-emitted the same bytes
    assert out.attempts[1].verdict == "same"      # a no-op is not material progress
    assert "noop_write" in ledger_kinds()
    # the NEXT attempt (index 3 in the write queue: self-test, attempt1, attempt2, attempt3)
    # carries the explicit no-op excerpt, and it lands ABOVE the test failure output
    next_attempt = model.calls("write_test")[3]
    failure_output = next_attempt.artifacts["failure_output"]
    assert _NOOP_WRITE_EXCERPT in failure_output
    assert failure_output.index(_NOOP_WRITE_EXCERPT) == 0


def test_a_real_write_is_not_flagged_as_a_no_op(tmp_path):
    """P3a/FIX 3: only a byte-identical re-emission is a no-op. A real change carries no
    flag and none of the no-op telemetry or excerpt."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl("def result():\n    return 1\n"),
        impl("def result():\n    return 2\n"),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 1]))

    assert out.attempts and all(a.noop is False for a in out.attempts)
    assert "noop_write" not in ledger_kinds()
    for call in model.calls("implement_write"):
        assert "already on disk" not in call.artifacts.get("failure_output", "")


def test_declared_boundary_violation_lands_and_is_recorded_not_refused(tmp_path):
    """PROBE (b): a write outside the leaf's declared write boundary LANDS (never refused)
    and is recorded as a deviation on the outcome and the attempt."""
    spec = dataclasses.replace(make_spec(), write_boundary=("pkg/calc.py",))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,
        impl(path="pkg/elsewhere.py", content="X = 1\n"),
        impl(),
    ]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 1, 0]))

    assert (tmp_path / "pkg" / "elsewhere.py").read_text() == "X = 1\n"   # landed
    assert any(d.path == "pkg/elsewhere.py" and "boundary" in d.reason
               for d in out.deviations)
    assert any("pkg/elsewhere.py" in a.deviations for a in out.attempts)


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
    assert seen == [{"use_judge": True, "use_iv": True, "use_review": True,
                     "verify_mode": "full"}]

    seen.clear()
    monkeypatch.setattr("sys.argv", ["v2_sweep", "--tasks", "all", "--no-judge", "--no-iv",
                                     "--no-review"])
    assert v2_sweep.main() == 0
    assert seen == [{"use_judge": False, "use_iv": False, "use_review": False,
                     "verify_mode": "full"}]

    # Ticket 25: --verify is exposed and forwarded to the driver.
    assert parser.parse_args([]).verify == "full"
    seen.clear()
    monkeypatch.setattr("sys.argv", ["v2_sweep", "--tasks", "all", "--verify", "raw"])
    assert v2_sweep.main() == 0
    assert seen == [{"use_judge": True, "use_iv": True, "use_review": True,
                     "verify_mode": "raw"}]


def test_verify_mode_selects_the_seams_and_forwards_the_mode(tmp_path, monkeypatch):
    """Ticket 25: ``--verify`` is authoritative over the seam flags. ``run_once`` maps
    each mode to exactly the seams it permits and forwards the mode to ``run_leaf`` so the
    leaf itself can skip the self-test for ``raw``/``review``."""
    from bench import v2_leaf
    from harness.leaf import VERIFICATION_MODES

    assert VERIFICATION_MODES == ("full", "test", "review", "raw")
    parser = v2_leaf.build_parser()
    choices = parser._option_string_actions["--verify"].choices
    assert set(choices) == set(VERIFICATION_MODES)
    assert parser.parse_args(["--task", "x"]).verify == "full"

    task_dir = tmp_path / "T-mode"
    (task_dir / "repo" / "pkg").mkdir(parents=True)
    (task_dir / "repo" / "pkg" / "calc.py").write_text("def result():\n    return 0\n")
    (task_dir / "request.md").write_text("make result() return 42")
    monkeypatch.setattr(v2_leaf, "LlamaServerRunner", lambda server: object())

    captured: dict = {}

    async def fake_run_leaf(model, spec, workdir, budget, **kw):
        captured.update(kw)
        raise RuntimeError("stop after capturing the seams")

    monkeypatch.setattr(v2_leaf, "run_leaf", fake_run_leaf)

    def _seams(mode):
        captured.clear()
        with pytest.raises(RuntimeError):
            v2_leaf.run_once(task_dir, tmp_path / f"o-{mode}", "http://s", 3, 1.0,
                             verify_mode=mode)
        assert captured["verification_mode"] == mode
        return (captured["judge"] is not None, captured["iv"] is not None,
                captured["review"] is not None)

    assert _seams("full") == (True, True, True)
    assert _seams("test") == (True, False, False)
    assert _seams("review") == (False, False, True)
    assert _seams("raw") == (False, False, False)


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


def test_proactive_judge_fires_on_the_first_red_code_changing_attempt(tmp_path):
    """Ticket 19 A, tightened P3a/FIX 2: the judge is consulted when the run's own test
    REPORTS RED on the FIRST red attempt that materially changed the code (K=1) — not only
    when the model volunteers a blame, and no longer after waiting for K=2 reds."""
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

    assert len(seen) == 1                       # exactly once, on the FIRST red
    request = seen[0]
    # the judge carries the evidence the owner direction names: goal, ACs, the run's own
    # test source, the failing output, and the current diff of the changed files.
    assert request.goal == spec.goal
    assert request.acs == spec.acs
    assert "def test_goal" in request.test_content
    assert request.test_path == "tests/test_leaf_self.py"
    assert "FAILED" in request.failure or "AssertionError" in request.failure
    # K=1: the judge sees the FIRST changed revision (return 1), not the second.
    assert request.files["pkg/calc.py"] == "def result():\n    return 1\n"
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
    # Ticket 22 round 2 grant-calibre evidence: the changed artifact AND the acceptance
    # criterion it serves AND the observed behaviour/value (a path alone cannot grant).
    changed = next(iter(request.final), "pkg/calc.py")
    return ReviewVerdict(grade="definitely-ok",
                         evidence=f"{changed}: `result()` now returns 42, satisfying AC-1",
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


def test_grant_calibre_review_evidence_rule():
    """Ticket 22 round 2 fix 1: a review that is about to GRANT must name the acceptance
    criterion it serves AND the specific behaviour/observable/value it verified. Naming a
    changed path (or a bare line reference) is grounding, not substance, and a generic
    endorsement is not evidence."""
    request = ReviewRequest(
        goal="make result() return 42",
        acs=["result() returns 42"],
        original={"pkg/calc.py": "def result():\n    return 0\n"},
        final={"pkg/calc.py": "def result():\n    return 42\n"})
    # the demonstrated attack: a changed path alone is grounding, not substance
    assert _evidence_is_grant_calibre("pkg/calc.py", request) is False
    assert _evidence_is_grant_calibre("pkg/calc.py:1", request) is False
    assert _evidence_is_grant_calibre("looks correct", request) is False
    assert _evidence_is_grant_calibre("implements the goal", request) is False
    # a criterion named with no observation, or a path+line+AC+generic word, still fails
    assert _evidence_is_grant_calibre("AC-1 is satisfied", request) is False
    assert _evidence_is_grant_calibre("pkg/calc.py:1 AC-1 looks correct", request) is False
    # naming the criterion AND the observed behaviour/value grants
    assert _evidence_is_grant_calibre("AC-1: result() now returns 42", request) is True
    assert _evidence_is_grant_calibre(
        "pkg/calc.py returns 42, satisfying AC-1", request) is True
    # an out-of-range criterion id alone is not a reference to the criteria the review saw
    assert _evidence_is_grant_calibre("AC-9: the change is in place", request) is False


def test_grant_calibre_evidence_is_required_for_a_review_backed_claim(tmp_path):
    """Ticket 22 round 2 fix 1, the demonstrated attack as a regression: with the run
    forced to review, a ``definitely-ok`` review whose evidence names ONLY the changed
    path, the run must NOT claim. The SAME run with grant-calibre evidence (criterion +
    observed behaviour) DOES claim, so the rule blocks thin evidence without blocking a
    substantive review.

    docs/6_FLOW.md §1.5 S4 W5 (P1c): the review here is forced by an UNRESOLVABLE criterion while
    the run's own test is GREEN, so the review seam legitimately runs; a red own test
    would end the How as FAIL before any review (see
    ``test_a_red_test_with_an_implementation_wrong_judge_ends_the_how_fail``)."""
    def run(tmp_root, verdict: ReviewVerdict):
        spec = dataclasses.replace(
            make_spec(), acs=["thread the timeout through the result and helper call sites"])
        stage(tmp_root, spec.files)
        model = FakeModelRunner({"write_test": [
            SELF_TEST,                                    # own test RED on arrival
            impl(),                                        # attempt 1: own test GREEN
        ]})
        reviews = ScriptedReview([verdict])
        return run_leaf_sync(
            model, spec, tmp_root, Budget(calls=10, deadline_ts=_FAR_FUTURE),
            review=reviews, run_tests=ScriptedTests([1, 0]))

    # the attack: path-only evidence names no criterion and no observed behaviour
    attacked = run(tmp_path / "thin", ReviewVerdict(grade="definitely-ok",
                                                    evidence="pkg/calc.py"))
    assert attacked.claimed is False
    assert attacked.verification_basis == "review"      # review ran, it just did not grant
    assert attacked.review_verdict is not None and attacked.review_verdict.approved
    assert "review_not_grant_calibre" in ledger_kinds()

    # the positive control: criterion + observed behaviour/value grants
    granted = run(tmp_path / "calibre",
                  ReviewVerdict(grade="definitely-ok",
                                evidence="AC-1: result() now returns 42"))
    assert granted.claimed is True and granted.claimed_basis == "review"
    assert granted.verification_basis == "review"


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


def test_repaired_test_that_cannot_discriminate_still_switches_to_review(tmp_path):
    """Ticket 23 item 2 (supersedes the ticket-21 check for a REVIEWS-ONLY plan): the judge
    says the test is wrong and the bounded repair still cannot produce a discriminating test
    (it greens on arrival); review becomes mandatory and, because the plan declared NO
    tests, the advisory test's rewrite does not block the review-carried claim."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_approving_review,
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.verification_basis == "review"
    assert out.test_rewrites == 1
    assert spec.planned_tests == ()
    assert out.claimed is True and out.claimed_basis in ("review", "review+independent-test")


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
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_ac1",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.test_case_problems == []


def test_declared_test_case_missing_is_a_repairable_failure_and_blocks_the_claim(tmp_path):
    spec = dataclasses.replace(
        make_spec(),
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
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


def test_green_on_arrival_judge_test_wrong_rewrites_instead_of_dropping(tmp_path):
    """P3a/FIX 4: a test that is GREEN on the pristine source is the suspect. When the
    judge says the TEST is wrong, the existing bounded repair REWRITES it against the
    desired end state (instead of the test being dropped and the run switching to
    review). The rewritten test is re-proved RED on arrival and kept as the target."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_alt.py",
                         "def test_goal():\n    assert result() == 42\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, repaired, impl()]})

    def judge(request: JudgeRequest) -> JudgeVerdict:
        # the defect names the retry test's failing assertion, so the deterministic filter
        # credits ``test_wrong`` (a bare blame would be coerced).
        return JudgeVerdict(test_wrong=True,
                            defect="test_goal asserts result() == 0, which pins the wrong value",
                            reason="the test asserts a value the goal does not ask for")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([0, 0, 1, 0]))

    assert out.test_rewrites == 1 and out.own_test_mutated is True
    assert "test_rewritten" in ledger_kinds()
    # the test was REWRITTEN, not dropped: the green-on-arrival drop path did not run
    assert out.stop_reason != "no-red-target"
    assert (tmp_path / "tests/test_leaf_alt.py").read_text() == repaired["content"]
    assert out.judge_verdicts and out.judge_verdicts[0].test_wrong


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
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
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


def test_blocked_declared_test_case_repair_does_not_claim_on_the_review_alone(tmp_path):
    """FIX 1, tightened ticket 21 round 5 (fix 2): a declared test case that survives the
    bounded repair and cannot carry the claim enters the REVIEW path — but because the
    repair REPLACED the run's own test, a grounded review pass ALONE can no longer claim
    (the replacement is red-on-pristine at best). The green is recorded as
    ``green-after-test-rewrite`` with the rewrite accounted, and the declared-case defect
    stays recorded."""
    spec = dataclasses.replace(
        make_spec(),
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl(), SELF_TEST]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
        review=_approving_review, run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "green-after-test-rewrite"
    assert out.test_rewrites == 1 and out.own_test_mutated is True
    assert out.test_case_problems and "test_goal" in out.test_case_problems[0]
    assert "review_verification" in ledger_kinds() and "review_verdict" in ledger_kinds()
    assert "leaf_green_after_test_rewrite" in ledger_kinds()


def _declared_case_repair_runner(tmp_path, *, pristine_green: bool = False,
                                 repaired_node="tests/test_leaf_self.py::test_ac1"):
    """A run_tests seam for the declared-case REPAIR accounting tests.

    On the workdir the own test is red on arrival (``test_goal``), then green once the
    repair has replaced it with the DECLARED ``test_ac1`` node; in the private pristine
    copy (``_repaired_test_is_red_on_pristine``) the replacement is red (a real
    discriminator) unless ``pristine_green`` makes it a placeholder."""
    state = {"n": 0}

    def runner(workdir, node_ids=None):
        if Path(workdir) != tmp_path:
            return (_green_result(repaired_node) if pristine_green
                    else _red_result(repaired_node))
        state["n"] += 1
        if state["n"] == 1:
            return _red_result("tests/test_leaf_self.py::test_goal")
        content = (Path(workdir) / "tests/test_leaf_self.py").read_text()
        if "test_ac1" in content:
            return _green_result(repaired_node)
        return _green_result("tests/test_leaf_self.py::test_goal")

    return runner


def test_declared_case_repair_is_accounted_exactly_like_a_test_rewrite(tmp_path):
    """Ticket 21 round 5 (fix 2): a declared-case repair REPLACES the run's own test file,
    so it must be accounted exactly like the judge-path repair — ``test_rewrites`` counts
    it (and therefore ``own_test_mutated`` is true), and the replaced test can never be
    the SOLE basis of a claim: the green is ``green-after-test-rewrite`` with no claim.
    The ledger stays honest (the criterion is not satisfied by the replacement)."""
    spec = dataclasses.replace(
        make_spec(),
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_ac1",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,                                        # test_goal, not the declared test_ac1
        impl(),                                           # green, declared case still missing
        write_env("tests/test_leaf_self.py",              # the declared-case repair
                  "def test_ac1():\n    assert result() == 42\n"),
    ]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        run_tests=_declared_case_repair_runner(tmp_path))

    assert out.claimed is False
    assert out.stop_reason == "green-after-test-rewrite"
    assert out.test_rewrites == 1 and out.own_test_mutated is True
    assert out.test_case_problems == []
    assert "test_case_repair" in ledger_kinds()
    assert "leaf_green_after_test_rewrite" in ledger_kinds()
    # the replaced test cannot carry the criterion: the ledger does not claim it satisfied
    assert [e.state for e in out.ledger] != ["satisfied"]


def test_declared_case_repair_green_on_pristine_is_still_rejected(tmp_path):
    """Ticket 19 D kept by round 5 (fix 2): the repaired own test must still DISCRIMINATE —
    RED on the PRISTINE source. A replacement that also passes there is recorded as a
    non-discriminating repaired test and cannot claim."""
    spec = dataclasses.replace(
        make_spec(),
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_ac1",)),))
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl(),
        write_env("tests/test_leaf_self.py",
                  "def test_ac1():\n    assert result() == 42\n"),
    ]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        run_tests=_declared_case_repair_runner(tmp_path, pristine_green=True))

    assert out.claimed is False
    assert any("still PASSES on the pristine source" in p for p in out.test_case_problems)
    assert "test_cases_missing" in ledger_kinds()


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
        planned_tests=(DeclaredTestCase("AC-1", "tests/test_leaf_self.py", ("test_goal",)),))
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
    # Ticket 22 round 2 grant-calibre evidence (see ``_approving_review``).
    changed = next(iter(request.final), "pkg/calc.py")
    return ReviewVerdict(
        grade="definitely-ok",
        evidence=f"{changed}: `result()` now returns 42, satisfying AC-1")


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
    assert out.verification.planned_reviews == ("ac-correctness", "contract-compat")
    assert len(out.verification.reviews) == 2
    assert out.verification.review_score == 12     # 3*(+2) + 3*(+2)
    assert out.verification.reviews[0].evidence


def test_review_angles_run_one_call_per_declared_angle_and_combine_by_weight(tmp_path):
    """Ticket 20 items 1-3: ``planned_reviews`` runs ONE fresh call per angle (a different
    angle each), and the weighted score decides. A negative grade is an ACTION ITEM: the
    node keeps working instead of claiming."""
    from harness.leaf import combine_review_verdicts, weighted_review_score

    spec = dataclasses.replace(
        make_spec(),
        planned_reviews=("ac-correctness", "contract-compat", "maintainability"))
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
    assert out.verification.planned_reviews == (
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
        planned_reviews=("ac-correctness", "ac-correctness", "contract-compat"))
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
        make_spec(), planned_tests=(dtc(),), planned_reviews=(),
        verification_reason="an exact-value unit test pins the result", best_effort=True,
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
    spec = dataclasses.replace(make_spec(), planned_tests=(dtc(),),
                               verification_reason="an exact-value unit test pins the result",
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
    spec = dataclasses.replace(
        make_spec(), planned_tests=(dtc(),),
        verification_reason="an exact-value unit test pins the result")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False and out.stop_reason == "verification-required"
    assert out.verification.tier == "review"
    assert out.verified is True and out.claim_status == "verified-failure"
    assert out.verification.downgraded is False
    # Ticket 22 round 3: no JUDGE-confirmed ``test_wrong`` with a repairable test means
    # no PLAN UPDATE — the test plan stands and nothing claims on the review alone.
    assert out.plan_updates == []
    assert out.verification.planned_tests and out.verification.planned_reviews


def test_required_test_with_best_effort_records_the_downgrade(tmp_path):
    """Item 4: with ``best_effort`` the weaker VERIFIED (review) tier is allowed, and the
    downgrade declaration + reason are recorded."""
    spec = dataclasses.replace(
        make_spec(), planned_tests=(dtc(),),
        verification_reason="an exact-value unit test pins the result", best_effort=True,
        best_effort_reason="the timing is only injected in production")
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.verification_basis == "review"
    assert out.verification.planned_tests and out.verification.tier == "review"
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
        planned_tests=[dtc()],
        planned_reviews=["ac-correctness", "contract-compat"],
        verification_reason="an exact-value unit test pins the result",
        verification=VerificationRecord(
            wrote_code=True, tier="none", reason=GOOD_REASON,
            planned_tests=(dtc(),), planned_reviews=("ac-correctness", "contract-compat"),
            review_angles=("ac-correctness", "contract-compat"), review_score=0,
            verification_reason="an exact-value unit test pins the result",
            best_effort=True, downgraded=True,
            downgrade_reason="best_effort: the planned route 'test' could not be met"))
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0,
                          verified_quad="unverified-success")
    assert record["verified"] is False
    assert record["claim_status"] == "unverified-success"
    assert record["verification"]["tier"] == "none"
    assert record["verification"]["reason"] == GOOD_REASON
    assert record["verification"]["planned_tests"][0]["ac_id"] == "AC-1"
    assert record["verified_quadrant"] == "unverified-success"
    assert record["best_effort_declared"] is True
    assert record["verification_downgrades"] == 1
    # Ticket 20 item 4: a one-node run whose only claim is covenant-weakened is DILUTED,
    # and its weakened claim is excluded from the verified counts.
    assert record["covenant_weakened"] is True and record["covenant_diluted"] is True
    assert record["verification"]["review_angles"] == ("ac-correctness", "contract-compat")
    assert record["review_score"] == 0
    # Ticket 22 round 3: the plan's two LISTS and the reason are on the run record too,
    # so the spec-time decision is never implicit.
    assert record["planned_reviews"] == ["ac-correctness", "contract-compat"]
    assert record["planned_tests"] and record["planned_tests"][0]["ac_id"] == "AC-1"
    assert record["plan_updates"] == []
    assert record["verification_disagreement"] == ""
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


# ===========================================================================
# ticket 21 round 2: the run's OWN verification may be wrong, so the INDEPENDENT one is
# consulted at exhaustion; the own test may not outvote it; coverage is a hard block.
# ===========================================================================

#: A run test that pins the SYMPTOM (asserts ``result() == 3``) while the goal is
#: ``result() == 42``: the correct fix can never make it green. This is the T-02
#: mechanism (asserting the buggy value makes a correct fix unwinnable from inside).
SYMPTOM_TEST = write_env("tests/test_leaf_self.py",
                         "def test_ac1():\n    assert result() == 3\n")

#: A WEAK independent test: red on the pristine source (``result() == 0``) and green on a
#: WRONG fix (``result() == 100``). Paired with the run's own CORRECT test it reproduces the
#: proven wrong-green route (ticket 21 round 4).
WEAK_IV = iv_candidate(
    content="from pkg.calc import result\n\n\ndef test_ac1_weak():\n    assert result() != 0\n")

#: An independent test whose assertion TEXT is identical to ``SYMPTOM_TEST``'s, so the two
#: verifier records cannot be told apart by their assertions (the round-4 fix-2 case).
SAME_ASSERT_IV = iv_candidate(
    content="from pkg.calc import result\n\n\ndef test_ac1_goal():\n    assert result() == 3\n")


def test_exhaustion_rubber_stamp_judge_cannot_confirm_a_claim(tmp_path):
    """Ticket 21 round 4 (fix 1) — the REMOVED collusion route.

    An independent verifier PROVED that a judge which rubber-stamps ``test_wrong`` (naming
    the test anchor, which the deterministic filter accepts) used to authorise a claim at
    exhaustion while the run's own CORRECT test was red on the wrong fix. AGREEMENT is now
    required, so no judge can authorise anything: the run records the verifier CONFLICT and
    does NOT claim. There is no exhaustion judge consultation and no ``own_test_invalid``
    record any more."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")   # the wrong green the weak IV accepts
    model = FakeModelRunner({"write_test": [SELF_TEST] + [wrong] * 8})

    def rubber_stamp(request):
        # The loop's PROACTIVE trigger consults the judge first (round 4 removed the
        # EXHAUSTION consultation, so this rubber stamp is never reached again).
        if not rubber_stamp.seen:
            rubber_stamp.seen = True
            return JudgeVerdict(attribution="implementation",
                                defect="the source is wrong; result() should return 42")
        return JudgeVerdict(attribution="tests", raw="tests",
                            defect="test_ac1 asserts result() == 42, which is wrong")
    rubber_stamp.seen = False

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=rubber_stamp, iv=lambda request: WEAK_IV,
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 0]))

    assert out.claimed is False
    assert out.stop_reason == "verifier-conflict"
    assert out.own_test_conflict is True
    assert out.test_rewrites == 0                  # the judge never got to rewrite
    assert "judge_verdict_at_exhaustion" not in ledger_kinds()
    assert not hasattr(out, "own_test_invalid")
    assert out.failure_report is not None and out.failure_report.violated


def test_exhaustion_conflict_between_two_imperfect_verifiers_does_not_claim(tmp_path):
    """Ticket 21 rounds 3-4 (the closed wrong-green route): the independent test is RED on
    pristine and GREEN on a WRONG fix (``result() -> 100``) while the run's own TRUE test
    stays red. The two imperfect verifiers DISAGREE at the same revision, so the node
    records the conflict and does NOT claim. The conflict names ONLY the assertions that
    really failed on the final revision, against the independent test's assertions.
    """
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")  # the WRONG fix the weak IV accepts
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 0]))

    assert out.claimed is False
    assert out.claimed_basis == "own-test"
    assert out.stop_reason == "verifier-conflict"
    assert out.own_test_conflict is True
    # the conflict names BOTH expectations and the shared revision
    assert "assert result() == 3" in out.own_test_conflict_reason
    assert "assert result() == 42" in out.own_test_conflict_reason
    assert "same revision" in out.own_test_conflict_reason
    assert "cannot characterise" not in out.own_test_conflict_reason
    assert "verifier_conflict" in ledger_kinds()
    # the ledger row names the disagreement, not a bare own-test red
    assert out.ledger[0].state == "violated"
    assert out.ledger[0].check == "verifier-conflict"
    assert out.failure_report is not None and out.failure_report.violated


def test_conflict_text_says_cannot_characterise_when_the_assertions_are_identical(tmp_path):
    """Ticket 21 round 4 (fix 2), record fidelity: when the run's own FAILING assertion and
    the independent test's assertion carry the SAME text, the conflict must NOT invent a
    disagreement — it must say ``cannot characterise the difference``."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: SAME_ASSERT_IV,
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 0]))

    assert out.claimed is False and out.stop_reason == "verifier-conflict"
    assert "cannot characterise the difference" in out.own_test_conflict_reason


def test_exhaustion_review_does_not_run_over_a_red_own_test(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1, §11 H3 (P1c): a test FAIL ends the How as FAIL and the
    review does NOT run. This REVERSES the old ticket-22 path where the graded review
    outranked a red own test: at exhaustion the run's own test is RED on the final
    revision, so the approving reviewer is never consulted, nothing is claimed, and the
    leaf's state is FAIL (never ``uncertain``).

    ``--no-iv`` route: no independent producer."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")     # the wrong fix the reviewer would accept
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    reviews = ScriptedReview([_passing_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=16, deadline_ts=_FAR_FUTURE),
                        review=reviews,
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 0]))

    assert out.claimed is False
    assert out.claimed_basis != "review"
    assert out.stop_reason == "attempts"
    assert out.state == "fail"                        # a FAIL test is FAIL, never uncertain
    assert reviews.calls == 0                          # the review never ran
    assert out.review_verdicts == []
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_exhaustion_review_does_not_run_over_a_red_test_with_a_vacuous_iv(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1, §11 H3 (P1c): even when the independent test is vacuous
    (``independent-test-not-red`` after its one repair), the run's OWN test is RED on the
    final revision, so the review does NOT run and nothing is claimed; the leaf's state is
    FAIL. The old ticket-22 'the review decides over the red test' path is gone."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    vacuous = iv_candidate(path="tests/test_vacuous.py",
                           content="def test_goal():\n    assert True\n")
    reviews = ScriptedReview([_passing_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=18, deadline_ts=_FAR_FUTURE),
                        review=reviews, iv=lambda request: vacuous,
                        run_tests=ScriptedTests([1, 1, 1, 1, 0, 0]))

    assert out.claimed is False
    assert out.claimed_basis != "review"
    assert out.state == "fail"
    assert reviews.calls == 0
    assert out.review_verdicts == []
    assert out.iv_verdicts and out.iv_verdicts[-1].approved is False
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_exhaustion_review_with_no_own_test_still_claims(tmp_path):
    """Ticket 21 round 5 (fix 1), the legitimate case: the agreement rule permits a
    review-based claim when the run's own test is ABSENT (never written). With no own
    test, the loop exhausts and an approving review DOES carry the claim on the review
    basis (``leaf_green_at_exhaustion``)."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    # both self-tests are green on arrival -> no red target -> review mode, NO own test.
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT] + [impl()] * 12})

    def review(request: ReviewRequest) -> ReviewVerdict:
        # reject on the normal path, approve only the exhaustion consultation
        if "exhausted" in request.reason:
            return _passing_review(request)
        return ReviewVerdict(grade="probably-problematic", detail="not yet")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=60, deadline_ts=_FAR_FUTURE),
                        review=review, run_tests=ScriptedTests([0, 0] + [1] * 30))

    assert out.self_test is None and out.test_rewrites == 0
    assert out.claimed is True and out.stop_reason == "green"
    assert out.claimed_basis == "review"
    assert out.own_test_conflict is False
    assert "leaf_green_at_exhaustion" in ledger_kinds()


def test_exhaustion_judge_that_does_not_confirm_keeps_the_own_test_valid(tmp_path):
    """Ticket 21 rounds 3-4: a judge that does NOT confirm ``test_wrong`` leaves the own
    test VALID, so the run records the conflict rather than branding a correct test
    invalid — and (round 4) a judge that DOES rubber-stamp it changes nothing."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    wrong = impl("def result():\n    return 100\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})

    def judge_blames_code(request):
        return JudgeVerdict(attribution="implementation",
                            defect="the source is wrong; result() should return 42")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_code,
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 0]))

    assert out.claimed is False
    assert out.own_test_conflict is True
    assert out.stop_reason == "verifier-conflict"


def test_exhaustion_with_zero_criteria_never_claims_on_an_empty_ledger(tmp_path):
    """Ticket 21 round 3 (fix B): with zero acceptance criteria ``final_verification``
    used to claim ``verified-success`` on an EMPTY ledger while the normal path hard-
    blocked. No claim with zero criteria on ANY path, and no empty ledger for a claim."""
    spec = dataclasses.replace(make_spec(), acs=[])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [impl()] * 8})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1] * 6))

    assert out.claimed is False
    assert out.ledger == []
    assert "no_acceptance_criteria_claim_blocked" in ledger_kinds()


def test_exhaustion_independent_verification_failure_marks_the_criterion_violated(tmp_path):
    """Ticket 21 round 2 (fix 1): when the independent verification FAILS on the final
    code, the node stays unclaimed and the ledger names the violated criterion with the
    independent evidence — never a bare ``attempts`` stop."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    wrong = impl("def result():\n    return 1\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 1]))

    assert out.claimed is False
    assert out.own_test_conflict is False
    assert out.iv_verdicts and out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert out.ledger[0].state == "violated"
    assert out.ledger[0].check == "independent-test"
    assert out.failure_report is not None and out.failure_report.violated


def test_judge_request_carries_the_failing_assertion_lines(tmp_path):
    """Ticket 21 round 2 (fix 2): the judge is given the run's failing ASSERTION lines
    explicitly (not only inside the full test and the failure excerpt), so a
    symptom-pinning expectation can be recognized."""
    from harness.leaf import _judge_request

    spec = make_spec()
    stage(tmp_path, {"pkg/calc.py": spec.files["pkg/calc.py"],
                     "tests/test_leaf_self.py":
                         "def test_goal():\n    assert result() == 3\n"})
    request = _judge_request(
        spec, tmp_path, "tests/test_leaf_self.py",
        ["FAILED tests/test_leaf_self.py::test_goal",
         "E   AssertionError: assert 42 == 3"],
        impl(), {})

    assert request.failing_assertions == ("assert result() == 3",)
    from bench.v2_leaf import _judge_question
    assert "assert result() == 3" in _judge_question(request)


def test_failing_assertion_lines_fall_back_to_every_assert():
    from harness.leaf import _failing_assertion_lines

    assert _failing_assertion_lines("def test_a():\n    assert x == 1\n",
                                    "no failing id here") == ("assert x == 1",)
    assert _failing_assertion_lines("", "FAILED t.py::test_a") == ()


def test_failed_assertion_lines_cite_only_the_failing_functions_asserts():
    """Ticket 21 round 4 (fix 2): the conflict record cites ONLY the asserts of the test
    functions that actually FAILED in the gate report — never a passing assertion — and
    never falls back to every assert in the file."""
    from harness.leaf import _failed_assertion_lines

    content = ("def test_a():\n    assert x == 1\n    assert y == 2\n"
               "def test_b():\n    assert z == 3\n")
    gate = _gate_report("tests/t.py", failed=("tests/t.py::test_a",))
    assert _failed_assertion_lines(content, gate) == ("assert x == 1", "assert y == 2")
    # a passing function's asserts are never cited
    assert "assert z == 3" not in _failed_assertion_lines(content, gate)
    # no failing node ids → no asserts at all (no silent all-asserts fallback)
    assert _failed_assertion_lines(content, _gate_report("tests/t.py")) == ()


def test_coverage_miss_blocks_an_ok_review_verdict(tmp_path):
    """Ticket 21 round 2 (fix 3): a non-empty requirement-coverage miss is a HARD block,
    not advice. A review that says ``ok`` cannot carry a claim while a criterion names a
    file the final diff never touches (the T-31 false-success route)."""
    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/other.py": "def helper():\n    return 1\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42", "pkg/other.py exposes helper"],
                    interfaces=[],
                    planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    # SELF_TEST is green on arrival -> the bounded re-ask also green -> REVIEW is the
    # mandatory basis; the run only ever writes pkg/calc.py, never pkg/other.py.
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]
                                          + [impl()] * 12})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=30, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False
    assert out.coverage_missing
    assert any("pkg/other.py" in m for m in out.coverage_missing)
    assert "review_coverage_blocked" in ledger_kinds()


# ===========================================================================
# ticket 21 round 6: ONE claim gate, enforced STRUCTURALLY. Rounds 2-5 each guarded
# a single branch and the next verifier found the same wrong green in a sibling branch
# (the last: the MAIN-PATH review route claimed while the run's own test was RED).
# ===========================================================================

def test_main_path_review_does_not_run_over_a_red_own_test(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1, §11 H3 (P1c): the MAIN-PATH review route no longer runs
    once the run's own test is RED on the final revision. Sequence (the old ticket-22
    scenario): attempt 1 makes the own test green but a criterion resolves to no artifact,
    so review is forced and REJECTS; attempt 2 writes a wrong fix (own test RED) the
    reviewer would approve — but that second review is NEVER consulted. Nothing is claimed
    and the leaf's state is FAIL; the first (legitimate) review stayed on the record."""
    spec = dataclasses.replace(
        make_spec(), acs=["thread the timeout through the result and helper call sites"])
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST,                                    # own test RED on arrival
        impl("def result():\n    return 1\n"),        # attempt 1: own test green, review rejects
        impl("def result():\n    return 7\n"),        # attempt 2: wrong fix, own test RED
    ]})
    reviews = ScriptedReview([
        ReviewVerdict(grade="probably-problematic",
                      evidence="pkg/calc.py:1 does not thread the timeout"),
        _approving_review,
    ])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=18, deadline_ts=_FAR_FUTURE),
                        review=reviews, run_tests=ScriptedTests([1, 0, 1, 1, 1, 1]))

    assert out.claimed is False
    assert out.state == "fail"
    assert out.verification_basis == "review"          # attempt 1 legitimately entered review
    # the red test stopped the seam: attempt 1's two-angle review is the ONLY review run
    assert reviews.calls == 2
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_test_plan_update_switches_to_review_and_claims(tmp_path):
    """Ticket 22 round 3: with BOTH lists planned, when the judge confirms ``test_wrong``
    (named defect) and the bounded repair cannot discriminate, the node records ONE PLAN
    UPDATE that DROPS the test plan and relies on the PLANNED reviews; the review then
    carries the claim."""
    spec = dataclasses.replace(
        make_spec(), planned_tests=(dtc(),),
        planned_reviews=("ac-correctness", "contract-compat"),
        verification_reason="an exact-value unit test pins the result")
    stage(tmp_path, spec.files)
    vacuous = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), vacuous, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_passing_review,
                        run_tests=ScriptedTests([1, 0, 0, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.claimed_basis == "review"
    assert out.test_rewrites == 1
    assert len(out.plan_updates) == 1
    update = out.plan_updates[0]
    assert update.old_policy == "test" and update.new_policy == "review"
    assert update.test_rewrites == 1
    assert update.dropped_tests is True and update.relies_on_reviews is True
    assert "test_goal asserts result() == 42" in update.judge_reason
    assert "plan_update" in ledger_kinds()
    assert out.verification.planned_tests and out.verification.planned_reviews
    assert out.verification_policy == "either"
    assert len(out.verification.plan_updates) == 1


def test_plan_update_is_recorded_only_when_a_test_plan_is_dropped(tmp_path):
    """Ticket 22 round 3: the PLAN UPDATE is recorded when the node DROPS a test plan (a
    node that planned no tests has nothing to drop), and its new route is ``review`` only
    when reviews were planned."""
    spec = dataclasses.replace(make_spec(), planned_tests=(),
                               planned_reviews=("ac-correctness", "contract-compat"),
                               verification_reason="no test can pin the timing, a review must")
    stage(tmp_path, spec.files)
    vacuous = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), vacuous, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_passing_review,
                        run_tests=ScriptedTests([1, 0, 0, 0]))

    assert out.verification_basis == "review"
    assert out.plan_updates == []           # no test plan -> nothing to drop
    assert out.verification_policy == "review"


def test_plan_update_never_refires(tmp_path):
    """Ticket 22 item 2: the PLAN UPDATE is recorded AT MOST ONCE per node, even when the
    judge confirms ``test_wrong`` again after the switch (the effective policy is no
    longer ``test``, so a second update is refused)."""
    spec = dataclasses.replace(
        make_spec(), planned_tests=(dtc(),),
        planned_reviews=("ac-correctness", "contract-compat"),
        verification_reason="an exact-value unit test pins the result")
    stage(tmp_path, spec.files)
    vacuous = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    # attempt 1 repairs the test (vacuous, greens on arrival -> update #1); attempt 2 is a
    # ``blocked`` envelope (another judge-confirmed test_wrong, but no test to repair);
    # attempt 3 lands the fix and the review carries the claim.
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), vacuous, blocked(),
                                             impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=18, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_passing_review,
                        run_tests=ScriptedTests([1, 0, 0, 0, 0]))

    assert len(out.plan_updates) == 1
    assert out.plan_updates[0].old_policy == "test"
    assert out.plan_updates[0].new_policy == "review"
    assert sum(1 for kind in ledger_kinds() if kind == "plan_update") == 1


def _gate_ledger() -> list[CriterionLedgerEntry]:
    return [CriterionLedgerEntry(ac_id="AC-1", statement="result() returns 42",
                                 state="satisfied", check="own-test",
                                 evidence="tests/t.py::test_goal passes")]


def _grounded_review() -> ReviewVerdict:
    return ReviewVerdict(angle="ac-correctness", grade="definitely-ok",
                         evidence="pkg/calc.py:1 returns 42 for AC-1")


def test_claim_gate_plan_update_lets_the_review_carry_a_rewritten_test():
    """Ticket 22 item 2: a recorded PLAN UPDATE (test -> review) means the rewritten test
    was GIVEN UP, so the review may carry the claim without the independent verification
    agreeing. Without the recorded update the rewrite still needs that agreement."""
    base = {
        "route": "review", "criteria_count": 1, "ledger": _gate_ledger(),
        "own_test": None, "own_test_green": False, "test_rewrites": 1,
        "iv_approved": False, "review_approved": True,
        "review_verdicts": (_grounded_review(),), "verification_basis": "review",
        "tier_allowed": True,
    }
    without = claim_decision(**base)
    assert without.claimed is False and without.blocker == "green-after-test-rewrite"
    updated = claim_decision(**base, plan_updated=True)
    assert updated.claimed is True and updated.basis == "review"


def test_claim_gate_enforces_every_rule_directly():
    """The ONE gate's rule list, pinned directly on :func:`claim_decision` (the code paths
    that call it are pinned elsewhere)."""
    base = {
        "criteria_count": 1, "ledger": _gate_ledger(), "own_test": "tests/t.py",
        "own_test_green": True, "test_rewrites": 0, "iv_approved": False,
        "iv_red_on_final": False, "review_approved": False, "review_verdicts": (),
        "coverage_missing": (), "test_case_problems": (),
        "verification_basis": "test", "tier_allowed": True,
    }

    # rule 1: no claim with zero acceptance criteria
    assert claim_decision(route="own-test", **{**base, "criteria_count": 0}).claimed is False
    # rule 2: no claim with an empty ledger
    assert claim_decision(route="own-test", **{**base, "ledger": ()}).claimed is False
    # rule 3: no claim when the coverage check missed a named artifact
    assert claim_decision(route="own-test",
                          **{**base, "coverage_missing": ["'AC' names x"]}).claimed is False
    # the legitimate own-test claim
    granted = claim_decision(route="own-test", **base)
    assert isinstance(granted, ClaimDecision)
    assert granted.claimed is True and granted.basis == "own-test"
    # rule 4: a RED own test on the FINAL revision can NEVER claim on the own-test route
    assert claim_decision(route="own-test",
                          **{**base, "own_test_green": False}).claimed is False
    # ... and when a TEST passed it with NO review to outrank it, that is a CONFLICT
    conflict = claim_decision(
        route="independent-test",
        **{**base, "own_test_green": False, "iv_approved": True,
           "conflict_detail": "own red vs iv green", "verification_basis": "reason"})
    assert conflict.claimed is False and conflict.conflict is True
    assert conflict.blocker == "verifier-conflict"
    assert conflict.detail == "own red vs iv green"
    # rule 4 (ticket 22 item 3): on the REVIEW route the review DECIDES — an approving
    # review carries the claim even with a red own test, and records the disagreement
    # while keeping the ``review`` basis label.
    review_decides = claim_decision(
        route="review",
        **{**base, "own_test_green": False, "review_approved": True,
           "review_verdicts": (_grounded_review(),), "conflict_detail": "own red vs review",
           "verification_basis": "review"})
    assert review_decides.claimed is True and review_decides.basis == "review"
    assert review_decides.disagreement == "own red vs review"
    # ... and a rejecting review blocks even a GREEN own test (review outranks in both
    # directions), recording the disagreement.
    review_rejects = claim_decision(
        route="review",
        **{**base, "own_test_green": True, "review_approved": False,
           "verification_basis": "review"})
    assert review_rejects.claimed is False
    assert review_rejects.blocker == "review-not-approved"
    assert "GREEN" in review_rejects.disagreement
    # rule 5: a review carries a claim ONLY when the own test is ABSENT (never written)...
    absent = claim_decision(
        route="review",
        **{**base, "own_test": None, "own_test_green": False, "test_rewrites": 0,
           "review_approved": True, "review_verdicts": (_grounded_review(),),
           "verification_basis": "review"})
    assert absent.claimed is True and absent.basis == "review"
    # ... not a test written and then REMOVED by a rewrite
    removed = claim_decision(
        route="review",
        **{**base, "own_test": None, "own_test_green": False, "test_rewrites": 1,
           "review_approved": True, "review_verdicts": (_grounded_review(),),
           "verification_basis": "review"})
    assert removed.claimed is False and removed.blocker == "green-after-test-rewrite"
    # rule 6: any rewrite needs the independent verification to agree
    rewritten = claim_decision(route="own-test", **{**base, "test_rewrites": 1})
    assert rewritten.claimed is False and rewritten.blocker == "green-after-test-rewrite"
    agreed = claim_decision(
        route="review",
        **{**base, "test_rewrites": 1, "iv_approved": True, "review_approved": True,
           "review_verdicts": (_grounded_review(),), "verification_basis": "review"})
    assert agreed.claimed is True and agreed.basis == "review+independent-test"
    # rule 8: a red-on-final independent verdict never carries a NON-review claim
    red = claim_decision(
        route="independent-test",
        **{**base, "iv_approved": False, "iv_red_on_final": True,
           "verification_basis": "reason"})
    assert red.claimed is False and red.blocker == "independent-test-red-on-final"
    # rule 4 (ticket 23 round 3, the T-14 #2 fix): a RED independent per-criterion
    # verification BLOCKS the review-backed claim. Unlike the model-written own test, the
    # independent verification is fresh, independently authored and discriminating — not
    # the thing the review-precedence rule was written to outrank — so its failure on the
    # delivered code cannot be overridden. The disagreement names both evidences.
    review_over_red_iv = claim_decision(
        route="review",
        **{**base, "own_test": None, "own_test_green": False, "iv_red_on_final": True,
           "iv_red_detail": "independent-test-red-on-final: the fix returns dicts",
           "review_approved": True, "review_verdicts": (_grounded_review(),),
           "verification_basis": "review"})
    assert review_over_red_iv.claimed is False
    assert review_over_red_iv.blocker == "independent-test-red-on-final"
    assert "REJECTED the same revision" in review_over_red_iv.disagreement
    assert "the fix returns dicts" in review_over_red_iv.disagreement
    # rule 4 (ticket 23 round 3): a VACUOUS/non-discriminating independent test is NOT a
    # red verdict; the review still carries the claim.
    review_over_vacuous_iv = claim_decision(
        route="review",
        **{**base, "own_test": None, "own_test_green": False, "iv_red_on_final": False,
           "review_approved": True, "review_verdicts": (_grounded_review(),),
           "verification_basis": "review"})
    assert review_over_vacuous_iv.claimed is True
    assert review_over_vacuous_iv.basis == "review"
    # rule 3b (ticket 23 round 3, the T-31 fix): the REQUEST-LEVEL artifacts are a hard
    # block on EVERY route, including the review route.
    request_blocked = claim_decision(
        route="review",
        **{**base, "own_test": None, "own_test_green": False, "review_approved": True,
           "review_verdicts": (_grounded_review(),), "verification_basis": "review",
           "request_coverage_missing": ["the request names api/service.py; ..."]})
    assert request_blocked.claimed is False
    assert request_blocked.blocker == "request-artifacts-uncovered"
    # ... but a green, unrewritten own test can still carry one (the IV red is a label)
    own_carries = claim_decision(route="own-test",
                                 **{**base, "iv_red_on_final": True})
    assert own_carries.claimed is True
    # the verification covenant (best-effort / required tier) is a precondition
    assert claim_decision(route="review",
                          **{**base, "own_test": None, "review_approved": True,
                             "review_verdicts": (_grounded_review(),),
                             "verification_basis": "review",
                             "tier_allowed": False}).claimed is False
    # the tree's internal close routes through the same gate
    assert claim_decision(route="integration", criteria_count=0,
                          integration_passed=True, all_children_closed=True).claimed is True
    assert claim_decision(route="integration", criteria_count=0,
                          integration_passed=True, all_children_closed=False).claimed is False
    assert claim_decision(route="integration", criteria_count=0,
                          integration_passed=False, all_children_closed=True).claimed is False


def test_claim_gate_refuses_a_visible_suite_regression():
    """docs/6_FLOW.md §4 W4 / §5 (P1b): a baseline-green test that no longer passes is a hard block
    on EVERY leaf route, through the ONE gate's ``regressions`` input."""
    base = {
        "criteria_count": 1, "ledger": _gate_ledger(), "own_test": "tests/t.py",
        "own_test_green": True, "test_rewrites": 0, "iv_approved": False,
        "iv_red_on_final": False, "review_approved": False, "review_verdicts": (),
        "coverage_missing": (), "test_case_problems": (),
        "verification_basis": "test", "tier_allowed": True,
    }
    assert claim_decision(route="own-test", **base).claimed is True
    blocked = claim_decision(route="own-test", **base,
                             regressions=("tests/test_visible.py::test_ok",))
    assert blocked.claimed is False and blocked.blocker == "regression"
    assert "tests/test_visible.py::test_ok" in blocked.detail
    # the review route cannot override a regression (it comes BEFORE the review step)
    review_blocked = claim_decision(
        route="review", **{**base, "own_test": None, "own_test_green": False,
                            "review_approved": True,
                            "review_verdicts": (_grounded_review(),),
                            "verification_basis": "review"},
        regressions=("tests/test_visible.py::test_ok",))
    assert review_blocked.claimed is False and review_blocked.blocker == "regression"


def test_a_visible_suite_regression_blocks_the_claim_and_is_recorded(tmp_path):
    """P1b wiring, end to end through ``run_leaf``: the visible suite is recorded green
    on the PRISTINE source, the final revision breaks it, and the claim is refused with
    the failing id in the outcome, the failure report and the ledger event."""
    visible_id = "tests/test_visible.py::test_ok"
    self_id = "tests/test_leaf_self.py::test_goal"
    spec = make_spec()
    stage(tmp_path, spec.files)
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})

    def suite(workdir, node_ids=None):
        source = (workdir / "pkg/calc.py").read_text()
        own_written = (workdir / "tests/test_leaf_self.py").exists()
        if not own_written:
            # the PRISTINE baseline: the visible suite is green
            return _leaf_suite(passed=(visible_id,))
        if "return 42" not in source:
            # the run's own test is red on arrival
            return _leaf_suite(passed=(), failed=(self_id,), exit=1)
        # the final revision: the run's own gate is GREEN, but the baseline-visible test
        # no longer runs (deleted/hidden) — exactly the gap the own-test gate cannot see.
        return _leaf_suite(passed=(self_id,))

    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=2, deadline_ts=_FAR_FUTURE),
                        run_tests=suite)

    assert out.claimed is False
    assert out.regressions == [visible_id]
    assert out.regression_observable is True
    assert out.regression_baseline == [visible_id]
    assert "regression" in out.regression_detail
    assert out.failure_report is not None
    assert out.failure_report.regressions == (visible_id,)
    assert out.failure_report.regression_observable is True
    kinds = ledger_kinds()
    assert "regression_baseline" in kinds and "regression_check" in kinds
    assert "regression_blocks_claim" in kinds


def _leaf_suite(passed=(), failed=(), *, exit: int = 0) -> ShapedResult:
    """A shaped suite result with a genuine machine-readable gate report."""
    green = exit == 0 and not failed
    return ShapedResult(
        command=["python3", "-m", "pytest", "-q"], exit=exit,
        verdict="ok" if green else "failed",
        excerpts=[] if green else [f"FAILED {nid}" for nid in failed],
        gate=GateReport(report_path="(fake)", process_exit=exit, canary="fake",
                        expected_files=(), n_tests=len(passed) + len(failed),
                        n_failed=len(failed), n_errors=0, passed_ids=tuple(passed),
                        failed_ids=tuple(failed), missing=(), observed=True,
                        anomaly="" if green else "tests-failed",
                        detail="" if green else "1 failure(s)"))


def test_a_visible_suite_that_stays_green_does_not_block_the_claim(tmp_path):
    """A visible suite that keeps passing is not a regression: the run still claims, and
    the outcome records the observed-but-clean check."""
    visible_id = "tests/test_visible.py::test_ok"
    self_id = "tests/test_leaf_self.py::test_goal"
    spec = make_spec()
    stage(tmp_path, spec.files)
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})

    def suite(workdir, node_ids=None):
        source = (workdir / "pkg/calc.py").read_text()
        if not (workdir / "tests/test_leaf_self.py").exists():
            return _leaf_suite(passed=(visible_id,))
        if "return 42" not in source:
            return _leaf_suite(passed=(), failed=(self_id,), exit=1)
        return _leaf_suite(passed=(self_id, visible_id))

    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        run_tests=suite)

    assert out.claimed is True
    assert out.regressions == []
    assert out.regression_observable is True
    assert out.regression_baseline == [visible_id]
    assert out.failure_report is None


def test_a_baseline_without_a_final_check_is_unobservable(tmp_path):
    """A run that stops before the final-revision check records UNOBSERVABLE with the
    baseline kept — never the false claim that the suite was clean or absent."""
    visible_id = "tests/test_visible.py::test_ok"
    spec = make_spec()
    stage(tmp_path, spec.files)
    stage(tmp_path, {"tests/test_visible.py": "def test_ok():\n    assert True\n"})

    def suite(workdir, node_ids=None):
        return _leaf_suite(passed=(visible_id,))

    # calls=0: the baseline is captured (no model call), then the self-test cannot afford
    # a call and the run hands over before any final-revision check.
    out = run_leaf_sync(FakeModelRunner({}), spec, tmp_path,
                        Budget(calls=0, deadline_ts=_FAR_FUTURE), run_tests=suite)

    assert out.claimed is False
    assert out.regressions == []
    assert out.regression_observable is False
    assert out.regression_baseline == [visible_id]
    assert "did not run" in out.regression_detail


#: The EXACT `claim_decision(...)` call sites the package is allowed to have (ticket 22
#: round 2). A new claim site must consciously update this whitelist, so the ONE-gate
#: invariant cannot be widened by accident.
CLAIM_SITE_WHITELIST = {"leaf.py": 3, "tree_run.py": 1}


def _scan_claim_gate(harness_dir: Path) -> dict:
    """The AST scan behind :func:`test_only_the_single_gate_can_produce_a_claimed_outcome`
    (ticket 21 round 6, hardened ticket 22 round 2).

    Walks ``harness_dir`` RECURSIVELY and returns ``offenders`` (any path that could
    produce a claimed outcome outside the gate), ``grant_functions`` (every
    ``_granted_claim`` definition), ``literal_true`` (every literal ``claimed=True`` with
    whether it sits inside a grant function), and ``call_sites`` (``claim_decision(...)``
    call counts per relative file). Exposed as module level so the round-2 regression probe
    can run it against a synthetic duplicate/extra call site under /tmp.
    """
    import ast

    offenders: list[str] = []
    grant_functions: list[str] = []
    #: ``(relative path, lineno, inside_a_grant_function)`` for every literal True.
    literal_true: list[tuple[str, int, bool]] = []
    call_sites: dict[str, int] = {}

    for path in sorted(Path(harness_dir).rglob("*.py")):    # RECURSIVE over harness/**
        rel = str(path.relative_to(harness_dir))
        tree = ast.parse(path.read_text(), filename=str(path))
        grant_ranges: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_granted_claim":
                grant_functions.append(f"{rel}:{node.lineno}")
                grant_ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "claim_decision":
                call_sites[rel] = call_sites.get(rel, 0) + 1

        def in_grant(lineno: int, ranges: list[tuple[int, int]] = grant_ranges) -> bool:
            return any(a <= lineno <= b for a, b in ranges)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "claimed":
                        value = node.value
                        literal_false = (isinstance(value, ast.Constant)
                                         and value.value is False)
                        from_decision = (isinstance(value, ast.Attribute)
                                         and value.attr == "claimed")
                        if isinstance(value, ast.Constant) and value.value is True:
                            literal_true.append((rel, node.lineno, in_grant(node.lineno)))
                            if not in_grant(node.lineno):
                                offenders.append(
                                    f"{rel}:{node.lineno}: claimed = True outside the gate")
                        elif not (literal_false or from_decision):
                            offenders.append(
                                f"{rel}:{node.lineno}: claimed = {ast.unparse(value)}")
            if isinstance(node, ast.keyword) and node.arg == "claimed" \
                    and isinstance(node.value, ast.Constant) and node.value.value is True:
                literal_true.append((rel, node.lineno, in_grant(node.lineno)))
                if not in_grant(node.lineno):
                    offenders.append(f"{rel}:{node.lineno}: claimed=True keyword")
    return {"offenders": offenders, "grant_functions": grant_functions,
            "literal_true": literal_true, "call_sites": call_sites}


def test_only_the_single_gate_can_produce_a_claimed_outcome():
    """STRUCTURAL enforcement of the ONE gate (ticket 21 round 6, hardened ticket 22
    round 2).

    Rounds 2-5 each fixed a single branch and the next verifier found the same wrong
    green in a sibling branch, because a branch could simply SET a claim itself. This AST
    check over the whole ``harness/**`` package fails if ANY path other than the gate can
    produce a claimed outcome:

    * every ``claimed = <value>`` assignment must be ``False`` or read from a
      ``ClaimDecision`` (an attribute ``.claimed``) — never a literal ``True``;
    * there is EXACTLY ONE ``_granted_claim`` function in the package and EVERY literal
      ``claimed=True`` (an assignment or a keyword) sits inside it — so a future duplicate
      grant constructor cannot smuggle a bypass;
    * the walk is RECURSIVE over ``harness/**`` (a subpackage would otherwise escape);
    * the ``claim_decision(...)`` call sites equal an explicit whitelist, so adding a claim
      site requires a conscious test update.
    """
    import harness
    import harness.leaf
    import harness.tree_run

    findings = _scan_claim_gate(Path(harness.__file__).parent)
    assert findings["offenders"] == [], findings["offenders"]
    # (1) EXACTLY ONE grant constructor across the whole package, and EVERY literal
    # ``claimed=True`` sits inside it.
    assert len(findings["grant_functions"]) == 1, (
        f"expected exactly one _granted_claim in harness/, saw "
        f"{findings['grant_functions']}")
    assert findings["literal_true"], "the single gate no longer constructs a claimed decision"
    assert all(inside for _, _, inside in findings["literal_true"]), (
        f"a literal claimed=True sits outside the single grant constructor: "
        f"{findings['literal_true']}")
    # (2) the claim sites are EXACTLY this whitelist. A new claim site (or a sibling that
    # stops calling the gate) fails here and forces a conscious update.
    assert findings["call_sites"] == CLAIM_SITE_WHITELIST, (
        f"claim_decision call sites changed: {findings['call_sites']} "
        f"!= {CLAIM_SITE_WHITELIST}")
    # (3) the leaf's three routes and the tree close are wired to the SAME function.
    assert "claim_decision(" in Path(harness.leaf.__file__).read_text()
    assert "claim_decision(" in Path(harness.tree_run.__file__).read_text()


# ===========================================================================
# Ticket 23 — best-evidence delivery and the four failure-forensics defects
# ===========================================================================


def _collection_error_result(iv_path: str = "tests/test_leaf_self.py") -> ShapedResult:
    """A Red gate whose only entry for the run's own test is a collection error: the
    module name with NO ``::`` selector (ticket 23 item 4)."""
    gate = GateReport(report_path="(scripted)", process_exit=2, canary="scripted",
                      expected_files=(iv_path,), n_tests=1, n_failed=0, n_errors=1,
                      passed_ids=(), failed_ids=("t23probe.tests.test_leaf_self",),
                      missing=(), observed=True, anomaly="tests-failed",
                      detail="1 error(s): collection failure")
    return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=2,
                        verdict="failed", excerpts=["collection failure: SyntaxError"],
                        gate=gate)


def test_own_test_collectible_requires_a_real_node_id():
    """Ticket 23 item 4: only a collected node id that references the run's own test file
    counts; a collection-error module name (no ``::``) is not a valid target."""
    good = dataclasses.replace(
        scripted_red_gate(), failed_ids=("tests/test_leaf_self.py::test_goal",))
    assert _own_test_collectible(good, "tests/test_leaf_self.py") is True
    assert _own_test_collectible(good, "tests/other.py") is False
    bad = GateReport(report_path="(scripted)", process_exit=2, canary="scripted",
                     expected_files=("tests/test_leaf_self.py",), n_tests=1, n_failed=0,
                     n_errors=1, passed_ids=(),
                     failed_ids=("t23probe.tests.test_leaf_self",), missing=(),
                     observed=True, anomaly="tests-failed", detail="collection failure")
    assert _own_test_collectible(bad, "tests/test_leaf_self.py") is False
    assert _own_test_collectible(None, "tests/test_leaf_self.py") is False


def test_uncollectible_self_test_is_a_defect_not_a_target(tmp_path):
    """Ticket 23 item 4: a self-test that cannot be collected is dropped (recorded), and
    with a reviewer the node switches to review instead of iterating against it."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
        review=_approving_review,
        run_tests=ScriptedTests([_collection_error_result(), 0]))

    assert "self_test_invalid" in ledger_kinds()
    assert out.self_test is None
    assert any("cannot be collected" in r for r in out.refusals)
    assert out.verification_basis == "review"


def test_uncollectible_self_test_without_a_reviewer_stops_honestly(tmp_path):
    """Ticket 23 item 4: with no reviewer there is no fallback — the node stops with the
    distinct ``self-test-invalid`` reason and records the refusal + its evidence."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=3, deadline_ts=_FAR_FUTURE),
        run_tests=ScriptedTests([_collection_error_result()]))

    assert out.claimed is False
    assert out.stop_reason == "self-test-invalid"
    assert out.self_test is None
    assert "self_test_invalid" in ledger_kinds()
    assert any("cannot be collected" in r for r in out.refusals)


def test_snapshot_and_restore_round_trip(tmp_path):
    """Ticket 23 item 1: the snapshot captures every deliverable file and the restore
    reproduces it exactly, removing files created later and skipping harness dot-paths."""
    stage(tmp_path, {"pkg/calc.py": "def result():\n    return 42\n",
                     "tests/test_x.py": "def test_x():\n    assert True\n"})
    snapshot = _snapshot_deliverable_files(tmp_path)
    assert set(snapshot) == {"pkg/calc.py", "tests/test_x.py"}
    # a later revision: change one file, add another, drop the test
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 0\n")
    (tmp_path / "pkg" / "new.py").write_text("added = True\n")
    (tmp_path / "tests" / "test_x.py").unlink()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored")
    _restore_deliverable_files(tmp_path, snapshot)
    assert (tmp_path / "pkg" / "calc.py").read_text() == "def result():\n    return 42\n"
    assert (tmp_path / "tests" / "test_x.py").read_text() == "def test_x():\n    assert True\n"
    assert not (tmp_path / "pkg" / "new.py").exists()


def test_best_evidence_refuses_an_own_test_restore_that_left_the_named_artifact_untouched(
        tmp_path):
    """Ticket 23 round 2, probe (a) — THE DEMONSTRATED HAZARD: the run's own test is
    model-written and can be WRONG, so a revision that merely greened it can be the wrong
    revision. Here that revision never touches the artifact the criterion names
    (``pkg/calc.py``), a later, redder revision follows, and the restore is REFUSED: the
    TERMINAL revision is delivered and the record names the untouched artifact."""
    spec = dataclasses.replace(make_spec(), acs=["pkg/calc.py must return 42"])
    stage(tmp_path, spec.files)
    green_but_wrong = write_env("pkg/other.py", "x = 1\n", comment="greens the wrong test")
    worse = write_env("pkg/other.py", "x = 2\n", comment="a later, redder revision")
    model = FakeModelRunner({"write_test": [SELF_TEST, green_but_wrong, worse, worse]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
        run_tests=ScriptedTests([1, 0, 1, 1, 1]))

    # the first (green) revision only missed coverage, so it was never claimed — and now
    # it is not delivered either: its own test greening is not evidence the revision is
    # the one the criteria asked for.
    assert out.claimed is False
    delivered = out.delivered_revision
    assert delivered["restore_refused"] is True
    assert delivered["restored"] is False
    assert delivered["best_tier"] == "own-test"
    assert delivered["best_rank"] == BEST_EVIDENCE_RANKS["own-test"]
    assert any("pkg/calc.py" in m and "untouched" in m
               for m in delivered["coverage_missing"])
    assert "pkg/calc.py" in delivered["restore_refused_reason"]
    # the TERMINAL revision lands on disk, never the wrong revision that greened the test
    assert (tmp_path / "pkg" / "other.py").read_text() == "x = 2\n"


def test_best_evidence_restores_an_own_test_revision_that_moved_the_named_artifact(
        tmp_path):
    """Ticket 23 round 2, probe (b) — THE SAFE CASE (the T-05 win): the own-test-green
    revision really MOVES the artifact the criterion names, so the coverage check is clean
    at its own revision and the restore still happens over the later, erased/worse terminal
    revision. The second criterion names no artifact, so the attempt routes to review; the
    review rejects, the loop continues, M1 erases the good revision — the snapshot saves
    it."""
    spec = dataclasses.replace(
        make_spec(), acs=["pkg/calc.py must return 42", "the widget must wobble"])
    stage(tmp_path, spec.files)
    fix = write_env("pkg/calc.py", "def result():\n    return 42\n", comment="the fix")
    worse = write_env("pkg/other.py", "x = 2\n", comment="a later, redder revision")
    model = FakeModelRunner({"write_test": [SELF_TEST, fix, worse, worse]})

    def rejecting(request: ReviewRequest) -> ReviewVerdict:
        return ReviewVerdict(grade="definitely-problematic", detail="no criterion cleared")

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        review=rejecting, run_tests=ScriptedTests([1, 0, 1, 1, 1]))

    assert out.claimed is False
    delivered = out.delivered_revision
    assert delivered["restored"] is True
    assert delivered["restore_refused"] is False
    assert delivered["best_tier"] == "own-test"
    assert delivered["restored_over_last_written"] is True
    # the delivered revision is the one that MOVED the named artifact ...
    assert (tmp_path / "pkg" / "calc.py").read_text() == "def result():\n    return 42\n"
    # ... and the later, weaker revision was removed by the restore.
    assert not (tmp_path / "pkg" / "other.py").exists()


def test_best_evidence_ranking_is_one_documented_order():
    """Ticket 23 round 2: the delivery strength order is ONE list, asserted here and used
    by the code: (4) AGREEMENT — the run's own discriminating test green AND the
    independent per-criterion verification approving the SAME revision; (3) the
    independent per-criterion verification approved; (2) the run's own discriminating test
    green; (1) a combined-positive, grant-calibre review. The pair the round-1 commit body
    got BACKWARDS (own test vs independent verification / review) is pinned explicitly."""
    assert BEST_EVIDENCE_ORDER == ("agreement", "independent-test", "own-test", "review")
    ranks = [BEST_EVIDENCE_RANKS[tier] for tier in BEST_EVIDENCE_ORDER]
    assert ranks == [4, 3, 2, 1]
    assert BEST_EVIDENCE_RANKS["agreement"] > BEST_EVIDENCE_RANKS["independent-test"]
    assert BEST_EVIDENCE_RANKS["independent-test"] > BEST_EVIDENCE_RANKS["own-test"]
    assert BEST_EVIDENCE_RANKS["own-test"] > BEST_EVIDENCE_RANKS["review"]
    assert set(BEST_EVIDENCE_RANKS) == set(BEST_EVIDENCE_ORDER)


def test_every_best_evidence_capture_reads_the_one_rank_table():
    """STRUCTURAL (ticket 23 round 2): the strength of every evidence milestone comes
    from :data:`BEST_EVIDENCE_RANKS` and names a tier of the ONE documented order, so the
    code cannot drift from that order. Each capture site must pair the rank and the tier
    through the SAME key."""
    import ast

    leaf = Path(__file__).resolve().parents[2] / "harness" / "leaf.py"
    tree = ast.parse(leaf.read_text(), filename=str(leaf))
    sites = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "note_current_evidence"]
    assert len(sites) == 8
    for node in sites:
        rank, tier = node.args[0], node.args[1]
        assert isinstance(rank, ast.Subscript) \
            and ast.unparse(rank.value) == "BEST_EVIDENCE_RANKS", \
            f"leaf.py:{node.lineno}: hard-coded rank {ast.unparse(rank)}"
        key = rank.slice.value if isinstance(rank.slice, ast.Constant) else None
        assert key in BEST_EVIDENCE_ORDER, \
            f"leaf.py:{node.lineno}: unknown rank key {ast.unparse(rank.slice)}"
        assert isinstance(tier, ast.Constant) and tier.value == key, \
            f"leaf.py:{node.lineno}: tier {ast.unparse(tier)} does not match rank key {key}"


def test_best_evidence_captures_agreement_above_the_independent_test_alone(tmp_path):
    """Ticket 23 round 2: the strongest evidence is AGREEMENT (rank 4) — the run's own
    discriminating test green AND the independent per-criterion verification approving the
    SAME revision — captured after the own-test milestone (rank 2) it subsumes. A granted
    claim is never replaced, so the record says nothing was restored."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    events: list[tuple[str, dict]] = []
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 0, 1, 0]),
                        on_event=lambda kind, data: events.append((kind, data)))

    assert out.claimed is True and out.claimed_basis == "own-test+independent-test"
    captures = [(d["rank"], d["tier"]) for kind, d in events
                if kind == "best_evidence_revision"]
    assert captures == [(BEST_EVIDENCE_RANKS["own-test"], "own-test"),
                        (BEST_EVIDENCE_RANKS["agreement"], "agreement")]
    assert out.delivered_revision["restored"] is False
    assert out.delivered_revision["terminal_tier"] == "claim"


def test_best_evidence_not_restored_over_a_granted_claim(tmp_path):
    """Ticket 23 item 1: a granted claim is the strongest evidence, so its revision is
    never replaced; the record says the last-written revision already carried the best."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=4, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True
    assert out.delivered_revision["restored"] is False
    assert out.delivered_revision["restore_refused"] is False
    assert out.delivered_revision["terminal_tier"] == "claim"


def test_claim_gate_advisory_own_test_rewrite_does_not_block_review():
    """Ticket 23 item 2: on the review route, an ADVISORY (plan declared no tests) own
    test's rewrite no longer blocks the review-carried claim; an unadvisory one still does."""
    ledger = [CriterionLedgerEntry("AC-1", "c", "satisfied", "review:ac-correctness", "ok")]
    passing = (ReviewVerdict(angle="ac-correctness", grade="definitely-ok", evidence="x"),
               ReviewVerdict(angle="contract-compat", grade="definitely-ok", evidence="y"))
    advisory = claim_decision(
        route="review", criteria_count=1, ledger=ledger, own_test=None,
        own_test_green=False, test_rewrites=2, iv_approved=False, review_approved=True,
        review_verdicts=passing, verification_basis="review", own_test_advisory=True)
    assert advisory.claimed is True and advisory.basis == "review"
    strict = claim_decision(
        route="review", criteria_count=1, ledger=ledger, own_test=None,
        own_test_green=False, test_rewrites=2, iv_approved=False, review_approved=True,
        review_verdicts=passing, verification_basis="review", own_test_advisory=False)
    assert strict.claimed is False and strict.blocker == "green-after-test-rewrite"


def test_reviews_only_plan_advisory_rewrite_can_still_claim(tmp_path):
    """Ticket 23 item 2 end to end: a reviews-only plan whose own test was rewritten still
    claims on the review (the round-3 acceptance run's missed success)."""
    spec = make_spec()                       # planned_tests=() -> advisory
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py", "def test_goal():\n    assert True\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_approving_review,
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.verification_basis == "review"
    assert out.test_rewrites == 1
    assert out.claimed is True and out.claimed_basis in ("review", "review+independent-test")


def test_model_review_preserves_an_explicit_negative_grade_on_a_non_ok_envelope():
    """Ticket 23 item 3: an envelope whose status is not ``ok`` but which carries an
    explicit grade keeps it — a ``definitely-problematic`` verdict must not silently
    become ``uncertain``; only an absent grade is uncertain."""
    from bench.v2_leaf import model_review

    model = FakeModelRunner({"leaf_review": [
        {"status": "failed", "comment": "reviewed but the envelope failed",
         "grade": "definitely-problematic", "evidence": "pkg/calc.py returns 0, not 42"},
        {"status": "unable", "comment": "no grade at all",
         "unable_reason": "no source to review"},
    ]})
    request = ReviewRequest(goal="g", acs=["a"], original={"pkg/calc.py": "x"},
                            final={"pkg/calc.py": "y"}, angle="ac-correctness")
    negative = asyncio.run(model_review(model, request))
    assert negative.grade == "definitely-problematic" and negative.approved is False
    assert "returns 0" in negative.evidence
    absent = asyncio.run(model_review(model, request))
    assert absent.grade == "uncertain" and absent.approved is False


def test_review_request_carries_the_coverage_facts(tmp_path):
    """Ticket 23 item 5: the reviewer is handed the criteria whose named artifacts the
    diff never touches, so a partial multi-file fix cannot draw ``definitely-ok``."""
    from bench.v2_leaf import _review_question

    spec = dataclasses.replace(make_spec(), acs=["pkg/calc.py must return 42"])
    stage(tmp_path, spec.files)
    (tmp_path / "pkg" / "other.py").write_text("x = 1\n")
    request = _review_request(spec, tmp_path, {"pkg/calc.py": "def result():\n    return 0\n"},
                              "no test can carry it", "ac-correctness")
    assert request.coverage_missing
    assert any("pkg/calc.py" in m for m in request.coverage_missing)
    question = _review_question(request)
    assert "COVERAGE FACTS" in question and "pkg/calc.py" in question


def test_run_record_carries_the_delivered_revision():
    """Ticket 23 item 1: the persisted record names the best-evidence revision and whether
    it was restored (the field must survive ``json.dumps``)."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="attempts",
        layers_used=["sampling"], stop_reason="attempts",
        delivered_revision={"restored": True, "best_tier": "review", "best_rank": 3,
                            "best_attempt": 1, "reason": "restored the best revision",
                            "best_files": ["pkg/calc.py"]})
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[], skipped=[])
    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="missed-success", run_wall_s=1.0)
    assert record["delivered_revision"]["restored"] is True
    assert record["delivered_revision"]["best_tier"] == "review"
    json.dumps(record)


def test_advisory_rewritten_test_cannot_block_and_routes_to_review(tmp_path):
    """Ticket 23 item 2, the T-05 path: a reviews-only plan whose judge-authorized test
    rewrite stays RED, then a later source fix greens it. The advisory test's rewrite must
    not stop the run at ``green-after-test-rewrite`` — the plan's review decides."""
    spec = make_spec()                       # planned_tests=() -> advisory
    stage(tmp_path, spec.files)
    repaired_red = write_env("tests/test_leaf_self.py",
                             "from pkg.calc import result\n\n\ndef test_goal():\n"
                             "    assert result() == 7\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired_red, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, review=_approving_review,
                        run_tests=ScriptedTests([1, 1, 0]))

    assert out.test_rewrites == 1
    assert out.claimed is True
    assert out.claimed_basis in ("review", "review+independent-test")
    assert out.stop_reason == "green"


# ===========================================================================
# ticket 23 round 3: the two gates that close the three measured false successes
# (T-31 request-level artifact coverage; T-14 #2 the red independent verification).
# ===========================================================================


def test_request_coverage_resolves_the_whole_request_not_just_one_criterion(tmp_path):
    """The deterministic request-level extraction: a request word that equals a source
    file's stem resolves to that file, a word that equals a defined symbol resolves to
    that symbol, and a test path is never a request artifact."""
    from harness.leaf import _request_coverage

    files = {"api/transport.py": "def send(url, payload):\n    return url\n",
             "api/client.py": "def fetch(url):\n    return url\n",
             "api/service.py": "def sync_record(rid):\n    return rid\n",
             "exporter/bulk.py": "def export_all(ids):\n    return ids\n",
             "tests/test_chain.py": "def test_x():\n    assert True\n"}
    spec = dataclasses.replace(
        make_spec(files, goal="thread the timeout through the transport's send(), the "
                              "client's fetch(), the service sync and the bulk exporter"),
        acs=["thread it through the client's fetch()"])
    baseline = dict(files)
    # only api/client.py touched
    stage(tmp_path, files)
    (tmp_path / "api" / "client.py").write_text(
        "from api.transport import send\n\n\ndef fetch(url, timeout=None):\n"
        "    return send(url, url)\n")
    coverage = _request_coverage(spec, tmp_path, baseline)
    assert set(coverage.files) == {"api/transport.py", "api/client.py", "api/service.py",
                                   "exporter/bulk.py"}
    assert "fetch" in coverage.symbols and "send" in coverage.symbols
    assert set(coverage.missing) == {"api/transport.py", "api/service.py",
                                     "exporter/bulk.py"}


def test_request_level_coverage_blocks_every_route_when_a_named_call_site_is_untouched(tmp_path):
    """PROBE (a), the T-31 fix: the request names three call sites, the run touches one.
    The per-criterion check is satisfied (its criterion names only pkg/calc.py) but the
    REQUEST-level check is not, so every claim route is blocked and the unmet artifacts
    are recorded (file names + the diff evidence)."""
    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/other.py": "def helper():\n    return 0\n",
             "pkg/third.py": "def thing():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, goal="thread the timeout through pkg/calc.py, pkg/other.py "
                              "and pkg/third.py"),
        acs=["thread the timeout through pkg/calc.py"])
    stage(tmp_path, files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl(path="pkg/calc.py", content="def result():\n    return 1\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is False
    assert out.coverage_missing == []                       # per-criterion check satisfied
    assert any("pkg/other.py" in m for m in out.request_coverage_missing)
    assert any("pkg/third.py" in m for m in out.request_coverage_missing)
    assert all("final diff does not touch it" in m
               for m in out.request_coverage_missing)
    assert out.request_coverage is not None
    assert set(out.request_coverage.missing) == {"pkg/other.py", "pkg/third.py"}
    assert "request_artifacts_uncovered" in ledger_kinds()


def test_request_level_coverage_blocks_the_review_route(tmp_path):
    """PROBE (a, review route): the request names three call sites; the run's own test is
    green on arrival, so REVIEW is mandatory and APPROVES — but the request-level coverage
    hard block vetoes the review (the T-31 route a graded review used to carry)."""
    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/other.py": "def helper():\n    return 0\n",
             "pkg/third.py": "def thing():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, goal="thread the timeout through pkg/calc.py, pkg/other.py "
                              "and pkg/third.py"),
        acs=["thread the timeout through pkg/calc.py"])
    stage(tmp_path, files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT]
                                          + [impl(path="pkg/calc.py",
                                                  content="def result():\n    return 1\n")] * 12})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=30, deadline_ts=_FAR_FUTURE),
                        review=_passing_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is False
    assert out.request_coverage_missing
    assert "review_request_artifacts_blocked" in ledger_kinds()


def test_red_own_test_blocks_the_review_before_a_red_independent_verification(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1 (P1c): the run's own test is RED on the final revision,
    so the REVIEW SEAM never opens --- the review does not run regardless of the
    independent verification. The IV still runs on the delivered code and is recorded as
    ``independent-test-red-on-final``, but the outcome is FAIL either way. The old ticket
    23 T-14 rule (a red IV blocks an approving review) is pinned directly on the claim
    gate in ``test_claim_gate_enforces_every_rule_directly``; the flow now stops the
    review earlier."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    reviews = ScriptedReview([_passing_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        review=reviews, iv=lambda request: iv_candidate(),
                        run_tests=ScriptedTests([1, 1, 1, 1, 1, 1]))

    assert out.claimed is False
    assert out.state == "fail"
    assert reviews.calls == 0                       # the review never ran
    assert out.review_verdicts == []
    assert out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_red_own_test_stops_the_review_even_with_a_vacuous_independent_test(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1 (P1c): a VACUOUS independent test (it passes on the
    pristine source) does not matter once the run's own test is RED on the final
    revision: the review seam stays shut, nothing is claimed, and the leaf's state is
    FAIL. (The claim-gate rule that a vacuous IV does not block a review is pinned in
    ``test_claim_gate_enforces_every_rule_directly``.)"""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = LeafSpec(goal="make result() return 42", files=files,
                    acs=["result() returns 42"], interfaces=["result() -> int"])
    spec = dataclasses.replace(spec, planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    wrong = impl("def result():\n    return 100\n")
    model = FakeModelRunner({"write_test": [SYMPTOM_TEST] + [wrong] * 8})
    vacuous = iv_candidate(path="tests/test_vacuous.py",
                           content="def test_goal():\n    assert True\n")
    reviews = ScriptedReview([_passing_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        review=reviews, iv=lambda request: vacuous,
                        run_tests=ScriptedTests([1, 1, 1, 1, 0, 0]))

    assert out.claimed is False
    assert out.state == "fail"
    assert reviews.calls == 0
    assert out.review_verdicts == []
    assert out.iv_verdicts[-1].approved is False
    assert out.iv_verdicts[-1].reason == "independent-test-not-red"
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_request_coverage_exempts_a_frozen_artifact_named_by_the_request(tmp_path):
    """PROBE (a)/(b), the T-33 false-block fix: the request NAMES ``serialize/base.py``
    (and the word ``base``) while the task's frozen list contains it. The resolved file is
    EXEMPTED and RECORDED (artifact + why), never required, so a run that touches the two
    live implementations is not blocked for not touching the file the task forbids it to
    touch — while the SAME artifact is still required when it is NOT in the frozen set, so
    the gate stays strict for every non-frozen artifact."""
    from harness.leaf import _request_coverage

    files = {"serialize/base.py": "class Serializer:\n    pass\n",
             "serialize/json_ser.py": "from serialize.base import Serializer\n",
             "serialize/pickle_ser.py": "from serialize.base import Serializer\n"}
    goal = ("our serializer layer has a binding contract in serialize/base.py; bring both "
            "implementations into the contract (base.py itself is frozen)")
    spec = dataclasses.replace(
        make_spec(files, grader=("serialize/base.py",), goal=goal),
        acs=["json_ser roundtrips non-ASCII text"])
    stage(tmp_path, files)
    # the two LIVE implementations are touched; the frozen base.py is not (and may not be).
    (tmp_path / "serialize" / "json_ser.py").write_text(
        "from serialize.base import Serializer\n\n\nclass JSONSerializer(Serializer):\n"
        "    pass\n")
    (tmp_path / "serialize" / "pickle_ser.py").write_text(
        "from serialize.base import Serializer\n\n\nclass PickleSerializer(Serializer):\n"
        "    pass\n")
    coverage = _request_coverage(spec, tmp_path, dict(files))
    assert "serialize/base.py" in coverage.files
    assert "serialize/base.py" not in coverage.missing
    assert coverage.missing == ()
    assert ("serialize/base.py",
            "frozen by the task (visible but must not change)") in coverage.exemptions
    # ... and the SAME name is required when the task does NOT freeze it (no over-exempt).
    strict = dataclasses.replace(spec, grader_paths=())
    strict_coverage = _request_coverage(strict, tmp_path, dict(files))
    assert "serialize/base.py" in strict_coverage.missing
    assert strict_coverage.exemptions == ()


def test_three_artifact_request_one_frozen_is_clean_two_touched(tmp_path):
    """PROBE (b): a request that names three artifacts — one frozen, two touched — yields
    no request-coverage miss and no claim block; the frozen one is recorded as exempt."""
    from harness.leaf import _request_coverage

    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/frozen.py": "CONTRACT = 1\n",
             "pkg/other.py": "def helper():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, grader=("pkg/frozen.py",),
                  goal="thread the timeout through pkg/calc.py, pkg/frozen.py and "
                       "pkg/other.py"),
        acs=["thread the timeout through pkg/calc.py"])
    stage(tmp_path, files)
    (tmp_path / "pkg" / "calc.py").write_text("def result(timeout=None):\n    return 0\n")
    (tmp_path / "pkg" / "other.py").write_text("def helper(timeout=None):\n    return 0\n")
    coverage = _request_coverage(spec, tmp_path, dict(files))
    assert set(coverage.files) == {"pkg/calc.py", "pkg/frozen.py", "pkg/other.py"}
    assert coverage.missing == ()
    assert coverage.exemptions == (("pkg/frozen.py",
                                    "frozen by the task (visible but must not change)"),)


def test_request_level_coverage_blocks_every_route_including_integration(tmp_path):
    """PROBE (c), the no-bypass fix: the request names three paths, one frozen and one
    genuinely untouched non-frozen. The untouched non-frozen artifact blocks EVERY claim
    route — the leaf routes AND the tree's ``integration`` close, which used to grant
    regardless of the request-coverage miss."""
    from harness.leaf import _request_coverage

    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/frozen.py": "CONTRACT = 1\n",
             "pkg/other.py": "def helper():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, grader=("pkg/frozen.py",),
                  goal="thread the timeout through pkg/calc.py, pkg/frozen.py and "
                       "pkg/other.py"),
        acs=["thread the timeout through pkg/calc.py"])
    stage(tmp_path, files)
    # only pkg/calc.py is touched; pkg/other.py (non-frozen) is untouched.
    (tmp_path / "pkg" / "calc.py").write_text("def result(timeout=None):\n    return 0\n")
    coverage = _request_coverage(spec, tmp_path, dict(files))
    miss = [f"the request names {m}; the final diff does not touch it (request artifact "
            f"coverage)" for m in coverage.missing]
    assert "pkg/other.py" in coverage.missing and "pkg/frozen.py" not in coverage.missing

    base = {"criteria_count": 1,
            "ledger": [CriterionLedgerEntry("AC-1", "s", "satisfied")],
            "own_test": "tests/test_leaf_self.py", "own_test_green": True}
    for route in ("own-test", "independent-test", "review", "reason", "integration"):
        blocked = claim_decision(route=route, request_coverage_missing=miss, **base)
        assert blocked.claimed is False, route
        assert blocked.blocker == "request-artifacts-uncovered", route
    # with the miss gone the integration close still grants (no collateral block).
    granted = claim_decision(route="integration", criteria_count=0,
                             request_coverage_missing=(),
                             integration_passed=True, all_children_closed=True)
    assert granted.claimed is True and granted.basis == "integration"


def test_a_frozen_artifact_named_by_the_request_does_not_block_a_real_run(tmp_path):
    """PROBE (a, end-to-end): a leaf whose request names a frozen file and which touches
    only the live file claims green — the frozen name is exempted, not required."""
    files = {"pkg/calc.py": "def result():\n    return 0\n",
             "pkg/frozen_base.py": "CONTRACT = 1\n"}
    spec = dataclasses.replace(
        make_spec(files, grader=("pkg/frozen_base.py",),
                  goal="respect the contract in pkg/frozen_base.py and make pkg/calc.py's "
                       "result 42"),
        acs=["result() returns 42"])
    stage(tmp_path, files)
    model = FakeModelRunner({"write_test": [
        SELF_TEST, impl(path="pkg/calc.py", content="def result():\n    return 42\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0]))

    assert out.claimed is True and out.stop_reason == "green"
    assert out.request_coverage is not None
    assert out.request_coverage_missing == []
    assert ("pkg/frozen_base.py",
            "frozen by the task (visible but must not change)") in out.request_coverage.exemptions
    assert (tmp_path / "pkg" / "frozen_base.py").read_text() == "CONTRACT = 1\n"


def test_request_coverage_exempts_a_symbol_named_only_in_a_frozen_file(tmp_path):
    """T-33 pattern (fix 1, symbol side): the request's ``contract (`` token resolves to
    ``contract`` in the frozen README, and the request word ``FrozenPolicy`` resolves to a
    class the frozen README defines. A symbol whose every occurrence is in a frozen file
    the run may not change is EXEMPTED and recorded; a symbol that also occurs in a LIVE
    file (``run``) stays strictly required."""
    from harness.leaf import _request_coverage

    files = {"README.md": "class FrozenPolicy:\n    pass\n\nthe contract is binding\n",
             "serialize/api.py": "def run():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, grader=("README.md",),
                  goal="honour the contract (FrozenPolicy says so) and make run() return 1"),
        acs=["run() returns 1"])
    stage(tmp_path, files)
    (tmp_path / "serialize" / "api.py").write_text("def run():\n    return 1\n")
    coverage = _request_coverage(spec, tmp_path, dict(files))

    assert "FrozenPolicy" in coverage.symbols
    assert "contract" in coverage.symbols
    assert "FrozenPolicy" not in coverage.missing and "contract" not in coverage.missing
    frozen_only = ("named only in a frozen/grader-owned source file "
                   "(the run may not change it)")
    assert ("FrozenPolicy", frozen_only) in coverage.exemptions
    assert "run" not in coverage.exemptions
    # the LIVE symbol is genuinely required: drop the live edit and it blocks.
    (tmp_path / "serialize" / "api.py").write_text("def run():\n    return 0\n")
    strict = _request_coverage(spec, tmp_path, dict(files))
    assert "run" in strict.missing


def test_requirement_coverage_exempts_a_criterion_naming_a_frozen_artifact(tmp_path):
    """T-33's real block: the extracted acceptance criteria NAME ``serialize/base.py``,
    which the task freezes. The per-criterion coverage must EXEMPT and record it too (the
    same fix as the request-level check), so a run that touches only the live file is not
    blocked for not touching a file the task forbids; without the frozen set it still
    blocks."""
    from harness.leaf import _requirement_coverage

    files = {"serialize/base.py": "class Serializer:\n    pass\n",
             "pkg/calc.py": "def result():\n    return 0\n"}
    spec = dataclasses.replace(
        make_spec(files, grader=("serialize/base.py",), goal="fix it"),
        acs=["serialize/base.py's contract holds and pkg/calc.py's result() returns 42"])
    stage(tmp_path, files)
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 42\n")
    record = _requirement_coverage(spec, tmp_path, dict(files))[0]

    assert "serialize/base.py" in record.files and "pkg/calc.py" in record.files
    assert record.missing == ()
    assert ("serialize/base.py",
            "frozen by the task (visible but must not change)") in record.exemptions
    # the SAME criterion blocks when the file is NOT frozen (no over-exempt).
    strict = _requirement_coverage(dataclasses.replace(spec, grader_paths=()),
                                   tmp_path, dict(files))[0]
    assert "serialize/base.py" in strict.missing


# ===========================================================================
# P1c-1: the three states + How terminal semantics (docs/6_FLOW.md §1.5 S4/S5, §4, §11 H3/H4)
# ===========================================================================


def test_leaf_terminal_state_maps_the_three_states_and_the_parked_cases():
    """docs/6_FLOW.md §1.5 S5 / §4 (P1c): the explicit state machine — a claim is PASS; a confirmed
    red test is FAIL (never UNCERTAIN); a give-up with no confirmed failure is UNCERTAIN;
    a deadline/call-budget handover is PARKED; a broken environment is NEEDS-USER."""
    from harness.leaf import OUTCOME_STATES, leaf_terminal_state

    assert set(OUTCOME_STATES) >= {"pass", "uncertain", "fail", "parked", "needs-user"}
    base = dict(claimed=False, needs_user=False, stop_reason="attempts",
                signal="honest-failure", own_test_failed=False, review_verdicts=())
    assert leaf_terminal_state(**{**base, "claimed": True}) == "pass"
    assert leaf_terminal_state(**base) == "uncertain"
    assert leaf_terminal_state(**{**base, "own_test_failed": True}) == "fail"
    assert leaf_terminal_state(**{**base, "stop_reason": "calls"}) == "parked"
    assert leaf_terminal_state(**{**base, "stop_reason": "deadline"}) == "parked"
    assert leaf_terminal_state(**{**base, "needs_user": True}) == "needs-user"
    # a graded review that RAN and REJECTED on the final revision is a confirmed fail too
    rejected = ReviewVerdict(angle="ac-correctness", grade="definitely-problematic",
                             evidence="pkg/calc.py:1 returns 0 for AC-1")
    assert leaf_terminal_state(**{**base, "review_verdicts": (rejected, )}) == "fail"


def test_a_red_test_with_an_implementation_wrong_judge_ends_the_how_fail(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §4.1, §11 H3 (P1c) (a): a red own test plus a judge that
    attributes the failure to the IMPLEMENTATION exhausts the retries as FAIL — the review
    is NEVER called (a FAIL test does not reach the review seam)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST]
                             + [impl("def result():\n    return 7\n")] * 6})

    def judge(request: JudgeRequest) -> JudgeVerdict:
        return JudgeVerdict(attribution="implementation",
                            defect="result() does not return 42; the source is wrong")

    reviews = ScriptedReview([_approving_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        judge=judge, review=reviews,
                        run_tests=ScriptedTests([1] * 8))

    assert out.claimed is False
    assert out.state == "fail"
    assert reviews.calls == 0                     # the review never ran
    assert out.review_verdicts == []
    assert "review_blocked_by_failed_test" in ledger_kinds()


def test_b_red_test_with_a_judge_repair_into_a_discriminating_test_continues(tmp_path):
    """docs/6_FLOW.md §1.5 S4 W2/W5, §6.1 (P1c) (b): when the judge attributes the red test to the
    TEST, a bounded repair that IS a real discriminator (red on the pristine source) is
    accepted and the How CONTINUES to the next attempt — it does not end as a red-test
    FAIL. (Contrast (a): an implementation-wrong judge leaves the red test in place and
    the How ends FAIL.)"""
    spec = make_spec()
    stage(tmp_path, spec.files)
    # P3c/FIX 2: the repair must emit a CHANGED test (an identical rewrite is recorded as
    # ``test_repair_unavailable`` and advances the ladder instead of being credited).
    repaired = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert result() == 42  # repaired\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})

    def judge(request: JudgeRequest) -> JudgeVerdict:
        return JudgeVerdict(attribution="tests", raw="tests",
                            defect="test_goal asserts the wrong expectation for AC-1")

    reviews = ScriptedReview([_approving_review])
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge, review=reviews, run_tests=ScriptedTests([1, 1, 0]))

    assert out.test_rewrites == 1
    assert out.attempts[0].layer == "tests"        # the repair, not a red-test FAIL
    assert "test_rewritten" in ledger_kinds()
    # the How CONTINUED: the discriminating repair was accepted and a later fix greened
    assert out.claimed is True and out.state == "pass"
    assert out.claimed_basis == "review"


def test_leaf_state_is_pass_for_a_claim_and_fail_for_an_exhausted_red_test(tmp_path):
    """docs/6_FLOW.md §1.5 S5 (P1c): the leaf's explicit state end-to-end — a discriminating own
    test that greens is PASS; a red own test at exhaustion is FAIL."""
    green = tmp_path / "green"
    spec = make_spec()
    stage(green, spec.files)
    out_green = run_leaf_sync(
        FakeModelRunner({"write_test": [SELF_TEST, impl()]}), spec, green,
        Budget(calls=8, deadline_ts=_FAR_FUTURE), run_tests=ScriptedTests([1, 0]))
    assert out_green.claimed is True and out_green.state == "pass"

    red = tmp_path / "red"
    stage(red, spec.files)
    out_red = run_leaf_sync(
        FakeModelRunner({"write_test": [SELF_TEST] + [impl("def result():\n    return 7\n")] * 6}),
        spec, red, Budget(calls=12, deadline_ts=_FAR_FUTURE),
        run_tests=ScriptedTests([1] * 8))
    assert out_red.claimed is False and out_red.state == "fail"


# ===========================================================================
# P3b (FIX A): an INVERTED independent test — it asserts the PRE-FIX behaviour — must
# not block a correct fix. The signature is deterministic and needs no model call: a
# node id that FAILS on the final revision but PASSED on the pristine pre-run gate is
# "inverted" (evidence the TEST is wrong); one that failed on BOTH gates is "unmet"
# (a genuine unmet criterion) and keeps today's hard block.
# ===========================================================================

def _shaped_iv_tests(original_gate: GateReport, final_gate: GateReport,
                     iv: str = "tests/test_independent.py"):
    """A ``run_tests`` seam shaped like the two deterministic independent-test gates.

    The run's own test (the independent-test file is absent) is GREEN on arrival; the
    independent test's whole-file gate is ``original_gate`` on the pre-run source and
    ``final_gate`` on the fixed source (distinguished by the source content). A
    per-criterion node-id call on the pre-run tree mirrors the requested ids as passing.
    """
    def run(workdir, node_ids=None):
        root = Path(workdir)
        if not (root / iv).exists():
            return ShapedResult(
                command=["python3", "-m", "pytest", "-q"], exit=0, verdict="ok",
                excerpts=[],
                gate=_gate_report("tests/test_leaf_self.py",
                                  passed=("tests/test_leaf_self.py::test_goal",)))
        if node_ids is not None:
            return ShapedResult(
                command=["python3", "-m", "pytest", "-q"], exit=0, verdict="ok",
                excerpts=[], gate=_gate_report(iv, passed=tuple(node_ids)))
        gate = (final_gate if "return 42" in (root / "pkg/calc.py").read_text()
                else original_gate)
        return ShapedResult(
            command=["python3", "-m", "pytest", "-q"],
            exit=0 if gate.green else 1,
            verdict="ok" if gate.green else "failed",
            excerpts=[] if gate.green else [f"FAILED {nid}" for nid in gate.failed_ids],
            gate=gate)
    return run


def test_iv_inversion_evidence_splits_inverted_from_unmet():
    """P3b (FIX A) unit: the deterministic split of the final-revision failures into the
    ids that PASSED on the pristine source (inverted) and the ids that failed on BOTH
    (unmet). A failure present on neither is never excused, and a missing gate is empty."""
    from harness.leaf import iv_all_inverted, iv_inversion_evidence

    iv = "tests/test_independent.py"
    inv = f"{iv}::test_ac1_inverted"
    unmet = f"{iv}::test_ac2_unmet"
    original = _gate_report(iv, passed=(inv,), failed=(unmet,), green=False)
    final = _gate_report(iv, passed=(), failed=(inv, unmet), green=False)

    inverted, unmet_ids = iv_inversion_evidence(original, final)
    assert inverted == (inv,)
    assert unmet_ids == (unmet,)
    partial = IndependentTestVerdict(approved=False,
                                     reason="independent-test-red-on-final",
                                     original_gate=original, final_gate=final)
    assert iv_all_inverted(partial) is False

    all_inverted = _gate_report(iv, passed=(unmet,), failed=(inv,), green=False)
    all_inv = IndependentTestVerdict(approved=False,
                                     reason="independent-test-red-on-final",
                                     original_gate=original, final_gate=all_inverted)
    assert iv_all_inverted(all_inv) is True
    # no report / no failing id / a non-red verdict are never "inverted"
    assert iv_inversion_evidence(None, final) == ((), ())
    assert iv_all_inverted(None) is False
    assert iv_all_inverted(IndependentTestVerdict(
        approved=True, original_gate=original, final_gate=final)) is False


def test_all_inverted_independent_test_does_not_block_the_claim(tmp_path):
    """P3b (FIX A): the independent test is RED on the final revision, but every failing
    node PASSED on the pristine pre-run source (it asserted the pre-fix behaviour, T-01's
    inversion). With no own test, the review must still carry the claim; the inversion is
    recorded with its ids and never blocks."""
    iv = "tests/test_independent.py"
    inverted = f"{iv}::test_ac1_inverted"
    genuine = f"{iv}::test_ac2_genuine"
    original = _gate_report(iv, passed=(inverted,), failed=(genuine,), green=False)
    final = _gate_report(iv, passed=(genuine,), failed=(inverted,), green=False)

    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(), review=_approving_review,
                        run_tests=_shaped_iv_tests(original, final))

    assert out.claimed is True and out.claimed_basis == "review"
    assert out.state == "pass"
    assert out.iv_verdicts[-1].reason == "independent-test-red-on-final"
    assert out.iv_inverted is True
    assert out.iv_inverted_tests == [inverted]
    assert out.iv_unmet_tests == []
    assert "independent_test_inverted" in ledger_kinds()


def test_partially_inverted_independent_test_still_blocks_the_claim(tmp_path):
    """P3b (FIX A): one failing node passed on the pristine source (inverted) but ANOTHER
    failed on BOTH (unmet) — the genuine unmet criterion keeps today's hard block, and the
    inversion is still recorded with its ids."""
    iv = "tests/test_independent.py"
    inverted = f"{iv}::test_ac1_inverted"
    unmet = f"{iv}::test_ac2_unmet"
    original = _gate_report(iv, passed=(inverted,), failed=(unmet,), green=False)
    final = _gate_report(iv, passed=(), failed=(inverted, unmet), green=False)

    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(), review=_approving_review,
                        run_tests=_shaped_iv_tests(original, final))

    assert out.claimed is False
    assert out.stop_reason == "independent-test-red-on-final"
    assert out.iv_inverted is False
    assert out.iv_inverted_tests == [inverted]
    assert out.iv_unmet_tests == [unmet]
    assert out.failure_report is not None and out.failure_report.iv_inverted is False
    assert out.failure_report.iv_unmet_tests == (unmet,)
    assert "independent_test_inverted" in ledger_kinds()


# ===========================================================================
# P3b (FIX B): anchor the graded review to the repository's OWN documentation, and
# honestly label a claim that rests on a review with no observable check.
# ===========================================================================

def test_review_request_carries_the_repository_documentation(tmp_path):
    """P3b (FIX B): the review request carries every non-test, non-grader .md/.txt/.rst
    from the staged repository as GROUND TRUTH, and the driver's review prompt injects it
    with the module-level-functions-vs-class contract rule."""
    from bench.v2_leaf import _review_question

    readme = ("# plugins\n\nPlugin registry: register(name, fn) / get(name) / "
              "run(name, *args).\n")
    files = {"README.md": readme, "plugins/__init__.py": "", "notes.txt": "old notes\n",
             "plugins/registry.py": "class Registry:\n    pass\n"}
    spec = LeafSpec(goal="scaffold the plugin registry", files=files,
                    acs=["Create the registry module"],
                    interfaces=[],
                    grader_paths=("tests/test_plugins.py", "pyproject.toml"),
                    planned_reviews=("ac-correctness", "contract-compat"))
    stage(tmp_path, files)
    request = _review_request(spec, tmp_path, dict.fromkeys(files),
                              "no test could carry it", "contract-compat")

    docs = dict(request.repo_docs)
    assert docs["README.md"] == readme and docs["notes.txt"] == "old notes\n"
    assert "tests/test_plugins.py" not in docs and "pyproject.toml" not in docs
    assert "plugins/registry.py" not in docs          # source, not documentation

    question = _review_question(request)
    assert "REPOSITORY DOCUMENTATION" in question and "GROUND TRUTH" in question
    assert "register(name, fn)" in question
    assert "class that only offers methods is a FAIL" in question


def test_review_only_claim_without_an_observable_check_records_basis_risk(tmp_path):
    """P3b (FIX B): a granted claim that rests on a review while NO observable check
    existed (no own test, independent verification unusable) is LABELLED. The label never
    changes the grant (T-28's false-success shape stays a grant here — that is the
    owner's rule — but the record is now honest about its basis)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        review=_approving_review, run_tests=ScriptedTests([0, 0, 0]))

    assert out.claimed is True and out.claimed_basis == "review"
    assert out.self_test is None
    assert out.basis_risk == "review-only-no-observable-check"


def test_basis_risk_is_absent_when_an_observable_check_existed(tmp_path):
    """P3b (FIX B): the label is only for a review-only claim with no observable check.
    An own-test claim (an observed check carried it) and a review that an independent
    verification AGREED with both carry no label."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=6, deadline_ts=_FAR_FUTURE),
                        iv=lambda request: iv_candidate(), run_tests=ScriptedTests([1, 0, 1, 1]))
    assert out.claimed is True and out.claimed_basis == "own-test"
    assert out.basis_risk == ""

    agreed = claim_decision(
        route="review", criteria_count=1, ledger=_gate_ledger(),
        own_test=None, own_test_green=False, test_rewrites=0, iv_approved=True,
        review_approved=True, review_verdicts=(_grounded_review(),),
        verification_basis="review", tier_allowed=True)
    assert agreed.claimed is True and agreed.basis == "review+independent-test"
    assert agreed.basis_risk == ""


def test_run_record_carries_basis_risk_and_iv_inversion_fields():
    """P3b: the new fields survive the run record (``json.dumps``) so the measurement can
    read them directly."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    iv = "tests/test_independent.py"
    inverted = f"{iv}::test_ac1_inverted"
    original = _gate_report(iv, passed=(inverted,), failed=(), green=False)
    final = _gate_report(iv, passed=(), failed=(inverted,), green=False)
    outcome = LeafOutcome(
        claimed=True, signal="green", attempts=[], calls=3, wall_s=1.0, self_test=None,
        questions=[], exhausted=False, exhaustion_reason="", layers_used=[],
        stop_reason="green", verification_basis="review", claimed_basis="review",
        basis_risk="review-only-no-observable-check",
        iv_inverted=True, iv_inverted_tests=[inverted], iv_unmet_tests=[],
        iv_verdicts=[IndependentTestVerdict(
            approved=False, reason="independent-test-red-on-final",
            original_gate=original, final_gate=final)])
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[],
                          skipped=[])

    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="true-success", run_wall_s=1.0, review_enabled=True)

    assert record["basis_risk"] == "review-only-no-observable-check"
    assert record["iv_inverted"] is True
    assert record["iv_inverted_tests"] == [inverted]
    assert record["iv_unmet_tests"] == []
    json.dumps(record)


# ===========================================================================
# P3c: the three fixes from the 2026-10-08 20-task measurement (T-05/T-12/T-16).
# ===========================================================================


def _own_gate(*, passed=(), failed=(), green=False) -> GateReport:
    """A scripted report whose own-test node ids are explicit (passed = green on pristine,
    failed = red on pristine)."""
    return GateReport(report_path="(scripted)", process_exit=0 if green else 1,
                      canary="scripted", expected_files=(),
                      n_tests=len(passed) + len(failed), n_failed=len(failed), n_errors=0,
                      passed_ids=tuple(passed), failed_ids=tuple(failed), missing=(),
                      observed=True, anomaly="" if green else "tests-failed",
                      detail="" if green else "1 failure(s)")


def _own_result(*, passed=(), failed=(), green=False) -> ShapedResult:
    return ShapedResult(command=["python3", "-m", "pytest", "-q"],
                        exit=0 if green else 1, verdict="ok" if green else "failed",
                        excerpts=[] if green else ["FAILED"],
                        gate=_own_gate(passed=passed, failed=failed, green=green))


def test_own_test_partition_splits_red_from_green_on_pristine():
    """FIX 1: the run's own test cases split into DISCRIMINATING (red on the pristine
    source) and symptom-asserting (green there); the split is scoped to the own test
    FILE, so the canary or any other collected file can never count."""
    from harness.leaf import _own_test_partition

    gate = _own_gate(passed=("t/test_x.py::test_symptom",),
                     failed=("t/test_x.py::test_goal",))
    disc, symptom = _own_test_partition(gate, "t/test_x.py")
    assert disc == ("t/test_x.py::test_goal",)
    assert symptom == ("t/test_x.py::test_symptom",)
    # a node id from another file (the canary) is never counted.
    other = _own_gate(passed=("tests/test_gate_canary_x.py::test_canary",))
    assert _own_test_partition(other, "t/test_x.py") == ((), ())
    # an unobserved report yields no split at all.
    assert _own_test_partition(None, "t/test_x.py") == ((), ())


def test_drop_test_functions_removes_only_named_top_level_cases():
    """FIX 1: a surviving symptom case is DROPPED from the target by excising its
    top-level definition and nothing else."""
    from harness.leaf import _drop_test_functions

    src = ("import pytest\n\n\n"
           "def test_goal():\n    assert 1\n\n\n"
           "def test_symptom():\n    assert 2\n\n\n"
           "class TestGroup:\n    def test_method(self):\n        assert 3\n")
    dropped = _drop_test_functions(src, ["f.py::test_symptom"])
    assert "def test_symptom" not in dropped
    assert "def test_goal" in dropped and "import pytest" in dropped
    assert "def test_method" in dropped          # a class method is not top-level
    # an unknown name / a class method leaves the source unchanged.
    assert _drop_test_functions(src, ["f.py::nope"]) == src
    assert _drop_test_functions(src, ["f.py::test_method"]) == src


def test_own_test_symptom_case_is_rewritten_then_dropped_from_the_target(tmp_path):
    """FIX 1 (T-12/T-16): an own test file with one DISCRIMINATING case (red on pristine)
    and one symptom-asserting case (green there) gets ONE bounded rewrite of the symptom
    case; when the rewrite leaves it green it is DROPPED from the target and recorded, so
    the loop never iterates to satisfy a case that asserts the reported symptom."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    own_content = ("def test_goal():\n    assert result() == 42\n\n\n"
                   "def test_symptom():\n    assert result() == 0\n")
    own = write_env("tests/test_leaf_self.py", own_content)
    same = write_env("tests/test_leaf_self.py", own_content)   # the rewrite changes nothing
    goal = "tests/test_leaf_self.py::test_goal"
    symptom = "tests/test_leaf_self.py::test_symptom"
    mixed = _own_result(passed=(symptom,), failed=(goal,))
    after_drop = _own_result(failed=(goal,))
    model = FakeModelRunner({"write_test": [own, same, impl(), impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([mixed, mixed, after_drop, after_drop,
                                                 after_drop]))

    assert out.own_test_discriminating == [goal]
    assert out.own_test_symptom_ids == [symptom]
    assert "own_test_partition" in ledger_kinds()
    assert "own_test_symptom_dropped" in ledger_kinds()
    text = (tmp_path / "tests/test_leaf_self.py").read_text()
    assert "def test_symptom" not in text         # dropped from the target
    assert "def test_goal" in text                # the discriminating target survives


def test_own_test_symptom_rewrite_to_the_desired_state_keeps_the_case(tmp_path):
    """FIX 1: when the bounded rewrite turns the symptom case into a discriminator
    (green-on-pristine -> red), it is KEPT and nothing is dropped."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    own = write_env("tests/test_leaf_self.py",
                    "def test_goal():\n    assert result() == 42\n\n\n"
                    "def test_symptom():\n    assert result() == 0\n")
    rewritten = write_env("tests/test_leaf_self.py",
                          "def test_goal():\n    assert result() == 42\n\n\n"
                          "def test_symptom():\n    assert result() == 42\n")
    goal = "tests/test_leaf_self.py::test_goal"
    symptom = "tests/test_leaf_self.py::test_symptom"
    mixed = _own_result(passed=(symptom,), failed=(goal,))
    both_red = _own_result(failed=(goal, symptom))
    model = FakeModelRunner({"write_test": [own, rewritten, impl(), impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([mixed, both_red, both_red, both_red]))

    assert out.own_test_symptom_ids == []
    assert set(out.own_test_discriminating) == {goal, symptom}
    assert "own_test_symptom_dropped" not in ledger_kinds()
    assert "def test_symptom" in (tmp_path / "tests/test_leaf_self.py").read_text()


def test_run_record_carries_the_own_test_partition():
    """FIX 1: the own-test split rides the persisted run record (survives json.dumps)."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=3, wall_s=1.0,
        self_test="tests/test_leaf_self.py", questions=[], exhausted=False,
        exhaustion_reason="attempts", layers_used=["sampling"], stop_reason="attempts",
        own_test_discriminating=["tests/test_leaf_self.py::test_goal"],
        own_test_symptom_ids=["tests/test_leaf_self.py::test_symptom"])
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[],
                          skipped=[])
    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)

    assert record["own_test_discriminating"] == ["tests/test_leaf_self.py::test_goal"]
    assert record["own_test_symptom_ids"] == ["tests/test_leaf_self.py::test_symptom"]
    json.dumps(record)


def test_credited_test_wrong_that_cannot_change_the_test_is_visible_and_advances(tmp_path):
    """FIX 2 (T-05): a credited ``test_wrong`` whose bounded repair emits the SAME test is
    visible as ``test_repair_unavailable`` (never a silent implementation retry against the
    unchanged test) and ADVANCES the ladder."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    same = write_env("tests/test_leaf_self.py", SELF_TEST["content"])

    seen: list[int] = []

    def judge(request: JudgeRequest) -> JudgeVerdict:
        # credit ``test_wrong`` for the FIRST (volunteered) claim; a later proactive
        # consultation is a plain implementation attribution so only the unchanged repair
        # is exercised here.
        seen.append(1)
        if len(seen) == 1:
            return judge_blames_test(request)
        return JudgeVerdict(attribution="implementation", raw="implementation",
                            defect="the implementation returns the wrong value")

    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), same, impl(), impl(),
                                              impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        judge=judge, run_tests=ScriptedTests([1] * 10))

    assert "test_repair_unavailable" in ledger_kinds()
    assert out.test_rewrites == 0 and out.own_test_mutated is False
    # the repair is a recorded attempt (not silently skipped) and the ladder advanced.
    assert out.attempts and out.attempts[0].layer == "tests"
    assert "implementation" in out.layers_used
    assert (tmp_path / "tests/test_leaf_self.py").read_text() == SELF_TEST["content"]


def test_credited_test_wrong_rewrite_replaces_the_test_before_the_next_attempt(tmp_path):
    """FIX 2: a credited ``test_wrong`` whose bounded repair DOES change the test leads to
    a ``test_rewritten`` event and the next attempt runs against the NEW test (the repair
    is the target, never the old one)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    repaired = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert result() == 7\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, blocked(), repaired, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        judge=judge_blames_test, run_tests=ScriptedTests([1, 1, 0]))

    assert "test_rewritten" in ledger_kinds()
    assert out.test_rewrites == 1
    assert out.attempts[0].layer == "tests"
    # the next implementation attempt (the one AFTER the repair) carried the REWRITTEN
    # test as the target — never the old test.
    implement_calls = model.calls("implement_write")
    assert len(implement_calls) >= 2
    assert implement_calls[-1].artifacts["self_test"] == repaired["content"]


def test_no_change_delivery_is_recorded_and_never_a_claim(tmp_path):
    """FIX 3 (T-05): a delivered revision that changes nothing is a first-class outcome —
    ``stop_reason="no-change-delivery"``, state ``fail``, never a claim, and not presented
    as best evidence."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    same = impl("def result():\n    return 0\n", comment="no change")
    model = FakeModelRunner({"write_test": [SELF_TEST, same, same, same]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1] * 6))

    assert out.claimed is False
    assert out.stop_reason == "no-change-delivery"
    assert out.state == "fail"
    assert out.signal == "honest-failure"
    assert "no_change_delivery" in ledger_kinds()
    assert out.delivered_revision.get("no_change_delivery") is True
    assert out.failure_report is not None
    assert out.failure_report.stop_reason == "no-change-delivery"


def test_a_real_change_is_not_a_no_change_delivery(tmp_path):
    """FIX 3: a revision that really changes a source file is never mislabelled."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST, impl("def result():\n    return 42\n"),
                                            impl("def result():\n    return 42\n")]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=8, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0, 0]))

    assert out.stop_reason != "no-change-delivery"
    assert "no_change_delivery" not in ledger_kinds()
    assert out.claimed is True


# ===========================================================================
# P3d/FIX 2: the documented-API contract (the T-28 false success).
# ===========================================================================


def _doc_spec(tmp_path: Path, readme: str, goal: str):
    """A spec whose blind view ships ``readme`` as the repository's own documentation."""
    files = {"README.md": readme, "plugins/__init__.py": ""}
    spec = make_spec(files=files, goal=goal)
    stage(tmp_path, files)
    return spec


def test_documented_api_names_are_call_forms_only(tmp_path):
    """P3d: the documented names are the identifiers in CALL form (adjacent paren) in the
    repo's OWN docs; prose with a space before a paren and a bare backticked word are never
    taken (they are fields/parameters/methods on this corpus, not a module-level API)."""
    from harness.leaf import documented_api_names

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args). Sessions last one hour (documented).\n",
                     "Create plugins/registry.py: register/get/run.")
    assert documented_api_names(spec) == ("get", "register", "run")


def test_documented_api_prose_that_merely_contains_words_does_not_trigger(tmp_path):
    """P3d: a doc with no call form names nothing, so the check is silent (never a false
    block)."""
    from harness.leaf import documented_api_names, documented_api_problem

    spec = _doc_spec(tmp_path, "# plugins\n\nA plugin registry with register, get and "
                     "run helpers. The module is documented in prose only.\n",
                     "Create plugins/registry.py.")
    assert documented_api_names(spec) == ()
    assert documented_api_problem(spec, tmp_path, {}) == []


def test_documented_api_class_only_module_blocks_with_a_targeted_message(tmp_path):
    """P3d/T-28: a module that delivers the documented call-form names ONLY as methods of a
    class is NOT module level and blocks, with the targeted message the next attempt needs."""
    from harness.leaf import documented_api_problem

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args).\n",
                     "Create plugins/registry.py: register/get/run.")
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins/registry.py").write_text(
        "class Registry:\n"
        "    def register(self, name, fn): pass\n"
        "    def get(self, name): pass\n"
        "    def run(self, name, *args): pass\n")
    problem = documented_api_problem(spec, tmp_path, {})
    assert len(problem) == 1
    assert "register" in problem[0] and "get" in problem[0] and "run" in problem[0]
    assert "plugins/registry.py" in problem[0] and "Registry" in problem[0]


def test_documented_api_honest_module_level_functions_pass(tmp_path):
    """P3d: the honest shape — the documented names as module-level functions — passes."""
    from harness.leaf import documented_api_problem

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args).\n",
                     "Create plugins/registry.py: register/get/run.")
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins/registry.py").write_text(
        "def register(name, fn): pass\n"
        "def get(name): return None\n"
        "def run(name, *args): pass\n")
    assert documented_api_problem(spec, tmp_path, {}) == []


def test_documented_api_a_module_level_import_satisfies_the_contract(tmp_path):
    """P3d: a documented name the module legitimately exposes as an import IS module level,
    so it passes."""
    from harness.leaf import documented_api_problem

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args).\n",
                     "Create plugins/registry.py: register/get/run.")
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins/registry.py").write_text(
        "from ._impl import register, get, run\n")
    assert documented_api_problem(spec, tmp_path, {}) == []


def test_documented_api_class_member_bindings_are_not_module_level(tmp_path):
    """P3e/T-28: the fixes the model reaches for when the class-only module is blocked are
    NOT the documented module-level API, so the contract still blocks with the targeted
    message. Three measured evasions, each answering the documented call form with a
    runtime failure (or a throwaway instance) exactly as the class-only shape does:

    * ``register = Registry.register`` — the UNBOUND method (needs ``self``);
    * ``register = Registry()`` — an instance, not a function;
    * ``get = Registry().get`` — a member of a fresh throwaway instance.

    ``module_level_names`` counted all three as module-level bindings, which is how the
    measured T-28 false-success survived."""
    from harness.leaf import documented_api_problem, module_level_names

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args).\n",
                     "Create plugins/registry.py: register/get/run.")
    (tmp_path / "plugins").mkdir(exist_ok=True)
    cls = ("class Registry:\n"
           "    def register(self, name, fn): pass\n"
           "    def get(self, name): pass\n"
           "    def run(self, name, *args): pass\n")
    unbound = cls + ("register = Registry.register\n"
                     "get = Registry.get\n"
                     "run = Registry.run\n")
    instance = cls + ("register = Registry()\n"
                      "get = Registry()\n"
                      "run = Registry()\n")
    bound = cls + ("register = Registry().register\n"
                   "get = Registry().get\n"
                   "run = Registry().run\n")
    for source in (unbound, instance, bound):
        (tmp_path / "plugins/registry.py").write_text(source)
        assert module_level_names(source) == set(), source
        problem = documented_api_problem(spec, tmp_path, {})
        assert len(problem) == 1, source
        assert "register" in problem[0] and "get" in problem[0] and "run" in problem[0]
        assert "plugins/registry.py" in problem[0] and "Registry" in problem[0]


def test_documented_api_static_method_alias_counts_as_module_level(tmp_path):
    """P3e: an alias to a STATIC method (callable without an instance) IS the documented
    call form, so it counts — the alias rule targets only plain instance methods."""
    from harness.leaf import documented_api_problem, module_level_names

    spec = _doc_spec(tmp_path, "# plugins\n\nPlugin registry: register(name, fn) / "
                     "get(name) / run(name, *args).\n",
                     "Create plugins/registry.py: register/get/run.")
    (tmp_path / "plugins").mkdir(exist_ok=True)
    source = ("class Registry:\n"
              "    @staticmethod\n"
              "    def register(name, fn): pass\n"
              "    @staticmethod\n"
              "    def get(name): pass\n"
              "    @staticmethod\n"
              "    def run(name, *args): pass\n"
              "register = Registry.register\n"
              "get = Registry.get\n"
              "run = Registry.run\n")
    (tmp_path / "plugins/registry.py").write_text(source)
    assert module_level_names(source) == {"register", "get", "run"}
    assert documented_api_problem(spec, tmp_path, {}) == []


def test_documented_api_missing_blocks_every_claim_route():
    """P3d: the documented-API miss is a HARD block in the ONE claim gate on every route."""
    base = {
        "criteria_count": 1, "ledger": _gate_ledger(), "own_test": "tests/t.py",
        "own_test_green": True, "test_rewrites": 0, "iv_approved": False,
        "iv_red_on_final": False, "review_approved": False, "review_verdicts": (),
        "coverage_missing": (), "test_case_problems": (),
        "verification_basis": "test", "tier_allowed": True,
    }
    miss = ["the repository documents register as module-level names; your "
            "plugins/registry.py exposes them only as methods of Registry"]
    blocked = claim_decision(route="own-test", **base, documented_api_missing=miss)
    assert blocked.claimed is False and blocked.blocker == "documented-api-missing"
    assert "register" in blocked.detail
    # the same revision WITHOUT the miss claims (the check is the only difference)
    assert claim_decision(route="own-test", **base).claimed is True


def test_run_record_carries_the_documented_api_missing_field():
    """P3d: the documented-API miss rides the persisted run record."""
    from bench.external_score import ExternalScore
    from bench.v2_leaf import build_record

    outcome = LeafOutcome(
        claimed=False, signal="honest-failure", attempts=[], calls=3, wall_s=1.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="attempts",
        layers_used=["sampling"], stop_reason="attempts",
        documented_api_missing=["the repository documents register as module-level names"])
    score = ExternalScore(passed=False, exit=1, notes=[], work_root="", applied=[],
                          skipped=[])
    record = build_record("T-x", "goal", outcome, withheld=[], produced={}, score=score,
                          quad="honest-failure", run_wall_s=1.0)
    assert record["documented_api_missing"] == outcome.documented_api_missing
    json.dumps(record)


# ===========================================================================
# P3d/FIX 1: the self-contradicting own test (the T-12 deviation).
# ===========================================================================


def test_own_test_contradictions_find_the_t12_shape():
    """P3d/FIX 1: a case asserting ``f(x)`` and one asserting ``not f(x)`` for the SAME
    inlined input contradict; the red one is unreliable and the green one is preserved."""
    from harness.leaf import _own_test_contradictions

    source = ("from access.gate import Author, can_publish\n"
              "from access.roles import Role\n\n\n"
              "def test_editor_rejected():\n"
              "    author = Author('e', Role.EDITOR)\n"
              "    assert not can_publish(author)\n\n\n"
              "def test_editor_allowed():\n"
              "    author = Author('e', Role.EDITOR)\n"
              "    assert can_publish(author)\n")
    unreliable, preserved = _own_test_contradictions(
        source, ["t.py::test_editor_rejected"], ["t.py::test_editor_allowed"])
    assert unreliable == ("t.py::test_editor_rejected",)
    assert preserved == {"t.py::test_editor_allowed"}


def test_own_test_contradictions_ignore_distinct_inputs():
    """P3d/FIX 1: opposite polarity on DIFFERENT inputs (a viewer rejected, an admin
    allowed) is NOT a contradiction and must not be mislabelled."""
    from harness.leaf import _own_test_contradictions

    source = ("def test_admin_allowed():\n"
              "    author = Author('a', Role.ADMIN)\n"
              "    assert can_publish(author)\n\n\n"
              "def test_viewer_rejected():\n"
              "    author = Author('v', Role.VIEWER)\n"
              "    assert not can_publish(author)\n")
    assert _own_test_contradictions(
        source, ["t.py::test_admin_allowed"], ["t.py::test_viewer_rejected"]) == ((), set())


def test_own_test_contradiction_drops_the_symptom_case_and_keeps_the_desired_one(tmp_path):
    """P3d/FIX 1 (T-12): when a case RED on the pristine source contradicts a green case,
    the RED case asserts the reported symptom: it is dropped, and the green case (the
    desired behaviour) is PRESERVED — never dropped as P3c used to (that was the deviation
    that left only the symptom-asserting case as the target)."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    own = ("def test_symptom_rejected():\n    assert not (result() == 42)\n\n\n"
           "def test_desired_allowed():\n    assert result() == 42\n")
    same = write_env("tests/test_leaf_self.py", own)   # the bounded rewrite changes nothing
    red = "tests/test_leaf_self.py::test_symptom_rejected"
    green = "tests/test_leaf_self.py::test_desired_allowed"
    mixed = _own_result(passed=(green,), failed=(red,))
    after_drop = _own_result(passed=(green,))
    model = FakeModelRunner({"write_test": [write_env("tests/test_leaf_self.py", own), same,
                                            impl(), impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([mixed, mixed, after_drop, after_drop]))

    assert "own_test_contradiction" in ledger_kinds()
    assert red in out.own_test_symptom_ids
    text = (tmp_path / "tests/test_leaf_self.py").read_text()
    assert "def test_desired_allowed" in text          # PRESERVED (the T-12 fix)
    assert "def test_symptom_rejected" not in text      # dropped


def test_own_test_contradictions_link_two_names_through_a_green_equality():
    """P3d/FIX 1: the T-12 variant where the symptom case and the desired case use two
    different author names — a GREEN ``assert f(a) == f(b)`` licenses treating them as the
    same predicate, so the contradiction is still caught."""
    from harness.leaf import _own_test_contradictions

    source = ("from access.gate import Author, can_publish\n"
              "from access.roles import Role\n\n\n"
              "def test_webhook_editor_cannot_publish():\n"
              "    author = Author('editor_webhook', Role.EDITOR)\n"
              "    assert can_publish(author) is False\n\n\n"
              "def test_app_ui_editor_can_publish():\n"
              "    author = Author('editor_app', Role.EDITOR)\n"
              "    assert can_publish(author) is True\n\n\n"
              "def test_equal_roles_are_equal():\n"
              "    webhook_author = Author('editor_webhook', Role.EDITOR)\n"
              "    app_author = Author('editor_app', Role.EDITOR)\n"
              "    assert can_publish(webhook_author) == can_publish(app_author)\n")
    unreliable, preserved = _own_test_contradictions(
        source, ["t.py::test_webhook_editor_cannot_publish"],
        ["t.py::test_app_ui_editor_can_publish", "t.py::test_equal_roles_are_equal"])
    assert unreliable == ("t.py::test_webhook_editor_cannot_publish",)
    assert "t.py::test_app_ui_editor_can_publish" in preserved


def test_own_test_contradictions_ignore_legitimate_opposite_inputs():
    """P3d/FIX 1: opposite outcomes for DIFFERENT inputs (an enterprise plan vs a pro plan)
    with no equality licensing them are legitimate and must not be mislabelled."""
    from harness.leaf import _own_test_contradictions

    source = ("from billing.plans import is_enterprise, parse_webhook\n\n\n"
              "def test_is_enterprise_detects_webhook_plan():\n"
              "    parsed = parse_webhook('plan=enterprise')\n"
              "    assert is_enterprise(parsed['plan'])\n\n\n"
              "def test_is_enterprise_false_for_non_enterprise():\n"
              "    parsed = parse_webhook('plan=pro')\n"
              "    assert not is_enterprise(parsed['plan'])\n")
    assert _own_test_contradictions(
        source, ["t.py::test_is_enterprise_detects_webhook_plan"],
        ["t.py::test_is_enterprise_false_for_non_enterprise"]) == ((), set())


def test_own_test_contradictions_ignore_stateful_tests():
    """P3d/FIX 1: a test that mutates state between otherwise identical calls (push then
    is_empty) asserts both polarities by design and is never a contradiction."""
    from harness.leaf import _own_test_contradictions

    source = ("def test_not_empty_after_push():\n"
              "    s = Stack()\n"
              "    s.push(1)\n"
              "    assert s.is_empty() is False\n\n\n"
              "def test_empty_again_after_pop():\n"
              "    s = Stack()\n"
              "    s.push(1)\n"
              "    s.pop()\n"
              "    assert s.is_empty() is True\n")
    assert _own_test_contradictions(
        source, ["t.py::test_not_empty_after_push"],
        ["t.py::test_empty_again_after_pop"]) == ((), set())


# --------------------------------------------------------------------------- P4a
# Four mechanisms, each traced to a quoted trajectory record from the 2026-10-08
# 40-task run. M1 an incoherent judge label; M2 a review claim over a contradicting
# verdict; M3 an unparseable delivered source; M4 a false RED that must not block.

#: The T-05 blind view: the source defines ``add_tag``; the own test asserts through the
#: literal ``'tags'`` so the LOOSE anchor set admits the judge reason that names the
#: source symbol ``add_tag`` (the seq294 inversion).
_T05_SOURCE = {
    "tagger/notes.py": (
        "def add_tag(note, tag, tags=None):\n"
        "    if tags is None:\n"
        "        tags = []\n"
        "    tags.append(tag)\n"
        "    note['tags'] = tags\n"
        "    return tags\n"),
}
_T05_TEST = (
    "def test_add_tag_returns_updated_tags():\n"
    "    note = {'id': 1}\n"
    "    assert note['tags'] == ['errand']\n")


def _t05_request() -> JudgeRequest:
    return JudgeRequest(goal="fix the tagger", failure="FAILED test_tag_isolation.py",
                        test_path="test_tag_isolation.py", test_content=_T05_TEST,
                        files=_T05_SOURCE)


def test_m1_incoherent_test_wrong_that_names_the_source_is_uncredited():
    """M1 (T-05 pass 2, seq294): the judge said ``test_wrong`` but its reason named the
    IMPLEMENTATION defect ("The add_tag function mutates the shared tags list ..."). The
    loose anchor set admits the bare word ``tags``, so the verdict used to be credited.
    It must now be UNCREDITED (``judge_incoherent``) and kept on the implementation path."""
    request = _t05_request()
    verdict = JudgeVerdict(
        attribution="tests",
        reason="The add_tag function mutates the shared tags list, causing tags to bleed.",
        defect="The add_tag function mutates the shared tags list, causing tags to bleed.")
    filtered = apply_judge_filter(verdict, request)
    assert filtered.test_wrong is False
    assert filtered.implementation_wrong is True
    assert filtered.coerced is True
    assert filtered.coercion_reason.startswith("judge_incoherent")
    assert _judge_incoherence(verdict, request).startswith("judge_incoherent")


def test_m1_incoherent_implementation_wrong_that_names_only_a_test_is_recorded():
    """M1's mirror: a credited ``implementation_wrong`` whose reason names only a
    test/assertion is recorded ``judge_incoherent`` and kept on the implementation path."""
    request = _t05_request()
    verdict = JudgeVerdict(
        attribution="implementation",
        reason="test_add_tag_returns_updated_tags asserts the wrong expectation",
        defect="test_add_tag_returns_updated_tags asserts the wrong expectation")
    filtered = apply_judge_filter(verdict, request)
    assert filtered.coerced is True
    assert filtered.coercion_reason.startswith("judge_incoherent")
    assert filtered.implementation_wrong is True


def test_m1_coherent_test_wrong_naming_the_test_stays_credited():
    """M1 does not over-coerce: a ``test_wrong`` that names the failing test FUNCTION is
    coherent and still credited."""
    request = _t05_request()
    verdict = JudgeVerdict(
        attribution="tests",
        reason=("test_add_tag_returns_updated_tags expects ['errand'] but the shared "
                "list behaviour it asserts is wrong"),
        defect=("test_add_tag_returns_updated_tags expects ['errand'] but the shared "
                "list behaviour it asserts is wrong"))
    filtered = apply_judge_filter(verdict, request)
    assert filtered.test_wrong is True and filtered.coerced is False


def test_m1_incoherent_verdict_is_recorded_and_the_source_fix_is_credited(tmp_path):
    """M1 end-to-end: the incoherent verdict does not take the test-repair path; the
    failure stays on the implementation path and the source fix can still green, with
    ``judge_incoherent`` recorded on the outcome."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    model = FakeModelRunner({"write_test": [SELF_TEST,
                                            impl("def result():\n    return 1\n"),
                                            impl("def result():\n    return 42\n")]})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=10, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(
            attribution="tests",
            defect="the result function returns 1, so `result() == 42` fails"),
        run_tests=ScriptedTests([1, 1, 0]))
    assert out.judge_incoherent == 1
    assert "judge_incoherent" in ledger_kinds()
    assert out.claimed is True and out.signal == "green"
    assert out.judge_verdicts[0].test_wrong is False
    assert out.judge_verdicts[0].coercion_reason.startswith("judge_incoherent")


def _m2_review_base() -> dict:
    return {
        "route": "review", "criteria_count": 1, "ledger": _gate_ledger(),
        "own_test": None, "own_test_green": False, "test_rewrites": 0,
        "iv_approved": False, "review_approved": True,
        "review_verdicts": (_grounded_review(),), "verification_basis": "review",
        "tier_allowed": True,
    }


def test_m2_review_claim_refused_when_a_judge_flagged_the_same_revision():
    """M2 (T-12 false success): the judge named the ``is``-comparison defect, the review
    approved the opposite, and the run still claimed green. A review-route claim now
    additionally requires that no judge consultation on the SAME revision recorded
    ``implementation_wrong``; the conflict is recorded and the claim refused."""
    base = _m2_review_base()
    assert claim_decision(**base).claimed is True
    blocked = claim_decision(
        **base, judge_implementation_wrong=True,
        judge_implementation_wrong_detail="can_publish uses identity comparison (is)")
    assert blocked.claimed is False
    assert blocked.blocker == "judge-implementation-wrong"
    assert "implementation_wrong" in blocked.disagreement
    assert "identity comparison" in blocked.disagreement


def test_m2_review_claim_refused_on_a_non_discriminating_independent_verdict():
    """M2 + P5(b) FIX (the T-13 #2 false success): a NON-DISCRIMINATING independent
    verdict cannot corroborate the review, so it BLOCKS the review-backed claim instead of
    being labelled and granted. The run is UNCERTAIN; the check is named in the
    disagreement/detail and the ``basis_risk`` says why."""
    base = _m2_review_base()
    blocked = claim_decision(
        **base, iv_non_discriminating=True,
        iv_non_discriminating_detail="independent-test-not-red: it PASSED on the pre-run source")
    assert blocked.claimed is False
    assert blocked.blocker == "independent-test-non-discriminating"
    assert "NON-DISCRIMINATING" in blocked.disagreement
    assert "pre-run source" in blocked.disagreement
    assert blocked.detail == "independent-test-not-red: it PASSED on the pre-run source"
    assert blocked.basis_risk == "review-over-non-discriminating-check"


def test_p5b_a_non_discriminating_independent_check_can_never_carry_a_review_claim():
    """P5(b) FIX (the T-13 #2 residual lie): a review-route claim may NOT be granted on a
    non-discriminating independent check in ANY of its states --- it passed on the pristine
    source, the report was ABSENT/could not be observed or was errors-only, it covered no
    criterion, or it reused one. Only a genuinely discriminating APPROVING independent
    check corroborates the review, and that path still grants.

    This test fails if a non-discriminating independent check can again carry a pass
    claim."""
    base = _m2_review_base()
    # The two paths that MUST keep granting: no independent check at all (review-only),
    # and an APPROVING (discriminating) independent check.
    assert claim_decision(**base).claimed is True
    assert claim_decision(**{**base, "iv_approved": True}).claimed is True
    for detail in (
        "independent-test-not-red: it PASSED on the pre-run source",
        "independent-test-unobserved: the report is absent (0 failure(s), 3 error(s))",
        "independent-test-not-discriminating: AC1 still PASSES on the pre-run source",
        "independent-test-incomplete-coverage: no node for AC2",
        "independent-test-shared-coverage: one node serves AC1 and AC2",
    ):
        blocked = claim_decision(
            **base, iv_non_discriminating=True, iv_non_discriminating_detail=detail)
        assert blocked.claimed is False, detail
        assert blocked.blocker == "independent-test-non-discriminating", detail
        assert blocked.basis_risk == "review-over-non-discriminating-check", detail


def test_m2_a_clean_review_claim_still_grants():
    """M2 must not weaken the honest review route: with no judge conflict and no
    non-discriminating independent verdict the review still carries the claim."""
    assert claim_decision(**_m2_review_base()).claimed is True


def test_m3_unparseable_source_is_found_and_the_test_path_is_ignored(tmp_path):
    """M3: the deterministic compile check answers on the produced SOURCE; a broken test
    path (grader-owned) is not part of it."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "calc.py").write_text("def result(:\n    return 42\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_(")
    path, detail = _unparseable_source(tmp_path)
    assert path == "pkg/calc.py"
    assert detail.startswith("pkg/calc.py:")


def test_m3_parseable_source_is_clean(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 42\n")
    assert _unparseable_source(tmp_path) == ("", "")


def test_m3_unparseable_delivery_is_recorded_and_blocks_the_claim(tmp_path):
    """M3 (T-13 pass 2): a delivered module that does not compile blocks the claim
    (``source_unparseable``) and drives another iteration; only the later parseable
    revision may claim."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    broken = impl("def result(:\n    return 42\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, broken, impl()]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=12, deadline_ts=_FAR_FUTURE),
                        run_tests=ScriptedTests([1, 0, 0]))
    assert "source_unparseable" in ledger_kinds()
    assert out.claimed is True
    # the delivered (claimed) revision is parseable, so the run-level record is clean at
    # delivery while the earlier block is still visible in the ledger
    assert out.source_unparseable == ""


def test_m4_gate_blocks_only_on_an_observed_real_failure():
    """M4: only an observed report with a real test FAILURE may block a claim; an
    errors/collection-only red and an unobserved report do not."""
    real = GateReport(report_path="(scripted)", process_exit=1, canary="c",
                      expected_files=(), n_tests=3, n_failed=2, n_errors=1, passed_ids=(),
                      failed_ids=("t.py::a", "t.py::b"), missing=(), observed=True,
                      anomaly="tests-failed", detail="2 failure(s), 1 error(s)")
    errors_only = dataclasses.replace(real, n_failed=0, n_errors=3,
                                      detail="0 failure(s), 3 error(s)")
    unobserved = dataclasses.replace(real, observed=False, anomaly="no-tests",
                                     n_failed=0, n_errors=0, failed_ids=())
    assert _gate_blocks_as_red(real) is True
    assert _gate_blocks_as_red(errors_only) is False
    assert _gate_blocks_as_red(unobserved) is False
    assert _gate_blocks_as_red(scripted_gate()) is False


def test_m4_a_false_own_red_does_not_block_a_non_review_claim():
    """M4 (the false-red class): the run's own red blocks only when it is real evidence.
    A non-evidence own red with a passing independent test must NOT become a
    verifier-conflict; the independent route still claims."""
    base = {
        "route": "independent-test", "criteria_count": 1, "ledger": _gate_ledger(),
        "own_test": "tests/t.py", "own_test_green": False, "test_rewrites": 0,
        "iv_approved": True, "iv_red_on_final": False, "review_approved": False,
        "review_verdicts": (), "coverage_missing": (), "test_case_problems": (),
        "verification_basis": "reason", "tier_allowed": True,
        "conflict_detail": "own red vs iv green",
    }
    conflict = claim_decision(**base, own_test_red_is_evidence=True)
    assert conflict.claimed is False and conflict.conflict is True
    defused = claim_decision(**base, own_test_red_is_evidence=False)
    assert defused.claimed is True and defused.basis == "independent-test"


def test_m4_an_honest_own_red_still_blocks():
    """M4 does not weaken the honest block: an observed, discriminating real failure
    still refuses the claim."""
    blocked = claim_decision(
        route="own-test", criteria_count=1, ledger=_gate_ledger(),
        own_test="tests/t.py", own_test_green=False, test_rewrites=0,
        iv_approved=False, iv_red_on_final=False, review_approved=False,
        review_verdicts=(), coverage_missing=(), test_case_problems=(),
        verification_basis="test", tier_allowed=True, own_test_red_is_evidence=True)
    assert blocked.claimed is False and blocked.blocker == "own-test-red"


def test_m2_review_claim_blocked_end_to_end_on_the_t12_shape(tmp_path):
    """M2 end-to-end (the T-12 false success): the run cannot make its own test red, so
    it enters REVIEW mode; the judge records ``implementation_wrong`` on the delivered
    revision, the review approves, and the independent verdict is NON-DISCRIMINATING.
    The review-route claim must be REFUSED (recorded in ``verification_disagreement`` and
    the ``review_agreement_blocked`` event) instead of claiming green."""
    spec = make_spec()
    stage(tmp_path, spec.files)
    # self-test green on arrival, re-ask green -> review mode; then a written revision.
    model = FakeModelRunner({"write_test": [SELF_TEST, SELF_TEST_ALT] + [impl()] * 12})
    out = run_leaf_sync(
        model, spec, tmp_path, Budget(calls=30, deadline_ts=_FAR_FUTURE),
        judge=lambda request: JudgeVerdict(
            attribution="implementation",
            defect="the result function compares by identity instead of by value"),
        review=_approving_review,
        iv=lambda request: iv_candidate(),
        # self-test green, re-ask green, attempt red (judge), then every IV original gate
        # is GREEN (independent-test-not-red -> non-discriminating)
        run_tests=ScriptedTests([0, 0, 1] + [0] * 40))

    assert out.claimed is False
    assert "review_agreement_blocked" in ledger_kinds()
    assert "NON-DISCRIMINATING" in out.verification_disagreement
    assert "implementation_wrong" in out.verification_disagreement
    # the review itself was well-formed and approved; the block is the agreement rule
    assert any(v.approved for v in out.review_verdicts)


# ---------------------------------------------------------------------------
# P5: the claim must follow the evidence
# ---------------------------------------------------------------------------


def _p5_own_test_base() -> dict:
    """The smallest green own-test claim, in the shape the main path supplies."""
    return dict(route="own-test", criteria_count=1, ledger=_gate_ledger(),
                own_test="tests/t.py", own_test_green=True, test_rewrites=0,
                verification_basis="test", tier_allowed=True)


def test_p5a_a_claim_requires_a_deterministic_green_and_a_real_delivery():
    """P5(a): a claim is about a REAL revision with at least one mechanically checked
    green. A model's approval over a delivery that changed nothing, or over a revision no
    deterministic signal could confirm, is not a claim."""
    base = _p5_own_test_base()
    granted = claim_decision(**base, deterministic_greens=("documented-api",),
                             delivery_changed=True)
    assert granted.claimed is True
    unchanged = claim_decision(**base, deterministic_greens=("documented-api",),
                               delivery_changed=False)
    assert unchanged.claimed is False
    assert unchanged.blocker == "no-change-delivery"
    silent = claim_decision(**base, deterministic_greens=(), delivery_changed=True)
    assert silent.claimed is False
    assert silent.blocker == "no-deterministic-green"
    # P8c: parsing alone is not a behavioural fact, so it cannot CARRY a claim (the A-02
    # false success: the same model's test and review both approved a wrong codon table).
    parses_only = claim_decision(**base, deterministic_greens=("source-compiles",),
                                 delivery_changed=True)
    assert parses_only.claimed is False
    assert parses_only.blocker == "no-deterministic-anchor"


def test_p5a_only_an_observed_regression_supplies_the_regression_green():
    """An UNOBSERVABLE regression check is silence, never a green signal."""
    assert deterministic_greens(source_unparseable="", documented_api_missing=(),
                                regression_clean=False) == ("source-compiles",
                                                            "documented-api")
    assert deterministic_greens(source_unparseable="pkg/x.py: syntax error",
                                documented_api_missing=("pkg/x.py: load() documented",
                                                        ),
                                regression_clean=True) == ("no-regression",)


def test_f1_a_judge_ruling_may_not_drop_a_discriminating_red():
    """F1 (P5(c) soundness): a check that produced a REAL observed failure on the PRISTINE
    source is DISCRIMINATING. No judge ruling against the check may drop it: the guard
    refuses, the honest block stands, and only a check whose every final failure was GREEN
    on the pristine source (an inversion) or a corroborating observed discriminating green
    may be dropped.

    This test fails if a judge ruling can clear a discriminating red."""
    discriminating = GateReport(report_path="(pristine)", process_exit=1, canary="c",
                                expected_files=(), n_tests=2, n_failed=1, n_errors=0,
                                passed_ids=("t.py::ac2",), failed_ids=("t.py::ac1",),
                                missing=(), observed=True, anomaly="tests-failed",
                                detail="1 failure(s)")
    # the check failed on the pristine source AND on the final revision: discriminating
    assert pristine_red_is_discriminating(discriminating) is True
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=False, own_red_blocks=False,
        iv_red_blocks=True, iv_final_failed_ids=("t.py::ac1",),
        iv_inverted_ids=()) is False
    # ... even when the SAME id also passed on the pristine source is impossible, but an
    # UNKNOWN final failure (present in neither report) is not excused either
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=False, own_red_blocks=False,
        iv_red_blocks=True, iv_final_failed_ids=("t.py::ac1", "t.py::ac9"),
        iv_inverted_ids=("t.py::ac1",)) is False
    # a ruling against the REVISION (or an unreadable ruling) never drops anything
    assert reconciled_check_may_be_dropped(
        ruling="revision", independent_approved=True, own_red_blocks=False,
        iv_red_blocks=True) is False
    assert reconciled_check_may_be_dropped(
        ruling="unclear", independent_approved=True, own_red_blocks=False,
        iv_red_blocks=True) is False


def test_p8b_an_errored_independent_run_is_not_discriminating_evidence():
    """P8b (the T-30 false success): a final red whose report was UNOBSERVED or only
    errors/collection failures proves nothing about the revision, so it must NOT
    corroborate a claim - exactly like an absent check. This test fails if an
    errors-only independent red can carry a pass claim again."""
    def gate(n_failed, anomaly="tests-failed"):
        return GateReport(report_path="(iv)", process_exit=1, canary="c", expected_files=(),
                          n_tests=3, n_failed=n_failed, n_errors=3 - n_failed, passed_ids=(),
                          failed_ids=tuple(f"t.py::ac{i}" for i in range(n_failed)),
                          missing=(), observed=True, anomaly=anomaly, detail="")
    errored = IndependentTestVerdict(approved=False, reason="independent-test-red-on-final",
                                     detail="0 failure(s), 3 error(s)", content="",
                                     original_gate=gate(0), final_gate=gate(0))
    assert iv_verdict_is_non_discriminating(errored) is True
    # a REAL final failure is evidence, not a non-discriminating state
    real_red = IndependentTestVerdict(approved=False, reason="independent-test-red-on-final",
                                      detail="1 failure(s)", content="",
                                      original_gate=gate(1), final_gate=gate(1))
    assert iv_verdict_is_non_discriminating(real_red) is False
    # approving is never non-discriminating, and the M2 set still qualifies
    approved = IndependentTestVerdict(approved=True, reason="", detail="", content="",
                                      original_gate=gate(1), final_gate=gate(0))
    assert iv_verdict_is_non_discriminating(approved) is False
    vacuous = IndependentTestVerdict(approved=False, reason="independent-test-not-red",
                                     detail="passed on the pristine source", content="",
                                     original_gate=gate(0), final_gate=gate(0))
    assert iv_verdict_is_non_discriminating(vacuous) is True
    assert iv_verdict_is_non_discriminating(None) is False


def test_f1_only_a_pure_inversion_or_a_corroborating_green_can_drop_a_check():
    """F1: the two sound drops survive — every final failure was GREEN on the pristine
    source (the delivery broke a check the pre-fix source passed), or an OBSERVED
    discriminating green about the same revision contradicts the red."""
    green_on_pristine = GateReport(report_path="(pristine)", process_exit=0, canary="c",
                                   expected_files=(), n_tests=2, n_failed=0, n_errors=0,
                                   passed_ids=("t.py::ac1", "t.py::ac2"), failed_ids=(),
                                   missing=(), observed=True)
    assert pristine_red_is_discriminating(green_on_pristine) is False
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=False, own_red_blocks=False,
        iv_red_blocks=True, iv_final_failed_ids=("t.py::ac1",),
        iv_inverted_ids=("t.py::ac1",)) is True
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=True, own_red_blocks=False,
        iv_red_blocks=True, iv_final_failed_ids=("t.py::ac1",),
        iv_inverted_ids=()) is True
    # an errors/collection-only pristine run never discriminated anything
    errors_only = dataclasses.replace(green_on_pristine, n_failed=0, n_errors=2,
                                      passed_ids=(), anomaly="tests-failed")
    assert pristine_red_is_discriminating(errors_only) is False
    assert pristine_red_is_discriminating(None) is False


def test_f1_the_runs_own_green_test_cannot_corroborate_dropping_a_discriminating_red():
    """F1 (the T-13 false success): a run can always write its own test that passes on its
    own (wrong) fix. When a judge rules the FRESH independent verification wrong, the run's
    own green test is not corroboration — only an approving independent verification is —
    so the discriminating independent red keeps blocking."""
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=False, own_red_blocks=False,
        iv_red_blocks=True,
        iv_final_failed_ids=("tests/test_independent.py::test_ac1",),
        iv_inverted_ids=()) is False
    # ... whereas the same ruling IS sound when the independent verification approved
    assert reconciled_check_may_be_dropped(
        ruling="check", independent_approved=True, own_red_blocks=True,
        iv_red_blocks=False) is True


def test_p5c_reconciliation_ruling_reads_the_judges_own_blame():
    """P5(c): the ruling is the judge's OWN attribution word from the raw envelope, even
    when the loop's filter coerced the credited label to implementation."""
    coerced = JudgeVerdict(
        implementation_wrong=True, coerced=True,
        coercion_reason=("test_wrong without a defect naming the failing test or one of "
                         "its assertions (deterministic filter)"),
        raw='{"status": "failed", "blame": "test", "problem": "the test asserts the '
            'pre-fix behaviour"}')
    assert reconciliation_ruling(coerced)[0] == "check"
    revision = JudgeVerdict(implementation_wrong=True,
                            raw='{"status": "failed", "blame": "implementation", '
                                '"problem": "the function still mutates the shared list"}')
    assert reconciliation_ruling(revision)[0] == "revision"
    assert reconciliation_ruling(None) == ("unclear", "no verdict was returned")
    unclear = JudgeVerdict(environment_broken=True, attribution="environment")
    assert reconciliation_ruling(unclear)[0] == "unclear"


def test_p5c_a_reconciled_claim_records_its_basis_risk():
    """P5(c): a claim allowed after the reconciliation judge ruled a blocking check wrong
    carries the recorded basis risk; a non-discriminating check, by contrast, BLOCKS the
    review route (never a labelled grant)."""
    granted = claim_decision(**_m2_review_base(), basis_risk="reconciled-check-dropped:x")
    assert granted.claimed is True
    assert granted.basis_risk == "reconciled-check-dropped:x"
    blocked = claim_decision(
        **{**_m2_review_base(), "own_test": "tests/t.py", "own_test_green": True},
        iv_non_discriminating=True,
        iv_non_discriminating_detail="independent-test-not-discriminating: AC3 passes "
                                     "on the pre-run source")
    assert blocked.claimed is False
    assert blocked.blocker == "independent-test-non-discriminating"
    assert blocked.basis_risk == "review-over-non-discriminating-check"


# ===========================================================================
# FIX WAVE 1 (ticket 28): make the model-written verification/review stages carry
# information and make best-evidence delivery coverage-aware.
# ===========================================================================

def test_fix1_independent_test_prompt_carries_the_desired_state_rule():
    """FIX 1: the independent-test question must carry the SAME desired-state rule the
    run's own test gets, plus the explicit line: the AC text may describe the BROKEN
    symptom, so assert the desired end state, never the reported symptom (the T-06/T-10
    inversion class at its source)."""
    from bench.v2_leaf import _independent_test_question

    request = IndependentTestRequest(
        goal="the scheduler crashes on a naive clock",
        acs=["is_due(job) raises TypeError with a naive clock"],
        original={"pkg/calc.py": "def result():\n    return 0\n"},
        final={"pkg/calc.py": "def result():\n    return 42\n"})
    question = _independent_test_question(request)
    assert "DESCRIBE THE CURRENT BROKEN behaviour" in question
    assert "never the reported symptom" in question
    assert "may describe the BROKEN symptom" in question


def test_fix2_iv_blocking_final_ids_excuses_inverted_and_blocks_the_unmet():
    """FIX 2: the per-id generalisation of ``iv_all_inverted``. A final-revision failure
    that PASSED on the pristine source is inverted and never blocks; only a failure that
    also FAILED there (a genuine unmet criterion) blocks a mixed file."""
    from harness.leaf import iv_all_inverted, iv_blocking_final_ids

    iv = "tests/test_independent.py"
    inverted = f"{iv}::test_ac1_inverted"
    unmet = f"{iv}::test_ac2_unmet"
    original = _gate_report(iv, passed=(inverted,), failed=(unmet,), green=False)
    final = _gate_report(iv, passed=(), failed=(inverted, unmet), green=False)
    mixed = IndependentTestVerdict(approved=False, reason="independent-test-red-on-final",
                                   original_gate=original, final_gate=final)
    assert iv_blocking_final_ids(mixed) == (unmet,)
    assert iv_all_inverted(mixed) is False

    all_inverted = IndependentTestVerdict(
        approved=False, reason="independent-test-red-on-final", original_gate=original,
        final_gate=_gate_report(iv, passed=(unmet,), failed=(inverted,), green=False))
    assert iv_blocking_final_ids(all_inverted) == ()
    assert iv_all_inverted(all_inverted) is True


def test_fix2_evaluate_independent_test_classifies_inversion_before_the_early_return():
    """FIX 2: the whole-file red-on-final early return must still classify per criterion,
    so a mixed file records WHICH ids were inverted (never evidence against the fix) and
    which are genuinely unmet (blocking)."""
    import harness.leaf as leaf_mod

    original = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 0\n"}
    final = {"pkg/__init__.py": "", "pkg/calc.py": "def result():\n    return 42\n"}
    content = ("from pkg.calc import result\n\n\n"
               "def test_ac1_symptom():\n    assert result() == 0\n\n\n"
               "def test_ac2_desired():\n    assert result() == 42\n\n\n"
               "def test_ac3_broken():\n    assert result() == 999\n")
    verdict = asyncio.run(evaluate_independent_test(
        IndependentTestCandidate(path="tests/test_independent.py", content=content),
        original, final, leaf_mod._default_run_tests, criteria_count=3))

    assert verdict.approved is False
    assert verdict.reason == "independent-test-red-on-final"
    assert verdict.inverted_indices == (1,)
    assert verdict.offending_indices == (3,)
    assert sorted(c.index for c in verdict.criteria) == [1, 2, 3]


def test_fix5_review_round_cannot_reapprove_bytes_it_rejected():
    """FIX 5: a review round must not approve the SAME source revision an earlier round of
    the same angle rejected (the T-26/T-28 flip-flop); on CHANGED bytes the approval is a
    new verdict and stands."""
    from harness.leaf import combine_review_verdicts

    angles = ("ac-correctness", "contract-compat")
    rejected = ReviewVerdict(angle="ac-correctness", grade="definitely-problematic",
                             evidence="pkg/calc.py:1 returns the wrong value",
                             source_revision="f1")
    old_companion = ReviewVerdict(angle="contract-compat", grade="uncertain",
                                  source_revision="f1")
    approval = ReviewVerdict(angle="ac-correctness", grade="definitely-ok",
                             evidence="pkg/calc.py:1 returns 42", source_revision="f1")
    new_companion = ReviewVerdict(angle="contract-compat", grade="definitely-ok",
                                  evidence="pkg/calc.py:1 keeps the contract",
                                  source_revision="f1")
    ok, _score, why = combine_review_verdicts(
        [rejected, old_companion, approval, new_companion], angles, "implementation")
    assert ok is False and "already rejected" in why

    changed = dataclasses.replace(approval, source_revision="f2")
    ok2, _score2, _why2 = combine_review_verdicts(
        [rejected, old_companion, changed, new_companion], angles, "implementation")
    assert ok2 is True


def test_fix6_best_evidence_prefers_more_complete_request_coverage():
    """FIX 6: best evidence ranks by (request-coverage of the revision, then evidence), so
    a complete revision is preferred over a partial one with stronger model evidence."""
    from harness.leaf import BestEvidenceRevision, _best_evidence_preference

    complete = BestEvidenceRevision(rank=1, tier="review", attempt=1, reason="",
                                    request_coverage_missing=())
    partial = BestEvidenceRevision(rank=4, tier="agreement", attempt=1, reason="",
                                   request_coverage_missing=("api/service.py",))
    unknown = BestEvidenceRevision(rank=4, tier="agreement", attempt=1, reason="")
    assert _best_evidence_preference(complete) > _best_evidence_preference(partial)
    assert _best_evidence_preference(complete) > _best_evidence_preference(unknown)
    assert _best_evidence_preference(partial) > _best_evidence_preference(unknown)


def test_d1_contract_clear_revision_displaces_a_failing_snapshot(tmp_path):
    """D1: a later revision that CLEARS the deterministic documented-API check is captured
    as ``contract-clear`` and displaces the earlier failing best-evidence snapshot (T-28:
    the delivered review snapshot failed the check while a later revision cleared it and
    passed the withheld suite). The check is never treated as a grader pass."""
    from harness.leaf import documented_api_problem

    files = {
        "README.md": "Use result() to read the value.\n",
        "pkg/calc.py": "class Calc:\n    def result(self):\n        return 0\n",
    }
    spec = dataclasses.replace(make_spec(files), acs=["pkg/calc.py must expose result()"])
    stage(tmp_path, files)
    # the class-only baseline IS the documented-API failure the later revision clears
    assert documented_api_problem(spec, tmp_path, {rel: None for rel in files})
    class_only = write_env("pkg/calc.py", "class Calc:\n    def result(self):\n        return 0\n")
    clear = write_env("pkg/calc.py", "def result():\n    return 42\n")
    # attempt 1: the class-only revision (the review snapshot fails documented-api)
    # attempt 2: the module-level API (clears it, no model evidence)
    model = FakeModelRunner({"write_test": [SELF_TEST, class_only, clear]})
    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=14, deadline_ts=_FAR_FUTURE),
                        review=ScriptedReview([_passing_review, _passing_review]),
                        run_tests=ScriptedTests([1, 0, 1, 0, 1, 0, 1, 0]))
    delivered = out.delivered_revision
    assert delivered["best_tier"] == "contract-clear"
    assert "def result(" in (tmp_path / "pkg" / "calc.py").read_text()


def test_d2_test_attributed_traceback_credits_test_wrong():
    """A test-local missing name proves setup invalidity despite a source blame.

    An assertion-only traceback is not such proof (covered by the negative control).
    """
    request = JudgeRequest(
        goal="fix the source", acs=["result() returns 42"],
        failure=("FAILED tests/test_leaf_self.py::test_goal\n"
                 "tests/test_leaf_self.py:3: NameError: name 'result' is not defined"),
        test_path="tests/test_leaf_self.py",
        test_content="def test_goal():\n    assert result() == 42\n",
        files={"pkg/calc.py": "def result():\n    return 0\n"})
    verdict = JudgeVerdict(attribution="implementation", reason="the source is wrong",
                           defect="the source is wrong")
    filtered = apply_judge_filter(verdict, request)
    assert filtered.test_wrong is True
    assert filtered.implementation_wrong is False
    assert filtered.coercion_reason == "test_attributed_from_traceback"

    for failure in (
        "tests/test_leaf_self.py:3: AssertionError: assert 0 == 42",
        "tests/test_leaf_self.py:3: AssertionError: NameError: unexpected result",
        ("tests/test_leaf_self.py:3: AssertionError: assert 0 == 42\n"
         "---------------- Captured stdout call ----------------\n"
         "tests/test_leaf_self.py:3: NameError: printed text"),
    ):
        assertion_request = dataclasses.replace(request, failure=failure)
        assertion_filtered = apply_judge_filter(verdict, assertion_request)
        assert assertion_filtered.test_wrong is False
        assert assertion_filtered.implementation_wrong is True

    # A missing name in source must not trigger a test repair either.
    source_request = dataclasses.replace(
        request, failure=("tests/test_leaf_self.py:3: \n"
                          "pkg/calc.py:1: NameError: name 'missing' is not defined"))
    source_filtered = apply_judge_filter(verdict, source_request)
    assert source_filtered.test_wrong is False
    assert source_filtered.implementation_wrong is True


def test_d3_spec_wrong_naming_a_source_defect_is_not_credited():
    """D3: a ``spec_wrong`` whose own reason names a source defect contradicts itself and
    is coerced to implementation (the T-35 3-call spec bubble)."""
    request = JudgeRequest(
        goal="fix merge()", acs=["merge() merges overlaps"],
        failure="FAILED test_merge.py::test_merge",
        test_path="test_merge.py",
        test_content="def test_merge():\n    assert merge([[1, 3], [2, 4]]) == [[1, 4]]\n",
        files={"spans/merge.py": "def merge(intervals):\n    return intervals\n"})
    verdict = JudgeVerdict(
        spec_wrong=True, attribution="spec",
        reason="The merge function uses 'start <= current_end' incorrectly",
        defect="The merge function uses 'start <= current_end' incorrectly")
    filtered = apply_judge_filter(verdict, request)
    assert filtered.spec_wrong is False
    assert filtered.implementation_wrong is True
    assert filtered.coerced is True


def test_fix3_resampled_independent_test_does_not_upgrade_the_claim(tmp_path):
    """FIX 3: when the run's last independent verdict is RED on the final revision, a fresh
    approving draw authored at exhaustion is a RE-SAMPLE of the same model. It is labelled
    ``independent-test-resampled`` and cannot by itself carry the claim above the review
    (T-35's false success)."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = dataclasses.replace(make_spec(files),
                               acs=["pkg/calc.py must return 42",
                                    "the widget must wobble"])
    stage(tmp_path, files)
    impl_env = write_env(
        "pkg/calc.py",
        "def result():\n    return 42\n\n\ndef helper():\n    return 7\n")
    model = FakeModelRunner({"write_test": [SELF_TEST, impl_env]})
    authored = {"n": 0}

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        authored["n"] += 1
        content = ("from pkg.calc import helper, result\n\n\n"
                   "def test_ac1_bad():\n    assert result() == 100\n\n\n"
                   "def test_ac2_bad():\n    assert helper() == 100\n"
                   if authored["n"] == 1 else
                   "from pkg.calc import helper, result\n\n\n"
                   "def test_ac1_goal():\n    assert result() == 42\n\n\n"
                   "def test_ac2_goal():\n    assert helper() == 7\n")
        return IndependentTestCandidate(path="tests/test_independent.py", content=content)

    iv_path = "tests/test_independent.py"

    def run(workdir, node_ids=None):
        root = Path(workdir)
        ivp = root / iv_path
        source = (root / "pkg/calc.py").read_text()
        if not ivp.exists():
            green = "return 42" in source and "def helper" in source
            nid = "tests/test_leaf_self.py::test_goal"
            gate = _gate_report("tests/test_leaf_self.py",
                                passed=(nid,) if green else (),
                                failed=() if green else (nid,), green=green)
            return ShapedResult(command=["python3", "-m", "pytest", "-q"],
                                exit=0 if green else 1, verdict="ok" if green else "failed",
                                excerpts=[] if green else ["FAILED " + nid], gate=gate)
        if node_ids is not None:
            final = "return 42" in source and "def helper" in source
            if final:
                return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=0,
                                    verdict="ok", excerpts=[],
                                    gate=_gate_report(iv_path, passed=tuple(node_ids)))
            return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=1,
                                verdict="failed", excerpts=[],
                                gate=_gate_report(iv_path, passed=(),
                                                  failed=tuple(node_ids), green=False))
        bad = "test_ac1_bad" in ivp.read_text()
        final = "return 42" in source and "def helper" in source
        ac1 = f"{iv_path}::{'test_ac1_bad' if bad else 'test_ac1_goal'}"
        ac2 = f"{iv_path}::{'test_ac2_bad' if bad else 'test_ac2_goal'}"
        if bad or not final:
            gate = _gate_report(iv_path, passed=(), failed=(ac1, ac2), green=False)
        else:
            gate = _gate_report(iv_path, passed=(ac1, ac2))
        return ShapedResult(command=["python3", "-m", "pytest", "-q"],
                            exit=0 if gate.green else 1,
                            verdict="ok" if gate.green else "failed", excerpts=[], gate=gate)

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        iv=iv, review=ScriptedReview([_passing_review, _passing_review]),
                        run_tests=run)

    assert out.claimed is True
    assert authored["n"] == 2                       # main-path IV + the exhaustion re-sample
    assert out.claimed_basis == "review"           # the re-sample did NOT carry a test claim
    assert "independent_test_resampled" in ledger_kinds()


# ===========================================================================
# FIX WAVE 1 CLOSURE (ticket 28): the T-35 false-success class and the
# canary-missing independent-test evidence.
# ===========================================================================

def test_fix7_a_collection_error_still_runs_and_authenticates_the_gate(tmp_path):
    """FIX 7 (wave 1): a test file that fails to IMPORT must not hide this run's own
    report. Without ``--continue-on-collection-errors`` pytest aborts the session before
    the canary is collected, the gate reports ``canary-missing`` ("the report cannot be
    this run's evidence" — FALSE: it is this run's report), and a real observed failure of
    the run's own check is downgraded to ``independent-test-unobserved``. With the flag the
    canary runs, the report is authenticated, and the collection error is the observed
    ``tests-failed`` red it is."""
    import harness.leaf as leaf_mod

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "calc.py").write_text("def result():\n    return 42\n")
    (tmp_path / "tests").mkdir()
    # the model-authored test imports a name the delivered module does not define
    (tmp_path / "tests" / "test_independent.py").write_text(
        "from pkg.calc import result, missing_name\n\n\n"
        "def test_ac1_goal():\n    assert result() == 42\n")

    res = asyncio.run(leaf_mod._default_run_tests(tmp_path))
    gate = res.gate

    assert gate.observed is True
    assert gate.anomaly == "tests-failed"          # not "canary-missing"
    assert any(nid.startswith("tests/test_gate_canary_") for nid in gate.passed_ids)
    assert any("test_independent" in nid for nid in gate.failed_ids)


def test_d3b_reconciliation_ruling_refuses_a_self_contradicting_check_blame():
    """D3b (wave 1): the raw ``blame`` word may not overrule the judge's own reason. The
    T-35 reconciliation verdict said ``blame="test"`` while its problem named the source
    defect; crediting the word dropped the run's red own test and granted a false success.
    The same coherence rule the filter applies to ``test_wrong``
    (:func:`_judge_incoherence`) decides: a reason naming the SOURCE and no failing test
    function is not a ruling against the check."""
    request = JudgeRequest(
        goal="fix merge()", acs=["merge() merges overlaps"],
        failure="FAILED tests/test_leaf_self.py::test_goal",
        test_path="tests/test_leaf_self.py",
        test_content="def test_goal():\n    assert result() == 42\n",
        files={"pkg/calc.py": "def result():\n    return 1\n"})
    t35 = JudgeVerdict(
        implementation_wrong=True, coerced=True,
        coercion_reason=("test_wrong without a defect naming the failing test or one of "
                         "its assertions (deterministic filter)"),
        defect="the code fails to satisfy the contract because result() is wrong",
        raw='{"status": "failed", "comment": "the tests are correct; the code is wrong", '
            '"blame": "test", "problem": "the code fails because result() is still '
            'wrong"}')
    ruling, why = reconciliation_ruling(t35, request)
    assert ruling != "check"
    assert "self-contradicting" in why

    # a REASON that names the failing test function keeps the check ruling readable
    coherent = t35.model_copy(update={
        "defect": "test_goal asserts the wrong expected value",
        "raw": '{"status": "failed", "blame": "test", '
               '"problem": "test_goal asserts the wrong expected value"}'})
    assert reconciliation_ruling(coherent, request)[0] == "check"
    # ... and with no request (the legacy call shape) the raw blame is still honoured
    assert reconciliation_ruling(t35)[0] == "check"


def test_d3b_incoherent_check_ruling_cannot_carry_a_false_success(tmp_path):
    """D3b (wave 1, the T-35 false success end to end): the run's own test is RED on the
    final revision, the exhaustion independent test APPROVES it, and the reconciliation
    judge answers ``blame="test"`` while its own reason names the SOURCE defect. Before
    the fix the ruling dropped the own red and the gate granted ``basis=independent-test``
    on a delivery its own test rejected; now the ruling is refused, the two imperfect
    tests CONFLICT, and the run does not claim."""
    files = {"pkg/calc.py": "def result():\n    return 0\n"}
    spec = make_spec(files)
    stage(tmp_path, files)
    # the run's own test asserts a value its source never returns: RED on every revision
    own_test = write_env("tests/test_leaf_self.py",
                         "def test_goal():\n    assert result() == 7\n")
    impl_env = write_env("pkg/calc.py", "def result():\n    return 42\n")
    model = FakeModelRunner({"write_test": [own_test, *([impl_env] * 8)]})

    def judge(request: JudgeRequest) -> JudgeVerdict:
        return JudgeVerdict(
            attribution="test",
            defect="the code fails to satisfy the contract because result() is wrong",
            raw='{"status": "failed", "comment": "the test expectations are correct", '
                '"blame": "test", "problem": "the code fails to satisfy the contract '
                'because result() is wrong"}')

    def iv(request: IndependentTestRequest) -> IndependentTestCandidate:
        return iv_candidate()

    iv_path = "tests/test_independent.py"

    def run(workdir, node_ids=None):
        root = Path(workdir)
        ivp = root / iv_path
        if not ivp.exists():
            # the run's OWN test: RED on the pristine and every written revision
            nid = "tests/test_leaf_self.py::test_goal"
            return ShapedResult(command=["python3", "-m", "pytest", "-q"], exit=1,
                                verdict="failed", excerpts=["FAILED " + nid],
                                gate=_gate_report("tests/test_leaf_self.py",
                                                  failed=(nid,), green=False))
        final = "return 42" in (root / "pkg/calc.py").read_text()
        if node_ids is not None:
            nodes = tuple(node_ids)
            gate = _gate_report(iv_path, passed=nodes if final else (),
                                failed=() if final else nodes, green=final)
            return ShapedResult(command=["python3", "-m", "pytest", "-q"],
                                exit=0 if gate.green else 1,
                                verdict="ok" if gate.green else "failed",
                                excerpts=[], gate=gate)
        nid = f"{iv_path}::test_ac1_goal"
        gate = _gate_report(iv_path, passed=(nid,) if final else (),
                            failed=() if final else (nid,), green=final)
        return ShapedResult(command=["python3", "-m", "pytest", "-q"],
                            exit=0 if gate.green else 1,
                            verdict="ok" if gate.green else "failed", excerpts=[], gate=gate)

    out = run_leaf_sync(model, spec, tmp_path, Budget(calls=20, deadline_ts=_FAR_FUTURE),
                        judge=judge, iv=iv,
                        review=ScriptedReview([_passing_review, _passing_review]),
                        run_tests=run)

    assert out.claimed is False
    assert out.stop_reason == "verifier-conflict"
    assert "claim_reconciliation_check_dropped" not in ledger_kinds()
    reconciliations = [e for e in ledger_entries() if e["kind"] == "claim_reconciliation"]
    assert reconciliations and reconciliations[0]["ruling"] != "check"
