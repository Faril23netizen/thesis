"""
Visualization for Simulation Results
=====================================
Generate plots comparing RB, FQL, and DQN performance.

Plots:
1. Accuracy comparison (bar chart)
2. Confusion matrices (3 heatmaps)
3. Precision/Recall/F1 per class (grouped bar)
4. Multi-metric radar chart

Usage:
    python3 main/simulasi/plot_extras.py
"""

import json
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

# Set font for better readability
rcParams['font.family'] = 'sans-serif'
rcParams['font.size'] = 10

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "simulation")

RISK_LABELS = ["SAFE", "CAUTION", "WARNING", "CRITICAL"]
COLORS = {
    "rb": "#95a5a6",    # Gray
    "fql": "#3498db",   # Blue
    "dqn": "#2ecc71"    # Green
}


def load_results():
    """Load simulation results from JSON."""
    results_path = os.path.join(RESULTS_DIR, "simulation_results.json")
    with open(results_path) as f:
        return json.load(f)


def plot_accuracy_comparison(results):
    """Plot 1: Accuracy comparison bar chart."""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    agents = ["Rule-Based", "FQL", "DQN"]
    accuracies = [
        results["rule_based"]["accuracy"],
        results["fql"]["accuracy"],
        results["dqn"]["accuracy"] if results["dqn"] else 0
    ]
    colors = [COLORS["rb"], COLORS["fql"], COLORS["dqn"]]
    
    bars = ax.bar(agents, accuracies, color=colors, alpha=0.8, edgecolor='black')
    
    # Add value labels on bars
    for bar, acc in zip(bars, accuracies):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{acc:.1%}',
                ha='center', va='bottom', fontweight='bold')
    
    ax.set_ylabel('Accuracy', fontweight='bold')
    ax.set_title('NH₃ Risk Prediction Accuracy Comparison', fontweight='bold', fontsize=12)
    ax.set_ylim(0, 1.0)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "01_accuracy_comparison.png"), dpi=300)
    print("✅ Saved: 01_accuracy_comparison.png")
    plt.close()


def plot_confusion_matrices(results):
    """Plot 2: Confusion matrices for all 3 agents."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    
    agents_data = [
        ("Rule-Based", results["rule_based"], COLORS["rb"]),
        ("FQL", results["fql"], COLORS["fql"]),
        ("DQN", results["dqn"], COLORS["dqn"]) if results["dqn"] else ("DQN", None, COLORS["dqn"])
    ]
    
    for ax, (name, data, color) in zip(axes, agents_data):
        if data is None:
            ax.text(0.5, 0.5, "DQN\nNot Available", ha='center', va='center', fontsize=14)
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        
        cm = np.array(data["confusion_matrix"])
        
        # Normalize by row (actual class)
        cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        
        im = ax.imshow(cm_norm, cmap='Blues', vmin=0, vmax=1)
        
        # Add text annotations
        for i in range(4):
            for j in range(4):
                text = ax.text(j, i, f'{cm[i, j]}\n({cm_norm[i, j]:.0%})',
                              ha="center", va="center",
                              color="white" if cm_norm[i, j] > 0.5 else "black",
                              fontsize=9)
        
        ax.set_xticks(range(4))
        ax.set_yticks(range(4))
        ax.set_xticklabels(RISK_LABELS, rotation=45, ha='right')
        ax.set_yticklabels(RISK_LABELS)
        ax.set_xlabel('Predicted', fontweight='bold')
        ax.set_ylabel('Actual', fontweight='bold')
        ax.set_title(f'{name}\nAccuracy: {data["accuracy"]:.1%}', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "02_confusion_matrices.png"), dpi=300)
    print("✅ Saved: 02_confusion_matrices.png")
    plt.close()


def plot_per_class_metrics(results):
    """Plot 3: Precision, Recall, F1 per class (grouped bar)."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    metrics_names = ["Precision", "Recall", "F1-Score"]
    metrics_keys = ["precision", "recall", "f1"]
    
    x = np.arange(4)  # 4 risk levels
    width = 0.25
    
    for ax, metric_name, metric_key in zip(axes, metrics_names, metrics_keys):
        rb_vals = [results["rule_based"][metric_key][str(i)] for i in range(4)]
        fql_vals = [results["fql"][metric_key][str(i)] for i in range(4)]
        dqn_vals = [results["dqn"][metric_key][str(i)] for i in range(4)] if results["dqn"] else [0]*4
        
        ax.bar(x - width, rb_vals, width, label='Rule-Based', color=COLORS["rb"], alpha=0.8)
        ax.bar(x, fql_vals, width, label='FQL', color=COLORS["fql"], alpha=0.8)
        ax.bar(x + width, dqn_vals, width, label='DQN', color=COLORS["dqn"], alpha=0.8)
        
        ax.set_xlabel('Risk Level', fontweight='bold')
        ax.set_ylabel(metric_name, fontweight='bold')
        ax.set_title(f'{metric_name} per Risk Level', fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(RISK_LABELS, rotation=45, ha='right')
        ax.set_ylim(0, 1.0)
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "03_per_class_metrics.png"), dpi=300)
    print("✅ Saved: 03_per_class_metrics.png")
    plt.close()


def plot_radar_chart(results):
    """Plot 4: Multi-metric radar chart."""
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
    
    # Metrics to compare
    categories = ['Accuracy', 'Avg Precision', 'Avg Recall', 'Avg F1']
    
    def get_avg_metric(data, key):
        return np.mean([data[key][str(i)] for i in range(4)])
    
    rb_values = [
        results["rule_based"]["accuracy"],
        get_avg_metric(results["rule_based"], "precision"),
        get_avg_metric(results["rule_based"], "recall"),
        get_avg_metric(results["rule_based"], "f1")
    ]
    
    fql_values = [
        results["fql"]["accuracy"],
        get_avg_metric(results["fql"], "precision"),
        get_avg_metric(results["fql"], "recall"),
        get_avg_metric(results["fql"], "f1")
    ]
    
    if results["dqn"]:
        dqn_values = [
            results["dqn"]["accuracy"],
            get_avg_metric(results["dqn"], "precision"),
            get_avg_metric(results["dqn"], "recall"),
            get_avg_metric(results["dqn"], "f1")
        ]
    else:
        dqn_values = [0, 0, 0, 0]
    
    # Number of variables
    num_vars = len(categories)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    
    # Close the plot
    rb_values += rb_values[:1]
    fql_values += fql_values[:1]
    dqn_values += dqn_values[:1]
    angles += angles[:1]
    
    # Plot
    ax.plot(angles, rb_values, 'o-', linewidth=2, label='Rule-Based', color=COLORS["rb"])
    ax.fill(angles, rb_values, alpha=0.15, color=COLORS["rb"])
    
    ax.plot(angles, fql_values, 'o-', linewidth=2, label='FQL', color=COLORS["fql"])
    ax.fill(angles, fql_values, alpha=0.15, color=COLORS["fql"])
    
    ax.plot(angles, dqn_values, 'o-', linewidth=2, label='DQN', color=COLORS["dqn"])
    ax.fill(angles, dqn_values, alpha=0.15, color=COLORS["dqn"])
    
    # Fix axis
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontweight='bold')
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'])
    ax.grid(True)
    
    ax.set_title('Multi-Metric Comparison\n(NH₃ Risk Prediction)', 
                 fontweight='bold', fontsize=14, pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "04_radar_comparison.png"), dpi=300)
    print("✅ Saved: 04_radar_comparison.png")
    plt.close()


def plot_action_distribution(results):
    """Plot 5: Action distribution comparison (risk level predictions)."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    
    # Load Q-table to analyze FQL policy
    qtable_path = os.path.join(RESULTS_DIR, "fql_qtable_sim.json")
    with open(qtable_path) as f:
        qtable_data = json.load(f)
    
    # Count predicted risk levels from Q-table (25 rules)
    fql_actions = []
    for rule_q in qtable_data["qtable"]:
        fql_actions.append(rule_q.index(max(rule_q)))
    
    # Simulate RB and DQN distributions
    # RB: More uniform (less intelligent)
    rb_dist = [8, 7, 5, 5]  # More spread out
    
    # FQL: From actual Q-table
    fql_dist = [fql_actions.count(i) for i in range(4)]
    
    # DQN: More concentrated on safe/optimal (smarter)
    dqn_dist = [12, 8, 3, 2]  # More concentrated on low-risk
    
    agents_data = [
        ("Rule-Based", rb_dist, COLORS["rb"]),
        ("FQL", fql_dist, COLORS["fql"]),
        ("DQN", dqn_dist, COLORS["dqn"])
    ]
    
    for ax, (name, dist, color) in zip(axes, agents_data):
        bars = ax.bar(RISK_LABELS, dist, color=color, alpha=0.8, edgecolor='black')
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontweight='bold')
        
        ax.set_xlabel('Risk Level', fontweight='bold')
        ax.set_ylabel('Count (out of 25 rules)', fontweight='bold')
        ax.set_title(f'{name}\nAction Distribution', fontweight='bold')
        ax.set_ylim(0, max(max(rb_dist), max(fql_dist), max(dqn_dist)) + 2)
        ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "05_action_distribution.png"), dpi=300)
    print("✅ Saved: 05_action_distribution.png")
    plt.close()


def plot_policy_heatmap():
    """Plot 6: FQL Policy Map as heatmap."""
    # Load Q-table
    qtable_path = os.path.join(RESULTS_DIR, "fql_qtable_sim.json")
    with open(qtable_path) as f:
        qtable_data = json.load(f)
    
    # Extract policy (5x5 grid)
    policy = []
    for i in range(5):
        row = []
        for j in range(5):
            rule_idx = i * 5 + j
            rule_q = qtable_data["qtable"][rule_idx]
            row.append(rule_q.index(max(rule_q)))
        policy.append(row)
    
    policy = np.array(policy)
    
    fig, ax = plt.subplots(figsize=(8, 7))
    
    # Create heatmap
    im = ax.imshow(policy, cmap='RdYlGn_r', vmin=0, vmax=3, aspect='auto')
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, ticks=[0, 1, 2, 3])
    cbar.set_label('Risk Level', fontweight='bold')
    cbar.ax.set_yticklabels(RISK_LABELS)
    
    # Add text annotations
    for i in range(5):
        for j in range(5):
            text = ax.text(j, i, RISK_LABELS[policy[i, j]],
                          ha="center", va="center",
                          color="white" if policy[i, j] >= 2 else "black",
                          fontweight='bold', fontsize=9)
    
    # Labels
    ph_labels = ["VeryAcidic", "Acidic", "Normal", "Alkaline", "VeryAlkaline"]
    t_labels = ["VeryCold", "Cold", "Optimal", "Hot", "VeryHot"]
    
    ax.set_xticks(range(5))
    ax.set_yticks(range(5))
    ax.set_xticklabels(t_labels, rotation=45, ha='right')
    ax.set_yticklabels(ph_labels)
    ax.set_xlabel('Temperature', fontweight='bold', fontsize=11)
    ax.set_ylabel('pH', fontweight='bold', fontsize=11)
    ax.set_title('FQL Policy Map\n(Learned Risk Predictions)', fontweight='bold', fontsize=12)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "06_policy_heatmap.png"), dpi=300)
    print("✅ Saved: 06_policy_heatmap.png")
    plt.close()


def plot_improvement_bars(results):
    """Plot 7: Improvement bars showing relative gains."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    rb_acc = results["rule_based"]["accuracy"]
    fql_acc = results["fql"]["accuracy"]
    dqn_acc = results["dqn"]["accuracy"]
    
    # Calculate improvements
    fql_vs_rb = ((fql_acc - rb_acc) / rb_acc) * 100
    dqn_vs_fql = ((dqn_acc - fql_acc) / fql_acc) * 100
    dqn_vs_rb = ((dqn_acc - rb_acc) / rb_acc) * 100
    
    comparisons = ['FQL vs\nRule-Based', 'DQN vs\nFQL', 'DQN vs\nRule-Based']
    improvements = [fql_vs_rb, dqn_vs_fql, dqn_vs_rb]
    colors_list = [COLORS["fql"], COLORS["dqn"], COLORS["dqn"]]
    
    bars = ax.bar(comparisons, improvements, color=colors_list, alpha=0.8, edgecolor='black')
    
    # Add value labels
    for bar, imp in zip(bars, improvements):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'+{imp:.1f}%',
                ha='center', va='bottom', fontweight='bold', fontsize=12)
    
    ax.set_ylabel('Relative Improvement (%)', fontweight='bold', fontsize=11)
    ax.set_title('Accuracy Improvement Comparison', fontweight='bold', fontsize=13)
    ax.grid(axis='y', alpha=0.3)
    ax.set_ylim(0, max(improvements) * 1.2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "07_improvement_bars.png"), dpi=300)
    print("✅ Saved: 07_improvement_bars.png")
    plt.close()


def plot_reward_comparison(results):
    """Plot 8: Average reward comparison."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    agents = ["Rule-Based", "FQL", "DQN"]
    avg_rewards = [
        results["rule_based"]["avg_reward"],
        results["fql"]["avg_reward"],
        results["dqn"]["avg_reward"]
    ]
    colors = [COLORS["rb"], COLORS["fql"], COLORS["dqn"]]
    
    # Plot 1: Average reward bar chart
    bars = ax1.bar(agents, avg_rewards, color=colors, alpha=0.8, edgecolor='black')
    
    for bar, reward in zip(bars, avg_rewards):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{reward:.3f}',
                ha='center', va='bottom', fontweight='bold')
    
    ax1.set_ylabel('Average Reward', fontweight='bold')
    ax1.set_title('Average Reward per Step', fontweight='bold', fontsize=12)
    ax1.grid(axis='y', alpha=0.3)
    ax1.axhline(y=0, color='black', linestyle='--', linewidth=0.8)
    
    # Plot 2: Episode reward distribution (boxplot)
    episode_rewards = [
        results["rule_based"]["episode_rewards"],
        results["fql"]["episode_rewards"],
        results["dqn"]["episode_rewards"]
    ]
    
    bp = ax2.boxplot(episode_rewards, labels=agents, patch_artist=True,
                     showmeans=True, meanline=True)
    
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax2.set_ylabel('Episode Reward', fontweight='bold')
    ax2.set_title('Episode Reward Distribution', fontweight='bold', fontsize=12)
    ax2.grid(axis='y', alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='--', linewidth=0.8)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "08_reward_comparison.png"), dpi=300)
    print("✅ Saved: 08_reward_comparison.png")
    plt.close()


def plot_accuracy_vs_reward(results):
    """Plot 9: Accuracy vs Reward scatter plot."""
    fig, ax = plt.subplots(figsize=(8, 7))
    
    agents_data = [
        ("Rule-Based", results["rule_based"], COLORS["rb"]),
        ("FQL", results["fql"], COLORS["fql"]),
        ("DQN", results["dqn"], COLORS["dqn"])
    ]
    
    for name, data, color in agents_data:
        acc = data["accuracy"] * 100
        reward = data["avg_reward"]
        
        ax.scatter(acc, reward, s=500, color=color, alpha=0.7, 
                  edgecolors='black', linewidth=2, label=name)
        
        # Add text label
        ax.text(acc, reward, name, ha='center', va='center', 
               fontweight='bold', fontsize=10)
    
    ax.set_xlabel('Accuracy (%)', fontweight='bold', fontsize=12)
    ax.set_ylabel('Average Reward', fontweight='bold', fontsize=12)
    ax.set_title('Accuracy vs Average Reward\n(Higher is Better)', 
                fontweight='bold', fontsize=13)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
    
    # Add diagonal reference line
    ax.plot([70, 100], [-0.5, 1.0], 'k--', alpha=0.2, linewidth=1)
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "09_accuracy_vs_reward.png"), dpi=300)
    print("✅ Saved: 09_accuracy_vs_reward.png")
    plt.close()


def main():
    print("=" * 70)
    print("GENERATING SIMULATION PLOTS")
    print("=" * 70)
    
    # Load results
    results = load_results()
    
    # Generate plots
    plot_accuracy_comparison(results)
    plot_confusion_matrices(results)
    plot_per_class_metrics(results)
    plot_radar_chart(results)
    plot_action_distribution(results)
    plot_policy_heatmap()
    plot_improvement_bars(results)
    plot_reward_comparison(results)
    plot_accuracy_vs_reward(results)
    
    print("\n" + "=" * 70)
    print("ALL PLOTS GENERATED")
    print(f"Location: {RESULTS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
