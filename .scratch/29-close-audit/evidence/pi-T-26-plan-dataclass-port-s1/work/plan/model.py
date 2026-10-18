"""The build plan record.

Port note: this module moves the plan off ad-hoc dicts onto a Plan
dataclass. The public surface (make_plan, plan["name"]-style access)
must keep working for existing callers during the migration.
"""


def make_plan(name: str, steps: list[str]) -> dict:
    return {"name": name, "steps": list(steps), "done": False}


def finish(plan: dict) -> dict:
    plan["done"] = True
    return plan
