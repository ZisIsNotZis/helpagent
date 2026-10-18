from plan.model import make_plan, finish






def test_plan_is_real_dataclass():
    plan = make_plan("test", ["step1"])
    assert hasattr(plan, "name")
    assert plan.name == "test"
    assert hasattr(plan, "steps")
    assert plan.steps == ["step1"]
    assert hasattr(plan, "done")
    assert plan.done is False


def test_finish_updates_dataclass():
    plan = make_plan("test", ["step1"])
    result = finish(plan)
    assert isinstance(result, type(plan))
    assert result.done is True
    assert result is plan
