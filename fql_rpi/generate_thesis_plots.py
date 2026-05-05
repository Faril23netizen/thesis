#!/usr/bin/env python3
"""
Generate comprehensive thesis plots and tables from simulation results.
Run AFTER simulate_compare.py has generated results.

Usage:
    python generate_thesis_plots.py
"""
import os, sys, random, csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── Import from simulate_compare ──────────────────────────────────────────── #
sys.path.insert(0, os.path.dirname(__file__))
from simulate_compare import (
    PondSimulator, SimConfig, ScenarioType, FQLAgent, DQNAgent,
    rule_based_action, compute_reward, nh3_fraction,
    run_episode_full, ACTION_NAMES, ACTION_COST,
    QTABLE_FILE, BASE_DIR,
)

SAVE_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(SAVE_DIR, exist_ok=True)

COLORS = {"Rule-Based": "#e74c3c", "FQL": "#27ae60", "DQN": "#2980b9"}
SCENARIOS = list(ScenarioType)
SCEN_LABELS = {s: PondSimulator.label(s) for s in SCENARIOS}


# ═══════════════════════════════════════════════════════════════════════════ #
#  1. Per-Scenario Evaluation
# ═══════════════════════════════════════════════════════════════════════════ #

def evaluate_per_scenario(controllers, sim, episodes=20, steps=300, seed=42):
    """Returns {ctrl_name: {scenario_label: metrics_dict}}"""
    results = {}
    for name, ctrl in controllers.items():
        results[name] = {}
        for scen in SCENARIOS:
            rews, nh3s, engs, safes, acts = [], [], [], [], []
            for ep in range(episodes):
                s = seed + ep * 100 + scen.value
                res = run_episode_full(ctrl, sim, scen, steps, s)
                rews.append(res["avg_reward"])
                nh3s.append(res["avg_nh3"])
                engs.append(res["avg_energy"])
                safes.append(res["ph_safe_pct"])
                acts.extend(res["actions"])
            n = len(acts)
            results[name][SCEN_LABELS[scen]] = {
                "avg_reward": np.mean(rews), "std_reward": np.std(rews),
                "rewards": rews,
                "avg_nh3": np.mean(nh3s), "avg_energy": np.mean(engs),
                "ph_safe_pct": np.mean(safes),
                "action_dist": [acts.count(a)/n*100 for a in range(4)],
            }
    return results


# ═══════════════════════════════════════════════════════════════════════════ #
#  2. CSV Export — Per-Scenario Table
# ═══════════════════════════════════════════════════════════════════════════ #

def export_csv(per_scen, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Scenario", "Controller", "Avg Reward", "Std Reward",
                     "Avg NH3 %", "Avg Energy", "pH Safe %",
                     "OFF %", "LOW %", "MED %", "HIGH %"])
        for ctrl in per_scen:
            for scen, m in per_scen[ctrl].items():
                w.writerow([scen, ctrl,
                            f"{m['avg_reward']:.4f}", f"{m['std_reward']:.4f}",
                            f"{m['avg_nh3']:.3f}", f"{m['avg_energy']:.3f}",
                            f"{m['ph_safe_pct']:.1f}",
                            *[f"{m['action_dist'][a]:.1f}" for a in range(4)]])
    print(f"  CSV saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════ #
#  3. Box Plot — Reward Distribution per Scenario
# ═══════════════════════════════════════════════════════════════════════════ #

def plot_boxplot(per_scen, save_dir):
    ctrls = list(per_scen.keys())
    scens = list(SCEN_LABELS.values())
    fig, axes = plt.subplots(1, len(scens), figsize=(3.5*len(scens), 5), sharey=True)
    fig.suptitle("Reward Distribution per Scenario", fontsize=14, fontweight="bold")

    for i, scen in enumerate(scens):
        ax = axes[i]
        data = [per_scen[c][scen]["rewards"] for c in ctrls]
        bp = ax.boxplot(data, labels=ctrls, patch_artist=True, widths=0.6)
        for patch, c in zip(bp["boxes"], ctrls):
            patch.set_facecolor(COLORS[c])
            patch.set_alpha(0.7)
        ax.set_title(scen, fontsize=9)
        ax.grid(True, alpha=0.3, axis="y")
        ax.axhline(0, color="gray", ls="--", lw=0.5)
        if i == 0:
            ax.set_ylabel("Avg Reward")

    plt.tight_layout()
    p = os.path.join(save_dir, "boxplot_reward_per_scenario.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  4. Grouped Bar — Per-Scenario Metrics
# ═══════════════════════════════════════════════════════════════════════════ #

def plot_per_scenario_bars(per_scen, save_dir):
    ctrls = list(per_scen.keys())
    scens = list(SCEN_LABELS.values())
    metrics = [
        ("Avg Reward", "avg_reward"),
        ("pH Safe %", "ph_safe_pct"),
        ("Avg Energy", "avg_energy"),
        ("NH3 %", "avg_nh3"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("Per-Scenario Performance Breakdown", fontsize=14, fontweight="bold")

    for ax, (title, key) in zip(axes.flat, metrics):
        x = np.arange(len(scens))
        w = 0.25
        for j, c in enumerate(ctrls):
            vals = [per_scen[c][s][key] for s in scens]
            offset = (j - len(ctrls)/2 + 0.5) * w
            ax.bar(x + offset, vals, w, label=c, color=COLORS[c], alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(scens, rotation=30, ha="right", fontsize=8)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    p = os.path.join(save_dir, "per_scenario_bars.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  5. Radar / Spider Chart
# ═══════════════════════════════════════════════════════════════════════════ #

def plot_radar(agg_results, save_dir):
    """Radar chart comparing controllers across 4 normalized metrics."""
    ctrls = list(agg_results.keys())
    labels = ["Reward", "Energy\nEfficiency", "NH3\nReduction", "pH Safety"]

    # Normalize: higher = better (invert energy & nh3)
    raw = {}
    for c in ctrls:
        m = agg_results[c]
        raw[c] = [m["avg_reward"],
                  1.0 - m["avg_energy"],   # lower energy = better
                  1.0 - m["avg_nh3"]/100,  # lower nh3 = better
                  m["ph_safe_pct"]/100]

    # Min-max scale across controllers
    n_met = len(labels)
    mins = [min(raw[c][i] for c in ctrls) for i in range(n_met)]
    maxs = [max(raw[c][i] for c in ctrls) for i in range(n_met)]
    scaled = {}
    for c in ctrls:
        scaled[c] = []
        for i in range(n_met):
            rng = maxs[i] - mins[i]
            scaled[c].append((raw[c][i] - mins[i]) / rng if rng > 0 else 0.5)

    angles = np.linspace(0, 2*np.pi, n_met, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    ax.set_title("Multi-Metric Comparison (Radar Chart)", fontsize=13,
                 fontweight="bold", pad=20)

    for c in ctrls:
        vals = scaled[c] + scaled[c][:1]
        ax.plot(angles, vals, "o-", linewidth=2, label=c, color=COLORS[c])
        ax.fill(angles, vals, alpha=0.15, color=COLORS[c])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    ax.grid(True)

    p = os.path.join(save_dir, "radar_comparison.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  6. Zone Distribution (% SAFE / WARNING / DANGER)
# ═══════════════════════════════════════════════════════════════════════════ #

def classify_zone(ph, t):
    if 6.5 <= ph <= 8.5 and t <= 30.0:
        return "SAFE"
    elif ph < 6.0 or ph > 9.5 or t > 34.0 or t < 18.0:
        return "DANGER"
    return "WARNING"


def compute_zone_dist(controllers, sim, episodes=20, steps=300, seed=42):
    """Compute % time in each zone for each controller."""
    zone_data = {}
    for name, ctrl in controllers.items():
        zones = {"SAFE": 0, "WARNING": 0, "DANGER": 0}
        total = 0
        for ep in range(episodes):
            for scen in SCENARIOS:
                s = seed + ep * 100 + scen.value
                res = run_episode_full(ctrl, sim, scen, steps, s)
                for ph, t in zip(res["pH"], res["T"]):
                    zones[classify_zone(ph, t)] += 1
                    total += 1
        zone_data[name] = {k: v/total*100 for k, v in zones.items()}
    return zone_data


def plot_zone_dist(zone_data, save_dir):
    ctrls = list(zone_data.keys())
    zones = ["SAFE", "WARNING", "DANGER"]
    zcolors = {"SAFE": "#2ecc71", "WARNING": "#f39c12", "DANGER": "#e74c3c"}

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.suptitle("Time in Each Zone (%)", fontsize=13, fontweight="bold")
    x = np.arange(len(ctrls))
    bottom = np.zeros(len(ctrls))

    for z in zones:
        vals = [zone_data[c][z] for c in ctrls]
        ax.bar(x, vals, bottom=bottom, label=z, color=zcolors[z], alpha=0.85,
               edgecolor="white", linewidth=0.5)
        for i, v in enumerate(vals):
            if v > 3:
                ax.text(i, bottom[i] + v/2, f"{v:.1f}%", ha="center",
                        va="center", fontsize=10, fontweight="bold")
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(ctrls, fontsize=11)
    ax.set_ylabel("Percentage (%)")
    ax.legend()
    ax.set_ylim(0, 105)

    p = os.path.join(save_dir, "zone_distribution.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  7. Temperature Time Series (currently missing)
# ═══════════════════════════════════════════════════════════════════════════ #

def plot_temperature_ts(controllers, sim, save_dir, steps=300, seed=42):
    """Plot temperature time series for Heat Stress & Cold Stress."""
    stress_scens = [ScenarioType.HEAT_STRESS, ScenarioType.COLD_STRESS]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Temperature Response Under Stress", fontsize=13, fontweight="bold")

    for ax, scen in zip(axes, stress_scens):
        for name, ctrl in controllers.items():
            res = run_episode_full(ctrl, sim, scen, steps, seed)
            ax.plot(res["T"], color=COLORS[name], linewidth=1, alpha=0.85, label=name)
        ax.axhline(30.0, color="orange", ls=":", lw=1, label="Warning (30°C)")
        ax.axhline(34.0, color="red", ls=":", lw=1, label="Danger (34°C)")
        ax.set_title(SCEN_LABELS[scen])
        ax.set_xlabel("Step")
        ax.set_ylabel("Temperature (°C)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    p = os.path.join(save_dir, "temperature_timeseries.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  8. Action Timeline (per-step action for one episode)
# ═══════════════════════════════════════════════════════════════════════════ #

def plot_action_timeline(controllers, sim, save_dir, steps=300, seed=42):
    """Show what action each controller takes at each step for key scenarios."""
    key_scens = [ScenarioType.NORMAL, ScenarioType.ACID_CRASH,
                 ScenarioType.ALKALINE, ScenarioType.HIGH_NH3]
    act_colors = {0: "#95a5a6", 1: "#3498db", 2: "#f39c12", 3: "#e74c3c"}
    act_labels = {0: "OFF", 1: "LOW", 2: "MED", 3: "HIGH"}
    ctrls = list(controllers.keys())

    fig, axes = plt.subplots(len(key_scens), len(ctrls),
                             figsize=(5*len(ctrls), 2.5*len(key_scens)),
                             sharex=True)
    fig.suptitle("Action Timeline per Step", fontsize=13, fontweight="bold")

    for row, scen in enumerate(key_scens):
        for col, name in enumerate(ctrls):
            ax = axes[row][col] if len(key_scens) > 1 else axes[col]
            res = run_episode_full(controllers[name], sim, scen, steps, seed)
            acts = res["actions"]
            for i, a in enumerate(acts):
                ax.bar(i, 1, color=act_colors[a], width=1.0)
            ax.set_yticks([])
            if row == 0:
                ax.set_title(name, fontsize=10)
            if col == 0:
                ax.set_ylabel(SCEN_LABELS[scen], fontsize=8)
            ax.set_xlim(0, steps)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=act_colors[a], label=act_labels[a]) for a in [1,2,3]]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3, fontsize=9)

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    p = os.path.join(save_dir, "action_timeline.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    print(f"  Plot saved: {p}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════ #
#  9. Summary Table (LaTeX-ready)
# ═══════════════════════════════════════════════════════════════════════════ #

def export_latex_table(agg, path):
    with open(path, "w") as f:
        f.write("\\begin{table}[h]\n\\centering\n")
        f.write("\\caption{Simulation Comparison Results}\n")
        f.write("\\label{tab:sim_comparison}\n")
        f.write("\\begin{tabular}{lcccc}\n\\hline\n")
        f.write("Controller & Avg Reward & Energy/step & NH3 (\\%) & pH Safe (\\%) \\\\\n")
        f.write("\\hline\n")
        for name, m in agg.items():
            f.write(f"{name} & {m['avg_reward']:+.4f} $\\pm$ {m['std_reward']:.4f} "
                    f"& {m['avg_energy']:.3f} & {m['avg_nh3']:.3f} "
                    f"& {m['ph_safe_pct']:.1f} \\\\\n")
        f.write("\\hline\n\\end{tabular}\n\\end{table}\n")
    print(f"  LaTeX table saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════ #
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    print("=" * 65)
    print("  Generating Thesis Plots & Tables")
    print("=" * 65)

    sim = PondSimulator(SimConfig())

    # Load controllers
    rb_ctrl = rule_based_action
    fql = FQLAgent()
    if not (os.path.exists(QTABLE_FILE) and fql.load_qtable(QTABLE_FILE)):
        print("ERROR: No Q-table found. Run simulate_compare.py first.")
        sys.exit(1)
    fql.epsilon = 0.0
    fql_ctrl = lambda ph, t: fql.select_action(ph, t)

    dqn = DQNAgent()
    dqn_path = os.path.join(BASE_DIR, "dqn_model_virtual.pt")
    if not dqn.load(dqn_path):
        print("ERROR: No DQN model found. Run simulate_compare.py --retrain-dqn first.")
        sys.exit(1)
    dqn_ctrl = lambda ph, t: dqn.select_action(ph, t)

    controllers = {"Rule-Based": rb_ctrl, "FQL": fql_ctrl, "DQN": dqn_ctrl}

    # ── Aggregate evaluation ──
    from simulate_compare import evaluate
    print("\n  Running aggregate evaluation (140 episodes)...")
    agg = {}
    for name, ctrl in controllers.items():
        agg[name] = evaluate(ctrl, sim, SCENARIOS, 20, 300, 42)

    # ── Per-scenario evaluation ──
    print("  Running per-scenario evaluation...")
    per_scen = evaluate_per_scenario(controllers, sim)

    # ── Generate all outputs ──
    print("\n  Generating outputs...\n")

    # 1. CSV table
    export_csv(per_scen, os.path.join(SAVE_DIR, "per_scenario_results.csv"))

    # 2. LaTeX table
    export_latex_table(agg, os.path.join(SAVE_DIR, "latex_table.tex"))

    # 3. Box plot
    plot_boxplot(per_scen, SAVE_DIR)

    # 4. Per-scenario grouped bars
    plot_per_scenario_bars(per_scen, SAVE_DIR)

    # 5. Radar chart
    plot_radar(agg, SAVE_DIR)

    # 6. Zone distribution
    print("  Computing zone distributions...")
    zone_data = compute_zone_dist(controllers, sim)
    plot_zone_dist(zone_data, SAVE_DIR)

    # 7. Temperature time series
    plot_temperature_ts(controllers, sim, SAVE_DIR)

    # 8. Action timeline
    plot_action_timeline(controllers, sim, SAVE_DIR)

    print("\n" + "=" * 65)
    print(f"  All outputs saved to: {SAVE_DIR}/")
    print("  Files generated:")
    print("    - per_scenario_results.csv      (data table)")
    print("    - latex_table.tex                (LaTeX ready)")
    print("    - boxplot_reward_per_scenario.png")
    print("    - per_scenario_bars.png")
    print("    - radar_comparison.png")
    print("    - zone_distribution.png")
    print("    - temperature_timeseries.png")
    print("    - action_timeline.png")
    print("=" * 65)
