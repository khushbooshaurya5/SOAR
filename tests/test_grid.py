"""Environment tests (no Soar involved)."""
from cognav.cost_model import enter_cost
from cognav.grid import CrowdPhase, CrowdZone, GridWorld
from cognav.reference import optimal_cost, shortest_path
from cognav.scenarios import ROOT


def world():
    return GridWorld.from_file(ROOT / "maps/campus_floor.txt")


def test_map_parses():
    w = world()
    assert (w.width, w.height) == (26, 16)
    assert w.terrain[(12, 7)] == "stairs"
    assert w.terrain[(23, 7)] == "ramp"
    assert not w.is_free((0, 0))


def test_neighbors_exclude_walls():
    w = world()
    assert dict(w.neighbors((1, 1))) == {"east": (2, 1), "south": (1, 2)}


def test_crowd_phases_and_epoch():
    w = world()
    w.set_crowd_phases([CrowdPhase(0, [CrowdZone(1, 5, 3, 5, 2)]),
                        CrowdPhase(5, [])])
    assert set(w.update_crowd(0)) == {(1, 5), (2, 5), (3, 5)}
    assert w.crowd[(2, 5)] == 2 and w.crowd_epoch == 1
    assert w.update_crowd(3) == [] and w.crowd_epoch == 1
    assert len(w.update_crowd(5)) == 3 and w.crowd[(2, 5)] == 0 and w.crowd_epoch == 2


def test_obstacles_only_visible_when_adjacent():
    w = world()
    w.obstacles = {(4, 6)}
    assert w.visible_obstacles((3, 6)) == [(4, 6)]
    assert w.visible_obstacles((2, 6)) == []


def test_reference_cost_model():
    assert enter_cost("wheelchair", "stairs", 0) is None
    assert enter_cost("standard", "stairs", 0) == 2
    assert enter_cost("low-vision", "open", 1) == 1 + 2 + 4
    w = world()
    assert optimal_cost(w, (9, 2), (10, 14), "standard") == 18
    assert len(shortest_path(w, (9, 2), (10, 14))) - 1 == 17
