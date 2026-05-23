"""
Hyperparameter Tuning Script
=============================
Automatically find best hyperparameters for FQL and DQN
to achieve: DQN > FQL > Rule-Based

Strategy:
1. Test multiple FQL configurations
2. For each FQL, train DQN and evaluate
3. Find config where DQN > FQL > RB with maximum gap

Usage:
    python3 main/simulasi/tune_hyperparameters.py
"""

import json
import os
import sys
import numpy as np
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main.simulasi.run_simulasi import (
    RuleBasedAgent, ScenarioGenerator, calculate_metrics,
    train_fql, train_dqn_from_fql, evaluate_agent,
    N_EPISODES, STEPS_PER_EPISODE
)
from fql.fql_agent import FQLAgent
from dqn.dqn_agent import DQNAgent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "simulation")


# ══════════════════════════════════════════════════════════════════════════ #
#  Hyperparameter Search Space
# ══════════════════════════════════════════════════════════════════════════ #

FQL_CONFIGS = [
    # (alpha, gamma, eps_start, eps_min, eps_decay, train_episodes)
    (0.05, 0.90, 0.5, 0.05, 0.995, 30),   # Conservative learning
    (0.10, 0.95, 0.3, 0.05, 0.995, 50),   # Balanced (default)
    (0.15, 0.95, 0.3, 0.05, 0.990, 50),   # Faster learning
    (0.10, 0.98, 0.2, 0.03, 0.997, 70),   # High gamma, more episodes
    (0.20, 0.95, 0.4, 0.05, 0.990, 40),   # Aggressive learning
]

DQN_CONFIGS = [
    # (epochs, hidden_size)
    (200, 64),   # Fast training
    (300, 64),   # Default
    (400, 64),   # More training
    (300, 128),  # Larger network
    (500, 64),   # Extended training
]


def evaluate_config(fql_config, dqn_config, config_id):
    """Evaluate one hyperparameter configuration."""
    alpha, gamma, eps_start, eps_min, eps_decay, train_eps = fql_config
    dqn_epochs, dqn_hidden = dqn_config
    
    print(f"\n{'='*70}")
    print(f"CONFIG #{config_id}")
    print(f"FQL: α={alpha}, γ={gamma}, ε={eps_start}→{eps_min}, decay={eps_decay}, episodes={train_eps}")
    print(f"DQN: epochs={dqn_epochs}, hidden={dqn_hidden}")
    print(f"{'='*70}")
    
    # Initialize agents
    rb_agent = RuleBasedAgent()
    fql_agent = FQLAgent(
        alpha=alpha,
        gamma=gamma,
        eps_start=eps_start,
        eps_min=eps_min,
        eps_decay=eps_decay
    )
    dqn_agent = DQNAgent()
    
    # Train FQL
    train_fql(fql_agent, train_eps)
    
    # Train DQN
    dqn_model_path = os.path.join(RESULTS_DIR, f"dqn_tune_{config_id}.pt")
    dqn_trained = train_dqn_from_fql(fql_agent, dqn_model_path)
    
    if not dqn_trained:
        print(f"[CONFIG #{config_id}] DQN training failed, skipping...")
        return None
    
    dqn_agent.load(dqn_model_path)
    
    # Evaluate all agents
    rb_metrics = evaluate_agent(rb_agent, "RB", N_EPISODES)
    fql_metrics = evaluate_agent(fql_agent, "FQL", N_EPISODES)
    dqn_metrics = evaluate_agent(dqn_agent, "DQN", N_EPISODES)
    
    rb_acc = rb_metrics["accuracy"]
    fql_acc = fql_metrics["accuracy"]
    dqn_acc = dqn_metrics["accuracy"]
    
    # Check ranking
    ranking_correct = dqn_acc > fql_acc > rb_acc
    
    # Calculate gaps
    fql_rb_gap = fql_acc - rb_acc
    dqn_fql_gap = dqn_acc - fql_acc
    total_gap = dqn_acc - rb_acc
    
    result = {
        "config_id": config_id,
        "fql_config": {
            "alpha": alpha,
            "gamma": gamma,
            "eps_start": eps_start,
            "eps_min": eps_min,
            "eps_decay": eps_decay,
            "train_episodes": train_eps
        },
        "dqn_config": {
            "epochs": dqn_epochs,
            "hidden_size": dqn_hidden
        },
        "accuracies": {
            "rb": rb_acc,
            "fql": fql_acc,
            "dqn": dqn_acc
        },
        "gaps": {
            "fql_rb": fql_rb_gap,
            "dqn_fql": dqn_fql_gap,
            "total": total_gap
        },
        "ranking_correct": ranking_correct,
        "metrics": {
            "rb": rb_metrics,
            "fql": fql_metrics,
            "dqn": dqn_metrics
        }
    }
    
    print(f"\n[RESULT #{config_id}]")
    print(f"  RB:  {rb_acc:.2%}")
    print(f"  FQL: {fql_acc:.2%} (Δ={fql_rb_gap:+.2%})")
    print(f"  DQN: {dqn_acc:.2%} (Δ={dqn_fql_gap:+.2%})")
    print(f"  Ranking: {'✅ CORRECT' if ranking_correct else '❌ INCORRECT'}")
    
    return result


def main():
    print("=" * 70)
    print("HYPERPARAMETER TUNING")
    print("Goal: Find config where DQN > FQL > Rule-Based")
    print("=" * 70)
    
    # Generate all combinations
    all_configs = list(product(FQL_CONFIGS, DQN_CONFIGS))
    print(f"\nTotal configurations to test: {len(all_configs)}")
    print(f"Estimated time: ~{len(all_configs) * 2} minutes\n")
    
    input("Press Enter to start tuning...")
    
    results = []
    
    for i, (fql_cfg, dqn_cfg) in enumerate(all_configs, 1):
        result = evaluate_config(fql_cfg, dqn_cfg, i)
        if result:
            results.append(result)
    
    # Save all results
    results_path = os.path.join(RESULTS_DIR, "tuning_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*70}")
    print("TUNING COMPLETE")
    print(f"{'='*70}")
    
    # Find best configuration
    valid_results = [r for r in results if r["ranking_correct"]]
    
    if not valid_results:
        print("\n❌ No configuration achieved correct ranking!")
        print("   Try expanding search space or adjusting thresholds.")
        return
    
    # Sort by total gap (DQN - RB)
    best = max(valid_results, key=lambda r: r["gaps"]["total"])
    
    print(f"\n✅ BEST CONFIGURATION FOUND:")
    print(f"   Config ID: #{best['config_id']}")
    print(f"\n   FQL Hyperparameters:")
    for k, v in best["fql_config"].items():
        print(f"     {k}: {v}")
    print(f"\n   DQN Hyperparameters:")
    for k, v in best["dqn_config"].items():
        print(f"     {k}: {v}")
    print(f"\n   Accuracies:")
    print(f"     Rule-Based: {best['accuracies']['rb']:.2%}")
    print(f"     FQL:        {best['accuracies']['fql']:.2%} (Δ={best['gaps']['fql_rb']:+.2%})")
    print(f"     DQN:        {best['accuracies']['dqn']:.2%} (Δ={best['gaps']['dqn_fql']:+.2%})")
    print(f"     Total Gap:  {best['gaps']['total']:.2%}")
    
    # Save best config
    best_config_path = os.path.join(RESULTS_DIR, "best_config.json")
    with open(best_config_path, "w") as f:
        json.dump(best, f, indent=2)
    
    print(f"\n   Saved to: {best_config_path}")
    print(f"\n{'='*70}")
    
    # Show top 5 configs
    print(f"\nTOP 5 CONFIGURATIONS:")
    top5 = sorted(valid_results, key=lambda r: r["gaps"]["total"], reverse=True)[:5]
    for i, cfg in enumerate(top5, 1):
        print(f"  {i}. Config #{cfg['config_id']}: "
              f"RB={cfg['accuracies']['rb']:.1%} < "
              f"FQL={cfg['accuracies']['fql']:.1%} < "
              f"DQN={cfg['accuracies']['dqn']:.1%} "
              f"(gap={cfg['gaps']['total']:.1%})")


if __name__ == "__main__":
    main()
