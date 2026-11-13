"""Episode runner: couples the grid world to the Soar agent and measures it.

The loop is the classic perceive -> decide -> act cycle:

    environment --(input-link)--> Soar --(output-link)--> environment

All choices are made inside ``SoarNavigator.decide()`` (i.e. inside the
Soar kernel). This module only executes the returned motor command and
keeps score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set

from .cost_model import enter_cost
from .grid import DIRECTIONS, GridWorld, Pos
from .scenarios import Scenario
from .soar_agent import SoarNavigator


@dataclass
class EpisodeResult:
    scenario: str
    profile: str
    outcome: str = "timeout"          # arrived | no-accessible-route | timeout | no-decision
    success: bool = False
    steps: int = 0                    # moves executed
    route_cost: int = 0               # sum of enter costs actually paid
    crowd_exposure: int = 0           # sum of crowd levels of cells entered
    collisions: int = 0               # moves into a wall/obstacle (should be 0)
    decisions: int = 0                # Soar decision cycles
    soar_seconds: float = 0.0         # wall time spent inside the Soar kernel
    plans: int = 0                    # times the plan-route subgoal was entered
    tie_impasses: int = 0             # times the tie-break subgoal was entered
    chunk_firings: int = 0            # firings of learned rules this episode
    obstacles_recorded: int = 0
    chunks_total: int = 0             # chunks in production memory afterwards
    path: List[Pos] = field(default_factory=list)
    # for visualisation
    crowd_by_step: List[int] = field(default_factory=list)       # snapshot index per step
    crowd_snapshots: List[Dict[Pos, int]] = field(default_factory=list)
    discovered_by_step: List[List[Pos]] = field(default_factory=list)
    decisions_by_step: List[int] = field(default_factory=list)
    seconds_by_step: List[float] = field(default_factory=list)

    @property
    def ms_per_step(self) -> float:
        n = len(self.seconds_by_step)
        return 1000.0 * self.soar_seconds / n if n else 0.0

    @property
    def ms_per_decision(self) -> float:
        return 1000.0 * self.soar_seconds / self.decisions if self.decisions else 0.0

    def summary(self) -> dict:
        """Scalar metrics only (for CSV/JSON)."""
        d = asdict(self)
        for k in ("path", "crowd_by_step", "crowd_snapshots", "discovered_by_step",
                  "decisions_by_step", "seconds_by_step"):
            d.pop(k)
        d["ms_per_step"] = round(self.ms_per_step, 3)
        d["ms_per_decision"] = round(self.ms_per_decision, 4)
        d["soar_seconds"] = round(self.soar_seconds, 5)
        return d


def run_episode(
    nav: SoarNavigator,
    scenario: Scenario,
    world: Optional[GridWorld] = None,
) -> EpisodeResult:
    world = world or scenario.build_world()
    world.reset_dynamics()
    world.obstacles = set(scenario.obstacles)
    world.set_crowd_phases(scenario.crowd_phases)
    world.update_crowd(0)

    res = EpisodeResult(scenario=scenario.name, profile=scenario.profile)
    pos = scenario.start
    res.path.append(pos)
    discovered: Set[Pos] = set(world.visible_obstacles(pos))

    def snapshot() -> None:
        if not res.crowd_snapshots or res.crowd_snapshots[-1] != world.crowd:
            res.crowd_snapshots.append(dict(world.crowd))
        res.crowd_by_step.append(len(res.crowd_snapshots) - 1)
        res.discovered_by_step.append(sorted(discovered))

    snapshot()
    nav.begin_episode(world, scenario.start, scenario.goal, scenario.profile)

    while True:
        command, used, seconds = nav.decide()
        res.decisions += used
        res.soar_seconds += seconds
        res.decisions_by_step.append(used)
        res.seconds_by_step.append(seconds)

        if command is None:
            res.outcome = "no-decision"
            break
        if command.name == "arrived":
            res.outcome, res.success = "arrived", pos == scenario.goal
            break
        if command.name == "stop":
            res.outcome = command.reason or "stopped"
            break

        # --- act: execute the motor command in the world ---
        dx, dy = DIRECTIONS[command.direction]
        target = (pos[0] + dx, pos[1] + dy)
        if not world.is_free(target) or target in world.obstacles:
            res.collisions += 1            # the world refuses the move
        else:
            pos = target
            cost = enter_cost(scenario.profile, world.terrain[pos], world.crowd[pos])
            res.route_cost += cost if cost is not None else 0
            res.crowd_exposure += world.crowd[pos]
        res.steps += 1
        res.path.append(pos)

        # --- the world moves on; perceive again ---
        changed = world.update_crowd(res.steps)
        discovered |= set(world.visible_obstacles(pos))
        snapshot()
        if res.steps >= scenario.max_steps:
            res.outcome = "timeout"
            break
        nav.update_percepts(pos, changed)

    # Soar-side bookkeeping (firing counts are reset by init-soar,
    # so these are per-episode numbers).
    res.plans = nav.firing_count("plan-route*apply*init-plan")
    res.tie_impasses = nav.firing_count("tie-break*elaborate*substate")
    res.obstacles_recorded = nav.firing_count("navigate*apply*record-obstacle")
    chunks = nav.chunk_names()
    res.chunks_total = len(chunks)
    res.chunk_firings = sum(nav.firing_count(c) for c in chunks)
    return res
