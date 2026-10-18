"""Queued process-local countercontrols; run only under parent-granted admission.

Each command must yield pytest exit 1 from the named regression assertion, not an
import/collection/transport error. This file does not grant resources or run on import.
No production file is mutated. Save full output and run the clean green gate first.
"""
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("setup-classifier", "old-frame-attribution",
                                         "setup-preservation", "observation-auth"))
    case = parser.parse_args().case
    import harness.leaf as leaf
    import pytest

    if case == "setup-classifier":
        leaf._own_test_setup_problem = lambda *args: ("", "")
        target = ("tests/unit/test_own_test_setup.py::"
                  "test_run_leaf_repairs_setup_before_implementation_and_reproves_red[missing-import]")
    elif case == "old-frame-attribution":
        def old_frame_attribution(failure, test_path, source_paths):
            frames = leaf._failure_frame_paths(failure)
            sources = {path for path in source_paths if not leaf.is_test_path(path)}
            return bool(test_path and any(leaf._same_path(frame, test_path) for frame in frames)
                        and not any(any(leaf._same_path(frame, source) for source in sources)
                                    for frame in frames))
        leaf.failure_is_test_attributed = old_frame_attribution
        target = "tests/unit/test_v2_leaf.py::test_d2_test_attributed_traceback_credits_test_wrong"
    elif case == "setup-preservation":
        leaf._setup_repair_preservation_problem = lambda *args: ""
        target = ("tests/unit/test_own_test_setup.py::"
                  "test_run_leaf_setup_only_repair_cannot_replace_existing_behavioral_checks[weakened-still-red]")
    else:
        leaf._own_test_observation_state = lambda *args: ("authenticated", "")
        target = ("tests/unit/test_own_test_setup.py::"
                  "test_run_leaf_setup_repair_with_missing_report_cannot_reuse_invalid_red")
    print(f"NEGATIVE CONTROL {case}: expect pytest exit 1 at the targeted behavioral assertion")
    return pytest.main(["-q", "-p", "no:warnings", target])


if __name__ == "__main__":
    raise SystemExit(main())
