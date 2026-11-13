"""Reference copy of the agent's cost model -- FOR EVALUATION ONLY.

The Soar agent never sees this module. Its costs are derived by the
productions in ``soar/cost-model.soar``. This Python mirror exists so
that the evaluation can

* price the route the agent actually walked, and
* compute an independent optimum (``reference.py``) to compare against.

``tests/test_soar_agent.py`` checks that Soar's routes cost exactly the
optimum computed from this table, which keeps the two descriptions of
the cost model honest with respect to each other.
"""
from __future__ import annotations

from typing import Optional

PROFILES = ("standard", "wheelchair", "low-vision")

BASE_COST = {
    "floor": 1, "tactile": 1, "open": 1, "autodoor": 1, "narrow": 1,
    "door": 2, "ramp": 2, "stairs": 2,
}

CROWD_WEIGHT = {"standard": 1, "wheelchair": 2, "low-vision": 2}

#: (profile, terrain) -> extra cost
ACCESS_PENALTY = {
    ("wheelchair", "door"): 3,
    ("low-vision", "open"): 4,
    ("low-vision", "stairs"): 2,
    ("low-vision", "floor"): 1,
}

#: (profile, terrain) pairs that must never be entered
IMPASSABLE = {("wheelchair", "stairs"), ("wheelchair", "narrow")}


def enter_cost(profile: str, terrain: str, crowd: int) -> Optional[int]:
    """Cost of stepping into a cell, or ``None`` if the profile cannot."""
    if (profile, terrain) in IMPASSABLE:
        return None
    return (
        BASE_COST[terrain]
        + CROWD_WEIGHT[profile] * crowd
        + ACCESS_PENALTY.get((profile, terrain), 0)
    )
