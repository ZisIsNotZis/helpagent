"""The build plan record.

Port note: this module moves the plan off ad-hoc dicts onto a Plan
dataclass. The public surface (make_plan, plan["name"]-style access) 
must keep working for existing callers during the migration.
"""


from dataclasses import dataclass


@dataclass
class Plan:
    name: str
    steps: list[str]
    done: bool = False


def make_plan(name: str, steps: list[str]) -> Plan:
    return Plan(name=name, steps=list(steps), done=False)


def finish(plan: Plan) -> Plan:
    plan.done = True
    return plan
