"""The ported Plan keeps the old contract and adds attribute access."""

from plan.model import Plan, finish, make_plan


def test_old_dict_access_still_works():
    p = make_plan("nightly", ["build", "test"])
    assert p["name"] == "nightly" and p["done"] is False
    finish(p)
    assert p["done"] is True


def test_plan_is_a_dataclass_with_attributes():
    p = make_plan("nightly", ["build"])
    assert isinstance(p, Plan)
    assert p.name == "nightly" and p.steps == ["build"] and p.done is False
