#!/usr/bin/env python3
"""Performance evaluation over randomised trials.

    python scripts/evaluate.py [--trials 30] [--seed 2024]

For each of the three scenario families it samples ``--trials`` random
tasks (seeded, therefore reproducible), runs the Soar agent on each and
records success, steps, route cost and decision time.

Reference numbers are computed by plain-Python planners that the agent
never sees (cognav/reference.py):
  * optimal cost  -- only where it is well defined (static worlds);
  * naive baseline -- fewest-steps path that ignores crowds/accessibility
                      and is told about all obstacles in advance.

Outputs (results/): evaluation_trials.csv, evaluation_summary.json,
evaluation_summary.md, evaluation_metrics.png
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cognav import viz  # noqa: E402
from cognav.cost_model import PROFILES, enter_cost  # noqa: E402
from cognav.grid import CrowdPhase, CrowdZone, GridWorld  # noqa: E402
from cognav.reference import optimal_cost, shortest_path  # noqa: E402
from cognav.scenarios import Scenario  # noqa: E402
from cognav.simulation import run_episode  # noqa: E402
from cognav.soar_agent import SoarNavigator  # noqa: E402

MAP = "maps/campus_floor.txt"
OUT = ROOT / "results"
FAMILIES = ("normal", "crowded", "accessibility")


def sample_task(world: GridWorld, rng: random.Random):
    """Random start/goal on ordinary floor, at least 10 steps apart."""
    cells = sorted(p for p, t in world.terrain.items() if t in ("floor", "tactile"))
    while True:
        start, goal = rng.sample(cells, 2)
        if len(shortest_path(world, start, goal)) - 1 >= 10:
            return start, goal


def sample_crowd(world: GridWorld, rng: random.Random):
    """Three crowd phases (from steps 0, 8, 20), three random zones each,
    placed in the circulation area (corridor, lower level)."""
    phases = []
    for from_step in (0, 8, 20):
        zones = []
        for _ in range(3):
            w, h = rng.randint(3, 8), rng.randint(1, 2)
            x0, y0 = rng.randint(1, world.width - 1 - w), rng.randint(5, 11 - h + 1)
            zones.append(CrowdZone(x0, y0, x0 + w - 1, y0 + h - 1, rng.randint(1, 3)))
        phases.append(CrowdPhase(from_step, zones))
    return phases


def sample_obstacles(world: GridWorld, rng: random.Random, start, goal, k=2):
    """k hidden obstacles that do not cut the goal off (resampled otherwise)."""
    cells = sorted(p for p, t in world.terrain.items()
                   if t in ("floor", "tactile", "open") and p not in (start, goal))
    while True:
        obs = rng.sample(cells, k)
        if shortest_path(world, start, goal, blocked=obs) is not None:
            return obs


def make_trial(family: str, i: int, world: GridWorld, rng: random.Random) -> Scenario:
    start, goal = sample_task(world, rng)
    sc = Scenario(name=f"{family}-{i:02d}", title=family, map=MAP, profile="standard",
                  start=start, goal=goal)
    if family == "crowded":
        sc.crowd_phases = sample_crowd(world, rng)
        sc.obstacles = sample_obstacles(world, rng, start, goal)
    elif family == "accessibility":
        sc.profile = PROFILES[i % len(PROFILES)]
    return sc


def baseline(world: GridWorld, sc: Scenario) -> dict:
    """Walk the naive fewest-steps path through the same crowd timeline."""
    world.reset_dynamics()
    world.set_crowd_phases(sc.crowd_phases)
    path = shortest_path(world, sc.start, sc.goal, blocked=sc.obstacles)
    cost = exposure = violations = 0
    for i, cell in enumerate(path[1:]):
        world.update_crowd(i)                       # crowd when move i+1 is made
        c = enter_cost(sc.profile, world.terrain[cell], world.crowd[cell])
        if c is None:
            violations += 1                         # cell this user cannot enter
        else:
            cost += c
        exposure += world.crowd[cell]
    return {"baseline_steps": len(path) - 1, "baseline_cost": cost,
            "baseline_crowd_exposure": exposure, "baseline_violations": violations}


def mean_sd(xs):
    xs = list(xs)
    if not xs:
        return None, None
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else 0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--seed", type=int, default=2024)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    world = GridWorld.from_file(ROOT / MAP)
    trials, summary = [], []
    for f_idx, family in enumerate(FAMILIES):
        rng = random.Random(args.seed + f_idx)
        rows = []
        for i in range(args.trials):
            world.reset_dynamics()
            sc = make_trial(family, i, world, rng)
            nav = SoarNavigator(seed=args.seed + i)     # fresh agent: independent trials
            res = run_episode(nav, sc, world)
            nav.close()
            row = {"family": family, "start": list(sc.start), "goal": list(sc.goal),
                   **res.summary(), **baseline(world, sc)}
            # the optimum is only well defined when the world does not change
            world.reset_dynamics()
            row["optimal_cost"] = (optimal_cost(world, sc.start, sc.goal, sc.profile)
                                   if family != "crowded" else None)
            rows.append(row)
        trials += rows

        ok = [r for r in rows if r["success"]]
        agg = {"label": family, "trials": len(rows),
               "success_rate": len(ok) / len(rows),
               "collisions_total": sum(r["collisions"] for r in rows)}
        for key, col in [("steps", "steps"), ("cost", "route_cost"),
                         ("decisions", "decisions"), ("ms_per_step", "ms_per_step"),
                         ("ms_per_decision", "ms_per_decision"),
                         ("crowd_exposure", "crowd_exposure"), ("plans", "plans"),
                         ("baseline_steps", "baseline_steps"),
                         ("baseline_cost", "baseline_cost"),
                         ("baseline_crowd_exposure", "baseline_crowd_exposure")]:
            m, sd = mean_sd(r[col] for r in ok)
            agg[f"{key}_mean"], agg[f"{key}_sd"] = m, sd
        agg["baseline_trials_with_violations"] = sum(1 for r in rows if r["baseline_violations"])
        with_opt = [r for r in ok if r["optimal_cost"] is not None]
        agg["optimal_trials"] = len(with_opt)
        agg["optimal_matches"] = sum(1 for r in with_opt if r["route_cost"] == r["optimal_cost"])
        summary.append(agg)
        print(f"{family:14s} success {len(ok)}/{len(rows)}  steps {agg['steps_mean']:.1f}  "
              f"cost {agg['cost_mean']:.1f}  ms/step {agg['ms_per_step_mean']:.2f}")

    # ---- write outputs ----
    with open(OUT / "evaluation_trials.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trials[0].keys()))
        w.writeheader(); w.writerows(trials)
    meta = {"trials_per_scenario": args.trials, "seed": args.seed,
            "python": platform.python_version(), "machine": platform.machine(),
            "system": platform.system(),
            "soar": SoarNavigator().kernel.GetSoarKernelVersion()}
    (OUT / "evaluation_summary.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, indent=2))

    def f(v, nd=1):
        return "n/a" if v is None else f"{v:.{nd}f}"

    md = ["| metric | " + " | ".join(a["label"] for a in summary) + " |",
          "|---|" + "---|" * len(summary)]

    def line(name, fn):
        md.append(f"| {name} | " + " | ".join(fn(a) for a in summary) + " |")

    line("trials", lambda a: str(a["trials"]))
    line("success rate", lambda a: f"{100 * a['success_rate']:.0f}%")
    line("steps (mean ± sd)", lambda a: f"{f(a['steps_mean'])} ± {f(a['steps_sd'])}")
    line("route cost (mean ± sd)", lambda a: f"{f(a['cost_mean'])} ± {f(a['cost_sd'])}")
    line("route cost = independent optimum",
         lambda a: f"{a['optimal_matches']}/{a['optimal_trials']}" if a["optimal_trials"]
         else "n/a (dynamic world)")
    line("Soar decision cycles per episode", lambda a: f"{f(a['decisions_mean'])} ± {f(a['decisions_sd'])}")
    line("plan-route subgoals per episode", lambda a: f(a["plans_mean"], 2))
    line("decision time per step, ms", lambda a: f"{f(a['ms_per_step_mean'], 2)} ± {f(a['ms_per_step_sd'], 2)}")
    line("decision time per decision cycle, ms", lambda a: f(a["ms_per_decision_mean"], 3))
    line("collisions (total)", lambda a: str(a["collisions_total"]))
    line("crowd exposure, agent", lambda a: f(a["crowd_exposure_mean"], 2))
    line("crowd exposure, naive baseline", lambda a: f(a["baseline_crowd_exposure_mean"], 2))
    line("steps, naive baseline", lambda a: f(a["baseline_steps_mean"]))
    line("route cost, naive baseline (passable cells only)", lambda a: f(a["baseline_cost_mean"]))
    line("baseline routes entering cells the user cannot use",
         lambda a: f"{a['baseline_trials_with_violations']}/{a['trials']}")
    (OUT / "evaluation_summary.md").write_text("\n".join(md) + "\n")
    viz.plot_metrics(summary, OUT / "evaluation_metrics.png", args.trials)
    print("\n" + "\n".join(md))


if __name__ == "__main__":
    main()
