"""
Simulation-Based Controller Comparison
=======================================
Thesis : Edge-Intelligent Aquaculture Aerator Control
         Using Progressive Hybrid FQL-DQN with N3IWF LES
Student: Faril Pirwanhadi (M14128104)

Evaluates RB, FQL, and DQN controllers in the SAME virtual environment
(identical scenarios, identical random seeds) for a fair comparison.

No real Pico or serial connection needed — purely simulation.

Usage:
  uv run python3 simulate_compare.py
  uv run python3 simulate_compare.py --episodes 30 --steps 300 --save results/
"""

import argparse
import math
import os
import random

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from pond_simulator import PondSimulator, ScenarioType, SimConfig
from fql_agent     import FQLAgent, ACTION_OFF, ACTION_LOW, ACTION_MED, ACTION_HIGH
from dqn_agent     import DQNAgent

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
QTABLE_FILE    = os.path.join(BASE_DIR, "qtable.json")
DQN_MODEL_FILE = os.path.join(BASE_DIR, "dqn_model.pt")

ACTION_NAMES = ["OFF", "LOW", "MED", "HIGH"]
ACTION_COST  = {ACTION_OFF: 0.0, ACTION_LOW: 0.3, ACTION_MED: 0.6, ACTION_HIGH: 1.0}


# ── Rule-based controller (mirrors Pico firmware) ────────────────────────── #

def rule_based_action(pH: float, T: float) -> int:
    if pH < 6.0 or pH > 9.5 or T > 35.0: return ACTION_HIGH
    if pH < 6.5 or pH > 8.5 or T > 30.0: return ACTION_MED
    return ACTION_LOW


# ── NH3 fraction ─────────────────────────────────────────────────────────── #

def nh3_fraction(pH: float, T: float) -> float:
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))


# ── Reward function (mirrors fql_agent.py compute_reward) ────────────────── #

def compute_reward(pH: float, T: float, action: int,
                   pH_next: float, T_next: float) -> float:
    """
    Imitation/Zone-based reward function.
    Forces the agent to use HIGH in Danger, MED in Warning, and LOW in Safe.
    """
    if action == ACTION_OFF:
        return -100.0

    if 6.5 <= pH <= 8.5 and T <= 30.0:
        energy = {ACTION_LOW: 0.0, ACTION_MED: 0.5, ACTION_HIGH: 1.0}.get(action, 0.0)
        return 1.0 - 0.6 * energy   # LOW=1.0, MED=0.7, HIGH=0.4
    elif pH < 6.0 or pH > 9.5 or T > 34.0 or T < 18.0:
        table = [-100.0, -1.0,  0.5,  1.0]        # HIGH=1.0, MED=0.5, LOW=-1.0
        return table[action]
    else:
        table = [-100.0, -0.3,  0.3,  0.0]        # MED=0.3, HIGH=0.0, LOW=-0.3
        return table[action]


# ── FQL pretrain using virtual simulator ──────────────────────────────────── #

def pretrain_fql(fql: FQLAgent, sim: PondSimulator, steps: int = 30_000) -> None:
    """Train FQL from scratch using virtual simulator before evaluation."""
    from pond_simulator import ScenarioType, SimConfig

    # 50% NORMAL so FQL strongly associates LOW with safe conditions.
    # Stress scenarios teach MED (WARNING) and HIGH (DANGER).
    # Previously 20% NORMAL caused 25% HIGH bleed-through into safe states.
    # Balanced scenarios to ensure agents learn DANGER states frequently
    _SCENARIO_ORDER = [
        ScenarioType.NORMAL,
        ScenarioType.ACID_CRASH,
        ScenarioType.ALKALINE,
        ScenarioType.HEAT_STRESS,
        ScenarioType.HIGH_NH3,
        ScenarioType.COLD_STRESS,
        ScenarioType.MULTI_STRESS,
    ]
    EPISODE_LEN = 200

    scen_idx   = 0
    steps_left = 0
    ph, temp   = 7.5, 27.0
    prev_action = None

    print(f"  Pretraining FQL for {steps:,} virtual steps (episode={EPISODE_LEN}, no NORMAL)...")
    for i in range(steps):
        if steps_left <= 0:
            scenario = _SCENARIO_ORDER[scen_idx % len(_SCENARIO_ORDER)]
            ph, temp = sim.reset(scenario)
            steps_left = EPISODE_LEN
            scen_idx += 1
            prev_action = None

        action      = fql.select_action(ph, temp)
        ph_next, t_next = sim.step(action)
        reward      = fql.compute_reward(ph, temp, action, ph_next, t_next, prev_action)
        fql.update(ph, temp, action, reward, ph_next, t_next)

        prev_action = action
        ph, temp    = ph_next, t_next
        steps_left -= 1

        if (i + 1) % 10_000 == 0:
            stats = fql.get_stats()
            print(f"    step {i+1:6d} | ε={stats['epsilon']:.3f} | "
                  f"AvgR={stats['avg_reward_100']:+.3f} | "
                  f"converged={stats['converged']}")

    fql.epsilon = 0.0  # greedy for evaluation
    print(f"  Pretrain done. Saving Q-table to {QTABLE_FILE}")
    fql.save_qtable(QTABLE_FILE)


# ── DQN virtual training ─────────────────────────────────────────────────── #

def collect_dqn_buffer(fql: FQLAgent, sim: PondSimulator,
                       n_steps: int = 50_000) -> list:
    """Collect transitions using pure random policy so DQN learns from reward signal alone.

    Using random policy (not FQL) prevents the DQN from inheriting any FQL bias —
    DQN learns purely from reward shaping across all action/state combinations.
    """
    # 50% NORMAL so SAFE-zone (LOW=1.0) isn't underrepresented vs stress scenarios.
    # Without this, only 1/7 ≈ 14% of buffer is SAFE zone → MED generalises everywhere.
    # Uniform distribution so DQN learns DANGER heavily
    _BUFFER_SCENARIOS = [
        ScenarioType.NORMAL, ScenarioType.ACID_CRASH,
        ScenarioType.ALKALINE, ScenarioType.HEAT_STRESS,
        ScenarioType.COLD_STRESS, ScenarioType.HIGH_NH3,
        ScenarioType.MULTI_STRESS,
    ]
    _VALID = [ACTION_LOW, ACTION_MED, ACTION_HIGH]

    buffer = []
    scen_idx, steps_left = 0, 0
    ph, temp = 7.5, 27.0

    print(f"  Collecting DQN buffer ({n_steps:,} steps, pure random, 50% NORMAL)...")
    for i in range(n_steps):
        if steps_left <= 0:
            sc = _BUFFER_SCENARIOS[scen_idx % len(_BUFFER_SCENARIOS)]
            ph, temp = sim.reset(sc)
            steps_left = 200
            scen_idx += 1

        action = random.choice(_VALID)           # pure random — no FQL bias
        ph_next, t_next = sim.step(action)
        r = compute_reward(ph, temp, action, ph_next, t_next)

        buffer.append({"s": [ph, temp], "a": action,
                       "r": round(r, 5), "s_next": [ph_next, t_next]})
        ph, temp = ph_next, t_next
        steps_left -= 1

        if (i + 1) % 10_000 == 0:
            print(f"    buffer {i+1:,}/{n_steps:,}")

    return buffer


def train_dqn_virtual(fql: FQLAgent, sim: PondSimulator,
                      save_path: str, epochs: int = 2000):
    """Train DQN from virtual buffer using new reward function."""
    buffer = collect_dqn_buffer(fql, sim, n_steps=50_000)
    print(f"  Training DQN ({epochs} epochs on {len(buffer):,} transitions)...")
    try:
        from train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
        if TORCH_AVAILABLE:
            train_pytorch(buffer, epochs, save_path)
        else:
            train_numpy(buffer, epochs, save_path)
        dqn = DQNAgent()
        if dqn.load(save_path):
            print("  [DQN] Trained and loaded.")
            return dqn
    except Exception as e:
        print(f"  [DQN] Training failed: {e}")
    return None


# ── Single episode evaluation ─────────────────────────────────────────────── #

def run_episode(controller, sim: PondSimulator, scenario: ScenarioType,
                steps: int, seed: int) -> dict:
    """
    Run one episode and return metrics dict.
    controller: callable (pH, T) -> action int
    """
    random.seed(seed)

    ph, temp = sim.reset(scenario)

    rewards, nh3s, energies, actions_taken = [], [], [], []

    for _ in range(steps):
        action         = controller(ph, temp)
        ph_next, t_next = sim.step(action)

        r = compute_reward(ph, temp, action, ph_next, t_next)

        rewards.append(r)
        nh3s.append(nh3_fraction(ph, temp) * 100.0)
        energies.append(ACTION_COST[action])
        actions_taken.append(action)

        ph, temp = ph_next, t_next

    ph_arr = np.array([sim.ph])   # final pH — use step-by-step for full trace
    # Re-run to collect pH trace (already done above, collect inline next pass)
    # Use rewards/nh3 collected above
    n = len(rewards)
    return {
        "avg_reward":    float(np.mean(rewards)),
        "avg_nh3":       float(np.mean(nh3s)),
        "avg_energy":    float(np.mean(energies)),
        "total_energy":  float(np.sum(energies)),
        "action_dist":   [actions_taken.count(a) / n * 100 for a in range(4)],
        "n":             n,
    }


def run_episode_full(controller, sim: PondSimulator, scenario: ScenarioType,
                     steps: int, seed: int) -> dict:
    """Run episode and return full time series for plotting."""
    random.seed(seed)
    ph, temp = sim.reset(scenario)

    phs, temps, nh3s, rewards, energies, actions_taken = [], [], [], [], [], []

    for _ in range(steps):
        action          = controller(ph, temp)
        ph_next, t_next = sim.step(action)
        r = compute_reward(ph, temp, action, ph_next, t_next)

        phs.append(ph); temps.append(temp)
        nh3s.append(nh3_fraction(ph, temp) * 100.0)
        rewards.append(r)
        energies.append(ACTION_COST[action])
        actions_taken.append(action)

        ph, temp = ph_next, t_next

    n = len(rewards)
    ph_arr = np.array(phs)
    return {
        "pH":           np.array(phs),
        "T":            np.array(temps),
        "NH3":          np.array(nh3s),
        "reward":       np.array(rewards),
        "energy":       np.array(energies),
        "actions":      actions_taken,
        "avg_reward":   float(np.mean(rewards)),
        "avg_nh3":      float(np.mean(nh3s)),
        "avg_energy":   float(np.mean(energies)),
        "ph_safe_pct":  float(((ph_arr >= 6.5) & (ph_arr <= 8.5)).mean() * 100),
        "action_dist":  [actions_taken.count(a) / n * 100 for a in range(4)],
        "n":            n,
    }


# ── Aggregate over multiple episodes ──────────────────────────────────────── #

def evaluate(controller, sim: PondSimulator, scenarios: list,
             episodes: int, steps: int, base_seed: int = 42) -> dict:
    """Run multiple episodes across all scenarios, return aggregated metrics."""
    all_rewards, all_nh3, all_energy, all_actions = [], [], [], []
    all_ph_safe = []

    for ep in range(episodes):
        for scen in scenarios:
            seed = base_seed + ep * 100 + scen.value
            res  = run_episode_full(controller, sim, scen, steps, seed)
            all_rewards.append(res["avg_reward"])
            all_nh3.append(res["avg_nh3"])
            all_energy.append(res["avg_energy"])
            all_ph_safe.append(res["ph_safe_pct"])
            all_actions.extend(res["actions"])

    n_total = len(all_actions)
    return {
        "avg_reward":   float(np.mean(all_rewards)),
        "std_reward":   float(np.std(all_rewards)),
        "avg_nh3":      float(np.mean(all_nh3)),
        "avg_energy":   float(np.mean(all_energy)),
        "ph_safe_pct":  float(np.mean(all_ph_safe)),
        "action_dist":  [all_actions.count(a) / n_total * 100 for a in range(4)],
        "n_episodes":   episodes * len(scenarios),
    }


# ── Time-series for plotting (one representative episode per scenario) ─────── #

def collect_timeseries(controller, sim: PondSimulator, scenario: ScenarioType,
                       steps: int, seed: int = 42) -> dict:
    return run_episode_full(controller, sim, scenario, steps, seed)


# ── Print summary table ───────────────────────────────────────────────────── #

def print_summary(results: dict) -> None:
    controllers = list(results.keys())
    print("\n" + "=" * 65)
    print("  SIMULATION COMPARISON  (same virtual environment)")
    print("=" * 65)

    for name, m in results.items():
        print(f"\n  ── {name} ({m['n_episodes']} episodes) ──")
        print(f"    Avg reward      : {m['avg_reward']:+.4f} ± {m['std_reward']:.4f}")
        print(f"    Avg NH3%%        : {m['avg_nh3']:.3f}%%")
        print(f"    Avg energy/step : {m['avg_energy']:.3f}")
        print(f"    %% time SAFE pH  : {m['ph_safe_pct']:.1f}%%")
        print(f"    Action dist     : " +
              "  ".join(f"{ACTION_NAMES[a]}={m['action_dist'][a]:.1f}%%" for a in range(4)))

    # Pairwise deltas
    names = controllers
    if len(names) >= 2:
        rb  = results.get("Rule-Based")
        fql = results.get("FQL")
        dqn = results.get("DQN")

        def delta(a, b, key):
            return a[key] - b[key]

        if rb and fql:
            print(f"\n  ── FQL vs RB ──")
            print(f"    Reward : {fql['avg_reward']:+.4f} vs {rb['avg_reward']:+.4f}  →  Δ={delta(fql,rb,'avg_reward'):+.4f}")
            print(f"    Energy : {fql['avg_energy']:.3f} vs {rb['avg_energy']:.3f}  →  Δ={delta(fql,rb,'avg_energy'):+.3f}")
            print(f"    NH3%%   : {fql['avg_nh3']:.3f} vs {rb['avg_nh3']:.3f}  →  Δ={delta(fql,rb,'avg_nh3'):+.3f}")

        if rb and dqn:
            print(f"\n  ── DQN vs RB ──")
            print(f"    Reward : {dqn['avg_reward']:+.4f} vs {rb['avg_reward']:+.4f}  →  Δ={delta(dqn,rb,'avg_reward'):+.4f}")
            print(f"    Energy : {dqn['avg_energy']:.3f} vs {rb['avg_energy']:.3f}  →  Δ={delta(dqn,rb,'avg_energy'):+.3f}")
            print(f"    NH3%%   : {dqn['avg_nh3']:.3f} vs {rb['avg_nh3']:.3f}  →  Δ={delta(dqn,rb,'avg_nh3'):+.3f}")

        if fql and dqn:
            print(f"\n  ── DQN vs FQL ──")
            print(f"    Reward : {dqn['avg_reward']:+.4f} vs {fql['avg_reward']:+.4f}  →  Δ={delta(dqn,fql,'avg_reward'):+.4f}")
            print(f"    Energy : {dqn['avg_energy']:.3f} vs {fql['avg_energy']:.3f}  →  Δ={delta(dqn,fql,'avg_energy'):+.3f}")
            print(f"    NH3%%   : {dqn['avg_nh3']:.3f} vs {fql['avg_nh3']:.3f}  →  Δ={delta(dqn,fql,'avg_nh3'):+.3f}")

    print("=" * 65 + "\n")


# ── Plots ─────────────────────────────────────────────────────────────────── #

def rolling(arr, w=20):
    return np.convolve(arr, np.ones(w) / w, mode="same")


def plot_comparison(ts_results: dict, save_dir: str | None = None) -> None:
    """
    ts_results: {controller_name: {scenario_label: timeseries_dict}}
    """
    colors = {"Rule-Based": "#e74c3c", "FQL": "#27ae60", "DQN": "#2980b9"}
    scenarios = list(next(iter(ts_results.values())).keys())

    n_scen = len(scenarios)
    fig = plt.figure(figsize=(18, 4 * n_scen))
    fig.suptitle("Simulation Comparison: RB vs FQL vs DQN\n(identical virtual environment)",
                 fontsize=13, fontweight="bold")

    gs = gridspec.GridSpec(n_scen, 3, figure=fig, hspace=0.5, wspace=0.35)

    for row, scen_label in enumerate(scenarios):
        # pH
        ax = fig.add_subplot(gs[row, 0])
        for name, scen_data in ts_results.items():
            d = scen_data[scen_label]
            ax.plot(d["pH"], color=colors[name], linewidth=0.8, alpha=0.85, label=name)
        ax.axhline(6.5, color="red", linestyle=":", linewidth=0.7)
        ax.axhline(8.5, color="red", linestyle=":", linewidth=0.7)
        ax.fill_between(range(len(d["pH"])), 6.5, 8.5, alpha=0.05, color="green")
        ax.set_title(f"{scen_label} — pH"); ax.set_ylabel("pH"); ax.grid(True, alpha=0.3)
        if row == 0: ax.legend(fontsize=7)

        # NH3
        ax = fig.add_subplot(gs[row, 1])
        for name, scen_data in ts_results.items():
            d = scen_data[scen_label]
            ax.plot(d["NH3"], color=colors[name], linewidth=0.8, alpha=0.85, label=name)
        ax.set_title(f"{scen_label} — NH3 (%)"); ax.set_ylabel("NH3 %"); ax.grid(True, alpha=0.3)

        # Cumulative reward
        ax = fig.add_subplot(gs[row, 2])
        for name, scen_data in ts_results.items():
            d = scen_data[scen_label]
            ax.plot(np.cumsum(d["reward"]), color=colors[name], linewidth=0.8,
                    alpha=0.85, label=name)
        ax.set_title(f"{scen_label} — Cumulative Reward")
        ax.set_ylabel("Cum. Reward"); ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "simulation_comparison.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Plot saved: {path}")
    plt.show()


def plot_bar_summary(results: dict, save_dir: str | None = None) -> None:
    """Bar chart summary: reward, energy, NH3, pH safe across all controllers."""
    names   = list(results.keys())
    colors  = ["#e74c3c", "#27ae60", "#2980b9"]
    metrics = {
        "Avg Reward":      [results[n]["avg_reward"]   for n in names],
        "Avg Energy/step": [results[n]["avg_energy"]   for n in names],
        "Avg NH3 %":       [results[n]["avg_nh3"]      for n in names],
        "pH Safe %":       [results[n]["ph_safe_pct"]  for n in names],
    }

    fig, axes = plt.subplots(1, 4, figsize=(16, 5))
    fig.suptitle("Simulation Summary: RB vs FQL vs DQN",
                 fontsize=13, fontweight="bold")

    for ax, (title, vals) in zip(axes, metrics.items()):
        bars = ax.bar(names, vals, color=colors[:len(names)], alpha=0.85, edgecolor="white")
        ax.set_title(title); ax.set_ylabel(title); ax.grid(True, alpha=0.3, axis="y")
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + abs(bar.get_height()) * 0.02,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=9)

    # Action distribution
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    x = np.arange(4)
    w = 0.25
    for i, name in enumerate(names):
        offset = (i - len(names) / 2 + 0.5) * w
        ax2.bar(x + offset, results[name]["action_dist"], w,
                label=name, color=colors[i], alpha=0.85)
    ax2.set_xticks(x); ax2.set_xticklabels(ACTION_NAMES)
    ax2.set_ylabel("Usage (%)"); ax2.set_title("Action Distribution")
    ax2.legend(); ax2.grid(True, alpha=0.3, axis="y")
    fig2.suptitle("Action Distribution: RB vs FQL vs DQN", fontweight="bold")

    plt.tight_layout()

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        p1 = os.path.join(save_dir, "sim_metrics_bar.png")
        p2 = os.path.join(save_dir, "sim_action_dist.png")
        fig.savefig(p1, dpi=150, bbox_inches="tight")
        fig2.savefig(p2, dpi=150, bbox_inches="tight")
        print(f"Plots saved: {p1}, {p2}")
    plt.show()


# ══════════════════════════════════════════════════════════════════════════ #
#  Entry point
# ══════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate RB vs FQL vs DQN comparison")
    parser.add_argument("--episodes", type=int, default=20,
                        help="Episodes per scenario (default 20)")
    parser.add_argument("--steps",    type=int, default=300,
                        help="Steps per episode (default 300)")
    parser.add_argument("--seed",     type=int, default=42,
                        help="Base random seed")
    parser.add_argument("--save",     default=None,
                        help="Directory to save plots (e.g. results/)")
    parser.add_argument("--scenarios", nargs="+",
                        choices=["all", "normal", "acid", "alkaline",
                                 "cold", "heat", "nh3", "multi"],
                        default=["all"],
                        help="Scenarios to test")
    parser.add_argument("--pretrain-steps", type=int, default=80_000,
                        help="Virtual steps to pretrain FQL if no Q-table found (default 80000)")
    parser.add_argument("--retrain-dqn", action="store_true",
                        help="Force retrain DQN from virtual simulator")
    args = parser.parse_args()

    # ── Scenario selection ───────────────────────────────────────────────── #
    _SCEN_MAP = {
        "normal":   ScenarioType.NORMAL,
        "acid":     ScenarioType.ACID_CRASH,
        "alkaline": ScenarioType.ALKALINE,
        "cold":     ScenarioType.COLD_STRESS,
        "heat":     ScenarioType.HEAT_STRESS,
        "nh3":      ScenarioType.HIGH_NH3,
        "multi":    ScenarioType.MULTI_STRESS,
    }
    if "all" in args.scenarios:
        scenarios = list(ScenarioType)
    else:
        scenarios = [_SCEN_MAP[s] for s in args.scenarios]

    print("=" * 65)
    print("  Simulation-Based Controller Evaluation")
    print(f"  Episodes : {args.episodes} per scenario × {len(scenarios)} scenarios")
    print(f"  Steps    : {args.steps} per episode")
    print(f"  Scenarios: {[PondSimulator.label(s) for s in scenarios]}")
    print("=" * 65)

    # ── Load controllers ──────────────────────────────────────────────────── #
    sim = PondSimulator(SimConfig())

    # Rule-Based
    rb_controller = rule_based_action
    print("  [RB]  Rule-Based controller loaded.")

    # FQL — load trained Q-table or pretrain from scratch
    fql = FQLAgent()
    if os.path.exists(QTABLE_FILE) and fql.load_qtable(QTABLE_FILE):
        fql.epsilon = 0.0
        print(f"  [FQL] Q-table loaded: {QTABLE_FILE}  (ε=0, greedy)")
    else:
        print(f"  [FQL] No Q-table found — pretraining from virtual simulator...")
        pretrain_fql(fql, sim, steps=args.pretrain_steps)
    fql_controller = lambda ph, t: fql.select_action(ph, t)

    # DQN — retrain from virtual simulator for fair comparison with new reward
    DQN_VIRTUAL_FILE = os.path.join(BASE_DIR, "dqn_model_virtual.pt")
    dqn = None
    if not args.retrain_dqn and os.path.exists(DQN_VIRTUAL_FILE):
        dqn = DQNAgent()
        if dqn.load(DQN_VIRTUAL_FILE):
            print(f"  [DQN] Virtual model loaded: {DQN_VIRTUAL_FILE}")
        else:
            dqn = None
    if dqn is None:
        print("  [DQN] Training from virtual simulator (new reward function)...")
        dqn = train_dqn_virtual(fql, sim, DQN_VIRTUAL_FILE)
    dqn_controller = (lambda ph, t: dqn.select_action(ph, t)) if dqn else None
    if dqn_controller is None:
        print("  [DQN] Skipped.")

    controllers = {"Rule-Based": rb_controller, "FQL": fql_controller}
    if dqn_controller:
        controllers["DQN"] = dqn_controller

    print()

    # ── Aggregate evaluation ──────────────────────────────────────────────── #
    results = {}
    for name, ctrl in controllers.items():
        print(f"  Evaluating {name}...")
        results[name] = evaluate(ctrl, sim, scenarios,
                                 args.episodes, args.steps, args.seed)
    print()

    print_summary(results)

    # ── Time-series plots — one representative episode per scenario ────────── #
    ts_results = {name: {} for name in controllers}
    for scen in scenarios:
        label = PondSimulator.label(scen)
        for name, ctrl in controllers.items():
            ts_results[name][label] = collect_timeseries(
                ctrl, sim, scen, args.steps, seed=args.seed
            )

    plot_comparison(ts_results, save_dir=args.save)
    plot_bar_summary(results,   save_dir=args.save)
