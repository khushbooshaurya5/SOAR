#!/usr/bin/env python3
"""Run the three showcase scenarios once and write figures + a results table.

    python scripts/run_scenarios.py

Outputs (in results/):
    scenario_normal.png, scenario_crowded.png, scenario_crowded.gif,
    scenario_accessibility.png, scenario_results.json, scenario_results.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cognav import viz  # noqa: E402
from cognav.cost_model import PROFILES  # noqa: E402
from cognav.reference import optimal_cost, shortest_path  # noqa: E402
from cognav.scenarios import Scenario  # noqa: E402
from cognav.simulation import run_episode  # noqa: E402
from cognav.soar_agent import SoarNavigator  # noqa: E402

OUT = ROOT / "results"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []

    def record(sc, world, res):
        # reference numbers on the *static* map (no crowd, no obstacles)
        world.reset_dynamics()
        row = res.summary()
        row["static_optimal_cost"] = optimal_cost(world, sc.start, sc.goal, sc.profile)
        row["shortest_possible_steps"] = len(shortest_path(world, sc.start, sc.goal)) - 1
        rows.append(row)
        print(f"{sc.name:28s} {res.outcome:8s} steps={res.steps:3d} cost={res.route_cost:3d} "
              f"decisions={res.decisions:4d} plans={res.plans} ties={res.tie_impasses} "
              f"soar={res.soar_seconds * 1000:.0f} ms")

    # A fresh agent per scenario so the three showcase runs are independent.
    # 1 -- normal
    sc = Scenario.load("normal"); world = sc.build_world()
    nav = SoarNavigator(); res = run_episode(nav, sc, world); nav.close()
    viz.plot_route(world, res, sc.start, sc.goal, sc.title, OUT / "scenario_normal.png")
    record(sc, world, res)

    # 2 -- crowded corridors
    sc = Scenario.load("crowded"); world = sc.build_world()
    nav = SoarNavigator(); res = run_episode(nav, sc, world); nav.close()
    viz.plot_route(world, res, sc.start, sc.goal, sc.title, OUT / "scenario_crowded.png")
    viz.animate_route(world, res, sc.start, sc.goal, sc.title, OUT / "scenario_crowded.gif")
    record(sc, world, res)

    # 3 -- accessibility: same trip, three profiles
    base = Scenario.load("accessibility"); world = base.build_world()
    results = []
    for profile in PROFILES:
        sc = base.with_profile(profile)
        nav = SoarNavigator(); res = run_episode(nav, sc, world); nav.close()
        results.append(res)
        record(sc, world, res)
    viz.plot_profile_comparison(world, results, base.start, base.goal, base.title,
                                OUT / "scenario_accessibility.png")

    (OUT / "scenario_results.json").write_text(json.dumps(rows, indent=2))
    cols = ["scenario", "outcome", "steps", "shortest_possible_steps", "route_cost",
            "static_optimal_cost", "crowd_exposure", "collisions", "decisions", "plans",
            "tie_impasses", "obstacles_recorded", "ms_per_step", "ms_per_decision"]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "scenario_results.md").write_text("\n".join(md) + "\n")
    print(f"\nwrote figures and tables to {OUT}/")


if __name__ == "__main__":
    main()
