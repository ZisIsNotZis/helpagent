import pytest
from plan.model import Plan, make_plan, finish


def test_ac1_plan_is_dataclass():
    """AC1: Plan must be a real dataclass object with attribute access."""
    plan = make_plan("test", ["step1"])
    assert isinstance(plan, Plan)
    assert plan.name == "test"
    assert plan.steps == ["step1"]
    assert plan.done is False


def test_ac2_dict_style_access_and_api():
    """AC2: Keep old dict-style access, make_plan/finish as-is, and attribute access."""
    plan = make_plan("test", ["step1", "step2"])
    assert plan["name"] == "test"
    assert plan["steps"] == ["step1", "step2"]
    assert plan["done"] is False

    finished = finish(plan)
    assert finished["done"] is True
    assert finished.done is True
    assert isinstance(finished, Plan)


def test_ac3_ported_plan():
    """AC3: The build plan is successfully ported to a real dataclass."""
    plan = make_plan("ported", ["a", "b", "c"])
    assert isinstance(plan, Plan)
    assert plan.name == "ported"
    assert plan.steps == ["a", "b", "c"]
    assert plan.done is False
    assert finish(plan).done is True
