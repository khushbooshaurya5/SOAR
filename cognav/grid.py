"""Grid-based indoor environment.

This module is the *world*: geometry, terrain, crowds and obstacles.
It contains no navigation logic at all -- every decision about where to
go is made by Soar productions (see ``soar/``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

Pos = Tuple[int, int]

#: map character -> terrain symbol sent to Soar
TERRAIN_BY_CHAR = {
    ".": "floor",
    "T": "tactile",   # tactile guidance paving
    "O": "open",      # open atrium space
    "D": "door",      # manual door
    "A": "autodoor",  # automatic door
    "R": "ramp",
    "S": "stairs",
    "N": "narrow",    # narrow service passage
}
WALL = "#"

#: direction name -> (dx, dy); y grows downwards (row index)
DIRECTIONS: Dict[str, Pos] = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


@dataclass
class CrowdZone:
    """Axis-aligned rectangle (inclusive) with a crowd level 1-3."""

    x0: int
    y0: int
    x1: int
    y1: int
    level: int

    def cells(self) -> Iterable[Pos]:
        for x in range(self.x0, self.x1 + 1):
            for y in range(self.y0, self.y1 + 1):
                yield (x, y)


@dataclass
class CrowdPhase:
    """The crowd picture that holds from ``from_step`` until the next phase."""

    from_step: int
    zones: List[CrowdZone] = field(default_factory=list)


class GridWorld:
    """Static floor plan plus time-varying crowds and hidden obstacles."""

    def __init__(self, rows: List[str]):
        if len({len(r) for r in rows}) != 1:
            raise ValueError("all map rows must have the same width")
        self.rows = rows
        self.width = len(rows[0])
        self.height = len(rows)
        self.terrain: Dict[Pos, str] = {}
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == WALL:
                    continue
                if ch not in TERRAIN_BY_CHAR:
                    raise ValueError(f"unknown map character {ch!r} at {(x, y)}")
                self.terrain[(x, y)] = TERRAIN_BY_CHAR[ch]
        self.crowd: Dict[Pos, int] = {p: 0 for p in self.terrain}
        self.obstacles: Set[Pos] = set()
        self.crowd_phases: List[CrowdPhase] = []
        self.crowd_epoch = 0
        self._active_phase: Optional[int] = None

    # -- construction ---------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path) -> "GridWorld":
        text = Path(path).read_text()
        return cls([line for line in text.splitlines() if line.strip()])

    # -- geometry -------------------------------------------------------
    def is_free(self, pos: Pos) -> bool:
        """Not a wall (obstacles and crowds are handled separately)."""
        return pos in self.terrain

    def neighbors(self, pos: Pos) -> List[Tuple[str, Pos]]:
        out = []
        for name, (dx, dy) in DIRECTIONS.items():
            q = (pos[0] + dx, pos[1] + dy)
            if q in self.terrain:
                out.append((name, q))
        return out

    # -- dynamics -------------------------------------------------------
    def reset_dynamics(self) -> None:
        """Clear crowds, obstacles and the epoch counter (new episode)."""
        self.crowd = {p: 0 for p in self.terrain}
        self.obstacles = set()
        self.crowd_phases = []
        self.crowd_epoch = 0
        self._active_phase = None

    def set_crowd_phases(self, phases: List[CrowdPhase]) -> None:
        self.crowd_phases = sorted(phases, key=lambda p: p.from_step)
        self._active_phase = None

    def update_crowd(self, step: int) -> List[Pos]:
        """Advance the crowd picture to ``step``.

        Returns the cells whose crowd level changed. ``crowd_epoch`` is
        incremented whenever at least one cell changed.
        """
        active = None
        for i, phase in enumerate(self.crowd_phases):
            if phase.from_step <= step:
                active = i
        if active == self._active_phase:
            return []
        self._active_phase = active
        new = {p: 0 for p in self.terrain}
        if active is not None:
            for zone in self.crowd_phases[active].zones:
                for p in zone.cells():
                    if p in new:
                        new[p] = max(new[p], zone.level)
        changed = [p for p in new if new[p] != self.crowd[p]]
        self.crowd = new
        if changed:
            self.crowd_epoch += 1
        return changed

    def visible_obstacles(self, pos: Pos) -> List[Pos]:
        """Obstacles are only perceived in the four adjacent cells."""
        return [q for _, q in self.neighbors(pos) if q in self.obstacles]
