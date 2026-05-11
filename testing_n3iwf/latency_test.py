#!/usr/bin/env python3
"""
latency_test.py - 5G N3IWF Network Performance Measurement
============================================================
Mengukur latency, jitter, dan PDR antara RPi5 dan Callbox
melalui tunnel IPsec (simulasi N3IWF).

Jalankan di RPi5:
    python3 testing_n3iwf/latency_test.py

Output:
    - results/network/latency_results.csv
    - results/network/latency_plot.png
    - results/network/network_summary.txt
"""

import os
import csv
import time
import subprocess
import statistics
import json
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARN] matplotlib not found. Install: pip3 install matplotlib")

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_IP    = "192.168.100.101"   # Callbox IP
N_PINGS      = 100                 # Total ping count
PING_INTERVAL = 0.5               # Seconds between pings

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR     = os.path.join(BASE_DIR, "results", "network")
CSV_PATH    = os.path.join(OUT_DIR, "latency_results.csv")
PLOT_PATH   = os.path.join(OUT_DIR, "latency_plot.png")
SUMMARY_PATH = os.path.join(OUT_DIR, "network_summary.json")

os.makedirs(OUT_DIR, exist_ok=True)

# ── Single Ping ────────────────────────────────────────────────────────────────
def ping_once(target: str) -> float | None:
    """Ping target once. Returns RTT in ms, or None if failed."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", target],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    rtt_str = line.split("time=")[1].split(" ")[0]
                    return float(rtt_str)
    except Exception:
        pass
    return None

# ── Check IPsec tunnel ────────────────────────────────────────────────────────
def check_ipsec() -> bool:
    try:
        result = subprocess.run(
            ["sudo", "ipsec", "statusall"],
            capture_output=True, text=True, timeout=5
        )
        return "ESTABLISHED" in result.stdout
    except Exception:
        return False

# ── Main ─────────────────────────────────────────────────────────────────────
def run_latency_test():
    print("\n" + "="*60)
    print("  5G N3IWF Network Performance Measurement")
    print("="*60)
    print(f"  Target    : {TARGET_IP} (Callbox / 5G Core)")
    print(f"  Pings     : {N_PINGS}")
    print(f"  Interval  : {PING_INTERVAL}s")
    print(f"  Output    : {OUT_DIR}")
    print("="*60)

    # Check IPsec
    ipsec_ok = check_ipsec()
    print(f"\n  IPsec Tunnel : {'ESTABLISHED ✅' if ipsec_ok else 'NOT ACTIVE ⚠️'}")
    if not ipsec_ok:
        print("  [WARN] Tunnel not active. Run: sudo ipsec up aquaculture-n3iwf")
    print()

    # Run pings
    latencies = []
    lost = 0

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seq", "timestamp", "rtt_ms", "status"])

        for i in range(1, N_PINGS + 1):
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            rtt = ping_once(TARGET_IP)

            if rtt is not None:
                latencies.append(rtt)
                writer.writerow([i, ts, rtt, "OK"])
                bar = "█" * int(rtt / 2)
                print(f"  [{i:3d}/{N_PINGS}] {rtt:6.2f} ms  {bar}")
            else:
                lost += 1
                writer.writerow([i, ts, "", "LOST"])
                print(f"  [{i:3d}/{N_PINGS}]  LOST ✗")

            if i < N_PINGS:
                time.sleep(PING_INTERVAL)

    # ── Statistics ────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)

    if latencies:
        avg   = statistics.mean(latencies)
        mn    = min(latencies)
        mx    = max(latencies)
        jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
        pdr   = len(latencies) / N_PINGS * 100
        p95   = sorted(latencies)[int(len(latencies) * 0.95)]
        p99   = sorted(latencies)[int(len(latencies) * 0.99)]

        print(f"  Min Latency   : {mn:.2f} ms")
        print(f"  Avg Latency   : {avg:.2f} ms")
        print(f"  Max Latency   : {mx:.2f} ms")
        print(f"  Jitter (σ)    : {jitter:.2f} ms")
        print(f"  95th pct      : {p95:.2f} ms")
        print(f"  99th pct      : {p99:.2f} ms")
        print(f"  PDR           : {pdr:.1f}% ({len(latencies)}/{N_PINGS})")
        print(f"  Packets Lost  : {lost}")
        print(f"  IPsec Encrypt : AES-128-CBC (IKEv2)")
        print("="*60)

        # Save summary JSON
        summary = {
            "timestamp": datetime.now().isoformat(),
            "target": TARGET_IP,
            "n_pings": N_PINGS,
            "ipsec_active": ipsec_ok,
            "min_ms": round(mn, 3),
            "avg_ms": round(avg, 3),
            "max_ms": round(mx, 3),
            "jitter_ms": round(jitter, 3),
            "p95_ms": round(p95, 3),
            "p99_ms": round(p99, 3),
            "pdr_pct": round(pdr, 1),
            "packets_lost": lost,
            "encryption": "AES-128-CBC IKEv2"
        }
        with open(SUMMARY_PATH, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n  Summary saved : {SUMMARY_PATH}")

        # ── Plot ─────────────────────────────────────────────────────────────
        if HAS_MATPLOTLIB:
            generate_plot(latencies, lost, avg, mn, mx, jitter, pdr)
    else:
        print("  [ERROR] No successful pings! Check network connectivity.")

def generate_plot(latencies, lost, avg, mn, mx, jitter, pdr):
    n = len(latencies)
    indices = list(range(1, n + 1))

    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor('#0d1117')
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    style = {
        'axes.facecolor': '#161b22',
        'axes.edgecolor': '#30363d',
        'axes.labelcolor': '#e6edf3',
        'text.color': '#e6edf3',
        'xtick.color': '#7d8590',
        'ytick.color': '#7d8590',
        'grid.color': '#21262d',
        'grid.alpha': 0.7,
    }
    plt.rcParams.update(style)

    # 1. Latency over time
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(indices, latencies, color='#58a6ff', linewidth=0.8,
             alpha=0.7, label='RTT')
    ax1.fill_between(indices, latencies, alpha=0.15, color='#58a6ff')
    ax1.axhline(avg, color='#3fb950', linewidth=1.5, linestyle='--',
                label=f'Avg: {avg:.2f} ms')
    ax1.axhline(mn, color='#bc8cff', linewidth=1, linestyle=':',
                label=f'Min: {mn:.2f} ms')
    ax1.axhline(mx, color='#f85149', linewidth=1, linestyle=':',
                label=f'Max: {mx:.2f} ms')
    ax1.set_title('RPi5 → Callbox Latency over Time (IPsec N3IWF Tunnel)',
                  fontsize=12, fontweight='bold', pad=10)
    ax1.set_xlabel('Ping Sequence'); ax1.set_ylabel('RTT (ms)')
    ax1.legend(fontsize=9); ax1.grid(True)

    # 2. Histogram
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.hist(latencies, bins=20, color='#58a6ff', alpha=0.8, edgecolor='#30363d')
    ax2.axvline(avg, color='#3fb950', linewidth=2, linestyle='--',
                label=f'Mean: {avg:.2f}ms')
    ax2.set_title('Latency Distribution', fontsize=11, fontweight='bold')
    ax2.set_xlabel('RTT (ms)'); ax2.set_ylabel('Count')
    ax2.legend(fontsize=9); ax2.grid(True)

    # 3. Summary metrics box
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis('off')
    metrics = [
        ['Metric', 'Value'],
        ['Min Latency', f'{mn:.2f} ms'],
        ['Avg Latency', f'{avg:.2f} ms'],
        ['Max Latency', f'{mx:.2f} ms'],
        ['Jitter (σ)', f'{jitter:.2f} ms'],
        ['PDR', f'{pdr:.1f}%'],
        ['Packets Lost', f'{lost}'],
        ['Encryption', 'AES-128 IKEv2'],
        ['Tunnel', 'IPsec N3IWF'],
    ]
    table = ax3.table(cellText=metrics[1:], colLabels=metrics[0],
                      cellLoc='center', loc='center',
                      bbox=[0.05, 0.05, 0.9, 0.9])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, col), cell in table.get_celld().items():
        cell.set_facecolor('#161b22' if row > 0 else '#21262d')
        cell.set_edgecolor('#30363d')
        cell.set_text_props(color='#e6edf3')
    ax3.set_title('Network Summary', fontsize=11, fontweight='bold')

    fig.suptitle('5G N3IWF Network Performance — RPi5 Edge Gateway',
                 fontsize=14, fontweight='bold', y=1.01)

    plt.savefig(PLOT_PATH, dpi=150, bbox_inches='tight',
                facecolor='#0d1117')
    print(f"  Plot saved    : {PLOT_PATH}")
    plt.close()

if __name__ == "__main__":
    run_latency_test()
