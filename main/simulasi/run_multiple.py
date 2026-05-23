"""
Multiple Simulation Runs for Statistical Validation
====================================================
Run simulation multiple times to ensure consistent DQN > FQL > RB ranking.

Usage:
    python3 main/simulasi/run_multiple.py
"""

import subprocess
import json
import os
import sys
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "simulation")
PYTHON_PATH = r"C:\Users\faril\AppData\Local\Programs\Python\Python310\python.exe"

N_RUNS = 5  # Number of simulation runs


def run_simulation():
    """Run single simulation and return results."""
    script_path = os.path.join(BASE_DIR, "main", "simulasi", "run_simulasi.py")
    result = subprocess.run(
        [PYTHON_PATH, script_path],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Simulation failed: {result.stderr}")
        return None
    
    # Load results
    results_path = os.path.join(RESULTS_DIR, "simulation_results.json")
    with open(results_path) as f:
        return json.load(f)


def main():
    print("=" * 70)
    print(f"RUNNING {N_RUNS} SIMULATION RUNS")
    print("=" * 70)
    
    all_results = []
    
    for i in range(N_RUNS):
        print(f"\n[Run {i+1}/{N_RUNS}] Starting simulation...")
        results = run_simulation()
        
        if results:
            rb_acc = results["rule_based"]["accuracy"]
            fql_acc = results["fql"]["accuracy"]
            dqn_acc = results["dqn"]["accuracy"]
            
            rb_reward = results["rule_based"]["avg_reward"]
            fql_reward = results["fql"]["avg_reward"]
            dqn_reward = results["dqn"]["avg_reward"]
            
            print(f"[Run {i+1}/{N_RUNS}] Results:")
            print(f"  Rule-Based: {rb_acc:.2%} | Reward: {rb_reward:.3f}")
            print(f"  FQL:        {fql_acc:.2%} | Reward: {fql_reward:.3f}")
            print(f"  DQN:        {dqn_acc:.2%} | Reward: {dqn_reward:.3f}")
            
            # Check ranking
            acc_ok = dqn_acc > fql_acc > rb_acc
            reward_ok = dqn_reward > fql_reward > rb_reward
            
            if acc_ok and reward_ok:
                print(f"  ✅ Ranking correct (Acc & Reward)!")
            else:
                print(f"  ⚠️  Ranking incorrect!")
                if not acc_ok:
                    print(f"     - Accuracy ranking wrong")
                if not reward_ok:
                    print(f"     - Reward ranking wrong")
            
            all_results.append({
                "rb": rb_acc,
                "fql": fql_acc,
                "dqn": dqn_acc,
                "rb_reward": rb_reward,
                "fql_reward": fql_reward,
                "dqn_reward": dqn_reward
            })
        else:
            print(f"[Run {i+1}/{N_RUNS}] Failed!")
    
    # Calculate statistics
    if all_results:
        print("\n" + "=" * 70)
        print("AGGREGATE STATISTICS")
        print("=" * 70)
        
        rb_accs = [r["rb"] for r in all_results]
        fql_accs = [r["fql"] for r in all_results]
        dqn_accs = [r["dqn"] for r in all_results]
        
        rb_rewards = [r["rb_reward"] for r in all_results]
        fql_rewards = [r["fql_reward"] for r in all_results]
        dqn_rewards = [r["dqn_reward"] for r in all_results]
        
        print(f"\nACCURACY:")
        print(f"  Rule-Based: {np.mean(rb_accs):.2%} ± {np.std(rb_accs):.2%}")
        print(f"  FQL:        {np.mean(fql_accs):.2%} ± {np.std(fql_accs):.2%}")
        print(f"  DQN:        {np.mean(dqn_accs):.2%} ± {np.std(dqn_accs):.2%}")
        
        print(f"\nAVERAGE REWARD:")
        print(f"  Rule-Based: {np.mean(rb_rewards):.3f} ± {np.std(rb_rewards):.3f}")
        print(f"  FQL:        {np.mean(fql_rewards):.3f} ± {np.std(fql_rewards):.3f}")
        print(f"  DQN:        {np.mean(dqn_rewards):.3f} ± {np.std(dqn_rewards):.3f}")
        
        # Check consistency
        correct_rankings = sum(
            1 for r in all_results 
            if (r["dqn"] > r["fql"] > r["rb"]) and 
               (r["dqn_reward"] > r["fql_reward"] > r["rb_reward"])
        )
        
        print(f"\n" + "=" * 70)
        print(f"RANKING CONSISTENCY: {correct_rankings}/{N_RUNS} runs correct")
        print(f"Success Rate: {correct_rankings/N_RUNS:.1%}")
        print("=" * 70)


if __name__ == "__main__":
    main()
