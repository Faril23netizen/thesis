"""
Extra Thesis Plots
==================
1. FQL Convergence Curve — rolling reward during FQL training phase
2. Policy Map 5x5 — greedy action for each pH x Temperature combination
   for RB, FQL, and DQN controllers

Usage:
  uv run python3 plot_extras.py
  uv run python3 plot_extras.py --save results/
"""

import argparse
import csv
import json
import math
import os

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from fql.fql_agent import FQLAgent, ACTION_OFF, ACTION_LOW, ACTION_MED, ACTION_HIGH
from dqn.dqn_agent import DQNAgent

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QTABLE_FILE    = os.path.join(BASE_DIR, "qtable.json")
DQN_MODEL_FILE = os.path.join(BASE_DIR, "dqn_model.pt")
COMPARISON_CSV = os.path.join(BASE_DIR, "logs", "comparison.csv")

ACTION_NAMES  = ["OFF", "LOW", "MED", "HIGH"]
ACTION_COLORS = ["#95a5a6", "#27ae60", "#f39c12", "#e74c3c"]

# 5x5 grid centers matching FQL rule centers
PH_CENTERS  = [5.75, 6.25, 7.25, 8.25, 9.25]
PH_LABELS   = ["Very\nAcidic\n(5.75)", "Acidic\n(6.25)", "Normal\n(7.25)",
                "Alkaline\n(8.25)", "Very\nAlkaline\n(9.25)"]
T_CENTERS   = [17.75, 21.0, 27.0, 32.5, 34.5]
T_LABELS    = ["Very Cold\n(17.75°C)", "Cold\n(21.0°C)", "Optimal\n(27.0°C)",
               "Hot\n(32.5°C)", "Very Hot\n(34.5°C)"]


# ── Rule-Based controller ─────────────────────────────────────────────────── #

def rule_based_action(pH: float, T: float) -> int:
    if pH < 6.0 or pH > 9.5 or T > 35.0: return ACTION_HIGH
    if pH < 6.5 or pH > 8.5 or T > 30.0: return ACTION_MED
    return ACTION_LOW


# ══════════════════════════════════════════════════════════════════════════ #
#  1. Convergence Curve
# ══════════════════════════════════════════════════════════════════════════ #

def plot_convergence(csv_path: str, save_dir: str | None = None) -> None:
    """Plot rolling average reward during FQL phase from comparison.csv."""

    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ph  = float(row["pH"])
                t   = float(row["T_C"])
                if not (5.5 <= ph <= 9.5 and 17.5 <= t <= 35.0):
                    continue
                rows.append(row)
            except (ValueError, KeyError):
                continue

    if not rows:
        print("[ERROR] No valid data in CSV")
        return

    modes   = [r["mode"]   for r in rows]
    rewards = np.array([float(r["reward"]) for r in rows])
    steps   = np.arange(len(rows))

    rb_mask  = np.array([m == "RB"  for m in modes])
    fql_mask = np.array([m == "FQL" for m in modes])
    dqn_mask = np.array([m == "DQN" for m in modes])

    def rolling(arr, w=50):
        out = np.full_like(arr, np.nan)
        for i in range(len(arr)):
            lo = max(0, i - w + 1)
            out[i] = arr[lo:i+1].mean()
        return out

    roll_all = rolling(rewards, w=50)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle("FQL Learning Convergence — Real Pond Data",
                 fontsize=13, fontweight="bold")

    # ── Top: full reward curve with phase markers ─────────────────────────── #
    ax = axes[0]
    ax.plot(steps, roll_all, color="#2980b9", linewidth=1.2, label="Rolling avg reward (w=50)")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")

    # Phase backgrounds
    if rb_mask.sum() > 0:
        ax.axvspan(steps[rb_mask][0], steps[rb_mask][-1],
                   alpha=0.08, color="#e74c3c", label="RB phase")
    if fql_mask.sum() > 0:
        ax.axvspan(steps[fql_mask][0], steps[fql_mask][-1],
                   alpha=0.08, color="#27ae60", label="FQL phase")
        ax.axvline(steps[fql_mask][0], color="purple", linestyle="--",
                   linewidth=1.2, alpha=0.8, label="FQL start")
    if dqn_mask.sum() > 0:
        ax.axvspan(steps[dqn_mask][0], steps[dqn_mask][-1],
                   alpha=0.08, color="#2980b9", label="DQN phase")
        ax.axvline(steps[dqn_mask][0], color="darkorange", linestyle="-.",
                   linewidth=1.2, alpha=0.8, label="DQN start")

    ax.set_ylabel("Avg Reward (rolling-50)")
    ax.set_xlabel("Real Step")
    ax.set_title("Reward over Time (All Phases)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.3)

    # ── Bottom: FQL phase only — convergence detail ───────────────────────── #
    ax2 = axes[1]
    if fql_mask.sum() > 0:
        fql_rewards = rewards[fql_mask]
        fql_steps   = np.arange(len(fql_rewards))
        roll_fql    = rolling(fql_rewards, w=30)

        ax2.plot(fql_steps, fql_rewards, color="#27ae60",
                 linewidth=0.5, alpha=0.3, label="Raw reward")
        ax2.plot(fql_steps, roll_fql, color="#1a7a4a",
                 linewidth=1.5, label="Rolling avg (w=30)")
        ax2.axhline(0, color="gray", linewidth=0.5, linestyle="--")
        ax2.axhline(fql_rewards.mean(), color="#e74c3c", linewidth=1.0,
                    linestyle=":", label=f"Mean = {fql_rewards.mean():+.3f}")
        ax2.set_ylabel("Reward")
        ax2.set_xlabel("FQL Step (real data only)")
        ax2.set_title("FQL Phase — Convergence Detail")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, "No FQL data available", ha="center", va="center",
                 transform=ax2.transAxes)

    plt.tight_layout()

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "convergence_curve.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
    plt.show()


# ══════════════════════════════════════════════════════════════════════════ #
#  2. Policy Map 5×5
# ══════════════════════════════════════════════════════════════════════════ #

def build_policy_grid(controller) -> np.ndarray:
    """Return 5x5 array of action indices (pH rows × T cols)."""
    grid = np.zeros((5, 5), dtype=int)
    for i, ph in enumerate(PH_CENTERS):
        for j, t in enumerate(T_CENTERS):
            grid[i, j] = controller(ph, t)
    return grid


def plot_policy_map(grids: dict, save_dir: str | None = None) -> None:
    """Plot side-by-side 5×5 policy maps for each controller."""
    n = len(grids)
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 5))
    if n == 1:
        axes = [axes]

    fig.suptitle("Policy Map: Greedy Action for Each pH × Temperature State",
                 fontsize=13, fontweight="bold")

    cmap = plt.cm.colors.ListedColormap(ACTION_COLORS)

    for ax, (name, grid) in zip(axes, grids.items()):
        im = ax.imshow(grid, cmap=cmap, vmin=0, vmax=3, aspect="auto")

        # Cell labels
        for i in range(5):
            for j in range(5):
                action = grid[i, j]
                color  = "white" if action in [2, 3] else "black"
                ax.text(j, i, ACTION_NAMES[action],
                        ha="center", va="center",
                        fontsize=11, fontweight="bold", color=color)

        ax.set_xticks(range(5)); ax.set_xticklabels(T_LABELS, fontsize=7)
        ax.set_yticks(range(5)); ax.set_yticklabels(PH_LABELS, fontsize=7)
        ax.set_xlabel("Temperature"); ax.set_ylabel("pH")
        ax.set_title(name, fontsize=12, fontweight="bold")

    # Legend
    patches = [mpatches.Patch(color=ACTION_COLORS[i], label=ACTION_NAMES[i])
               for i in range(4)]
    fig.legend(handles=patches, loc="lower center", ncol=4,
               fontsize=10, bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "policy_map.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
    plt.show()


def print_policy_table(grids: dict) -> None:
    """Print ASCII policy tables for all controllers."""
    ph_lbl = ["VeryAcid(5.75)", "Acidic  (6.25)", "Normal  (7.25)",
              "Alkaline(8.25)", "VeryAlk (9.25)"]
    t_lbl  = ["VCold(17.75)", "Cold(21.0)", "Opt(27.0)", "Hot(32.5)", "VHot(34.5)"]

    for name, grid in grids.items():
        print(f"\n  {'='*60}")
        print(f"  Policy Map — {name}")
        print(f"  {'='*60}")
        print("  pH \\ T        " + "   ".join(t_lbl))
        print("  " + "-" * 80)
        for i, ph_l in enumerate(ph_lbl):
            row = "   ".join(f"{ACTION_NAMES[grid[i,j]]:4s}" for j in range(5))
            print(f"  {ph_l} : {row}")


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate extra thesis plots")
    parser.add_argument("--save", default=None, help="Directory to save plots")
    parser.add_argument("--csv",  default=COMPARISON_CSV, help="Path to comparison.csv")
    parser.add_argument("--no-convergence", action="store_true")
    parser.add_argument("--no-policy",      action="store_true")
    args = parser.parse_args()

    # ── Load controllers ────────────────────────────────────────────────── #
    fql = FQLAgent()
    if os.path.exists(QTABLE_FILE) and fql.load_qtable(QTABLE_FILE):
        fql.epsilon = 0.0
        print(f"[FQL] Q-table loaded: {QTABLE_FILE}")
    else:
        print(f"[FQL] WARNING: {QTABLE_FILE} not found")

    dqn = DQNAgent()
    if dqn.load(DQN_MODEL_FILE):
        print(f"[DQN] Model loaded: {DQN_MODEL_FILE}")
    else:
        print(f"[DQN] WARNING: {DQN_MODEL_FILE} not found")
        dqn = None

    # ── 1. Convergence Curve ─────────────────────────────────────────────── #
    if not args.no_convergence:
        print("\nGenerating convergence curve...")
        if os.path.exists(args.csv):
            plot_convergence(args.csv, save_dir=args.save)
        else:
            print(f"[ERROR] CSV not found: {args.csv}")

    # ── 2. Policy Map ────────────────────────────────────────────────────── #
    if not args.no_policy:
        print("\nGenerating policy maps...")
        grids = {
            "Rule-Based": build_policy_grid(rule_based_action),
            "FQL":        build_policy_grid(lambda ph, t: fql.select_action(ph, t)),
        }
        if dqn:
            grids["DQN"] = build_policy_grid(lambda ph, t: dqn.select_action(ph, t))

        print_policy_table(grids)
        plot_policy_map(grids, save_dir=args.save)
