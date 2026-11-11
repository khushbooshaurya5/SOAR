"""Python <-> Soar bridge using the official SML interface (``soar-sml``).

Responsibilities of this class -- and nothing more:

* create a Soar kernel + agent and load the productions in ``soar/``;
* mirror what the agent can *perceive* onto the input-link;
* run Soar's decision cycle until it issues a command on the output-link;
* hand that command back to the simulation.

It never chooses an action and never computes a route.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import soar_sml as sml

from .grid import GridWorld, Pos

SOAR_DIR = Path(__file__).resolve().parent.parent / "soar"
DEFAULT_RULES = SOAR_DIR / "load.soar"


@dataclass
class Command:
    """One command read from Soar's output-link."""

    name: str                 # move | arrived | stop
    direction: Optional[str] = None
    reason: Optional[str] = None


class SoarNavigator:
    def __init__(
        self,
        rules: Path | str = DEFAULT_RULES,
        learning: bool = True,
        seed: int = 1,
        max_decisions_per_step: int = 5000,
    ):
        self.kernel = sml.Kernel.CreateKernelInCurrentThread(True)
        if self.kernel is None or self.kernel.HadError():
            raise RuntimeError("could not create Soar kernel")
        self.agent = self.kernel.CreateAgent("navigator")
        if self.agent is None:
            raise RuntimeError(self.kernel.GetLastErrorDescription())
        self.agent.LoadProductions(str(rules))
        if self.agent.HadError():
            raise RuntimeError(self.agent.GetLastErrorDescription())
        # load.soar selects `chunk except`; `chunk never` turns learning off.
        if not learning:
            self.cli("chunk never")
        self.learning = learning
        self.cli(f"decide set-random-seed {seed}")
        # RunSelfTilOutput gives up after this many decisions without output.
        self.cli(f"soar max-nil-output-cycles {max_decisions_per_step}")
        self.max_decisions_per_step = max_decisions_per_step
        self._print_handler = None
        self._print_cb_id = None
        self._top_wmes: list = []
        self._cell_ids: Dict[Pos, object] = {}
        self._crowd_wmes: Dict[Pos, object] = {}
        self._agent_cell_wme = None
        self._epoch_wme = None
        self._percept_id = None
        self._obstacle_wmes: Dict[Pos, object] = {}
        self.world: Optional[GridWorld] = None

    # -- utilities ------------------------------------------------------
    def cli(self, command: str) -> str:
        """Run a Soar command-line command and return its output."""
        return self.agent.ExecuteCommandLine(command)

    def capture_trace(self, handler: Callable[[str], None], level: int = 1) -> None:
        """Send Soar's own trace output (``trace <level>``) to ``handler``."""
        self._print_handler = handler

        def _cb(event_id, user_data, agent, message):
            handler(message)

        self._print_cb = _cb
        self._print_cb_id = self.agent.RegisterForPrintEvent(
            sml.smlEVENT_PRINT, _cb, None
        )
        self.cli(f"trace {level}")

    @property
    def decision_count(self) -> int:
        return self.agent.GetDecisionCycleCounter()

    def chunk_names(self) -> List[str]:
        out = self.cli("print --chunks")
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def firing_count(self, production: str) -> int:
        """How often a production has fired since it was loaded/learned."""
        out = self.cli(f"production firing-counts {production}")
        m = re.search(r"(\d+):\s+" + re.escape(production), out)
        return int(m.group(1)) if m else 0

    # -- input-link -----------------------------------------------------
    def begin_episode(self, world: GridWorld, start: Pos, goal: Pos, profile: str) -> None:
        """Reset working memory (chunks are kept) and present a new task."""
        a = self.agent
        for wme in self._top_wmes:
            a.DestroyWME(wme)
        self._top_wmes = []
        a.InitSoar()

        self.world = world
        il = a.GetInputLink()

        # (I2 ^map M) (M ^cell C ...) -- the floor plan the agent knows
        m = a.CreateIdWME(il, "map")
        self._cell_ids, self._crowd_wmes = {}, {}
        for pos, terrain in world.terrain.items():
            c = a.CreateIdWME(m, "cell")
            a.CreateIntWME(c, "x", pos[0])
            a.CreateIntWME(c, "y", pos[1])
            a.CreateStringWME(c, "terrain", terrain)
            self._crowd_wmes[pos] = a.CreateIntWME(c, "crowd", world.crowd[pos])
            self._cell_ids[pos] = c
        for pos, c in self._cell_ids.items():
            for direction, q in world.neighbors(pos):
                nb = a.CreateIdWME(c, "neighbor")
                a.CreateStringWME(nb, "dir", direction)
                a.CreateSharedIdWME(nb, "cell", self._cell_ids[q])

        # (I2 ^user U) (U ^profile standard|wheelchair|low-vision)
        user = a.CreateIdWME(il, "user")
        a.CreateStringWME(user, "profile", profile)

        # (I2 ^goal G) (G ^cell C)
        goal_id = a.CreateIdWME(il, "goal")
        a.CreateSharedIdWME(goal_id, "cell", self._cell_ids[goal])

        # (I2 ^agent A) (A ^cell C)
        self._agent_id = a.CreateIdWME(il, "agent")
        self._agent_cell_wme = a.CreateSharedIdWME(
            self._agent_id, "cell", self._cell_ids[start]
        )

        # (I2 ^crowd-epoch N) and (I2 ^percept P) (P ^obstacle C)
        self._epoch_wme = a.CreateIntWME(il, "crowd-epoch", world.crowd_epoch)
        self._percept_id = a.CreateIdWME(il, "percept")
        self._obstacle_wmes = {}
        self._top_wmes = [m, user, goal_id, self._agent_id, self._epoch_wme, self._percept_id]
        self.update_percepts(start, [])

    def update_percepts(self, agent_pos: Pos, crowd_changed: List[Pos]) -> None:
        """Push the current perception to the input-link."""
        a, world = self.agent, self.world
        # where am I?
        a.DestroyWME(self._agent_cell_wme)
        self._agent_cell_wme = a.CreateSharedIdWME(
            self._agent_id, "cell", self._cell_ids[agent_pos]
        )
        # building occupancy feed
        for pos in crowd_changed:
            a.Update(self._crowd_wmes[pos], world.crowd[pos])
        a.Update(self._epoch_wme, world.crowd_epoch)
        # obstacles currently in view (adjacent cells only)
        seen = set(world.visible_obstacles(agent_pos))
        for pos in list(self._obstacle_wmes):
            if pos not in seen:
                a.DestroyWME(self._obstacle_wmes.pop(pos))
        for pos in seen:
            if pos not in self._obstacle_wmes:
                self._obstacle_wmes[pos] = a.CreateSharedIdWME(
                    self._percept_id, "obstacle", self._cell_ids[pos]
                )
        a.Commit()

    # -- decision cycle + output-link -----------------------------------
    def decide(self) -> tuple[Optional[Command], int, float]:
        """Run Soar until it produces output.

        Returns ``(command, decision_cycles_used, wall_seconds_inside_soar)``.
        """
        before = self.decision_count
        t0 = time.perf_counter()
        self.agent.RunSelfTilOutput()
        elapsed = time.perf_counter() - t0
        used = self.decision_count - before

        command = None
        for i in range(self.agent.GetNumberCommands()):
            cmd = self.agent.GetCommand(i)
            name = cmd.GetCommandName()
            if name == "move":
                command = Command("move", direction=cmd.GetParameterValue("dir"))
            elif name == "arrived":
                command = Command("arrived")
            elif name == "stop":
                command = Command("stop", reason=cmd.GetParameterValue("reason"))
            cmd.AddStatusComplete()
        self.agent.ClearOutputLinkChanges()
        return command, used, elapsed

    def close(self) -> None:
        if self.kernel is not None:
            self.kernel.DestroyAgent(self.agent)
            self.kernel.Shutdown()
            self.kernel = None
