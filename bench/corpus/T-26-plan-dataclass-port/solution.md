# T-26-plan-dataclass-port - solution (never shown to a run)

One file: repo/plan/model.py. Introduce @dataclass Plan (name, steps default_factory list, done=False) with __getitem__/__setitem__ delegating to getattr/setattr; make_plan returns Plan(...); finish sets plan.done.

Red->green: test_plan_is_a_dataclass_with_attributes fails before, passes after; the dict-compat test passes throughout. Everything except repo/plan/model.py stays byte-identical.
