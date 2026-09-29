"""v2 skeleton pins: budget arithmetic, novelty/exhaustion, questions, blind split."""
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bench.external_score import external_score
from harness import checks as checks_mod
from harness.attempts import Attempt, exhausted, failure_signature, layers_tried, prefilter
from harness.budget import Budget, BudgetError
from harness.questions import QuestionQueue, QuestionStateError
from harness.staging import excluded_paths, is_test_path, source_only, stage_blind

ROOT = Path(__file__).resolve().parents[2]
T31 = ROOT / "bench" / "corpus" / "T-31-parameter-threading"


# ----------------------------------------------------------------- budget

def test_split_keeps_reserve_and_each_child_can_work():
    parent = Budget(calls=40, deadline_ts=time.time() + 3600)
    children = parent.split(4)
    assert [c.calls for c in children] == [7, 7, 7, 7]      # 40 * 0.75 // 4
    assert parent.calls == 12                               # remainder stays as reserve


def test_split_refuses_when_children_would_get_nothing():
    small = Budget(calls=2, deadline_ts=time.time() + 60)
    with pytest.raises(BudgetError, match="too small to decompose"):
        small.split(3)


def test_spend_release_and_grant_are_audited():
    parent = Budget(calls=10, deadline_ts=time.time() + 60)
    child = parent.split(1)[0]          # 10 * 0.75 = 7 to the child, 3 held back
    assert child.calls == 7 and parent.calls == 3
    child.take(2)
    assert child.calls == 5 and child.spent_calls == 2
    assert parent.release(child) == 5 and parent.calls == 8
    assert parent.grant(5, "weekend extension").approved
    assert parent.deny("no new evidence").approved is False
    assert [g.approved for g in parent.grants] == [True, False]
    with pytest.raises(BudgetError):
        child.take(99)


def test_deadline_is_the_primary_stop_and_is_durable():
    now = 1000.0
    live = Budget(calls=5, deadline_ts=now + 10)
    assert not live.exhausted(now) and live.expired(now) is False
    assert live.exhausted(now + 11) and live.calls == 5      # deadline, not calls
    dead = Budget(calls=0, deadline_ts=now + 10)
    assert dead.exhausted(now)
    again = Budget.from_dict(live.to_dict())
    assert again.to_dict() == live.to_dict()


# --------------------------------------------------------------- attempts

def _attempt(**kw) -> Attempt:
    base = dict(node_id="N-1", layer="implementation", strategy="L1-resample",
                claimed_delta="rewrite send()", outcome="fail", verdict=None)
    base.update(kw)
    return Attempt(**base)


def test_failure_signature_tracks_tests_and_error_kinds():
    sig = failure_signature(
        ["FAILED tests/test_chain.py::test_client_threads_timeout",
         "FAILED tests/test_chain.py::test_service_threads_timeout"],
        ["E TypeError: send() got an unexpected keyword argument 'timeout'",
         "E TypeError: fetch() got an unexpected keyword argument 'timeout'"])
    assert "test_client_threads_timeout" in sig and "test_service_threads_timeout" in sig
    assert "TypeError" in sig
    other = failure_signature(["FAILED tests/test_chain.py::test_exporter_threads_timeout"],
                              ["E TypeError: export_all() got an unexpected keyword argument 'timeout'"])
    assert other != sig


def test_silence_is_the_cheapest_exhaustion_signal():
    silent = _attempt(claimed_delta="   ")
    assert prefilter([], silent) == "same"


def test_repeat_of_same_idea_is_same_but_new_evidence_is_novel():
    sig = failure_signature(["FAILED tests/test_chain.py::test_client_threads_timeout"],
                            ["E TypeError: send() got an unexpected keyword argument 'timeout'"])
    first = _attempt(failure_signature=sig, touched_files=["api/transport.py"], verdict="novel")
    # Same failure and same file, different wording of the claim: the judge decides —
    # a small model claiming novelty is not evidence of novelty.
    repeat = _attempt(failure_signature=sig, touched_files=["api/transport.py"],
                      claimed_delta="rewrite send() again")
    assert prefilter([first], repeat) == "undecided"
    # Byte-identical claim: no judge call needed, this is the same idea again.
    verbatim = _attempt(failure_signature=sig, touched_files=["api/transport.py"],
                        claimed_delta="rewrite send()")
    assert prefilter([first, repeat], verbatim) == "same"
    new_file = _attempt(failure_signature=sig, touched_files=["api/client.py"],
                        claimed_delta="thread through the client too")
    assert prefilter([first], new_file) == "novel"
    new_sig = _attempt(failure_signature=sig + "x", touched_files=["api/transport.py"],
                       claimed_delta="different failure now")
    assert prefilter([first], new_sig) == "novel"


def test_ambiguous_claim_goes_to_the_judge_not_to_trust():
    sig = failure_signature(["FAILED t::x"], ["E AssertionError"])
    past = _attempt(failure_signature=sig, touched_files=["a.py"],
                    claimed_delta="try condition X", verdict="novel")
    candidate = _attempt(failure_signature=sig, touched_files=["a.py"],
                         claimed_delta="try a different condition Y")
    assert prefilter([past], candidate) == "undecided"
    assert candidate.verdict is None            # the judge fills this in


def test_exhaustion_needs_two_same_verdicts_or_three_layers():
    assert not exhausted([])
    one = _attempt(verdict="same")
    assert not exhausted([one])
    assert not exhausted([one, _attempt(verdict="same")])
    # Two layers that are both "same" is not enough to declare a node exhausted:
    # the structural levers (re-split, parent spec) have not been tried yet.
    shallow = [_attempt(layer="implementation", verdict="same"),
               _attempt(layer="spec", verdict="same")]
    assert not exhausted(shallow)
    # A structural attempt plus the same-verdict tail is a real end of the road.
    with_structure = shallow + [_attempt(strategy="L6-resplit", layer="decomposition",
                                        verdict="same")]
    assert exhausted(with_structure)
    # Or a broadly exercised ladder that still yields nothing new.
    layered = [_attempt(layer="implementation", verdict="novel"),
               _attempt(layer="spec", verdict="novel"),
               _attempt(layer="tests", verdict="novel"),
               _attempt(layer="implementation", verdict="same"),
               _attempt(layer="spec", verdict="same")]
    assert exhausted(layered)
    assert layers_tried(layered) == {"implementation", "spec", "tests"}


# -------------------------------------------------------------- questions

def test_question_lifecycle_is_terminal_and_audited():
    queue = QuestionQueue()
    q, created = queue.open("T-31:timeout-default", "Default timeout 1.0 or 2.0?",
                            blocks=["N-3"], default_choice="proceed with 1.0")
    assert created and q.state == "open"
    same, created_again = queue.open("T-31:timeout-default", "duplicate wording")
    assert same is q and created_again is False          # dedupe by fork, not wording
    queue.answer(q.id, "keep 1.0")
    assert q.state == "answered" and "1.0" in q.resolution
    with pytest.raises(QuestionStateError):
        queue.withdraw(q.id, "too late")


def test_withdrawing_moves_the_fork_and_rejects_empty_reasons():
    queue = QuestionQueue()
    q, _ = queue.open("k", "which module owns the retry?")
    with pytest.raises(QuestionStateError):
        queue.withdraw(q.id, "   ")
    queue.withdraw(q.id, "the run solved it another way")
    assert queue.active() == [] and q.state == "withdrawn"


def test_resolved_nodes_withdraw_their_questions_with_a_reason():
    queue = QuestionQueue()
    blocking, _ = queue.open("a", "scope: A or B?", blocks=["N-3", "N-4"])
    other, _ = queue.open("b", "naming preference?", blocks=["N-9"])
    closed = queue.withdraw_resolved({"N-3", "N-4"})
    assert closed == [blocking] and blocking.state == "withdrawn"
    assert "N-3" in blocking.resolution and other.state == "open"
    assert queue.active() == [other]


def test_only_open_questions_can_be_superseded():
    queue = QuestionQueue()
    old, _ = queue.open("a", "old fork")
    new, _ = queue.open("b", "new fork")
    queue.supersede(old.id, new.id)
    assert old.state == "superseded" and old.superseded_by == new.id
    with pytest.raises(QuestionStateError):
        queue.supersede(old.id, new.id)


# ------------------------------------------------------------- blind split

def test_test_path_rule_matches_the_check_pipeline():
    samples = ["tests/test_x.py", "pkg/tests/helper.py", "test_a.py", "a_test.py",
               "pkg/test_b.py", "src/module.py", "contest.py", "src/latest.py"]
    for rel in samples:
        assert is_test_path(rel) == checks_mod._is_test_path(rel), rel


def test_stage_blind_withholds_grader_files_on_disk(tmp_path: Path):
    files = {"api/transport.py": "def send(u, p): pass\n",
             "tests/test_chain.py": "def test_timeout(): assert False\n",
             "tests/__init__.py": ""}
    withheld = stage_blind(tmp_path, files)
    assert withheld == ["tests/__init__.py", "tests/test_chain.py"]
    assert (tmp_path / "api" / "transport.py").exists()
    assert not (tmp_path / "tests").exists()
    assert set(source_only(files)) == {"api/transport.py"}
    assert excluded_paths(files) == withheld


# ------------------------------------------------------------ external grade

def test_external_score_runs_grader_outside_the_harness(tmp_path: Path):
    task = T31
    source = {rel: (task / "repo" / rel).read_text()
              for rel in ["api/transport.py", "api/client.py", "api/service.py",
                          "exporter/bulk.py"] if (task / "repo" / rel).exists()}
    # Pristine sources: the corpus suite is red before the fix.
    red = external_score(task, source, tmp_path / "runA")
    assert red.passed is False and red.exit != 0

    # The grader owns the untouched contract: touching a frozen file fails the run
    # even when the tests would pass.
    violated = dict(source, **{"README.md": "tampered\n"})
    caught = external_score(task, violated, tmp_path / "runB")
    assert caught.passed is False
    assert any("NOT" in note or "untouched" in note.lower() or "MISMATCH" in note.upper()
               or "violat" in note.lower() for note in caught.notes) or caught.exit != 0


def test_grader_keeps_its_own_tests_even_if_the_run_rewrites_them(tmp_path: Path):
    """A run that overwrites the grader's test file must not grade itself."""
    task = T31
    tampered = {"api/transport.py": "def send(url, payload, timeout=1.0):\n    return f'200:{url}:{payload}'\n",
                "tests/test_chain.py": "def test_everything_is_fine():\n    assert True\n"}
    outcome = external_score(task, tampered, tmp_path / "runC")
    assert outcome.passed is False                       # the real suite still runs
    assert any("grader-owned" in note for note in outcome.skipped)
    assert any("not applied" in note for note in outcome.skipped)


def test_run_may_add_its_own_test_but_never_rewrite_an_existing_one(tmp_path: Path):
    """The self-test step's guard, which the blind protocol proved was dead."""
    from types import SimpleNamespace
    from bench import golden_bugfix as gb

    calls = []

    def fake_step(_model, _kind, **kw):
        return SimpleNamespace(status="ok", file_path=calls.pop(0),
                               content="def test_repro():\n    assert True\n")

    async def fake_check(*_a, **_kw):
        return SimpleNamespace(ok=True, findings=[])

    files = {"api/transport.py": "def send(u, p): pass\n"}
    grader = {"tests/test_chain.py"}
    for rel, expected in [("tests/test_chain.py", "grader-owned"),
                          ("api/transport.py", "already exists"),
                          ("../escape.py", "escapes"),
                          ("tests/test_repro.py", None)]:
        calls.append(rel)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(gb, "llm_step", fake_step)
            mp.setattr(gb, "check_write", fake_check)
            mp.setattr(gb, "note", lambda *_a, **_kw: None)
            spec = SimpleNamespace(interfaces=[], behavior="b")
            acs = SimpleNamespace(acs=[])
            written = gb.step_write_test(None, spec, acs, tmp_path, files,
                                         grader_paths=grader)
        if expected is None:
            assert written is not None and written.name == "test_repro.py"
        else:
            assert written is None, rel
