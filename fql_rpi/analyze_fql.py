"""
FQL vs Rule-Based Comparison Analysis
======================================
Reads logs/comparison.csv and generates:
  1. Time-series plot  : pH, T, NH3, actions over time
  2. Action distribution: bar chart RB vs FQL
  3. Energy comparison  : cumulative energy cost
  4. Reward comparison  : rolling average reward
  5. Summary table      : key metrics side-by-side

Usage:
  python3 analyze_fql.py
  python3 analyze_fql.py --csv logs/comparison.csv --save results/
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV  = os.path.join(BASE_DIR, "logs", "comparison.csv")
ACTION_NAMES = ["OFF", "LOW", "MED", "HIGH"]
ACTION_COST  = [0.0, 0.3, 0.6, 1.0]


# ── Load CSV ─────────────────────────────────────────────────────────────── #

def load_csv(path: str) -> dict:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print(f"[ERROR] No data in {path}")
        sys.exit(1)

    def col(key, dtype=float):
        return np.array([dtype(r[key]) for r in rows])

    return {
        "step":        col("real_step", int),
        "pH":          col("pH"),
        "T":           col("T_C"),
        "NH3":         col("NH3_pct"),
        "mode":        [r["mode"] for r in rows],
        "real_action": col("real_action", int),
        "rb_action":   col("rb_action", int),
        "fql_action":  col("fql_action", int),
        "reward":      col("reward"),
        "rb_reward":   col("rb_reward"),
        "energy_real": col("energy_real"),
        "energy_rb":   col("energy_rb"),
        "energy_fql":  col("energy_fql"),
        "fql_steps":   col("fql_steps", int),
        "epsilon":     col("epsilon"),
        "n":           len(rows),
    }


# ── Split RB vs FQL phases ───────────────────────────────────────────────── #

def split_phases(d: dict):
    rb_mask  = np.array([m == "RB"  for m in d["mode"]])
    fql_mask = np.array([m == "FQL" for m in d["mode"]])
    return rb_mask, fql_mask


# ── Summary statistics ───────────────────────────────────────────────────── #

def summary(d: dict, rb_mask, fql_mask) -> None:
    def stats(label, mask, action_key, reward_key, energy_key):
        if mask.sum() == 0:
            print(f"  {label}: no data")
            return
        actions = d[action_key][mask]
        rewards = d[reward_key][mask]
        nh3     = d["NH3"][mask]
        energy  = d[energy_key][mask]
        ph      = d["pH"][mask]
        t       = d["T"][mask]

        ph_safe = ((ph >= 6.5) & (ph <= 8.5)).mean() * 100
        dist    = {a: (actions == a).mean() * 100 for a in range(4)}

        print(f"\n  ── {label} ({mask.sum()} steps) ──")
        print(f"    Avg reward      : {rewards.mean():+.4f}")
        print(f"    Avg NH3%%        : {nh3.mean():.3f}%%")
        print(f"    NH3 exposure    : {nh3.sum():.1f} (%%-steps, lower=better)")
        print(f"    Avg energy/step : {energy.mean():.3f}")
        print(f"    Total energy    : {energy.sum():.1f}")
        print(f"    %% time SAFE pH  : {ph_safe:.1f}%%")
        print(f"    Action dist     : " +
              "  ".join(f"{ACTION_NAMES[a]}={dist[a]:.1f}%%" for a in range(4)))

    print("\n" + "=" * 60)
    print("  COMPARISON SUMMARY")
    print("=" * 60)
    # RB phase: real_action vs rb_action (should be same during RB mode)
    stats("Rule-Based (actual)", rb_mask,  "real_action", "reward",    "energy_real")
    # FQL phase: real_action = FQL decision; compare with what RB would have done
    stats("FQL (actual)",        fql_mask, "real_action", "reward",    "energy_real")
    stats("RB shadow (in FQL phase)", fql_mask, "rb_action", "rb_reward", "energy_rb")

    if fql_mask.sum() > 0 and rb_mask.sum() > 0:
        rb_r   = d["reward"][rb_mask].mean()
        fql_r  = d["reward"][fql_mask].mean()
        rb_e   = d["energy_real"][rb_mask].mean()
        fql_e  = d["energy_real"][fql_mask].mean()
        rb_nh3 = d["NH3"][rb_mask].mean()
        fql_nh3= d["NH3"][fql_mask].mean()
        print(f"\n  ── Improvement (FQL vs RB) ──")
        print(f"    Reward  : {fql_r:+.4f} vs {rb_r:+.4f}  →  Δ={fql_r-rb_r:+.4f}")
        print(f"    Energy  : {fql_e:.3f} vs {rb_e:.3f}  →  Δ={fql_e-rb_e:+.3f}")
        print(f"    NH3%%    : {fql_nh3:.3f} vs {rb_nh3:.3f}  →  Δ={fql_nh3-rb_nh3:+.3f}")
    print("=" * 60 + "\n")


# ── Plots ────────────────────────────────────────────────────────────────── #

def rolling(arr, w=20):
    return np.convolve(arr, np.ones(w) / w, mode="same")


def plot_all(d: dict, rb_mask, fql_mask, save_dir: str | None = None):
    steps = d["step"]
    rb_start  = steps[rb_mask][0]  if rb_mask.sum()  > 0 else None
    fql_start = steps[fql_mask][0] if fql_mask.sum() > 0 else None

    fig = plt.figure(figsize=(16, 20))
    fig.suptitle("FQL vs Rule-Based — Aquaculture Controller Comparison",
                 fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.45, wspace=0.35)

    def vlines(ax):
        if fql_start is not None:
            ax.axvline(fql_start, color="purple", linestyle="--",
                       linewidth=1.2, alpha=0.7, label="FQL start")

    # ── 1. pH over time ──────────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[0, :])
    ax.plot(steps, d["pH"], color="#2980b9", linewidth=0.7, alpha=0.8)
    ax.axhline(6.5, color="red",    linestyle=":", linewidth=0.8, alpha=0.6)
    ax.axhline(8.5, color="red",    linestyle=":", linewidth=0.8, alpha=0.6)
    ax.fill_between(steps, 6.5, 8.5, alpha=0.06, color="#2ecc71")
    vlines(ax)
    ax.set_ylabel("pH"); ax.set_title("pH over Time"); ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # ── 2. Temperature ───────────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[1, :])
    ax.plot(steps, d["T"], color="#8e44ad", linewidth=0.7, alpha=0.8)
    ax.axhline(30.0, color="#f39c12", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.axhline(35.0, color="red",     linestyle=":", linewidth=0.8, alpha=0.6)
    vlines(ax)
    ax.set_ylabel("Temp (°C)"); ax.set_title("Temperature over Time"); ax.grid(True, alpha=0.3)

    # ── 3. NH3 over time ─────────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[2, :])
    if rb_mask.sum() > 0:
        ax.plot(steps[rb_mask],  d["NH3"][rb_mask],
                color="#e67e22", linewidth=0.8, alpha=0.7, label="RB phase")
    if fql_mask.sum() > 0:
        ax.plot(steps[fql_mask], d["NH3"][fql_mask],
                color="#27ae60", linewidth=0.8, alpha=0.7, label="FQL phase")
    vlines(ax)
    ax.set_ylabel("NH3 fraction (%)"); ax.set_title("NH3 Fraction (lower = safer)")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # ── 4. Rolling average reward ─────────────────────────────────────────── #
    ax = fig.add_subplot(gs[3, 0])
    ax.plot(steps, rolling(d["reward"],   20), color="#2980b9", label="Real (RB+FQL)")
    ax.plot(steps, rolling(d["rb_reward"],20), color="#e74c3c",
            linestyle="--", label="RB shadow")
    vlines(ax)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.set_ylabel("Avg Reward (roll-20)"); ax.set_title("Reward Comparison")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # ── 5. Cumulative energy ──────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[3, 1])
    ax.plot(steps, np.cumsum(d["energy_real"]), color="#2980b9", label="Real")
    ax.plot(steps, np.cumsum(d["energy_rb"]),   color="#e74c3c",
            linestyle="--", label="RB shadow")
    ax.plot(steps, np.cumsum(d["energy_fql"]),  color="#27ae60",
            linestyle=":",  label="FQL greedy")
    vlines(ax)
    ax.set_ylabel("Cumulative Energy"); ax.set_title("Energy Consumption")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # ── 6. Action distribution bar chart ─────────────────────────────────── #
    ax = fig.add_subplot(gs[4, 0])
    x = np.arange(4)
    w = 0.3
    phases = {}
    if rb_mask.sum() > 0:
        phases["Rule-Based"] = [(d["real_action"][rb_mask]  == a).mean()*100 for a in range(4)]
    if fql_mask.sum() > 0:
        phases["FQL"]        = [(d["real_action"][fql_mask] == a).mean()*100 for a in range(4)]
        phases["RB shadow"]  = [(d["rb_action"][fql_mask]   == a).mean()*100 for a in range(4)]

    colors = ["#3498db", "#27ae60", "#e74c3c"]
    for i, (label, vals) in enumerate(phases.items()):
        offset = (i - len(phases)/2 + 0.5) * w
        bars = ax.bar(x + offset, vals, w, label=label, color=colors[i], alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(ACTION_NAMES)
    ax.set_ylabel("Usage (%)"); ax.set_title("Action Distribution")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3, axis="y")

    # ── 7. Epsilon decay ─────────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[4, 1])
    ax.plot(steps, d["epsilon"], color="#9b59b6", linewidth=1.0)
    vlines(ax)
    ax.set_ylabel("Epsilon"); ax.set_title("FQL Exploration Rate (ε)")
    ax.set_ylim(0, 1.05); ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "fql_vs_rb_comparison.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Plot saved: {path}")

    plt.show()


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",  default=DEFAULT_CSV,  help="Path to comparison.csv")
    parser.add_argument("--save", default=None, help="Directory to save plot PNG")
    args = parser.parse_args()

    print(f"Loading: {args.csv}")
    d = load_csv(args.csv)
    print(f"Loaded {d['n']} records  |  "
          f"RB steps: {sum(m=='RB' for m in d['mode'])}  |  "
          f"FQL steps: {sum(m=='FQL' for m in d['mode'])}")

    rb_mask, fql_mask = split_phases(d)
    summary(d, rb_mask, fql_mask)
    plot_all(d, rb_mask, fql_mask, save_dir=args.save)
