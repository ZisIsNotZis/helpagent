"""Node-tree mechanics pinned with the scripted fake model (ticket 18, no live server).

The tree layer composes the working leaf (:mod:`harness.tree_run` calls
:func:`harness.leaf.run_leaf` verbatim) over a budgeted decomposition plan
(:mod:`harness.node`). These cases pin the twelve design-note invariants plus the
PlanNode / ``validate_decomposition`` contract, all against
:class:`harness.fake_model.FakeModelRunner` and a scripted ``run_tests`` so
``uv run pytest`` never touches a model server or a real pytest.

Covered: sibling disjointness (incl. canonicalization evasion), budget-1 cannot split,
reserve/release conservation, an internal node cannot close without a passing
integration verdict, root grader-path inheritance, L7 (spec bubble → subtree reset +
re-plan), L6 (exhausted leaf → re-split), the identical-re-split refusal, subtree reset
leaving siblings untouched, the shared-deadline stop, and that the tree calls
``run_leaf`` unchanged.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness import tree_run
from harness.attempts import Attempt
from harness.budget import Budget, BudgetError
from harness.envelopes import PlanNode
from harness.exec import ShapedResult
from harness.fake_model import FakeModelRunner
from harness.gate_report import GateReport
from harness.leaf import DeclaredTestCase, LeafOutcome, LeafSpec, _source_write_problem
from harness.node import (
    Decomposition,
    NodeSpec,
    SplitHistory,
    can_decompose,
    canonical_path,
    decomposition_from_envelope,
    plan_node,
    validate_decomposition,
)
from harness.runner import ledger_entries, reset_ledger_for_tests
from harness.trajectory import Trajectory
from harness.tree import ACEntry, TaskTree

_FAR = 2_000_000_000.0
_GRADER = "tests/test_grader_secret.py"
_FILES = {"pkg/a.py": "x = 1\n", "pkg/b.py": "y = 2\n"}


# ------------------------------------------------------------------- helpers


def ac(statement: str = "criterion", ac_id: str = "AC-1") -> dict:
    return {"ac_id": ac_id, "statement": statement, "check_kind": "test"}


def child(what: str, files, *, acs=None, kind: str = "leaf", est: int = 3,
          why: str = "because") -> dict:
    return {"what": what, "why": why, "kind": kind, "files": list(files),
            "acs": list(acs) if acs is not None else [ac()],
            "interfaces": [], "est_calls": est}


def plan_env(children, *, files, goal: str = "root goal", acs=(), behavior: str = "shared",
             notes: str = "notes") -> dict:
    return {"status": "ok", "comment": "planned", "goal": goal, "behavior": behavior,
            "implementation_notes": notes, "files": list(files), "acs": list(acs),
            "interfaces": [], "children": list(children)}


def leaf_outcome(claimed: bool = True, signal: str = "green", stop: str = "green",
                 self_test: str = "tests/test_self.py", **kw) -> LeafOutcome:
    base = {"claimed": claimed, "signal": signal, "attempts": [], "calls": 2, "wall_s": 0.0,
            "self_test": self_test, "questions": [], "exhausted": False,
            "exhaustion_reason": "", "layers_used": [], "stop_reason": stop}
    base.update(kw)
    return LeafOutcome(**base)


class FakeLeaf:
    """Scripted stand-in for ``harness.tree_run.run_leaf`` (records every call)."""

    def __init__(self, outcomes=None):
        self._outcomes = list(outcomes or [])
        self.specs: list[LeafSpec] = []
        self.budgets: list[Budget] = []
        self.extras: list[dict] = []
        self.calls = 0

    async def __call__(self, model, spec, workdir, budget, *, judge=None, iv=None, review=None,
                       run_tests=None, now=None, on_event=None):
        self.specs.append(spec)
        self.budgets.append(budget)
        self.extras.append({"judge": judge, "iv": iv, "run_tests": run_tests})
        self.calls += 1
        budget.take(1)
        if self._outcomes:
            return self._outcomes.pop(0)
        return leaf_outcome()


def _gate(green: bool) -> GateReport:
    if green:
        return GateReport(report_path="(scripted)", process_exit=0, canary="scripted",
                          expected_files=(), n_tests=1, n_failed=0, n_errors=0,
                          passed_ids=("scripted::test_ac1",), failed_ids=(), missing=(),
                          observed=True)
    return GateReport(report_path="(scripted)", process_exit=1, canary="scripted",
                      expected_files=(), n_tests=1, n_failed=1, n_errors=0,
                      passed_ids=(), failed_ids=("scripted::test_ac1",), missing=(),
                      observed=True, anomaly="tests-failed", detail="1 failure(s)")


class Gates:
    """Deterministic ``run_tests`` seam for the integration re-run."""

    def __init__(self, green: bool = True):
        self.green = green
        self.calls = 0
        self.selections: list[tuple[str, ...] | None] = []

    def __call__(self, workdir, node_ids=None) -> ShapedResult:
        self.calls += 1
        self.selections.append(tuple(node_ids) if node_ids is not None else None)
        gate = _gate(self.green)
        return ShapedResult(command=["pytest", "-q"], exit=gate.process_exit,
                            verdict="ok" if gate.green else "failed", excerpts=[], gate=gate)


def stage(workdir: Path, files=None) -> None:
    for rel, text in (files or _FILES).items():
        path = workdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def make_tree() -> TaskTree:
    return TaskTree(what="root goal", files=sorted(_FILES))


def run_tree_sync(model, root, tree, workdir, budget, **kw):
    reset_ledger_for_tests()
    kw.setdefault("root_grader_paths", (_GRADER,))
    return asyncio.run(tree_run.run_tree(model, root, tree, workdir, budget, **kw))


def ledger_kinds() -> list[str]:
    return [entry["kind"] for entry in ledger_entries()]


def ledger_with(kind: str) -> list[dict]:
    return [entry for entry in ledger_entries() if entry["kind"] == kind]


# ---------------------------------------------------------------------------
# 1-2. ticket 19 F: sibling files may OVERLAP (the tree serializes writers)
# ---------------------------------------------------------------------------


def test_sibling_files_may_overlap_and_boundaries_still_narrow():
    """Ticket 19 F: two children declaring the same file are ALLOWED (two requirements may
    legitimately change one file). The tree SERIALIZES overlapping writers and audits each
    node's declared boundary; child ⊆ parent is still enforced."""
    d = Decomposition(
        spec=NodeSpec(goal="root", files=("pkg/a.py", "pkg/b.py"), kind="internal"),
        children=(NodeSpec(goal="one", files=("pkg/a.py",), acs=("c",), kind="leaf"),
                  NodeSpec(goal="two", files=("pkg/a.py", "pkg/b.py"), acs=("c",), kind="leaf")),
        signature="sig")
    findings = validate_decomposition(
        d, parent_files={"pkg/a.py", "pkg/b.py"},
        candidate_files={"pkg/a.py", "pkg/b.py"}, depth=0, depth_cap=4, max_children=15)
    assert findings.ok                                  # overlapping is no longer a finding
    # a child outside the parent boundary is still refused (narrowing-only)
    out_of_boundary = Decomposition(
        spec=NodeSpec(goal="root", files=("pkg/a.py",), kind="internal"),
        children=(NodeSpec(goal="one", files=("pkg/c.py",), acs=("c",), kind="leaf"),),
        signature="sig")
    assert any(f.kind == "child-outside-boundary" for f in validate_decomposition(
        out_of_boundary, parent_files={"pkg/a.py"}, candidate_files={"pkg/a.py"},
        depth=0, depth_cap=4, max_children=15).items)


def test_path_canonicalization_keeps_boundary_narrowing_honest():
    """``./pkg/a.py`` and ``pkg/./a.py`` are the same file as ``pkg/a.py`` — the boundary
    check must canonicalize first or it is bypassable."""
    assert canonical_path("./pkg/a.py") == "pkg/a.py"
    assert canonical_path("pkg/./a.py") == "pkg/a.py"
    assert canonical_path("pkg/nested/../a.py") == "pkg/a.py"
    assert canonical_path("../evil.py") is None
    assert canonical_path("/etc/passwd") is None

    d = Decomposition(
        spec=NodeSpec(goal="root", files=("pkg/a.py",), kind="internal"),
        children=(NodeSpec(goal="one", files=("./pkg/a.py",), acs=("c",), kind="leaf"),
                  NodeSpec(goal="two", files=("pkg/./a.py",), acs=("c",), kind="leaf")),
        signature="sig")
    # canonicalized aliases are inside the boundary AND no longer an overlap finding
    findings = validate_decomposition(
        d, parent_files={"pkg/a.py"}, candidate_files={"pkg/a.py"},
        depth=0, depth_cap=4, max_children=15)
    assert findings.ok
    # an unusable path is its own structured finding, never an exception
    bad = Decomposition(
        spec=NodeSpec(goal="root", files=("pkg/a.py",), kind="internal"),
        children=(NodeSpec(goal="one", files=("../escape.py",), acs=("c",), kind="leaf"),),
        signature="sig")
    assert any(f.kind == "bad-path" for f in
               validate_decomposition(bad, parent_files={"pkg/a.py"},
                                      candidate_files={"pkg/a.py"}, depth=0,
                                      depth_cap=4, max_children=15).items)


# ---------------------------------------------------------------------------
# 3. a node with budget 1 cannot split
# ---------------------------------------------------------------------------


def test_budget_one_cannot_split(tmp_path, monkeypatch):
    """DESIGN §10.2: the node pool cannot fund two leaves, so the decomposer is never
    called and the node runs as a leaf; a BudgetError never escapes."""
    assert not can_decompose(Budget(calls=1, deadline_ts=_FAR))
    assert not can_decompose(Budget(calls=4, deadline_ts=_FAR))   # spendable 3 // 2 = 1
    assert can_decompose(Budget(calls=12, deadline_ts=_FAR))      # spendable 9 // 2 = 4

    stage(tmp_path)
    fake = FakeLeaf()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"),
                    acs=(), kind="internal")
    model = FakeModelRunner({})   # any plan_node call would exhaust the script
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=1, deadline_ts=_FAR))
    assert model.calls("plan_node") == []   # never decomposed
    assert fake.calls == 1                  # ran as a leaf instead
    assert out.claimed


# ---------------------------------------------------------------------------
# 4. reserve + release conservation
# ---------------------------------------------------------------------------


def test_split_keeps_reserve_and_releases_children(tmp_path, monkeypatch):
    """Reserve stays with the parent and unused child calls return: conservation holds
    at the join (no leak, no double-count)."""
    parent = Budget(calls=20, deadline_ts=_FAR)
    kids = parent.split_weighted([1, 1], min_each=3)
    assert sum(k.calls for k in kids) + parent.calls == 20      # nothing invented
    assert parent.calls >= int(20 * parent.reserve_fraction)    # reserve kept

    kids[0].take(4)
    assert parent.release(kids[0]) == kids[0].calls
    parent.release(kids[1])
    assert parent.calls == 20 - 4                               # only the spend is gone

    with pytest.raises(BudgetError):
        Budget(calls=2, deadline_ts=_FAR).split_weighted([1, 1], min_each=3)

    # at the tree join: every call spent or still in a pool
    stage(tmp_path)
    fake = FakeLeaf()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("one", ["pkg/a.py"]), child("two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"))]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=20, deadline_ts=_FAR))
    assert out.calls + out.budget.calls == 20                   # conservation holds


# ---------------------------------------------------------------------------
# 5. an internal node cannot close without a passing integration verdict
# ---------------------------------------------------------------------------


def _run_root_with_integration(workdir: Path, monkeypatch, *, green: bool):
    stage(workdir)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"),
                    acs=("the cross-child behavior holds",), kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"))]})
    fake = FakeLeaf()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    gates = Gates(green=green)
    out = run_tree_sync(model, root, make_tree(), workdir,
                        Budget(calls=30, deadline_ts=_FAR), run_tests=gates)
    return out, fake, gates


def test_internal_close_requires_integration_pass(tmp_path, monkeypatch):
    """Child claims alone never close an internal node: the integration check is
    re-run on the frozen tree, and a red verdict leaves the node open."""
    ok, _, gates = _run_root_with_integration(tmp_path / "ok", monkeypatch, green=True)
    assert ok.claimed and ok.root.stop_reason == "closed"
    assert set(ok.root.integration_verdicts.values()) == {"pass"}
    assert gates.calls == 1                                   # the check really re-ran
    assert all(c.stop_reason == "closed" for c in ok.root.children)

    bad, _, _ = _run_root_with_integration(tmp_path / "bad", monkeypatch, green=False)
    assert not bad.claimed and bad.root.stop_reason == "open"
    assert set(bad.root.integration_verdicts.values()) == {"fail"}
    assert all(c.stop_reason == "closed" for c in bad.root.children)  # children fine


# ---------------------------------------------------------------------------
# 6. grader paths always come from the root
# ---------------------------------------------------------------------------


def test_leaf_inherits_root_grader_paths(tmp_path, monkeypatch):
    """Every descendant LeafSpec carries the ROOT's grader set — never one a child
    could have declared."""
    stage(tmp_path)
    fake = FakeLeaf()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"))]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=30, deadline_ts=_FAR))
    assert out.claimed
    assert len(fake.specs) == 2
    assert all(spec.grader_paths == (_GRADER,) for spec in fake.specs)

    direct = tree_run.leaf_spec_from(
        NodeSpec(goal="g", files=("pkg/a.py",), acs=("c",)), tmp_path,
        root_grader_paths=("not/child/owned.py",))
    assert direct.grader_paths == ("not/child/owned.py",)


# ---------------------------------------------------------------------------
# 7. a spec bubble triggers L7: reset the parent subtree and re-plan
# ---------------------------------------------------------------------------


def test_spec_bubble_triggers_l7_and_resets_subtree(tmp_path, monkeypatch):
    """A child ``needs_parent``/``spec-bubble`` sends the owning parent back to its
    checkpoint and re-runs ``plan_node`` with the failure as evidence — never a fresh
    ``run_leaf`` on the unchanged spec."""
    stage(tmp_path)
    fake = FakeLeaf([
        leaf_outcome(claimed=False, signal="bubble", stop="spec-bubble", needs_parent=True,
                     exhaustion_reason="the parent spec contradicts the goal"),
    ])
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py")),
        plan_env([child("fix one corrected", ["pkg/a.py"]),
                  child("fix two corrected", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"), goal="root goal corrected",
                 behavior="the corrected contract"),
    ]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR))

    assert out.claimed
    assert len(model.calls("plan_node")) == 2                  # re-planned once
    resets = ledger_with("subtree_reset")
    assert resets and resets[0]["reason"] == "L7"
    assert "l7_respec" in ledger_kinds()
    goals = [spec.goal.splitlines()[0] for spec in fake.specs]
    assert goals == ["fix one", "fix one corrected", "fix two corrected"]
    assert goals.count("fix one") == 1                         # the bubbled spec never re-ran


# ---------------------------------------------------------------------------
# 8. an exhausted leaf triggers L6: re-split into smaller children
# ---------------------------------------------------------------------------


def test_exhausted_child_triggers_l6_resplit(tmp_path, monkeypatch):
    """``signal == "exhausted"`` restores the node's own checkpoint and re-plans it into
    smaller children (which then run)."""
    stage(tmp_path)
    fake = FakeLeaf([
        leaf_outcome(claimed=False, signal="exhausted", stop="attempts", exhausted=True,
                     exhaustion_reason="node exhausted"),
    ])
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix the whole working set", ["pkg/a.py", "pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py")),
        plan_env([child("fix part one", ["pkg/a.py"]), child("fix part two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"), goal="fix the whole working set"),
    ]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=True))

    assert "l6_resplit" in ledger_kinds()
    assert len(model.calls("plan_node")) == 2
    goals = [spec.goal.splitlines()[0] for spec in fake.specs]
    assert goals[0] == "fix the whole working set"             # exhausted first
    assert "fix part one" in goals and "fix part two" in goals  # re-split children ran
    assert out.claimed


# ---------------------------------------------------------------------------
# 9. an identical re-split is refused as wasted
# ---------------------------------------------------------------------------


def test_identical_resplit_is_refused_as_wasted(tmp_path, monkeypatch):
    """The T-31 "nine identical retries" defect: a re-split with the same signature and
    no shrink is recorded ``wasted`` and refused."""
    history = SplitHistory()
    assert history.accept("sig", n_children=2, max_child_budget=5)
    assert not history.accept("sig", n_children=2, max_child_budget=5)   # identical
    assert history.attempts[-1].verdict == "wasted"
    assert history.wasted == 1
    assert history.accept("sig", n_children=3, max_child_budget=3)       # more children: shrink
    assert history.accept("other", n_children=2, max_child_budget=9)     # new signature

    # tree-level: an L7 re-plan that returns the identical decomposition parks the node
    stage(tmp_path)
    fake = FakeLeaf([
        leaf_outcome(claimed=False, signal="bubble", stop="spec-bubble", needs_parent=True,
                     exhaustion_reason="spec is wrong"),
    ])
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    same = plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                    files=("pkg/a.py", "pkg/b.py"))
    model = FakeModelRunner({"plan_node": [same, same]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR))
    assert not out.claimed
    assert out.root.stop_reason == "parked"
    assert "split_wasted" in ledger_kinds()


# ---------------------------------------------------------------------------
# 10. a subtree reset leaves siblings untouched and records the discarded SHAs
# ---------------------------------------------------------------------------


def test_subtree_reset_leaves_siblings_untouched(tmp_path):
    """L6/L7 reset restores only the node's own branch (its post-checkpoint commits),
    keeps committed sibling work, removes untracked output, and ledgers every discarded
    SHA BEFORE the hard reset."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "base.py").write_text("base = 1\n")
    traj = Trajectory(workdir)
    traj.ensure_git()
    reset_ledger_for_tests()

    (workdir / "sibling.py").write_text("kept\n")
    traj.checkpoint("sibling")
    checkpoint = traj.checkpoint("N-2")                    # N-2's pre-checkpoint
    (workdir / "node_work.py").write_text("discard me\n")
    work_sha = traj.checkpoint("N-2-work")
    (workdir / "scratch.py").write_text("untracked\n")     # never committed

    discarded = traj.reset_to(checkpoint, reason="L6", detail="node exhausted")

    assert discarded == [work_sha]
    assert (workdir / "sibling.py").read_text() == "kept\n"   # sibling branch untouched
    assert not (workdir / "node_work.py").exists()            # node commit discarded
    assert not (workdir / "scratch.py").exists()              # untracked output cleaned
    assert traj.discarded[-1].sha == work_sha
    entries = ledger_with("checkpoint_discarded")
    assert entries and entries[0]["sha"] == work_sha          # ledgered before reset


# ---------------------------------------------------------------------------
# 11. the shared deadline stops the tree and keeps the checkpoints
# ---------------------------------------------------------------------------


def test_deadline_expiry_stops_tree_and_keeps_checkpoints(tmp_path, monkeypatch):
    """After the shared deadline no new node starts; the checkpoints stay for resume."""
    stage(tmp_path)
    clock = {"t": 0.0}
    calls = {"n": 0}

    async def fake_leaf(model, spec, workdir, budget, **kw):
        calls["n"] += 1
        budget.take(1)
        clock["t"] = 200.0          # the window closes during the first child
        return leaf_outcome()

    monkeypatch.setattr(tree_run, "run_leaf", fake_leaf)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"))]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=100.0), now=lambda: clock["t"])

    assert calls["n"] == 1                       # the second child never started
    assert out.root.stop_reason == "parked"
    assert not out.claimed
    assert len(out.checkpoints) >= 2             # root + the child that ran
    assert [c.stop_reason for c in out.root.children] == ["closed", "parked"]


# ---------------------------------------------------------------------------
# 12. the tree reuses the leaf loop verbatim
# ---------------------------------------------------------------------------


def test_tree_calls_run_leaf_unchanged(tmp_path, monkeypatch):
    """The tree layer must call ``run_leaf`` with a ``LeafSpec``/``Budget`` (and pass the
    injected judge/iv/run_tests through) rather than reimplement the loop."""
    stage(tmp_path)
    captured = []

    async def fake(model, spec, workdir, budget, *, judge=None, iv=None, review=None, run_tests=None,
                   now=None, on_event=None):
        captured.append((spec, budget, judge, iv, review, run_tests))
        budget.take(1)
        return leaf_outcome()

    monkeypatch.setattr(tree_run, "run_leaf", fake)
    marker = object()
    root = NodeSpec(goal="the only goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([], files=("pkg/a.py", "pkg/b.py"), goal="the only goal",
                 acs=[ac("the only criterion")])]})   # children=[] ⇒ this node is a leaf
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=10, deadline_ts=_FAR), judge=marker, review=marker,
                        run_tests=None)

    assert len(captured) == 1
    spec, budget, judge, iv, review, run_tests = captured[0]
    assert isinstance(spec, LeafSpec) and isinstance(budget, Budget)
    assert judge is marker and review is marker
    assert iv is None and run_tests is None
    assert spec.grader_paths == (_GRADER,)
    assert out.claimed


# ---------------------------------------------------------------------------
# 13-16. structural close rule + runtime write boundary (ticket 18 gaps 1-3)
# ---------------------------------------------------------------------------


class WritingTree:
    """Monkeypatched ``run_leaf`` for the structural close-rule cases.

    A SOURCE child writes its declared file and records the write in an ``Attempt`` (so
    the runner sees an ACTUAL writing descendant); the dedicated INTEGRATION leaf
    (empty write boundary) writes a test and returns the scripted self-test path — or
    none, to exercise the 'no test artifact ⇒ no integration verdict' hole.
    """

    def __init__(self, *, integration_self_test: str | None =
                 "tests/test_integration.py", integration_claims: bool = True):
        self.specs: list[LeafSpec] = []
        self.writer_calls: list[str] = []
        self.integration_calls = 0
        self._integration_self_test = integration_self_test
        self._integration_claims = integration_claims

    async def __call__(self, model, spec, workdir, budget, *, judge=None, iv=None, review=None,
                       run_tests=None, now=None, on_event=None):
        budget.take(1)
        self.specs.append(spec)
        boundary = list(spec.write_boundary or ())
        if boundary:
            rel = boundary[0]
            target = workdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# rewritten\n")
            self.writer_calls.append(rel)
            attempt = Attempt(node_id="leaf", layer="implementation",
                              strategy="L1-resample", outcome="pass",
                              touched_files=[rel], claimed_delta=f"wrote {rel}")
            return leaf_outcome(claimed=True, attempts=[attempt])
        self.integration_calls += 1
        if self._integration_self_test:
            path = workdir / self._integration_self_test
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_integration():\n    assert seen_integration()\n")
        if not self._integration_claims:
            # A red test exposed on the frozen tree, no claim: its verdict is the
            # parent's report-gated re-run, not the leaf's own claim.
            return leaf_outcome(claimed=False, signal="honest-failure", stop="attempts",
                                self_test=self._integration_self_test,
                                exhaustion_reason="exposed a red integration check")
        return leaf_outcome(self_test=self._integration_self_test)


class SequenceGates:
    """A scripted ``run_tests`` whose verdict flips on the Nth integration run."""

    def __init__(self, greens: list[bool]):
        self._greens = list(greens)
        self.calls = 0

    def __call__(self, workdir, node_ids=None) -> ShapedResult:
        green = self._greens[min(self.calls, len(self._greens) - 1)]
        self.calls += 1
        gate = _gate(green)
        return ShapedResult(command=["pytest", "-q"], exit=gate.process_exit,
                            verdict="ok" if gate.green else "failed", excerpts=[],
                            gate=gate)


def _plan_two_writers() -> FakeModelRunner:
    return FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"]), child("fix two", ["pkg/b.py"])],
                 files=("pkg/a.py", "pkg/b.py"))]})


def test_close_requires_a_passing_integration_check_for_two_writers(tmp_path, monkeypatch):
    """Two writing descendants MUST have a report-gated integration check before the
    node closes; child claims alone are never enough (ticket 18 gap 1)."""
    stage(tmp_path)
    fake = WritingTree()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    gates = Gates(green=True)
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=gates)

    assert out.claimed and out.root.stop_reason == "closed"
    assert out.root.close_rule == "integration"
    assert set(out.root.integration_verdicts.values()) == {"pass"}
    assert fake.integration_calls == 1 and gates.calls == 1


def test_single_writer_closes_without_integration(tmp_path, monkeypatch):
    """≤1 writing descendant: there is nothing to integrate, so the node closes on the
    child claims alone and records ``close_single_writer`` (ticket 18 gap 1)."""
    stage(tmp_path)
    fake = WritingTree()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py",), acs=(), kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"])], files=("pkg/a.py",))]})
    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=True))

    assert out.claimed and out.root.close_rule == "close_single_writer"
    assert out.root.integration_verdicts == {}
    assert fake.integration_calls == 0        # the integration leaf was never run


def test_integration_leaf_without_a_test_artifact_cannot_close(tmp_path, monkeypatch):
    """An 'integration leaf' that claims green but exposes no test artifact is NOT a
    verdict: no keys ⇒ no close, and the node parks ``needs-integration``."""
    stage(tmp_path)
    fake = WritingTree(integration_self_test=None)
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=True))

    assert not out.claimed
    assert out.root.stop_reason == "parked"
    assert out.root.close_rule == "needs-integration"
    assert "needs-integration" in out.root.evidence
    assert fake.integration_calls == 1


def test_failed_integration_verdict_reopens_its_writers(tmp_path, monkeypatch):
    """A failing integration verdict reopens the responsible writers and re-integrates;
    the reopen is bounded (≤2) and then parks with a recorded reason — never a close on
    a stale child (ticket 18 gap 2)."""
    stage(tmp_path)
    fake = WritingTree()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=False))

    assert not out.claimed and out.root.stop_reason == "parked"
    assert out.root.close_rule == "needs-integration"
    assert out.root.integration_reopen_rounds == tree_run._MAX_INTEGRATION_REOPEN
    assert "integration_reopen" in ledger_kinds()
    # the two writers were re-run on each of the two reopen rounds; the integration
    # leaf's test is re-verified (not rewritten), so it ran once.
    assert fake.writer_calls == ["pkg/a.py", "pkg/b.py"] * 3
    assert fake.integration_calls == 1


def test_failed_integration_reopens_writers_then_a_passing_verdict_closes(tmp_path, monkeypatch):
    """A red integration check (the integration leaf exposed it without claiming) is
    force-closed, its failure reopens the writers, and the re-run verdict closes the node
    — the integration leaf's own claim is not the gate (ticket 18 gap 1 + gap 2)."""
    stage(tmp_path)
    fake = WritingTree(integration_claims=False)
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    gates = SequenceGates([False, True])       # red, then green after the writers re-run
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=gates)

    assert out.claimed and out.root.stop_reason == "closed"
    assert out.root.close_rule == "integration"
    assert set(out.root.integration_verdicts.values()) == {"pass"}
    assert out.root.integration_reopen_rounds == 1
    assert fake.integration_calls == 1
    assert fake.writer_calls == ["pkg/a.py", "pkg/b.py"] * 2   # initial + one reopen


def test_declared_write_boundary_is_enforced_at_runtime(tmp_path):
    """``leaf_spec_from`` hands a child its declared files as BOTH the view and the write
    boundary: a sibling's file is refused (parameter-layer, never a crash), its own file
    and a declared-but-missing path it is meant to create are writable (ticket 18 gap 3)."""
    stage(tmp_path)
    sib1 = tree_run.leaf_spec_from(
        NodeSpec(goal="one", files=("pkg/a.py", "pkg/new.py"), acs=("c",)),
        tmp_path, root_grader_paths=(_GRADER,))
    sib2 = tree_run.leaf_spec_from(
        NodeSpec(goal="two", files=("pkg/b.py",), acs=("c",)),
        tmp_path, root_grader_paths=(_GRADER,))

    assert sib1.write_boundary == ("pkg/a.py", "pkg/new.py")
    assert set(sib1.files) == {"pkg/a.py"}         # the missing path is not in the view
    assert set(sib2.files) == {"pkg/b.py"}
    # own file and a declared-but-missing file are writable
    assert _source_write_problem("pkg/a.py", sib1, None) == ""
    assert _source_write_problem("pkg/new.py", sib1, None) == ""
    # the sibling's file is refused, and a path alias does not evade the boundary
    assert "boundary" in _source_write_problem("pkg/b.py", sib1, None)
    assert _source_write_problem("./pkg/b.py", sib1, None) != ""

    # the single-leaf driver sets no explicit boundary ⇒ behaviour unchanged.
    open_spec = LeafSpec(goal="g", files=dict(_FILES), acs=[], interfaces=[])
    assert open_spec.write_boundary is None
    assert _source_write_problem("pkg/b.py", open_spec, None) == ""


# ---------------------------------------------------------------------------
# PlanNode envelope + validate_decomposition contract
# ---------------------------------------------------------------------------


def test_plan_node_envelope_shape():
    base = plan_env([child("one", ["pkg/a.py"])], files=("pkg/a.py",), acs=())
    PlanNode.model_validate({"status": "ok", "comment": "c", **base})
    # children cap 15
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "ok", "comment": "c", **base,
                                 "children": [child(f"c{i}", ["pkg/a.py"]) for i in range(16)]})
    # est_calls >= 1
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "ok", "comment": "c", **base,
                                 "children": [child("one", ["pkg/a.py"], est=0)]})
    # the unable branch forbids payload fields (§0)
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "unable", "comment": "c", "unable_reason": "r",
                                 "goal": "g"})


def test_validate_decomposition_shape_rules():
    parent = {"pkg/a.py", "pkg/b.py"}

    def findings(children, *, spec_files=("pkg/a.py", "pkg/b.py"), kind="internal",
                 spec_acs=("root ac",)):
        d = Decomposition(
            spec=NodeSpec(goal="root", files=spec_files, acs=spec_acs, kind=kind),
            children=tuple(children), signature="sig")
        return validate_decomposition(
            d, parent_files=parent, candidate_files=parent, depth=0, depth_cap=4,
            max_children=15).items

    # child outside the parent boundary (narrowing-only)
    assert any(f.kind == "child-outside-boundary" for f in
               findings([NodeSpec(goal="one", files=("pkg/c.py",), acs=("c",))]))
    # leaf without an AC map
    assert any(f.kind == "leaf-empty-acs" for f in
               findings([], spec_files=("pkg/a.py",), kind="leaf", spec_acs=()))
    assert any(f.kind == "leaf-child-empty-acs" for f in
               findings([NodeSpec(goal="one", files=("pkg/a.py",), acs=(), kind="leaf")]))
    # duplicate child goal (normalized)
    assert any(f.kind == "duplicate-child" for f in
               findings([NodeSpec(goal="Fix  It", files=("pkg/a.py",), acs=("c",)),
                         NodeSpec(goal="fix it", files=("pkg/b.py",), acs=("c",))]))
    # depth cap
    d = Decomposition(
        spec=NodeSpec(goal="root", files=("pkg/a.py",), acs=("c",), kind="internal"),
        children=(NodeSpec(goal="one", files=("pkg/a.py",), acs=("c",)),),
        signature="sig")
    capped = validate_decomposition(d, parent_files={"pkg/a.py"},
                                    candidate_files={"pkg/a.py"}, depth=5, depth_cap=4,
                                    max_children=15)
    assert any(f.kind == "depth-cap" for f in capped.items)
    # ungrounded file token in free text
    assert any(f.kind == "ungrounded-reference" for f in
               findings([NodeSpec(goal="edit pkg/ghost.py", files=("pkg/a.py",), acs=("c",))]))
    # a clean decomposition has no findings
    assert findings([NodeSpec(goal="one", files=("pkg/a.py",), acs=("c",)),
                     NodeSpec(goal="two", files=("pkg/b.py",), acs=("c",))]) == []


def test_plan_node_one_call_reasks_once_then_forces_a_leaf():
    """Invalid output never crashes and never silently produces a child: one re-ask with
    the findings as evidence, then a force-leaf (``None``)."""
    bad = plan_env([child("one", ["pkg/a.py"], acs=[])], files=("pkg/a.py",))
    model = FakeModelRunner({"plan_node": [bad, bad]})
    budget = Budget(calls=5, deadline_ts=_FAR)
    result = asyncio.run(plan_node(model, goal="root", boundary={"pkg/a.py"},
                                   candidate_files={"pkg/a.py"}, depth=0, budget=budget))
    assert result is None
    calls = model.calls("plan_node")
    assert len(calls) == 2
    assert "plan_node findings" in calls[1].question      # re-ask carries the evidence
    assert budget.spent_calls == 2


def test_plan_node_returns_a_valid_decomposition():
    good = plan_env([child("one", ["pkg/a.py"]), child("two", ["pkg/b.py"])],
                    files=("pkg/a.py", "pkg/b.py"))
    model = FakeModelRunner({"plan_node": [good]})
    result = asyncio.run(plan_node(model, goal="root",
                                   boundary={"pkg/a.py", "pkg/b.py"},
                                   candidate_files={"pkg/a.py", "pkg/b.py"}, depth=0))
    assert isinstance(result, Decomposition)
    assert result.spec.kind == "internal"
    assert [c.goal for c in result.children] == ["one", "two"]
    assert result.signature


# ---------------------------------------------------------------------------
# blind CLI driver contract
# ---------------------------------------------------------------------------


def test_v2_tree_driver_builds_the_root_and_withholds_grader_paths():
    """The driver's root spec: source-only boundary, the extracted request ACs as the
    root integration map, and the withheld grader set injected from the root."""
    from bench import v2_tree

    task = {"task_id": "T-demo", "task_dir": "",
            "request": "Fix the expiry bug. It must not crash.",
            "files": {"pkg/a.py": "x = 1\n", "pkg/b.py": "y = 2\n",
                      "tests/test_a.py": "def test_x():\n    pass\n"}}
    root, grader_paths = v2_tree.build_root(task)
    assert root.kind == "internal"
    assert root.files == ("pkg/a.py", "pkg/b.py")          # source only
    assert root.acs == ("Fix the expiry bug.", "It must not crash.")
    assert grader_paths == ("tests/test_a.py",)

    args = v2_tree.build_parser().parse_args(["--task", "x"])
    assert args.judge is True and args.iv is True             # independent machinery ON
    assert args.review is True                                # review verification ON
    off = v2_tree.build_parser().parse_args(["--task", "x", "--no-judge", "--no-iv"])
    assert off.judge is False and off.iv is False
    assert v2_tree.build_parser().parse_args(
        ["--task", "x", "--no-review"]).review is False


# ---------------------------------------------------------------------------
# gap A: the post-hoc write-boundary audit (code the gate runs cannot change the tree)
# ---------------------------------------------------------------------------


class EscapingLeaf:
    """Scripted ``run_leaf`` that writes its declared boundary + its own test, then runs
    ``escape`` inside the shared workdir — exactly what a run-authored TEST can do at
    import time, since pytest executes it in the study tree."""

    def __init__(self, escape, *, test_path: str = "tests/test_leaf.py"):
        self._escape = escape
        self._test_path = test_path
        self.specs: list[LeafSpec] = []
        self.calls = 0

    async def __call__(self, model, spec, workdir, budget, *, judge=None, iv=None, review=None,
                       run_tests=None, now=None, on_event=None):
        budget.take(1)
        self.calls += 1
        self.specs.append(spec)
        boundary = list(spec.write_boundary or ())
        rel = boundary[0] if boundary else None
        if rel is not None:
            target = workdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# rewritten\n")
        test = workdir / self._test_path
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text("def test_leaf():\n    assert True\n")
        self._escape(workdir)
        attempt = Attempt(node_id="leaf", layer="implementation",
                          strategy="L1-resample", outcome="pass",
                          touched_files=[rel] if rel else [],
                          claimed_delta="wrote the boundary")
        return leaf_outcome(claimed=True, attempts=[attempt], self_test=self._test_path)


def _single_writer_root(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("fix one", ["pkg/a.py"])], files=("pkg/a.py", "pkg/b.py"))]})
    return run_tree_sync(model, root, make_tree(), tmp_path,
                         Budget(calls=20, deadline_ts=_FAR), run_tests=Gates(green=True))


def test_boundary_escape_is_detected_restored_and_never_claimed(tmp_path, monkeypatch):
    """A sibling file overwritten from inside the leaf's own test is a boundary escape:
    the run must NOT claim, the exact path is recorded, and it is restored from the
    pre-leaf snapshot so the sibling's work is never left damaged (gap A)."""
    stage(tmp_path)
    fake = EscapingLeaf(lambda wd: (wd / "pkg/b.py").write_text("hijacked\n"))
    out = _single_writer_root(tmp_path, monkeypatch, fake)

    assert not out.claimed and out.root.stop_reason == "open"
    child_out = out.root.children[0]
    assert child_out.stop_reason == "boundary-escape"
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"      # restored
    assert (tmp_path / "pkg/a.py").read_text() == "# rewritten\n"  # its own boundary kept
    audit = child_out.boundary_audit
    assert audit is not None and not audit.clean
    assert audit.violations == ["pkg/b.py"]
    assert audit.restored == ["pkg/b.py"] and audit.removed == []
    escapes = ledger_with("boundary_escape")
    assert escapes and escapes[0]["violations"] == ["pkg/b.py"]


def test_a_test_file_renamed_into_a_source_path_is_a_boundary_escape(tmp_path, monkeypatch):
    """The allowed set is EXACTLY 'boundary + test paths': renaming the leaf's own test
    into an undeclared source path is caught (the destination is neither) and removed
    (gap A pitfall)."""
    stage(tmp_path)

    def escape(wd):
        (wd / "tests/test_leaf.py").rename(wd / "pkg/hijack.py")

    fake = EscapingLeaf(escape)
    out = _single_writer_root(tmp_path, monkeypatch, fake)

    assert not out.claimed
    assert not (tmp_path / "pkg/hijack.py").exists()             # added escape removed
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"       # sibling untouched
    assert (tmp_path / "pkg/a.py").read_text() == "# rewritten\n"
    audit = out.root.children[0].boundary_audit
    assert "pkg/hijack.py" in audit.violations
    assert audit.removed == ["pkg/hijack.py"]


def test_boundary_audit_is_clean_for_a_declared_write(tmp_path, monkeypatch):
    """A leaf that writes only its declared boundary and its own test passes the audit
    and keeps its claim (the audit must not punish legitimate work)."""
    stage(tmp_path)
    out = _single_writer_root(tmp_path, monkeypatch, EscapingLeaf(lambda wd: None))

    assert out.claimed and out.root.stop_reason == "closed"
    audit = out.root.children[0].boundary_audit
    assert audit.clean and audit.violations == []
    assert (tmp_path / "pkg/a.py").read_text() == "# rewritten\n"
    assert (tmp_path / "tests/test_leaf.py").exists()            # the leaf's own test kept


def test_audit_allowed_set_is_boundary_plus_test_paths(tmp_path):
    """The audit's allowed set is the canonicalized declared boundary OR any test path;
    every other changed/added/removed path is a violation, restored/deleted."""
    stage(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_keep.py").write_text("keep\n")
    before = tree_run.snapshot_workdir(tmp_path)

    (tmp_path / "pkg/a.py").write_text("changed\n")               # boundary write
    (tmp_path / "pkg/b.py").write_text("hijacked\n")              # violation (changed)
    (tmp_path / "pkg/evil.py").write_text("new\n")                # violation (added)
    (tmp_path / "tests/test_new.py").write_text("new test\n")     # test path
    (tmp_path / "tests/test_keep.py").unlink()                    # test path: allowed

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ("./pkg/a.py",))

    assert audit.violations == ["pkg/b.py", "pkg/evil.py"]
    assert audit.restored == ["pkg/b.py"] and audit.removed == ["pkg/evil.py"]
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"
    assert not (tmp_path / "pkg/evil.py").exists()
    assert (tmp_path / "pkg/a.py").read_text() == "changed\n"    # boundary write kept
    assert (tmp_path / "tests/test_new.py").exists()             # test write kept
    assert not (tmp_path / "tests/test_keep.py").exists()        # test removal allowed


def test_run_record_includes_the_boundary_audit(tmp_path, monkeypatch):
    """The audit result rides the persisted run record (gap A: 'record the audit result
    on the outcome AND in the run record')."""
    from bench import v2_tree

    stage(tmp_path)
    fake = EscapingLeaf(lambda wd: (wd / "pkg/b.py").write_text("hijacked\n"))
    out = _single_writer_root(tmp_path, monkeypatch, fake)
    record = v2_tree.node_record(out.root)
    assert record["boundary_audit"] is None           # the internal node ran no leaf
    assert record["children"][0]["boundary_audit"]["violations"] == ["pkg/b.py"]


# ---------------------------------------------------------------------------
# ticket 18 round 4: the audit's RESTORE path and snapshot scope
# ---------------------------------------------------------------------------


def test_audit_detects_symlinks_and_never_writes_through_them(tmp_path):
    """A leaf that replaces a sibling file with a symlink is a violation; the restore
    removes the LINK and rewrites the original file, so the link target is never entered
    (the pre-fix restore followed the link and corrupted what it pointed at)."""
    stage(tmp_path)
    before = tree_run.snapshot_workdir(tmp_path)
    (tmp_path / "pkg/b.py").unlink()
    os.symlink(tmp_path / "pkg/a.py", tmp_path / "pkg/b.py")

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ("pkg/a.py",))

    assert audit.violations == ["pkg/b.py"]
    assert audit.links == {"pkg/b.py": str(tmp_path / "pkg/a.py")}
    assert (tmp_path / "pkg/a.py").read_text() == "x = 1\n"   # the target is untouched
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"   # the original is restored
    assert "pkg/b.py" in audit.restored


def test_audit_records_a_symlinked_directory_without_traversing_it(tmp_path):
    """A symlinked directory inside the workdir is recorded as a link violation with its
    target and never entered, so nothing outside the workdir can be compared or edited."""
    stage(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("secret\n")
    before = tree_run.snapshot_workdir(tmp_path)

    os.symlink(outside, tmp_path / "pkg/linked")

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ())

    assert "pkg/linked" in audit.violations
    assert audit.links["pkg/linked"] == str(outside)
    assert not any(v.startswith("pkg/linked/") for v in audit.violations)
    assert not (tmp_path / "pkg/linked").exists()             # the link itself was removed
    assert (outside / "secret.py").read_text() == "secret\n"  # never entered or edited


def test_audit_detects_a_hardlinked_target_but_never_writes_through_it(tmp_path):
    """A hardlinked target (st_nlink > 1) is detected and recorded but NOT written
    through: the restore is refused per path and the violation still counts."""
    stage(tmp_path)
    before = tree_run.snapshot_workdir(tmp_path)
    os.link(tmp_path / "pkg/b.py", tmp_path / "pkg/b_link.py")
    (tmp_path / "pkg/b.py").write_text("hijacked\n")          # shared inode: both change

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ("pkg/a.py",))

    assert "pkg/b.py" in audit.violations and "pkg/b_link.py" in audit.violations
    assert audit.restored == []
    assert any(v.startswith("pkg/b.py:") and "hard links" in v
               for v in audit.restore_refused)


def test_audit_records_a_metadata_only_change_and_does_not_repair_it(tmp_path):
    """A chmod/ownership-only change is invisible to content comparison, so it is
    recorded as a metadata violation and deliberately left unrepaired."""
    stage(tmp_path)
    before = tree_run.snapshot_workdir(tmp_path)
    (tmp_path / "pkg/b.py").chmod(0o600)

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ("pkg/a.py",))

    assert audit.violations == ["pkg/b.py"]
    assert audit.metadata == ["pkg/b.py"]
    assert audit.restored == []
    assert stat.S_IMODE((tmp_path / "pkg/b.py").stat().st_mode) == 0o600  # left as found


def test_restore_is_refused_when_a_parent_component_is_gone(tmp_path):
    """A restore that cannot be done safely (a parent component no longer a real
    directory) is recorded per path instead of silently 'restoring'."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/b.py").write_text("y = 2\n")
    before = tree_run.snapshot_workdir(tmp_path)
    (tmp_path / "pkg/b.py").unlink()
    (tmp_path / "pkg").rmdir()

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ())

    assert "pkg/b.py" in audit.violations
    assert any(r.startswith("pkg/b.py:") and "parent" in r for r in audit.restore_refused)
    assert audit.restored == []


def test_audit_includes_dot_git_and_excludes_only_caches(tmp_path):
    """``.git/**`` is now in scope (a leaf that tampers the harness's git state is a
    violation); ONLY interpreter/pytest cache artifacts are excluded."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("baseline\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/a.py").write_text("x = 1\n")
    before = tree_run.snapshot_workdir(tmp_path)

    (tmp_path / ".git/config").write_text("tampered\n")           # git tamper: violation
    (tmp_path / "pkg/__pycache__").mkdir()
    (tmp_path / "pkg/__pycache__/a.cpython-312.pyc").write_bytes(b"\x00")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / ".pytest_cache/x").write_text("cache\n")

    audit = tree_run.audit_leaf_boundary(tmp_path, before, ("pkg/a.py",))

    assert audit.violations == [".git/config"]
    assert (tmp_path / ".git/config").read_text() == "baseline\n"  # restored byte-identically


def test_snapshot_skips_oversized_files_and_records_the_skip(tmp_path):
    """The snapshot is bounded: a file larger than the cap is never read/restored, and
    the skip is recorded so the limit is visible."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/big.py").write_text("x" * 5000)

    state = tree_run.snapshot_workdir(tmp_path, max_file_bytes=1000)

    assert "pkg/big.py" not in state.files
    assert any("pkg/big.py" in s and "snapshot cap" in s for s in state.skipped)


def test_snapshot_caps_the_file_count_and_records_the_skip(tmp_path):
    """At most ``max_files`` files are recorded; the count cap is recorded too."""
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("x = 1\n")

    state = tree_run.snapshot_workdir(tmp_path, max_files=3)

    assert len(state.files) == 3
    assert any("file-count cap" in s for s in state.skipped)


def test_symlink_escape_through_the_tree_is_detected_and_never_claimed(tmp_path, monkeypatch):
    """Finding 2 through the tree: a leaf-authored symlink escape does not claim, and the
    restore never follows the link (the sibling's data is intact and the file restored)."""
    stage(tmp_path)
    (tmp_path / "outside").write_text("secret\n")

    def escape(wd):
        (wd / "pkg/b.py").unlink()
        os.symlink(wd / "outside", wd / "pkg/b.py")

    out = _single_writer_root(tmp_path, monkeypatch, EscapingLeaf(escape))

    assert not out.claimed
    child = out.root.children[0]
    assert child.stop_reason == "boundary-escape"
    audit = child.boundary_audit
    assert "pkg/b.py" in audit.violations
    assert audit.links.get("pkg/b.py") == str(tmp_path / "outside")
    assert (tmp_path / "outside").read_text() == "secret\n"   # never written through
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"   # restored


def test_tree_survives_a_bare_unable_self_test_envelope(tmp_path, monkeypatch):
    """P0 through the tree: the real ``run_leaf`` with a bare ``unable`` self-test
    envelope takes the honest refusal instead of crashing the whole run."""
    from harness.leaf import run_leaf as real_run_leaf

    monkeypatch.setattr(tree_run, "run_leaf", real_run_leaf)
    stage(tmp_path)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    model = FakeModelRunner({
        "plan_node": [plan_env([child("fix one", ["pkg/a.py"])],
                               files=("pkg/a.py", "pkg/b.py"))],
        "write_test": [{"status": "unable", "comment": "cannot",
                        "unable_reason": "no interpreter"}],
    })

    out = run_tree_sync(model, root, make_tree(), tmp_path,
                        Budget(calls=20, deadline_ts=_FAR), run_tests=Gates(green=True))

    assert not out.claimed
    child_out = out.root.children[0]
    assert child_out.leaf is not None and child_out.leaf.stop_reason == "self-test"


# ---------------------------------------------------------------------------
# gap B: the integration verdict FAILS CLOSED
# ---------------------------------------------------------------------------


def _integration_result(gate, exit_code: int = 0) -> ShapedResult:
    return ShapedResult(command=["pytest", "-q"], exit=exit_code, verdict="ok",
                        excerpts=[], gate=gate)


def _iv_root() -> tuple[TaskTree, str]:
    tree = TaskTree(what="root", files=["pkg/a.py"])
    key = "tests/test_child.py::test_x"
    findings = tree.root.set_ac_test_map([
        ACEntry(ac_id="AC-1", statement="integration holds", check_kind="test",
                check_hint=key)])
    assert findings.ok
    return tree, key


def test_integration_verdict_fails_closed_without_a_report_gate(tmp_path):
    """``pass`` requires the machine-readable report gate to be green for the check: a
    gate-less exit-0 result, an anomalous report with exit forced to 0, and a missing
    gate are all ``fail`` (gap B)."""
    stage(tmp_path)
    tree, key = _iv_root()
    no_gate = asyncio.run(tree_run.integration_verdicts(
        tree, tree.root, lambda wd, node_ids=None: _integration_result(None), tmp_path))
    assert no_gate.verdicts == {key: "fail"}

    tree, key = _iv_root()
    lie = asyncio.run(tree_run.integration_verdicts(
        tree, tree.root,
        lambda wd, node_ids=None: _integration_result(_gate(False), exit_code=0),
        tmp_path))
    assert lie.verdicts == {key: "fail"}          # anomalous report, exit 0 ⇒ still fail

    tree, key = _iv_root()
    good = asyncio.run(tree_run.integration_verdicts(
        tree, tree.root,
        lambda wd, node_ids=None: _integration_result(_gate(True), exit_code=0),
        tmp_path))
    assert good.verdicts == {key: "pass"}         # a green report is the only pass


class GatelessGates:
    """``run_tests`` whose result exits 0 but carries NO machine-readable gate (gap B)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, workdir, node_ids=None) -> ShapedResult:
        self.calls += 1
        return _integration_result(None, exit_code=0)


def test_integration_without_a_report_gate_cannot_close(tmp_path, monkeypatch):
    """A gate-less integration re-run (exit 0, no report) never closes the parent: the
    node parks ``needs-integration`` instead of treating exit 0 as a pass (gap B)."""
    stage(tmp_path)
    fake = WritingTree()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=GatelessGates())

    assert not out.claimed
    assert out.root.stop_reason == "parked"
    assert out.root.close_rule == "needs-integration"
    assert set(out.root.integration_verdicts.values()) == {"fail"}
    assert fake.integration_calls == 1


# ---------------------------------------------------------------------------
# gap C: the integration leaf reads the code it integrates (read-only)
# ---------------------------------------------------------------------------


def test_integration_leaf_reads_the_code_under_integration(tmp_path, monkeypatch):
    """The dedicated integration leaf gets a READ-ONLY view of the parent's declared
    files (the integrated code) while its write boundary stays its own test path, so it
    tests the real code instead of inventing a test from the goal alone (gap C)."""
    stage(tmp_path)
    fake = WritingTree()
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"), acs=(),
                    kind="internal")
    out = run_tree_sync(_plan_two_writers(), root, make_tree(), tmp_path,
                        Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=True))
    assert out.claimed

    integration = [s for s in fake.specs if s.write_boundary == ()]
    assert len(integration) == 1
    view = integration[0]
    assert set(view.files) == {"pkg/a.py", "pkg/b.py"}
    assert view.files["pkg/a.py"] == "# rewritten\n"      # the INTEGRATED code, not the goal
    assert view.files["pkg/b.py"] == "# rewritten\n"
    assert _source_write_problem("pkg/a.py", view, None) != ""   # read-only
    sources = [s for s in fake.specs if s.write_boundary != ()]
    assert {b for s in sources for b in s.write_boundary} == {"pkg/a.py", "pkg/b.py"}


def test_integration_spec_is_read_only_over_the_parent_files(tmp_path):
    """``_integration_spec`` keeps the write boundary empty (its own test only) and puts
    the parent's declared files in the READ-ONLY view (gap C)."""
    stage(tmp_path)
    spec = NodeSpec(goal="root goal", files=("pkg/a.py", "pkg/b.py"),
                    acs=("integration holds",), kind="internal")
    node = tree_run._integration_spec(spec)
    assert node.files == ()
    assert node.view_files == ("pkg/a.py", "pkg/b.py")

    leaf = tree_run.leaf_spec_from(node, tmp_path, root_grader_paths=(_GRADER,))
    assert set(leaf.files) == {"pkg/a.py", "pkg/b.py"}
    assert leaf.write_boundary == ()
    assert _source_write_problem("pkg/a.py", leaf, None) != ""


def test_an_incomplete_snapshot_cannot_certify_a_leaf(tmp_path, monkeypatch):
    """Round-4 finding: a file skipped by the audit's size/count cap could hide a
    violation. An audit that cannot see the whole tree is never clean."""
    import harness.tree_run as tree_run

    workdir = tmp_path
    (workdir / "pkg").mkdir()
    (workdir / "pkg" / "a.py").write_text("x = 1\n")
    before = tree_run.snapshot_workdir(workdir)

    # simulate a capped/partial snapshot on the post side (the only later call)
    real = tree_run.snapshot_workdir

    def capped(path):
        state = real(path)
        return replace(state, skipped=("huge.py: over the snapshot size cap",))

    monkeypatch.setattr(tree_run, "snapshot_workdir", capped)
    audit = tree_run.audit_leaf_boundary(workdir, before, ("pkg/a.py",))
    assert audit.violations == []
    assert audit.skipped
    assert audit.clean is False


# ===========================================================================
# ticket 19 D/F: split by requirement, declare expected test cases
# ===========================================================================


def test_planner_guidance_splits_by_requirement_and_declares_test_cases():
    """Ticket 19 F/D: the PlanNode prompt tells the planner to split by requirement (not
    by file, since overlapping writers are allowed) and to declare expected test cases."""
    from harness.node import _plan_node_question

    question = _plan_node_question("", 0)
    assert "REQUIREMENT" in question
    assert "test_cases" in question
    assert "outside this node's write boundary" in question


def test_plan_node_carries_declared_test_cases():
    """Ticket 19 D: the fused plan envelope carries per-criterion declared test cases and
    they survive the translation into a :class:`Decomposition`."""
    payload = {
        "status": "ok", "comment": "planned", "goal": "root", "behavior": "b",
        "implementation_notes": "n", "files": ["pkg/a.py"], "acs": [ac("criterion")],
        "interfaces": [],
        "test_cases": [{"ac_id": "AC-1", "file": "tests/test_a.py",
                        "names": ["test_ac1_ok", "test_ac1_edge"]}],
        "children": [],
    }
    env = PlanNode.model_validate(payload)
    decomp = decomposition_from_envelope(env)
    assert decomp.spec.test_cases == (
        DeclaredTestCase("AC-1", "tests/test_a.py", ("test_ac1_ok", "test_ac1_edge")),)


def test_a_child_carries_declared_test_cases():
    base = plan_env([{**child("one", ["pkg/a.py"]),
                      "test_cases": [{"ac_id": "AC-1", "file": "tests/test_a.py",
                                      "names": ["test_ac1"]}]}],
                    files=("pkg/a.py",))
    decomp = decomposition_from_envelope(PlanNode.model_validate(
        {"status": "ok", "comment": "c", **base}))
    assert decomp.children[0].test_cases == (
        DeclaredTestCase("AC-1", "tests/test_a.py", ("test_ac1",)),)


def test_leaf_spec_from_carries_declared_test_cases(tmp_path):
    """Ticket 19 D wiring: the declared test cases reach the leaf's ``LeafSpec``."""
    from harness.tree_run import leaf_spec_from

    spec = NodeSpec(goal="g", files=("pkg/a.py",), acs=("c",), kind="leaf",
                    test_cases=(DeclaredTestCase("AC-1", "tests/test_a.py", ("test_ac1",)),))
    leaf_spec = leaf_spec_from(spec, tmp_path, root_grader_paths=("tests/test_grader_secret.py",),
                               candidate_files=("pkg/a.py", "pkg/b.py"))
    assert leaf_spec.test_cases == spec.test_cases
    assert leaf_spec.write_boundary == ("pkg/a.py",)
    assert leaf_spec.candidate_files == ("pkg/a.py", "pkg/b.py")


# ===========================================================================
# ticket 19 F: overlapping siblings are allowed, serialized, and boundary-audited
# ===========================================================================


class OverlapLeaf:
    """Scripted ``run_leaf`` for overlapping siblings: records concurrency, writes the
    shared declared boundary, and (optionally) escapes it for one child keyed on its goal."""

    def __init__(self, *, escape_for: str = "", escape_rel: str = "pkg/b.py"):
        self._escape_for = escape_for
        self._escape_rel = escape_rel
        self.active = 0
        self.max_concurrent = 0
        self.writes: list[str] = []

    async def __call__(self, model, spec, workdir, budget, *, judge=None, iv=None, review=None,
                       run_tests=None, now=None, on_event=None):
        self.active += 1
        self.max_concurrent = max(self.max_concurrent, self.active)
        try:
            budget.take(1)
            boundary = list(spec.write_boundary or ())
            if boundary:
                rel = boundary[0]
                target = workdir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# written\n")
                self.writes.append(rel)
                if self._escape_for and self._escape_for in spec.goal:
                    (workdir / self._escape_rel).write_text("hijacked\n")
                attempt = Attempt(node_id="leaf", layer="implementation",
                                  strategy="L1-resample", outcome="pass",
                                  touched_files=[rel], claimed_delta=f"wrote {rel}")
                return leaf_outcome(claimed=True, attempts=[attempt])
            # the dedicated integration leaf: expose a test artifact
            path = workdir / "tests/test_integration.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_integration():\n    assert True\n")
            return leaf_outcome(self_test="tests/test_integration.py")
        finally:
            self.active -= 1


def _overlap_root(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(tree_run, "run_leaf", fake)
    root = NodeSpec(goal="root goal", files=("pkg/a.py",), acs=(), kind="internal")
    model = FakeModelRunner({"plan_node": [
        plan_env([child("add the timeout argument", ["pkg/a.py"]),
                  child("thread the timeout to callers", ["pkg/a.py"])],
                 files=("pkg/a.py",))]})
    return run_tree_sync(model, root, make_tree(), tmp_path,
                         Budget(calls=40, deadline_ts=_FAR), run_tests=Gates(green=True))


def test_overlapping_siblings_are_allowed_and_serialized(tmp_path, monkeypatch):
    """Ticket 19 F: two children may declare the SAME file (two requirements, one file);
    the tree accepts the plan, runs both, and never runs them concurrently."""
    stage(tmp_path)
    fake = OverlapLeaf()
    out = _overlap_root(tmp_path, monkeypatch, fake)

    assert out.claimed and out.root.stop_reason == "closed"
    assert fake.max_concurrent == 1                     # serialized, never concurrent
    assert fake.writes.count("pkg/a.py") == 2           # both overlapping writers ran
    # two writing descendants ⇒ the node still owes a report-gated integration verdict
    assert out.root.close_rule == "integration"
    assert set(out.root.integration_verdicts.values()) == {"pass"}


def test_boundary_audit_still_holds_for_overlapping_siblings(tmp_path, monkeypatch):
    """Ticket 19 F: relaxing sibling disjointness does NOT relax the per-node boundary
    audit. With two siblings on ``pkg/a.py``, a write to an UNDECLARED path is still caught,
    restored from the pre-leaf snapshot, and the escaping node never closes."""
    stage(tmp_path)
    fake = OverlapLeaf(escape_for="thread the timeout to callers")
    out = _overlap_root(tmp_path, monkeypatch, fake)

    assert not out.claimed
    assert (tmp_path / "pkg/b.py").read_text() == "y = 2\n"          # restored
    escaping = [c for c in out.root.children
                if c.boundary_audit is not None and c.stop_reason == "boundary-escape"]
    assert escaping and escaping[0].boundary_audit.violations == ["pkg/b.py"]
    clean = [c for c in out.root.children
             if c.boundary_audit is not None and c.boundary_audit.clean]
    # the sibling that respected its declared boundary (the shared file) kept its claim
    assert clean and (tmp_path / "pkg/a.py").read_text() == "# written\n"


def test_tree_run_record_carries_the_new_leaf_fields():
    """Ticket 19 item 3: the tree's persisted record carries each leaf's claim basis,
    verification basis, review verdicts, coverage results, attribution labels and
    needs-user flag."""
    from bench import v2_tree
    from bench.external_score import ExternalScore
    from harness.attempts import JudgeVerdict
    from harness.leaf import LeafOutcome, RequirementCoverage, ReviewVerdict
    from harness.tree_run import NodeOutcome, TreeOutcome

    leaf = LeafOutcome(
        claimed=True, signal="green", attempts=[], calls=1, wall_s=0.0,
        self_test=None, questions=[], exhausted=False, exhaustion_reason="",
        layers_used=[], stop_reason="green", claimed_basis="review",
        verification_basis="review",
        review_verdicts=[ReviewVerdict(approved=True, evidence="pkg/a.py:1 implements AC-1")],
        coverage=[RequirementCoverage(1, "c", files=("pkg/a.py",), symbols=("result",))],
        judge_verdicts=[JudgeVerdict(implementation_wrong=True, reason="r", evidence="e")])
    node = NodeOutcome(node_id="n1", claimed=True, stop_reason="closed", leaf=leaf)
    tree_outcome = TreeOutcome(root=node, claimed=True, calls=1, wall_s=0.0,
                               budget=Budget(calls=5, deadline_ts=_FAR),
                               checkpoints={}, split_history={})
    score = ExternalScore(passed=True, exit=0, notes=[], work_root="", applied=[], skipped=[])

    record = v2_tree.build_record("T-x", "goal", tree_outcome, withheld=[], produced={},
                                  score=score, quad="true-success", run_wall_s=0.0,
                                  judge_enabled=True, iv_enabled=True, review_enabled=True,
                                  acs=[])

    assert record["review"] is True
    node_rec = record["nodes"]
    assert node_rec["claimed_basis"] == "review"
    assert node_rec["verification_basis"] == "review"
    assert node_rec["review_verdicts"][0]["approved"] is True
    assert node_rec["coverage"][0]["files"] == ("pkg/a.py",)
    assert node_rec["judge_verdicts"][0]["implementation_wrong"] is True
    assert node_rec["needs_user"] is False


# ===========================================================================
# ticket 20: the verification covenant (structural hard checks + plan wiring)
# ===========================================================================


def _findings(spec, children=(), *, parent=("pkg/a.py",), depth=0, cap=4, max_children=15):
    d = Decomposition(spec=spec, children=tuple(children), signature="sig")
    return validate_decomposition(d, parent_files=set(parent), candidate_files=set(parent),
                                  depth=depth, depth_cap=cap, max_children=max_children).items


def test_leaf_node_without_files_is_invalid_at_construction():
    """Item 6: a LEAF that declares no file list (writes no code) is invalid at plan
    construction, never later."""
    findings = _findings(NodeSpec(goal="root", files=(), acs=("c",), kind="leaf"))
    assert any(f.kind == "leaf-empty-files" for f in findings)


def test_non_leaf_node_may_declare_or_omit_a_file_list():
    """Item 6: a non-leaf node MAY have code (a file list) and is not invalidated when it
    omits one."""
    with_code = _findings(NodeSpec(goal="root", files=("pkg/a.py",), acs=(), kind="internal"),
                          [NodeSpec(goal="one", files=("pkg/a.py",), acs=("c",))])
    without = _findings(NodeSpec(goal="root", files=(), acs=(), kind="internal"),
                        [NodeSpec(goal="one", files=("pkg/a.py",), acs=("c",))])
    assert not any(f.kind == "leaf-empty-files" for f in (*with_code, *without))
    assert not any(f.kind == "internal-without-children" for f in (*with_code, *without))


def test_leaf_child_without_files_is_invalid_at_construction():
    findings = _findings(
        NodeSpec(goal="root", files=("pkg/a.py",), acs=(), kind="internal"),
        [NodeSpec(goal="one", files=(), acs=("c",), kind="leaf")])
    assert any(f.kind == "leaf-child-empty-files" for f in findings)


def test_out_of_domain_verification_declaration_invalidates_the_node():
    """Item 4/6: the declared tier and review rounds are validated at construction."""
    findings = _findings(NodeSpec(goal="root", files=("pkg/a.py",), acs=("c",), kind="leaf",
                                  verification_required="sometimes"))
    assert any(f.kind == "bad-verification-required" for f in findings)
    rounds = _findings(NodeSpec(goal="root", files=("pkg/a.py",), acs=("c",), kind="leaf",
                                review_rounds=9))
    assert any(f.kind == "bad-review-rounds" for f in rounds)


def test_covenant_valid_leaf_declaration_has_no_findings():
    assert _findings(NodeSpec(goal="root", files=("pkg/a.py",), acs=("c",), kind="leaf",
                              verification_required="test", review_rounds=3,
                              best_effort=True)) == []


def test_plan_node_carries_the_verification_covenant():
    """Item 4: the fused plan envelope carries the per-node covenant and it survives the
    translation into a :class:`Decomposition` (both the node and its children)."""
    base = plan_env([{**child("one", ["pkg/a.py"]),
                      "verification_required": "test", "review_rounds": 2,
                      "best_effort": True}],
                    files=("pkg/a.py",))
    payload = {"status": "ok", "comment": "c", **base,
               "verification_required": "review", "review_rounds": 3, "best_effort": True}
    decomp = decomposition_from_envelope(PlanNode.model_validate(payload))
    assert (decomp.spec.verification_required, decomp.spec.review_rounds,
            decomp.spec.best_effort) == ("review", 3, True)
    assert (decomp.children[0].verification_required, decomp.children[0].review_rounds,
            decomp.children[0].best_effort) == ("test", 2, True)


def test_plan_node_envelope_enforces_the_covenant_domain():
    base = plan_env([child("one", ["pkg/a.py"])], files=("pkg/a.py",))
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "ok", "comment": "c", **base,
                                 "verification_required": "maybe"})
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "ok", "comment": "c", **base, "review_rounds": 0})
    with pytest.raises(ValidationError):
        PlanNode.model_validate({"status": "ok", "comment": "c", **base, "review_rounds": 4})


def test_leaf_spec_from_carries_the_verification_covenant(tmp_path):
    """Item 4 wiring: the node's declaration reaches the leaf's ``LeafSpec``."""
    from harness.tree_run import leaf_spec_from

    spec = NodeSpec(goal="g", files=("pkg/a.py",), acs=("c",), kind="leaf",
                    verification_required="test", review_rounds=2, best_effort=True)
    leaf_spec = leaf_spec_from(spec, tmp_path, root_grader_paths=(_GRADER,))
    assert leaf_spec.verification_required == "test"
    assert leaf_spec.review_rounds == 2
    assert leaf_spec.best_effort is True


def test_planner_guidance_declares_the_verification_covenant():
    """Item 4: the PlanNode prompt asks the planner for the per-node verification tier,
    the review rounds, and the best-effort opt-in."""
    from harness.node import _plan_node_question

    question = _plan_node_question("", 0)
    assert "verification_required" in question
    assert "review_rounds" in question
    assert "best_effort" in question


def test_tree_run_record_counts_best_effort_declarations_and_downgrades():
    """Item 4: the run-level counters make an 'everywhere best_effort' plan auditable."""
    from bench.v2_tree import _verification_tally
    from harness.leaf import VerificationRecord
    from harness.tree_run import NodeOutcome

    record = VerificationRecord(wrote_code=True, tier="review", required="test",
                                best_effort=True, downgraded=True,
                                downgrade_reason="best_effort: met 'review', required 'test'")
    leaf = leaf_outcome(verification=record, verified=True,
                        claim_status="verified-success")
    root = NodeOutcome(node_id="root", claimed=True, stop_reason="closed", children=[
        NodeOutcome(node_id="n", claimed=True, stop_reason="closed", leaf=leaf)])
    assert _verification_tally(root) == (1, 1)
