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

import shutil

# Input files
def get_latest_session_dir() -> str:
    if not os.path.exists(RESULTS_REAL):
        return RESULTS_REAL
        
    sessions = [d for d in os.listdir(RESULTS_REAL) if d.startswith("session_") and os.path.isdir(os.path.join(RESULTS_REAL, d))]
    if not sessions:
        return RESULTS_REAL
        
    sessions.sort(reverse=True)
    return os.path.join(RESULTS_REAL, sessions[0])

if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    LATEST_SESSION = os.path.abspath(sys.argv[1])
else:
    LATEST_SESSION = get_latest_session_dir()

COMPARISON_CSV = os.path.join(LATEST_SESSION, "comparison.csv")
CALLBOX_STATS = os.path.join(LATEST_SESSION, "callbox_stats.json")
N3IWF_STATUS = os.path.join(LATEST_SESSION, "n3iwf_status.json")
NETWORK_TIMELINE = os.path.join(LATEST_SESSION, "network_timeline.csv")

def archive_network_stats():
    """Copy live network stats to the session folder for permanent archiving"""
    if LATEST_SESSION == RESULTS_REAL:
        return
        
    live_callbox = os.path.join(RESULTS_NETWORK, "callbox_stats.json")
    live_n3iwf = os.path.join(RESULTS_NETWORK, "n3iwf_status.json")
    live_timeline = os.path.join(RESULTS_NETWORK, "network_timeline.csv")
    
    if os.path.exists(live_callbox):
        shutil.copy2(live_callbox, CALLBOX_STATS)
    if os.path.exists(live_n3iwf):
        shutil.copy2(live_n3iwf, N3IWF_STATUS)
    if os.path.exists(live_timeline):
        shutil.copy2(live_timeline, NETWORK_TIMELINE)

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
        with open(COMPARISON_CSV, 'r', encoding='utf-8') as f:
            content = f.read().replace('\x00', '')
            import io
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                try:
                    # Skip rows with missing or None values
                    if not row.get('real_step') or not row.get('pH') or not row.get('T_C'):
                        continue
                    
                    # Parse which action the AI took based on mode
                    mode = row.get('mode', 'Unknown')
                    if mode == 'RB':
                        action = int(row.get('rb_risk', 0))
                        correct = int(row.get('rb_correct', 0))
                    elif mode == 'FQL':
                        action = int(row.get('fql_risk', 0))
                        correct = int(row.get('fql_correct', 0))
                    elif mode == 'DQN':
                        action = int(row.get('dqn_risk', 0))
                        correct = int(row.get('dqn_correct', 0))
                    else:
                        action = int(row.get('actual_risk', 0))
                        correct = 0

                    data.append({
                        'step': int(row['real_step']),
                        'pH': float(row['pH']),
                        'T': float(row['T_C']),
                        'mode': mode,
                        'actual_risk': int(row.get('actual_risk', 0)),
                        'action': action,
                        'reward': 1.0 if correct == 1 else -1.0,
                        'correct': correct,
                        'nh3': float(row.get('NH3_pct', 0)),
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


def load_network_timeline():
    """Load network timeline data"""
    timeline = []
    try:
        with open(NETWORK_TIMELINE, 'r', encoding='utf-8') as f:
            content = f.read().replace('\x00', '')
            import io
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                try:
                    timeline.append({
                        'uptime': float(row['uptime']),
                        'latency': float(row['avg_latency_ms']),
                        'jitter': float(row['jitter_ms']),
                        'packets_dropped': int(row['packets_dropped'])
                    })
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    
    return timeline


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
    }
    
    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  Plotting Functions
# ══════════════════════════════════════════════════════════════════════════════

def plot_ph_trend(data, ax):
    """Plot pH trend over time"""
    steps = [d['step'] for d in data]
    pH = [d['pH'] for d in data]
    
    ax.plot(steps, pH, 'b-', label='pH Level', linewidth=1.5, alpha=0.8)
    
    # Safe zones
    ax.axhspan(6.5, 8.5, alpha=0.1, color='green', label='pH Safe Zone (6.5 - 8.5)')
    
    ax.set_xlabel('Step', fontweight='bold')
    ax.set_ylabel('pH', color='b', fontweight='bold')
    ax.set_title('pH Level Trend', fontweight='bold')
    
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, alpha=0.3)


def plot_temperature_trend(data, ax):
    """Plot Temperature trend over time"""
    steps = [d['step'] for d in data]
    T = [d['T'] for d in data]
    
    ax.plot(steps, T, 'r-', label='Temperature (°C)', linewidth=1.5, alpha=0.8)
    
    # Safe zones
    ax.axhspan(26, 30, alpha=0.1, color='orange', label='Temp Safe Zone (26 - 30°C)')
    
    ax.set_xlabel('Step', fontweight='bold')
    ax.set_ylabel('Temperature (°C)', color='r', fontweight='bold')
    ax.set_title('Temperature Trend', fontweight='bold')
    
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, alpha=0.3)


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
    all_correct = [d['correct'] for d in data]
    window = min(50, len(data) // 10)
    if window > 0:
        rolling_avg = np.convolve(all_correct, np.ones(window)/window, mode='same')
        ax.plot(all_steps, rolling_avg, 'k-', linewidth=2, label='Rolling Accuracy', alpha=0.8)
    
    ax.axhline(0, color='gray', linestyle=':', linewidth=1)
    ax.set_xlabel('Step')
    ax.set_ylabel('Reward / Correctness')
    ax.set_title('Progressive Learning: RB → FQL → DQN')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


def plot_action_distribution(data, ax):
    """Plot action distribution by phase"""
    action_names = ['SAFE', 'CAUTION', 'WARNING', 'CRITICAL']
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


    pass


def plot_nh3_toxicity(data, ax):
    """Plot NH3 toxicity fraction over time"""
    steps = [d['step'] for d in data]
    nh3 = [d['nh3'] for d in data]
    modes = [d['mode'] for d in data]
    
    # Split by mode for different colors
    for mode, color, label in [('RB', '#e74c3c', 'Rule-Based'), 
                               ('FQL', '#f39c12', 'FQL'), 
                               ('DQN', '#27ae60', 'DQN')]:
        mask = [m == mode for m in modes]
        if any(mask):
            x = [s for s, m in zip(steps, mask) if m]
            y = [n for n, m in zip(nh3, mask) if m]
            ax.plot(x, y, color=color, linewidth=1.5, alpha=0.8, label=label)
            
    # Danger zones
    ax.axhline(5.0, color='orange', linestyle=':', linewidth=1.5, label='Warning Threshold (>5%)')
    ax.axhline(10.0, color='red', linestyle='--', linewidth=1.5, label='Critical Threshold (>10%)')
    
    ax.set_ylabel('NH3 Fraction (%)', fontweight='bold')
    ax.set_title('Ammonia (NH3) Toxicity Evolution', fontweight='bold')
    ax.set_xlabel('Step')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)


def plot_epsilon_decay(data, ax):
    """Plot exploration rate (Epsilon) decay over time"""
    steps = [d['step'] for d in data]
    epsilon = [d['epsilon'] for d in data]
    
    ax.plot(steps, epsilon, color='#9b59b6', linewidth=2, label='Epsilon (Exploration Rate)')
    ax.axhline(0.01, color='gray', linestyle='--', linewidth=1.5, label='Min Epsilon (0.01)')
    
    ax.set_ylabel('Epsilon Value', fontweight='bold')
    ax.set_title('AI Exploration vs Exploitation (FQL Phase)', fontweight='bold')
    ax.set_xlabel('Step')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)


def plot_accuracy_comparison(data, ax):
    """Plot overall prediction accuracy comparison"""
    rb_correct = sum(1 for d in data if d['mode'] == 'RB' and d['correct'] == 1)
    rb_total = sum(1 for d in data if d['mode'] == 'RB')
    
    fql_correct = sum(1 for d in data if d['mode'] == 'FQL' and d['correct'] == 1)
    fql_total = sum(1 for d in data if d['mode'] == 'FQL')
    
    dqn_correct = sum(1 for d in data if d['mode'] == 'DQN' and d['correct'] == 1)
    dqn_total = sum(1 for d in data if d['mode'] == 'DQN')
    
    rb_acc = (rb_correct / rb_total * 100) if rb_total > 0 else 0
    fql_acc = (fql_correct / fql_total * 100) if fql_total > 0 else 0
    dqn_acc = (dqn_correct / dqn_total * 100) if dqn_total > 0 else 0
    
    models = ['Rule-Based', 'FQL', 'DQN']
    accuracies = [rb_acc, fql_acc, dqn_acc]
    colors = ['#e74c3c', '#f39c12', '#27ae60']
    
    bars = ax.bar(models, accuracies, color=colors, alpha=0.8, width=0.6)
    
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')
                
    ax.set_ylim(0, 110)
import matplotlib.gridspec as gridspec

def plot_confusion_matrix(data, grafik_dir):
    """Plot confusion matrix of AI Predictions vs Ground Truth (3 columns)"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('AI Confusion Matrix (RB vs FQL vs DQN)', fontweight='bold')
    
    phases = ['RB', 'FQL', 'DQN']
    
    for i, phase in enumerate(phases):
        ax = axes[i]
        
        phase_data = [d for d in data if d['mode'] == phase]
        if not phase_data:
            ax.text(0.5, 0.5, f"{phase}\nNot Available", ha='center', va='center', fontsize=12)
            ax.set_xticks([])
            ax.set_yticks([])
            continue
            
        matrix = np.zeros((4, 4), dtype=int)
        for d in phase_data:
            actual = d['actual_risk']
            predicted = d['action']
            if 0 <= actual <= 3 and 0 <= predicted <= 3:
                matrix[actual][predicted] += 1
                
        # Normalize
        row_sums = matrix.sum(axis=1)
        row_sums[row_sums == 0] = 1 # Avoid division by zero
        cm_norm = matrix.astype('float') / row_sums[:, np.newaxis]
        
        im = ax.imshow(cm_norm, interpolation='nearest', cmap='Blues', vmin=0, vmax=1)
        
        for r in range(4):
            for c in range(4):
                color = "white" if cm_norm[r, c] > 0.5 else "black"
                ax.text(c, r, f"{matrix[r, c]}\n({cm_norm[r, c]:.0%})", 
                        ha="center", va="center", color=color, fontweight='bold', fontsize=8)
                
        labels = ['SAFE', 'CAUTION', 'WARNING', 'CRIT']
        ax.set_xticks(np.arange(4))
        ax.set_yticks(np.arange(4))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        
        if i == 0:
            ax.set_yticklabels(labels, fontsize=8)
            ax.set_ylabel('Actual Risk Level', fontweight='bold', fontsize=9)
        else:
            ax.set_yticklabels([])
            
        ax.set_xlabel('Predicted Risk Level', fontweight='bold', fontsize=9)
        
        correct = sum(1 for d in phase_data if d['correct'] == 1)
        acc = (correct / len(phase_data) * 100) if len(phase_data) > 0 else 0
        
        ax.set_title(f'{phase}\nAccuracy: {acc:.1f}%', fontweight='bold', fontsize=10)

    plt.tight_layout()
    plt.savefig(os.path.join(grafik_dir, '07_confusion_matrix.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)
def plot_policy_map(data, ax):
    """Plot AI Policy Map (Decision Boundary over State Space)"""
    pH_vals = [d['pH'] for d in data]
    T_vals = [d['T'] for d in data]
    actions = [d['action'] for d in data]
    
    colors = ['#3498db', '#f1c40f', '#e67e22', '#e74c3c'] # Safe, Caution, Warn, Crit
    labels = ['SAFE', 'CAUTION', 'WARNING', 'CRITICAL']
    
    for i in range(4):
        mask = [a == i for a in actions]
        if any(mask):
            x = [p for p, m in zip(pH_vals, mask) if m]
            y = [t for t, m in zip(T_vals, mask) if m]
            ax.scatter(x, y, c=colors[i], label=labels[i], alpha=0.6, edgecolors='none', s=30)
            
    # Add safe zone box
    rect = plt.Rectangle((6.5, 26), 2.0, 4.0, fill=False, edgecolor='green', 
                         linestyle='--', linewidth=2, label='Optimal Target Zone')
    ax.add_patch(rect)
    
    ax.set_xlabel('pH Level', fontweight='bold')
    ax.set_ylabel('Temperature (°C)', fontweight='bold')
    ax.set_title('AI Learned Policy (State Space Map)', fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)


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
    ipsec_emoji = '[OK]' if ipsec_status == 'ESTABLISHED' else '[FAIL]'
    table_data.append(['IPsec Tunnel', ipsec_status, ipsec_emoji])
    
    # Latency
    avg_latency = callbox.get('avg_latency_ms', 0)
    latency_status = '[OK]' if avg_latency <= 15 else '[WARN]' if avg_latency <= 25 else '[FAIL]'
    table_data.append(['Avg Latency', f'{avg_latency:.2f} ms', latency_status])
    
    # Packet Loss
    loss_status = '[OK]' if packet_loss_rate <= 1.5 else '[WARN]' if packet_loss_rate <= 3 else '[FAIL]'
    table_data.append(['Packet Loss', f'{packet_loss_rate:.2f} %', loss_status])
    
    # Throughput
    throughput = callbox.get('current_bandwidth_mbps', 100)
    throughput_status = '[OK]' if throughput >= 90 else '[WARN]' if throughput >= 70 else '[FAIL]'
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
    uptime_status = '[OK]' if uptime_hours >= 1 else '-'
    table_data.append(['Uptime', f'{uptime_hours:.2f} hours', uptime_status])
    
    # 5G Core Status
    amf_status = callbox.get('amf_status', 'UNKNOWN')
    amf_emoji = '[OK]' if amf_status == 'RUNNING' else '[FAIL]'
    table_data.append(['AMF Status', amf_status, amf_emoji])
    
    smf_status = callbox.get('smf_status', 'UNKNOWN')
    smf_emoji = '[OK]' if smf_status == 'RUNNING' else '[FAIL]'
    table_data.append(['SMF Status', smf_status, smf_emoji])
    
    upf_status = callbox.get('upf_status', 'UNKNOWN')
    upf_emoji = '[OK]' if upf_status == 'RUNNING' else '[FAIL]'
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
        if status == '[OK]':
            cell.set_facecolor('#d5f4e6')
        elif status == '[WARN]':
            cell.set_facecolor('#fff3cd')
        elif status == '[FAIL]':
            cell.set_facecolor('#f8d7da')
    
    ax.set_title('Network Performance Details (N3IWF + 5G Core)', fontsize=12, fontweight='bold', pad=20)
    ax.axis('off')


def plot_latency_timeline(timeline_data, ax):
    """Plot network latency over Uptime"""
    if not timeline_data:
        ax.text(0.5, 0.5, 'No Timeline Data Available', ha='center', va='center', fontsize=12)
        ax.set_title('Network Latency Timeline')
        return
        
    uptimes = [d['uptime'] / 60 for d in timeline_data] # Convert to minutes
    latencies = [d['latency'] for d in timeline_data]
    
    ax.plot(uptimes, latencies, color='#2ecc71', linewidth=1.5, label='Avg Latency', alpha=0.8)
    ax.axhline(15.0, color='red', linestyle='--', linewidth=1, label='Max Target (15ms)')
    
    ax.set_xlabel('Uptime (Minutes)', fontweight='bold')
    ax.set_ylabel('Latency (ms)', fontweight='bold')
    ax.set_title('N3IWF Latency Timeline', fontweight='bold')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)


def plot_jitter_timeline(timeline_data, ax):
    """Plot network jitter over Uptime"""
    if not timeline_data:
        ax.text(0.5, 0.5, 'No Timeline Data Available', ha='center', va='center', fontsize=12)
        ax.set_title('Network Jitter Timeline')
        return
        
    uptimes = [d['uptime'] / 60 for d in timeline_data] # Convert to minutes
    jitters = [d['jitter'] for d in timeline_data]
    
    ax.plot(uptimes, jitters, color='#9b59b6', linewidth=1.5, label='Jitter', alpha=0.8)
    ax.axhline(5.0, color='red', linestyle='--', linewidth=1, label='Max Target (5ms)')
    
    ax.set_xlabel('Uptime (Minutes)', fontweight='bold')
    ax.set_ylabel('Jitter (ms)', fontweight='bold')
    ax.set_title('N3IWF Jitter Timeline', fontweight='bold')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)


# ══════════════════════════════════════════════════════════════════════════════
#  Main Analysis
# ══════════════════════════════════════════════════════════════════════════════

def generate_all_plots():
    """Generate all plots individually and save to session grafik directory"""
    print("="*70)
    print("  COMPLETE ANALYSIS - Generating Individual Plots")
    print("="*70)
    
    # Load data
    print("\n[1/4] Loading data...")
    archive_network_stats()
    data = load_comparison_data()
    network_stats = load_network_stats()
    network_timeline = load_network_timeline()
    
    if not data:
        print("❌ No data found in comparison.csv")
        print("   Run the system first: python3 main/real/run_real.py")
        return False
    
    print(f"[OK] Loaded {len(data)} data points")
    
    # Create grafik directory in the current session folder
    grafik_dir = os.path.join(LATEST_SESSION, "grafik")
    os.makedirs(grafik_dir, exist_ok=True)
    
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
    print("="*70)
    
    # Save summary to CSV in session dir
    session_summary = os.path.join(LATEST_SESSION, "summary.csv")
    with open(session_summary, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Metric', 'Value'])
        for key, value in stats.items():
            writer.writerow([key, value])
    
    print(f"\n[OK] Summary saved: {session_summary}")
    
    # Generate plots
    print(f"\n[3/4] Generating plots individually to {grafik_dir}...")
    
    # Helper to save individual plots
    def save_single_plot(filename, plot_func, *args, figsize=(10, 6)):
        fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
        plot_func(*args, ax)
        path = os.path.join(grafik_dir, filename)
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  - Saved {filename}")

    save_single_plot('01a_ph_trend.png', plot_ph_trend, data, figsize=(10, 5))
    save_single_plot('01b_temperature_trend.png', plot_temperature_trend, data, figsize=(10, 5))
    save_single_plot('02_progressive_learning.png', plot_progressive_learning, data, figsize=(12, 6))
    save_single_plot('03_action_distribution.png', plot_action_distribution, data)
    save_single_plot('04_nh3_toxicity.png', plot_nh3_toxicity, data)
    save_single_plot('05_epsilon_decay.png', plot_epsilon_decay, data)
    save_single_plot('06_accuracy_comparison.png', plot_accuracy_comparison, data)
    
    # Confusion matrix has a unique signature
    plot_confusion_matrix(data, grafik_dir)
    print(f"  - Saved 07_confusion_matrix.png")
    
    save_single_plot('08_policy_map.png', plot_policy_map, data)
    save_single_plot('09_latency_timeline.png', plot_latency_timeline, network_timeline, figsize=(12, 6))
    save_single_plot('10_jitter_timeline.png', plot_jitter_timeline, network_timeline, figsize=(12, 6))
    save_single_plot('11_network_stats.png', plot_network_stats, network_stats)
    save_single_plot('12_network_details_table.png', plot_network_details_table, network_stats, figsize=(8, 4))
    
    print("\n" + "="*70)
    print("  [OK] ANALYSIS COMPLETE!")
    print("="*70)
    print(f"  Semua grafik berhasil disimpan di:")
    print(f"  {grafik_dir}")
    print("="*70 + "\n")
    
    return True

if __name__ == "__main__":
    success = generate_all_plots()
    sys.exit(0 if success else 1)
