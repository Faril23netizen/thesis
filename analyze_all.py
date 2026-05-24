#!/usr/bin/env python3
"""
analyze_all.py - Complete Analysis for Thesis
==============================================
Generate semua grafik dan analisis dalam 1 run:
- Data real (pH, temp, learning)
- Network performance (N3IWF, IPsec)
- Progressive AI (RB → FQL → DQN)
- Summary statistics

Usage:
  python3 analyze_all.py
  
Output:
  results/thesis/complete_analysis.pdf
  results/thesis/summary.csv
  results/thesis/plots/*.png
"""

import os
import sys
import csv
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_REAL = os.path.join(BASE_DIR, "results", "hasil_real")
RESULTS_NETWORK = os.path.join(BASE_DIR, "results", "network")
RESULTS_THESIS = os.path.join(BASE_DIR, "results", "thesis")
PLOTS_DIR = os.path.join(RESULTS_THESIS, "plots")

# Input files
def get_latest_session_csv() -> str:
    base_csv = os.path.join(RESULTS_REAL, "comparison.csv")
    if not os.path.exists(RESULTS_REAL):
        return base_csv
        
    sessions = [d for d in os.listdir(RESULTS_REAL) if d.startswith("session_") and os.path.isdir(os.path.join(RESULTS_REAL, d))]
    if not sessions:
        return base_csv
        
    sessions.sort(reverse=True)
    latest_csv = os.path.join(RESULTS_REAL, sessions[0], "comparison.csv")
    return latest_csv if os.path.exists(latest_csv) else base_csv

COMPARISON_CSV = get_latest_session_csv()
CALLBOX_STATS = os.path.join(RESULTS_NETWORK, "callbox_stats.json")
N3IWF_STATUS = os.path.join(RESULTS_NETWORK, "n3iwf_status.json")

# Output files
PDF_OUTPUT = os.path.join(RESULTS_THESIS, "complete_analysis.pdf")
SUMMARY_CSV = os.path.join(RESULTS_THESIS, "summary.csv")

os.makedirs(PLOTS_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Data Loading
# ══════════════════════════════════════════════════════════════════════════════

def load_comparison_data():
    """Load data from comparison.csv"""
    data = []
    try:
        with open(COMPARISON_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Skip rows with missing or None values
                    if not row.get('real_step') or not row.get('pH') or not row.get('T_C'):
                        continue
                    
                    data.append({
                        'step': int(row['real_step']),
                        'pH': float(row['pH']),
                        'T': float(row['T_C']),
                        'mode': row.get('mode', 'Unknown'),
                        'action': int(row.get('real_action', 0)),
                        'reward': float(row.get('reward', 0)),
                        'rb_reward': float(row.get('rb_reward', 0)),
                        'energy': float(row.get('energy_real', 0)),
                        'fql_steps': int(row.get('fql_steps', 0)),
                        'epsilon': float(row.get('epsilon', 0))
                    })
                except (ValueError, KeyError, TypeError):
                    continue
    except FileNotFoundError:
        print(f"⚠️  File not found: {COMPARISON_CSV}")
        return []
    
    return data


def load_network_stats():
    """Load network statistics"""
    stats = {}
    
    # Callbox stats
    try:
        with open(CALLBOX_STATS, 'r') as f:
            stats['callbox'] = json.load(f)
    except FileNotFoundError:
        stats['callbox'] = None
    
    # N3IWF status
    try:
        with open(N3IWF_STATUS, 'r') as f:
            stats['n3iwf'] = json.load(f)
    except FileNotFoundError:
        stats['n3iwf'] = None
    
    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  Analysis Functions
# ══════════════════════════════════════════════════════════════════════════════

def compute_statistics(data):
    """Compute summary statistics"""
    if not data:
        return {}
    
    # Separate by mode
    rb_data = [d for d in data if d['mode'] == 'RB']
    fql_data = [d for d in data if d['mode'] == 'FQL']
    dqn_data = [d for d in data if d['mode'] == 'DQN']
    
    stats = {
        'total_steps': len(data),
        'rb_steps': len(rb_data),
        'fql_steps': len(fql_data),
        'dqn_steps': len(dqn_data),
        
        # pH statistics
        'pH_mean': np.mean([d['pH'] for d in data]),
        'pH_std': np.std([d['pH'] for d in data]),
        'pH_min': np.min([d['pH'] for d in data]),
        'pH_max': np.max([d['pH'] for d in data]),
        
        # Temperature statistics
        'T_mean': np.mean([d['T'] for d in data]),
        'T_std': np.std([d['T'] for d in data]),
        'T_min': np.min([d['T'] for d in data]),
        'T_max': np.max([d['T'] for d in data]),
        
        # Reward statistics
        'rb_reward_mean': np.mean([d['reward'] for d in rb_data]) if rb_data else 0,
        'fql_reward_mean': np.mean([d['reward'] for d in fql_data]) if fql_data else 0,
        'dqn_reward_mean': np.mean([d['reward'] for d in dqn_data]) if dqn_data else 0,
        
        # Energy statistics
        'total_energy': np.sum([d['energy'] for d in data]),
        'avg_energy': np.mean([d['energy'] for d in data]),
    }
    
    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  Plotting Functions
# ══════════════════════════════════════════════════════════════════════════════

def plot_water_quality(data, ax):
    """Plot pH and Temperature"""
    steps = [d['step'] for d in data]
    pH = [d['pH'] for d in data]
    T = [d['T'] for d in data]
    
    ax1 = ax
    ax2 = ax.twinx()
    
    line1 = ax1.plot(steps, pH, 'b-', label='pH', linewidth=1.5, alpha=0.8)
    line2 = ax2.plot(steps, T, 'r-', label='Temperature', linewidth=1.5, alpha=0.8)
    
    # Safe zones
    ax1.axhspan(6.5, 8.5, alpha=0.1, color='green', label='pH Safe Zone')
    ax2.axhspan(26, 30, alpha=0.1, color='orange')
    
    ax1.set_xlabel('Step')
    ax1.set_ylabel('pH', color='b')
    ax2.set_ylabel('Temperature (°C)', color='r')
    ax1.set_title('Water Quality Monitoring')
    
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.3)


def plot_progressive_learning(data, ax):
    """Plot reward progression by phase"""
    rb_data = [(d['step'], d['reward']) for d in data if d['mode'] == 'RB']
    fql_data = [(d['step'], d['reward']) for d in data if d['mode'] == 'FQL']
    dqn_data = [(d['step'], d['reward']) for d in data if d['mode'] == 'DQN']
    
    if rb_data:
        steps, rewards = zip(*rb_data)
        ax.scatter(steps, rewards, c='red', s=10, alpha=0.5, label='Rule-Based')
    
    if fql_data:
        steps, rewards = zip(*fql_data)
        ax.scatter(steps, rewards, c='orange', s=10, alpha=0.5, label='FQL')
    
    if dqn_data:
        steps, rewards = zip(*dqn_data)
        ax.scatter(steps, rewards, c='green', s=10, alpha=0.5, label='DQN')
    
    # Rolling average
    all_steps = [d['step'] for d in data]
    all_rewards = [d['reward'] for d in data]
    window = min(50, len(data) // 10)
    if window > 0:
        rolling_avg = np.convolve(all_rewards, np.ones(window)/window, mode='same')
        ax.plot(all_steps, rolling_avg, 'k-', linewidth=2, label='Rolling Avg', alpha=0.8)
    
    ax.axhline(0, color='gray', linestyle=':', linewidth=1)
    ax.set_xlabel('Step')
    ax.set_ylabel('Reward')
    ax.set_title('Progressive Learning: RB → FQL → DQN')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


def plot_action_distribution(data, ax):
    """Plot action distribution by phase"""
    action_names = ['OFF', 'LOW', 'MED', 'HIGH']
    phases = ['RB', 'FQL', 'DQN']
    colors = ['#e74c3c', '#f39c12', '#27ae60']
    
    phase_actions = {}
    for phase in phases:
        phase_data = [d for d in data if d['mode'] == phase]
        if phase_data:
            actions = [d['action'] for d in phase_data]
            phase_actions[phase] = [actions.count(i) for i in range(4)]
        else:
            phase_actions[phase] = [0, 0, 0, 0]
    
    x = np.arange(len(action_names))
    width = 0.25
    
    for i, phase in enumerate(phases):
        offset = (i - 1) * width
        ax.bar(x + offset, phase_actions[phase], width, label=phase, color=colors[i], alpha=0.8)
    
    ax.set_xlabel('Action')
    ax.set_ylabel('Count')
    ax.set_title('Action Distribution by Phase')
    ax.set_xticks(x)
    ax.set_xticklabels(action_names)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')


def plot_energy_consumption(data, ax):
    """Plot cumulative energy consumption"""
    steps = [d['step'] for d in data]
    energy = [d['energy'] for d in data]
    cumulative = np.cumsum(energy)
    
    ax.plot(steps, cumulative, 'purple', linewidth=2)
    ax.fill_between(steps, 0, cumulative, alpha=0.3, color='purple')
    
    ax.set_xlabel('Step')
    ax.set_ylabel('Cumulative Energy Cost')
    ax.set_title('Energy Consumption Over Time')
    ax.grid(True, alpha=0.3)


def plot_phase_comparison(data, ax):
    """Plot reward comparison between phases"""
    rb_data = [d['reward'] for d in data if d['mode'] == 'RB']
    fql_data = [d['reward'] for d in data if d['mode'] == 'FQL']
    dqn_data = [d['reward'] for d in data if d['mode'] == 'DQN']
    
    phases = []
    means = []
    stds = []
    colors_list = []
    
    if rb_data:
        phases.append('Rule-Based')
        means.append(np.mean(rb_data))
        stds.append(np.std(rb_data))
        colors_list.append('#e74c3c')
    
    if fql_data:
        phases.append('FQL')
        means.append(np.mean(fql_data))
        stds.append(np.std(fql_data))
        colors_list.append('#f39c12')
    
    if dqn_data:
        phases.append('DQN')
        means.append(np.mean(dqn_data))
        stds.append(np.std(dqn_data))
        colors_list.append('#27ae60')
    
    bars = ax.bar(phases, means, yerr=stds, capsize=10, color=colors_list, alpha=0.8)
    
    # Add value labels
    for bar, mean in zip(bars, means):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{mean:.4f}', ha='center', va='bottom', fontweight='bold')
    
    ax.set_ylabel('Average Reward')
    ax.set_title('Performance Comparison by Phase')
    ax.axhline(0, color='gray', linestyle=':', linewidth=1)
    ax.grid(True, alpha=0.3, axis='y')


def plot_network_stats(stats, ax):
    """Plot network statistics - Enhanced version"""
    if not stats.get('callbox'):
        ax.text(0.5, 0.5, 'No Network Data Available', 
                ha='center', va='center', fontsize=12)
        ax.set_title('Network Performance (N3IWF + IPsec)')
        return
    
    callbox = stats['callbox']
    
    # Create subplot for better visualization
    ax.clear()
    
    # Metrics to display
    metrics = ['Latency\n(ms)', 'Jitter\n(ms)', 'Packet Loss\n(%)', 'Throughput\n(Mbps)']
    
    # Calculate values
    avg_latency = callbox.get('avg_latency_ms', 0)
    jitter = 5  # From simulation config
    packet_loss = (callbox.get('packets_dropped', 0) / max(callbox.get('packets_sent', 1), 1)) * 100
    throughput = callbox.get('current_bandwidth_mbps', 100)
    
    values = [avg_latency, jitter, packet_loss, throughput]
    
    # Target/expected values for comparison
    targets = [12.5, 5, 1.0, 100]  # Expected values
    
    # Colors based on performance
    colors_bars = []
    for val, target in zip(values, targets):
        if val <= target * 1.1:  # Within 10% of target
            colors_bars.append('#27ae60')  # Green (good)
        elif val <= target * 1.3:  # Within 30% of target
            colors_bars.append('#f39c12')  # Orange (acceptable)
        else:
            colors_bars.append('#e74c3c')  # Red (poor)
    
    x = np.arange(len(metrics))
    width = 0.35
    
    # Plot actual values
    bars1 = ax.bar(x - width/2, values, width, label='Actual', color=colors_bars, alpha=0.8)
    
    # Plot target values
    bars2 = ax.bar(x + width/2, targets, width, label='Target', color='gray', alpha=0.5)
    
    # Add value labels
    for bar, val in zip(bars1, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_ylabel('Value')
    ax.set_title('Network Performance (N3IWF + IPsec)')
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add status text
    ipsec_status = callbox.get('ipsec_status', 'UNKNOWN')
    status_color = 'green' if ipsec_status == 'ESTABLISHED' else 'red'
    ax.text(0.02, 0.98, f'IPsec: {ipsec_status}', 
            transform=ax.transAxes, fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor=status_color, alpha=0.3))


def plot_network_details_table(stats, ax):
    """Plot detailed network statistics table"""
    ax.axis('tight')
    ax.axis('off')
    
    if not stats.get('callbox'):
        ax.text(0.5, 0.5, 'No Network Data Available', ha='center', va='center', fontsize=12)
        return
    
    callbox = stats['callbox']
    n3iwf = stats.get('n3iwf', {})
    
    # Calculate metrics
    packet_loss_rate = (callbox.get('packets_dropped', 0) / max(callbox.get('packets_sent', 1), 1)) * 100
    uptime_hours = callbox.get('uptime', 0) / 3600
    
    # Create table data
    table_data = []
    table_data.append(['Metric', 'Value', 'Status'])
    
    # IPsec Status
    ipsec_status = callbox.get('ipsec_status', 'UNKNOWN')
    ipsec_emoji = '✅' if ipsec_status == 'ESTABLISHED' else '❌'
    table_data.append(['IPsec Tunnel', ipsec_status, ipsec_emoji])
    
    # Latency
    avg_latency = callbox.get('avg_latency_ms', 0)
    latency_status = '✅' if avg_latency <= 15 else '⚠️' if avg_latency <= 25 else '❌'
    table_data.append(['Avg Latency', f'{avg_latency:.2f} ms', latency_status])
    
    # Packet Loss
    loss_status = '✅' if packet_loss_rate <= 1.5 else '⚠️' if packet_loss_rate <= 3 else '❌'
    table_data.append(['Packet Loss', f'{packet_loss_rate:.2f} %', loss_status])
    
    # Throughput
    throughput = callbox.get('current_bandwidth_mbps', 100)
    throughput_status = '✅' if throughput >= 90 else '⚠️' if throughput >= 70 else '❌'
    table_data.append(['Throughput', f'{throughput:.0f} Mbps', throughput_status])
    
    # Packets Sent
    packets_sent = callbox.get('packets_sent', 0)
    table_data.append(['Packets Sent', f'{packets_sent:,}', '-'])
    
    # Packets Received
    packets_received = callbox.get('packets_received', 0)
    table_data.append(['Packets Received', f'{packets_received:,}', '-'])
    
    # Packets Dropped
    packets_dropped = callbox.get('packets_dropped', 0)
    table_data.append(['Packets Dropped', f'{packets_dropped:,}', '-'])
    
    # Uptime
    uptime_status = '✅' if uptime_hours >= 1 else '-'
    table_data.append(['Uptime', f'{uptime_hours:.2f} hours', uptime_status])
    
    # 5G Core Status
    amf_status = callbox.get('amf_status', 'UNKNOWN')
    amf_emoji = '✅' if amf_status == 'RUNNING' else '❌'
    table_data.append(['AMF Status', amf_status, amf_emoji])
    
    smf_status = callbox.get('smf_status', 'UNKNOWN')
    smf_emoji = '✅' if smf_status == 'RUNNING' else '❌'
    table_data.append(['SMF Status', smf_status, smf_emoji])
    
    upf_status = callbox.get('upf_status', 'UNKNOWN')
    upf_emoji = '✅' if upf_status == 'RUNNING' else '❌'
    table_data.append(['UPF Status', upf_status, upf_emoji])
    
    # Create table
    table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                     colWidths=[0.35, 0.35, 0.15])
    
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)
    
    # Style header row
    for i in range(3):
        cell = table[(0, i)]
        cell.set_facecolor('#3498db')
        cell.set_text_props(weight='bold', color='white')
    
    # Color code status column
    for i in range(1, len(table_data)):
        status = table_data[i][2]
        cell = table[(i, 2)]
        if status == '✅':
            cell.set_facecolor('#d5f4e6')
        elif status == '⚠️':
            cell.set_facecolor('#fff3cd')
        elif status == '❌':
            cell.set_facecolor('#f8d7da')
    
    ax.set_title('Network Performance Details (N3IWF + 5G Core)', fontsize=12, fontweight='bold', pad=20)
    ax.axis('off')


# ══════════════════════════════════════════════════════════════════════════════
#  Main Analysis
# ══════════════════════════════════════════════════════════════════════════════

def generate_all_plots():
    """Generate all plots and save to PDF"""
    print("="*70)
    print("  COMPLETE ANALYSIS - Generating All Plots")
    print("="*70)
    
    # Load data
    print("\n[1/4] Loading data...")
    data = load_comparison_data()
    network_stats = load_network_stats()
    
    if not data:
        print("❌ No data found in comparison.csv")
        print("   Run the system first: python3 main/real/run_real.py")
        return False
    
    print(f"✅ Loaded {len(data)} data points")
    
    # Compute statistics
    print("\n[2/4] Computing statistics...")
    stats = compute_statistics(data)
    
    # Print summary
    print("\n" + "="*70)
    print("  SUMMARY STATISTICS")
    print("="*70)
    print(f"  Total Steps:        {stats['total_steps']}")
    print(f"  RB Steps:           {stats['rb_steps']}")
    print(f"  FQL Steps:          {stats['fql_steps']}")
    print(f"  DQN Steps:          {stats['dqn_steps']}")
    print()
    print(f"  pH:                 {stats['pH_mean']:.3f} ± {stats['pH_std']:.3f}")
    print(f"  Temperature:        {stats['T_mean']:.2f} ± {stats['T_std']:.2f} °C")
    print()
    print(f"  RB Avg Reward:      {stats['rb_reward_mean']:.4f}")
    print(f"  FQL Avg Reward:     {stats['fql_reward_mean']:.4f}")
    print(f"  DQN Avg Reward:     {stats['dqn_reward_mean']:.4f}")
    print()
    print(f"  Total Energy Cost:  {stats['total_energy']:.2f}")
    print("="*70)
    
    # Save summary to CSV
    with open(SUMMARY_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Metric', 'Value'])
        for key, value in stats.items():
            writer.writerow([key, value])
    
    print(f"\n✅ Summary saved: {SUMMARY_CSV}")
    
    # Generate plots
    print("\n[3/4] Generating plots...")
    
    fig = plt.figure(figsize=(16, 24))
    fig.suptitle('Complete Analysis - Aquaculture Edge AI with N3IWF', 
                 fontsize=16, fontweight='bold', y=0.995)
    
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.35, wspace=0.30)
    
    # Plot 1: Water Quality
    ax1 = fig.add_subplot(gs[0, :])
    plot_water_quality(data, ax1)
    
    # Plot 2: Progressive Learning
    ax2 = fig.add_subplot(gs[1, :])
    plot_progressive_learning(data, ax2)
    
    # Plot 3: Action Distribution
    ax3 = fig.add_subplot(gs[2, 0])
    plot_action_distribution(data, ax3)
    
    # Plot 4: Phase Comparison
    ax4 = fig.add_subplot(gs[2, 1])
    plot_phase_comparison(data, ax4)
    
    # Plot 5: Energy Consumption
    ax5 = fig.add_subplot(gs[3, 0])
    plot_energy_consumption(data, ax5)
    
    # Plot 6: Network Stats
    ax6 = fig.add_subplot(gs[3, 1])
    plot_network_stats(network_stats, ax6)
    
    # Plot 7: Network Details Table (NEW!)
    ax7 = fig.add_subplot(gs[4, :])
    plot_network_details_table(network_stats, ax7)
    
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    
    # Save to PDF
    print("\n[4/4] Saving to PDF...")
    pdf_path = PDF_OUTPUT
    plt.savefig(pdf_path, dpi=150, bbox_inches='tight')
    print(f"✅ PDF saved: {pdf_path}")
    
    # Save individual plots
    for i, ax in enumerate([ax1, ax2, ax3, ax4, ax5, ax6, ax7], 1):
        extent = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        fig.savefig(os.path.join(PLOTS_DIR, f'plot_{i}.png'), 
                   bbox_inches=extent.expanded(1.2, 1.2), dpi=150)
    
    print(f"✅ Individual plots saved: {PLOTS_DIR}/")
    
    plt.show()
    
    print("\n" + "="*70)
    print("  ✅ ANALYSIS COMPLETE!")
    print("="*70)
    print(f"  PDF:      {pdf_path}")
    print(f"  Summary:  {SUMMARY_CSV}")
    print(f"  Plots:    {PLOTS_DIR}/")
    print("="*70 + "\n")
    
    return True


if __name__ == "__main__":
    success = generate_all_plots()
    sys.exit(0 if success else 1)
