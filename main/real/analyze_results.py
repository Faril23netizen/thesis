"""
RB vs FQL vs DQN Comparison Analysis
======================================
Reads logs/comparison.csv and generates:
  1. Time-series plot  : pH, T, NH3, actions over time
  2. Action distribution: bar chart RB vs FQL vs DQN
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_REAL = os.path.join(BASE_DIR, "results", "hasil_real")

def get_latest_session() -> tuple[str, str]:
    base_csv = os.path.join(RESULTS_REAL, "comparison.csv")
    if not os.path.exists(RESULTS_REAL):
        return base_csv, RESULTS_REAL
        
    sessions = [d for d in os.listdir(RESULTS_REAL) if d.startswith("session_") and os.path.isdir(os.path.join(RESULTS_REAL, d))]
    if not sessions:
        return base_csv, RESULTS_REAL
        
    sessions.sort(reverse=True)
    latest_dir = os.path.join(RESULTS_REAL, sessions[0])
    latest_csv = os.path.join(latest_dir, "comparison.csv")
    
    if os.path.exists(latest_csv):
        return latest_csv, latest_dir
    return base_csv, RESULTS_REAL

DEFAULT_CSV, DEFAULT_SAVE_DIR = get_latest_session()
ACTION_NAMES = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]


# ── Load CSV ─────────────────────────────────────────────────────────────── #

def load_csv(path: str) -> dict:
    rows = []
    skipped = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ph  = float(row["pH"])
                t   = float(row["T_C"])
                nh3 = float(row["NH3_pct"])
                # Filter sensor artifacts and reconnection spikes
                if not (5.5 <= ph <= 9.5 and 17.5 <= t <= 35.0 and 0 <= nh3 <= 100):
                    skipped += 1
                    continue
            except (ValueError, KeyError):
                skipped += 1
                continue
            rows.append(row)

    if skipped > 0:
        print(f"  Filtered {skipped} outlier rows (sensor artifacts/reconnections)")

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
        "fql_steps":   col("fql_steps", int),
        "epsilon":     col("epsilon"),
        "n":           len(rows),
    }


# ── Split RB / FQL / DQN phases ──────────────────────────────────────────── #

def split_phases(d: dict):
    rb_mask  = np.array([m == "RB"  for m in d["mode"]])
    fql_mask = np.array([m == "FQL" for m in d["mode"]])
    dqn_mask = np.array([m == "DQN" for m in d["mode"]])
    return rb_mask, fql_mask, dqn_mask


# ── Summary statistics ───────────────────────────────────────────────────── #

def summary(d: dict, rb_mask, fql_mask, dqn_mask) -> None:
    def stats(label, mask, action_key, reward_key, energy_key):
        if mask.sum() == 0:
            print(f"  {label}: no data")
            return
        actions = d[action_key][mask]
        rewards = d[reward_key][mask]
        nh3     = d["NH3"][mask]
        ph      = d["pH"][mask]

        ph_safe = ((ph >= 6.5) & (ph <= 8.5)).mean() * 100
        dist    = {a: (actions == a).mean() * 100 for a in range(4)}

        print(f"\n  ── {label} ({mask.sum()} steps) ──")
        print(f"    Avg reward      : {rewards.mean():+.4f}")
        print(f"    Avg NH3%%        : {nh3.mean():.3f}%%")
        print(f"    NH3 exposure    : {nh3.sum():.1f} (%%-steps, lower=better)")
        print(f"    %% time SAFE pH  : {ph_safe:.1f}%%")
        print(f"    Action dist     : " +
              "  ".join(f"{ACTION_NAMES[a]}={dist[a]:.1f}%%" for a in range(4)))

    print("\n" + "=" * 60)
    print("  COMPARISON SUMMARY  (RB → FQL → DQN)")
    print("=" * 60)
    stats("Rule-Based (actual)",      rb_mask,  "real_action", "reward")
    stats("FQL (actual)",             fql_mask, "real_action", "reward")
    stats("RB shadow (in FQL phase)", fql_mask, "rb_action",   "rb_reward")
    stats("DQN (actual)",             dqn_mask, "real_action", "reward")

    # pairwise deltas
    def _mean(mask, key): return d[key][mask].mean() if mask.sum() > 0 else None

    rb_r  = _mean(rb_mask,  "reward");       rb_n  = _mean(rb_mask,  "NH3")
    fql_r = _mean(fql_mask, "reward");       fql_n = _mean(fql_mask, "NH3")
    dqn_r = _mean(dqn_mask, "reward");       dqn_n = _mean(dqn_mask, "NH3")

    if rb_r is not None and fql_r is not None:
        print(f"\n  ── FQL vs RB ──")
        print(f"    Reward : {fql_r:+.4f} vs {rb_r:+.4f}  →  Δ={fql_r-rb_r:+.4f}")
        print(f"    NH3%%   : {fql_n:.3f} vs {rb_n:.3f}  →  Δ={fql_n-rb_n:+.3f}")

    if rb_r is not None and dqn_r is not None:
        print(f"\n  ── DQN vs RB ──")
        print(f"    Reward : {dqn_r:+.4f} vs {rb_r:+.4f}  →  Δ={dqn_r-rb_r:+.4f}")
        print(f"    NH3%%   : {dqn_n:.3f} vs {rb_n:.3f}  →  Δ={dqn_n-rb_n:+.3f}")

    if fql_r is not None and dqn_r is not None:
        print(f"\n  ── DQN vs FQL ──")
        print(f"    Reward : {dqn_r:+.4f} vs {fql_r:+.4f}  →  Δ={dqn_r-fql_r:+.4f}")
        print(f"    NH3%%   : {dqn_n:.3f} vs {fql_n:.3f}  →  Δ={dqn_n-fql_n:+.3f}")

    print("=" * 60 + "\n")


# ── Plots ────────────────────────────────────────────────────────────────── #

def rolling(arr, w=20):
    return np.convolve(arr, np.ones(w) / w, mode="same")


def plot_all(d: dict, rb_mask, fql_mask, dqn_mask, save_dir: str | None = None):
    steps = d["step"]
    rb_start  = steps[rb_mask][0]  if rb_mask.sum()  > 0 else None
    fql_start = steps[fql_mask][0] if fql_mask.sum() > 0 else None
    dqn_start = steps[dqn_mask][0] if dqn_mask.sum() > 0 else None

    fig = plt.figure(figsize=(16, 20))
    fig.suptitle("RB → FQL → DQN — Aquaculture Controller Comparison",
                 fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.45, wspace=0.35)

    def vlines(ax):
        if fql_start is not None:
            ax.axvline(fql_start, color="purple", linestyle="--",
                       linewidth=1.2, alpha=0.7, label="FQL start")
        if dqn_start is not None:
            ax.axvline(dqn_start, color="darkorange", linestyle="-.",
                       linewidth=1.2, alpha=0.7, label="DQN start")

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
    if dqn_mask.sum() > 0:
        ax.plot(steps[dqn_mask], d["NH3"][dqn_mask],
                color="darkorange", linewidth=0.8, alpha=0.7, label="DQN phase")
    vlines(ax)
    ax.set_ylabel("NH3 fraction (%)"); ax.set_title("NH3 Fraction (lower = safer)")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # ── 4. Rolling average reward ─────────────────────────────────────────── #
    ax = fig.add_subplot(gs[3, 0])
    ax.plot(steps, rolling(d["reward"],   20), color="#2980b9", label="Real controller")
    ax.plot(steps, rolling(d["rb_reward"],20), color="#e74c3c",
            linestyle="--", label="RB shadow")
    vlines(ax)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.set_ylabel("Avg Reward (roll-20)"); ax.set_title("Reward Comparison")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # ── 5. Action distribution bar chart ─────────────────────────────────── #
    ax = fig.add_subplot(gs[3, 1])
    x = np.arange(4)
    w = 0.22
    phases = {}
    if rb_mask.sum() > 0:
        phases["Rule-Based"] = [(d["real_action"][rb_mask]  == a).mean()*100 for a in range(4)]
    if fql_mask.sum() > 0:
        phases["FQL"]        = [(d["real_action"][fql_mask] == a).mean()*100 for a in range(4)]
    if dqn_mask.sum() > 0:
        phases["DQN"]        = [(d["real_action"][dqn_mask] == a).mean()*100 for a in range(4)]

    colors = ["#3498db", "#27ae60", "darkorange", "#e74c3c"]
    for i, (label, vals) in enumerate(phases.items()):
        offset = (i - len(phases)/2 + 0.5) * w
        ax.bar(x + offset, vals, w, label=label, color=colors[i], alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(ACTION_NAMES)
    ax.set_ylabel("Usage (%)"); ax.set_title("Action Distribution")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3, axis="y")

    # ── 6. Epsilon decay ─────────────────────────────────────────────────── #
    ax = fig.add_subplot(gs[4, :])
    ax.plot(steps, d["epsilon"], color="#9b59b6", linewidth=1.0)
    vlines(ax)
    ax.set_ylabel("Epsilon"); ax.set_title("FQL Exploration Rate (ε)")
    ax.set_ylim(0, 1.05); ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "rb_fql_dqn_comparison.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Plot saved: {path}")

    plt.show()


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",  default=DEFAULT_CSV,  help="Path to comparison.csv")
    parser.add_argument("--save", default=DEFAULT_SAVE_DIR, help="Directory to save plot PNG")
    args = parser.parse_args()

    print(f"Loading: {args.csv}")
    d = load_csv(args.csv)
    rb_n  = sum(m == "RB"  for m in d["mode"])
    fql_n = sum(m == "FQL" for m in d["mode"])
    dqn_n = sum(m == "DQN" for m in d["mode"])
    print(f"Loaded {d['n']} records  |  RB={rb_n}  FQL={fql_n}  DQN={dqn_n}")

    rb_mask, fql_mask, dqn_mask = split_phases(d)
    summary(d, rb_mask, fql_mask, dqn_mask)
    plot_all(d, rb_mask, fql_mask, dqn_mask, save_dir=args.save)
