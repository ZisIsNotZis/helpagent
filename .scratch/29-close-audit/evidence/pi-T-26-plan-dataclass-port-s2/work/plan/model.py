"""The build plan record.

Port note: this module moves the plan off ad-hoc dicts onto a Plan
dataclass. The public surface (make_plan, plan["name"]-style access)
must keep working for existing callers during the migration.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Plan:
    """A build plan record.

    This is a real dataclass object supporting both attribute access
    (``plan.name``, ``plan.steps``, ``plan.done``) and the legacy
    dict-style access (``plan["name"]``, ``plan.get("name")``,
    ``list(plan.items())``) so callers not yet migrated keep working.
    """

    name: str
    steps: list[str]
    done: bool = False

    # --- dict-style access ---

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def __iter__(self) -> Any:
        return iter(self.__dict__)

    def keys(self) -> list[str]:
        return list(self.__dict__.keys())

    def items(self) -> list[tuple[str, Any]]:
        return list(self.__dict__.items())

    def values(self) -> list[Any]:
        return list(self.__dict__.values())

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def make_plan(name: str, steps: list[str]) -> Plan:
    return Plan(name=name, steps=list(steps))


def finish(plan: Plan) -> Plan:
    plan["done"] = True
    return plan
