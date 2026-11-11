"""Reference planners written in plain Python -- FOR EVALUATION ONLY.

Nothing in here is ever shown to the Soar agent. They provide:

* ``optimal_cost``     the cheapest route cost under the profile's cost
                       model for a *static* snapshot of the world
                       (ground truth for the optimality check);
* ``shortest_path``    a fewest-steps route that ignores crowds and
                       accessibility (the "naive" baseline).
"""
from __future__ import annotations

import heapq
from collections import deque
from typing import Dict, Iterable, List, Optional, Set

from .cost_model import enter_cost
from .grid import GridWorld, Pos


def optimal_cost(
    world: GridWorld,
    start: Pos,
    goal: Pos,
    profile: str,
    blocked: Iterable[Pos] = (),
) -> Optional[int]:
    """Dijkstra over the current crowd snapshot. ``None`` = unreachable."""
    blocked = set(blocked)
    dist: Dict[Pos, int] = {start: 0}
    heap = [(0, start)]
    while heap:
        d, p = heapq.heappop(heap)
        if p == goal:
            return d
        if d > dist[p]:
            continue
        for _, q in world.neighbors(p):
            if q in blocked:
                continue
            c = enter_cost(profile, world.terrain[q], world.crowd[q])
            if c is None:
                continue
            if d + c < dist.get(q, 1 << 60):
                dist[q] = d + c
                heapq.heappush(heap, (d + c, q))
    return None


def shortest_path(
    world: GridWorld, start: Pos, goal: Pos, blocked: Iterable[Pos] = ()
) -> Optional[List[Pos]]:
    """Breadth-first fewest-steps path; blind to crowds and accessibility."""
    blocked: Set[Pos] = set(blocked)
    prev: Dict[Pos, Optional[Pos]] = {start: None}
    queue = deque([start])
    while queue:
        p = queue.popleft()
        if p == goal:
            path = []
            while p is not None:
                path.append(p)
                p = prev[p]
            return path[::-1]
        for _, q in world.neighbors(p):
            if q not in prev and q not in blocked:
                prev[q] = p
                queue.append(q)
    return None
