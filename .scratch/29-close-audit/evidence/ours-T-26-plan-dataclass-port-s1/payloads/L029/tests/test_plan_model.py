import pytest
from plan.model import Plan, make_plan, finish


def test_ac1_plan_is_real_dataclass():
    """AC1: Plan must be a real dataclass object with attribute access."""
    plan = make_plan("test", ["step1"])
    assert isinstance(plan, Plan)
    assert plan.name == "test"
    assert plan.steps == ["step1"]
    assert plan.done is False


def test_ac2_dict_style_access_and_api():
    """AC2: Keep dict-style access, make_plan/finish as-is, and attribute access."""
    plan = make_plan("test", ["step1", "step2"])
    assert plan["name"] == "test"
    assert plan["steps"] == ["step1", "step2"]
    assert plan["done"] is False

    finished = finish(plan)
    assert finished["done"] is True
    assert finished.name == "test"
    assert finished.steps == ["step1", "step2"]


def test_ac3_make_plan_and_finish_return_plan():
    """AC3: Ported version keeps make_plan and finish returning Plan objects."""
    p1 = make_plan("a", ["x"])
    p2 = finish(p1)
    assert isinstance(p1, Plan)
    assert isinstance(p2, Plan)
    assert p1.name == "a"
    assert p2.done is True
    assert p2.steps == ["x"]
