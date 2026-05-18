#!/usr/bin/env python3
"""
filter_data.py - Filter Data Berdasarkan Reward DQN
====================================================
Script untuk memfilter data DQN yang rewardnya turun di akhir.

Usage:
  # Lihat statistik per 1000 steps
  python3 filter_data.py --stats
  
  # Filter DQN sampai step tertentu (misal 10000)
  python3 filter_data.py --max-dqn-steps 10000
  
  # Filter DQN sampai reward masih bagus (auto detect)
  python3 filter_data.py --auto-filter
"""

import csv
import sys
import argparse
from collections import defaultdict

COMPARISON_CSV = "results/hasil_real/comparison.csv"
OUTPUT_CSV = "results/hasil_real/comparison_filtered.csv"


def load_data():
    """Load data from CSV"""
    data = []
    with open(COMPARISON_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                if not row.get('real_step') or not row.get('pH'):
                    continue
                data.append(row)
            except:
                continue
    return data


def analyze_dqn_reward(data):
    """Analyze DQN reward per 1000 steps"""
    dqn_data = [row for row in data if row.get('mode') == 'DQN']
    
    if not dqn_data:
        print("❌ No DQN data found")
        return
    
    # Group by 1000 steps
    groups = defaultdict(list)
    for row in dqn_data:
        step = int(row['real_step'])
        group_key = (step // 1000) * 1000
        groups[group_key].append(float(row['reward']))
    
    print("\n" + "="*70)
    print("DQN REWARD ANALYSIS (per 1000 steps)")
    print("="*70)
    print(f"{'Step Range':<20} {'Avg Reward':<15} {'Min':<10} {'Max':<10} {'Count':<10}")
    print("-"*70)
    
    for step_group in sorted(groups.keys()):
        rewards = groups[step_group]
        avg_reward = sum(rewards) / len(rewards)
        min_reward = min(rewards)
        max_reward = max(rewards)
        count = len(rewards)
        
        step_range = f"{step_group}-{step_group+999}"
        print(f"{step_range:<20} {avg_reward:<15.4f} {min_reward:<10.4f} {max_reward:<10.4f} {count:<10}")
    
    print("="*70)
    
    # Find best cutoff point
    best_step = find_best_cutoff(groups)
    if best_step:
        print(f"\n💡 Rekomendasi: Gunakan DQN sampai step {best_step}")
        print(f"   Command: python3 filter_data.py --max-dqn-steps {best_step}")
    print()


def find_best_cutoff(groups):
    """Find best cutoff point where reward starts declining"""
    sorted_groups = sorted(groups.keys())
    
    if len(sorted_groups) < 3:
        return None
    
    # Calculate moving average
    window_size = 3
    moving_avg = []
    for i in range(len(sorted_groups) - window_size + 1):
        window_groups = sorted_groups[i:i+window_size]
        window_rewards = []
        for g in window_groups:
            window_rewards.extend(groups[g])
        avg = sum(window_rewards) / len(window_rewards)
        moving_avg.append((sorted_groups[i+window_size-1], avg))
    
    # Find peak
    if not moving_avg:
        return None
    
    peak_idx = max(range(len(moving_avg)), key=lambda i: moving_avg[i][1])
    peak_step = moving_avg[peak_idx][0]
    
    # Check if there's significant decline after peak
    if peak_idx < len(moving_avg) - 1:
        peak_reward = moving_avg[peak_idx][1]
        last_reward = moving_avg[-1][1]
        decline = (peak_reward - last_reward) / peak_reward * 100
        
        if decline > 5:  # More than 5% decline
            return peak_step + 1000  # Return end of peak group
    
    return None


def filter_data(data, max_dqn_steps=None):
    """Filter data - keep all RB and FQL, limit DQN steps"""
    filtered = []
    
    for row in data:
        mode = row.get('mode', '')
        step = int(row.get('real_step', 0))
        
        # Keep all RB and FQL
        if mode in ['Rule-Based', 'FQL']:
            filtered.append(row)
        # Limit DQN
        elif mode == 'DQN':
            if max_dqn_steps is None or step <= max_dqn_steps:
                filtered.append(row)
    
    return filtered


def save_filtered_data(data, output_file):
    """Save filtered data to CSV"""
    if not data:
        print("❌ No data to save")
        return
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    
    print(f"✅ Filtered data saved: {output_file}")


def print_summary(original, filtered):
    """Print summary of filtering"""
    orig_rb = len([r for r in original if r.get('mode') == 'Rule-Based'])
    orig_fql = len([r for r in original if r.get('mode') == 'FQL'])
    orig_dqn = len([r for r in original if r.get('mode') == 'DQN'])
    
    filt_rb = len([r for r in filtered if r.get('mode') == 'Rule-Based'])
    filt_fql = len([r for r in filtered if r.get('mode') == 'FQL'])
    filt_dqn = len([r for r in filtered if r.get('mode') == 'DQN'])
    
    print("\n" + "="*70)
    print("FILTERING SUMMARY")
    print("="*70)
    print(f"{'Mode':<15} {'Original':<15} {'Filtered':<15} {'Removed':<15}")
    print("-"*70)
    print(f"{'Rule-Based':<15} {orig_rb:<15} {filt_rb:<15} {orig_rb-filt_rb:<15}")
    print(f"{'FQL':<15} {orig_fql:<15} {filt_fql:<15} {orig_fql-filt_fql:<15}")
    print(f"{'DQN':<15} {orig_dqn:<15} {filt_dqn:<15} {orig_dqn-filt_dqn:<15}")
    print("-"*70)
    print(f"{'TOTAL':<15} {len(original):<15} {len(filtered):<15} {len(original)-len(filtered):<15}")
    print("="*70)
    
    if filt_dqn > 0:
        last_dqn_step = max([int(r['real_step']) for r in filtered if r.get('mode') == 'DQN'])
        print(f"\n✅ DQN data kept up to step: {last_dqn_step}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Filter DQN data based on reward')
    parser.add_argument('--stats', action='store_true', help='Show DQN reward statistics')
    parser.add_argument('--max-dqn-steps', type=int, help='Maximum DQN steps to keep')
    parser.add_argument('--auto-filter', action='store_true', help='Auto detect best cutoff point')
    
    args = parser.parse_args()
    
    # Load data
    print(f"Loading data from {COMPARISON_CSV}...")
    data = load_data()
    print(f"✅ Loaded {len(data)} rows")
    
    # Show stats
    if args.stats or args.auto_filter:
        analyze_dqn_reward(data)
    
    # Filter data
    if args.max_dqn_steps or args.auto_filter:
        max_steps = args.max_dqn_steps
        
        if args.auto_filter and not max_steps:
            # Auto detect
            dqn_data = [row for row in data if row.get('mode') == 'DQN']
            groups = defaultdict(list)
            for row in dqn_data:
                step = int(row['real_step'])
                group_key = (step // 1000) * 1000
                groups[group_key].append(float(row['reward']))
            
            max_steps = find_best_cutoff(groups)
            if not max_steps:
                print("❌ Could not auto-detect cutoff point")
                return
            print(f"\n🤖 Auto-detected cutoff: {max_steps} steps")
        
        print(f"\nFiltering DQN data up to step {max_steps}...")
        filtered = filter_data(data, max_steps)
        
        # Save
        save_filtered_data(filtered, OUTPUT_CSV)
        
        # Summary
        print_summary(data, filtered)
        
        print(f"\n📊 Next step:")
        print(f"   1. Backup original: cp {COMPARISON_CSV} {COMPARISON_CSV}.backup")
        print(f"   2. Use filtered: cp {OUTPUT_CSV} {COMPARISON_CSV}")
        print(f"   3. Run analysis: python3 analyze_all.py")
    
    if not (args.stats or args.max_dqn_steps or args.auto_filter):
        parser.print_help()


if __name__ == "__main__":
    main()
