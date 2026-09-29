"""v2 skeleton pins: budget arithmetic, novelty/exhaustion, questions, blind split."""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bench import external_score as ext_mod
from bench.external_score import external_score
from harness import checks as checks_mod
from harness import leaf as leaf_mod
from harness.attempts import (
    Attempt,
    exhausted,
    failure_signature,
    layers_tried,
    prefilter,
)
from harness.budget import Budget, BudgetError
from harness.questions import QuestionQueue, QuestionStateError
from harness.staging import (
    PYTEST_ISOLATION_ENV,
    excluded_paths,
    is_test_infrastructure,
    is_test_path,
    owned_paths,
    pytest_isolation_env,
    shadowing_path,
    source_only,
    stage_blind,
)

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


def test_grader_restores_a_tampering_conftest_and_the_grade_is_unchanged(tmp_path: Path):
    """Finding 1 (grader contamination): a run that writes ``conftest.py`` with a
    ``pytest_sessionfinish`` hook forcing exit 0 must not be able to turn the grader into
    a liar. The grader restores the grader-owned path from the pristine copy, records
    the restore, and the verdict is unchanged."""
    task = T31
    source = {rel: (task / "repo" / rel).read_text()
              for rel in ["api/transport.py", "api/client.py", "api/service.py",
                          "exporter/bulk.py"] if (task / "repo" / rel).exists()}
    clean = external_score(task, source, tmp_path / "clean")
    malicious = ("import pytest\n"
                 "\n\n"
                 "def pytest_sessionfinish(session, exitstatus):\n"
                 "    session.exitstatus = 0\n")
    tampered = external_score(task, dict(source, **{"conftest.py": malicious}),
                              tmp_path / "tampered")

    assert clean.passed is False
    assert tampered.passed is False                     # the tamper bought no green
    assert tampered.passed == clean.passed
    assert "conftest.py" not in tampered.applied        # never accepted the run's version
    assert any("conftest.py" in line for line in tampered.restored)
    assert any("conftest.py" in line for line in tampered.skipped)
    # the tamper never landed in the graded tree
    copy_repo = Path(tampered.work_root) / task.name / "repo"
    assert not (copy_repo / "conftest.py").exists()


# ------------------------- round 6: the grader's OWN machine-readable report gate (F1)
# The process exit status is forgeable by the run's own code (both pytest runs execute
# the run's modules). ``checks.py`` is the corpus's instrument and is NOT modified; the
# grader runs its own report-based verification instead and actual is True only when the
# corpus check exited 0 AND that report is green.

#: The reference fix for T-31 (bench/corpus/T-31-parameter-threading/solution.md).
_T31_FIXED = {
    "api/transport.py": ("def send(url: str, payload: str, timeout: float = 1.0) -> str:\n"
                         "    return f\"200:{url}:{payload}\"\n"),
    "api/client.py": ("from api.transport import send\n\n\n"
                      "def fetch(url: str, payload: str = \"\", timeout: float = 1.0) -> str:\n"
                      "    return send(url, payload, timeout=timeout)\n"),
    "api/service.py": ("from api.client import fetch\n\n\n"
                       "def sync_record(record_id: str, timeout: float = 1.0) -> str:\n"
                       "    return fetch(f\"/records/{record_id}\", payload=\"sync\", timeout=timeout)\n"),
    "exporter/bulk.py": ("from api.client import fetch\n\n\n"
                         "def export_all(ids: list, timeout: float = 1.0) -> list:\n"
                         "    return [fetch(f\"/export/{i}\", timeout=timeout) for i in ids]\n"),
}


def _t31_source() -> dict[str, str]:
    return {rel: (T31 / "repo" / rel).read_text()
            for rel in ["api/transport.py", "api/client.py", "api/service.py",
                        "exporter/bulk.py"]}


def test_external_score_report_gate_catches_a_forged_grader_exit(tmp_path: Path):
    """F1: run code (``atexit`` + ``os._exit(0)``) forces ``checks.py`` and its pytest to
    exit 0 with the real bug untouched. That exit status is no longer enough — the
    grader's own report gate is red and the grade is recorded as SUSPECTED CONTAMINATED."""
    source = _t31_source()
    forgery = ("import atexit, os\natexit.register(lambda: os._exit(0))\n\n"
               + source["api/transport.py"])
    outcome = external_score(T31, dict(source, **{"api/transport.py": forgery}),
                             tmp_path / "forged")

    assert outcome.exit == 0                        # the corpus check was fooled
    assert outcome.passed is False                  # ... the report gate was not
    assert outcome.suspected_contaminated_grade is True
    assert outcome.report_gate is not None
    assert outcome.report_gate.green is False
    assert outcome.report_gate.observed is True     # a real report that says: failed
    assert outcome.report_gate.anomaly == "tests-failed"
    assert outcome.report_gate.expected_files == ("tests/test_chain.py",)
    assert any("gate_report_anomaly" in note for note in outcome.notes)
    assert any("suspected contaminated" in note for note in outcome.notes)


def test_external_score_report_gate_catches_a_grader_that_never_ran(tmp_path: Path):
    """The other forgery shape: ``os._exit(0)`` at import kills pytest before the report
    is written, so there is no machine-readable evidence at all — never a green."""
    source = _t31_source()
    killed = "import os\nos._exit(0)\n\n" + source["api/transport.py"]
    outcome = external_score(T31, dict(source, **{"api/transport.py": killed}),
                             tmp_path / "killed")

    assert outcome.exit == 0
    assert outcome.passed is False
    assert outcome.suspected_contaminated_grade is True
    assert outcome.report_gate.anomaly == "report-missing"
    assert outcome.report_gate.observed is False
    assert outcome.report_gate.process_exit == 0    # the process lied; the gate did not


def test_external_score_report_gate_greens_on_a_correct_fix(tmp_path: Path):
    """No false reds: the correct fix satisfies the corpus check AND the report gate,
    which sees every corpus test file plus the per-run canary."""
    outcome = external_score(T31, _T31_FIXED, tmp_path / "ok")

    assert outcome.passed is True
    assert outcome.suspected_contaminated_grade is False
    assert outcome.report_gate.green is True
    assert outcome.report_gate.expected_files == ("tests/test_chain.py",)
    assert outcome.report_gate.canary
    assert outcome.report_gate.n_tests >= 1


# --------------------------------------- round 5: one owned-path definition

#: Fixed path table (ticket 17 round 5). Every consumer must classify these identically.
_OWNED_TABLE = ["tests/test_x.py", "pkg/tests/helper.py", "test_a.py", "conftest.py",
                "tests/conftest.py", "pytest.ini", "tox.ini", "setup.cfg",
                "pyproject.toml", "sitecustomize.py", "evil.pth"]
_SOURCE_TABLE = ["api/transport.py", "pkg/calc.py", "src/module.py", "contest.py",
                 "src/latest.py", "a_test.py"]


def test_owned_path_definition_is_the_same_in_every_consumer():
    """One definition of what a run may not touch (ticket 17 round 5): staging's
    ``owned_paths`` drives the blind projection, the leaf's source-write guard, and the
    grader's restore set, so a newly guarded infrastructure path cannot leak past any of
    them."""
    spec = leaf_mod.LeafSpec(goal="g", files={"pkg/calc.py": "x = 1\n"}, acs=[],
                             interfaces=[])
    for rel in _OWNED_TABLE:
        assert owned_paths(rel) is True
        assert excluded_paths({rel: "x"}) == [rel]
        assert source_only({rel: "x"}) == {}
        assert leaf_mod._source_write_problem(rel, spec, None) != ""
        assert ext_mod._grader_owned(rel, set()) is True
    for rel in _SOURCE_TABLE:
        assert owned_paths(rel) is False
        assert source_only({rel: "x"}) == {rel: "x"}
        assert leaf_mod._source_write_problem(rel, spec, None) == ""
        assert ext_mod._grader_owned(rel, set()) is False
    # the corpus UNTOUCHED list is still honoured by the grader (a source path there is
    # grader-owned even though owned_paths does not know it)
    assert ext_mod._grader_owned("README.md", {"README.md"}) is True


def test_stage_blind_withholds_test_infrastructure(tmp_path: Path):
    files = {"api/transport.py": "x = 1\n",
             "tests/test_a.py": "def test_a():\n    pass\n",
             "conftest.py": "import pytest\n",
             "pyproject.toml": "[tool.pytest.ini_options]\n",
             "sitecustomize.py": "print('startup')\n",
             "evil.pth": "import os\n"}
    withheld = stage_blind(tmp_path, files)

    assert set(withheld) == {"tests/test_a.py", "conftest.py", "pyproject.toml",
                             "sitecustomize.py", "evil.pth"}
    assert (tmp_path / "api" / "transport.py").exists()
    for rel in withheld:
        assert not (tmp_path / rel).exists()
    assert is_test_infrastructure("conftest.py") is True
    assert is_test_infrastructure("api/x.py") is False


@pytest.mark.parametrize("rel", ["json.py", "pytest.py", "_pytest/__init__.py",
                                 "sitecustomize.py"])
def test_first_component_module_shadow_names_are_recognized(rel):
    assert shadowing_path(rel) is True


@pytest.mark.parametrize("rel", ["api/transport.py", "api/json.py", "pkg/calc.py",
                                 "contest.py", "src/module.py"])
def test_nested_or_harmless_paths_do_not_shadow_imports(rel):
    # only the FIRST component under the repo root can shadow the interpreter's import
    assert shadowing_path(rel) is False


# ------------------------------------------- round 5: attack 3A (shadow import)


@pytest.mark.parametrize("rel", ["json.py", "pytest.py", "_pytest/__init__.py"])
def test_run_authored_shadow_module_cannot_forge_a_green(tmp_path: Path, rel: str):
    """Attack 3A reproduced: with the unfixed source, a run-authored top-level module
    containing ``sys.exit(0)`` made the grader exit 0 — a forged TRUE SUCCESS with the
    real bug untouched. The produced shadow path is never applied and the attempt is
    recorded; the grade stays the honest FAIL."""
    task = T31
    source = {r: (task / "repo" / r).read_text()
              for r in ["api/transport.py", "api/client.py", "api/service.py",
                        "exporter/bulk.py"]}
    clean = external_score(task, source, tmp_path / "clean")
    attack = external_score(task, dict(source, **{rel: "import sys\nsys.exit(0)\n"}),
                            tmp_path / "attack")

    assert clean.passed is False                       # the real bug is still red
    assert attack.passed is False                      # the shadow bought no green
    assert attack.passed == clean.passed
    assert rel in attack.shadowed
    assert rel not in attack.applied
    assert any(rel in line for line in attack.skipped)
    copy_repo = Path(attack.work_root) / task.name / "repo"
    assert not (copy_repo / rel).exists()              # never landed in the graded tree


def test_grader_pytest_isolation_env_defeats_a_shadowing_json(tmp_path: Path):
    """The isolation env applied to the grader's pytest keeps the run's repo root off
    ``sys.path``, so ``json.py`` can no longer shadow the interpreter's own import."""
    (tmp_path / "json.py").write_text(
        "import pathlib, sys\npathlib.Path('shadowed.txt').write_text('x')\nsys.exit(0)\n")
    (tmp_path / "test_red.py").write_text("def test_red():\n    assert False\n")

    env = pytest_isolation_env({**os.environ, "PYTHONPATH": ""})
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    assert PYTEST_ISOLATION_ENV["PYTHONSAFEPATH"] == "1"    # the switch we rely on
    assert not (tmp_path / "shadowed.txt").exists()         # real json was imported
    assert proc.returncode != 0                            # the red test really ran
    assert "test_red" in (proc.stdout + proc.stderr)


def test_without_isolation_the_same_shadowing_json_forges_a_green(tmp_path: Path):
    """Negative control: the exact attack, demonstrated. Without ``PYTHONSAFEPATH`` the
    repo root is ``sys.path[0]``, ``json.py`` runs at import, and pytest never starts —
    exit 0 is a forged green. This pins WHY the isolation env exists."""
    (tmp_path / "json.py").write_text("import sys\nsys.exit(0)\n")
    (tmp_path / "test_red.py").write_text("def test_red():\n    assert False\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONSAFEPATH"}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0                            # forged: the red test never ran
    assert "test_red" not in (proc.stdout + proc.stderr)
