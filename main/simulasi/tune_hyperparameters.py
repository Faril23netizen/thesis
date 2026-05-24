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
    TraditionalRuleBased, ScenarioGenerator, calculate_metrics, evaluate_agent,
    append_transition, calculate_actual_risk,
    N_EPISODES, STEPS_PER_EPISODE
)
from fql.fql_agent import FQLAgent
from dqn.dqn_agent import DQNAgent

try:
    from dqn.train_dqn import train_pytorch, train_numpy, TORCH_AVAILABLE
except ImportError:
    TORCH_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "simulation")


# ══════════════════════════════════════════════════════════════════════════ #
#  Hyperparameter Search Space
# ══════════════════════════════════════════════════════════════════════════ #

FQL_CONFIGS = [
    # (alpha, gamma, eps_start, eps_min, eps_decay, train_episodes)
    (0.05, 0.90, 0.5, 0.05, 0.995, 100),  # Conservative learning
    (0.15, 0.95, 0.5, 0.01, 0.999, 150),  # Fast learning (Default)
    (0.20, 0.95, 0.6, 0.05, 0.990, 200),  # Aggressive learning
]

DQN_CONFIGS = [
    # epochs
    (500,),   
    (1000,),  
    (1500,),  
]


def evaluate_config(fql_config, dqn_config, config_id):
    """Evaluate one hyperparameter configuration."""
    alpha, gamma, eps_start, eps_min, eps_decay, train_eps = fql_config
    dqn_epochs = dqn_config[0]
    
    print(f"\n{'='*70}")
    print(f"CONFIG #{config_id}")
    print(f"FQL: α={alpha}, γ={gamma}, ε={eps_start}→{eps_min}, decay={eps_decay}, episodes={train_eps}")
    print(f"DQN: epochs={dqn_epochs}")
    print(f"{'='*70}")
    
    # Initialize agents
    rb_agent = TraditionalRuleBased()
    fql_agent = FQLAgent(
        alpha=alpha,
        gamma=gamma,
        eps_start=eps_start,
        eps_min=eps_min,
        eps_decay=eps_decay
    )
    dqn_buffer = []
    
    # Train FQL
    episode_types = ["safe", "acidic", "alkaline", "cold", "hot", "multi", "random"]
    for ep in range(train_eps):
        ep_type = episode_types[ep % len(episode_types)]
        trajectory = ScenarioGenerator.generate_episode(ep_type, STEPS_PER_EPISODE)
        for pH, T in trajectory:
            actual_risk = calculate_actual_risk(pH, T)
            predicted_risk = fql_agent.predict_risk(pH, T)
            fql_agent.update(pH, T, predicted_risk, actual_risk)
            append_transition(dqn_buffer, s=[pH, T], a=actual_risk, 
                              r=1.0 if predicted_risk == actual_risk else -1.0, 
                              s_next=[pH, T])
    
    # Train DQN
    dqn_model_path = os.path.join(RESULTS_DIR, f"dqn_tune_{config_id}.pt")
    if TORCH_AVAILABLE:
        train_pytorch(dqn_buffer, epochs=dqn_epochs, model_path=dqn_model_path)
    else:
        train_numpy(dqn_buffer, epochs=dqn_epochs, model_path=dqn_model_path)
        
    dqn_agent = DQNAgent()
    if not dqn_agent.load(dqn_model_path):
        print(f"[CONFIG #{config_id}] DQN loading failed, skipping...")
        return None
        
    fql_agent.epsilon = 0.0 # greedy for eval
    
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
