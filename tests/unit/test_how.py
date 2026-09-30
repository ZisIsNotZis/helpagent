"""Ticket 20 step 2a — the How axis, the selection function, and immutability.

Covers the owner decision of 2026-09-30: the append-only How list with statuses, the
prior-as-hint table, the lexicographic selection function with its tie-breaks, the
manager loop's four decisions and its automatic-advance boundary, the model-maintained
node record area, and candidate isolation (a copy, never a git worktree / destructive
reset).
"""

from pathlib import Path

import pytest

from harness.budget import Budget
from harness.envelopes import SCHEMAS, HowList, PlanNode
from harness.how import (
    MANAGER_DECISIONS,
    How,
    HowFailure,
    HowList as HowListData,
    ManagerDecision,
    NodeRecord,
    NodeRecordView,
    PRIOR_DECAY,
    abandon_candidate,
    audit_candidate_boundary,
    candidate_dir,
    create_candidate,
    decide_after_failure,
    how_exploration_limit,
    how_list_from_envelope,
    how_viability,
    make_how,
    planned_test_score,
    prior_for_rank,
    select_key,
    snapshot_candidate,
)
from harness.leaf import ReviewVerdict


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


def test_how_list_envelope_ranks_contiguous_and_prior_from_rank():
    env = HowList.model_validate({
        "status": "ok", "comment": "three approaches",
        "hows": [
            {"how_id": "HOW-1", "text": "a", "rank": 1, "reason": "r1"},
            {"how_id": "HOW-2", "text": "b", "rank": 3, "reason": "r2"},
            {"how_id": "HOW-3", "text": "c", "rank": 2, "reason": "r3"},
        ]})
    with pytest.raises(Exception):
        HowList.model_validate({
            "status": "ok", "comment": "gap",
            "hows": [{"how_id": "HOW-1", "text": "a", "rank": 1, "reason": "r"},
                     {"how_id": "HOW-2", "text": "b", "rank": 3, "reason": "r"}]})
    data = how_list_from_envelope(env)
    assert [h.id for h in data] == ["HOW-1", "HOW-3", "HOW-2"]
    assert [h.prior for h in data] == [0.5, 0.25, 0.125]


def test_plan_node_binds_result_to_a_how_id():
    assert SCHEMAS["how_list"] is HowList
    assert len(SCHEMAS) == 27
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


def test_how_viability_is_prior_times_best_viable_child():
    assert how_viability(0.5, []) == 0.5  # a leaf How carries its own prior
    assert how_viability(0.5, [("active", 0.4), ("untried", 0.25)]) == pytest.approx(0.2)
    # failed/abandoned children are removed from the product
    assert how_viability(0.5, [("failed", 9.0), ("active", 0.4)]) == pytest.approx(0.2)
    # children exist but NONE is viable -> not viable
    assert how_viability(0.5, [("failed", 0.4), ("abandoned", 0.9)]) == 0.0


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


def test_selection_test_score_beats_review_score():
    strong_review = select_key(planned_test_points=[], test_results={},
                               review_verdicts=_positive_verdicts(),
                               rank=2, cost=9)
    weak_review_but_tests = select_key(
        planned_test_points=["t1", "t2"], test_results={"t1": True, "t2": True},
        review_verdicts=[], rank=1, cost=1)
    # the test component is compared FIRST
    assert weak_review_but_tests.key > strong_review.key
    assert strong_review.review_score > 0


def test_selection_ties_fall_through_rank_then_cost():
    a = select_key(planned_test_points=["t"], test_results={"t": True},
                   review_verdicts=_positive_verdicts(), rank=1, cost=50)
    b = select_key(planned_test_points=["t"], test_results={"t": True},
                   review_verdicts=_positive_verdicts(), rank=2, cost=1)
    assert a.key < b.key  # rank tie-break before cost
    c = select_key(planned_test_points=["t"], test_results={"t": True},
                   review_verdicts=_positive_verdicts(), rank=1, cost=50)
    d = select_key(planned_test_points=["t"], test_results={"t": True},
                   review_verdicts=_positive_verdicts(), rank=1, cost=5)
    assert d.key < c.key  # same rank -> smaller cost wins
    assert a.key == c.key


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
