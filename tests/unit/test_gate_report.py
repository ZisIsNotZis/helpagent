"""Machine-readable pytest gate (ticket 17 F1): the exit status is not evidence.

The adversarial pass forged a green with ``import atexit, os`` +
``atexit.register(lambda: os._exit(0))``: both gates exited 0 with no test summary and
the run claimed a true success with the real bug untouched. These cases pin the
replacement — a green needs a report that parses, holds the expected test files and the
per-run random canary, and reports no failure or error — and pin that a report which
merely says the tests FAILED is still a trustworthy RED (not a gate anomaly).
"""

from __future__ import annotations

from pathlib import Path

from harness.gate_report import (
    canary_node_id,
    canary_path,
    canary_source,
    canary_token,
    evaluate_gate,
    parse_junit,
)


def _report(tmp_path: Path, body: str, name: str = "report.xml") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def _case(file: str, name: str, kind: str = "", token: str = "") -> str:
    open_tag = f'<testcase classname="{file.replace("/", ".").removesuffix(".py")}" name="{name}" file="{file}"'
    if not kind:
        return open_tag + "/>"
    return open_tag + f'><{kind} message="boom"/></testcase>'


def _suite(*cases: str) -> str:
    return ("<testsuites><testsuite tests=\"1\" failures=\"0\" errors=\"0\">"
            + "".join(cases) + "</testsuite></testsuites>")


def test_canary_is_random_and_the_token_rides_the_node_id():
    first, second = canary_token(), canary_token()
    assert first != second and len(first) >= 16
    node = canary_node_id(first)
    assert node.startswith("tests/test_gate_canary_")
    assert first in node
    assert f"def test_gate_canary_{first}()" in canary_source(first)
    assert canary_path(first) == node.split("::", 1)[0]


def test_missing_report_is_never_green_even_with_exit_zero(tmp_path):
    """The forgery shape: the process exits 0 and writes no report."""
    gate = evaluate_gate(tmp_path / "absent.xml", canary="abc",
                        expected_files=("tests/test_x.py",), process_exit=0)
    assert gate.green is False
    assert gate.anomaly == "report-missing"
    assert gate.observed is False            # nothing was observed -> not even a red
    assert gate.structural_anomaly is True
    assert "process exit 0" in gate.detail


def test_unparsable_and_empty_reports_are_red(tmp_path):
    broken = evaluate_gate(_report(tmp_path, "<testsuites>", "broken.xml"),
                          canary="c", expected_files=("tests/test_x.py",), process_exit=0)
    assert broken.anomaly == "report-unparsable" and broken.green is False
    assert broken.observed is False

    empty = evaluate_gate(_report(tmp_path, "<testsuites/>", "empty.xml"),
                         canary="c", expected_files=("tests/test_x.py",), process_exit=0)
    assert empty.anomaly == "no-tests" and empty.green is False
    assert empty.observed is False


def test_a_fabricated_report_without_the_canary_cannot_green(tmp_path):
    """A fabricated report cannot contain a token it never saw."""
    path = _report(tmp_path, _suite(_case("tests/test_x.py", "test_ok")))
    gate = evaluate_gate(path, canary="deadbeef",
                         expected_files=("tests/test_x.py",), process_exit=0)
    assert gate.green is False
    assert gate.anomaly == "canary-missing"
    assert gate.observed is True


def test_green_needs_the_expected_tests_the_canary_and_a_zero_exit(tmp_path):
    token = "feedface"
    good = _suite(_case("tests/test_x.py", "test_ok"), _case(canary_path(token),
                                                             f"test_gate_canary_{token}"))
    gate = evaluate_gate(_report(tmp_path, good, "green.xml"), canary=token,
                         expected_files=("tests/test_x.py",), process_exit=0)
    assert gate.green is True and gate.anomaly == ""
    assert gate.n_tests == 2 and gate.n_failed == 0 and gate.n_errors == 0
    assert gate.observed is True and gate.structural_anomaly is False

    missing = _suite(_case(canary_path(token), f"test_gate_canary_{token}"))
    gone = evaluate_gate(_report(tmp_path, missing, "gone.xml"), canary=token,
                         expected_files=("tests/test_x.py",), process_exit=0)
    assert gone.anomaly == "expected-tests-missing" and gone.missing == ("tests/test_x.py",)

    skipped = _suite(_case("tests/test_x.py", "test_ok", "skipped"),
                     _case(canary_path(token), f"test_gate_canary_{token}"))
    skip = evaluate_gate(_report(tmp_path, skipped, "skip.xml"), canary=token,
                         expected_files=("tests/test_x.py",), process_exit=0)
    assert skip.anomaly == "expected-test-not-passed"

    canary_skipped = _suite(_case("tests/test_x.py", "test_ok"),
                             _case(canary_path(token), f"test_gate_canary_{token}", "skipped"))
    skipped_canary = evaluate_gate(_report(tmp_path, canary_skipped, "canaryskip.xml"),
                                   canary=token, expected_files=("tests/test_x.py",),
                                   process_exit=0)
    assert skipped_canary.anomaly == "canary-failed"

    canary_failed = _suite(_case("tests/test_x.py", "test_ok"),
                           _case(canary_path(token), f"test_gate_canary_{token}", "failure"))
    dead = evaluate_gate(_report(tmp_path, canary_failed, "canaryfail.xml"), canary=token,
                         expected_files=("tests/test_x.py",), process_exit=0)
    assert dead.anomaly == "tests-failed" and dead.observed is True

    disagreeing = evaluate_gate(_report(tmp_path, good, "copy.xml"), canary=token,
                                expected_files=("tests/test_x.py",), process_exit=1)
    assert disagreeing.anomaly == "process-exit"


def test_a_report_that_says_tests_failed_is_a_trustworthy_red_not_an_anomaly(tmp_path):
    token = "cafe"
    failed = _suite(_case("tests/test_x.py", "test_goal", "failure"),
                    _case(canary_path(token), f"test_gate_canary_{token}"))
    gate = evaluate_gate(_report(tmp_path, failed), canary=token,
                         expected_files=("tests/test_x.py",), process_exit=1)
    assert gate.green is False
    assert gate.anomaly == "tests-failed"
    assert gate.observed is True
    assert gate.structural_anomaly is False     # the loop may use it as a red target
    assert gate.failed_ids == ("tests/test_x.py::test_goal",)


def test_parse_junit_reads_outcomes_and_reports_parse_errors(tmp_path):
    token = "abc123"
    body = _suite(_case("tests/test_x.py", "test_pass"), _case("tests/test_x.py", "test_fail", "failure"),
                  _case("tests/test_x.py", "test_err", "error"),
                  _case(canary_path(token), f"test_gate_canary_{token}"))
    cases, error = parse_junit(_report(tmp_path, body))
    assert error == ""
    outcomes = {c.name: c.outcome for c in cases}
    assert outcomes == {"test_pass": "passed", "test_fail": "failed", "test_err": "error",
                        f"test_gate_canary_{token}": "passed"}
    assert parse_junit(tmp_path / "missing.xml")[1].startswith("FileNotFoundError")
    assert parse_junit(_report(tmp_path, "not xml", "bad.xml"))[1].startswith("ParseError")


def test_expected_file_with_no_passing_case_is_red(tmp_path: Path):
    """R4: an expected file that is merely present (all skipped) must not green."""
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest" tests="2" failures="0" errors="0">'
        '<testcase classname="tests.test_canary" name="test_gate_canary_canary" file="tests/test_gate_canary_canary.py"/>'
        '<testcase classname="tests.test_x" name="test_all" file="tests/test_all.py">'
        '<skipped message="skip"/></testcase>'
        '</testsuite></testsuites>')
    gate = evaluate_gate(report, canary="canary", expected_files=("tests/test_all.py",),
                         canary_dir="tests", process_exit=0)
    assert gate.green is False
    assert gate.anomaly == "expected-test-not-passed"


def test_class_qualified_testcases_get_a_runnable_selector(tmp_path: Path):
    """A class-based test must yield a pytest-runnable node id (file::Class::name);
    discarding classname produced an exit-4 'not found' and a false negative."""
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest" tests="2" failures="0" errors="0">'
        '<testcase classname="tests.test_x" name="test_top" file="tests/test_x.py"/>'
        '<testcase classname="tests.test_x.TestAC1" name="test_ac1_thing" '
        'file="tests/test_x.py"/>'
        '</testsuite></testsuites>')
    cases, error = parse_junit(report)
    assert error == ""
    ids = [c.node_id for c in cases]
    assert ids == ["tests/test_x.py::test_top", "tests/test_x.py::TestAC1::test_ac1_thing"]
