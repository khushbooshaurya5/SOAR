"""Visualisations (matplotlib): route maps, animations and metric charts."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from .grid import GridWorld, Pos
from .simulation import EpisodeResult

# -- palette (roles) ----------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
WALL = "#3d3d3a"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # categorical slots 1-3
CROWD = {1: "#fbd9c9", 2: "#f4a582", 3: "#d95926"}   # one-hue ordinal ramp (orange)
OBSTACLE = "#d03b3b"
TERRAIN_FILL = {
    "floor": "#ffffff", "tactile": "#f3efdc", "open": "#eaf1f7", "door": "#e9e4dc",
    "autodoor": "#e9e4dc", "ramp": "#e3efe6", "stairs": "#ece6f3", "narrow": "#f0eeee",
}
TERRAIN_GLYPH = {"tactile": "·", "door": "D", "autodoor": "A", "ramp": "R",
                 "stairs": "S", "narrow": "N"}
TERRAIN_LABEL = {
    "S": "stairs", "R": "ramp", "N": "narrow passage", "D": "manual door",
    "A": "automatic door",
}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "text.color": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def draw_map(ax, world: GridWorld, crowd: Optional[Dict[Pos, int]] = None,
             obstacles: Sequence[Pos] = ()) -> None:
    ax.add_patch(Rectangle((-0.5, -0.5), world.width, world.height, color=WALL, zorder=0))
    for (x, y), terrain in world.terrain.items():
        level = crowd.get((x, y), 0) if crowd else 0
        fill = CROWD[level] if level else TERRAIN_FILL[terrain]
        ax.add_patch(Rectangle((x - 0.5, y - 0.5), 1, 1, facecolor=fill,
                               edgecolor=GRID, linewidth=0.4, zorder=1))
        glyph = TERRAIN_GLYPH.get(terrain)
        if glyph:
            ax.text(x, y, glyph, ha="center", va="center", fontsize=7,
                    color=INK_2, zorder=2)
        if level:  # crowd level is also written, never colour alone
            ax.text(x + 0.32, y - 0.28, str(level), ha="center", va="center",
                    fontsize=5, color=INK, zorder=2)
    for (x, y) in obstacles:
        ax.add_patch(Rectangle((x - 0.5, y - 0.5), 1, 1, facecolor=OBSTACLE,
                               edgecolor=SURFACE, linewidth=1, zorder=3))
        ax.text(x, y, "✕", ha="center", va="center", fontsize=9, color="white", zorder=4)
    ax.set_xlim(-0.5, world.width - 0.5)
    ax.set_ylim(world.height - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def draw_path(ax, path: Sequence[Pos], color=SERIES[0], offset=0.0, label=None,
              upto: Optional[int] = None) -> None:
    pts = path if upto is None else path[: upto + 1]
    xs = [p[0] + offset for p in pts]
    ys = [p[1] + offset for p in pts]
    ax.plot(xs, ys, color=SURFACE, linewidth=4.5, solid_capstyle="round", zorder=5)
    ax.plot(xs, ys, color=color, linewidth=2, solid_capstyle="round", zorder=6, label=label)


def draw_endpoints(ax, start: Pos, goal: Pos, agent: Optional[Pos] = None) -> None:
    ax.scatter(*start, s=70, marker="o", facecolor=SURFACE, edgecolor=INK, linewidth=1.5, zorder=8)
    ax.scatter(*goal, s=130, marker="*", facecolor=INK, edgecolor=SURFACE, linewidth=1, zorder=8)
    ax.annotate("start", start, xytext=(0, -9), textcoords="offset points",
                ha="center", fontsize=7, color=INK, zorder=9)
    ax.annotate("goal", goal, xytext=(0, 11), textcoords="offset points",
                ha="center", fontsize=7, color=INK, zorder=9)
    if agent is not None:
        ax.scatter(*agent, s=60, marker="o", facecolor=SERIES[0], edgecolor=SURFACE,
                   linewidth=1.5, zorder=9)


def _legend(fig, extra=(), crowd=False):
    handles = list(extra)
    handles += [Line2D([], [], marker=f"${g}$", color=INK_2, linestyle="none",
                       markersize=6, label=l) for g, l in TERRAIN_LABEL.items()]
    handles += [Patch(facecolor=TERRAIN_FILL["tactile"], edgecolor=GRID, label="tactile paving"),
                Patch(facecolor=TERRAIN_FILL["open"], edgecolor=GRID, label="open atrium")]
    if crowd:
        handles += [Patch(facecolor=CROWD[k], edgecolor=GRID, label=f"crowd level {k}")
                    for k in (1, 2, 3)]
        handles.append(Patch(facecolor=OBSTACLE, label="obstacle (discovered)"))
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=7)


def plot_route(world: GridWorld, result: EpisodeResult, start: Pos, goal: Pos,
               title: str, path_out: str) -> None:
    """One panel per crowd phase (a single panel if the crowd never changes)."""
    n_snap = len(result.crowd_snapshots)
    # last step index that belongs to each snapshot
    ends = [max(i for i, s in enumerate(result.crowd_by_step) if s == k) for k in range(n_snap)]
    fig, axes = plt.subplots(1, n_snap, figsize=(6.2 * n_snap, 4.6), squeeze=False)
    for k, ax in enumerate(axes[0]):
        step = ends[k]
        draw_map(ax, world, result.crowd_snapshots[k], result.discovered_by_step[step])
        draw_path(ax, result.path, upto=step)
        draw_endpoints(ax, start, goal, agent=result.path[step] if k < n_snap - 1 else None)
        if n_snap > 1:
            first = 0 if k == 0 else ends[k - 1] + 1
            ax.set_title(f"crowd phase {k + 1}: steps {first}–{step}", fontsize=9,
                         color=INK_2, loc="left")
    has_crowd = any(any(s.values()) for s in result.crowd_snapshots)
    fig.suptitle(
        f"{title}\n{result.profile} user · {result.outcome} · {result.steps} steps · "
        f"route cost {result.route_cost} · {result.decisions} Soar decisions",
        fontsize=10, x=0.02, ha="left")
    _legend(fig, [Line2D([], [], color=SERIES[0], linewidth=2, label="route walked")],
            crowd=has_crowd or bool(result.discovered_by_step[-1]))
    fig.tight_layout(rect=(0, 0.08, 1, 0.93))
    fig.savefig(path_out, dpi=160)
    plt.close(fig)


def plot_profile_comparison(world: GridWorld, results: List[EpisodeResult], start: Pos,
                            goal: Pos, title: str, path_out: str) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    draw_map(ax, world)
    offsets = [-0.16, 0.0, 0.16]
    handles = []
    for r, color, off in zip(results, SERIES, offsets):
        draw_path(ax, r.path, color=color, offset=off)
        handles.append(Line2D([], [], color=color, linewidth=2,
                              label=f"{r.profile}: {r.steps} steps, cost {r.route_cost}"))
    draw_endpoints(ax, start, goal)
    fig.suptitle(title, fontsize=10, x=0.02, ha="left")
    _legend(fig, handles)
    fig.tight_layout(rect=(0, 0.1, 1, 0.96))
    fig.savefig(path_out, dpi=160)
    plt.close(fig)


def animate_route(world: GridWorld, result: EpisodeResult, start: Pos, goal: Pos,
                  title: str, path_out: str, fps: int = 5) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 4.9))

    def frame(i):
        ax.clear()
        draw_map(ax, world, result.crowd_snapshots[result.crowd_by_step[i]],
                 result.discovered_by_step[i])
        draw_path(ax, result.path, upto=i)
        draw_endpoints(ax, start, goal, agent=result.path[i])
        ax.set_title(f"{title} — step {i}/{len(result.path) - 1}", fontsize=9, loc="left")

    frames = list(range(len(result.path))) + [len(result.path) - 1] * fps
    anim = animation.FuncAnimation(fig, frame, frames=frames)
    anim.save(path_out, writer=animation.PillowWriter(fps=fps), dpi=80)
    plt.close(fig)


def _bars(ax, labels, values, title, fmt="{:.1f}", errors=None):
    xs = range(len(labels))
    ax.bar(xs, values, width=0.55, color=SERIES[0], zorder=3)
    if errors is not None:
        ax.errorbar(xs, values, yerr=errors, fmt="none", ecolor=INK_2, elinewidth=1,
                    capsize=3, zorder=4)
    top = max([v + (e or 0) for v, e in zip(values, errors or [0] * len(values))] + [1e-9])
    for x, v, e in zip(xs, values, errors or [0] * len(values)):
        ax.text(x, v + (e or 0) + top * 0.03, fmt.format(v), ha="center", fontsize=8, color=INK)
    ax.set_xticks(list(xs)); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, top * 1.18)
    ax.set_title(title, fontsize=9, loc="left", color=INK)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


def plot_metrics(rows: List[dict], path_out: str, n_trials: int) -> None:
    """``rows``: one aggregated dict per scenario (see scripts/evaluate.py)."""
    labels = [r["label"] for r in rows]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4))
    _bars(axes[0], labels, [100 * r["success_rate"] for r in rows], "Success rate (%)", "{:.0f}")
    _bars(axes[1], labels, [r["steps_mean"] for r in rows], "Steps per episode (mean ± sd)",
          errors=[r["steps_sd"] for r in rows])
    _bars(axes[2], labels, [r["cost_mean"] for r in rows], "Route cost (mean ± sd)",
          errors=[r["cost_sd"] for r in rows])
    _bars(axes[3], labels, [r["ms_per_step_mean"] for r in rows],
          "Soar decision time per step (ms, mean ± sd)", "{:.1f}",
          errors=[r["ms_per_step_sd"] for r in rows])
    fig.suptitle(f"Soar navigation agent — {n_trials} randomised trials per scenario",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path_out, dpi=160)
    plt.close(fig)


def plot_learning(episodes: List[int], with_chunking: List[float], without: List[float],
                  ylabel: str, title: str, path_out: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(episodes, without, color=SERIES[1], linewidth=2, marker="o", markersize=4,
            label="chunking off")
    ax.plot(episodes, with_chunking, color=SERIES[0], linewidth=2, marker="o", markersize=4,
            label="chunking on")
    ax.annotate("chunking off", (episodes[-1], without[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=8, color=INK)
    ax.annotate("chunking on", (episodes[-1], with_chunking[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=8, color=INK)
    ax.set_xlabel("episode"); ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10, loc="left")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlim(episodes[0] - 0.5, episodes[-1] + 0.12 * len(episodes) + 1)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path_out, dpi=160)
    plt.close(fig)
