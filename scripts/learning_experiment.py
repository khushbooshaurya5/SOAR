#!/usr/bin/env python3
"""Does chunking pay off? Same task sequence, learning on vs. off.

    python scripts/learning_experiment.py [--episodes 20] [--seed 7]

ONE agent lives through all episodes (working memory is reset between
episodes with init-soar; learned chunks stay in production memory).
For each episode we count how often Soar hit an operator-tie impasse and
had to open the tie-break subgoal.

Outputs (results/): learning_curve.png, learning_results.json,
learned_chunks.soar (the rules Soar wrote for itself)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cognav import viz  # noqa: E402
from cognav.grid import GridWorld  # noqa: E402
from cognav.scenarios import Scenario  # noqa: E402
from cognav.simulation import run_episode  # noqa: E402
from cognav.soar_agent import SoarNavigator  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import MAP, sample_crowd, sample_task  # noqa: E402

OUT = ROOT / "results"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    world = GridWorld.from_file(ROOT / MAP)
    rng = random.Random(args.seed)
    tasks = []
    for i in range(args.episodes):
        start, goal = sample_task(world, rng)
        # a static crowd picture (phase 0 only) so that all three tie-break
        # criteria get exercised
        tasks.append(Scenario(name=f"ep{i + 1}", title="learning", map=MAP,
                              profile="standard", start=start, goal=goal,
                              crowd_phases=sample_crowd(world, rng)[:1]))

    runs = {}
    for learning in (True, False):
        nav = SoarNavigator(learning=learning, seed=args.seed)
        rows = []
        for sc in tasks:
            r = run_episode(nav, sc, world)
            rows.append({"episode": sc.name, "success": r.success, "steps": r.steps,
                         "route_cost": r.route_cost, "decisions": r.decisions,
                         "tie_impasses": r.tie_impasses, "chunk_firings": r.chunk_firings,
                         "chunks_total": r.chunks_total})
        if learning:
            (OUT / "learned_chunks.soar").write_text(
                "# Rules written by Soar's chunking mechanism during\n"
                "# scripts/learning_experiment.py -- not by a human.\n\n"
                + nav.cli("print --chunks --full"))
        nav.close()
        runs["chunking_on" if learning else "chunking_off"] = rows

    on, off = runs["chunking_on"], runs["chunking_off"]
    totals = {k: {"tie_impasses": sum(r["tie_impasses"] for r in v),
                  "decisions": sum(r["decisions"] for r in v),
                  "route_cost": sum(r["route_cost"] for r in v),
                  "successes": sum(r["success"] for r in v),
                  "chunks_learned": v[-1]["chunks_total"]} for k, v in runs.items()}
    (OUT / "learning_results.json").write_text(
        json.dumps({"episodes": args.episodes, "seed": args.seed,
                    "totals": totals, "runs": runs}, indent=2))
    eps = list(range(1, args.episodes + 1))
    viz.plot_learning(eps, [r["tie_impasses"] for r in on], [r["tie_impasses"] for r in off],
                      "tie impasses (subgoals) in episode",
                      "Chunking removes tie impasses: same 20 tasks, learning on vs. off",
                      OUT / "learning_curve.png")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
