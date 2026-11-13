"""Scenario definitions (JSON files in ``scenarios/``)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from .grid import CrowdPhase, CrowdZone, GridWorld, Pos

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "scenarios"


@dataclass
class Scenario:
    name: str
    title: str
    map: str
    profile: str
    start: Pos
    goal: Pos
    crowd_phases: List[CrowdPhase] = field(default_factory=list)
    obstacles: List[Pos] = field(default_factory=list)
    max_steps: int = 200
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        phases = [
            CrowdPhase(p["from_step"], [CrowdZone(**z) for z in p["zones"]])
            for p in d.get("crowd_phases", [])
        ]
        return cls(
            name=d["name"],
            title=d.get("title", d["name"]),
            map=d["map"],
            profile=d.get("profile", "standard"),
            start=tuple(d["start"]),
            goal=tuple(d["goal"]),
            crowd_phases=phases,
            obstacles=[tuple(o) for o in d.get("obstacles", [])],
            max_steps=d.get("max_steps", 200),
            description=d.get("description", ""),
        )

    @classmethod
    def load(cls, name_or_path: str | Path) -> "Scenario":
        path = Path(name_or_path)
        if not path.exists():
            path = SCENARIO_DIR / f"{name_or_path}.json"
        return cls.from_dict(json.loads(path.read_text()))

    def build_world(self) -> GridWorld:
        return GridWorld.from_file(ROOT / self.map)

    def with_profile(self, profile: str) -> "Scenario":
        from dataclasses import replace
        return replace(self, profile=profile, name=f"{self.name}-{profile}")
