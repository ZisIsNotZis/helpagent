"""Ticket 20 step 2a — the How axis, the selection function, and immutability.

Covers the owner decision of 2026-09-30: the append-only How list with statuses, the
prior-as-hint table, the lexicographic selection function with its tie-breaks, the
manager loop's four decisions and its automatic-advance boundary, the model-maintained
node record area, and candidate isolation (a copy, never a git worktree / destructive
reset).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.budget import Budget
from harness.envelopes import SCHEMAS, HowList, PlanNode
from harness.gate_report import GateReport
from harness.how import (
    MANAGER_DECISIONS,
    How,
    HowFailure,
    HowList as HowListData,
    ManagerDecision,
    NodeRecord,
    NodeRecordView,
    PRIOR_DECAY,
    Selection,
    TestPoint,
    abandon_candidate,
    audit_candidate_boundary,
    candidate_dir,
    create_candidate,
    decide_after_failure,
    extra_test_points,
    how_exploration_limit,
    how_list_from_envelope,
    how_viability,
    make_how,
    pick,
    planned_test_points,
    planned_test_score,
    point_results,
    prior_for_rank,
    select_key,
    snapshot_candidate,
)
from harness.leaf import DeclaredTestCase, ReviewVerdict
from harness.node import NodeSpec


# ---------------------------------------------------------------------------
# The How record, statuses, and immutability
# ---------------------------------------------------------------------------


def test_how_record_fields_and_statuses():
    how = make_how("HOW-1", "clamp the ttl at read time", 1, "smallest diff")
    assert (how.id, how.rank, how.prior, how.status) == ("HOW-1", 1, 0.5, "untried")
    assert how.text and how.reason
    with pytest.raises(ValueError):
        How(id="HOW-2", text="", rank=1, reason="r", prior=0.5)
    with pytest.raises(ValueError):
        How(id="HOW-3", text="t", rank=0, reason="r", prior=0.5)
    with pytest.raises(ValueError):
        How(id="HOW-4", text="t", rank=1, reason="  ", prior=0.5)
    with pytest.raises(ValueError):
        How(id="HOW-5", text="t", rank=1, reason="r", prior=0.5, status="bogus")


def test_how_append_only_failure_never_edits():
    first = make_how("HOW-1", "clamp at read", 1, "smallest diff")
    hows = HowListData().append(first)
    # A failure appends a NEW How and marks the old one failed — the old HowList and the
    # old How are unchanged (content is immutable).
    new_how = make_how("HOW-2", "normalize at write", 2, "fixes the root")
    updated = hows.append(new_how, mark=("HOW-1", "failed"))
    assert len(hows) == 1 and hows.get("HOW-1").status == "untried"
    assert len(updated) == 2
    assert updated.get("HOW-1").status == "failed"
    assert updated.get("HOW-2").status == "untried"
    assert updated.get("HOW-1").text == first.text
    with pytest.raises(ValueError):
        updated.append(make_how("HOW-2", "dup", 3, "dup"))


def test_untried_returns_candidates_in_rank_order():
    hows = HowListData()
    hows = hows.append(make_how("HOW-2", "b", 2, "r"))
    hows = hows.append(make_how("HOW-1", "a", 1, "r"))
    hows = hows.append(make_how("HOW-3", "c", 3, "r"), mark=("HOW-2", "abandoned"))
    assert [h.id for h in hows.untried()] == ["HOW-1", "HOW-3"]


def test_how_list_from_envelope_assigns_ids_ranks_and_priors_from_order():
    """Ticket 20 step 2b-ii: identity, rank and prior are HARNESS-OWNED. The model
    supplies only ``text``/``reason``; the LIST ORDER is the rank, so
    :func:`how_list_from_envelope` assigns ``HOW-1``..``HOW-n``, ranks ``1``..``n`` and
    the deterministic priors — regardless of what the model wrote in the text."""
    env = HowList.model_validate({
        "status": "ok", "comment": "three approaches",
        "hows": [
            {"text": "HOW-2: clamp the ttl at read time", "reason": "r1"},
            {"text": "approach_3 - normalize the ttl at write time", "reason": "r2"},
            {"text": "a third approach that names no rank at all", "reason": "r3"},
        ]})
    data = how_list_from_envelope(env)
    assert [h.id for h in data] == ["HOW-1", "HOW-2", "HOW-3"]
    assert [h.rank for h in data] == [1, 2, 3]
    assert [h.prior for h in data] == [prior_for_rank(1), prior_for_rank(2),
                                       prior_for_rank(3)]


def test_plan_node_binds_result_to_a_how_id():
    assert SCHEMAS["how_list"] is HowList
    assert len(SCHEMAS) == 28  # ticket 20 step 2b-ii: +manager_decision
    bound = PlanNode.model_validate({
        "status": "ok", "comment": "one how",
        "goal": "g", "behavior": "b", "implementation_notes": "n",
        "files": ["a.py"], "acs": [], "interfaces": [], "how_id": "HOW-2",
        "children": []})
    assert bound.how_id == "HOW-2"
    with pytest.raises(Exception):
        PlanNode.model_validate({
            "status": "ok", "comment": "bad", "goal": "g", "behavior": "b",
            "implementation_notes": "n", "files": [], "acs": [],
            "interfaces": [], "how_id": "not-a-how", "children": []})


# ---------------------------------------------------------------------------
# The prior as a scheduler hint (never evidence)
# ---------------------------------------------------------------------------


def test_prior_table_is_geometric_decay():
    assert PRIOR_DECAY == 0.5
    assert [prior_for_rank(r) for r in (1, 2, 3)] == [0.5, 0.25, 0.125]
    with pytest.raises(ValueError):
        prior_for_rank(0)


def test_prior_comes_from_the_rank_table_only():
    # rank 15 must never out-viability rank 1, and NO caller can pass an arbitrary prior
    rank1 = make_how("HOW-1", "a", 1, "r")
    rank15 = make_how("HOW-15", "a", 15, "r")
    assert (rank1.prior, rank15.prior) == (prior_for_rank(1), prior_for_rank(15))
    assert rank15.prior < rank1.prior
    with pytest.raises(TypeError):
        make_how("HOW-1", "a", 1, "r", prior=10.0)  # the inflation seam is gone
    with pytest.raises(ValueError):
        How(id="HOW-2", text="a", rank=2, reason="r", prior=10.0)


def test_how_viability_is_prior_times_best_viable_child():
    assert how_viability(0.5, []) == 0.5  # a leaf How carries its own prior
    assert how_viability(0.5, [("active", 0.4), ("untried", 0.25)]) == pytest.approx(0.2)
    # failed/abandoned children are removed from the product
    assert how_viability(0.5, [("failed", 9.0), ("active", 0.4)]) == pytest.approx(0.2)
    # children exist but NONE is viable -> not viable
    assert how_viability(0.5, [("failed", 0.4), ("abandoned", 0.9)]) == 0.0


def test_how_viability_rejects_an_unrecognised_status():
    # a typo such as "fail" must NEVER count as viable (it would mask a real failure)
    with pytest.raises(ValueError):
        how_viability(0.5, [("fail", 9.0)])
    # the node's OWN status is validated against the closed set too
    with pytest.raises(ValueError):
        how_viability(0.5, [], status="finished")


def test_how_viability_of_a_failed_or_abandoned_how_is_zero():
    # the node's OWN status dominates: a failed/abandoned How is not viable even when its
    # children are perfectly good (a failure is never rescued by its subtree)
    assert how_viability(0.5, [("active", 0.9)], status="failed") == 0.0
    assert how_viability(0.5, [("active", 0.9)], status="abandoned") == 0.0
    assert how_viability(0.5, [], status="succeeded") == 0.5


# ---------------------------------------------------------------------------
# The selection function (lexicographic, deterministic)
# ---------------------------------------------------------------------------


def _positive_verdicts(score_grade="definitely-ok"):
    return [
        ReviewVerdict(angle="ac-correctness", grade=score_grade, evidence="a.py:1"),
        ReviewVerdict(angle="contract-compat", grade="probably-ok", evidence="a.py:2"),
    ]


def test_planned_test_score_denominator_is_the_plan():
    assert planned_test_score([], {}) == (0, 0.0)
    assert planned_test_score(["t1", "t2", "t3", "t4"], {"t1": True, "t2": True}) == (2, 0.5)
    assert planned_test_score(["t1"], None) == (0, 0.0)


# ---------------------------------------------------------------------------
# The plan-time test list (name + file + what it verifies + the AC it serves)
# ---------------------------------------------------------------------------


def _own_gate(*, passed=(), failed=()):
    return GateReport(report_path="(scripted)", process_exit=0, canary="c",
                      expected_files=(), n_tests=len(passed) + len(failed),
                      n_failed=len(failed), n_errors=0,
                      passed_ids=tuple(passed), failed_ids=tuple(failed),
                      missing=(), observed=True)


def _leaf_with_gate(*, passed=(), failed=()):
    return SimpleNamespace(own_test_gate=_own_gate(passed=passed, failed=failed))


def test_planned_test_point_declares_name_file_verifies_and_ac():
    spec = NodeSpec(goal="g", acs=("sessions expire per ttl",), kind="leaf",
                    files=("a.py",),
                    test_cases=(DeclaredTestCase("AC-1", "tests/test_a.py",
                                                 ("test_ac1_expiry",)),))
    points = planned_test_points(spec)
    assert len(points) == 1
    point = points[0]
    assert (point.name, point.file, point.verifies, point.ac_id) == (
        "test_ac1_expiry", "tests/test_a.py", "sessions expire per ttl", "AC-1")
    assert point.id == "tests/test_a.py::test_ac1_expiry"
    assert point.to_dict() == {"name": "test_ac1_expiry", "file": "tests/test_a.py",
                               "verifies": "sessions expire per ttl", "ac_id": "AC-1",
                               "id": "tests/test_a.py::test_ac1_expiry"}
    # no declaration => no points (the pre-plan behaviour, test component (0, 0.0))
    assert planned_test_points(NodeSpec(goal="g", files=("a.py",), kind="leaf",
                                        acs=("c",))) == ()


def test_point_results_score_the_declared_points_only():
    points = (TestPoint("t1", "tests/test_a.py", "v", "AC-1"),
              TestPoint("t2", "tests/test_a.py", "v", "AC-1"),
              TestPoint("t3", "tests/test_a.py", "v", "AC-1"))
    # t1 passed, t2 failed, t3 never observed; a test the candidate INVENTED is not a point
    leaves = [_leaf_with_gate(passed=("tests/test_a.py::t1", "tests/test_a.py::invented"),
                              failed=("tests/test_a.py::t2",))]
    results = point_results(points, leaves)
    assert results == {"tests/test_a.py::t1": True, "tests/test_a.py::t2": False}
    assert planned_test_score([p.id for p in points], results) == (2, 1 / 3)
    # a pytest class-method node id is matched on its final segment
    assert point_results(points, [_leaf_with_gate(passed=("tests/test_a.py::TestX::t1",))]) \
        == {"tests/test_a.py::t1": True}


def test_extra_test_points_are_a_reported_deviation_but_never_score():
    points = (TestPoint("t1", "tests/test_a.py", "v", "AC-1"),)
    leaves = [_leaf_with_gate(passed=("tests/test_a.py::t1",
                                      "tests/test_a.py::TestX::t2",
                                      "tests/other.py::t9"))]
    # an extra in a DECLARED file is a deviation; one in an unrelated file is not
    assert extra_test_points(points, leaves) == ("tests/test_a.py::t2",)
    # extras never enter the plan denominator
    assert planned_test_score([p.id for p in points],
                              point_results(points, leaves)) == (1, 1.0)


def test_manager_view_carries_the_test_deviations_and_candidate_selections():
    from harness.how import CandidateSet

    cs = CandidateSet(node_id="N1", run_outdir=Path("/tmp/x"), source=Path("/tmp/y"))
    cs.add_how(make_how("HOW-1", "a", 1, "r"))
    cs.add_how(make_how("HOW-2", "b", 2, "r"))
    cs.record_deviations(["tests/test_a.py::t1", "tests/test_a.py::t1"])
    cs.record_deviations(["tests/test_a.py::t2"])
    cs.record_selection("HOW-2", Selection(test_covered=2, test_pass_rate=1.0,
                                            review_score=0, rank=2, cost=5,
                                            review_ok=True))
    view = cs.manager_view(current_how_id="HOW-1")
    assert view.deviations == ("tests/test_a.py::t1", "tests/test_a.py::t2")
    assert [how_id for how_id, _ in view.selections] == ["HOW-2"]
    assert view.selections[0][1].test_covered == 2


def _selection(*, covered, rate, review_score, rank, cost):
    return Selection(test_covered=covered, test_pass_rate=rate, review_score=review_score,
                     rank=rank, cost=cost, review_ok=True, repair_reason="")


def test_pick_maximises_test_score_above_every_other_component():
    # a strictly better test score WINS even though review, rank and cost all favour the
    # other candidate: the test component is the first, dominant key
    better_tests = _selection(covered=2, rate=1.0, review_score=0, rank=9, cost=99)
    better_rest = _selection(covered=1, rate=1.0, review_score=9, rank=1, cost=1)
    assert pick([better_rest, better_tests]) is better_tests
    assert pick([better_tests, better_rest]) is better_tests


def test_pick_pass_rate_breaks_a_coverage_tie():
    full = _selection(covered=1, rate=1.0, review_score=0, rank=9, cost=99)
    partial = _selection(covered=1, rate=0.5, review_score=9, rank=1, cost=1)
    assert pick([partial, full]) is full


def test_pick_full_tie_break_chain_review_then_rank_then_cost():
    # equal test score -> the higher review score wins even with a worse rank and cost
    high_review = _selection(covered=1, rate=1.0, review_score=5, rank=9, cost=99)
    high_rank = _selection(covered=1, rate=1.0, review_score=1, rank=1, cost=1)
    assert pick([high_rank, high_review]) is high_review
    # equal test + review -> the SMALLER rank wins even with a larger cost
    low_rank = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=99)
    high_rank2 = _selection(covered=1, rate=1.0, review_score=5, rank=2, cost=1)
    assert pick([high_rank2, low_rank]) is low_rank
    # equal through rank -> the SMALLER cost wins
    cheap = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=1)
    dear = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=99)
    assert pick([dear, cheap]) is cheap


def test_pick_uses_the_select_key_order_and_is_empty_safe():
    strong_review = select_key(planned_test_points=[], test_results={},
                               review_verdicts=_positive_verdicts(), rank=1, cost=1)
    strong_tests = select_key(planned_test_points=["t1", "t2"],
                              test_results={"t1": True, "t2": True}, review_verdicts=[],
                              rank=9, cost=99)
    assert strong_review.review_score > 0
    assert pick([strong_review, strong_tests]) is strong_tests
    assert pick([]) is None


def test_negative_review_is_an_action_item_not_just_a_lost_comparison():
    verdicts = [
        ReviewVerdict(angle="ac-correctness", grade="probably-problematic",
                      evidence="a.py:1 misses the ttl reset", detail="misses the reset"),
        ReviewVerdict(angle="contract-compat", grade="probably-ok", evidence="a.py:2"),
    ]
    sel = select_key(planned_test_points=["t"], test_results={"t": True},
                     review_verdicts=verdicts, rank=1, cost=1)
    assert sel.needs_repair and "ac-correctness" in sel.repair_reason
    assert sel.review_score == 0


def test_critical_angle_veto_is_an_action_item():
    verdicts = [
        ReviewVerdict(angle="ac-correctness", grade="definitely-problematic",
                      evidence="a.py:1", detail="returns the wrong ttl"),
        ReviewVerdict(angle="contract-compat", grade="definitely-ok", evidence="a.py:2"),
    ]
    sel = select_key(planned_test_points=[], test_results={},
                     review_verdicts=verdicts, rank=1, cost=1)
    assert sel.needs_repair and "veto" in sel.repair_reason.lower() or \
        "critical angle ac-correctness" in sel.repair_reason
    assert sel.review_score == 0


# ---------------------------------------------------------------------------
# The manager loop
# ---------------------------------------------------------------------------


def _view(current="HOW-1"):
    return NodeRecordView(
        node_id="N1",
        hows=(make_how("HOW-1", "a", 1, "r"), make_how("HOW-2", "b", 2, "r")),
        failures=(HowFailure("HOW-1", "3 tests failed", "clamp was wrong"),),
        untried=("HOW-2",), current_how_id=current)


def test_manager_decision_values_are_exactly_four():
    assert MANAGER_DECISIONS == ("continue-with-next-how", "author-a-new-how",
                                 "request-feasibility-review", "escalate-or-park")
    with pytest.raises(ValueError):
        ManagerDecision("do-something", "r")
    with pytest.raises(ValueError):
        ManagerDecision("author-a-new-how", "  ")


def test_automatic_advance_only_after_an_infeasible_feasibility_review():
    auto = decide_after_failure(_view(), feasibility="infeasible")
    assert auto.decision == "continue-with-next-how"
    # No automatic advance without an infeasible verdict: the manager decides.
    calls = []

    def manager(record):
        calls.append(record)
        return ManagerDecision("request-feasibility-review", "the next How is unproven")

    decided = decide_after_failure(_view(), feasibility="feasible", manager=manager)
    assert decided.decision == "request-feasibility-review"
    assert calls and calls[0].untried == ("HOW-2",)
    # No manager injected -> safe default, never an implicit advance.
    assert decide_after_failure(_view()).decision == "escalate-or-park"
    # Infeasible but nothing untried -> the manager still decides.
    no_untried = NodeRecordView(node_id="N1", hows=_view().hows, untried=())
    assert decide_after_failure(no_untried, feasibility="infeasible",
                                manager=manager).decision == "request-feasibility-review"


def test_manager_view_carries_statuses_failures_and_untried():
    from harness.how import CandidateSet

    cs = CandidateSet(node_id="N1", run_outdir=Path("/tmp/x"), source=Path("/tmp/y"))
    cs.add_how(make_how("HOW-1", "a", 1, "r"))
    cs.add_how(make_how("HOW-2", "b", 2, "r"))
    cs.fail("HOW-1", evidence="3 tests failed", reason="clamp was wrong")
    view = cs.manager_view(current_how_id="HOW-1")
    assert view.failed == ("HOW-1",) and view.untried == ("HOW-2",)
    assert view.failures[0].evidence == "3 tests failed"
    cs.record(ManagerDecision("continue-with-next-how", "next"))
    assert [d.decision for d in cs.decisions] == ["continue-with-next-how"]


# ---------------------------------------------------------------------------
# The node record area
# ---------------------------------------------------------------------------


def test_node_record_is_rewritten_with_a_reason_and_is_never_evidence():
    record = NodeRecord(node_id="N1")
    assert NodeRecord.IS_EVIDENCE is False
    assert record.rewrite("tried the read-time clamp; ttl lives in config", "first plan") == ("", "")
    assert record.rewrite("switched to a write-time normalize", "clamp failed AC-1") == (
        "tried the read-time clamp; ttl lives in config", "first plan")
    assert record.text.startswith("switched")
    assert record.last_reason == "clamp failed AC-1"
    with pytest.raises(ValueError):
        record.rewrite("no reason", "   ")


def test_no_verification_or_claim_input_can_carry_a_node_record():
    from harness.leaf import JudgeRequest, LeafSpec, ReviewRequest, VerificationRecord

    record = NodeRecord(node_id="N1", text="scratchpad", last_reason="plan")
    # every evidence input rejects a node record, top-level OR nested in the blind view
    with pytest.raises(ValueError):
        LeafSpec(goal="g", files={"a.py": record}, acs=[], interfaces=[])
    with pytest.raises(ValueError):
        ReviewRequest(goal="g", acs=[], original={}, final={"a.py": record})
    with pytest.raises(ValueError):
        JudgeRequest(goal="g", failure="f", test_path="t", test_content="c",
                     files={"a.py": record}, acs=[])
    with pytest.raises(ValueError):
        VerificationRecord(wrote_code=True, tier="test", reason_problem=record)
    # the selection key may not read a node record either
    with pytest.raises(ValueError):
        select_key(planned_test_points=[], test_results={}, rank=record, cost=1)


# ---------------------------------------------------------------------------
# Candidate isolation (a copy, not a git worktree; no destructive reset)
# ---------------------------------------------------------------------------


def test_candidate_workspace_is_an_isolated_copy(tmp_path: Path):
    source = tmp_path / "run"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("x = 1\n")
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    ws = create_candidate(tmp_path / "out", "N1", "HOW-1", source)
    assert ws.path == candidate_dir(tmp_path / "out", "N1", "HOW-1")
    assert (ws.path / "src" / "app.py").read_text() == "x = 1\n"
    assert not (ws.path / ".git").exists()  # git state never enters a candidate

    # a candidate edit does not touch the source tree (isolation)
    (ws.path / "src" / "app.py").write_text("x = 2\n")
    assert (source / "src" / "app.py").read_text() == "x = 1\n"

    before = snapshot_candidate(ws)
    (ws.path / "src" / "app.py").write_text("x = 3\n")
    audit = audit_candidate_boundary(ws, before, ["src/app.py"])
    assert audit.clean
    (ws.path / "src" / "other.py").write_text("y = 1\n")
    escaped = audit_candidate_boundary(ws, before, ["src/app.py"])
    assert not escaped.clean and "src/other.py" in escaped.violations

    abandon_candidate(ws)
    assert not ws.path.exists()


def test_how_exploration_limit_bounds_the_hows_a_node_may_open():
    # spendable = int(calls * 0.75); each explored How costs min_leaf_calls + 1.
    budget = Budget(calls=20, deadline_ts=1e12)
    assert how_exploration_limit(budget, 5, min_leaf_calls=3) == 3  # 15 // 4
    assert how_exploration_limit(Budget(calls=4, deadline_ts=1e12), 5,
                                 min_leaf_calls=3) == 0
    assert how_exploration_limit(budget, 2, min_leaf_calls=3) == 2


def test_how_exploration_limit_is_budget_only_when_the_caller_does_not_cap():
    """Ticket 20 step 2b D5: the runner passes ``n_hows=None`` so the cap is purely
    budget-derived, computed once from the node pool rather than recounted from the
    growing How list (a manager that authors Hows must not raise it)."""
    budget = Budget(calls=20, deadline_ts=1e12)
    assert how_exploration_limit(budget, None, min_leaf_calls=3) == 3
    assert how_exploration_limit(Budget(calls=4, deadline_ts=1e12), None,
                                 min_leaf_calls=3) == 0
    # the How count is irrelevant to the uncapped (cumulative) form
    assert how_exploration_limit(budget, None, min_leaf_calls=3) == \
        how_exploration_limit(budget, 999, min_leaf_calls=3)


def test_the_audit_key_and_the_picker_agree_on_rank_and_cost_ties():
    """Regression pin: the audit key once stored rank/cost UNSIGNED, so
    ``max(key=Selection.key)`` picked the OPPOSITE candidate on a rank/cost tie while
    the picker picked the documented winner - the same contradiction twice over."""
    low_rank = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=99)
    high_rank = _selection(covered=1, rate=1.0, review_score=5, rank=2, cost=1)
    assert pick([high_rank, low_rank]) is low_rank
    assert max([high_rank, low_rank], key=lambda s: s.key) is low_rank
    assert max([high_rank, low_rank], key=lambda s: s.order) is low_rank

    cheap = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=1)
    dear = _selection(covered=1, rate=1.0, review_score=5, rank=1, cost=99)
    assert pick([dear, cheap]) is cheap
    assert max([dear, cheap], key=lambda s: s.key) is cheap


def test_a_nan_or_mistyped_selection_field_is_rejected_not_compared():
    """A NaN pass rate made the winner depend on input order (NaN compares false with
    everything); a string rank failed lazily only when compared."""
    import pytest as _pytest

    for kwargs in ({"rate": float("nan")}, {"review_score": float("inf")},
                   {"rank": "1"}, {"rank": 0}, {"rank": True}, {"cost": -1},
                   {"cost": None}, {"covered": -1}):
        base = dict(covered=1, rate=1.0, review_score=5, rank=1, cost=1)
        base.update(kwargs)
        with _pytest.raises(ValueError):
            _selection(**base)
