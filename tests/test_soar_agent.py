"""Integration tests: these run the real Soar kernel through SML."""
import random

import pytest

from cognav.cost_model import PROFILES
from cognav.grid import CrowdPhase, CrowdZone, GridWorld
from cognav.reference import optimal_cost
from cognav.scenarios import ROOT, Scenario
from cognav.simulation import run_episode
from cognav.soar_agent import SoarNavigator

MAP = "maps/campus_floor.txt"


@pytest.fixture
def nav():
    n = SoarNavigator()
    yield n
    n.close()


def test_productions_load_into_real_soar(nav):
    assert nav.kernel.GetSoarKernelVersion().startswith("9.")
    names = nav.cli("print")
    for rule in ("navigate*propose*move", "plan-route*propose*label",
                 "tie-break*apply*prefer", "access*wheelchair*stairs-impassable"):
        assert rule in names


@pytest.mark.parametrize("name", ["normal", "crowded"])
def test_showcase_scenarios_succeed(nav, name):
    res = run_episode(nav, Scenario.load(name))
    assert res.success and res.collisions == 0


@pytest.mark.parametrize("profile", PROFILES)
def test_route_cost_equals_independent_optimum(nav, profile):
    """Soar's rule-derived routes must cost exactly what a textbook
    Dijkstra over the reference cost table says is optimal."""
    world = GridWorld.from_file(ROOT / MAP)
    rng = random.Random(11)
    cells = sorted(p for p, t in world.terrain.items() if t in ("floor", "tactile"))
    for i in range(4):
        start, goal = rng.sample(cells, 2)
        sc = Scenario(f"t{i}", "t", MAP, profile, start, goal)
        res = run_episode(nav, sc, world)
        world.reset_dynamics()
        assert res.success
        assert res.route_cost == optimal_cost(world, start, goal, profile)


def test_wheelchair_never_enters_stairs_or_narrow(nav):
    sc = Scenario.load("accessibility")          # wheelchair profile
    world = sc.build_world()
    res = run_episode(nav, sc, world)
    assert res.success
    assert not {world.terrain[p] for p in res.path} & {"stairs", "narrow"}


def test_profiles_choose_different_routes():
    paths = {}
    for profile in PROFILES:
        n = SoarNavigator()
        paths[profile] = tuple(run_episode(n, Scenario.load("accessibility").with_profile(profile)).path)
        n.close()
    assert len(set(paths.values())) == 3


def test_subgoals_are_used(nav):
    res = run_episode(nav, Scenario.load("normal"))
    assert res.plans == 1            # operator no-change impasse -> plan-route substate
    assert res.tie_impasses >= 1     # operator tie impasse -> tie-break substate


def test_chunking_learns_and_removes_impasses(nav):
    sc = Scenario.load("normal")
    first = run_episode(nav, sc)
    assert first.chunks_total >= 1
    assert all(c.startswith("chunk*tie-break") for c in nav.chunk_names())
    second = run_episode(nav, sc)    # same agent: chunks persist across init-soar
    assert second.tie_impasses == 0 and second.chunk_firings > 0
    assert second.route_cost == first.route_cost


def test_no_chunks_without_learning():
    n = SoarNavigator(learning=False)
    a = run_episode(n, Scenario.load("normal"))
    b = run_episode(n, Scenario.load("normal"))
    n.close()
    assert a.chunks_total == 0 and b.tie_impasses == a.tie_impasses > 0


def test_hidden_obstacle_is_recorded_and_avoided(nav):
    # corridor trip; a cart blocks both lanes' direct line except a gap
    sc = Scenario("obst", "obst", MAP, "standard", (2, 6), (12, 6),
                  obstacles=[(6, 6), (7, 5)])
    res = run_episode(nav, sc)
    assert res.success and res.collisions == 0
    assert res.obstacles_recorded >= 1 and res.plans >= 2
    assert not set(res.path) & set(sc.obstacles)


def test_crowd_change_triggers_replanning(nav):
    sc = Scenario("crowd", "crowd", MAP, "standard", (2, 6), (22, 6),
                  crowd_phases=[CrowdPhase(0, []),
                                CrowdPhase(4, [CrowdZone(10, 6, 14, 6, 3)])])
    res = run_episode(nav, sc)
    assert res.success and res.plans == 2
    assert res.crowd_exposure == 0          # switched to the free lane


def test_unreachable_goal_is_reported_not_attempted(nav):
    # lower level is reachable for a wheelchair only via the ramp: block it
    sc = Scenario("noroute", "noroute", MAP, "wheelchair", (9, 6), (10, 14),
                  obstacles=[(23, 7)])
    res = run_episode(nav, sc)
    assert not res.success
    assert res.outcome == "no-accessible-route"
    assert res.collisions == 0


def test_tie_break_prefers_less_crowded_cell(tmp_path, nav):
    """Two symmetric routes with identical total cost; only the crowd level
    of the FIRST cell differs -> the less-crowded criterion must decide."""
    m = tmp_path / "ring.txt"
    m.write_text("#####\n#...#\n#.#.#\n#...#\n#####\n")
    world = GridWorld.from_file(m)
    sc = Scenario("ring", "ring", str(m), "standard", (1, 1), (3, 3),
                  crowd_phases=[CrowdPhase(0, [CrowdZone(2, 1, 2, 1, 1),     # east route, 1st cell
                                               CrowdZone(2, 3, 2, 3, 1)])])  # south route, 3rd cell
    res = run_episode(nav, sc, world)
    assert res.success and res.tie_impasses == 1
    assert res.path[1] == (1, 2)
    # the learned rule compares the two crowd levels
    chunk = nav.cli("print --chunks --full")
    assert "^crowd" in chunk and "< <c" in chunk
