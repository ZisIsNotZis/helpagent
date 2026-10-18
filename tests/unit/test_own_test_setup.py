"""Own-test setup failures must not drive source edits or establish discrimination.

Use the actual pytest/JUnit gate with a scripted model, never a model server. These
checks distinguish missing imports, syntax and fixture setup from assertion/source red.
"""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from harness.budget import Budget
from harness.exec import ShapedResult
from harness.fake_model import EnvelopeSpec, FakeModelRunner
from harness.leaf import (
    DeclaredTestCase,
    JudgeVerdict,
    LeafSpec,
    _default_run_tests,
    _own_test_setup_problem,
    _setup_repair_preservation_problem,
    failure_is_test_attributed,
    run_leaf,
)
from harness.runner import reset_ledger_for_tests


TEST_PATH = "tests/test_generated.py"
SOURCE_PATH = "pkg/calc.py"
BROKEN_SOURCE = "def result():\n    return 0\n"
FIXED_SOURCE = "def result():\n    return 42\n"
VALID_TEST = "from pkg.calc import result\n\ndef test_ac1_result():\n    assert result() == 42\n"
MISSING_IMPORT_TEST = "def test_ac1_result():\n    assert result() == 42\n"
SYNTAX_TEST = "def test_ac1_result(:\n    assert True\n"
# Tree-sitter accepts this grammar; CPython rejects deleting a call expression.
# It reaches the real pytest/preflight boundary rather than the earlier parse respawn.
CPYTHON_SYNTAX_TEST = "def test_ac1_result():\n    del result()\n"
MISSING_FIXTURE_TEST = "def test_ac1_result(unknown_fixture):\n    assert unknown_fixture == 42\n"
FIXTURE_SOURCE = ("import pytest\n\n" + BROKEN_SOURCE
                  + "\n@pytest.fixture\ndef unknown_fixture():\n    return result()\n")
FIXTURE_TEST = "from pkg.calc import unknown_fixture\n\n" + MISSING_FIXTURE_TEST


def _write(path: str, content: str) -> dict:
    return {"status": "ok", "comment": "write the declared artifact",
            "file_path": path, "content": content}


def _stage(workdir: Path, source: str, test: str | None = None) -> None:
    source_path = workdir / SOURCE_PATH
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source)
    if test is not None:
        test_path = workdir / TEST_PATH
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test)


def _spec(source: str) -> LeafSpec:
    return LeafSpec(
        goal="make result() return 42", files={SOURCE_PATH: source},
        acs=["result() returns 42"], interfaces=["pkg.calc.result() -> int"],
        planned_tests=(DeclaredTestCase("AC-1", TEST_PATH, ("test_ac1_result",)),),
        verification_reason="a returned-value assertion pins the goal",
    )


def _run(workdir, source, responses, **kwargs):
    reset_ledger_for_tests()
    _stage(workdir, source)
    model = FakeModelRunner({"write_test": responses})
    events = []
    outcome = asyncio.run(run_leaf(
        model, _spec(source), workdir,
        kwargs.pop("budget", Budget(calls=8, deadline_ts=2_000_000_000)),
        on_event=lambda kind, body: events.append((kind, body)),
        verification_mode="test", **kwargs))
    test_calls = [c for c in model.calls("write_test") if c.step_type == "write_test"]
    return outcome, model, test_calls, events


@pytest.mark.parametrize(("test", "layer"), [
    (MISSING_IMPORT_TEST, "name"), (SYNTAX_TEST, "syntax"),
    (CPYTHON_SYNTAX_TEST, "syntax"), (MISSING_FIXTURE_TEST, "fixture"),
])
def test_own_test_setup_problem_uses_real_gate_output(tmp_path, test, layer):
    _stage(tmp_path, BROKEN_SOURCE, test)
    result = asyncio.run(_default_run_tests(tmp_path))
    assert result.gate.observed and not result.gate.green
    actual, detail = _own_test_setup_problem(TEST_PATH, test, result, (SOURCE_PATH,))
    assert actual == layer
    assert detail


@pytest.mark.parametrize(("source", "test", "repair", "fixed"), [
    (BROKEN_SOURCE, MISSING_IMPORT_TEST, VALID_TEST, FIXED_SOURCE),
    (FIXTURE_SOURCE, MISSING_FIXTURE_TEST, FIXTURE_TEST,
     FIXTURE_SOURCE.replace("return 0", "return 42")),
], ids=["missing-import", "fixture-import"])
def test_run_leaf_repairs_setup_before_implementation_and_reproves_red(
    tmp_path, source, test, repair, fixed,
):
    outcome, model, test_calls, events = _run(
        tmp_path, source,
        [_write(TEST_PATH, test), _write(TEST_PATH, repair),
         _write(SOURCE_PATH, fixed)])
    assert len(test_calls) == 2
    assert len(model.calls("implement_write")) == 1
    assert "not behavior evidence" in test_calls[1].artifacts["failure_output"]
    assert SOURCE_PATH in test_calls[1].artifacts["repo_files"]
    assert (tmp_path / SOURCE_PATH).read_text() == fixed
    kinds = [kind for kind, _ in events]
    assert kinds.index("self_test_setup_invalid") < kinds.index("self_test_written")
    assert "self_test_setup_rechecked" in kinds
    assert outcome.own_test_discriminating == [f"{TEST_PATH}::test_ac1_result"]
    assert outcome.test_rewrites == 0  # no valid red target existed before setup repair
    assert outcome.claimed is True


@pytest.mark.parametrize("repair", [
    MISSING_IMPORT_TEST, SYNTAX_TEST, "import math\n\n" + MISSING_IMPORT_TEST,
], ids=["unchanged", "unparseable", "still-missing-name"])
def test_run_leaf_unrepaired_setup_stops_without_source_churn(tmp_path, repair):
    outcome, model, _, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, repair)])
    assert not model.calls("implement_write")
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE
    assert not outcome.claimed
    assert outcome.stop_reason == "self-test-invalid"
    assert outcome.state == "uncertain"
    assert outcome.attempts == []
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert any(kind == "self_test_invalid" for kind, _ in events)
    assert (tmp_path / TEST_PATH).is_file()  # invalid artifact remains inspectable


@pytest.mark.parametrize("source", [
    BROKEN_SOURCE,
    "def result():\n    return unknown_source_name\n",
], ids=["assertion", "source-name"])
def test_run_leaf_assertion_and_source_name_error_remain_implementation_feedback(tmp_path, source):
    outcome, model, test_calls, events = _run(
        tmp_path, source, [_write(TEST_PATH, VALID_TEST), _write(SOURCE_PATH, FIXED_SOURCE)],
        judge=lambda request: JudgeVerdict(
            implementation_wrong=True, reason="result returns the wrong value",
            defect="result must return 42"))
    assert len(test_calls) == 1
    assert not any(kind == "self_test_setup_invalid" for kind, _ in events)
    assert len(model.calls("implement_write")) == 1
    assert outcome.claimed


@pytest.mark.parametrize("source", [
    "def result(:\n    return 42\n",
    "def different_api():\n    return 42\n",
], ids=["source-syntax", "missing-source-api"])
def test_source_import_collection_errors_are_not_automatic_test_setup_blame(tmp_path, source):
    # Ownership of a missing imported API needs goal/visible-interface evidence, not
    # an automatic rewrite of the importing test. Its controller route remains P1b.
    _stage(tmp_path, source, VALID_TEST)
    result = asyncio.run(_default_run_tests(tmp_path))
    assert result.gate.observed and not result.gate.green
    assert _own_test_setup_problem(TEST_PATH, VALID_TEST, result, (SOURCE_PATH,)) == ("", "")


def test_run_leaf_setup_repair_with_missing_report_cannot_reuse_invalid_red(tmp_path):
    calls = 0

    async def lose_repair_report(workdir):
        nonlocal calls
        calls += 1
        if calls == 1:
            return await _default_run_tests(workdir)
        return ShapedResult(command=["pytest"], exit=1, verdict="failed")

    outcome, model, _, _ = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, VALID_TEST)],
        run_tests=lose_repair_report)
    assert not outcome.claimed
    assert not model.calls("implement_write")
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert outcome.own_test_gate is None
    assert outcome.state == "uncertain"
    assert (tmp_path / TEST_PATH).is_file()
    assert (tmp_path / TEST_PATH).read_text() == VALID_TEST
    assert outcome.stop_reason == "self-test-unverified"


def test_run_leaf_repaired_test_green_on_pristine_cannot_claim(tmp_path):
    # Preserve the original predicate: the pristine implementation already meets it.
    outcome, model, _, _ = _run(
        tmp_path, FIXED_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, VALID_TEST),
         _write(TEST_PATH, VALID_TEST)])
    assert not outcome.claimed
    assert not model.calls("implement_write")
    assert outcome.own_test_discriminating == []
    assert (tmp_path / SOURCE_PATH).read_text() == FIXED_SOURCE


@pytest.mark.parametrize("failure", [
    f"{TEST_PATH}:4: AssertionError: NameError: unexpected result",
    (f"{TEST_PATH}:4: AssertionError: assert 0 == 42\n"
     "---------------- Captured stdout call ----------------\n"
     f"{TEST_PATH}:4: NameError: printed text, not the exception"),
    (f"{TEST_PATH}:4: NameError: handled by the test\n"
     "During handling of the above exception, another exception occurred:\n"
     f"{TEST_PATH}:8: AssertionError: NameError: wrong result"),
    (f"{TEST_PATH}:4: \n"
     f"{SOURCE_PATH}:2: NameError: source failure"),
], ids=["assertion-message", "captured-output", "chained-exception", "source-owner"])
def test_failure_is_test_attributed_requires_the_actual_terminal_exception(failure):
    assert not failure_is_test_attributed(failure, TEST_PATH, (SOURCE_PATH,))


@pytest.mark.parametrize("separator", [
    "During handling of the above exception, another exception occurred:",
    "The above exception was the direct cause of the following exception:",
], ids=["handling", "direct-cause"])
def test_failure_is_test_attributed_discards_chain_without_terminal_location(separator):
    failure = (f"{TEST_PATH}:4: NameError: earlier test fault\n{separator}\n"
               "E   ValueError: final exception has no retained terminal location")
    assert not failure_is_test_attributed(failure, TEST_PATH, (SOURCE_PATH,))


@pytest.mark.parametrize("exception", ["NameError", "UnboundLocalError"])
def test_failure_is_test_attributed_accepts_terminal_test_name_fault(exception):
    failure = f"{TEST_PATH}:4: {exception}: missing local name"
    assert failure_is_test_attributed(failure, TEST_PATH, (SOURCE_PATH,))


@pytest.mark.parametrize("test", [
    VALID_TEST.replace("== 42", '== 42, "NameError: unexpected result"'),
    VALID_TEST.replace("== 42", '== 42, "UnboundLocalError: unexpected result"'),
    VALID_TEST.replace("    assert", f'    print("{TEST_PATH}:4: NameError: captured")\n    assert'),
], ids=["name-in-assertion-message", "unbound-in-assertion-message", "captured-location"])
def test_run_leaf_exception_name_prose_stays_implementation_feedback(tmp_path, test):
    outcome, model, test_calls, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, test), _write(SOURCE_PATH, FIXED_SOURCE)],
        judge=lambda request: JudgeVerdict(
            implementation_wrong=True, reason="result returns 0 instead of 42",
            defect="result must return 42"))
    assert len(test_calls) == 1
    assert not any(kind == "self_test_setup_invalid" for kind, _ in events)
    assert len(model.calls("implement_write")) == 1
    assert outcome.claimed


@pytest.mark.parametrize("repair", [
    VALID_TEST.replace("== 42", ">= 42"),  # still red on return 0; not caught by green re-ask
    VALID_TEST.replace("assert result() == 42", "assert True"),
    VALID_TEST.replace("    assert", "    if False:\n        assert"),
    VALID_TEST.replace("def test_ac1_result():", "def test_other():"),
    VALID_TEST.replace("def test_ac1_result():", "@pytest.mark.skip\ndef test_ac1_result():"),
    "from pkg.calc import result\n",  # deleting the check also cannot be setup-only
], ids=["weakened-still-red", "vacuous", "unreachable", "renamed", "skipped", "deleted"])
def test_run_leaf_setup_only_repair_cannot_replace_existing_behavioral_checks(tmp_path, repair):
    outcome, model, _, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), _write(TEST_PATH, repair)])
    assert outcome.state == "uncertain"
    assert outcome.stop_reason == "self-test-invalid"
    assert not outcome.claimed
    assert not model.calls("implement_write")
    assert outcome.attempts == []
    assert outcome.own_test_discriminating == []
    assert outcome.own_test_gate is None
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert any(kind == "self_test_setup_repair_rejected" for kind, _ in events)
    assert (tmp_path / TEST_PATH).read_text() == MISSING_IMPORT_TEST
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE


def test_setup_repair_preservation_includes_expected_values_helpers_and_check_context():
    original = ("EXPECTED = 42\n\ndef read_result():\n    return result()\n\n"
                "def test_ac1_result():\n    assert read_result() == EXPECTED\n")
    repair = "from pkg.calc import result\n\n" + original
    assert _setup_repair_preservation_problem(original, repair) == ""
    assert _setup_repair_preservation_problem(original, repair.replace("EXPECTED = 42", "EXPECTED = 0"))
    assert _setup_repair_preservation_problem(original, repair.replace("return result()", "return 42"))
    assert _setup_repair_preservation_problem(SYNTAX_TEST, VALID_TEST)
    assert _setup_repair_preservation_problem(MISSING_IMPORT_TEST, SYNTAX_TEST)
    # This proves structural preservation only. Dynamic import effects/semantic oracle
    # correctness are explicitly outside this mechanical check's guarantee.


def test_run_leaf_unparseable_original_stops_when_preservation_is_unknown(tmp_path):
    outcome, model, test_calls, _ = _run(
        tmp_path, BROKEN_SOURCE, [_write(TEST_PATH, CPYTHON_SYNTAX_TEST)])
    assert len(test_calls) == 1  # do not spend a repair call we cannot safely validate
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "uncertain"
    assert outcome.stop_reason == "self-test-invalid"
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert any("preservation is unknown" in refusal for refusal in outcome.refusals)
    assert (tmp_path / TEST_PATH).read_text() == CPYTHON_SYNTAX_TEST


@pytest.mark.parametrize("fault", [
    "report-missing", "unobserved", "canary-missing", "expected-tests-missing",
    "process-exit", "transport", "process-unfinished", "transport-verdict", "blocked",
])
@pytest.mark.parametrize("during_repair", [False, True], ids=["initial", "repair-reobservation"])
def test_run_leaf_untrusted_observation_stops_uncertain_retaining_artifact(
    tmp_path, fault, during_repair,
):
    calls = 0

    async def untrusted_observation(workdir):
        nonlocal calls
        calls += 1
        result = await _default_run_tests(workdir)
        if during_repair and calls == 1:
            return result
        if fault == "report-missing":
            return replace(result, gate=None)
        if fault == "transport":
            return replace(result, exit=None, verdict="transport_error")
        if fault == "process-unfinished":
            return replace(result, gate=replace(result.gate, process_exit=None))
        if fault == "transport-verdict":
            return replace(result, verdict="transport_error")
        if fault == "blocked":
            return replace(result, policy_blocked=True)
        if fault == "unobserved":
            return replace(result, gate=replace(result.gate, observed=False))
        # Retain real failed own-test IDs and observed=True: structural distrust must
        # stop before collectibility/partitioning could promote them to a source target.
        return replace(result, gate=replace(result.gate, anomaly=fault, observed=True))

    responses = [_write(TEST_PATH, MISSING_IMPORT_TEST)]
    if during_repair:
        responses.append(_write(TEST_PATH, VALID_TEST))
    outcome, model, test_calls, events = _run(
        tmp_path, BROKEN_SOURCE, responses, run_tests=untrusted_observation)
    assert len(test_calls) == (2 if during_repair else 1)
    assert calls == (2 if during_repair else 1)
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "uncertain"
    assert outcome.stop_reason == "self-test-unverified"
    assert outcome.attempts == []
    assert outcome.own_test_discriminating == []
    assert outcome.own_test_symptom_ids == []
    assert outcome.own_test_gate is None
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert any(kind == "self_test_unverified" for kind, _ in events)
    assert (tmp_path / TEST_PATH).read_text() == (VALID_TEST if during_repair else MISSING_IMPORT_TEST)
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE


def test_run_leaf_green_reask_setup_failure_is_repaired_before_source_iteration(tmp_path):
    green_test = VALID_TEST.replace("== 42", "== 0")
    outcome, model, test_calls, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, green_test), _write(TEST_PATH, MISSING_IMPORT_TEST),
         _write(TEST_PATH, VALID_TEST), _write(SOURCE_PATH, FIXED_SOURCE)])
    assert len(test_calls) == 3
    assert len(model.calls("implement_write")) == 1
    kinds = [kind for kind, _ in events]
    assert kinds.index("self_test_green_on_arrival") < kinds.index("self_test_setup_invalid")
    assert kinds.index("self_test_setup_rechecked") < kinds.index("self_test_written")
    assert outcome.own_test_discriminating == [f"{TEST_PATH}::test_ac1_result"]
    assert outcome.claimed


def test_run_leaf_green_reask_shares_the_single_setup_repair_cap(tmp_path):
    missing_green_test = MISSING_IMPORT_TEST.replace("== 42", "== 0")
    green_test = VALID_TEST.replace("== 42", "== 0")
    outcome, model, test_calls, events = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, missing_green_test), _write(TEST_PATH, green_test),
         _write(TEST_PATH, MISSING_IMPORT_TEST)])
    assert len(test_calls) == 3
    assert sum(kind == "self_test_setup_invalid" for kind, _ in events) == 2
    assert any("cap exhausted" in refusal for refusal in outcome.refusals)
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "uncertain"
    assert outcome.own_test_discriminating == []
    assert outcome.own_test_gate is None
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert (tmp_path / TEST_PATH).read_text() == MISSING_IMPORT_TEST


def test_run_leaf_setup_failure_with_no_repair_calls_stops_without_source_churn(tmp_path):
    outcome, model, test_calls, _ = _run(
        tmp_path, BROKEN_SOURCE, [_write(TEST_PATH, MISSING_IMPORT_TEST)],
        budget=Budget(calls=1, deadline_ts=2_000_000_000))
    assert len(test_calls) == 1
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "uncertain"
    assert outcome.stop_reason == "self-test-invalid"
    assert any("no calls remain" in refusal for refusal in outcome.refusals)
    assert (tmp_path / TEST_PATH).read_text() == MISSING_IMPORT_TEST


@pytest.mark.parametrize("expire_during_repair", [False, True], ids=["before-repair", "during-repair"])
def test_run_leaf_setup_repair_respects_deadline_and_retains_artifact(
    tmp_path, monkeypatch, expire_during_repair,
):
    clock = [0]
    original_complete = FakeModelRunner.complete

    async def expire_after_model_response(model, request):
        response = await original_complete(model, request)
        if expire_during_repair and model.total_calls == 2:
            clock[0] = 10
        return response

    monkeypatch.setattr(FakeModelRunner, "complete", expire_after_model_response)

    async def expire_after_initial_observation(workdir):
        result = await _default_run_tests(workdir)
        if not expire_during_repair:
            clock[0] = 10
        return result

    responses = [_write(TEST_PATH, MISSING_IMPORT_TEST)]
    if expire_during_repair:
        responses.append(_write(TEST_PATH, VALID_TEST))
    outcome, model, test_calls, _ = _run(
        tmp_path, BROKEN_SOURCE, responses,
        budget=Budget(calls=8, deadline_ts=10), now=lambda: clock[0],
        run_tests=expire_after_initial_observation)
    assert len(test_calls) == (2 if expire_during_repair else 1)
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "parked"  # preserve the existing deadline/handover contract
    assert outcome.stop_reason == "deadline"
    assert outcome.own_test_discriminating == []
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert (tmp_path / TEST_PATH).read_text() == MISSING_IMPORT_TEST


@pytest.mark.parametrize("repair", [
    {**_write(TEST_PATH, VALID_TEST), "status": "blocked"},
    {"status": "unable", "comment": "cannot repair imports", "unable_reason": "no valid setup edit"},
    _write(TEST_PATH, ""),
    _write(TEST_PATH, MISSING_IMPORT_TEST),
    _write(SOURCE_PATH, VALID_TEST),
    _write("../test_escape.py", VALID_TEST),
    EnvelopeSpec(kind="raw", body='{"status": "ok",'),
], ids=["blocked", "unable", "empty", "unchanged", "source-path", "escaping-path", "malformed"])
def test_run_leaf_unusable_setup_repair_is_bounded_and_cannot_write_another_path(tmp_path, repair):
    outcome, model, test_calls, _ = _run(
        tmp_path, BROKEN_SOURCE,
        [_write(TEST_PATH, MISSING_IMPORT_TEST), repair])
    assert len(test_calls) == 2
    assert not model.calls("implement_write")
    assert not outcome.claimed
    assert outcome.state == "uncertain"
    assert outcome.stop_reason == "self-test-invalid"
    assert outcome.attempts == []
    assert outcome.own_test_discriminating == []
    assert outcome.own_test_gate is None
    assert not any(row.state == "violated" for row in outcome.ledger)
    assert (tmp_path / TEST_PATH).read_text() == MISSING_IMPORT_TEST
    assert (tmp_path / SOURCE_PATH).read_text() == BROKEN_SOURCE
    assert not (tmp_path.parent / "test_escape.py").exists()
